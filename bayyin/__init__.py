"""نظام «بيّن» — محاكاة المحاكمات القضائية السعودية بوكلاء متعددين."""
from __future__ import annotations

__version__ = "0.1.0"  # M1: شريحة رأسية للمرحلة الأولى

from .graph import build_graph

__all__ = ["build_graph", "__version__"]
