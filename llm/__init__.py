"""
LLM package: completion via configured provider.
"""

from __future__ import annotations

from .client import (
    complete,
    get_first_provider,
    get_llm_log_buffer,
    log_llm_outcome,
    LLMResult,
    set_show_provider_in_log,
)
from config import LLMTaskType

__all__ = [
    "complete",
    "get_first_provider",
    "get_llm_log_buffer",
    "LLMResult",
    "LLMTaskType",
    "log_llm_outcome",
    "set_show_provider_in_log",
]
