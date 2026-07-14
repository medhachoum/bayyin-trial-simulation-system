"""
عُقَد LangGraph — سلوك كل دور. كل عقدة تأخذ الحالة وتُعيد تحديثاً جزئياً.
النموذج يولّد المحتوى؛ والقواعد الحتمية وبوابة الاستشهاد تحرسان الإجراء والإسناد.
يغطّي: المرحلة الابتدائية (مع حلقة المرافعة والخبير) + الاستئناف + التماس م.200.
"""
from __future__ import annotations

from functools import lru_cache

from . import exploits, panel, procedure, prompts, rules, settings
from . import sources as sources_mod
from .audit import event
from .llm import get_llm
from .state import CaseState, Citation, Document, DocType, Ruling
from .tools import tools_for


@lru_cache(maxsize=1)
def _llm():
    return get_llm()


# --- مخططات المخرَج المنظَّم (structured outputs صارمة) ----------------------
_CITATION_ITEMS = {
    "type": "object",
    "properties": {
        "claim": {"type": "string"}, "source_tool": {"type": "string"},
        "source_ref": {"type": "string"}, "quote": {"type": "string"},
    },
    "required": ["claim", "source_tool", "source_ref", "quote"],
    "additionalProperties": False,
}
DEFENSE_SCHEMA = {
    "title": "defense_memo", "type": "object",
    "properties": {
        "title": {"type": "string"}, "body": {"type": "string"},
        "citations": {"type": "array", "items": _CITATION_ITEMS},
    },
    "required": ["title", "body", "citations"], "additionalProperties": False,
}
JUDGMENT_SCHEMA = {
    "title": "judgment", "type": "object",
    "properties": {
        "facts": {"type": "string"}, "reasons": {"type": "string"},
        "operative": {"type": "string"},
        "citations": {"type": "array", "items": _CITATION_ITEMS},
    },
    "required": ["facts", "reasons", "operative", "citations"],
    "additionalProperties": False,
}

_ORDINALS = ["", "الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة"]


# ============================ المرحلة الابتدائية =============================
def router_node(state: CaseState) -> dict:
    """الموجِّه السريع: يصنّف النوع والتعقيد (GPT_ROUTER — الطبقة الأسرع)."""
    res = _llm().complete(
        model=settings.GPT_ROUTER, system=prompts.ROUTER,
        user=f"موضوع الدعوى: {state.get('claim_subject','')}\nقيمتها: {state.get('claim_value','')}",
        role="router",
    )
    data = res.get("data") or {}
    return {
        "case_type": state.get("case_type") or data.get("case_type", "تجاري"),
        "complexity": data.get("complexity", "عادية"),
        "current_phase": "المرحلة الابتدائية",
        "hearing_no": 0, "pleading_rounds": 0,
        "audit_log": [event("الموجِّه", "تصنيف الدعوى", model=settings.GPT_ROUTER, detail=str(data))],
    }


def intake_register_node(state: CaseState) -> dict:
    """قيد الدعوى: تدقيقٌ شكليٌّ حتمي (intake_ok) + فحصُ اختصاصٍ نوعيٍّ تجاري (intake_referred)
    منفصلان: النقص الشكلي يُردّ، وعدم الاختصاص النوعي يُحال — لا يُخلطان."""
    result = rules.validate_claim_sheet(state)
    formal_ok = result.ok
    referred, referral_reason = False, ""
    if formal_ok:  # الاختصاص النوعي يُفحص فقط متى صحّت الصحيفة شكلاً.
        in_scope, reason = rules.commercial_jurisdiction(state)
        referred, referral_reason = (not in_scope), (reason if not in_scope else "")
    accepted = formal_ok and not referred
    note = ""
    if accepted and settings.REGISTRAR_RAG_NOTE:  # ملاحظةٌ استئناسية — نداءٌ قابلٌ للتعطيل
        res = _llm().complete(
            model=settings.GPT_STANDARD, system=prompts.REGISTRAR,
            user=f"دقّق صحيفة الدعوى التالية:\n{_claim_text(state)}",
            tools=tools_for("search_saudi_codes"), role="registrar",
        )
        note = res.get("text", "")
    detail = ("مقبولة. " + note if accepted else
              referral_reason if referred else "؛ ".join(result.issues))
    return {
        "intake_ok": formal_ok, "intake_issues": result.issues,
        "intake_referred": referred, "referral_reason": referral_reason,
        "audit_log": [event("المُسجِّل", "تدقيق صحيفة الدعوى (شكلاً واختصاصاً نوعياً)",
                            model=settings.GPT_STANDARD, detail=detail,
                            sources=["search_saudi_codes"] if accepted else [])],
    }


