"""
محرّك الاستدلال القضائي السعودي — العمليات السبع.
كل عملية = توليدٌ مُقيَّد (الاستدلال) + مُتحقِّقٌ حتميٌّ سعودي (الصحة والإسناد).
النموذج لا يقرّر مضمون القاعدة؛ يطبّقها، ويُتحقَّق من إسناده عبر طبقة sources.

التسلسل: التحرير ← التكييف ← تحديد محل النزاع ← الإثبات ← التطبيق ← التسبيب والمنطوق ← المراجعة.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import settings, sources
from .llm import get_llm
from .sources import Cite
from .tools import tools_for


@dataclass
class Verdict:
    ok: bool
    issues: list[str]
    confidence: str   # عالية / متوسطة / منخفضة


@dataclass
class OpResult:
    key: str
    label: str
    data: dict
    cites: list[Cite]
    verdict: Verdict
    # نصوص المقاطع المُسترجَعة فعلاً في هذه العملية: None = لا استرجاعَ في النداء.
    evidence: list[str] | None = None


_CITE = {
    "type": "object",
    "properties": {"system": {"type": "string"}, "article": {"type": "string"},
                   "quote": {"type": "string"}, "claim": {"type": "string"}},
    "required": ["system", "article", "quote", "claim"], "additionalProperties": False,
}
_AMT = {
    "type": "object",
    "properties": {"type": {"type": "string"}, "amount": {"type": "number"}},
    "required": ["type", "amount"], "additionalProperties": False,
}


def _schema(title, props, required):
    return {"title": title, "type": "object", "properties": props,
            "required": required, "additionalProperties": False}


# مخططات العمليات
S_TAHRIR = _schema("tahrir", {
    "requests": {"type": "array", "items": _AMT}, "summary": {"type": "string"}}, ["requests", "summary"])
S_TAKYIF = _schema("takyif", {
    "nature": {"type": "string"}, "governing_system": {"type": "string"},
    "cite": _CITE, "summary": {"type": "string"}}, ["nature", "governing_system", "cite", "summary"])
S_MAHAL = _schema("mahal", {
    "agreed": {"type": "array", "items": {"type": "string"}},
    "contested": {"type": "array", "items": {"type": "string"}},
    "defenses": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"}}, ["agreed", "contested", "defenses", "summary"])
S_ITHBAT = _schema("ithbat", {
    "findings": {"type": "array", "items": _schema("f", {
        "point": {"type": "string"}, "burden_on": {"type": "string"},
        "established": {"type": "boolean"}, "basis": _CITE}, ["point", "burden_on", "established", "basis"])},
    "summary": {"type": "string"}}, ["findings", "summary"])
S_TATBIQ = _schema("tatbiq", {
    "rule": _CITE, "conclusion": {"type": "string"}, "summary": {"type": "string"}}, ["rule", "conclusion", "summary"])
S_TASBIB = _schema("tasbib", {
    "reasons": {"type": "string"}, "operative": {"type": "string"},
    "direction": {"type": "string", "enum": ["للمدعي", "للمدعى عليه", "رفض الدعوى", "جزئي"]},
    "granted": {"type": "array", "items": _AMT},
    "addressed_defenses": {"type": "array", "items": {"type": "string"}},
    "cites": {"type": "array", "items": _CITE}},
    ["reasons", "operative", "direction", "granted", "addressed_defenses", "cites"])
S_MURAJA = _schema("muraja", {
    "sound": {"type": "boolean"}, "issues_found": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"}}, ["sound", "issues_found", "summary"])


# مطالبات العمليات (سعودية)
_P = {
    "tahrir": "أنت قاضٍ سعودي في طور تحرير الدعوى: حدّد طلبات المدعي بدقّة (نوعها وقيمتها)، والصفة والمصلحة.",
    "takyif": "أنت قاضٍ تجاريٌّ سعودي تُكيّف النزاع قانوناً: حدّد طبيعته والنظام الحاكم له، واستشهد بالنظام والمادة، وبالمبادئ القضائية التجارية المُسترجَعة في ملف الدعوى عند مطابقتها. لا تخترع نظاماً أو مادة أو مبدأً.",
    "mahal": "أنت قاضٍ تجاريٌّ سعودي تحدّد محل النزاع: ميّز المتّفق عليه من المتنازَع، وأحصِ دفوع المدعى عليه الجوهرية.",
    "ithbat": "أنت قاضٍ تجاريٌّ سعودي تُعمِل نظام الإثبات: لكل نقطة متنازعة حدّد من عليه عبء الإثبات (البيّنة على من ادّعى) وهل ثبتت، مستنداً لنظام الإثبات.",
    "tatbiq": "أنت قاضٍ تجاريٌّ سعودي تُنزِل الحكم النظامي على الوقائع الثابتة: استشهد بالقاعدة الحاكمة من نظامها ومادتها، وبالمبدأ القضائي التجاري المُسترجَع عند مطابقته (النظام=المبادئ القضائية التجارية، المرجع=رقم/عنوان المبدأ، الاقتباس=نصّه)، ثم استنتج. لا تخترع.",
    "tasbib": "أنت قاضٍ تجاريٌّ سعودي تصوغ التسبيب والمنطوق: اربط الأسباب بالمنطوق، ولا تقضِ بما لم يُطلب ولا بأكثر منه، ولا تترك تناقضاً، وردّ على كل دفعٍ جوهري، واذكر إسناداتك (نظام+مادة، أو مبدأٌ قضائيٌّ تجاريٌّ مُسترجَع باقتباسه). تستأنس بالسوابق دون أن تتقيّد بها.",
    "muraja": "أنت قاضٍ مراجِع (بمنطق الاستئناف): افحص سلامة الحكم — تأصيل الأسباب، عدم تجاوز الطلبات، اتّساق المنطوق، الردّ على الدفوع.",
}
# نماذج العمليات تُحسب ديناميكياً (تتأثّر بإعدادات المستخدم وقت التشغيل).
def _model_for_op(key: str) -> str:
    return settings.GPT_STANDARD if key in ("tahrir", "mahal") else settings.GPT_JUDGE


def _effort_for_op(key: str) -> str | None:
    # عمليات القاضي الجوهرية (تكييف/إثبات/تطبيق/تسبيب) تأخذ جهد القاضي؛ التحرير ومحل النزاع جهدَ القياسي.
    return settings.EFFORT_STANDARD if key in ("tahrir", "mahal") else settings.EFFORT_JUDGE


def _cites(items) -> list[Cite]:
    out = []
    for c in items or []:
        out.append(Cite(system=c.get("system", ""), article=c.get("article", ""),
                        quote=c.get("quote", ""), claim=c.get("claim", "")))
    return out


def _call(key: str, user: str, schema: dict, tools: list | None = None) -> tuple[dict, list[str] | None]:
    res = get_llm().complete(model=_model_for_op(key), system=_P[key], user=user, tools=tools,
                             schema=schema, role=f"op_{key}", effort=_effort_for_op(key))
    # نحفظ دلالة الأدلة: None = لا استرجاعَ في النداء؛ [] = استرجاعٌ لم يُعِد شيئاً.
    return (res.get("data") or {}), res.get("evidence")


def _merge_ev(state, ev: list[str] | None) -> list[str] | None:
    """أدلة العملية + أدلة البحث القضائي (المبدأ الصحيح الوارد في ملف الدعوى يُؤصَّل
    بأدلة البحث ولو لم يُعِد نداءُ العملية استرجاعه). None يبقى None إن غاب الاثنان."""
    r_ev = (state.get("research") or {}).get("evidence")
    if ev is None and r_ev is None:
        return None
    return (ev or []) + (r_ev or [])


def _ctx(state, prior: dict, research: bool = True) -> str:
    from .nodes import _case_file_text  # إعادة استخدام نصّ ملف الدعوى (نسخة القاضي: بلا اتجاه السوابق)
    parts = [_case_file_text(state, for_judge=True, research=research)]
    for k, v in prior.items():
        parts.append(f"[{k}] {v.get('summary', '')}")
    return "\n".join(parts)


# ============================ العمليات ============================
def op_tahrir(state, prior) -> OpResult:
    # التحرير لا يحتاج ملخّص البحث (تقليل الحمولة) — يقرأ الصحيفة والمذكرات فقط.
    d, ev = _call("tahrir", _ctx(state, prior, research=False), S_TAHRIR)
    issues = [] if d.get("requests") else ["لم تتحدّد طلبات الدعوى."]
    return OpResult("tahrir", "التحرير", d, [], Verdict(not issues, issues, "عالية"), ev)


def op_takyif(state, prior) -> OpResult:
    d, ev = _call("takyif", _ctx(state, prior), S_TAKYIF,
                  tools=tools_for("search_saudi_codes", "search_commercial_principles"))
    cites = _cites([d.get("cite")] if d.get("cite") else [])
    issues = []
    for c in cites:
        st, why = sources.verify_cite(c, _merge_ev(state, ev))
        if st == sources.CiteStatus.FABRICATED:
            issues.append(f"تكييفٌ يستند لمصدرٍ مختلق: {why}")
    conf = "عالية" if not issues else "منخفضة"
    return OpResult("takyif", "التكييف", d, cites, Verdict(not issues, issues, conf), ev)


def op_mahal(state, prior) -> OpResult:
    # تحديد محل النزاع يقرأ الصحيفة والمذكرات — لا يحتاج ملخّص البحث.
    d, ev = _call("mahal", _ctx(state, prior, research=False), S_MAHAL)
    return OpResult("mahal", "تحديد محل النزاع", d, [], Verdict(True, [], "عالية"), ev)


def op_ithbat(state, prior) -> OpResult:
    d, ev = _call("ithbat", _ctx(state, prior), S_ITHBAT,
                  tools=tools_for("search_saudi_codes"))
    cites, issues = [], []
    for f in d.get("findings", []):
        c = _cites([f.get("basis")])[0] if f.get("basis") else None
        if c:
            cites.append(c)
            st, why = sources.verify_cite(c, _merge_ev(state, ev))
            if st == sources.CiteStatus.FABRICATED:
                issues.append(f"إثباتٌ بإسنادٍ مختلق: {why}")
    return OpResult("ithbat", "الإثبات", d, cites, Verdict(not issues, issues, "عالية" if not issues else "منخفضة"), ev)


def op_tatbiq(state, prior) -> OpResult:
    d, ev = _call("tatbiq", _ctx(state, prior), S_TATBIQ,
                  tools=tools_for("search_saudi_codes", "search_commercial_principles"))
    cites = _cites([d.get("rule")] if d.get("rule") else [])
    issues = []
    for c in cites:
        st, why = sources.verify_cite(c, _merge_ev(state, ev))
        if st == sources.CiteStatus.FABRICATED:
            issues.append(f"تطبيقُ قاعدةٍ مختلقة: {why}")
    return OpResult("tatbiq", "التطبيق", d, cites, Verdict(not issues, issues, "عالية" if not issues else "منخفضة"), ev)


def op_tasbib(state, prior) -> OpResult:
    d, ev = _call("tasbib", _ctx(state, prior), S_TASBIB,
                  tools=tools_for("search_saudi_codes", "search_commercial_principles"))
    cites = _cites(d.get("cites"))
    requests = (prior.get("tahrir") or {}).get("requests", [])
    defenses = (prior.get("mahal") or {}).get("defenses", [])
    issues: list[str] = []
    # (1) لا يُقضى بما لم يُطلب
    issues += check_non_ultra_petita(requests, d.get("granted", []))
    # (2) عدم تناقض المنطوق (يغطّي الاتجاهات الأربعة والاتجاه المجهول)
    issues += check_mantuq_consistency(d.get("direction", ""), d.get("operative", ""),
                                       d.get("granted", []), requests)
    # (3) الردّ على الدفوع الجوهرية
    issues += check_defenses_addressed(defenses, d.get("addressed_defenses", []))
    conf = "عالية" if not issues else "منخفضة"
    return OpResult("tasbib", "التسبيب والمنطوق", d, cites, Verdict(not issues, issues, conf), ev)


def op_muraja(results: list[OpResult]) -> OpResult:
    issues = [i for r in results for i in r.verdict.issues]
    sound = not issues
    summary = "الحكم سليمٌ استدلالاً وتأصيلاً." if sound else f"رُصدت {len(issues)} ملاحظة تستوجب التصحيح."
    return OpResult("muraja", "المراجعة", {"sound": sound, "issues_found": issues, "summary": summary},
                    [], Verdict(sound, issues, "عالية" if sound else "منخفضة"))


# ===================== المُتحقِّقات الحتمية السعودية =====================
def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# مرادفاتٌ ماليةٌ شائعة لنوع الطلب (بعد التطبيع) — يولّد النموذج النوع نصاً حراً في
# نداءين منفصلين (تحرير ثم تسبيب) فالاختلاف اللفظي واردٌ ولا يصحّ حجبُ حكمٍ صحيحٍ به.
_MONEY_TYPES = {"مبلغ", "المبلغ", "مطالبه ماليه", "المطالبه الماليه", "ثمن", "الثمن",
                "قيمه", "القيمه", "مبالغ", "المطالبه"}


def _match_req_type(t: str, req: dict[str, float]) -> str | None:
    """مطابقة نوعٍ رخوة: حرفية ← تقاطع رموز ← مرادفات مالية."""
    if t in req:
        return t
    tt = sources._tokens(t)
    for k in req:
        if tt and tt & sources._tokens(k):
            return k
    if t in _MONEY_TYPES:
        for k in req:
            if k in _MONEY_TYPES:
                return k
    return None


def check_non_ultra_petita(requests: list[dict], granted: list[dict]) -> list[str]:
    """لا يُقضى بما لم يُطلب ولا بأكثر منه (م.200): مجموعُ الممنوح لكل نوعٍ يُقارَن
    بالمطلوب (لا كل عنصرٍ منفرداً — يصيد التجزئة)، والمطابقة رخوة (لا حجب بالمرادف)."""
    issues: list[str] = []
    req: dict[str, float] = {}
    for r in requests:
        t = sources._norm(r.get("type", ""))
        req[t] = max(req.get(t, 0.0), _num(r.get("amount", 0)))
    total_req = sum(req.values())
    granted_by_type: dict[str, float] = {}
    unmatched: list[tuple[str, float]] = []
    for g in granted:
        t, ga, raw = sources._norm(g.get("type", "")), _num(g.get("amount", 0)), g.get("type", "")
        k = _match_req_type(t, req)
        if k is None:
            unmatched.append((raw, ga))
        else:
            granted_by_type[k] = granted_by_type.get(k, 0.0) + ga
    for k, tot in granted_by_type.items():
        if tot > req[k] + 1e-6:
            issues.append(f"⛔ قضاءٌ بأكثر مما طُلب في «{k}» (مجموع الممنوح {tot:g} > {req[k]:g}).")
    for raw, ga in unmatched:
        if ga > total_req + 1e-6:
            issues.append(f"⛔ قضاءٌ بما لم يُطلب: «{raw}» غير مطلوبٍ ويتجاوز إجمالي المطلوب.")
        else:
            issues.append(f"⚠️ نوع محكومٍ به لم يُطابق طلباً بلفظه: «{raw}» — يُتحقَّق أنه ضمن الطلبات.")
    total_granted = sum(granted_by_type.values()) + sum(ga for _, ga in unmatched)
    if total_granted > total_req + 1e-6:
        issues.append(f"⛔ مجموع المحكوم به ({total_granted:g}) يتجاوز مجموع المطلوب ({total_req:g}).")
    return issues


_ILZAM = ("إلزام", "ألزم", "يؤدي", "بأداء", "يدفع")
_RAFD = ("رفض", "عدم قبول", "ردّ الدعوى")


def check_mantuq_consistency(direction: str, operative: str, granted: list[dict] | None = None,
                             requests: list[dict] | None = None) -> list[str]:
    """اتّساق المنطوق مع نتيجة التسبيب (م.200: تناقض المنطوق) — يغطّي الاتجاهات
    الأربعة كلّها والاتجاهَ المجهول (فشل parsing)، فلا يُعطَّل الفحص باختيار الاتجاه."""
    op = sources._norm(operative or "")
    has_ilzam = any(sources._norm(k) in op for k in _ILZAM)
    has_rafd = any(sources._norm(k) in op for k in _RAFD)
    g = granted or []
    issues: list[str] = []
    if direction == "رفض الدعوى":
        if has_ilzam:
            issues.append("⛔ تناقض: التسبيب يقضي بالرفض والمنطوق يُلزم.")
        if g:
            issues.append("⛔ تناقض: التسبيب بالرفض مع وجود محكومٍ به.")
    elif direction == "للمدعي":
        if has_rafd and not has_ilzam:
            issues.append("⛔ تناقض: التسبيب لصالح المدعي والمنطوق يرفض.")
        if not g and not has_ilzam:
            issues.append("⚠️ المنطوق لا يعكس صراحةً ما رجّحه التسبيب لصالح المدعي.")
    elif direction == "للمدعى عليه":
        if has_ilzam:
            issues.append("⛔ تناقض: التسبيب لصالح المدعى عليه والمنطوق يُلزمه بالأداء.")
        if g:
            issues.append("⛔ تناقض: التسبيب لصالح المدعى عليه مع وجود محكومٍ به للمدعي.")
    elif direction == "جزئي":
        if not g:
            issues.append("⛔ تناقض: اتجاهٌ جزئيٌّ بلا محكومٍ به في المنطوق.")
        elif has_rafd and not has_ilzam:
            issues.append("⛔ تناقض: اتجاهٌ جزئيٌّ والمنطوق رفضٌ خالصٌ بلا إلزام.")
        elif requests:
            req: dict[str, float] = {}
            for r in requests:
                t = sources._norm(r.get("type", ""))
                req[t] = max(req.get(t, 0.0), _num(r.get("amount", 0)))
            got: dict[str, float] = {}
            for x in g:
                k = _match_req_type(sources._norm(x.get("type", "")), req)
                if k is not None:
                    got[k] = got.get(k, 0.0) + _num(x.get("amount", 0))
            if req and all(got.get(t, 0.0) >= v - 1e-6 for t, v in req.items() if v > 0) and got:
                issues.append("⚠️ اتجاهٌ «جزئي» اسماً والمحكومُ به يساوي كامل المطلوب فعلاً.")
    else:
        issues.append("⚠️ اتجاه التسبيب غير محدّد — تعذّر فحص اتّساق المنطوق مع الأسباب.")
    return issues


def check_defenses_addressed(defenses: list[str], addressed: list[str]) -> list[str]:
    """الردّ على الدفوع الجوهرية (إغفالها مطعنٌ في الحكم) — بمطابقةٍ مُطبَّعة."""
    add = {sources._norm(a) for a in addressed}
    return [f"⚠️ دفعٌ جوهريٌّ لم يُردّ عليه: «{d}»." for d in defenses if sources._norm(d) not in add]


# ============================ القيادة ============================
def adjudicate(state) -> dict:
    """
    يشغّل سلسلة العمليات ويُنتج حكماً مُتحقَّقاً منه مقدّمةً مقدّمة + تقرير تأصيل.
    """
    from concurrent.futures import ThreadPoolExecutor
    prior: dict = {}
    results: list[OpResult] = []
    # المرحلة 1 (متوازية): التحرير/التكييف/محل النزاع — كلٌّ يقرأ ملف الدعوى فقط
    # ولا يعتمد على مخرَج الآخر. الدمج بترتيبٍ ثابت حفاظاً على حتمية السياق اللاحق.
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(op, state, {}) for op in (op_tahrir, op_takyif, op_mahal)]
        stage1 = [f.result() for f in futs]
    for r in stage1:
        prior[r.key] = r.data
        results.append(r)
    # المراحل 2→4 (تسلسلية بحكم الاعتمادية): إثبات ← تطبيق (يُنزِل على الوقائع الثابتة) ← تسبيب.
    for op in (op_ithbat, op_tatbiq, op_tasbib):
        r = op(state, prior)
        prior[r.key] = r.data
        results.append(r)
    results.append(op_muraja(results))

    tasbib = prior.get("tasbib", {})
    all_cites = [c for r in results for c in r.cites]
    # نصوص المقاطع المُسترجَعة فعلاً (عمليات + بحث قضائي) — تُحقَّق بها اقتباسات المبادئ/السوابق.
    # None يبقى None إن لم يجرِ أي استرجاعٍ إطلاقاً (وضعٌ وهمي/اختبار وحدوي) فلا يُحاسَب عليه.
    ev_lists = [r.evidence for r in results]
    research_ev = (state.get("research") or {}).get("evidence")
    if all(e is None for e in ev_lists) and research_ev is None:
        all_evidence = None
    else:
        all_evidence = [x for e in ev_lists if e for x in e] + (research_ev or [])
    grounding = sources.assess_grounding(all_cites, all_evidence)

    flags = list(grounding["issues"]) + list(grounding["uncertainty"])
    for r in results:
        flags += [f"[{r.label}] {i}" for i in r.verdict.issues]

    # المخالفات الحابسة (⛔): اختلاقٌ في التأصيل، أو قضاءٌ بما لم يُطلب، أو تناقض المنطوق.
    blocking = [f for f in flags if "⛔" in f]
    if not grounding["ok"]:
        blocking.append(f"⛔ الحكم غير مؤصَّل (اختلاق={grounding['fabricated']}، مؤصَّل={grounding['verified']}).")
    blocked = bool(blocking)

    sound = (not blocked) and all(r.verdict.ok for r in results)
    confidence = ("محجوب" if blocked else
                  "عالية" if sound and not grounding["uncertainty"] else
                  "متوسطة" if sound else "منخفضة")
    direction = tasbib.get("direction", "")

    facts = (prior.get("tahrir", {}).get("summary", "") + " " +
             prior.get("mahal", {}).get("summary", "")).strip()
    # الحبس: لا يُنطَق بحكمٍ موضوعيٍّ مبنيٍّ على اختلاقٍ أو مخالفةٍ جوهرية.
    if blocked:
        operative = "⛔ تعذّر إصدار حكمٍ مؤصَّل — رُصدت مخالفاتٌ جوهرية تمنع النطق: " + "؛ ".join(blocking[:4])
    else:
        operative = tasbib.get("operative", "")

    return {
        "facts": facts,
        "reasons": tasbib.get("reasons", ""),
        "operative": operative,
        "direction": direction,
        "blocked": blocked,
        "cites": all_cites,
        "confidence": confidence,
        "flags": flags,
        "grounding": grounding,
        "chain": [{"key": r.key, "label": r.label, "summary": r.data.get("summary", ""),
                   "ok": r.verdict.ok, "issues": r.verdict.issues} for r in results],
    }
