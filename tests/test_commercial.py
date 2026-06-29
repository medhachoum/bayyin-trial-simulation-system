"""
اختبارات التخصّص التجاري وطبقة البحث القضائي (المبادئ والسوابق):
  • الاختصاص النوعي: المحكمة التجارية تقبل التجاري وتحيل غيره نوعياً.
  • طبقة البحث: استرجاع مبادئ وسوابق وإشارة اتجاه (وهمي).
  • التأصيل: المبادئ/السوابق مصادرُ معروفةٌ (لا مختلقة) تُؤصَّل بالاقتباس المُسترجَع.
  • حدّ file_search: مخزنان كحدّ أقصى لكل نداء.
"""
from __future__ import annotations

from bayyin import research, rules, settings, sources
from bayyin.settings import COMMERCIAL_PRECEDENT_STORES, VECTOR_STORES
from bayyin.sources import Cite, CiteStatus
from bayyin.state import Document, DocType, Party
from bayyin.tools import file_search_tool, precedents_tool

settings.MOCK = True


# ---------- المخزونات الجديدة ----------
def test_new_commercial_stores_wired():
    for k in ("search_commercial_principles", "search_commercial_precedents_1",
              "search_commercial_precedents_2"):
        assert k in VECTOR_STORES and VECTOR_STORES[k]["id"].startswith("vs_")
    # المخزن التجاري القديم لم يعد مرجعاً منطقياً.
    assert "search_commercial_precedents" not in VECTOR_STORES


def test_precedents_tool_uses_both_stores_within_limit():
    t = precedents_tool()
    assert len(t) == 1 and t[0]["type"] == "file_search"
    assert len(t[0]["vector_store_ids"]) == 2          # المخزنان معاً
    assert len(COMMERCIAL_PRECEDENT_STORES) == 2


def test_file_search_caps_at_two():
    t = file_search_tool("search_saudi_codes", "search_commercial_principles",
                         "search_commercial_precedents_1")
    assert len(t[0]["vector_store_ids"]) == 2          # لا يتجاوز الحدّ أبداً


# ---------- الاختصاص النوعي (تجاري فقط) ----------
def _state(case_type="تجاري", subject="مطالبة بثمن بضاعة بموجب عقد توريد", body="مطالبة بثمن توريد."):
    return {"case_type": case_type, "claim_subject": subject, "claim_value": 250000.0,
            "parties": [Party(role="مدعي", name="أ"), Party(role="مدعى عليه", name="ب")],
            "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي",
                                         title="صحيفة", body=body)]}


def test_commercial_case_within_jurisdiction():
    ok, reason = rules.commercial_jurisdiction(_state())
    assert ok and reason == ""


def test_labor_case_declined_specifically():
    ok, reason = rules.commercial_jurisdiction(
        _state("عمالي", "مكافأة نهاية الخدمة", "فصل تعسفي ومكافأة نهاية الخدمة."))
    assert not ok and "الاختصاص النوعي" in reason


def test_family_marker_in_body_declined():
    ok, reason = rules.commercial_jurisdiction(
        _state("أخرى", "نزاع", "طلب حضانة ونفقة بعد الطلاق."))
    assert not ok and "أحوال" in reason


def test_commercial_supply_not_false_declined():
    # قضية توريدٍ تجاريةٍ بحتة لا تُردّ خطأً.
    ok, _ = rules.commercial_jurisdiction(
        _state("تجاري", "عقد توريد", "توريد بضاعة بقيمة المطالبة، ونزاع على المطابقة."))
    assert ok


# ---------- طبقة البحث القضائي (وهمي) ----------
def test_research_returns_principles_and_precedents():
    r = research.research(_state())
    assert len(r["principles"]) >= 1 and len(r["precedents"]) >= 1
    assert r["outcome_signal"] in ("للمدعي", "للمدعى عليه", "مختلط", "غير حاسم")
    assert "مبادئ" in r["summary"] or "سوابق" in r["summary"]


# ---------- تأصيل المبادئ/السوابق ----------
def test_principle_cite_verified_with_quote():
    c = Cite(system="المبادئ القضائية التجارية", article="مبدأ-1",
             quote="للمشتري حبس ما يقابل العيب من الثمن", claim="حبس الثمن بقدر العيب")
    assert sources.verify_cite(c)[0] == CiteStatus.VERIFIED


def test_principle_cite_unloaded_without_quote():
    c = Cite(system="السوابق القضائية التجارية", article="سابقة-9", quote="", claim="x")
    assert sources.verify_cite(c)[0] == CiteStatus.UNLOADED


def test_unknown_system_still_fabricated():
    assert sources.verify_cite(Cite(system="مبادئ مختلقة", article="1"))[0] == CiteStatus.FABRICATED


def test_principle_counts_toward_grounding():
    g = sources.assess_grounding([
        Cite(system="المبادئ القضائية التجارية", article="مبدأ-1", quote="نصٌّ مُسترجَع", claim="y")])
    assert g["ok"] and g["verified"] >= 1 and g["fabricated"] == 0


