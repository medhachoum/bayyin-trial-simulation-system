"""اختبارات الإجراء المتولّد من الحقوق: كشف الدفوع، الفصل فيها، وأثرها على المسار."""
from __future__ import annotations

from bayyin import procedure, settings
from bayyin.graph import build_graph
from bayyin.state import Document, DocType, Party

settings.MOCK = True


def _defense(body):
    return Document(doc_type=DocType.DEFENSE_MEMO, author_role="مدعى عليه", title="جوابية", body=body)


def _base(**kw):
    s = {"case_type": "تجاري", "claim_subject": "مطالبة بثمن بضاعة", "claim_value": 250000.0,
         "parties": [Party(role="مدعي", name="أ"), Party(role="مدعى عليه", name="ب")],
         "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي", title="ص",
                                      body="مطالبة بثمن بضاعة 250,000 ريال بموجب عقد توريد.")],
         "scripted_plaintiff_replies": ["أتمسّك بطلبي."]}
    s.update(kw)
    return s


# ---------- كشف الدفوع ----------
def test_detect_invoked():
    assert procedure.detect_invoked({"document_ledger": [_defense("أدفع بعدم الاختصاص المكاني.")]}) == ["jurisdiction"]
    assert procedure.detect_invoked({"document_ledger": [_defense("الدعوى سقطت بالتقادم لمضي المدة.")]}) == ["prescription"]
    assert procedure.detect_invoked({"document_ledger": [_defense("أنكر الاستلام فقط.")]}) == []


def test_adjudicate_incident_mock():
    j = procedure.adjudicate_incident({"document_ledger": [_defense("عدم الاختصاص")]}, "jurisdiction")
    assert j["upheld"] is False and j["dispositive"] and j["grounded"]
    # التقادم لا يُقبل إلا بتاريخَي استحقاقٍ وقيدٍ تُحسب بهما المدة (حارسٌ حتمي).
    p = procedure.adjudicate_incident(
        {"document_ledger": [_defense("التقادم")],
         "obligation_due_date": "2013-01-01", "filing_date": "2026-01-15"}, "prescription")
    assert p["upheld"] is True and p["dispositive"]


def test_prescription_fails_closed_without_dates():
    """غيابُ التواريخ → لا يُقبل الدفع بالتقادم مهما قال النموذج (fail-closed)."""
    p = procedure.adjudicate_incident({"document_ledger": [_defense("التقادم")]}, "prescription")
    assert p["upheld"] is False
    assert "التواريخ" in p["reasoning"] or "تاريخ" in p["reasoning"]


# ---------- أثر الدفع على المسار (عبر الرسم البياني) ----------
def test_prescription_defense_dismisses_case():
    state = _base(overrides={"defendant_plea-1": "الدفع الجوهري: سقطت الدعوى بالتقادم لمضي المدة النظامية دون مطالبة."},
                  obligation_due_date="2013-01-01", filing_date="2026-01-15")
    final = build_graph().invoke(state, {"configurable": {"thread_id": "t-presc"}})
    op = final["judgment"].operative
    assert ("سماع" in op or "تقادم" in op or "سقوط" in op)
    assert any(i["key"] == "prescription" and i["upheld"] for i in final.get("incidents", []))


def test_default_jurisdiction_rejected_then_merits():
    final = build_graph().invoke(_base(), {"configurable": {"thread_id": "t-jur"}})
    assert any(i["key"] == "jurisdiction" and not i["upheld"] for i in final.get("incidents", []))
    assert "إلزام" in final["judgment"].operative   # رُفض الدفع فمضت الدعوى للموضوع


def test_detect_new_defenses():
    assert procedure.detect_invoked({"document_ledger": [_defense("أدفع بعدم القبول لانتفاء الصفة.")]}) == ["inadmissibility"]
    assert procedure.detect_invoked({"document_ledger": [_defense("وأتقدّم بطلب عارض بمقابل الإيجار.")]}) == ["incidental"]


def test_inadmissibility_is_dispositive_incidental_is_not():
    a = procedure.adjudicate_incident({"document_ledger": [_defense("عدم القبول")]}, "inadmissibility")
    assert a["upheld"] and a["dispositive"]
    b = procedure.adjudicate_incident({"document_ledger": [_defense("طلب عارض")]}, "incidental")
    assert b["upheld"] and not b["dispositive"]   # يُضمّ ولا يُنهي الدعوى


def test_inadmissibility_dismisses_but_incidental_continues():
    f1 = build_graph().invoke(_base(overrides={"defendant_plea-1": "أدفع بعدم قبول الدعوى لانتفاء صفة المدعي."}),
                              {"configurable": {"thread_id": "t-inad"}})
    assert "عدم قبول" in f1["judgment"].operative          # دفعٌ قاطعٌ أنهى الدعوى
    f2 = build_graph().invoke(_base(overrides={"defendant_plea-1": "أتقدّم بطلب عارض مرتبطٍ بالدعوى الأصلية."}),
                              {"configurable": {"thread_id": "t-incid"}})
    assert any(i["key"] == "incidental" for i in f2.get("incidents", []))
    assert "إلزام" in f2["judgment"].operative              # ضُمّ الطلب العارض واستمرّت الدعوى للموضوع
