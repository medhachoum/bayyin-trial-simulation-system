"""
المحرّك الزمني — يمنح المحاكاة «وعياً زمنياً»: تواريخ تقديرية (ميلادية/هجرية)
لكل إجراء، ومواعيد نظامية محسوبة (مهلة الاستئناف...). تقديريٌّ لا قطعي.
يُثبَّت على «تاريخ القيد» المُدخَل، فالنتائج حتمية وقابلة لإعادة التشغيل.
"""
from __future__ import annotations

from datetime import date, timedelta

try:
    from hijridate import Gregorian
    _HIJRI = True
except Exception:  # pragma: no cover
    _HIJRI = False

HIJRI_MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
                "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]

# أيام تقديرية تفصل كل إجراءٍ عمّا قبله (مسار تجاري سعودي نموذجي عبر ناجز).
DURATIONS: dict[str, int] = {
    "router": 0, "intake_register": 0, "rejected": 0, "referred": 0, "research": 0,
    "notify_defendant": 7, "defendant_plea": 14, "plaintiff_plea": 10,
    "hearing_manager": 3, "expert": 30, "close_pleadings": 7,
    "judgment": 21, "serve_judgment": 7,
    "appeal_brief": 20, "appellee_response": 15, "appeal_hearing": 30,
    "appellate_panel": 21, "reconsideration": 20,
}
APPEAL_WINDOW_DAYS = 30
RECONSIDERATION_WINDOW_DAYS = 30


def _hijri(g: date) -> str:
    if not _HIJRI:
        return ""
    try:
        h = Gregorian(g.year, g.month, g.day).to_hijri()
        return f"{h.day} {HIJRI_MONTHS[h.month - 1]} {h.year}هـ"
    except Exception:
        return ""


def fmt(g: date) -> dict:
    return {"greg": g.isoformat(), "hijri": _hijri(g)}


def parse(iso: str) -> date:
    try:
        return date.fromisoformat(iso)
    except Exception:
        return date(2026, 1, 15)


def advance(clock_iso: str, node: str) -> tuple[str, dict]:
    """يقدّم الساعة بمدّة الإجراء التقديرية ويُرجع (التاريخ الجديد، وصفه)."""
    g = parse(clock_iso) + timedelta(days=DURATIONS.get(node, 5))
    return g.isoformat(), fmt(g)


def add_days(clock_iso: str, days: int) -> dict:
    return fmt(parse(clock_iso) + timedelta(days=days))
