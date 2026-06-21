"""
مِقياس تقييم محرّك الاستدلال (corpus-agnostic) — ركيزة «يُقاس لا يُفترَض».
يُحمِّل قضايا بحقيقةٍ مرجعية (JSONL) ويُشغّل operators.adjudicate على وقائعها، فيقيس:
  • موافقة المنطوق (direction) — Macro-F1 (لأن التوزيع منحرف).
  • أمانة الاستشهاد — نسبة «صفر اختلاق»، ونسبة المؤصَّل، واسترجاع المواد الصحيحة.
  • السلامة البنيوية — نسبة الأحكام المحجوبة (مخالفات م.200/اختلاق).

هذا هو ما يجعل ALARB مفيداً: ليس مكوّناً في المحكمة، بل المسطرة التي تُثبت
أن الاستدلال والإسناد يتحسّنان (بوابة عدم انحدار)، ويعمل لاحقاً على أحكام
وزارة العدل والمبادئ القضائية بنفس الواجهة.

تنبيه صدق: في الوضع الوهمي المحرّك يُعيد مخرجاً ثابتاً، فالأرقام «سباكة» لا دلالة لها.
الدلالة في الوضع الحقيقي (BAYYIN_MOCK=0) على بياناتٍ حقيقية.

  python -m bayyin.evaluation alarb.jsonl       # حقول: case_id, facts, true_direction, true_regulations[]
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from bayyin import operators, settings
from bayyin.sources import _norm
from bayyin.state import Document, DocType

SAMPLE = [
    {"case_id": "S1", "true_direction": "للمدعي", "true_regulations": ["نظام المعاملات المدنية", "نظام الإثبات"],
     "facts": "عقد توريد ثابت، تسلّم المدعى عليه البضاعة بمحاضر موقّعة وامتنع عن السداد بلا دفعٍ معتبر."},
    {"case_id": "S2", "true_direction": "رفض الدعوى", "true_regulations": ["نظام الإثبات"],
     "facts": "لم يُثبت المدعي علاقةً تعاقدية ولا تسلّم المدعى عليه أي مبلغ، وأنكر المدعى عليه الدعوى."},
]


def _load(path: str | None) -> list[dict]:
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return SAMPLE


def _state(facts: str) -> dict:
    return {"case_type": "تجاري", "claim_subject": facts[:120], "claim_value": 0.0,
            "document_ledger": [Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي",
                                         title="صحيفة الدعوى", body=facts)]}


def _macro_f1(pairs: list[tuple[str, str]]) -> float:
    labels = {t for t, _ in pairs} | {p for _, p in pairs}
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    for t, p in pairs:
        if t == p:
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1
    f1s = []
    for lab in labels:
        prec = tp[lab] / (tp[lab] + fp[lab]) if (tp[lab] + fp[lab]) else 0.0
        rec = tp[lab] / (tp[lab] + fn[lab]) if (tp[lab] + fn[lab]) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def _reg_recall(cites, true_regs: list[str]) -> tuple[int, int]:
    cited = " ".join(_norm(c.system + " " + c.article) for c in cites)
    hit = 0
    for r in true_regs:
        key = _norm(r).split()
        if key and key[0] in cited:
            hit += 1
    return hit, len(true_regs)


def evaluate(path: str | None = None) -> dict:
    data = _load(path)
    pairs, rows = [], []
    zero_fab = grounded = blocked = reg_hit = reg_tot = 0
    for case in data:
        adj = operators.adjudicate(_state(case["facts"]))
        pred = adj["direction"] or ("محجوب" if adj["blocked"] else "—")
        pairs.append((case.get("true_direction", ""), pred))
        g = adj["grounding"]
        zero_fab += g["fabricated"] == 0
        grounded += g["verified"] >= 1
        blocked += bool(adj["blocked"])
        h, t = _reg_recall(adj["cites"], case.get("true_regulations", []))
        reg_hit += h
        reg_tot += t
        rows.append((case.get("case_id", ""), case.get("true_direction", ""), pred, g["fabricated"]))
    n = len(data) or 1
    return {
        "n": len(data),
        "direction_macro_f1": _macro_f1(pairs),
        "zero_fabrication_rate": zero_fab / n,
        "grounded_rate": grounded / n,
        "blocked_rate": blocked / n,
        "regulation_recall": (reg_hit / reg_tot) if reg_tot else 0.0,
        "rows": rows,
    }


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("ALARB_PATH")
    rep = evaluate(path)
    if settings.MOCK:
        print("⚠️ وضع وهمي: المحرّك يُعيد مخرجاً ثابتاً — هذه الأرقام «سباكة» لا دلالة لها.")
        print("   شغّل بـ BAYYIN_MOCK=0 على بيانات ALARB الحقيقية لقياسٍ ذي معنى.\n")
    print(f"عدد القضايا: {rep['n']}")
    print(f"موافقة المنطوق (Macro-F1): {rep['direction_macro_f1']:.2f}")
    print(f"صفر اختلاق: {rep['zero_fabrication_rate'] * 100:.0f}%  ·  مؤصَّل: {rep['grounded_rate'] * 100:.0f}%")
    print(f"استرجاع المواد الصحيحة: {rep['regulation_recall'] * 100:.0f}%")
    print(f"الأحكام المحجوبة: {rep['blocked_rate'] * 100:.0f}%")
    print("\n(corpus-agnostic: نفس الهارنس على ALARB التجاري ثم أحكام وزارة العدل والمبادئ القضائية.)")


if __name__ == "__main__":
    main()
