"""
تشغيل حقيقي بمفتاح المستخدم — المرحلة الأولى كاملة حتى النطق بالحكم.
يستدعي عائلة gpt-5.6 فعلياً (luna/terra/sol حسب الطبقة) + file_search + web_search.
(لتفعيل الاستئناف الحقيقي أيضاً: اجعل appeal_requested=True — يضيف ٦ نداءات sol.)
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ["BAYYIN_MOCK"] = "0"  # وضع حقيقي

from bayyin.graph import build_graph                  # noqa: E402
from bayyin.settings import DISCLAIMER                 # noqa: E402
from bayyin.state import Document, DocType, Party      # noqa: E402

state = {
    "case_id": "REAL-TC-2026-001", "case_type": "تجاري",
    "claim_subject": "مطالبة بثمن بضاعة بموجب عقد توريد مع خلاف على الكمية والمواصفات",
    "claim_value": 250_000.0,
    "parties": [Party(role="مدعي", name="شركة التوريدات", is_human=True),
                Party(role="مدعى عليه", name="شركة المقاولات")],
    "document_ledger": [Document(
        doc_type=DocType.CLAIM_SHEET, author_role="مدعي", title="صحيفة الدعوى",
        body=("يطالب المدعي المدعى عليه بسداد 250,000 ريال ثمن بضاعة وُرّدت بموجب "
              "عقد توريد موقّع، مع الفائدة النظامية، لامتناعه عن السداد رغم الإنذار."),
        event="قيد الدعوى")],
    "scripted_plaintiff_replies": ["الاختصاص منعقد، ومحاضر الاستلام تثبت المطابقة، وأتمسك بطلباتي."],
    "deadlines": {},
}


def main() -> None:
    print("⏳ تشغيل حقيقي (عائلة gpt-5.6) — قد يستغرق دقيقة أو دقيقتين…\n")
    app = build_graph()
    final = app.invoke(state, {"configurable": {"thread_id": state["case_id"]}})

    print("=" * 72)
    print(f"الدعوى {final['case_id']} — التعقيد: {final.get('complexity')}")
    print("=" * 72)

    for doc in final["document_ledger"]:
        if doc.doc_type in (DocType.DEFENSE_MEMO, DocType.EXPERT_REPORT):
            print(f"\n▸ [{doc.title}] — {doc.author_role}")
            print("  " + doc.body[:600].replace("\n", "\n  "))
            for c in doc.citations:
                print(f"    • {c.claim} ⟵ {c.source_tool} | {c.source_ref}")

    j = final.get("judgment")
    if j:
        print("\n" + "=" * 72 + "\n■ صك الحكم (حقيقي)\n" + "=" * 72)
        print(f"\n● الوقائع:\n{j.facts}")
        print(f"\n● الأسباب:\n{j.reasons}")
        print(f"\n● المنطوق:\n{j.operative}")
        for c in j.citations:
            print(f"   • {c.claim} ⟵ {c.source_tool} | {c.source_ref}")
        print(f"\n● قابلية الاعتراض: {'قابل للاستئناف' if j.appealable else 'نهائي'} ({j.appeal_route})")

    print("\n■ سجل التدقيق:")
    for i, e in enumerate(final.get("audit_log", []), 1):
        src = f" | مصادر: {', '.join(e['sources'])}" if e.get("sources") else ""
        print(f"  {i:>2}. {e['actor']}: {e['action']}{(' [' + e['model'] + ']') if e.get('model') else ''}{src}")

    print("\n" + DISCLAIMER)


if __name__ == "__main__":
    main()
