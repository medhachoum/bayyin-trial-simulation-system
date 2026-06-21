"""
بُناة مواصفات الأدوات المستضافة (file_search و web_search) لـ Responses API.
نختار قواعد البحث حسب دور الوكيل (المُسجِّل: الأنظمة فقط؛ المدعى عليه: الكل؛ القاضي: أنظمة+سوابق).
"""
from __future__ import annotations

from .settings import ALLOWED_DOMAINS, VECTOR_STORES


def file_search_tool(*tool_keys: str) -> list[dict]:
    """أداة file_search واحدة تشمل مخزونات الأدوات المنطقية المطلوبة.
    حدّ Responses API: مخزونان كحدّ أقصى لكل نداء → نقتصر على أهمّ مخزونين."""
    ids = [VECTOR_STORES[k]["id"] for k in tool_keys if k in VECTOR_STORES]
    if not ids:
        return []
    return [{"type": "file_search", "vector_store_ids": ids[:2]}]


def web_search_tool() -> list[dict]:
    """بحث ويب مقيّد بالنطاقات الرسمية المسموح بها."""
    return [{"type": "web_search", "filters": {"allowed_domains": ALLOWED_DOMAINS}}]


def tools_for(*tool_keys: str, web: bool = False) -> list[dict]:
    tools = file_search_tool(*tool_keys)
    if web:
        tools += web_search_tool()
    return tools
