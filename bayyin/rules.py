"""
قواعد الإجراء بالكود (Rules-as-Code).
هذه الوحدة هي "القاضي الإجرائي" — حتمية، قابلة للتدقيق، وخالية من أي نموذج لغوي.
النموذج اللغوي يولّد المحتوى؛ أما تسلسل الإجراء والمواعيد وقابلية الاعتراض
فتُحسم هنا بكود يمكن اختباره والاحتجاج به.

لا تستورد هذه الوحدة LangGraph ولا OpenAI عمداً، لتظل قابلة للاختبار بمعزل.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import settings
from .state import CaseState, Document, DocType, Ruling

# العناصر الشكلية الواجب توافرها في صحيفة الدعوى (نظام المرافعات / المحاكم التجارية).
REQUIRED_CLAIM_FIELDS: dict[str, str] = {
    "claim_subject": "موضوع الدعوى",
    "claim_value": "قيمة المطالبة",
    "parties": "بيانات أطراف الدعوى",
}


@dataclass
class ValidationResult:
    ok: bool
    issues: list[str]


# ---------- الاختصاص النوعي: محكمةٌ تجارية فقط ----------
# علاماتٌ مميِّزة لمنازعاتٍ تخرج عن الاختصاص النوعي للمحكمة التجارية (تُحال لجهتها).
_NONCOMMERCIAL_MARKERS: dict[str, tuple[str, ...]] = {
    "عمالية (محكمة عمالية)": ("فصل تعسفي", "مكافأة نهاية الخدمة", "مستحقات عمالية",
                              "أجور متأخرة", "نظام العمل", "إصابة عمل"),
    "أحوال شخصية (محكمة الأحوال)": ("طلاق", "حضانة", "نفقة", "خلع", "نسب", "ميراث", "وصية", "عضل"),
    "جزائية (محكمة جزائية)": ("جناية", "جنحة", "قصاص", "حدّ السرقة", "مخدرات", "عقوبة سجن"),
}
_COMMERCIAL_TYPES = {"تجاري", "تجارية", "", "أخرى"}


def commercial_jurisdiction(state: CaseState) -> tuple[bool, str]:
    """مصفاةٌ نوعيةٌ أوليّةٌ لفظية فقط (التخصّص: تجاري فقط) — لا تكييفَ موضوعيّاً للمادة 16
    هنا ولا بتّاً نهائياً في الاختصاص عند القيد. محافِظةٌ (شاملةٌ زائدة): لا تردّ إلا بنوعٍ
    غير تجاريٍّ صريح أو علامةٍ لفظيةٍ قاطعة (عمالية/أحوال/جزائية). التكييف الموضوعي العميق
    للاختصاص النوعي محالٌ إلى الدفع القاطع بعدم الاختصاص داخل الخصومة
    (procedure.adjudicate_incident)؛ وملاحظةُ المُسجِّل (RAG) استئناسيةٌ تُدوَّن فقط ولا تردّ.
    تُرجع (مختصّة، سبب عدم الاختصاص إن وُجد)."""
    if not settings.COMMERCIAL_ONLY:
        return True, ""
    ct = (state.get("case_type") or "").strip()
    if ct not in _COMMERCIAL_TYPES:
        return False, (f"عدم الاختصاص النوعي: المنازعة من نوع «{ct}»، ولا تختصّ بها "
                       f"المحكمة التجارية؛ الاختصاص لجهته المختصّة — وتُحال إليها.")
    text = state.get("claim_subject", "") + " " + _all_pleadings_text(state)
    for jurisdiction, markers in _NONCOMMERCIAL_MARKERS.items():
        if any(m in text for m in markers):
            return False, (f"عدم الاختصاص النوعي: المنازعة تبدو {jurisdiction}؛ لا تختصّ بها "
                           f"المحكمة التجارية، وتُحال إلى جهتها المختصّة.")
    return True, ""


def validate_claim_sheet(state: CaseState) -> ValidationResult:
    """
    تدقيق شكلي لصحيفة الدعوى: حضور العناصر الجوهرية ووجود مدعٍ ومدعى عليه.
    (التدقيق الموضوعي العميق يضيفه وكيل المُسجِّل عبر RAG؛ هذا الأساس الحتمي.)
    """
    issues: list[str] = []

    for field, label in REQUIRED_CLAIM_FIELDS.items():
        value = state.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            issues.append(f"عنصر ناقص: {label}")

    value = state.get("claim_value")
    if isinstance(value, (int, float)) and value <= 0:
        issues.append("قيمة المطالبة يجب أن تكون أكبر من صفر.")

    parties = state.get("parties") or []
    roles = {p.role for p in parties}
    if "مدعي" not in roles:
        issues.append("لا يوجد طرف بصفة «مدعي».")
    if "مدعى عليه" not in roles:
        issues.append("لا يوجد طرف بصفة «مدعى عليه».")

    # وجود صحيفة الدعوى فعلياً في السجل
    if not _find_doc(state, DocType.CLAIM_SHEET):
        issues.append("لم تُقدَّم صحيفة الدعوى في سجل المستندات.")

    return ValidationResult(ok=not issues, issues=issues)


def mediation_required(state: CaseState) -> tuple[bool, str]:
    """هل يجب عرض النزاع على المصالحة/الوساطة قبل القيد؟ (م.8 محاكم تجارية + لائحته م.58)
    نطاقٌ تمثيلي: الدعاوى التي لا تزيد على مليون ريال، أو عقدٌ تضمّن اتفاق تسويةٍ ودّية."""
    value = state.get("claim_value", 0) or 0
    if value <= settings.MEDIATION_MAX_SAR:
        return True, "دعوى لا تزيد قيمتها على مليون ريال — المصالحة قبل القيد وجوبية."
    text = _all_pleadings_text(state)
    # الصيغتان بأل التعريف وبدونها (درسٌ عربيٌّ متكرّر: «التسوية الودية» ≠ «تسوية ودية»).
    if any(k in text for k in ("تسوية ودية", "التسوية الودية", "تسوية ودّية", "التسوية الودّية",
                               "فضّ النزاع ودياً", "فض النزاع وديا", "الصلح قبل القضاء", "صلح قبل القضاء")):
        return True, "العقد تضمّن اتفاقاً على التسوية الودّية قبل القضاء — تجب المصالحة أولاً."
    return False, ""


def first_instance_composition(state: CaseState) -> str:
    """تشكيل الدائرة الابتدائية: قاضٍ فردٌ فيما لا يزيد على مليون ريال، وإلا دائرةٌ ثلاثية."""
    value = state.get("claim_value", 0) or 0
    return ("قاضٍ فرد" if value <= settings.SINGLE_JUDGE_MAX_SAR
            else "دائرة ابتدائية ثلاثية")


def appeal_window_days(state: CaseState) -> int:
    """مهلة الاعتراض: 30 يوماً، و10 أيامٍ للمستعجلة والأحكام الصادرة في الاختصاص."""
    disp = state.get("incident_disposition") or {}
    if disp.get("key") == "jurisdiction":
        return settings.APPEAL_WINDOW_DAYS_URGENT
    return settings.APPEAL_WINDOW_DAYS


def pleadings_saturated(state: CaseState) -> bool:
    """
    هل بلغ تبادل المذكرات حالة التشبّع؟
    يخرج من الحلقة عند بلوغ سقف الجولات (حارس حتمي ضد اللانهاية)
    أو عند إعلان المدعي عدم وجود إضافة.
    """
    if state.get("pleading_rounds", 0) >= settings.MAX_PLEADING_ROUNDS:
        return True
    return bool(state.get("no_new_additions"))


# كلمات مفتاحية لاستنتاج الحاجة لخبير وتخصصه (M2).
EXPERT_TRIGGERS: dict[str, tuple[str, ...]] = {
    "محاسبي": ("حساب", "كمية", "فاتورة", "جرد", "مديونية"),
    "فني": ("مواصفات", "عيب", "جودة", "مطابقة"),
    "تقني": ("برمج", "بيانات", "إلكترون", "منصة"),
}


def needs_expert(state: CaseState) -> bool:
    """هل تستدعي وقائع الدعوى ندب خبير؟ (يُندب مرة واحدة فقط)."""
    if state.get("expert_done"):
        return False
    text = (state.get("claim_subject", "") + " " + _all_pleadings_text(state))
    return any(any(k in text for k in kws) for kws in EXPERT_TRIGGERS.values())


def expert_specialty_for(state: CaseState) -> str:
    text = state.get("claim_subject", "") + " " + _all_pleadings_text(state)
    for specialty, kws in EXPERT_TRIGGERS.items():
        if any(k in text for k in kws):
            return specialty
    return "فني"


# ---------- قابلية المرحلة الثانية ----------
def can_appeal(state: CaseState) -> bool:
    j = state.get("judgment")
    return bool(j and j.appealable and state.get("appeal_requested"))


def can_reconsider(state: CaseState) -> bool:
    """التماس متاح فقط إذا طُلب وكان سببه من الأسباب السبعة الحصرية (م.200)."""
    if not state.get("reconsideration_requested"):
        return False
    return reconsideration_ground_valid(state.get("reconsideration_ground", ""))


def panel_consensus(votes: list[str]) -> str:
    """إجماع/أغلبية دائرة الاستئناف: تأييد/إلغاء/تعديل (التعادل لصالح التأييد)."""
    from collections import Counter
    if not votes:
        return "تأييد"
    counts = Counter(votes)
    top = max(counts.items(), key=lambda kv: (kv[1], kv[0] == "تأييد"))
    return top[0]


def _all_pleadings_text(state: CaseState) -> str:
    return " ".join(d.body for d in state.get("document_ledger", []) or [])


def determine_appealability(state: CaseState) -> Ruling:
    """
    يحدّد طريق الاعتراض على الحكم الابتدائي — قاعدة بحتة لا نموذج.
    - إن كانت قيمة الدعوى دون حدّ القطعية → الحكم نهائي، والطريق التماس إعادة النظر حصراً.
    - وإلا → قابل للاستئناف خلال المهلة النظامية.
    يُرجع نسخة من الحكم محدَّثة الحقول appealable / appeal_route.
    """
    judgment = state.get("judgment")
    if judgment is None:
        raise ValueError("لا يوجد حكم لتحديد قابليته للاعتراض.")

    value = state.get("claim_value", 0) or 0
    # قرار المجلس الأعلى للقضاء: «لا تزيد عن 50 ألف» ⇒ 50,000 فأقل = نهائي (≤).
    below_threshold = value <= settings.SUMMARY_COURT_FINALITY_SAR

    if below_threshold:
        appealable = False
        route = "التماس إعادة النظر"  # نهائي ابتدائياً (دعوى يسيرة)
    else:
        appealable = True
        route = "استئناف"

    return judgment.model_copy(update={"appealable": appealable, "appeal_route": route})


# الأسباب السبعة الحصرية للمادة 200 (التماس إعادة النظر) — للمرحلة الثانية لاحقاً.
ARTICLE_200_GROUNDS: dict[str, str] = {
    "forgery": "وثائق ثبت تزويرها أو شهادة قُضي بأنها زور",
    "withheld_docs": "أوراق قاطعة احتجزها الخصم أو استحال تقديمها",
    "fraud": "غش من الخصم أثّر في الحكم",
    "ultra_petita": "حكم بما لم يُطلب أو بأكثر مما طُلب",
    "contradiction": "تناقض في منطوق الحكم",
    "in_absentia": "حكم غيابي",
    "defective_representation": "تمثيل ناقص لأحد الأطراف",
}


def reconsideration_ground_valid(ground_key: str) -> bool:
    """التحقّق من أن سبب الالتماس من الأسباب السبعة الحصرية للمادة 200."""
    return ground_key in ARTICLE_200_GROUNDS


def _find_doc(state: CaseState, doc_type: DocType) -> Document | None:
    for doc in state.get("document_ledger", []) or []:
        if doc.doc_type == doc_type:
            return doc
    return None
