"""
طبقة المصادر النظامية السعودية — «القانون كبيانات موثّقة».
المبدأ: النموذج لا يقرّر ما هو الحكم النظامي؛ بل يُسترجَع من هنا ويُتحقَّق منه.
كل استشهادٍ صادرٍ عن أي عملية استدلالية يُعرَض على verify_cite، فلا يَعبُر
ما لا يُسنَد إلى مصدرٍ معروفٍ في هذه الطبقة.

تدرّج المصادر في القضاء السعودي: الشريعة ← النظام ← اللائحة ← التعاميم/المبادئ القضائية.

تنبيه جوهري (تنبيه المطوّر): هذه الطبقة مصدر الحقيقة، والمعوّل عليه تحميلها
من النصوص الرسمية (هيئة الخبراء/وزارة العدل/أم القرى). البذور أدناه نواةٌ
سعوديةٌ موثّقة جزئياً؛ ما لم يُحمَّل بعد يُعلَّم «غير مؤصَّل» لا «مختلق».
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class Rank(str, Enum):
    SHARIA = "الشريعة"
    NIZAM = "نظام"
    LAIHA = "لائحة"
    PRINCIPLE = "تعميم/مبدأ قضائي"


# الأنظمة السعودية المعروفة (ما عداها يُعدّ مصدراً مجهولاً = مؤشّر اختلاق).
KNOWN_SYSTEMS: dict[str, Rank] = {
    "الشريعة الإسلامية": Rank.SHARIA,
    "نظام المرافعات الشرعية": Rank.NIZAM,
    "نظام المحاكم التجارية": Rank.NIZAM,
    "نظام الإثبات": Rank.NIZAM,
    "نظام المعاملات المدنية": Rank.NIZAM,
    "نظام العمل": Rank.NIZAM,
    "نظام التنفيذ": Rank.NIZAM,
    "اللائحة التنفيذية لنظام المرافعات الشرعية": Rank.LAIHA,
    "قرارات المجلس الأعلى للقضاء": Rank.PRINCIPLE,
}


class Cite(BaseModel):
    """إسنادٌ صادرٌ عن عمليةٍ استدلالية: نظامٌ + رقم مادة/مرجع + اقتباس."""
    system: str
    article: str = ""
    quote: str = ""
    claim: str = ""   # القول القانوني الذي يدعمه الإسناد


@dataclass(frozen=True)
class Article:
    system: str
    number: str
    title: str
    text: str
    verified: bool          # True فقط إذا ثُبّت من نصٍّ رسمي
    provenance: str
    effective: str = ""


def _a(system, number, title, text, verified, provenance, effective=""):
    return Article(system, number, title, text, verified, provenance, effective)


# ---------------------------------------------------------------------------
# نواة المصادر السعودية (مفتاح = (النظام، رقم المادة))
# ---------------------------------------------------------------------------
_SEED: list[Article] = [
    _a("نظام الإثبات", "1", "عبء الإثبات",
       "على المدّعي إثبات ما يدّعيه، وللمدّعى عليه نفيه (البيّنة على من ادّعى، واليمين على من أنكر).",
       True, "مبدأ أصيل في نظام الإثبات والفقه؛ يُثبَّت رقم المادة من النص الرسمي."),
    _a("نظام الإثبات", "حجية المحرر", "حجية المحرر العادي",
       "المحرّر العادي حجّةٌ على من وقّعه ما لم يُنكِر صراحةً ما نُسب إليه من خطٍّ أو إمضاءٍ أو ختمٍ أو بصمة.",
       True, "مبدأ ثابت في نظام الإثبات؛ يُثبَّت رقم المادة من النص الرسمي."),
    _a("نظام المرافعات الشرعية", "187", "مهلة الاعتراض بالاستئناف",
       "مدة الاعتراض بالاستئناف ثلاثون يوماً تبدأ من اليوم التالي لتسلّم صورة صك الحكم أو لليوم المحدد لتسلّمها، وعشرة أيام في المستعجلة.",
       True, "تأكيد ويب (يونيو 2026) — المادة 187 بالترقيم الحالي.", "—"),
    _a("نظام المرافعات الشرعية", "200", "أسباب التماس إعادة النظر",
       "يجوز الالتماس لسبعة أسبابٍ حصرية: التزوير، أوراق قاطعة احتُجزت، الغش، الحكم بما لم يُطلب أو بأكثر منه، تناقض المنطوق، الحكم الغيابي، التمثيل الناقص.",
       True, "تحقّق سابق — نسخة 2021."),
    _a("نظام المحاكم التجارية", "16", "الاختصاص النوعي",
       "تختص المحكمة التجارية بالمنازعات التي تنشأ بين التجار بسبب أعمالهم التجارية الأصلية أو التبعية.",
       False, "مبدأ معروف؛ يُثبَّت رقم المادة ونصّها من النظام ولائحته."),
    _a("نظام المعاملات المدنية", "العقد", "وجوب الوفاء بالعقد",
       "العقد شريعة المتعاقدين، فيجب الوفاء بما اشتمل عليه وفق ما تقتضيه أحكامه وحسن النية.",
       False, "مبدأ في نظام المعاملات المدنية (نافذ 1445هـ)؛ يُثبَّت رقم المادة من النص الرسمي."),
    _a("نظام المعاملات المدنية", "التقادم", "تقادم الالتزام (سقوط سماع الدعوى)",
       "لا تُسمع دعوى الالتزام بعد مُضيّ المدة النظامية من وقت استحقاقه ما لم يُقرّ المدين أو يوجد عذرٌ يقطع التقادم.",
       False, "مبدأ التقادم في نظام المعاملات المدنية؛ تُثبَّت المادة والمدة من النص الرسمي."),
    _a("نظام المرافعات الشرعية", "شروط الدعوى", "شروط قبول الدعوى (الصفة والمصلحة)",
       "يُشترط لقبول الدعوى توافر الصفة والمصلحة القائمة المشروعة؛ فإن انتفت إحداهما حُكم بعدم قبول الدعوى.",
       False, "مبدأ اشتراط الصفة والمصلحة لقبول الدعوى؛ يُثبَّت رقم المادة من النظام."),
    _a("نظام المرافعات الشرعية", "الطلبات العارضة", "الطلبات العارضة",
       "للخصم تقديم طلباتٍ عارضةٍ مرتبطةٍ بالدعوى الأصلية، فتُنظر معها ويُفصل فيها بحكمٍ واحد.",
       False, "مبدأ الطلبات العارضة؛ يُثبَّت رقم المادة من النظام."),
    _a("قرارات المجلس الأعلى للقضاء", "41/19/2", "حدّ الدعاوى اليسيرة (قطعية الأحكام)",
       "الدعاوى — أياً كان نوعها — التي لا تزيد قيمة المطالبة الأصلية فيها عن خمسين ألف ريال (بما فيها منازعات التنفيذ) تُعدّ يسيرة لا تقبل الاعتراض بالاستئناف تدقيقاً ومرافعةً.",
       True, "تأكيد ويب (تعميم 1544/ت ~1441هـ) — يثبَّت الرقم/التاريخ الدقيق.", "للأحكام الصادرة بعد 01-03-1442هـ"),
]

STORE: dict[tuple[str, str], Article] = {(a.system, a.number): a for a in _SEED}


# ---------------------------------------------------------------------------
# واجهة الاستعلام والتحقّق
# ---------------------------------------------------------------------------
def get(system: str, number: str) -> Article | None:
    return STORE.get((system, number))


def search(keyword: str) -> list[Article]:
    """استرجاع لفظي بسيط على النواة المُحمَّلة (يُكمَّل بـ file_search في الوضع الحقيقي)."""
    k = keyword.strip()
    return [a for a in STORE.values() if k and (k in a.text or k in a.title or k in a.system)]


class CiteStatus(str, Enum):
    VERIFIED = "مؤصَّل"          # موجود في طبقة المصادر الموثّقة
    SHARIA = "اجتهاد شرعي"       # استناد للشريعة عند غياب النص (مؤصَّل لكنه يرفع عدم اليقين)
    UNLOADED = "غير مُحمَّل"      # نظامٌ معروفٌ لكن المادة ليست في النواة بعد (فجوة تشغيلية لا اختلاق)
    FABRICATED = "مختلق"         # مصدرٌ مجهولٌ أو مرجعٌ غير ممكن


def verify_cite(c: Cite) -> tuple[CiteStatus, str]:
    """
    حجر الزاوية: يصنّف كل إسناد. لا يُعدّ القول مُؤصَّلاً إلا VERIFIED/SHARIA.
    FABRICATED يُسقِط الحكم (بوابة صفر-اختلاق).
    """
    if c.system not in KNOWN_SYSTEMS:
        return CiteStatus.FABRICATED, f"مصدرٌ غير معروف: «{c.system}»."
    if KNOWN_SYSTEMS[c.system] == Rank.SHARIA:
        if not (c.quote.strip() or c.claim.strip()):
            return CiteStatus.UNLOADED, "استنادٌ للشريعة بلا مبدأٍ أو دليلٍ محدّد — لا يُعتدّ به تأصيلاً."
        return CiteStatus.SHARIA, "استنادٌ للشريعة (مسألةٌ قد لا نصّ نظاميٌّ فيها)."
    art = get(c.system, c.article)
    if art is None:
        return CiteStatus.UNLOADED, f"«{c.system}» معروف، لكن المادة «{c.article}» ليست في النواة المُحمَّلة بعد."
    # تحقّق اقتباسٍ متساهل: إن وُجد اقتباس ولم يتقاطع مطلقاً مع نصّ المادة → اشتباه تحريف.
    if c.quote and art.text and not _loose_overlap(c.quote, art.text):
        return CiteStatus.UNLOADED, "الاقتباس لا يتطابق مع نصّ المادة المؤصَّل — يُراجَع."
    return CiteStatus.VERIFIED, art.title


import re

_DIAC = re.compile(r"[ً-ْـ]")     # تشكيل + تطويل
_SPLIT = re.compile(r"[\s،.؛:()«»\"'\-—]+")


def _norm(s: str) -> str:
    s = _DIAC.sub("", s)
    s = s.translate(str.maketrans("أإآىؤئ", "ااايوي")).replace("ة", "ه").replace("ء", "")
    return s


def _tokens(s: str) -> set[str]:
    return {w for w in _SPLIT.split(_norm(s)) if len(w) > 3}


def _loose_overlap(quote: str, text: str) -> bool:
    """مطابقة اقتباسٍ بتطبيعٍ عربيّ (تشكيل/همزات/ترقيم) — مهمّة للتأصيل الحقيقي."""
    qs, ts = _tokens(quote), _tokens(text)
    if not qs:
        return True
    return len(qs & ts) / len(qs) >= 0.25


def assess_grounding(cites: list[Cite]) -> dict:
    """
    تقرير تأصيلٍ للحكم: يلزم ≥1 إسنادٍ VERIFIED وصفر FABRICATED.
    يرفع عدم اليقين عند الاستناد للشريعة (غياب النص) أو وجود غير مُحمَّل.
    """
    counts = {s: 0 for s in CiteStatus}
    issues: list[str] = []
    for c in cites:
        st, why = verify_cite(c)
        counts[st] += 1
        if st in (CiteStatus.FABRICATED,):
            issues.append(f"⛔ {why}")
        elif st == CiteStatus.UNLOADED:
            issues.append(f"⚠️ {why}")
    ok = counts[CiteStatus.FABRICATED] == 0 and (counts[CiteStatus.VERIFIED] + counts[CiteStatus.SHARIA]) >= 1
    uncertainty = []
    if counts[CiteStatus.SHARIA]:
        uncertainty.append("مسألةٌ تستند للاجتهاد الشرعي عند غياب النص — أعلى خطراً، تتطلّب تحقّق المحامي.")
    if counts[CiteStatus.UNLOADED]:
        uncertainty.append("بعض الإسنادات لأنظمةٍ معروفةٍ لكنها خارج النواة المُحمَّلة — تُؤصَّل من النص الرسمي.")
    return {
        "ok": ok,
        "verified": counts[CiteStatus.VERIFIED],
        "sharia": counts[CiteStatus.SHARIA],
        "unloaded": counts[CiteStatus.UNLOADED],
        "fabricated": counts[CiteStatus.FABRICATED],
        "issues": issues,
        "uncertainty": uncertainty,
    }