def mediation_node(state: CaseState) -> dict:
    """المصالحة/الوساطة قبل القيد (م.8 محاكم تجارية): وجوبيةٌ لطيفٍ من الدعاوى؛ تُحاكى
    محاولةُ الصلح ويُوثَّق انتهاؤها بغير اتفاقٍ (شرطُ قبول القيد) — لا تُتخطّى الخطوة."""
    required, why = rules.mediation_required(state)
    if not required:
        return {"mediation_done": True,
                "audit_log": [event("مركز المصالحة", "لا تجب المصالحة قبل القيد لهذه الدعوى",
                                    detail="خارج نطاق الوجوب — تُقيَّد مباشرة.")]}
    doc = Document(doc_type=DocType.CLAIM_SHEET, author_role="مركز المصالحة",
                   title="وثيقة انتهاء المصالحة بغير اتفاق",
                   body=(f"{why}\nعُرض النزاع على المصالحة والوساطة فلم يتوصّل الطرفان إلى صلحٍ "
                         f"خلال المدة النظامية (لا تتجاوز {settings.MEDIATION_WINDOW_DAYS} يوماً)، "
                         "فحُرِّرت هذه الوثيقة ليُقبل قيدُ الدعوى."),
                   event="مصالحة", key="mediation")
    return {"mediation_done": True, "document_ledger": [doc],
            "audit_log": [event("مركز المصالحة", "عرض النزاع على المصالحة قبل القيد (وجوبي)",
                                detail=why + " انتهت بغير اتفاق — تُقيَّد الدعوى.")]}


def route_after_intake(state: CaseState) -> str:
    if not state.get("intake_ok"):
        return "rejected"                    # نقصٌ شكلي → استيفاءٌ خلال المهلة وإلا كأن لم يكن
    if state.get("intake_referred"):
        return "referred"                    # عدم اختصاصٍ نوعي → الحكم بعدم الاختصاص والإحالة
    return "research"


def referred_node(state: CaseState) -> dict:
    """الحكم بعدم الاختصاص النوعي وإحالة الدعوى للجهة المختصّة (لا ردٌّ شكلي — تُنقل الخصومة)."""
    reason = state.get("referral_reason") or "عدم الاختصاص النوعي للمحكمة التجارية."
    return {
        "referral_decision": reason,
        "audit_log": [event("المحكمة", "الحكم بعدم الاختصاص النوعي وإحالة الدعوى",
                            detail=reason)],
    }


def research_node(state: CaseState) -> dict:
    """البحث القضائي: استرجاع المبادئ والسوابق التجارية لتوجيه المحاكاة (مرّةً واحدة)."""
    if state.get("research"):
        return {}
    from . import research as research_mod
    r = research_mod.research(state)
    srcs = r.get("sources") or ["search_commercial_principles",
                                "search_commercial_precedents_1", "search_commercial_precedents_2"]
    return {
        "research": r,
        "audit_log": [event("هيئة البحث القضائي", "استرجاع المبادئ والسوابق التجارية ذات الصلة",
                            model=settings.GPT_STANDARD,
                            detail=(f"مبادئ: {len(r['principles'])} · سوابق: {len(r['precedents'])} · "
                                    f"إشارة الاتجاه (استئناسية): {r['outcome_signal']}"),
                            sources=srcs)],
    }


