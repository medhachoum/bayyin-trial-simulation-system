"""
مخطّط حالة الدعوى (CaseState) والكائنات القانونية.
Typed case state + domain objects for the Bayyin court simulation.

CaseState هو TypedDict تقرؤه LangGraph؛ القوائم المُعلَّمة بـ operator.add
تتراكم عبر العُقَد (ledger, audit_log)، وبقية الحقول يستبدلها آخر تحديث.
الكائنات الغنية (Document, Ruling…) نماذج Pydantic للتحقّق والتوثيق.
"""
from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Optional, TypedDict

from pydantic import BaseModel, Field


class CaseType(str, Enum):
    COMMERCIAL = "تجاري"
    CIVIL = "حقوقي"
    LABOR = "عمالي"
    OTHER = "أخرى"


class Phase(str, Enum):
    FIRST_INSTANCE = "المرحلة الابتدائية"
    APPEAL = "الاستئناف"
    RECONSIDERATION = "التماس إعادة النظر"
    FINAL = "نهائي"


class DocType(str, Enum):
    CLAIM_SHEET = "صحيفة دعوى"
    DEFENSE_MEMO = "مذكرة جوابية"
    PLAINTIFF_REPLY = "رد المدعي"
    EXPERT_REPORT = "تقرير خبير"
    JUDGMENT = "صك حكم"
    APPEAL_BRIEF = "صحيفة اعتراض (استئناف)"
    APPEAL_RESPONSE = "مذكرة جوابية على الاستئناف"
    RECONSIDERATION = "التماس إعادة النظر"


class Complexity(str, Enum):
    STANDARD = "عادية"
    COMPLEX = "شائكة"


class Party(BaseModel):
    role: str  # "مدعي" أو "مدعى عليه"
    name: str
    is_human: bool = False  # هل يلعب هذا الدور محامٍ بشري؟


class Citation(BaseModel):
    """إسناد واحد: ادّعاء قانوني مربوط بمصدر مُسترجَع."""
    claim: str           # الجملة/الحكم القانوني
    source_tool: str     # أي أداة file_search (search_saudi_codes ...)
    source_ref: str      # معرّف/عنوان المقطع المسترجَع
    quote: str = ""      # اقتباس داعم من المصدر
    status: str = ""     # وسم التحقّق: مؤصَّل / غير مُحمَّل / مختلق (للعرض التدريبي)
    status_reason: str = ""


class Document(BaseModel):
    doc_type: DocType
    author_role: str
    title: str
    body: str
    citations: list[Citation] = Field(default_factory=list)
    hearing_no: Optional[int] = None
    event: str = ""      # وسم منطقي للزمن
    flag: str = ""       # وسم داخلي خفي (مثل "forged" في وضع التدريب) — لا يُعرض للمحامي
    key: str = ""        # مفتاح ثابت للتجاوز (يُحرّره المستخدم ويُعاد التشغيل)
    overridden: bool = False  # هل هذا النص من المستخدم بدل النموذج؟


class Ruling(BaseModel):
    """صك الحكم: الوقائع، الأسباب (التسبيب)، المنطوق — نتاج محرّك الاستدلال."""
    facts: str           # الوقائع
    reasons: str         # الأسباب / التسبيب
    operative: str       # المنطوق
    composition: str = ""  # تشكيل الدائرة المُصدِرة (قاضٍ فرد / دائرة ثلاثية) — لبيانات الصك
    citations: list[Citation] = Field(default_factory=list)
    appealable: Optional[bool] = None
    appeal_route: str = ""   # "استئناف" / "التماس إعادة النظر" / "نهائي"
    confidence: str = ""     # ثقة المحرّك: عالية/متوسطة/منخفضة/محجوب
    direction: str = ""      # اتجاه المنطوق: للمدعي/للمدعى عليه/رفض الدعوى/جزئي
    blocked: bool = False    # حُجِب النطق لمخالفةٍ جوهرية (اختلاق/تجاوز/تناقض)
    flags: list[str] = Field(default_factory=list)  # تحذيرات التأصيل وعدم اليقين


def _replace_last(_old, new):
    """مُختزِل بسيط: يأخذ آخر قيمة (للحقول التي لا تتراكم)."""
    return new


class CaseState(TypedDict, total=False):
    # تعريف الدعوى
    case_id: str
    case_type: str
    claim_subject: str
    claim_value: float
    parties: list[Party]
    complexity: str

    # المسار الإجرائي
    current_phase: str
    hearing_no: int
    pleading_rounds: int
    pleadings_closed: bool

    # حلقة المرافعة والخبير (M2)
    no_new_additions: bool      # هل أعلن المدعي عدم وجود إضافة؟
    expert_done: bool
    expert_specialty: str

    # الإجراء المتولّد من الحقوق — الدفوع الشكلية
    incidents_done: bool
    incidents: list[dict]            # ما فُصل فيه من دفوع
    incident_disposition: dict       # دفعٌ قاطعٌ مقبولٌ يُنهي الدعوى

    # المرحلة الثانية — الاستئناف (M3)
    appeal_requested: bool
    appeal_judgment: Optional[Ruling]
    scripted_appeal_brief: str
    panel_votes: list[dict]

    # التماس إعادة النظر + حقن الثغرات (M4)
    reconsideration_requested: bool
    reconsideration_ground: str     # المفتاح الذي يلتمس عليه المحامي
    reconsideration_outcome: str
    inject_exploit: str             # وضع التدريب: ما يُطلب حقنه
    injected_exploit: str           # الحقيقة الخفية: ما حُقن فعلاً
    detected_exploit: str           # ما ادّعى المحامي اكتشافه

    # المستندات والحكم (تتراكم في السجل)
    document_ledger: Annotated[list[Document], operator.add]
    judgment: Optional[Ruling]
    adjudication: dict        # سلسلة العمليات الاستدلالية السبع وتقرير التأصيل

    # المواعيد النظامية {اسم_الحدث: وصف}
    deadlines: dict

    # القيد والتحقّق
    intake_ok: bool
    intake_issues: list[str]
    intake_referred: bool        # عدم اختصاصٍ نوعي (تجاري فقط) → إحالة لا ردّ
    referral_reason: str
    referral_decision: str

    # البحث القضائي التجاري (مبادئ + سوابق مُسترجَعة لتوجيه المحاكاة)
    research: dict

    # التفاعل البشري (المدعي) — للعرض غير التفاعلي نزوّد ردوداً مكتوبة مسبقاً
    scripted_plaintiff_replies: list[str]

    # التحرير وإعادة الإطلاق: نصوصٌ من المستخدم تستبدل نصوص النموذج (key → text)
    overrides: dict
    filing_date: str          # تاريخ قيد الدعوى (مرساة المحرّك الزمني)
    obligation_due_date: str  # تاريخ استحقاق الالتزام (لحساب التقادم حساباً لا تخميناً)
    appeal_window_days: int   # مهلة الاعتراض الفعلية (30، و10 للمستعجل/أحكام الاختصاص)
    mediation_done: bool      # جرت المصالحة/الوساطة قبل القيد (وجوبية لطيفٍ من الدعاوى)

    # سجل التدقيق (يتراكم) — كل خطوة: من فعل ماذا وبأي نموذج ومصادر
    audit_log: Annotated[list[dict], operator.add]
