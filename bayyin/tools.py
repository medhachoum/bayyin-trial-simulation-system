"""
بُناة مواصفات الأدوات المستضافة (file_search و web_search) لـ Responses API.
نختار قواعد البحث حسب دور الوكيل (المُسجِّل: الأنظمة فقط؛ المدعى عليه: الكل؛ القاضي: أنظمة+سوابق).
"""
from __future__ import annotations

import warnings

from .settings import (ALLOWED_DOMAINS, COMMERCIAL_PRECEDENT_STORES,
                       FILE_SEARCH_MAX_RESULTS, VECTOR_STORES)


def _fs(ids: list[str]) -> dict:
    """مواصفة file_search مع حدٍّ لعدد النتائج (يسرّع الاسترجاع من المخازن الكبيرة)."""
    return {"type": "file_search", "vector_store_ids": ids[:2],
            "max_num_results": FILE_SEARCH_MAX_RESULTS}


def file_search_tool(*tool_keys: str) -> list[dict]:
    """أداة file_search واحدة تشمل مخزونات الأدوات المنطقية المطلوبة.
    حدّ Responses API: مخزونان كحدّ أقصى لكل نداء → نقتصر على أهمّ مخزونين.
    نُحذّر صراحةً (بدل الإسقاط الصامت) عند مفتاحٍ مجهول أو تجاوز الحدّ، كشفاً لسوء الإعداد."""
    for k in tool_keys:
        if k not in VECTOR_STORES:
            warnings.warn(f"file_search: مفتاح مخزونٍ غير معروف «{k}» — تُجوهِل.", stacklevel=2)
    ids = [VECTOR_STORES[k]["id"] for k in tool_keys if k in VECTOR_STORES]
    if not ids:
        return []
    if len(ids) > 2:
        warnings.warn(f"file_search: طُلب {len(ids)} مخزوناً والحدّ مخزونان — اقتُصِر على الأوّلين.",
                      stacklevel=2)
    return [_fs(ids)]


def precedents_tool() -> list[dict]:
    """نداء file_search على مخزني السوابق التجارية معاً (يستهلك حدّ المخزنين كاملاً).
    يُستعمل في طبقة البحث القضائي حصراً، فلا يُزاحم نداءات التأصيل (أنظمة+مبادئ)."""
    ids = [VECTOR_STORES[k]["id"] for k in COMMERCIAL_PRECEDENT_STORES if k in VECTOR_STORES]
    return [_fs(ids)] if ids else []


def web_search_tool() -> list[dict]:
    """بحث ويب مقيّد بالنطاقات الرسمية المسموح بها."""
    return [{"type": "web_search", "filters": {"allowed_domains": ALLOWED_DOMAINS}}]


def tools_for(*tool_keys: str, web: bool = False) -> list[dict]:
    tools = file_search_tool(*tool_keys)
    if web:
        tools += web_search_tool()
    return tools
