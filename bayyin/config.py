"""
إعدادات التشغيل القابلة للتخصيص من الواجهة:
  • مفتاح OpenAI (لكل تشغيل) — وإلا مفتاح .env.
  • اختيار نماذج OpenAI لكل طبقة (الموجِّه/القياسي/المتقدّم/القاضي).
  • معاينة وتعديل مطالبات النظام (System Prompts).
الافتراضيات محفوظة دائماً (لا تبدأ فارغة)؛ وكل تشغيل يُعيد ضبط الأصل ثم يطبّق ما اختاره المستخدم.
"""
from __future__ import annotations

from . import operators, prompts, settings

# المطالبات القابلة للتحرير: المفتاح المعروض → (النوع، المرجع)
PROMPT_REGISTRY: dict[str, tuple[str, str]] = {
    "المُسجِّل (تدقيق الصحيفة)": ("attr", "REGISTRAR"),
    "هيئة البحث — المبادئ القضائية": ("attr", "RESEARCH_PRINCIPLES"),
    "هيئة البحث — السوابق التجارية": ("attr", "RESEARCH_PRECEDENTS"),
    "وكيل المدعى عليه": ("attr", "DEFENDANT"),
    "وكيل المستأنف ضدّه": ("attr", "APPELLEE"),
    "القاضي — التكييف": ("op", "takyif"),
    "القاضي — الإثبات": ("op", "ithbat"),
    "القاضي — التطبيق": ("op", "tatbiq"),
    "القاضي — التسبيب والمنطوق": ("op", "tasbib"),
    "القاضي — تحديد محل النزاع": ("op", "mahal"),
}

_ORIG: dict | None = None


def _get_prompt(key: str) -> str:
    kind, ref = PROMPT_REGISTRY[key]
    return getattr(prompts, ref) if kind == "attr" else operators._P[ref]


def _set_prompt(key: str, val: str) -> None:
    kind, ref = PROMPT_REGISTRY[key]
    if kind == "attr":
        setattr(prompts, ref, val)
    else:
        operators._P[ref] = val


def _models() -> dict:
    return {"router": settings.GPT_ROUTER, "standard": settings.GPT_STANDARD,
            "pro": settings.GPT_PRO, "judge": settings.GPT_JUDGE}


def _efforts() -> dict:
    return {"router": settings.EFFORT_ROUTER, "standard": settings.EFFORT_STANDARD,
            "pro": settings.EFFORT_PRO, "judge": settings.EFFORT_JUDGE}


_VALID_EFFORTS = ("minimal", "low", "medium", "high")


def _norm_effort(v) -> str | None:
    v = (v or "").strip().lower()
    return v if v in _VALID_EFFORTS else None


def _capture_originals() -> None:
    global _ORIG
    if _ORIG is None:
        _ORIG = {"models": _models(), "efforts": _efforts(),
                 "prompts": {k: _get_prompt(k) for k in PROMPT_REGISTRY}}


def defaults() -> dict:
    """الافتراضيات للواجهة (تُعرض في صفحة الإعدادات)."""
    _capture_originals()
    return {"models": dict(_ORIG["models"]),
            "efforts": {k: (v or "") for k, v in _ORIG["efforts"].items()},
            "prompts": dict(_ORIG["prompts"]),
            "model_suggestions": ["gpt-5.4-mini", "gpt-5.5", "gpt-5.5-pro", "gpt-5.4-2026-03-05", "gpt-5.4-pro"],
            "effort_options": ["", "low", "medium", "high"]}


def apply(cfg: dict | None) -> None:
    """يُعيد ضبط الأصل ثم يطبّق اختيارات المستخدم (مفتاح/نماذج/جهد/مطالبات) لهذا التشغيل."""
    _capture_originals()
    # استعادة الأصل (تشغيلٌ مستقل عن سابقه)
    settings.GPT_ROUTER = _ORIG["models"]["router"]
    settings.GPT_STANDARD = _ORIG["models"]["standard"]
    settings.GPT_PRO = _ORIG["models"]["pro"]
    settings.GPT_JUDGE = _ORIG["models"]["judge"]
    settings.EFFORT_ROUTER = _ORIG["efforts"]["router"]
    settings.EFFORT_STANDARD = _ORIG["efforts"]["standard"]
    settings.EFFORT_PRO = _ORIG["efforts"]["pro"]
    settings.EFFORT_JUDGE = _ORIG["efforts"]["judge"]
    for k, v in _ORIG["prompts"].items():
        _set_prompt(k, v)
    settings.RUNTIME_API_KEY = None

    cfg = cfg or {}
    key = (cfg.get("api_key") or "").strip()
    settings.RUNTIME_API_KEY = key or None
    m = cfg.get("models") or {}
    if m.get("router"): settings.GPT_ROUTER = m["router"]
    if m.get("standard"): settings.GPT_STANDARD = m["standard"]
    if m.get("pro"): settings.GPT_PRO = m["pro"]
    if m.get("judge"): settings.GPT_JUDGE = m["judge"]
    e = cfg.get("efforts") or {}
    if "router" in e: settings.EFFORT_ROUTER = _norm_effort(e["router"])
    if "standard" in e: settings.EFFORT_STANDARD = _norm_effort(e["standard"])
    if "pro" in e: settings.EFFORT_PRO = _norm_effort(e["pro"])
    if "judge" in e: settings.EFFORT_JUDGE = _norm_effort(e["judge"])
    for k, v in (cfg.get("prompts") or {}).items():
        if k in PROMPT_REGISTRY and isinstance(v, str) and v.strip():
            _set_prompt(k, v)