def rejected_node(state: CaseState) -> dict:
    """نقص الصحيفة قرارٌ إداري من إدارة القيد لا حكمٌ قضائي (م.20 محاكم تجارية):
    مهلةُ استيفاءٍ 15 يوماً، فإن لم تُستوفَ عُدّ الطلب كأن لم يكن، مع حقّ التظلّم."""
    days = settings.CLAIM_CURE_WINDOW_DAYS
    return {"deadlines": {**state.get("deadlines", {}),
                          "استيفاء نواقص الصحيفة": f"{days} يوماً من الإبلاغ"},
            "audit_log": [event("إدارة القيد (قرارٌ إداري)",
                                f"طلبُ استيفاء النواقص خلال {days} يوماً",
                                detail=("؛ ".join(state.get("intake_issues", [])) +
                                        f" — فإن استُوفيت عُدّت الدعوى مقيّدةً من تاريخ الطلب، "
                                        f"وإلا عُدّ الطلب كأن لم يكن؛ ولطالب القيد التظلّم "
                                        f"لرئيس المحكمة خلال {days} يوماً وقراره نهائي."))]}


def notify_defendant_node(state: CaseState) -> dict:
    return {
        "deadlines": {**state.get("deadlines", {}),
                      "مذكرة الدفاع": "قبل الجلسة المحدّدة بيومٍ على الأقل (والجلسة خلال ٢٠ يوماً من القيد)"},
        "audit_log": [event("النظام", "تبليغ المدعى عليه بالدعوى (عبر ناجز، في اليوم التالي للقيد)",
                            detail="تحديد الجلسة الأولى خلال ٢٠ يوماً وضبط ميعاد مذكرة الدفاع")],
    }


def defendant_plea_node(state: CaseState) -> dict:
    """مذكرة جوابية للجولة الحالية — تحترم نصّ المستخدم إن عدّله (تجاوز)."""
    round_no = state.get("pleading_rounds", 0) + 1
    ordinal = _ORDINALS[round_no] if round_no < len(_ORDINALS) else str(round_no)
    key = f"defendant_plea-{round_no}"
    ov = _override(state, key)
    if ov is not None:
        doc = Document(doc_type=DocType.DEFENSE_MEMO, author_role="مدعى عليه",
                       title=f"المذكرة الجوابية {ordinal}", body=ov, hearing_no=state.get("hearing_no", 0),
                       event=f"جوابية {round_no}", key=key, overridden=True)
        return {"document_ledger": [doc], "pleading_rounds": round_no,
                "audit_log": [event("وكيل المدعى عليه", f"المذكرة الجوابية {ordinal} (نصٌّ من المستخدم)")]}

    user = _case_file_text(state) + "\n\nاكتب مذكرتك الجوابية لهذه الجولة رداً على ما استجدّ."
    res = _llm().complete(
        model=_model_for(state), system=prompts.DEFENDANT, user=user,
        tools=tools_for("search_saudi_codes", "search_commercial_principles"),
        schema=DEFENSE_SCHEMA, role="defendant",
    )
    data = res.get("data") or {"title": "مذكرة جوابية", "body": res.get("text", ""), "citations": []}
    cits = _verify_memo_citations(_citations(data), res.get("evidence"))
    doc = Document(
        doc_type=DocType.DEFENSE_MEMO, author_role="مدعى عليه",
        title=data.get("title") or f"المذكرة الجوابية {ordinal}", body=data.get("body", ""),
        citations=cits, hearing_no=state.get("hearing_no", 0),
        event=f"جوابية {round_no}", key=key,
    )
    upd: dict = {
        "document_ledger": [doc], "pleading_rounds": round_no,
        "audit_log": [event("وكيل المدعى عليه", f"تقديم المذكرة الجوابية {ordinal}",
                            model=_model_for(state), detail=_cit_counts(cits),
                            sources=_srcs(doc.citations))],
    }
    if round_no == 1 and exploits.injection_for(state) == "forgery":
        doc.flag = "forged"
        upd["injected_exploit"] = "forgery"
        upd["audit_log"].append(event("وضع التدريب", "حقن مستند مزوّر (خفي عن المحامي)"))
    return upd


