"""
بوابة الاستشهاد (Citation / Grounding Gate).
تتصدّى لأخطر مشكلة موثّقة بحثياً: الهلوسة القانونية (69–88% في الدراسات).
كل قول قانوني مُلزِم — خصوصاً المنطوق والأسباب — يجب أن يُسنَد إلى مصدر
مُسترجَع فعلاً من قواعد file_search. ما لا يُسنَد يُرفَع كعَلَم (flag).

وحدة حتمية، لا نموذج لغوي، قابلة للاختبار.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .settings import VECTOR_STORES
from .state import Citation, Ruling

_VALID_TOOLS = set(VECTOR_STORES.keys())


def _is_valid_tool(tool: str) -> bool:
    # نقبل الأسماء المنطقية، والتسمية الفعلية لأداة الاسترجاع في Responses API
    # (file_search / file_search.msearch)، و«record» (استشهاد بمستند داخل ملف الدعوى).
    return tool in _VALID_TOOLS or tool.startswith("file_search") or tool == "record"


def _is_statute_or_precedent(tool: str) -> bool:
    return tool.startswith("file_search") or tool in {
        "search_saudi_codes", "search_commercial_principles",
        "search_commercial_precedents_1", "search_commercial_precedents_2"}


@dataclass
class GateResult:
    ok: bool
    issues: list[str] = field(default_factory=list)


def _check_citation(c: Citation) -> list[str]:
    problems: list[str] = []
    if not _is_valid_tool(c.source_tool):
        problems.append(f"أداة مصدر غير معروفة: «{c.source_tool}».")
    if not (c.source_ref.strip() or c.quote.strip()):
        problems.append(f"إسناد بلا مرجع ولا اقتباس: «{c.claim[:40]}…».")
    return problems


def enforce_ruling_grounding(ruling: Ruling) -> GateResult:
    """
    يتحقّق أن الحكم مُسنَد: يوجد إسناد واحد صحيح على الأقل، وكل إسناد
    يشير إلى أداة قاعدة معروفة وبمرجع غير فارغ.
    """
    issues: list[str] = []

    if not ruling.citations:
        issues.append("الحكم خالٍ من أي إسناد نظامي — مرفوض (خطر هلوسة).")
        return GateResult(ok=False, issues=issues)

    for c in ruling.citations:
        issues.extend(_check_citation(c))

    # يجب أن يستند التسبيب إلى نظام أو سابقة (عبر file_search) على الأقل.
    if not any(_is_statute_or_precedent(c.source_tool) for c in ruling.citations):
        issues.append("التسبيب لا يستند إلى نظام أو سابقة قضائية.")

    return GateResult(ok=not issues, issues=issues)


def enforce_citations(citations: list[Citation]) -> GateResult:
    """تحقّق عام من قائمة إسنادات (للمذكرات)."""
    issues: list[str] = []
    if not citations:
        issues.append("لا توجد إسنادات داعمة.")
    for c in citations:
        issues.extend(_check_citation(c))
    return GateResult(ok=not issues, issues=issues)


def enforce_against_retrieved(citations: list[Citation],
                              retrieved_sources: list[str]) -> GateResult:
    """
    M5: تأصيل فعلي — تحقّق أن الإسناد يقابل مصدراً استُرجع فعلاً من file_search.
    إن لم تتوفّر مصادر مسترجَعة (وضع وهمي أو استجابة بلا نتائج) نتجاوز بلطف.
    """
    if not retrieved_sources:
        return GateResult(ok=True, issues=[])
    joined = " ".join(retrieved_sources)
    issues: list[str] = []
    for c in citations:
        key = c.source_ref.split("—")[0].strip()[:8]
        if key and key not in joined:
            issues.append(f"إسناد غير مؤكَّد بالاسترجاع الفعلي: «{c.claim[:35]}…».")
    return GateResult(ok=not issues, issues=issues)
