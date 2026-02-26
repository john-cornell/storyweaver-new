"""
LLM package: completion via configured provider.
"""

from __future__ import annotations

from .client import complete, get_first_provider

__all__ = [
    "complete",
    "get_first_provider",
]