def incidents_node(state: CaseState) -> dict:
    """الفصل في الدفوع الشكلية المثارة — بعد تمكين المدعي من الردّ (مبدأ المواجهة):
    لا يُقضى في دفعٍ منهٍ للخصومة من مذكرة المدعى عليه وحدها. الدفوع مستقلّة → متوازية."""
    if state.get("incidents_done"):
        return {}
    invoked = procedure.detect_invoked(state)
    if not invoked:
        return {"incidents_done": True}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(4, len(invoked))) as ex:
        results = list(ex.map(lambda k: procedure.adjudicate_incident(state, k), invoked))
    audit = [event("القاضي", f"الفصل في {r['label']}", model=settings.GPT_PRO,
                   detail=("قُبِل: " if r["upheld"] else "رُفِض: ") + r["operative"][:70],
                   sources=[r["cite"]["system"]] if r.get("cite", {}).get("system") else [])
             for r in results]
    upd: dict = {"incidents_done": True, "incidents": results, "audit_log": audit}
    disp = next((r for r in results if r["dispositive"] and r["upheld"]), None)
    if disp:
        upd["incident_disposition"] = disp
    return upd


def route_after_incidents(state: CaseState) -> str:
    # بعد نقل الفصل في الدفوع إلى ما بعد ردّ المدعي (المواجهة)، الرفض يمضي للجلسة.
    return "incident_ruling" if state.get("incident_disposition") else "hearing_manager"


def incident_ruling_node(state: CaseState) -> dict:
    """حكمٌ بقبول دفعٍ قاطع. عدمُ الاختصاص لا يُنهي الحقّ بل يُحيل: تُنقل الدعوى بحالتها
    إلى المحكمة المختصّة (م.76 مرافعات) — لا مجرّد إنهاء الخصومة."""
    disp = state["incident_disposition"]
    c = disp["cite"]
    operative = disp["operative"]
    if disp.get("key") == "jurisdiction" and "إحالة" not in operative and "تُحال" not in operative:
        operative = (operative.rstrip("۔. ") +
                     "؛ وأمرت بإحالة الدعوى بحالتها إلى المحكمة المختصّة (م.76 مرافعات).")
    ruling = Ruling(facts="فصلٌ في دفعٍ شكليٍّ قاطعٍ أُثير في المرافعة.",
                    reasons=disp["reasoning"], operative=operative,
                    composition=rules.first_instance_composition(state),
                    citations=[Citation(claim=c.get("claim", ""), source_tool=c.get("system", ""),
                                        source_ref=c.get("article", ""), quote=c.get("quote", ""))],
                    confidence="عالية", direction="للمدعى عليه")
    ruling = rules.determine_appealability({**state, "judgment": ruling})  # type: ignore
    label = ("قبول الدفع بعدم الاختصاص — إحالةٌ للمحكمة المختصّة"
             if disp.get("key") == "jurisdiction" else "حكمٌ بقبول دفعٍ قاطع (إنهاء الدعوى)")
    return {"judgment": ruling,
            "appeal_window_days": rules.appeal_window_days(state),
            "audit_log": [event("المحكمة", label,
                                detail=f"{disp['label']} — {'قابل للاستئناف' if ruling.appealable else 'نهائي'}")]}


