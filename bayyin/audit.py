"""سجل التدقيق — كل خطوة إجرائية تُسجَّل: الفاعل، الإجراء، النموذج، المصادر."""
from __future__ import annotations


def event(actor: str, action: str, *, model: str = "", detail: str = "",
          sources: list[str] | None = None) -> dict:
    """يبني قيد تدقيق واحداً (يُضاف إلى audit_log المتراكم في الحالة)."""
    return {
        "actor": actor,
        "action": action,
        "model": model,
        "detail": detail,
        "sources": sources or [],
    }
