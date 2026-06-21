"""
اختبارات محرّك الاستدلال القضائي: طبقة المصادر، المُتحقِّقات الحتمية، والسلسلة كاملةً.
هذه نواة الثقة المهنية — كلها حتمية (وضع وهمي، بلا API حقيقي).
"""
from __future__ import annotations

from bayyin import operators, settings, sources
from bayyin.sources import Cite, CiteStatus
from bayyin.state import Document, DocType, Party

settings.MOCK = True  # تشغيل العمليات بنماذج وهمية


# ---------- طبقة المصادر ----------
def test_verify_cite_statuses():
    assert sources.verify_cite(Cite(system="نظام الإثبات", article="1"))[0] == CiteStatus.VERIFIED
    assert sources.verify_cite(Cite(system="نظام المرافعات الشرعية", article="999"))[0] == CiteStatus.UNLOADED
    assert sources.verify_cite(Cite(system="نظام مختلق", article="1"))[0] == CiteStatus.FABRICATED
    # استنادٌ للشريعة بمبدأٍ محدّد ⇒ مؤصَّل شرعاً؛ وبلا مبدأ ⇒ لا يُعتدّ به (غير مُحمَّل).
    assert sources.verify_cite(Cite(system="الشريعة الإسلامية", article="", claim="قاعدة: الضرر يُزال"))[0] == CiteStatus.SHARIA
    assert sources.verify_cite(Cite(system="الشريعة الإسلامية", article=""))[0] == CiteStatus.UNLOADED


def test_assess_grounding_zero_fabrication_gate():
    ok = sources.assess_grounding([Cite(system="نظام الإثبات", article="1", claim="x")])
    assert ok["ok"] and ok["verified"] >= 1 and ok["fabricated"] == 0
    bad = sources.assess_grounding([Cite(system="نظام مختلق", article="1")])
    assert not bad["ok"] and bad["fabricated"] == 1


# ---------- المُتحقِّقات الحتمية السعودية ----------
def test_non_ultra_petita():
    req = [{"type": "مبلغ", "amount": 250000}]
    assert operators.check_non_ultra_petita(req, [{"type": "مبلغ", "amount": 250000}]) == []
    assert operators.check_non_ultra_petita(req, [{"type": "مبلغ", "amount": 300000}])  # أكثر مما طُلب
    assert operators.check_non_ultra_petita(req, [{"type": "تعويض", "amount": 1}])       # ما لم يُطلب


def test_mantuq_consistency():
    assert operators.check_mantuq_consistency("رفض الدعوى", "حكمت بإلزام المدعى عليه بالأداء")  # تناقض
    assert operators.check_mantuq_consistency("للمدعي", "حكمت بإلزام المدعى عليه بأداء المبلغ") == []
    assert operators.check_mantuq_consistency("للمدعي", "حكمت برفض الدعوى")                      # تناقض


def test_defenses_addressed():
    assert operators.check_defenses_addressed(["اختصاص", "مطابقة"], ["اختصاص"])  # مطابقة غير مردودٍ عليها
    assert operators.check_defenses_addressed(["اختصاص"], ["اختصاص"]) == []


# ---------- السلسلة الكاملة (وهمي) ----------
def _state():
    return {
        "case_type": "تجاري", "claim_subject": "مطالبة بثمن بضاعة بموجب عقد توريد",
        "claim_value": 250000.0,
        "parties": [Party(role="مدعي", name="أ"), Party(role="مدعى عليه", name="ب")],
        "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي",
                                     title="صحيفة الدعوى", body="مطالبة بثمن بضاعة 250,000 ريال.")],
    }


def test_adjudicate_chain_sound_and_grounded():
    adj = operators.adjudicate(_state())
    assert len(adj["chain"]) == 7                      # العمليات السبع
    assert all(c["ok"] for c in adj["chain"])          # كلها سليمة
    assert adj["grounding"]["fabricated"] == 0          # صفر اختلاق
    assert adj["grounding"]["verified"] >= 1            # مؤصَّل فعلاً
    assert adj["confidence"] == "عالية"
    assert "إلزام" in adj["operative"]
    assert not adj["flags"]                              # بلا تحذيرات


def test_adjudicate_blocks_on_fabrication():
    # حقن تكييفٍ يستند لمصدرٍ مختلق ⇒ يجب أن يَحبِس المحرّك النطق (لا يكتفي بالتحذير).
    import bayyin.llm as llm
    orig = llm._MOCKS["op_takyif"]
    llm._MOCKS["op_takyif"] = lambda u: {"text": "", "data": {
        "nature": "x", "governing_system": "نظام مختلق",
        "cite": {"system": "نظام مختلق", "article": "1", "quote": "", "claim": "y"}, "summary": "s"}}
    try:
        adj = operators.adjudicate(_state())
        assert adj["grounding"]["fabricated"] >= 1
        assert adj["blocked"] is True
        assert adj["operative"].startswith("⛔")        # حُجِب النطق فعلاً
        assert adj["confidence"] == "محجوب"
    finally:
        llm._MOCKS["op_takyif"] = orig


def test_adjudicate_exposes_direction_not_blocked():
    adj = operators.adjudicate(_state())
    assert adj["direction"] == "للمدعي"
    assert adj["blocked"] is False


def test_num_safe_on_bad_amounts():
    out = operators.check_non_ultra_petita([{"type": "مبلغ", "amount": "abc"}],
                                           [{"type": "مبلغ", "amount": "xyz"}])
    assert out == []


def test_finality_boundary_le_50000():
    from bayyin import rules
    from bayyin.state import Citation, Ruling
    r = Ruling(facts="و", reasons="ر", operative="م",
               citations=[Citation(claim="c", source_tool="نظام المعاملات المدنية", source_ref="العقد")])
    assert rules.determine_appealability({"claim_value": 50000, "judgment": r}).appealable is False
    assert rules.determine_appealability({"claim_value": 50001, "judgment": r}).appealable is True


def test_evaluation_harness_runs():
    from bayyin import evaluation
    rep = evaluation.evaluate(None)
    assert rep["n"] == 2
    assert 0.0 <= rep["direction_macro_f1"] <= 1.0
    assert rep["zero_fabrication_rate"] == 1.0
