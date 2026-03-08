"""
Working package: expand idea into précis, expand précis into steps, expand paragraphs (tree + history).
"""

from __future__ import annotations

from .handlers import (
    do_auto_expand_next,
    do_expand_idea,
    do_expand_next,
    do_generate_beat_outline,
    do_pause_auto,
    do_regenerate_beat_outline,
    do_reset_write,
    do_start_write,
    do_undo_precis,
)
from .erl_ui import build_erl_tab_content
from .steps_ui import (
    EMPTY_STORY_PLACEHOLDER,
    build_current_story_html,
    build_current_story_markdown,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_latest_story_display,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
    build_story_prose_only,
    build_working_markdown,
)
from .types import HistoryEntry, Step

__all__ = [
    "build_erl_tab_content",
    "EMPTY_STORY_PLACEHOLDER",
    "HistoryEntry",
    "Step",
    "build_current_story_html",
    "build_current_story_markdown",
    "build_full_history_copy_button_html",
    "build_full_history_text",
    "build_history_markdown",
    "build_latest_story_display",
    "build_output_copy_button_html",
    "build_output_paragraphs_markdown",
    "build_story_prose_only",
    "build_working_markdown",
    "do_auto_expand_next",
    "do_expand_idea",
    "do_expand_next",
    "do_generate_beat_outline",
    "do_pause_auto",
    "do_regenerate_beat_outline",
    "do_reset_write",
    "do_start_write",
    "do_undo_precis",
]
