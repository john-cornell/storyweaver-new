"""
Generation mode abstraction: expansion (tree) vs interactive (binary choices, replay).
"""

from __future__ import annotations

from .registry import get_handler
from .types import GenerationMode, ModeHandler

__all__ = ["GenerationMode", "ModeHandler", "get_handler"]