def plaintiff_plea_node(state: CaseState) -> dict:
    """رد المدعي (المحامي البشري) — يحترم نصّ المستخدم إن عدّله."""
    round_no = state.get("pleading_rounds", 0)
    key = f"plaintiff_plea-{round_no}"
    scripted = list(state.get("scripted_plaintiff_replies", []) or [])
    ov = _override(state, key)
    overridden = ov is not None
    if overridden:
        reply_text, no_more = ov, (len(scripted) == 0)
    elif scripted:
        reply_text = scripted.pop(0)
        no_more = len(scripted) == 0
    elif settings.MOCK:
        reply_text, no_more = "لا إضافة لديّ، وأتمسّك بما سبق من طلبات.", True
    else:
        from langgraph.types import interrupt
        reply_text = interrupt({"prompt": "رد المدعي على المذكرة الجوابية (أو اكتب: لا إضافة)."})
        no_more = "لا إضافة" in (reply_text or "")
    doc = Document(
        doc_type=DocType.PLAINTIFF_REPLY, author_role="مدعي",
        title="رد المدعي على المذكرة الجوابية", body=reply_text,
        hearing_no=state.get("hearing_no", 0), event="رد المدعي", key=key, overridden=overridden,
    )
    return {
        "document_ledger": [doc], "scripted_plaintiff_replies": scripted,
        "no_new_additions": no_more,
        "audit_log": [event("المدعي (بشري)", "تقديم رد على المذكرة الجوابية" + (" (نصٌّ من المستخدم)" if overridden else ""))],
    }


def hearing_manager_node(state: CaseState) -> dict:
    """القاضي يدير الجلسة ويقدّر كفاية المرافعة."""
    return {
        "hearing_no": state.get("hearing_no", 0) + 1,
        "audit_log": [event("القاضي", "إدارة الجلسة وتقدير كفاية المرافعة",
                            detail=f"عدد جولات التبادل حتى الآن: {state.get('pleading_rounds', 0)}")],
    }


def route_pleadings(state: CaseState) -> str:
    """توجيه حلقة المرافعة: ندب خبير، أو إقفال، أو جولة جديدة (حتمي)."""
    if rules.needs_expert(state):
        return "expert"
    if rules.pleadings_saturated(state):
        return "close_pleadings"
    return "defendant_plea"


def expert_node(state: CaseState) -> dict:
    """ندب خبير متخصص يقدّم تقريراً — يحترم نصّ المستخدم إن عدّله."""
    specialty = rules.expert_specialty_for(state)
    ov = _override(state, "expert")
    if ov is not None:
        doc = Document(doc_type=DocType.EXPERT_REPORT, author_role=f"خبير {specialty}",
                       title="تقرير الخبير", body=ov, hearing_no=state.get("hearing_no", 0),
                       event="تقرير خبير", key="expert", overridden=True)
        return {"document_ledger": [doc], "expert_done": True, "expert_specialty": specialty,
                "audit_log": [event(f"خبير {specialty}", "تقرير الخبرة (نصٌّ من المستخدم)")]}
    res = _llm().complete(
        model=settings.GPT_STANDARD, system=prompts.EXPERT.format(specialty=specialty),
        user=_case_file_text(state),
        tools=tools_for("search_saudi_consultations", web=True),
        schema=DEFENSE_SCHEMA, role="expert",
    )
    data = res.get("data") or {"title": "تقرير الخبير", "body": res.get("text", ""), "citations": []}
    cits = _verify_memo_citations(_citations(data), res.get("evidence"))
    doc = Document(
        doc_type=DocType.EXPERT_REPORT, author_role=f"خبير {specialty}",
        title=data.get("title", "تقرير الخبير"), body=data.get("body", ""),
        citations=cits, hearing_no=state.get("hearing_no", 0), event="تقرير خبير", key="expert",
    )
    return {
        "document_ledger": [doc], "expert_done": True, "expert_specialty": specialty,
        "audit_log": [event(f"خبير {specialty}", "تقديم تقرير الخبرة", model=settings.GPT_STANDARD,
                            detail=_cit_counts(cits),
                            sources=_srcs(doc.citations))],
    }


def close_pleadings_node(state: CaseState) -> dict:
    """قفل باب المرافعة ورفع الدعوى للتأمل (حتمي)."""
    return {
        "pleadings_closed": True,
        "audit_log": [event("القاضي", "قفل باب المرافعة ورفع الدعوى للتأمل",
                            detail=f"عدد جولات التبادل: {state.get('pleading_rounds', 0)}")],
    }


