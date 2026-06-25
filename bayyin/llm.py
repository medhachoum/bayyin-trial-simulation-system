"""
طبقة النماذج اللغوية: غلاف موحّد فوق OpenAI Responses API، ونموذج وهمي
(MockLLM) يشغّل النظام كاملاً بلا أي نداء API — للتطوير والعرض والاختبار.

الواجهة الموحّدة complete(...) تُرجع: {"text": str, "data": dict|None}
- data تُملأ عندما يُطلب مخرَج JSON منظَّم (المُوجِّه، المدعى عليه، الحكم).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from . import settings


def _extract_sources(resp) -> list[str]:
    """استخراج مراجع نتائج file_search فعلياً من استجابة Responses API (أفضل جهد، M5)."""
    sources: list[str] = []
    try:
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") == "file_search_call":
                for r in getattr(item, "results", []) or []:
                    ref = getattr(r, "filename", None) or getattr(r, "file_id", None)
                    if ref:
                        sources.append(str(ref))
    except Exception:
        pass
    return sources


def _extract_evidence(resp) -> list[str]:
    """استخراج نصوص المقاطع المُسترجَعة فعلاً من file_search — تُحقَّق بها اقتباسات
    المبادئ/السوابق ضد الاسترجاع الحقيقي (سدّ ثغرة اختلاق الاقتباس)."""
    out: list[str] = []
    try:
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") == "file_search_call":
                for r in getattr(item, "results", []) or []:
                    txt = getattr(r, "text", None)
                    if not txt:
                        content = getattr(r, "content", None) or []
                        parts = [getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                                 for p in content]
                        txt = " ".join(p for p in parts if p)
                    if txt:
                        out.append(str(txt))
    except Exception:
        pass
    return out


# ===========================================================================
# التنفيذ الحقيقي عبر Responses API
# ===========================================================================
class OpenAILLM:
    def __init__(self) -> None:
        # تحميل .env (يحوي OPENAI_API_KEY) إن وُجد.
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        from openai import OpenAI
        key = getattr(settings, "RUNTIME_API_KEY", None)
        self.client = OpenAI(api_key=key) if key else OpenAI()

    def complete(self, *, model: str, system: str, user: str,
                 tools: list[dict] | None = None, schema: dict | None = None,
                 role: str | None = None, effort: str | None = None) -> dict:
        kwargs: dict = {"model": model, "instructions": system, "input": user}
        if tools:
            kwargs["tools"] = tools
        if effort:  # جهد الاستدلال (للنماذج الاستدلالية كـ gpt-5.5)
            kwargs["reasoning"] = {"effort": effort}
        if schema is not None:
            # مخرَج JSON منظَّم صارم (structured outputs)
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema.get("title", "output"),
                    "schema": schema,
                    "strict": True,
                }
            }
        resp = self.client.responses.create(**kwargs)
        text = getattr(resp, "output_text", "") or ""
        data = None
        if schema is not None and text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        return {"text": text, "data": data, "sources": _extract_sources(resp),
                "evidence": _extract_evidence(resp)}


# ===========================================================================
# نموذج وهمي — محتوى عربي واقعي يكفي لتشغيل الدعوى من القيد حتى الحكم
# ===========================================================================
def _mock_router(_user: str) -> dict:
    return {"text": "", "data": {"case_type": "تجاري", "complexity": "عادية"}}


def _mock_registrar(_user: str) -> dict:
    return {
        "text": (
            "تدقيق موضوعي: الطلبات محدّدة، والسند النظامي قائم (مطالبة بثمن "
            "بضاعة بموجب عقد توريد)، والاختصاص ينعقد للمحكمة التجارية. لا ملاحظة جوهرية."
        ),
        "data": None,
    }


def _mock_defendant(user: str) -> dict:
    second = "الثانية" in user or "رد المدعي" in user
    title = "المذكرة الجوابية الثانية" if second else "المذكرة الجوابية الأولى"
    body = (
        f"{title} من وكيل المدعى عليه:\n"
        "أولاً (الدفوع الشكلية): الدفع بعدم الاختصاص المكاني لرفع الدعوى في غير "
        "موطن المدعى عليه، والتمسك بشرط فضّ النزاع ودّياً المنصوص عليه في العقد.\n"
        "ثانياً (الدفوع الموضوعية): إنكار استلام كامل الكمية محل المطالبة، "
        "والدفع بأن المدعي أخلّ بمواصفات التوريد المتفق عليها، فلا يستحق كامل الثمن.\n"
        "لذا نلتمس رفض الدعوى، واحتياطياً ندب خبير لحصر الكميات المستلمة فعلاً."
    )
    citations = [
        {
            "claim": "الدفع بعدم الاختصاص المكاني",
            "source_tool": "search_saudi_codes",
            "source_ref": "نظام المرافعات الشرعية — مادة الاختصاص المكاني",
            "quote": "ترفع الدعوى إلى محكمة موطن المدعى عليه ما لم يرد نص خاص.",
        },
        {
            "claim": "ربط استحقاق الثمن بمطابقة المواصفات",
            "source_tool": "search_commercial_principles",
            "source_ref": "مبدأ تجاري — أثر مخالفة المواصفات على الثمن",
            "quote": "للمشتري حبس ما يقابل العيب من الثمن عند مخالفة المواصفات.",
        },
    ]
    return {"text": body, "data": {"title": title, "body": body, "citations": citations}}


def _mock_judge(_user: str) -> dict:
    data = {
        "facts": (
            "أقام المدعي دعواه مطالباً المدعى عليه بثمن بضاعة وُرّدت بموجب عقد "
            "توريد، وقدره المبلغ المدّعى به. دفع المدعى عليه بعدم الاختصاص وبمخالفة "
            "المواصفات، وتبادل الطرفان المذكرات، ثم حُجزت الدعوى للحكم."
        ),
        "reasons": (
            "وحيث ثبت قيام عقد التوريد وتسلّم المدعى عليه البضاعة بموجب محاضر "
            "الاستلام، وحيث إن العقد شريعة المتعاقدين، وحيث لم يقم المدعى عليه "
            "دليلاً كافياً على مخالفة المواصفات بعد أن مكّنته المحكمة من ذلك، "
            "فإن الدفوع الموضوعية غير قائمة على سند، والاختصاص منعقد للدائرة."
        ),
        "operative": (
            "حكمت المحكمة بإلزام المدعى عليه بأن يؤدي للمدعي المبلغ المطالب به، "
            "ورفض ما عدا ذلك من طلبات."
        ),
        "citations": [
            {
                "claim": "العقد شريعة المتعاقدين ووجوب الوفاء بالالتزام",
                "source_tool": "search_saudi_codes",
                "source_ref": "نظام المعاملات المدنية — أثر العقد",
                "quote": "يجب الوفاء بما اشتمل عليه العقد وفقاً لما تقتضيه أحكامه.",
            },
            {
                "claim": "عبء إثبات مخالفة المواصفات على المدعى عليه",
                "source_tool": "search_commercial_principles",
                "source_ref": "مبدأ تجاري — عبء إثبات العيب",
                "quote": "البيّنة على من ادّعى خلاف الأصل.",
            },
        ],
    }
    return {"text": json.dumps(data, ensure_ascii=False), "data": data}


def _mock_expert(_user: str) -> dict:
    body = (
        "تقرير الخبير المنتدب:\n"
        "بعد الاطلاع على محاضر الاستلام والفواتير وعقد التوريد، تبيّن أن الكمية "
        "المستلمة فعلاً تطابق المتفق عليه في معظم البنود، مع نقص يسير لا يؤثر "
        "جوهرياً على استحقاق الثمن. ويوصي الخبير باحتساب خصم محدود مقابل النقص."
    )
    return {"text": body, "data": {"title": "تقرير الخبير", "body": body, "citations": [
        {"claim": "منهجية ندب الخبرة", "source_tool": "search_saudi_consultations",
         "source_ref": "أصول الخبرة القضائية", "quote": ""}]}}


def _mock_appellee(_user: str) -> dict:
    body = (
        "مذكرة المستأنف ضده: الحكم الابتدائي صحيح في تطبيقه للنظام وتسبيبه، "
        "وأسباب الاعتراض لا تنال من سلامة الحكم، فنلتمس تأييده ورفض الاستئناف."
    )
    return {"text": body, "data": {"title": "مذكرة جوابية على الاستئناف", "body": body,
            "citations": [{"claim": "سلامة تطبيق النظام", "source_tool": "search_saudi_codes",
                           "source_ref": "نظام المحاكم التجارية", "quote": ""}]}}


def _mock_panel(user: str) -> dict:
    # تصويت حتمي حسب عدسة القاضي نفسه (المعلَّمة بـ «...»)، لا آراء زملائه.
    vote = "تعديل" if "«الإنصاف" in user else "تأييد"
    return {"text": "", "data": {"vote": vote,
            "opinion": f"بعد مراجعة أوراق الدعوى وأسباب الاعتراض، أرى {vote} الحكم المستأنف."}}


# --- محاكاة العمليات الاستدلالية السبع (قضية توريد متّسقة تنتهي بحكمٍ مؤصَّل) ---
def _mock_op_tahrir(_u):
    return {"text": "", "data": {"requests": [{"type": "مبلغ", "amount": 250000}],
            "summary": "يطالب المدعي بثمن بضاعة قدره 250,000 ريال بموجب عقد توريد، وله الصفة والمصلحة."}}


def _mock_op_takyif(_u):
    return {"text": "", "data": {"nature": "عقد توريد (بيع تجاري)", "governing_system": "نظام المعاملات المدنية",
            "cite": {"system": "نظام المعاملات المدنية", "article": "العقد",
                     "quote": "العقد شريعة المتعاقدين", "claim": "العقد ملزمٌ لطرفيه"},
            "summary": "النزاع عقد توريدٍ يحكمه نظام المعاملات المدنية، والاختصاص النوعي للمحكمة التجارية."}}


def _mock_op_mahal(_u):
    return {"text": "", "data": {"agreed": ["قيام عقد التوريد"], "contested": ["مطابقة الكمية والمواصفات"],
            "defenses": ["الاختصاص", "المطابقة"],
            "summary": "المتّفق: قيام العقد. المتنازَع: المطابقة. الدفوع الجوهرية: الاختصاص والمطابقة."}}


def _mock_op_ithbat(_u):
    return {"text": "", "data": {"findings": [
        {"point": "تسلّم البضاعة", "burden_on": "المدعى عليه (لنفي المطابقة)", "established": True,
         "basis": {"system": "نظام الإثبات", "article": "1", "quote": "البيّنة على من ادّعى",
                   "claim": "عبء نفي المطابقة على المدعى عليه"}},
        {"point": "حجية محاضر الاستلام", "burden_on": "المدعى عليه", "established": True,
         "basis": {"system": "نظام الإثبات", "article": "حجية المحرر", "quote": "المحرّر العادي حجّةٌ على من وقّعه",
                   "claim": "محاضر الاستلام الموقّعة حجّة"}}],
        "summary": "ثبت التسلّم بمحاضر موقّعة، ولم يُثبت المدعى عليه مخالفة المواصفات."}}


def _mock_op_tatbiq(_u):
    return {"text": "", "data": {"rule": {"system": "نظام المعاملات المدنية", "article": "العقد",
            "quote": "يجب الوفاء بما اشتمل عليه العقد", "claim": "وجوب الوفاء بالثمن"},
            "conclusion": "يستحق المدعي الثمن المطالب به.",
            "summary": "بإنزال قاعدة وجوب الوفاء بالعقد على الوقائع الثابتة، يستحق المدعي الثمن."}}


def _mock_op_tasbib(user):
    # حسّاسٌ لنصّ القضية (يشمل المذكرات المعدّلة من المستخدم): إشاراتُ السداد/البراءة/التنازل ترجّح الرفض.
    u = user or ""
    # إشاراتُ سدادٍ واقعٍ/براءةٍ/تنازل (لا مجرّد «المطالبة بالسداد» من المدعي).
    if any(k in u for k in ("سدّد", "تم السداد", "براءة الذمة", "أبرأ", "تنازل", "أسقط", "إسقاط الدعوى")):
        return {"text": "", "data": {
            "reasons": "وحيث تبيّن من أوراق الدعوى ما يفيد سدادَ المبلغ أو براءةَ الذمة أو تنازلَ المدعي، "
                       "وحيث إن البيّنة على من ادّعى ولم يَثبُت بقاءُ المديونية، فإن الدعوى غير قائمةٍ على سند.",
            "operative": "حكمت المحكمة برفض الدعوى.",
            "direction": "رفض الدعوى", "granted": [], "addressed_defenses": ["الاختصاص", "المطابقة"],
            "cites": [
                {"system": "نظام الإثبات", "article": "1", "quote": "البيّنة على من ادّعى", "claim": "عبء الإثبات على المدعي"},
                {"system": "نظام المعاملات المدنية", "article": "العقد", "quote": "يجب الوفاء بما اشتمل عليه العقد", "claim": "أثر السداد/البراءة على الالتزام"}]}}
    return {"text": "", "data": {
        "reasons": "وحيث ثبت قيام العقد وتسلّم البضاعة بمحاضر موقّعة، وحيث العقد شريعة المتعاقدين، ولم يُثبت "
                   "المدعى عليه مخالفة المواصفات بعد تمكينه، والاختصاص منعقدٌ للدائرة التجارية.",
        "operative": "حكمت المحكمة بإلزام المدعى عليه بأن يؤدي للمدعي مبلغ 250,000 ريال، ورفض ما عدا ذلك.",
        "direction": "للمدعي", "granted": [{"type": "مبلغ", "amount": 250000}],
        "addressed_defenses": ["الاختصاص", "المطابقة"],
        "cites": [
            {"system": "نظام المعاملات المدنية", "article": "العقد", "quote": "العقد شريعة المتعاقدين", "claim": "وجوب الوفاء"},
            {"system": "نظام الإثبات", "article": "1", "quote": "البيّنة على من ادّعى", "claim": "عبء النفي على المدعى عليه"},
            {"system": "نظام المحاكم التجارية", "article": "16", "quote": "المنازعات بين التجار", "claim": "الاختصاص النوعي"}]}}


def _mock_research_principles(_u):
    return {"text": "", "data": {"principles": [
        {"principle": "استحقاق البائع للثمن يقابله التزامه بالمطابقة؛ وللمشتري حبس ما يقابل العيب من الثمن.",
         "ref": "مبدأ تجاري — مطابقة المبيع والثمن",
         "quote": "للمشتري حبس ما يقابل العيب من الثمن عند مخالفة المواصفات",
         "relevance": "صلب النزاع: مطالبة بثمن توريد يقابلها دفعٌ بمخالفة المواصفات."},
        {"principle": "الاختصاص النوعي للمحكمة التجارية في منازعات التجار بسبب أعمالهم التجارية.",
         "ref": "مبدأ تجاري — الاختصاص النوعي",
         "quote": "تختص المحكمة التجارية بالمنازعات بين التجار بسبب أعمالهم التجارية",
         "relevance": "يردّ الدفع بعدم الاختصاص."}],
        "note": "مبادئ مستخلصة من قاعدة المبادئ التجارية، مطابقةٌ لوقائع النزاع."}}


def _mock_research_precedents(_u):
    return {"text": "", "data": {"precedents": [
        {"summary": "مطالبة بثمن بضاعةٍ وُرّدت بموجب عقد توريد، ودفع المشتري بعيوبٍ في المواصفات.",
         "holding": "إلزام المشتري بالثمن لثبوت التسليم وعجزه عن إثبات العيب المؤثّر.",
         "outcome": "للمدعي", "ref": "سابقة تجارية — توريد/مطابقة"},
        {"summary": "نزاع توريدٍ مع نقصٍ يسيرٍ في الكمية المستلمة.",
         "holding": "خصمٌ محدودٌ مقابل النقص مع استحقاق باقي الثمن.",
         "outcome": "مختلط", "ref": "سابقة تجارية — نقص الكمية"}],
        "outcome_signal": "للمدعي",
        "note": "سوابق استئناسيةٌ مشابهةٌ للوقائع، لا تقيّد القاضي."}}


def _mock_incident_jurisdiction(_u):
    return {"text": "", "data": {"upheld": False,
        "operative": "رفض الدفع بعدم الاختصاص لانعقاد الاختصاص النوعي للدائرة التجارية.",
        "reasoning": "لمّا كانت المنازعة بين تاجرين بسبب أعمالهما التجارية، فالاختصاص للمحكمة التجارية.",
        "cite": {"system": "نظام المحاكم التجارية", "article": "16", "quote": "المنازعات بين التجار", "claim": "الاختصاص النوعي منعقد"}}}


def _mock_incident_prescription(_u):
    return {"text": "", "data": {"upheld": True,
        "operative": "قبول الدفع بالتقادم والقضاء بعدم سماع الدعوى لمُضيّ المدة النظامية.",
        "reasoning": "لمُضيّ المدة النظامية من وقت الاستحقاق دون مطالبةٍ قاطعةٍ للتقادم ولا إقرارٍ بالحق.",
        "cite": {"system": "نظام المعاملات المدنية", "article": "التقادم", "quote": "لا تُسمع دعوى الالتزام بعد مُضيّ المدة النظامية", "claim": "سقوط سماع الدعوى بالتقادم"}}}


def _mock_incident_inadmissibility(_u):
    return {"text": "", "data": {"upheld": True,
        "operative": "قبول الدفع بعدم القبول والقضاء بعدم قبول الدعوى لانتفاء الصفة/المصلحة.",
        "reasoning": "لانتفاء صفة/مصلحة المدعي، وهي شرطٌ لقبول الدعوى، فلا يُنظر في موضوعها.",
        "cite": {"system": "نظام المرافعات الشرعية", "article": "شروط الدعوى", "quote": "يُشترط لقبول الدعوى الصفة والمصلحة", "claim": "انتفاء شرط القبول"}}}


def _mock_incident_incidental(_u):
    return {"text": "", "data": {"upheld": True,
        "operative": "قبول الطلب العارض وضمّه للدعوى الأصلية للفصل فيهما معاً.",
        "reasoning": "لارتباط الطلب العارض بالدعوى الأصلية ارتباطاً لا يقبل التجزئة.",
        "cite": {"system": "نظام المرافعات الشرعية", "article": "الطلبات العارضة", "quote": "تُنظر الطلبات العارضة مع الدعوى الأصلية", "claim": "ضمّ الطلب العارض"}}}


_MOCKS = {
    "router": _mock_router,
    "research_principles": _mock_research_principles,
    "research_precedents": _mock_research_precedents,
    "incident_jurisdiction": _mock_incident_jurisdiction,
    "incident_prescription": _mock_incident_prescription,
    "incident_inadmissibility": _mock_incident_inadmissibility,
    "incident_incidental": _mock_incident_incidental,
    "registrar": _mock_registrar,
    "defendant": _mock_defendant,
    "judge": _mock_judge,
    "expert": _mock_expert,
    "appellee": _mock_appellee,
    "panel": _mock_panel,
    "op_tahrir": _mock_op_tahrir,
    "op_takyif": _mock_op_takyif,
    "op_mahal": _mock_op_mahal,
    "op_ithbat": _mock_op_ithbat,
    "op_tatbiq": _mock_op_tatbiq,
    "op_tasbib": _mock_op_tasbib,
}


class MockLLM:
    def complete(self, *, model: str, system: str, user: str,
                 tools: list[dict] | None = None, schema: dict | None = None,
                 role: str | None = None, effort: str | None = None) -> dict:
        builder = _MOCKS.get(role or "", lambda u: {"text": "—", "data": None})
        out = builder(user)
        out.setdefault("sources", [])
        out.setdefault("evidence", [])
        return out


# ===========================================================================
# تخزينٌ محتوى-معنوَن (incremental) — يجعل تعديل عقدةٍ وإعادةَ التشغيل يُعيد حساب
# العُقَد المتأثّرة فقط؛ فما لم تتغيّر مدخلاته (model+system+user+tools+schema) يعود
# فورياً من القرص بلا نداءٍ ولا تكلفة. يُغلَّف به الحقيقيُّ فقط (لا الوهمي).
# ===========================================================================
_CACHE_DIR = Path(os.getenv("BAYYIN_CACHE_DIR") or (Path(tempfile.gettempdir()) / "bayyin_llm_cache"))


def _cache_key(model, system, user, tools, schema, role, effort) -> str:
    payload = json.dumps({"m": model, "s": system, "u": user, "t": tools,
                          "sc": schema, "r": role, "e": effort},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CachingLLM:
    """غلافٌ يخزّن مخرجات النموذج على القرص بمفتاح المحتوى (أفضل جهد؛ يفشل بأمان)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def complete(self, *, model, system, user, tools=None, schema=None, role=None, effort=None) -> dict:
        f = _CACHE_DIR / (_cache_key(model, system, user, tools, schema, role, effort) + ".json")
        if not getattr(settings, "LLM_CACHE_FRESH", False):
            try:
                if f.exists():
                    return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        res = self.inner.complete(model=model, system=system, user=user,
                                  tools=tools, schema=schema, role=role, effort=effort)
        try:
            f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return res


def get_llm():
    """مصنع النموذج: وهمي في وضع MOCK؛ وإلا الحقيقي مُغلَّفاً بالتخزين التدريجي (إن فُعِّل)."""
    if settings.MOCK:
        return MockLLM()
    inner = OpenAILLM()
    return CachingLLM(inner) if getattr(settings, "LLM_CACHE", True) else inner
