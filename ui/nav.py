"""
Panel navigation: return visibility updates, refreshed Working (current + history) and Log, and log entries.
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from log import add_entry, build_llm_log_markdown, build_log_markdown
from working import (
    build_current_story_html,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_latest_story_display,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
)
from working.modes import GenerationMode


def _nav_outputs(
    write_vis: bool,
    working_vis: bool,
    config_vis: bool,
    log_vis: bool,
    humanize_vis: bool,
    steps: list | None,
    history: list | None,
    entries: list[str],
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict, dict, dict, dict, dict, str, str, str, str, str, str, str, list[str], str, str, str]:
    if (mode or "").strip() == GenerationMode.INTERACTIVE.value and interactive_state and interactive_state.get("nodes"):
        from working.interactive.tree_utils import format_choices_block, get_prose_to_node
        from working.interactive.ui import build_path_tree_html
        node_id = interactive_state.get("current_node_id", 0)
        prose = get_prose_to_node(interactive_state["nodes"], node_id)
        choice_a = interactive_state.get("choice_a", "") or ""
        choice_b = interactive_state.get("choice_b", "") or ""
        prose += format_choices_block(choice_a, choice_b)
        current_md = prose
        path_tree = build_path_tree_html(
            interactive_state["nodes"],
            interactive_state.get("choices", []),
            node_id,
        )
    else:
        current_md = build_current_story_html(steps or [])
        path_tree = "<p><em>No story yet.</em></p>"
    history_md = build_history_markdown(history or [])
    output_md = build_output_paragraphs_markdown(steps or [])
    output_copy_html = build_output_copy_button_html(steps or [])
    full_history_copy_html = build_full_history_copy_button_html(steps or [], history or [])
    full_history_md = build_full_history_text(steps or [], history or [])
    story_prose = build_latest_story_display(steps or [])
    return (
        gr.update(visible=write_vis),
        gr.update(visible=working_vis),
        gr.update(visible=config_vis),
        gr.update(visible=log_vis),
        gr.update(visible=humanize_vis),
        current_md,
        history_md,
        output_md,
        output_copy_html,
        full_history_copy_html,
        full_history_md,
        build_log_markdown(entries),
        entries,
        build_llm_log_markdown(),
        story_prose,
        path_tree,
    )


def nav_to_write(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Show Write panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Write")
    return _nav_outputs(True, False, False, False, False, steps, history, entries, interactive_state, mode)


def nav_to_working(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Show Working panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Working")
    return _nav_outputs(False, True, False, False, False, steps, history, entries, interactive_state, mode)


def nav_to_config(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Show Config panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Config")
    return _nav_outputs(False, False, True, False, False, steps, history, entries, interactive_state, mode)


def nav_to_log(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Show Log panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Log")
    return _nav_outputs(False, False, False, True, False, steps, history, entries, interactive_state, mode)


def nav_to_humanize(
    steps: list | None,
    history: list | None,
    log_entries: list[str] | None,
    interactive_state: dict | None = None,
    mode: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Show Humanize panel; log the action."""
    entries = add_entry(log_entries or [], "Navigated to Humanize")
    return _nav_outputs(False, False, False, False, True, steps, history, entries, interactive_state, mode)