# ---------- تأصيل المبدأ/السابقة ضد الاسترجاع الفعلي (سدّ ثغرة اختلاق الاقتباس) ----------
def test_principle_quote_must_match_retrieved_evidence():
    c = Cite(system="المبادئ القضائية التجارية", article="مبدأ-1",
             quote="للمشتري حبس ما يقابل العيب من الثمن", claim="حبس الثمن")
    # اقتباسٌ لا يقابل أيّ نصٍّ مُسترجَع → لا يُعتدّ به (UNLOADED) رغم أنه غير فارغ.
    assert sources.verify_cite(c, ["وثيقةٌ أخرى لا علاقة لها بالموضوع إطلاقاً"])[0] == CiteStatus.UNLOADED
    # اقتباسٌ يطابق نصاً مُسترجَعاً فعلاً → مؤصَّل.
    assert sources.verify_cite(c, ["القاعدة أن للمشتري حبس ما يقابل العيب من الثمن"])[0] == CiteStatus.VERIFIED


def test_grounding_blocks_fabricated_principle_quote():
    cites = [Cite(system="المبادئ القضائية التجارية", article="مبدأ مخترَع",
                  quote="نصٌّ لا أصل له في المسترجَع", claim="x")]
    g = sources.assess_grounding(cites, ["نصٌّ مُسترجَعٌ مختلفٌ تماماً عن الاقتباس"])
    assert not g["ok"] and g["verified"] == 0          # لم يُحتسَب مؤصَّلاً


# ---------- طبقة البحث: حجب اتجاه السوابق عن القاضي ----------
def test_judge_context_hides_outcome_signal():
    r = research.research(_state())
    full = research.summary_text(r["principles"], r["precedents"], r["outcome_signal"], for_judge=False)
    judge = research.summary_text(r["principles"], r["precedents"], r["outcome_signal"], for_judge=True)
    assert "إشارة اتجاه السوابق" in full          # العرض/الخصم يرى الاتجاه
    assert "إشارة اتجاه السوابق" not in judge      # القاضي لا يراه (تفادي الإرساء)
    assert "مبادئ قضائية" in judge                 # لكنه يرى المبادئ القابلة للاستشهاد


# ---------- العقدة والرسم البياني الكامل ----------
def test_research_node_idempotent():
    from bayyin import nodes
    assert nodes.research_node({"research": {"x": 1}}) == {}


def _graph_state(case_type="تجاري", subject="مطالبة بثمن بضاعة بموجب عقد توريد",
                 body="مطالبة بثمن بضاعة 250,000 ريال بموجب عقد توريد.", value=250000.0):
    s = _state(case_type, subject, body)
    s["claim_value"] = value
    s.update({"case_id": "C-" + case_type, "scripted_plaintiff_replies": ["أتمسّك بطلبي."],
              "overrides": {}, "filing_date": "2026-01-15", "deadlines": {}})
    return s


def test_full_graph_populates_and_injects_research():
    from bayyin import nodes
    from bayyin.graph import build_graph
    final = build_graph().invoke(_graph_state(), {"configurable": {"thread_id": "t-research-inj"}})
    r = final.get("research") or {}
    assert len(r.get("principles", [])) >= 1 and len(r.get("precedents", [])) >= 1
    assert "مبادئ وسوابق تجارية ذات صلة" in nodes._case_file_text(final)   # حُقن الملخّص
    assert "إشارة اتجاه السوابق" not in nodes._case_file_text(final, for_judge=True)  # محجوب عن القاضي
    assert final.get("judgment") is not None


def test_default_models_are_gpt55():
    from bayyin import config
    d = config.defaults()
    assert d["models"]["standard"] == "gpt-5.5"
    assert d["models"]["pro"] == "gpt-5.5"
    assert d["models"]["judge"] == "gpt-5.5"
    assert d["efforts"]["judge"] == "high"        # القاضي: جهدٌ عالٍ افتراضاً
    assert "effort_options" in d


def test_judge_ops_run_at_high_effort():
    from bayyin import operators
    assert operators._effort_for_op("tasbib") == "high"   # عمليات القاضي
    assert operators._effort_for_op("tatbiq") == "high"
    assert operators._effort_for_op("tahrir") is None      # تحرير/محل النزاع: جهد القياسي
    assert operators._effort_for_op("mahal") is None


def test_effort_passes_into_responses_kwargs():
    # OpenAILLM.complete يبني reasoning={"effort": ...} فقط حين يُمرَّر جهد.
    import inspect
    from bayyin import llm
    src = inspect.getsource(llm.OpenAILLM.complete)
    assert '"effort"' in src and "reasoning" in src