def judgment_node(state: CaseState) -> dict:
    """النطق بالحكم عبر محرّك الاستدلال القضائي (العمليات السبع) ← قابلية الاعتراض."""
    from . import operators
    adj = operators.adjudicate(state)
    composition = rules.first_instance_composition(state)
    ruling = Ruling(
        facts=adj["facts"], reasons=adj["reasons"], operative=adj["operative"],
        composition=composition,
        citations=[Citation(claim=c.claim, source_tool=c.system, source_ref=c.article, quote=c.quote)
                   for c in adj["cites"]],
        confidence=adj["confidence"], direction=adj.get("direction", ""),
        blocked=adj.get("blocked", False), flags=adj["flags"],
    )
    g = adj["grounding"]
    audit = [event(f"القاضي ({composition})", "النطق بالحكم عبر محرّك الاستدلال",
                   model=settings.GPT_JUDGE,
                   detail="، ".join(f"{c['label']}{'✓' if c['ok'] else '⚠'}" for c in adj["chain"]),
                   sources=_srcs(ruling.citations))]
    audit.append(event("بوابة التأصيل",
                       f"مؤصَّل:{g['verified']} · شرعي:{g['sharia']} · غير مُحمَّل:{g['unloaded']} · مختلق:{g['fabricated']}",
                       detail=("؛ ".join(adj["flags"]) if adj["flags"] else f"سليم (الثقة: {adj['confidence']})")))

    upd: dict = {"adjudication": adj}
    # وضع التدريب: حقن خلل في الحكم بعد التحقّق (يبقى خفياً عن المحرّك ليكتشفه المحامي).
    exploit = exploits.injection_for(state)
    if exploit in ("ultra_petita", "contradiction"):
        ruling = exploits.apply_to_ruling(ruling, exploit)
        upd["injected_exploit"] = exploit
        audit.append(event("وضع التدريب", "حقن خلل في الحكم (خفي عن المحامي)"))

    state_with = {**state, "judgment": ruling}
    ruling = rules.determine_appealability(state_with)  # type: ignore
    audit.append(event("النظام", "تحديد قابلية الاعتراض",
                       detail=f"{'قابل للاستئناف' if ruling.appealable else 'نهائي ابتدائياً'} — الطريق: {ruling.appeal_route}"))
    upd["judgment"] = ruling
    upd["audit_log"] = audit
    return upd


def serve_judgment_node(state: CaseState) -> dict:
    """تسليم الحكم وبدء مهلة الاعتراض — 30 يوماً، و10 للمستعجل/أحكام الاختصاص (م.187)."""
    days = state.get("appeal_window_days") or rules.appeal_window_days(state)
    return {
        "appeal_window_days": days,
        "deadlines": {**state.get("deadlines", {}),
                      "مهلة الاعتراض": f"{days} يوماً من تاريخ التسليم"},
        "audit_log": [event("النظام", "تسليم الحكم وبدء مهلة الاعتراض",
                            detail=f"{days} يوماً")],
    }


def route_after_judgment(state: CaseState) -> str:
    if rules.can_appeal(state):
        return "appeal_brief"
    if state.get("reconsideration_requested"):
        return "reconsideration"
    return "end"


# ============================ المرحلة الثانية ===============================
def appeal_brief_node(state: CaseState) -> dict:
    ov = _override(state, "appeal_brief")
    brief = ov if ov is not None else (state.get("scripted_appeal_brief") or
        "ألتمس نقض الحكم لمخالفته النظام والثابت بالأوراق، وأعيد التمسك بمذكراتي السابقة.")
    doc = Document(doc_type=DocType.APPEAL_BRIEF, author_role="مستأنف",
                   title="صحيفة الاعتراض بالاستئناف", body=brief, event="استئناف",
                   key="appeal_brief", overridden=ov is not None)
    return {
        "document_ledger": [doc], "current_phase": "الاستئناف", "hearing_no": 0,
        "audit_log": [event("المستأنف (بشري)", "تقديم صحيفة الاعتراض بالاستئناف")],
    }


