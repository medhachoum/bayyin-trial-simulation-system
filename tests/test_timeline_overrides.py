"""اختبارات الوعي الزمني وآلية التجاوز (نص المستخدم يستبدل نص النموذج فيتغيّر الحكم)."""
from __future__ import annotations

from bayyin import nodes, operators, settings, timeline
from bayyin.state import Document, DocType

settings.MOCK = True


# ---------- الوعي الزمني ----------
def test_timeline_advance_and_hijri():
    # التبليغ في اليوم التالي للقيد على الأكثر (لائحة المحاكم التجارية) → +1 يوم.
    iso, d = timeline.advance("2026-01-15", "notify_defendant")
    assert iso == "2026-01-16"
    assert d["greg"] == "2026-01-16"
    assert d["hijri"]                     # هجريٌّ غير فارغ (hijridate مثبّت)


def test_timeline_add_days():
    assert timeline.add_days("2026-01-15", 30)["greg"] == "2026-02-14"


# ---------- التجاوز ----------
def test_override_replaces_defendant_text():
    state = {"pleading_rounds": 0, "hearing_no": 0, "document_ledger": [],
             "overrides": {"defendant_plea-1": "دفعي: سقطت المطالبة بالتقادم."}}
    doc = nodes.defendant_plea_node(state)["document_ledger"][0]
    assert doc.body == "دفعي: سقطت المطالبة بالتقادم."
    assert doc.overridden and doc.key == "defendant_plea-1"


def test_edited_facts_change_verdict():
    # وقائع تتضمّن السداد/البراءة ⇒ يرفض المحرّك الدعوى (تعديل النص يغيّر مجرى الحكم).
    state = {"case_type": "تجاري", "claim_subject": "مطالبة", "claim_value": 250000.0,
             "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي", title="ص",
                                          body="أقرّ المدعي أن المدعى عليه قد سدّد كامل المبلغ وبرئت ذمته.")]}
    adj = operators.adjudicate(state)
    assert adj["direction"] == "رفض الدعوى"
    assert "رفض" in adj["operative"]
    assert not adj["blocked"]
