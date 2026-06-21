"""مسبار تكامل حقيقي: يختبر file_search + JSON schema عبر مسار الكود الفعلي."""
import os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ["BAYYIN_MOCK"] = "0"

from bayyin import prompts, settings
from bayyin.llm import get_llm
from bayyin.nodes import DEFENSE_SCHEMA
from bayyin.tools import tools_for

llm = get_llm()

print("— اختبار file_search + JSON schema (مسار وكيل المدعى عليه) —")
try:
    res = llm.complete(
        model=settings.GPT_ROUTER,  # mini لتوفير التكلفة في المسبار
        system=prompts.DEFENDANT,
        user="دعوى تجارية: مطالبة بثمن بضاعة 250000 ريال بموجب عقد توريد. اكتب مذكرة جوابية موجزة.",
        tools=tools_for("search_saudi_codes", "search_commercial_precedents"),
        schema=DEFENSE_SCHEMA, role="defendant",
    )
    data = res.get("data")
    print("DATA parsed:", "نعم" if data else "لا")
    if data:
        print("  title:", data.get("title"))
        print("  citations:", len(data.get("citations", [])))
    print("TEXT head:", (res.get("text") or "")[:200])
    print(">>> file_search + schema: OK")
except Exception as e:
    print(">>> ERROR:", type(e).__name__, str(e)[:500])