def appellee_response_node(state: CaseState) -> dict:
    ov = _override(state, "appellee_response")
    if ov is not None:
        doc = Document(doc_type=DocType.APPEAL_RESPONSE, author_role="مستأنف ضده",
                       title="مذكرة جوابية على الاستئناف", body=ov, event="جواب استئناف",
                       key="appellee_response", overridden=True)
        return {"document_ledger": [doc],
                "audit_log": [event("وكيل المستأنف ضده", "الرد على الاستئناف (نصٌّ من المستخدم)")]}
    res = _llm().complete(
        model=settings.GPT_STANDARD, system=prompts.APPELLEE, user=_appeal_context(state),
        tools=tools_for("search_saudi_codes", "search_commercial_principles"),
        schema=DEFENSE_SCHEMA, role="appellee",
    )
    data = res.get("data") or {"title": "مذكرة جوابية على الاستئناف", "body": res.get("text", ""), "citations": []}
    cits = _verify_memo_citations(_citations(data), res.get("evidence"))
    doc = Document(doc_type=DocType.APPEAL_RESPONSE, author_role="مستأنف ضده",
                   title=data.get("title", "مذكرة جوابية على الاستئناف"),
                   body=data.get("body", ""), citations=cits, event="جواب استئناف",
                   key="appellee_response")
    return {
        "document_ledger": [doc],
        "audit_log": [event("وكيل المستأنف ضده", "الرد على لائحة الاعتراض",
                            model=settings.GPT_STANDARD, detail=_cit_counts(cits),
                            sources=_srcs(doc.citations))],
    }


def appeal_hearing_node(state: CaseState) -> dict:
    return {"audit_log": [event("قاضي الاستئناف", "جلسة استماع وطلب إيضاحات",
                               detail="مراجعة لائحة الاعتراض والمذكرة الجوابية قبل المداولة")]}


def appellate_panel_node(state: CaseState) -> dict:
    return panel.run_panel(state)


def route_after_appeal(state: CaseState) -> str:
    return "reconsideration" if state.get("reconsideration_requested") else "end"


def reconsideration_node(state: CaseState) -> dict:
    """التماس إعادة النظر (م.200): تحقّق من السبب الحصري ثم تقييم اكتشاف الثغرة."""
    ground = state.get("reconsideration_ground", "")
    valid = rules.reconsideration_ground_valid(ground)
    doc = Document(doc_type=DocType.RECONSIDERATION, author_role="ملتمس",
                   title="التماس إعادة النظر",
                   body=f"ألتمس إعادة النظر استناداً إلى: {rules.ARTICLE_200_GROUNDS.get(ground, ground)}",
                   event="التماس")
    audit = [event("الملتمس", "تقديم التماس إعادة النظر (م.200)",
                   detail=f"السبب: {ground} ({'سبب نظامي' if valid else 'سبب غير مقبول'})")]
    upd: dict = {"document_ledger": [doc], "current_phase": "التماس إعادة النظر"}
    if not valid:
        upd["reconsideration_outcome"] = (
            "عدم قبول الالتماس: السبب ليس من الأسباب السبعة الحصرية للمادة 200.")
        upd["audit_log"] = audit
        return upd
    ev = exploits.evaluate(state)
    upd["reconsideration_outcome"] = ev["reconsideration_outcome"]
    upd["audit_log"] = audit + ev["audit_log"]
    return upd


# ============================ مساعدات نصية ==================================
def _model_for(state: CaseState) -> str:
    return settings.GPT_PRO if state.get("complexity") == "شائكة" else settings.GPT_STANDARD


def _citations(data: dict) -> list[Citation]:
    out: list[Citation] = []
    for c in data.get("citations", []) or []:
        out.append(Citation(claim=c.get("claim", ""), source_tool=c.get("source_tool", ""),
                            source_ref=c.get("source_ref", ""), quote=c.get("quote", "")))
    return out