def test_effort_changes_cache_key(tmp_path, monkeypatch):
    from bayyin import llm, settings as st
    monkeypatch.setattr(llm, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(st, "LLM_CACHE_FRESH", False)
    calls = {"n": 0}

    class _Inner:
        def complete(self, *, model, system, user, tools=None, schema=None, role=None, effort=None):
            calls["n"] += 1
            return {"text": f"r{calls['n']}", "data": None, "sources": [], "evidence": []}

    c = llm.CachingLLM(_Inner())
    c.complete(model="m", system="s", user="u", effort=None)
    c.complete(model="m", system="s", user="u", effort="high")   # جهدٌ مختلف → مفتاحٌ مختلف
    assert calls["n"] == 2


def test_caching_llm_incremental(tmp_path, monkeypatch):
    """التخزين التدريجي: نفس المدخلات → نداءٌ واحد؛ مدخلٌ مختلف → نداءٌ جديد؛ «توليد جديد» يتجاهل الكاش."""
    from bayyin import llm, settings as st
    monkeypatch.setattr(llm, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(st, "LLM_CACHE_FRESH", False)
    calls = {"n": 0}

    class _Inner:
        def complete(self, *, model, system, user, tools=None, schema=None, role=None, effort=None):
            calls["n"] += 1
            return {"text": f"r{calls['n']}", "data": None, "sources": [], "evidence": []}

    c = llm.CachingLLM(_Inner())
    a = c.complete(model="m", system="s", user="u1")
    b = c.complete(model="m", system="s", user="u1")     # نفس المدخلات → من الكاش
    assert calls["n"] == 1 and a == b
    c.complete(model="m", system="s", user="u2")          # مدخلٌ مختلف (محاكاة تعديل عقدة) → نداءٌ جديد
    assert calls["n"] == 2
    monkeypatch.setattr(st, "LLM_CACHE_FRESH", True)       # «توليد جديد» يتجاهل القراءة
    c.complete(model="m", system="s", user="u1")
    assert calls["n"] == 3


def test_noncommercial_referred_not_rejected():
    from bayyin.graph import build_graph
    final = build_graph().invoke(_graph_state("عمالي", "مكافأة نهاية الخدمة", "فصل تعسفي ومكافأة نهاية الخدمة.", 80000.0),
                                 {"configurable": {"thread_id": "t-referral"}})
    assert final.get("intake_referred") is True
    assert final.get("referral_decision") and "الاختصاص النوعي" in final["referral_decision"]
    assert not final.get("research")        # لم يُجرَ البحث
    assert final.get("judgment") is None     # لا حكم موضوعي — أُحيلت لا رُدّت


# ---------- ② الاستئناف عبر بوابة التأصيل ----------
def test_appellate_ruling_is_grounded_and_final():
    from bayyin import panel
    from bayyin.state import Citation, Ruling
    state = _graph_state()
    state["judgment"] = Ruling(facts="وقائع", reasons="أسباب", operative="إلزام المدعى عليه بالمبلغ",
                               citations=[Citation(claim="c", source_tool="نظام المعاملات المدنية", source_ref="العقد")],
                               appealable=True, direction="للمدعي")
    state["document_ledger"].append(Document(doc_type=DocType.APPEAL_BRIEF, author_role="مستأنف",
                                             title="اعتراض", body="أعترض على الحكم."))
    upd = panel.run_panel(state)
    aj = upd["appeal_judgment"]
    assert len(upd["panel_votes"]) == 3
    assert aj.citations and aj.blocked is False        # خضع لبوابة التأصيل ومرّ
    assert aj.confidence in ("عالية", "متوسطة")
    assert aj.appealable is False and aj.appeal_route == "نهائي"


# ---------- ③ تصدير الصك (DOCX) ----------
def test_export_docx_builds_valid_file():
    from bayyin.export_docx import build_ruling_docx
    data = build_ruling_docx({
        "kind": "الحكم الابتدائي", "facts": "وقائع الدعوى", "reasons": "أسباب الحكم",
        "operative": "إلزام المدعى عليه بأداء المبلغ", "confidence": "عالية",
        "route": "التماس إعادة النظر", "appealable": False, "blocked": False,
        "citations": [{"claim": "وجوب الوفاء", "tool": "نظام المعاملات المدنية", "ref": "العقد"}],
        "chain": [{"label": "التحرير", "ok": True, "issues": []}], "flags": [],
        "meta": {"case_id": "TC-1", "case_type": "تجاري", "value": 250000}})
    assert isinstance(data, bytes) and data[:2] == b"PK" and len(data) > 1500   # ملفّ DOCX (zip)


# ---------- ④ مرونة الوضع الحقيقي (إعادة المحاولة) ----------
def test_llm_retries_on_transient_error(monkeypatch):
    from bayyin import llm, settings as st
    monkeypatch.setattr(st, "LLM_MAX_RETRIES", 3)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    class Boom(Exception):
        pass

    o = llm.OpenAILLM.__new__(llm.OpenAILLM)   # تجاوز __init__ (لا عميل حقيقي)
    o._transient = (Boom,)
    calls = {"n": 0}

    class _Resp:
        class responses:
            @staticmethod
            def create(**k):
                calls["n"] += 1
                if calls["n"] < 2:
                    raise Boom("عابر")
                return type("R", (), {"output_text": "ok"})()

    o.client = _Resp()
    r = o._create({"model": "m"})
    assert calls["n"] == 2 and r.output_text == "ok"   # فشلت مرّةً ثم نجحت
