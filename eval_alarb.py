"""
M5 — مِقياس تقييم مستوحى من ALARB (arXiv:2510.00694).
يشغّل وكيل القاضي على عيّنة {وقائع → منطوق متوقع} ويقيس نسبة الاتفاق.
يحمّل JSONL إن وُفّر عبر متغيّر البيئة ALARB_PATH، وإلا يستخدم عيّنة مدمجة.
هذا هيكل تقييم يُوصَل ببيانات ALARB الحقيقية (13 ألف قضية) للقياس الجاد.

  python eval_alarb.py                      # وهمي
  $env:BAYYIN_MOCK=0 ; python eval_alarb.py  # حقيقي
"""
from __future__ import annotations

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from bayyin import prompts, settings           # noqa: E402
from bayyin.llm import get_llm                  # noqa: E402
from bayyin.nodes import JUDGMENT_SCHEMA        # noqa: E402
from bayyin.tools import tools_for              # noqa: E402

SAMPLE = [
    {"facts": "ثبت عقد التوريد وتسلّم المدعى عليه البضاعة وامتنع عن السداد بلا دفع معتبر.",
     "expected": "إلزام"},
    {"facts": "لم يُثبت المدعي علاقة تعاقدية ولا تسلّم المدعى عليه أي مبلغ، وأنكر المدعى عليه.",
     "expected": "رفض"},
]


def _load() -> list[dict]:
    path = os.getenv("ALARB_PATH")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return SAMPLE


def _classify(operative: str) -> str:
    return "رفض" if ("رفض" in operative and "إلزام" not in operative) else "إلزام"


def main() -> None:
    llm = get_llm()
    data = _load()
    correct = 0
    for i, case in enumerate(data, 1):
        res = llm.complete(
            model=settings.GPT_PRO, system=prompts.TRIAL_JUDGE,
            user=f"الوقائع: {case['facts']}\nأصدر حكماً مسبّباً.",
            tools=tools_for("search_saudi_codes", "search_commercial_precedents"),
            schema=JUDGMENT_SCHEMA, role="judge",
        )
        got = _classify((res.get("data") or {}).get("operative", ""))
        ok = got == case["expected"]
        correct += ok
        print(f"{i}. متوقع={case['expected']}  ناتج={got}  {'✓' if ok else '✗'}")
    print(f"\nالدقة: {correct}/{len(data)} = {correct / len(data) * 100:.0f}%")
    print("(عيّنة مدمجة — اضبط ALARB_PATH على بيانات ALARB الحقيقية للقياس الجاد.)")


if __name__ == "__main__":
    main()
