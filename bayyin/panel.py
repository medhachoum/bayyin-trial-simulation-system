"""
دائرة الاستئناف الثلاثية (M3) — بمنطق محرّك الاستدلال نفسه.
مبني على بحث مقاومة التحيّز في القضاء الآلي:
- ثلاث عدسات متمايزة (تنوّع الرأي) بدل ثلاث نسخ متطابقة → يقلّل المجاملة (sycophancy).
- جولة عمياء أولاً: كل قاضٍ مستقل لا يرى الآخرين → يمنع الإرساء المبكر (anchoring).
- مداولة لاحقة على آراء مجهّلة → نقاش دون انحياز هوية أو موضع.
- الإجماع/الأغلبية يحسم، لا قاضٍ واحد.
ثم: الحكم النهائي يخضع لـ«بوابة التأصيل» الحابسة نفسها التي يخضع لها حكم أول درجة —
فلا يصدر حكمٌ استئنافيٌّ يستند إلى إسنادٍ مختلق، ويحمل ثقةً ومخالفاتٍ كأول درجة.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import prompts, rules, settings, sources
from .audit import event
from .llm import get_llm
from .sources import Cite
from .state import CaseState, Citation, Ruling
from .tools import tools_for

# عدسات القضاة الثلاث (متمايزة عمداً).
LENSES = ["الصحة الإجرائية", "التطبيق النظامي", "الإنصاف الموضوعي"]

_CITE = {"type": "object", "additionalProperties": False,
         "properties": {"system": {"type": "string"}, "article": {"type": "string"},
                        "quote": {"type": "string"}, "claim": {"type": "string"}},
         "required": ["system", "article", "quote", "claim"]}
VOTE_SCHEMA = {
    "title": "appeal_vote", "type": "object", "additionalProperties": False,
    "properties": {
        "vote": {"type": "string", "enum": ["تأييد", "إلغاء", "تعديل"]},
        "opinion": {"type": "string"},
        "cites": {"type": "array", "items": _CITE},
    },
    "required": ["vote", "opinion", "cites"],
}


def _vote(llm, state: CaseState, lens: str, peers: list[str] | None = None) -> dict:
    user = _panel_user(state, lens, peers)
    res = llm.complete(
        model=settings.GPT_JUDGE, system=prompts.APPEAL_JUDGE.format(lens=lens),
        user=user, tools=tools_for("search_saudi_codes", "search_commercial_principles"),
        schema=VOTE_SCHEMA, role="panel", effort=settings.EFFORT_JUDGE,
    )
    d = res.get("data") or {"vote": "تأييد", "opinion": "", "cites": []}
    return {"lens": lens, "vote": d.get("vote", "تأييد"), "opinion": d.get("opinion", ""),
            "cites": d.get("cites") or [], "evidence": res.get("evidence") or []}


def run_panel(state: CaseState) -> dict:
    """يشغّل الدائرة ويُرجع تحديث الحالة (الحكم النهائي المؤصَّل + أصوات + تدقيق)."""
    llm = get_llm()

    # 1) جولة عمياء — كل قاضٍ مستقل (الأصوات الثلاثة متوازية).
    with ThreadPoolExecutor(max_workers=3) as ex:
        blind = list(ex.map(lambda lens: _vote(llm, state, lens), LENSES))

    # 2) مداولة — يرى كلٌّ آراء زملائه مجهّلةً ويعيد النظر (الثلاثة متوازية أيضاً).
    anon = [f"رأي عضو ({b['lens']}): {b['vote']} — {b['opinion']}" for b in blind]

    def _delib(i_lens):
        i, lens = i_lens
        peers = [a for j, a in enumerate(anon) if j != i]
        return _vote(llm, state, lens, peers)

    with ThreadPoolExecutor(max_workers=3) as ex:
        deliberated = list(ex.map(_delib, list(enumerate(LENSES))))

    votes = [d["vote"] for d in deliberated]
    consensus = rules.panel_consensus(votes)
    cite_dicts = [c for d in deliberated for c in d.get("cites", [])]
    evidence = [e for d in deliberated for e in d.get("evidence", [])]
    final, grounding = _compose_final(state, consensus, deliberated, cite_dicts, evidence)

    audit = [event("دائرة الاستئناف", "جولة تصويت عمياء", model=settings.GPT_JUDGE,
                   detail="، ".join(f"{b['lens']}: {b['vote']}" for b in blind))]
    audit.append(event("دائرة الاستئناف", "مداولة وتصويت نهائي", model=settings.GPT_JUDGE,
                       detail="، ".join(f"{d['lens']}: {d['vote']}" for d in deliberated)))
    audit.append(event("بوابة التأصيل (الاستئناف)",
                       f"مؤصَّل:{grounding['verified']} · شرعي:{grounding['sharia']} · "
                       f"غير مُحمَّل:{grounding['unloaded']} · مختلق:{grounding['fabricated']}",
                       detail=("؛ ".join(final.flags) if final.flags else f"سليم (الثقة: {final.confidence})")))
    audit.append(event("دائرة الاستئناف", f"الحكم النهائي القطعي: {consensus}", detail=final.operative))

    return {
        "appeal_judgment": final,
        "panel_votes": deliberated,
        "current_phase": "نهائي",
        "audit_log": audit,
    }


def _panel_user(state: CaseState, lens: str, peers: list[str] | None) -> str:
    trial = state.get("judgment")
    parts = [
        f"الحكم الابتدائي المستأنف:\n- الأسباب: {trial.reasons if trial else '—'}\n"
        f"- المنطوق: {trial.operative if trial else '—'}",
        f"\nأسباب الاعتراض (لائحة الاستئناف):\n{_appeal_brief_text(state)}",
        f"\nراجع من خلال عدسة «{lens}» وأصدر رأيك، واذكر إسناداتك (نظام+مادة، أو مبدأٌ "
        "قضائيٌّ تجاريٌّ مُسترجَع باقتباسه).",
    ]
    if peers:
        parts.append("\nآراء بقية أعضاء الدائرة (مجهّلة) للمداولة:\n" + "\n".join(peers))
    return "\n".join(parts)


def _appeal_brief_text(state: CaseState) -> str:
    from .state import DocType
    for d in reversed(state.get("document_ledger", []) or []):
        if d.doc_type == DocType.APPEAL_BRIEF:
            return d.body
    return "—"


def _compose_final(state: CaseState, consensus: str, deliberated: list[dict],
                   cite_dicts: list[dict], evidence: list[str]) -> tuple[Ruling, dict]:
    """يصوغ الحكم النهائي القطعي بإجماع الدائرة، ثم يمرّره على بوابة التأصيل الحابسة."""
    trial = state.get("judgment")
    base_op = trial.operative if trial else ""

    # إسنادات الدائرة (مُزالة التكرار) → تحقّقٌ بنفس صرامة أول درجة.
    seen, cites = set(), []
    for c in cite_dicts:
        key = (c.get("system", ""), c.get("article", ""), (c.get("claim", "") or "")[:40])
        if key in seen:
            continue
        seen.add(key)
        cites.append(Citation(claim=c.get("claim", ""), source_tool=c.get("system", ""),
                              source_ref=c.get("article", ""), quote=c.get("quote", "")))
    src_cites = [Cite(system=c.source_tool, article=c.source_ref, quote=c.quote, claim=c.claim)
                 for c in cites]
    grounding = sources.assess_grounding(src_cites, evidence)
    flags = list(grounding["issues"]) + list(grounding["uncertainty"])
    blocking = [f for f in flags if "⛔" in f]
    blocked = (not grounding["ok"]) or bool(blocking)

    reasons = (
        "وحيث راجعت الدائرة الحكم الابتدائي وأسباب الاعتراض عبر عدسات إجرائية ونظامية وإنصاف، "
        f"فقد انتهت أغلبيتها إلى «{consensus}» الحكم المستأنف."
    )
    if blocked:
        why = "؛ ".join((blocking or flags)[:3]) or "إسنادٌ غير مؤصَّل"
        operative = f"⛔ تعذّر إصدار حكمٍ استئنافيٍّ مؤصَّل — رُصدت مخالفاتٌ في الإسناد تمنع النطق: {why}"
        confidence = "محجوب"
    else:
        if consensus == "تأييد":
            operative = f"حكمت الدائرة بتأييد الحكم المستأنف القاضي بـ«{base_op}» ورفض الاستئناف."
        elif consensus == "إلغاء":
            operative = "حكمت الدائرة بإلغاء الحكم المستأنف والقضاء برفض الدعوى الأصلية."
        else:
            operative = f"حكمت الدائرة بتعديل الحكم المستأنف «{base_op}» بما يتفق ونتيجة المراجعة."
        operative += " وهذا حكم نهائي قطعي."
        confidence = "عالية" if not grounding["uncertainty"] else "متوسطة"

    ruling = Ruling(
        facts=trial.facts if trial else "", reasons=reasons, operative=operative,
        citations=cites, appealable=False, appeal_route="نهائي",
        confidence=confidence, direction=consensus, blocked=blocked, flags=flags,
    )
    return ruling, grounding
