"""
الإجراء المتولّد من الحقوق — أوّل زيادة نحو «الإجراء يتولّد من ممارسة الخصوم».
الدفوع الشكلية (عدم الاختصاص، التقادم) ليست عُقداً مخصّصة، بل حقوقٌ يُمارسها
المدعى عليه في مذكرته؛ يُكتشف الدفع من نصّ المذكرة (يشمل نصّ المستخدم المعدّل)،
ويفصل فيه القاضي بنفس منطق الاستدلال (تكييف + تطبيق على القاعدة الحاكمة).
الدفع القاطع المقبول يُنهي الدعوى (عدم اختصاص/سقوط بالتقادم).
"""
from __future__ import annotations

from . import settings, sources
from .llm import get_llm
from .sources import Cite, CiteStatus
from .state import DocType

RIGHTS: dict[str, dict] = {
    "jurisdiction": {"label": "الدفع بعدم الاختصاص", "dispositive": True,
                     "triggers": ("عدم الاختصاص", "غير مختص", "عدم اختصاص", "الاختصاص المكاني", "ليست مختصة")},
    "prescription": {"label": "الدفع بالتقادم (سقوط الحق)", "dispositive": True,
                     "triggers": ("التقادم", "سقطت بالتقادم", "سقوط الحق", "مضي المدة", "تقادمت")},
    "inadmissibility": {"label": "الدفع بعدم القبول (انتفاء الصفة/المصلحة)", "dispositive": True,
                        "triggers": ("عدم قبول", "عدم القبول", "انتفاء صفة", "انتفاء الصفة", "لا صفة",
                                     "انتفاء مصلحة", "انتفاء المصلحة", "لا مصلحة", "سبق الفصل")},
    "incidental": {"label": "طلبٌ عارض", "dispositive": False,
                   "triggers": ("طلب عارض", "الطلب العارض", "طلباً عارضاً", "مطالبة مقابلة", "دعوى متقابلة")},
}

_PROMPT = {
    "jurisdiction": "أنت قاضٍ سعودي تفصل في الدفع بعدم الاختصاص. هل المحكمة مختصةٌ نوعياً ومكانياً؟ "
                    "استند لقاعدة الاختصاص من نظامها ولا تخترع مادة. أعد JSON.",
    "prescription": "أنت قاضٍ سعودي تفصل في الدفع بالتقادم. هل سقط سماع الدعوى بمضي المدة النظامية؟ "
                    "استند لقاعدة التقادم ولا تخترع مادة. أعد JSON.",
    "inadmissibility": "أنت قاضٍ سعودي تفصل في الدفع بعدم القبول (انتفاء الصفة أو المصلحة أو سبق الفصل). "
                       "استند لشروط قبول الدعوى ولا تخترع مادة. أعد JSON.",
    "incidental": "أنت قاضٍ سعودي تنظر طلباً عارضاً: هل يُقبل ضمّه للدعوى الأصلية للارتباط؟ "
                  "استند لقاعدة الطلبات العارضة ولا تخترع مادة. أعد JSON.",
}

_CITE = {"type": "object", "additionalProperties": False,
         "properties": {"system": {"type": "string"}, "article": {"type": "string"},
                        "quote": {"type": "string"}, "claim": {"type": "string"}},
         "required": ["system", "article", "quote", "claim"]}
INCIDENT_SCHEMA = {"title": "incident", "type": "object", "additionalProperties": False,
                   "properties": {"upheld": {"type": "boolean"}, "operative": {"type": "string"},
                                  "reasoning": {"type": "string"}, "cite": _CITE},
                   "required": ["upheld", "operative", "reasoning", "cite"]}


def _text(state) -> str:
    parts = []
    for d in state.get("document_ledger", []) or []:
        if d.doc_type in (DocType.CLAIM_SHEET, DocType.DEFENSE_MEMO):
            parts.append(d.body)
    return " ".join(parts)


def detect_invoked(state) -> list[str]:
    """يكتشف الدفوع الشكلية المثارة من نصّ الصحيفة/المذكرات (يشمل تعديل المستخدم)."""
    t = _text(state)
    return [k for k, r in RIGHTS.items() if any(x in t for x in r["triggers"])]


def adjudicate_incident(state, key: str) -> dict:
    """يفصل في الدفع: توليدٌ مُقيَّد + تحقّقٌ من إسناده. القبول يلزمه إسنادٌ غير مختلق."""
    r = RIGHTS[key]
    res = get_llm().complete(model=settings.GPT_JUDGE, system=_PROMPT[key], user=_text(state),
                             schema=INCIDENT_SCHEMA, role=f"incident_{key}", effort=settings.EFFORT_JUDGE)
    d = res.get("data") or {}
    c = d.get("cite") or {}
    cite = Cite(system=c.get("system", ""), article=c.get("article", ""),
                quote=c.get("quote", ""), claim=c.get("claim", ""))
    st, _why = sources.verify_cite(cite)
    upheld = bool(d.get("upheld")) and st != CiteStatus.FABRICATED
    return {"key": key, "label": r["label"], "upheld": upheld, "dispositive": r["dispositive"],
            "operative": d.get("operative", ""), "reasoning": d.get("reasoning", ""),
            "cite": {"system": cite.system, "article": cite.article, "quote": cite.quote, "claim": cite.claim},
            "grounded": st != CiteStatus.FABRICATED}