def _verify_memo_citations(cits: list[Citation], evidence: list[str] | None) -> list[Citation]:
    """وسمُ إسنادات مذكرات الخصوم (لا حجب — وسمٌ يراه المحامي المتدرّب): المنتَج يدرّب
    على التأصيل، فلا يُعرض إسنادٌ بمظهر مصدرٍ رسميٍّ دون بيان حاله. المطابقة على
    المُسترجَع فعلاً متى توفّر؛ وعند غيابه (وهمي) يُكتفى بصحة شكل الإسناد."""
    from . import citations as gate
    joined = " ".join(evidence) if evidence else ""
    for c in cits:
        if not gate._is_valid_tool(c.source_tool):
            c.status, c.status_reason = "مختلق", f"أداة مصدرٍ غير معروفة: «{c.source_tool}»"
        elif not (c.quote.strip() or c.source_ref.strip()):
            c.status, c.status_reason = "مختلق", "إسنادٌ بلا مرجعٍ ولا اقتباس"
        elif evidence is None:
            c.status = "مؤصَّل"     # لا استرجاعَ في النداء (وهمي/اختبار) — شكل الإسناد سليم
        elif joined.strip() and c.quote.strip() and sources_mod._loose_overlap(c.quote, joined) \
                and not sources_mod._numeric_mismatch(c.quote, joined):
            c.status = "مؤصَّل"
        else:
            c.status, c.status_reason = "غير مُحمَّل", "الاقتباس لا يقابل نصاً مُسترجَعاً في النداء نفسه"
    return cits


def _cit_counts(cits: list[Citation]) -> str:
    ok = sum(1 for c in cits if c.status == "مؤصَّل")
    un = sum(1 for c in cits if c.status == "غير مُحمَّل")
    fab = sum(1 for c in cits if c.status == "مختلق")
    return f"إسنادات المذكرة — مؤصَّل:{ok} · غير مُحمَّل:{un} · مختلق:{fab}"


def _srcs(citations: list[Citation]) -> list[str]:
    """مصادر فريدة مرتبة لسجل التدقيق (بلا تكرار)."""
    return sorted({c.source_tool for c in citations if c.source_tool})


def _override(state: CaseState, key: str):
    """نصّ المستخدم الذي يستبدل نصّ النموذج لهذا المستند (إن وُجد)."""
    return (state.get("overrides") or {}).get(key)


def _claim_text(state: CaseState) -> str:
    sheet = _latest(state, DocType.CLAIM_SHEET)
    base = (f"نوع الدعوى: {state.get('case_type','')}\n"
            f"موضوعها: {state.get('claim_subject','')}\n"
            f"قيمتها: {state.get('claim_value','')} ر.س\n")
    return base + (f"\nصحيفة الدعوى:\n{sheet.body}" if sheet else "")


def _case_file_text(state: CaseState, for_judge: bool = False, research: bool = True) -> str:
    parts = [_claim_text(state)]
    r = state.get("research") or {}
    # للقاضي: نسخةٌ تحجب اتجاه السوابق ونتائجها (تفادي الإرساء)؛ للخصم/العرض: النسخة الكاملة.
    # research=False: عملياتٌ لا تحتاج ملخّص البحث أصلاً (تحرير/محل النزاع) — حمولةٌ أخفّ.
    summ = (r.get("summary_judge") if for_judge else r.get("summary")) if research else ""
    if summ:
        parts.append("\n" + summ)
    parts.append("\n--- المذكرات المتبادلة ---")
    for doc in state.get("document_ledger", []):
        if doc.doc_type in (DocType.DEFENSE_MEMO, DocType.PLAINTIFF_REPLY, DocType.EXPERT_REPORT):
            parts.append(f"[{doc.title}]\n{doc.body}")
    return "\n".join(parts)


def _appeal_context(state: CaseState) -> str:
    j = state.get("judgment")
    parts = [f"الحكم الابتدائي:\n- الأسباب: {j.reasons if j else '—'}\n- المنطوق: {j.operative if j else '—'}"]
    for doc in state.get("document_ledger", []):
        if doc.doc_type == DocType.APPEAL_BRIEF:
            parts.append(f"\nلائحة الاعتراض:\n{doc.body}")
    return "\n".join(parts)


def _latest(state: CaseState, doc_type: DocType) -> Document | None:
    found = None
    for doc in state.get("document_ledger", []) or []:
        if doc.doc_type == doc_type:
            found = doc
    return found
