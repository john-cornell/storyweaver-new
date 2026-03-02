"""
Panel navigation: return visibility updates, refreshed Working (current + history) and Log, and log entries.
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from log import add_entry, build_log_markdown
from working import (
    build_current_story_html,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
    build_story_prose_only,
)


def _nav_outputs(
    write_vis: bool,
    working_vis: bool,
    config_vis: bool,
    log_vis: bool,
    steps: list | None,
    history: list | None,
    entries: list[str],
) -> tuple[dict, dict, dict, dict, str, str, str, str, str, str, str, list[str], str]:
    current_md = build_current_story_html(steps or [])
    history_md = build_history_markdown(history or [])
    output_md = build_output_paragraphs_markdown(steps or [])
    output_copy_html = build_output_copy_button_html(steps or [])
    full_history_copy_html = build_full_history_copy_button_html(steps or [], history or [])
    full_history_md = build_full_history_text(steps or [], history or [])
    story_prose = build_story_prose_only(steps or [])
    return (
        gr.update(visible=write_vis),
        gr.update(visible=working_vis),
        gr.update(visible=config_vis),
        gr.update(visible=log_vis),
        current_md,
        history_md,
        output_md,
        output_copy_html,
        full_history_copy_html,
        full_history_md,
        build_log_markdown(entries),
        entries,
        story_prose,
    )


def nav_to_write(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
) -> tuple[dict[str, Any], ...]:
    """Show Write panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Write")
    return _nav_outputs(True, False, False, False, steps, history, entries)


def nav_to_working(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
) -> tuple[dict[str, Any], ...]:
    """Show Working panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Working")
    return _nav_outputs(False, True, False, False, steps, history, entries)


def nav_to_config(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
) -> tuple[dict[str, Any], ...]:
    """Show Config panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Config")
    return _nav_outputs(False, False, True, False, steps, history, entries)


def nav_to_log(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
) -> tuple[dict[str, Any], ...]:
    """Show Log panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Log")
    return _nav_outputs(False, False, False, True, steps, history, entries)
