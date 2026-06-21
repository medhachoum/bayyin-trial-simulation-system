"""
اختبارات القلب الحتمي (لا تتطلب API ولا LangGraph).
تغطّي: تدقيق الصحيفة، قابلية الاعتراض، بوابة الاستشهاد، أسباب المادة 200.
"""
from __future__ import annotations

from bayyin import rules
from bayyin.citations import enforce_ruling_grounding
from bayyin.state import Citation, Document, DocType, Party, Ruling


def _valid_state(value: float = 250_000.0) -> dict:
    return {
        "claim_subject": "مطالبة بثمن بضاعة",
        "claim_value": value,
        "parties": [Party(role="مدعي", name="أ"), Party(role="مدعى عليه", name="ب")],
        "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET,
                                     author_role="مدعي", title="صحيفة", body="...")],
    }


# ---------- تدقيق صحيفة الدعوى ----------
def test_valid_claim_sheet_passes():
    assert rules.validate_claim_sheet(_valid_state()).ok


def test_missing_party_fails():
    state = _valid_state()
    state["parties"] = [Party(role="مدعي", name="أ")]  # بلا مدعى عليه
    res = rules.validate_claim_sheet(state)
    assert not res.ok
    assert any("مدعى عليه" in i for i in res.issues)


def test_zero_value_fails():
    res = rules.validate_claim_sheet(_valid_state(value=0))
    assert not res.ok


def test_missing_claim_sheet_doc_fails():
    state = _valid_state()
    state["document_ledger"] = []
    assert not rules.validate_claim_sheet(state).ok


# ---------- قابلية الاعتراض ----------
def _ruling() -> Ruling:
    return Ruling(facts="و", reasons="ر", operative="م",
                  citations=[Citation(claim="c", source_tool="search_saudi_codes",
                                      source_ref="مادة")])


def test_high_value_is_appealable():
    state = {**_valid_state(value=250_000.0), "judgment": _ruling()}
    out = rules.determine_appealability(state)
    assert out.appealable is True
    assert out.appeal_route == "استئناف"


def test_low_value_is_final():
    state = {**_valid_state(value=20_000.0), "judgment": _ruling()}
    out = rules.determine_appealability(state)
    assert out.appealable is False
    assert out.appeal_route == "التماس إعادة النظر"


# ---------- بوابة الاستشهاد ----------
def test_ruling_without_citations_is_rejected():
    r = Ruling(facts="و", reasons="ر", operative="م", citations=[])
    assert not enforce_ruling_grounding(r).ok


def test_ruling_with_valid_code_citation_passes():
    assert enforce_ruling_grounding(_ruling()).ok


def test_ruling_with_unknown_tool_flagged():
    r = Ruling(facts="و", reasons="ر", operative="م",
               citations=[Citation(claim="c", source_tool="bogus_tool", source_ref="x")])
    assert not enforce_ruling_grounding(r).ok


# ---------- المادة 200 ----------
def test_article_200_grounds():
    assert rules.reconsideration_ground_valid("forgery")
    assert rules.reconsideration_ground_valid("ultra_petita")
    assert not rules.reconsideration_ground_valid("not_a_ground")
    assert len(rules.ARTICLE_200_GROUNDS) == 7
