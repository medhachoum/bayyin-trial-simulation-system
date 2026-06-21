"""
دائرة الاستئناف الثلاثية (M3).
مبني على بحث مقاومة التحيّز في القضاء الآلي:
- ثلاث عدسات متمايزة (تنوّع الرأي) بدل ثلاث نسخ متطابقة → يقلّل المجاملة (sycophancy).
- جولة عمياء أولاً: كل قاضٍ مستقل لا يرى الآخرين → يمنع الإرساء المبكر (anchoring).
- مداولة لاحقة على آراء مجهّلة → نقاش دون انحياز هوية أو موضع.
- الإجماع/الأغلبية يحسم، لا قاضٍ واحد.
"""
from __future__ import annotations

from . import prompts, rules, settings
from .audit import event
from .llm import get_llm
from .state import CaseState, Citation, Ruling
from .tools import tools_for

# عدسات القضاة الثلاث (متمايزة عمداً).
LENSES = ["الصحة الإجرائية", "التطبيق النظامي", "الإنصاف الموضوعي"]

VOTE_SCHEMA = {
    "title": "appeal_vote", "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["تأييد", "إلغاء", "تعديل"]},
        "opinion": {"type": "string"},
    },
    "required": ["vote", "opinion"], "additionalProperties": False,
}


def _vote(llm, state: CaseState, lens: str, peers: list[str] | None = None) -> dict:
    user = _panel_user(state, lens, peers)
    res = llm.complete(
        model=settings.GPT_PRO, system=prompts.APPEAL_JUDGE.format(lens=lens),
        user=user, tools=tools_for("search_saudi_codes", "search_commercial_precedents"),
        schema=VOTE_SCHEMA, role="panel",
    )
    d = res.get("data") or {"vote": "تأييد", "opinion": ""}
    return {"lens": lens, "vote": d.get("vote", "تأييد"), "opinion": d.get("opinion", "")}


def run_panel(state: CaseState) -> dict:
    """يشغّل الدائرة ويُرجع تحديث الحالة (الحكم النهائي + أصوات + تدقيق)."""
    llm = get_llm()

    # 1) جولة عمياء — كل قاضٍ مستقل.
    blind = [_vote(llm, state, lens) for lens in LENSES]

    # 2) مداولة — يرى كلٌّ آراء زملائه مجهّلةً ويعيد النظر.
    anon = [f"رأي عضو ({b['lens']}): {b['vote']} — {b['opinion']}" for b in blind]
    deliberated = []
    for i, lens in enumerate(LENSES):
        peers = [a for j, a in enumerate(anon) if j != i]
        deliberated.append(_vote(llm, state, lens, peers))

    votes = [d["vote"] for d in deliberated]
    consensus = rules.panel_consensus(votes)
    final = _compose_final(state, consensus)

    audit = [event("دائرة الاستئناف", "جولة تصويت عمياء", model=settings.GPT_PRO,
                   detail="، ".join(f"{b['lens']}: {b['vote']}" for b in blind))]
    audit.append(event("دائرة الاستئناف", "مداولة وتصويت نهائي", model=settings.GPT_PRO,
                       detail="، ".join(f"{d['lens']}: {d['vote']}" for d in deliberated)))
    audit.append(event("دائرة الاستئناف", f"الحكم النهائي القطعي: {consensus}",
                       detail=final.operative))

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
        f"\nراجع من خلال عدسة «{lens}» وأصدر رأيك.",
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


def _compose_final(state: CaseState, consensus: str) -> Ruling:
    """يصوغ الحكم النهائي القطعي بناءً على إجماع الدائرة (حتمي، يعمل في الوضعين)."""
    trial = state.get("judgment")
    base_op = trial.operative if trial else ""
    if consensus == "تأييد":
        operative = f"حكمت الدائرة بتأييد الحكم المستأنف القاضي بـ«{base_op}» ورفض الاستئناف."
    elif consensus == "إلغاء":
        operative = "حكمت الدائرة بإلغاء الحكم المستأنف والقضاء برفض الدعوى الأصلية."
    else:
        operative = f"حكمت الدائرة بتعديل الحكم المستأنف «{base_op}» بما يتفق ونتيجة المراجعة."
    operative += " وهذا حكم نهائي قطعي."
    reasons = (
        "وحيث راجعت الدائرة الحكم الابتدائي وأسباب الاعتراض عبر عدسات إجرائية "
        f"ونظامية وإنصاف، فقد انتهت أغلبيتها إلى «{consensus}» الحكم المستأنف."
    )
    return Ruling(
        facts=trial.facts if trial else "", reasons=reasons, operative=operative,
        citations=[Citation(claim="اختصاص محكمة الاستئناف بمراجعة الحكم",
                            source_tool="search_saudi_codes",
                            source_ref="نظام المرافعات الشرعية — باب الاستئناف", quote="")],
        appealable=False, appeal_route="نهائي",
    )
