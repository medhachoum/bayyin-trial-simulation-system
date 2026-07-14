"""
طبقة البحث القضائي التجاري — تُجرى مرّةً بعد قبول الدعوى وقبل المرافعة.
الفكرة المعمارية: السوابق والمبادئ التجارية تُسترجَع مُسبقاً لتوجيه المحاكاة
(دفوعٌ واقعية، تكييفٌ وتطبيقٌ مؤصَّل، وتقديرُ اتجاه الحكم)، مع احترام حدّ
file_search (مخزنان لكل نداء):
  • نداء «المبادئ + الأنظمة» → المرجع التأصيلي القابل للاستشهاد (يستشهد به القاضي).
  • نداء «السوابق» (مخزنا السوابق معاً) → توجيهٌ استئناسيٌّ تحليليٌّ (لا يقيّد القاضي).
المخرَج يُحقَن في ملف الدعوى فيراه وكيل المدعى عليه ومحرّك الاستدلال.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import prompts, settings
from .llm import get_llm
from .tools import precedents_tool, tools_for

# ---------------------------------------------------------------------------
# مخططات المخرَج المنظَّم (صارمة)
# ---------------------------------------------------------------------------
_PRINCIPLE = {
    "type": "object", "additionalProperties": False,
    "properties": {"principle": {"type": "string"}, "ref": {"type": "string"},
                   "quote": {"type": "string"}, "relevance": {"type": "string"}},
    "required": ["principle", "ref", "quote", "relevance"],
}
PRINCIPLES_SCHEMA = {
    "title": "research_principles", "type": "object", "additionalProperties": False,
    "properties": {"principles": {"type": "array", "items": _PRINCIPLE}, "note": {"type": "string"}},
    "required": ["principles", "note"],
}
_PRECEDENT = {
    "type": "object", "additionalProperties": False,
    "properties": {"summary": {"type": "string"}, "holding": {"type": "string"},
                   "outcome": {"type": "string", "enum": ["للمدعي", "للمدعى عليه", "مختلط"]},
                   "ref": {"type": "string"}},
    "required": ["summary", "holding", "outcome", "ref"],
}
PRECEDENTS_SCHEMA = {
    "title": "research_precedents", "type": "object", "additionalProperties": False,
    "properties": {"precedents": {"type": "array", "items": _PRECEDENT},
                   "outcome_signal": {"type": "string",
                                      "enum": ["للمدعي", "للمدعى عليه", "مختلط", "غير حاسم"]},
                   "note": {"type": "string"}},
    "required": ["precedents", "outcome_signal", "note"],
}


def _model() -> str:
    """نموذج البحث يُحسب لحظياً (يحترم إعدادات المستخدم)."""
    return settings.GPT_STANDARD


def _case_brief(state) -> str:
    """نصٌّ موجزٌ للنزاع وقت البحث (لا تكون قد قُدّمت سوى صحيفة الدعوى)."""
    from .state import DocType
    parts = [f"نوع الدعوى: {state.get('case_type', '')}",
             f"موضوعها: {state.get('claim_subject', '')}",
             f"قيمتها: {state.get('claim_value', '')} ر.س"]
    for d in state.get("document_ledger", []) or []:
        if d.doc_type == DocType.CLAIM_SHEET:
            parts.append(f"\nصحيفة الدعوى:\n{d.body}")
    return "\n".join(parts)


def research(state) -> dict:
    """يُجري نداءي الاسترجاع ويُرجع حصيلةً موحّدة (principles / precedents / outcome_signal)."""
    brief = _case_brief(state)
    llm = get_llm()

    def _principles():
        return llm.complete(model=_model(), system=prompts.RESEARCH_PRINCIPLES, user=brief,
                            tools=tools_for("search_commercial_principles", "search_saudi_codes"),
                            schema=PRINCIPLES_SCHEMA, role="research_principles")

    def _precedents():
        return llm.complete(model=_model(), system=prompts.RESEARCH_PRECEDENTS, user=brief,
                            tools=precedents_tool(), schema=PRECEDENTS_SCHEMA, role="research_precedents")

    # نداءا الاسترجاع مستقلّان → يُشغَّلان معاً (يقصّ زمن الطبقة للنصف تقريباً).
    with ThreadPoolExecutor(max_workers=2) as ex:
        fp, fc = ex.submit(_principles), ex.submit(_precedents)
        rp, rc = fp.result(), fc.result()
    pd = rp.get("data") or {}
    cd = rc.get("data") or {}
    # أدلة الاسترجاع الفعلية: None إن لم يجرِ استرجاعٌ في النداءين (وهمي/اختبار).
    ev_p, ev_c = rp.get("evidence"), rc.get("evidence")
    evidence = None if (ev_p is None and ev_c is None) else (ev_p or []) + (ev_c or [])
    # ترشيحٌ قبل الحقن: مبدأٌ/سابقةٌ اقتباسُها لا يقابل المُسترجَع فعلاً لا يدخل ملف
    # الدعوى أصلاً — «حقيقة السياق» يجب أن تكون مُتحقَّقةً هي الأخرى، لا النموذج وحده.
    principles = _screen(pd.get("principles", []) or [],
                         "المبادئ القضائية التجارية", "quote", evidence)
    precedents = _screen(cd.get("precedents", []) or [],
                         "السوابق القضائية التجارية", "holding", evidence)
    src = sorted(set((rp.get("sources") or []) + (rc.get("sources") or [])))
    signal = cd.get("outcome_signal", "غير حاسم")
    return {
        "principles": principles,
        "precedents": precedents,
        "outcome_signal": signal,
        "principles_note": pd.get("note", ""),
        "precedents_note": cd.get("note", ""),
        "sources": src,
        "evidence": evidence,   # تُستعمل لاحقاً لتأصيل استشهادات القاضي بمبادئ ملف الدعوى
        # نسختان: «full» للعرض ولوكيل المدعى عليه (الخصم)، و«judge» لمحرّك الاستدلال —
        # تحجب اتجاه السوابق ونتائجها كي لا تُرسي القاضيَ نحو نتيجةٍ مسبقة (anchoring).
        "summary": summary_text(principles, precedents, signal, for_judge=False),
        "summary_judge": summary_text(principles, precedents, signal, for_judge=True),
    }


def _screen(items: list[dict], system: str, quote_field: str,
            evidence: list[str] | None) -> list[dict]:
    """يُبقي العنصر إن أصَّله verify_cite (بأدلة الاسترجاع متى وُجدت) — يُسقط ما اقتباسه
    لا يقابل نصاً مُسترجَعاً (شبهة اختلاقٍ في طبقة البحث نفسها)."""
    from . import sources as _s
    if evidence is None:      # لا استرجاع (وهمي/اختبار) — المسار المتساهل الموثَّق
        return items
    kept = []
    for it in items:
        c = _s.Cite(system=system, quote=it.get(quote_field, "") or "",
                    claim=it.get("principle") or it.get("summary") or "")
        if _s.verify_cite(c, evidence)[0] == _s.CiteStatus.VERIFIED:
            kept.append(it)
    return kept


def summary_text(principles: list[dict], precedents: list[dict], outcome_signal: str,
                 for_judge: bool = False) -> str:
    """كتلةٌ مُكثّفة تُحقَن في ملف الدعوى. النسخة القضائية (for_judge) تُبقي المبادئ
    القابلة للاستشهاد فقط، وتحجب اتجاه السوابق ونتائجها (تفادي الإرساء على نتيجةٍ مسبقة)."""
    lines = ["--- مبادئ وسوابق تجارية ذات صلة (بحثٌ تأصيليٌّ تمهيدي — للاستئناس) ---"]
    if principles:
        lines.append("• مبادئ قضائية حاكمة:")
        for p in principles[:4]:
            ref = f" [{p.get('ref', '')}]" if p.get("ref") else ""
            lines.append(f"  - {p.get('principle', '')}{ref}")
    if precedents:
        if for_judge:
            # للقاضي: ذكرٌ محايدٌ بالعدد فقط — دون نتائج السوابق ولا اتجاهها، فلا يُبنى عليها الترجيح.
            lines.append(f"• استُعرضت {len(precedents)} سابقةٌ مشابهةٌ للاطّلاع "
                         "(استئناسٌ لا يقيّد، ولا يُبنى عليه الاتجاه — يُحسم بأدلة الدعوى وتأصيلها).")
        else:
            lines.append("• سوابق مشابهة:")
            for c in precedents[:4]:
                lines.append(f"  - {c.get('summary', '')} ← {c.get('holding', '')} "
                             f"(الاتجاه: {c.get('outcome', '')}) [{c.get('ref', '')}]")
            lines.append(f"• إشارة اتجاه السوابق (استئناسيةٌ لا تقيّد القاضي): {outcome_signal}")
    if not principles and not precedents:
        lines.append("• لم يُسترجَع مبدأٌ أو سابقةٌ قريبةٌ بدرجةٍ كافية.")
    return "\n".join(lines)
