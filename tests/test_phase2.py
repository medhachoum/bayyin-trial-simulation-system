"""اختبارات منطق M2–M5 الحتمي: الحلقة، الخبير، المرحلة الثانية، الثغرات، التأصيل."""
from __future__ import annotations

from bayyin import exploits, rules
from bayyin.citations import enforce_against_retrieved
from bayyin.state import Citation, Ruling


# ---------- M2: تشبّع المرافعة + الخبير ----------
def test_saturation_by_max_rounds():
    assert rules.pleadings_saturated({"pleading_rounds": 3})
    assert not rules.pleadings_saturated({"pleading_rounds": 1})


def test_saturation_by_no_new_additions():
    assert rules.pleadings_saturated({"pleading_rounds": 1, "no_new_additions": True})


def test_needs_expert_keyword():
    assert rules.needs_expert({"claim_subject": "نزاع حول كمية مستلمة"})
    assert not rules.needs_expert({"claim_subject": "مطالبة بمبلغ قرض"})


def test_needs_expert_once():
    assert not rules.needs_expert({"claim_subject": "كمية", "expert_done": True})


def test_expert_specialty():
    assert rules.expert_specialty_for({"claim_subject": "خلاف على مواصفات"}) == "فني"
    assert rules.expert_specialty_for({"claim_subject": "خلاف على كمية وفاتورة"}) == "محاسبي"


# ---------- M3: قابلية المرحلة الثانية + إجماع الدائرة ----------
def _ruling(appealable=True):
    return Ruling(facts="و", reasons="ر", operative="م", appealable=appealable,
                  citations=[Citation(claim="c", source_tool="search_saudi_codes", source_ref="x")])


def test_can_appeal_requires_flag_and_appealable():
    assert rules.can_appeal({"judgment": _ruling(True), "appeal_requested": True})
    assert not rules.can_appeal({"judgment": _ruling(True)})              # لا طلب
    assert not rules.can_appeal({"judgment": _ruling(False), "appeal_requested": True})


def test_panel_consensus_majority_and_tie():
    assert rules.panel_consensus(["تأييد", "تأييد", "تعديل"]) == "تأييد"
    assert rules.panel_consensus(["إلغاء", "إلغاء", "تأييد"]) == "إلغاء"
    assert rules.panel_consensus(["تأييد", "إلغاء"]) == "تأييد"          # التعادل للتأييد


# ---------- M4: التماس + حقن الثغرات ----------
def test_can_reconsider_valid_and_invalid_ground():
    assert rules.can_reconsider({"reconsideration_requested": True, "reconsideration_ground": "forgery"})
    assert not rules.can_reconsider({"reconsideration_requested": True, "reconsideration_ground": "xx"})
    assert not rules.can_reconsider({"reconsideration_ground": "forgery"})  # لا طلب


def test_exploit_apply_ultra_petita():
    r = exploits.apply_to_ruling(_ruling(), "ultra_petita")
    assert "لم يطلبه" in r.operative


def test_exploit_apply_contradiction():
    r = exploits.apply_to_ruling(_ruling(), "contradiction")
    assert "رفض" in r.operative


def test_exploit_evaluate_caught():
    out = exploits.evaluate({"injected_exploit": "ultra_petita", "reconsideration_ground": "ultra_petita"})
    assert "أصاب" in out["reconsideration_outcome"]


def test_exploit_evaluate_missed():
    out = exploits.evaluate({"injected_exploit": "ultra_petita", "reconsideration_ground": "contradiction"})
    assert "فات" in out["reconsideration_outcome"]


def test_exploit_evaluate_none():
    out = exploits.evaluate({"reconsideration_ground": "forgery"})
    assert "لا توجد ثغرة" in out["reconsideration_outcome"]


# ---------- M5: التأصيل بالاسترجاع ----------
def test_grounding_lenient_when_no_sources():
    cits = [Citation(claim="c", source_tool="search_saudi_codes", source_ref="نظام المرافعات")]
    assert enforce_against_retrieved(cits, []).ok


def test_grounding_flags_mismatch():
    cits = [Citation(claim="c", source_tool="search_saudi_codes", source_ref="نظام مختلق")]
    res = enforce_against_retrieved(cits, ["وثيقة لا علاقة لها"])
    assert not res.ok


# ---------- بوابة الاستشهاد مع تسميات النموذج الحقيقية ----------
def test_gate_accepts_real_filesearch_labels():
    from bayyin.citations import enforce_ruling_grounding
    r = Ruling(facts="و", reasons="ر", operative="م", citations=[
        Citation(claim="أساس نظامي", source_tool="file_search.msearch", source_ref="", quote="نص مسترجع"),
        Citation(claim="تقرير الخبير", source_tool="record", source_ref="تقرير", quote=""),
    ])
    assert enforce_ruling_grounding(r).ok


def test_gate_still_requires_statute_or_precedent():
    from bayyin.citations import enforce_ruling_grounding
    # استشهاد بمستند ملف فقط (record) دون نظام/سابقة → يُرفض.
    r = Ruling(facts="و", reasons="ر", operative="م",
               citations=[Citation(claim="x", source_tool="record", source_ref="تقرير", quote="")])
    assert not enforce_ruling_grounding(r).ok
