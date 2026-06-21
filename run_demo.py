"""
عرض تشغيلي كامل لنظام «بيّن» (M1–M4).
يعمل في الوضع الوهمي افتراضياً (بلا أي نداء API).

  python run_demo.py                          # وهمي
  $env:BAYYIN_MOCK=0 ; python run_demo.py      # حقيقي (يتطلب OPENAI_API_KEY)

سيناريوهان:
  أ) تقاضٍ كامل: ابتدائي (حلقة + خبير) ← استئناف ← دائرة ثلاثية ← حكم قطعي.
  ب) وضع تدريب: حكم نهائي فيه ثغرة محقونة ← التماس إعادة النظر (م.200).
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ.setdefault("BAYYIN_MOCK", "1")

from bayyin.graph import build_graph                       # noqa: E402
from bayyin.settings import DISCLAIMER                      # noqa: E402
from bayyin.state import Document, DocType, Party           # noqa: E402


def _claim(body: str) -> Document:
    return Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي",
                    title="صحيفة الدعوى", body=body, event="قيد الدعوى")


def scenario_full() -> dict:
    return {
        "case_id": "TC-2026-000123", "case_type": "تجاري",
        "claim_subject": "مطالبة بثمن بضاعة بموجب عقد توريد (كمية ومواصفات)",
        "claim_value": 250_000.0,
        "parties": [Party(role="مدعي", name="شركة التوريدات", is_human=True),
                    Party(role="مدعى عليه", name="شركة المقاولات")],
        "document_ledger": [_claim(
            "يطالب المدعي المدعى عليه بسداد 250,000 ريال ثمن بضاعة وُرّدت بموجب "
            "عقد توريد موقّع، مع الفائدة النظامية، لامتناعه عن السداد رغم الإنذار.")],
        "scripted_plaintiff_replies": ["الاختصاص منعقد، ومحاضر الاستلام تثبت المطابقة، وأتمسك بطلباتي."],
        "appeal_requested": True,
        "scripted_appeal_brief": "أعترض على الحكم لمخالفته الثابت بمحاضر الاستلام وتقرير الخبير، وألتمس إلغاءه.",
        "deadlines": {},
    }


def scenario_training() -> dict:
    return {
        "case_id": "TC-2026-000777", "case_type": "تجاري",
        "claim_subject": "مطالبة بمبلغ قرض",
        "claim_value": 20_000.0,           # دون حدّ القطعية → نهائي ابتدائياً
        "parties": [Party(role="مدعي", name="فهد", is_human=True),
                    Party(role="مدعى عليه", name="سالم")],
        "document_ledger": [_claim("يطالب المدعي المدعى عليه بسداد قرض قدره 20,000 ريال.")],
        "scripted_plaintiff_replies": ["أتمسك بطلبي."],
        "inject_exploit": "ultra_petita",          # وضع التدريب: حقن «الحكم بما لم يُطلب»
        "reconsideration_requested": True,
        "reconsideration_ground": "ultra_petita",  # المحامي يلتمس على السبب الصحيح
        "deadlines": {},
    }


def _print_doc(doc: Document) -> None:
    tag = " ⚑(مزوّر-خفي)" if doc.flag == "forged" else ""
    print(f"\n  ▸ [{doc.title}] — {doc.author_role}{tag}")
    print("   " + doc.body.replace("\n", "\n   "))
    for c in doc.citations:
        print(f"      • إسناد: {c.claim}  ⟵  {c.source_tool}")


def _print_ruling(title: str, j) -> None:
    print("\n" + "=" * 72 + f"\n■ {title}\n" + "=" * 72)
    print(f"\n● الوقائع:\n{j.facts}")
    print(f"\n● الأسباب:\n{j.reasons}")
    print(f"\n● المنطوق:\n{j.operative}")
    if j.appealable is not None:
        route = "قابل للاستئناف" if j.appealable else "نهائي"
        print(f"\n● قابلية الاعتراض: {route} — الطريق: {j.appeal_route}")


def run(title: str, state: dict) -> None:
    app = build_graph()
    final = app.invoke(state, {"configurable": {"thread_id": state["case_id"]}})

    print("\n" + "#" * 72)
    print(f"# {title}: الدعوى {final['case_id']} ({final['case_type']}) — قيمة {final.get('claim_value')}")
    print("#" * 72)

    print("\n■ المرافعات والمستندات:")
    for doc in final["document_ledger"]:
        if doc.doc_type != DocType.CLAIM_SHEET:
            _print_doc(doc)

    if final.get("judgment"):
        _print_ruling("الحكم الابتدائي", final["judgment"])
    if final.get("panel_votes"):
        print("\n● أصوات دائرة الاستئناف:")
        for v in final["panel_votes"]:
            print(f"   - عضو ({v['lens']}): {v['vote']}")
    if final.get("appeal_judgment"):
        _print_ruling("الحكم النهائي القطعي (استئناف)", final["appeal_judgment"])
    if final.get("reconsideration_outcome"):
        print(f"\n● نتيجة التماس إعادة النظر (م.200):\n   {final['reconsideration_outcome']}")

    print("\n■ سجل التدقيق:")
    for i, e in enumerate(final.get("audit_log", []), 1):
        extra = f" | مصادر: {', '.join(e['sources'])}" if e.get("sources") else ""
        mdl = f" [{e['model']}]" if e.get("model") else ""
        print(f"  {i:>2}. {e['actor']}: {e['action']}{mdl}{extra}")
        if e.get("detail"):
            print(f"      {e['detail']}")


def main() -> None:
    run("سيناريو (أ) — تقاضٍ كامل حتى الاستئناف", scenario_full())
    run("سيناريو (ب) — وضع التدريب على الثغرات", scenario_training())
    print("\n" + DISCLAIMER)


if __name__ == "__main__":
    main()
