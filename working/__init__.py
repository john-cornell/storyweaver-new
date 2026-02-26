"""
Working package: expand idea into précis, expand précis into steps, expand paragraphs (tree + history).
"""

from __future__ import annotations

from .handlers import (
    do_auto_expand_next,
    do_expand_idea,
    do_expand_next,
    do_pause_auto,
    do_start_write,
    do_undo_precis,
)
from .steps_ui import (
    EMPTY_STORY_PLACEHOLDER,
    build_current_story_markdown,
    build_history_markdown,
    build_story_prose_only,
    build_working_markdown,
)
from .types import HistoryEntry, Step

__all__ = [
    "EMPTY_STORY_PLACEHOLDER",
    "HistoryEntry",
    "Step",
    "build_current_story_markdown",
    "build_history_markdown",
    "build_story_prose_only",
    "build_working_markdown",
    "do_auto_expand_next",
    "do_expand_idea",
    "do_expand_next",
    "do_pause_auto",
    "do_start_write",
    "do_undo_precis",
]
