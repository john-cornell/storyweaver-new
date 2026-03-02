"""
Write-panel and Working-panel handlers:
  do_expand_idea   — pre-run only: turn rough idea into précis, update Idea textbox (no paragraphs added)
  do_start_write  — kick off: expand précis into two paragraphs, navigate to Working
  do_expand_next  — expand first leaf paragraph into two (tree + history)
  do_auto_expand_next — generator: run expand_round in a loop (2→4→8→…) until limit/pause/no leaf; updates Write-tab buttons (Start, Expand idea to précis, Undo précis) to disabled while running, re-enabled when done
  do_pause_auto  — set flag so auto loop stops after current expansion
Logs actions and outcomes to running log. Vetting stubs run after expansion.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Iterator

import gradio as gr

from db import load_story, save_story
from llm import complete
from log import add_entry, build_log_markdown

from .parsing import parse_two_paragraphs
from .prompts import EXPAND_PARAGRAPH_SYSTEM, EXPAND_SYSTEM, PRECIS_SYSTEM, VALIDATE_EXPANSION_SYSTEM
from .validate import get_first_rejected_char, is_english_only
from .steps_ui import (
    build_current_story_html,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
)
from .tree_utils import (
    count_words_in_steps,
    get_all_leaf_paths,
    get_first_leaf_path,
    get_previous_leaf_in_reading_order,
    path_label,
    set_leaf_at_path,
)
from .types import HistoryEntry, Step
from .vetting import vet_consistency, vet_similarity

# Set by do_pause_auto; read by auto-expand thread. Single-process, single-session only.
_auto_stop_requested = False

# Total attempts = 1 initial + MAX_EXPANSION_RETRIES retries before giving up.
MAX_EXPANSION_RETRIES = 10

# Appended to system prompt when LLM response is rejected for non-English characters.
_REJECT_NON_ENGLISH_MESSAGE = (
    "\n\n[REJECTED: Your previous response contained non-English characters. "
    "You MUST write in English only using Latin script (no Chinese, CJK, or other scripts). "
    "Output a completely new response.]"
)


def _is_empty_or_dash(text: str) -> bool:
    """True if paragraph is empty, only whitespace, or just a dash/placeholder (should trigger retry)."""
    t = (text or "").strip()
    return not t or t in ("-", "—", "*—*")


# Phrases that must not be stored as paragraph content (prompt echo); if a segment is only/mostly these, we reject and retry.
_PROMPT_ECHO_PHRASES = (
    "paragraph to expand:",
    "paragraph to expand",
    "previous paragraph (for flow):",
    "previous paragraph (for flow)",
)


def _is_prompt_echo(text: str) -> bool:
    """True if paragraph is empty/dash or is only/mostly prompt echo (e.g. 'Paragraph to expand:'). Triggers retry."""
    if _is_empty_or_dash(text):
        return True
    normalized = " ".join((text or "").split()).lower().strip()
    if not normalized:
        return True
    # Entire content is exactly one of the phrases
    if normalized in _PROMPT_ECHO_PHRASES:
        return True
    # Content is only repetitions of these phrases (with optional punctuation)
    remainder = normalized
    for phrase in _PROMPT_ECHO_PHRASES:
        remainder = remainder.replace(phrase, " ")
    remainder = remainder.replace(":", " ").replace(".", " ").strip()
    if not remainder or len(remainder) <= 2:
        return True
    # Starts with phrase and has very little else (e.g. "Paragraph to expand:\n\nParagraph to expand:")
    for phrase in _PROMPT_ECHO_PHRASES:
        if normalized.startswith(phrase) and len(normalized) <= len(phrase) + 60:
            return True
    return False


def _strip_leading_source_text(
    paragraph: str,
    original: str,
    previous: str | None,
) -> str:
    """
    Remove leading copies of the source or previous paragraph text when the model
    echoes them back into the expansion.

    This keeps stored content to "only the generated paragraphs" instead of
    repeating input context the model saw (original/previous paragraphs).
    """
    p = (paragraph or "").lstrip()
    original_stripped = (original or "").strip()
    previous_stripped = (previous or "").strip()

    # Strip an exact leading copy of the original paragraph, if present.
    if original_stripped and p.startswith(original_stripped):
        p = p[len(original_stripped) :].lstrip()

    # Then strip an exact leading copy of the previous paragraph, if present.
    if previous_stripped and p.startswith(previous_stripped):
        p = p[len(previous_stripped) :].lstrip()

    return p


def _truncate_for_debug(text: str, max_len: int = 200) -> str:
    """Truncate and escape for safe display in debug output."""
    if not text:
        return "(empty)"
    s = (text or "").replace("\r", "\n").replace("\n", " ")  # collapse newlines
    s = " ".join(s.split())  # collapse runs of whitespace
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _complete_english_only(
    prompt: str,
    system: str,
    entries: list[str],
    log_prefix: str,
    max_retries: int = 3,
) -> str:
    """
    Call LLM until response passes is_english_only, or raise after max_retries.
    On reject, appends a log entry to entries (mutates the list) and retries with augmented system prompt; does not send rejected text back.
    """
    current_system = system
    for attempt in range(max_retries):
        raw = complete(prompt, system=current_system)
        if is_english_only(raw):
            return raw
        entries[:] = add_entry(
            entries,
            f"{log_prefix}: response contained non-English characters (attempt {attempt + 1}/{max_retries}); requesting new response.",
            level="error",
        )
        if attempt + 1 >= max_retries:
            snippet = _truncate_for_debug(raw)
            rejected_info = get_first_rejected_char(raw)
            entries[:] = add_entry(
                entries,
                f"{log_prefix}: DEBUG — last rejected response snippet: {snippet}",
                level="error",
            )
            if rejected_info:
                idx, char_info = rejected_info
                entries[:] = add_entry(
                    entries,
                    f"{log_prefix}: DEBUG — first rejected char at index {idx}: {char_info}",
                    level="error",
                )
            raise ValueError(
                f"{log_prefix}: LLM returned text with disallowed characters after {max_retries} attempts. "
                f"Last response snippet: {snippet} "
                "Try again."
            )
        current_system = system + _REJECT_NON_ENGLISH_MESSAGE
    # Unreachable when max_retries > 0; loop always returns or raises above.
    raise ValueError("LLM did not return English-only text within retry limit.")


def _validate_expansion(
    original_text: str,
    p1: str,
    p2: str,
    entries: list[str],
    log_label: str,
) -> bool:
    """
    Validation step: checker responds Yes/No (or true/false). Returns True if accepted or on error (fail open); False if rejected.
    Mutates entries with log lines. Caller should retry expansion when False.
    """
    if not (original_text or "").strip():
        return True
    if not (p1 or "").strip() or not (p2 or "").strip():
        return True
    validate_prompt = (
        "ORIGINAL PARAGRAPH (that was expanded):\n\n"
        f"{original_text.strip()}\n\n"
        "TWO NEW PARAGRAPHS (the expansion):\n\n"
        "Paragraph 1:\n"
        f"{(p1 or '').strip()}\n\n"
        "Paragraph 2:\n"
        f"{(p2 or '').strip()}\n\n"
        "Answer with exactly one word: Yes or No."
    )
    try:
        raw = complete(validate_prompt, system=VALIDATE_EXPANSION_SYSTEM)
    except Exception as e:
        entries[:] = add_entry(entries, f"{log_label}: validation call failed ({e}); treating as accept.", level="error")
        return True
    first = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
    first_upper = first.upper()
    # Accept: Yes, true, 1, or legacy YAY
    if first_upper.startswith("YES") or first_upper == "TRUE" or first_upper == "1" or first_upper.startswith("YAY"):
        entries[:] = add_entry(entries, f"{log_label}: validation accepted.")
        return True
    entries[:] = add_entry(entries, f"{log_label}: validation rejected — writer will retry.", level="error")
    return False


def _expand_next_btn_update(
    steps: list[Step],
    word_limit: int | float | None,
) -> dict[str, Any]:
    """Interactive=True iff there is a leaf and (no limit or current words < limit)."""
    limit = int(word_limit) if word_limit is not None else 0
    if limit > 0 and count_words_in_steps(steps) >= limit:
        return gr.update(interactive=False)
    path, _ = get_first_leaf_path(steps)
    return gr.update(interactive=path is not None)


def do_expand_idea(
    idea: str,
    log_entries: list[str] | None,
    precis_undo: str | None,
) -> tuple[str, str, str, list[str], str | None, dict[str, Any]]:
    """
    Pre-run only: turn rough idea into a story précis and update the Idea textbox.
    Does not add any paragraphs or steps; it only replaces the Idea content with the précis.
    Separate choice before Start. Saves previous idea for Undo.
    Returns (idea_text, progress, log_md, log_entries, new_precis_undo, undo_btn_update).
    """
    entries = log_entries or []

    if not (idea or "").strip():
        entries = add_entry(entries, "Expand idea to précis skipped — Idea empty")
        return (
            idea,
            "Enter a rough idea first.",
            build_log_markdown(entries),
            entries,
            precis_undo,
            gr.update(interactive=precis_undo is not None),
        )

    previous_idea = idea.strip()
    entries = add_entry(entries, f"Expand idea to précis requested ({len(previous_idea)} chars)")
    entries = add_entry(entries, "Calling LLM for précis only (no paragraphs added)…")

    try:
        precis = _complete_english_only(
            previous_idea, PRECIS_SYSTEM, entries, "Expand idea to précis"
        )
        entries = add_entry(entries, "Précis updated in Idea; no paragraphs added.")
        return (
            precis,
            "Only the précis was updated; no paragraphs were added. Review/edit the précis, then press Start when ready. Undo restores the previous idea.",
            build_log_markdown(entries),
            entries,
            previous_idea,
            gr.update(interactive=True),
        )
    except Exception as e:
        entries = add_entry(entries, f"Expand idea to précis failed: {e}", level="error")
        return (
            idea,
            f"Error: {e}",
            build_log_markdown(entries),
            entries,
            precis_undo,
            gr.update(interactive=precis_undo is not None),
        )


def do_undo_precis(
    precis_undo: str | None,
    log_entries: list[str] | None,
) -> tuple[str, str, str, list[str], str | None, dict[str, Any]]:
    """
    Restore Idea text to what it was before the last Expand idea to précis.
    Returns (idea_text, progress, log_md, log_entries, new_precis_undo, undo_btn_update).
    """
    entries = log_entries or []

    if not precis_undo:
        entries = add_entry(entries, "Undo précis skipped — nothing to restore")
        return (
            "",
            "Nothing to undo.",
            build_log_markdown(entries),
            entries,
            None,
            gr.update(interactive=False),
        )

    entries = add_entry(entries, "Undo précis: restored previous idea")
    return (
        precis_undo,
        "Previous idea restored. You can edit and Expand again.",
        build_log_markdown(entries),
        entries,
        None,
        gr.update(interactive=False),
    )


def do_start_write(
    idea: str,
    steps: list[Step] | None,
    log_entries: list[str] | None,
    precis_undo: str | None,
    history: list[HistoryEntry] | None,
    word_limit: int | float | None,
) -> tuple[
    list[Step], str, str, str, str,
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any],
    str, list[str],
    dict[str, Any],
    str | None,
    dict[str, Any],
    list[HistoryEntry],
]:
    """
    Kick off writing: expand précis into two paragraphs, append step, show Working.
    Clears history and précis-undo; disables Expand and Undo.
    Returns (..., working_current_md, working_history_md, working_status_md, ..., history_state).
    """
    steps = steps or []
    entries = log_entries or []
    expand_disabled = gr.update(interactive=False)
    undo_disabled = gr.update(interactive=False)
    empty_history: list[HistoryEntry] = []

    if not (idea or "").strip():
        entries = add_entry(entries, "Start skipped — Idea empty")
        return (
            steps,
            build_current_story_html(steps),
            build_history_markdown(history or []),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history or []),
            build_full_history_text(steps, history or []),
            "",
            "Enter or expand an idea first.",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            build_log_markdown(entries),
            entries,
            expand_disabled,
            _expand_next_btn_update(steps, word_limit),
            None,
            undo_disabled,
            empty_history,
        )

    precis_len = len(idea.strip())
    entries = add_entry(entries, f"Start write requested (précis: {precis_len} chars)")
    entries = add_entry(entries, "Calling LLM…")
    # NOTICE ME PLS!!! <-------------HERE
    try:
        response = _complete_english_only(
            idea.strip(), EXPAND_SYSTEM, entries, "Start write"
        )
        entries = add_entry(entries, "LLM response received; parsing paragraphs")
        p1, p2 = parse_two_paragraphs(response)
        new_steps = steps + [{"paragraph_1": p1, "paragraph_2": p2}]
        try:
            save_story(idea.strip(), new_steps, empty_history)
        except Exception as e:
            entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
        current_md = build_current_story_html(new_steps)
        history_md = build_history_markdown(empty_history)
        output_md = build_output_paragraphs_markdown(new_steps)
        entries = add_entry(entries, f"Start completed — step {len(new_steps)} (two paragraphs) added")
        return (
            new_steps,
            current_md,
            history_md,
            output_md,
            build_output_copy_button_html(new_steps),
            build_full_history_copy_button_html(new_steps, empty_history),
            build_full_history_text(new_steps, empty_history),
            "Story started.",
            f"Done. Step {len(new_steps)}: two paragraphs added. Use **Expand next** or **Run** in Working to expand further. **Run** continues until you press **Pause** or the word count is reached.",
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            build_log_markdown(entries),
            entries,
            expand_disabled,
            _expand_next_btn_update(new_steps, word_limit),
            None,
            undo_disabled,
            empty_history,
        )
    except Exception as e:
        entries = add_entry(entries, f"Start write failed: {e}", level="error")
        return (
            steps,
            build_current_story_html(steps),
            build_history_markdown(history or []),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history or []),
            build_full_history_text(steps, history or []),
            "",
            f"Error: {e}",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            build_log_markdown(entries),
            entries,
            expand_disabled,
            _expand_next_btn_update(steps, word_limit),
            precis_undo,
            undo_disabled,
            empty_history,
        )


def do_expand_next(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
    log_entries: list[str] | None,
    word_limit: int | float | None,
) -> tuple[
    list[Step],
    list[HistoryEntry],
    str,
    str,
    str,
    str,
    str,
    list[str],
    dict[str, Any],
]:
    """
    Expand the first leaf paragraph (depth-first) into two via LLM; update tree and history.
    Stops when story word count is at or above word_limit (from Word count slider).
    Returns (..., log_entries, expand_next_btn_update).
    """
    steps = steps or []
    history = history or []
    entries = log_entries or []

    limit = int(word_limit) if word_limit is not None else 0
    if limit > 0:
        current_words = count_words_in_steps(steps)
        if current_words >= limit:
            entries = add_entry(
                entries,
                f"Expand next: word limit reached ({current_words} >= {limit})",
            )
            return (
                steps,
                history,
                build_current_story_html(steps),
                build_history_markdown(history),
                build_output_paragraphs_markdown(steps),
                build_output_copy_button_html(steps),
                build_full_history_copy_button_html(steps, history),
                build_full_history_text(steps, history),
                f"Word limit reached ({current_words} words). No further expansion.",
                build_log_markdown(entries),
                entries,
                _expand_next_btn_update(steps, word_limit),
            )

    path, text = get_first_leaf_path(steps)
    if path is None or not text:
        entries = add_entry(entries, "Expand next: no leaf paragraph to expand")
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            "No more paragraphs to expand.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
        )

    step_idx, key, indices = path
    path_str = path_label(step_idx, key, indices)
    entries = add_entry(entries, f"Expand next: {path_str} ({len(text)} chars)")
    entries = add_entry(entries, "Calling LLM…")

    previous_text = get_previous_leaf_in_reading_order(steps, path)
    prev_stripped = (previous_text or "").strip()
    if prev_stripped:
        expand_prompt = (
            f"Previous paragraph (for flow):\n\n{prev_stripped}\n\n"
            f"Paragraph to expand:\n\n{text.strip()}"
        )
    else:
        expand_prompt = f"Paragraph to expand:\n\n{text.strip()}"

    last_error: Exception | None = None
    for attempt in range(MAX_EXPANSION_RETRIES + 1):
        try:
            response = _complete_english_only(
                expand_prompt, EXPAND_PARAGRAPH_SYSTEM, entries, "Expand next"
            )
            entries = add_entry(entries, "LLM response received; parsing paragraphs")
            p1, p2 = parse_two_paragraphs(response)
            # Remove any echoed source/previous text at the start of each new paragraph.
            p1 = _strip_leading_source_text(p1, text, previous_text)
            p2 = _strip_leading_source_text(p2, text, previous_text)
            entries = add_entry(entries, f"Parsed: P1={len(p1)} chars, P2={len(p2)} chars")
            if not (p1 or "").strip() or not (p2 or "").strip():
                entries = add_entry(
                    entries,
                    f"Empty paragraph from parser — P1 empty: {not (p1 or '').strip()}, P2 empty: {not (p2 or '').strip()} (raw: {len(response)} chars)",
                    level="error",
                )
                snippet = (response or "")[:400].replace("\n", " ")
                entries = add_entry(entries, f"Raw response snippet: {snippet}…", level="error")
            if _is_empty_or_dash(p1) or _is_empty_or_dash(p2):
                raise ValueError("Empty or invalid paragraph (P1 or P2 empty/dash); retrying.")
            if _is_prompt_echo(p1) or _is_prompt_echo(p2):
                raise ValueError("Prompt echo or invalid content (P1 or P2); retrying.")
            if not _validate_expansion(text, p1, p2, entries, "Expand next"):
                entries = add_entry(entries, "Expand next: writer retry (validation rejected).")
                retry_prompt = expand_prompt + "\n\n[Your previous expansion failed validation (flow/consistency). Please try again: ensure the two paragraphs faithfully expand the paragraph above and are in chronological order.]"
                try:
                    response = _complete_english_only(retry_prompt, EXPAND_PARAGRAPH_SYSTEM, entries, "Expand next retry")
                    r1, r2 = parse_two_paragraphs(response)
                    r1 = _strip_leading_source_text(r1, text, previous_text)
                    r2 = _strip_leading_source_text(r2, text, previous_text)
                    if (
                        (r1 or "").strip()
                        and (r2 or "").strip()
                        and not _is_empty_or_dash(r1)
                        and not _is_empty_or_dash(r2)
                        and not _is_prompt_echo(r1)
                        and not _is_prompt_echo(r2)
                    ):
                        p1, p2 = r1, r2
                        entries = add_entry(entries, f"Retry parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                    else:
                        entries = add_entry(entries, "Retry returned empty or single paragraph; keeping first expansion.", level="error")
                except Exception as retry_err:
                    entries = add_entry(entries, f"Retry failed ({retry_err}); keeping first expansion.", level="error")
            new_steps = set_leaf_at_path(steps, path, p1, p2)
            entry: HistoryEntry = {
                "path_label": path_str,
                "original": text,
                "left": p1,
                "right": p2,
                "step_index": step_idx,
                "paragraph_key": key,
                "indices": list(indices),
            }
            new_history = history + [entry]
            try:
                precis, _, _ = load_story()
                save_story(precis, new_steps, new_history)
            except Exception as e:
                entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
            # TODO: surface in UI when implemented
            _consistency_issues = vet_consistency(new_steps)
            _similarity_issues = vet_similarity(new_steps)
            entries = add_entry(entries, f"Expanded — {path_str}")
            return (
                new_steps,
                new_history,
                build_current_story_html(new_steps),
                build_history_markdown(new_history),
                build_output_paragraphs_markdown(new_steps),
                build_output_copy_button_html(new_steps),
                build_full_history_copy_button_html(new_steps, new_history),
                build_full_history_text(new_steps, new_history),
                f"Expanded {path_str} into two paragraphs.",
                build_log_markdown(entries),
                entries,
                _expand_next_btn_update(new_steps, word_limit),
            )
        except Exception as e:
            last_error = e
            entries = add_entry(
                entries,
                f"Expand next failed (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1}): {e}",
                level="error",
            )
            if attempt >= MAX_EXPANSION_RETRIES:
                return (
                    steps,
                    history,
                    build_current_story_html(steps),
                    build_history_markdown(history),
                    build_output_paragraphs_markdown(steps),
                    build_output_copy_button_html(steps),
                    build_full_history_copy_button_html(steps, history),
                    build_full_history_text(steps, history),
                    f"Error: {e}",
                    build_log_markdown(entries),
                    entries,
                    _expand_next_btn_update(steps, word_limit),
                )
    err = last_error or ValueError("Expand next failed after retries")
    entries = add_entry(entries, f"Expand next failed: {err}", level="error")
    return (
        steps,
        history,
        build_current_story_html(steps),
        build_history_markdown(history),
        build_output_paragraphs_markdown(steps),
        build_output_copy_button_html(steps),
        build_full_history_copy_button_html(steps, history),
        build_full_history_text(steps, history),
        f"Error: {err}",
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(steps, word_limit),
    )


def do_expand_round(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
    log_entries: list[str] | None,
    word_limit: int | float | None,
) -> tuple[
    list[Step],
    list[HistoryEntry],
    str,
    str,
    str,
    str,
    list[str],
    dict[str, Any],
]:
    """
    Expand every current leaf into two (one round). Progression: 2 → 4 → 8 → 16 …
    Stops when at/over word_limit or no leaves. Same return shape as do_expand_next.
    """
    steps = steps or []
    history = history or []
    entries = log_entries or []

    limit = int(word_limit) if word_limit is not None else 0
    if limit > 0 and count_words_in_steps(steps) >= limit:
        entries = add_entry(
            entries,
            f"Expand round: word limit reached ({count_words_in_steps(steps)} >= {limit})",
        )
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            f"Word limit reached. No further expansion.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
        )

    all_leaves = get_all_leaf_paths(steps)
    if not all_leaves:
        entries = add_entry(entries, "Expand round: no leaf paragraphs to expand")
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            "No more paragraphs to expand.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
        )

    entries = add_entry(
        entries,
        f"Expand round: splitting {len(all_leaves)} paragraph(s) → {len(all_leaves) * 2}",
    )
    current_steps = steps
    new_history = list(history)
    status_parts: list[str] = []
    round_stop_error: str | None = None  # set when we break due to exception so status shows it

    for path, text in all_leaves:
        if limit > 0 and count_words_in_steps(current_steps) >= limit:
            entries = add_entry(entries, "Expand round: word limit hit mid-round; stopping")
            break
        step_idx, key, indices = path
        path_str = path_label(step_idx, key, indices)
        entries = add_entry(entries, f"  {path_str} ({len(text)} chars)…")
        previous_text = get_previous_leaf_in_reading_order(current_steps, path)
        prev_stripped = (previous_text or "").strip()
        if prev_stripped:
            expand_prompt = (
                f"Previous paragraph (for flow):\n\n{prev_stripped}\n\n"
                f"Paragraph to expand:\n\n{text.strip()}"
            )
        else:
            expand_prompt = f"Paragraph to expand:\n\n{text.strip()}"
        path_succeeded = False
        for attempt in range(MAX_EXPANSION_RETRIES + 1):
            try:
                response = _complete_english_only(
                    expand_prompt, EXPAND_PARAGRAPH_SYSTEM, entries, "Expand round"
                )
                p1, p2 = parse_two_paragraphs(response)
                p1 = _strip_leading_source_text(p1, text, previous_text)
                p2 = _strip_leading_source_text(p2, text, previous_text)
                entries = add_entry(entries, f"  {path_str} parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                if not (p1 or "").strip() or not (p2 or "").strip():
                    entries = add_entry(
                        entries,
                        f"  {path_str} WARNING: empty P1 or P2 — P1 empty: {not (p1 or '').strip()}, P2 empty: {not (p2 or '').strip()} (raw: {len(response)} chars)",
                        level="error",
                    )
                    snippet = (response or "")[:350].replace("\n", " ")
                    entries = add_entry(entries, f"  Raw snippet: {snippet}…", level="error")
                if _is_empty_or_dash(p1) or _is_empty_or_dash(p2):
                    raise ValueError("Empty or invalid paragraph (P1 or P2 empty/dash); retrying.")
                if _is_prompt_echo(p1) or _is_prompt_echo(p2):
                    raise ValueError("Prompt echo or invalid content (P1 or P2); retrying.")
                if not _validate_expansion(text, p1, p2, entries, f"  {path_str}"):
                    entries = add_entry(entries, f"  {path_str}: writer retry (validation rejected).")
                    retry_prompt = expand_prompt + "\n\n[Your previous expansion failed validation (flow/consistency). Please try again: ensure the two paragraphs faithfully expand the paragraph above and are in chronological order.]"
                    try:
                        response = _complete_english_only(retry_prompt, EXPAND_PARAGRAPH_SYSTEM, entries, "Expand round retry")
                        r1, r2 = parse_two_paragraphs(response)
                        r1 = _strip_leading_source_text(r1, text, previous_text)
                        r2 = _strip_leading_source_text(r2, text, previous_text)
                        if (
                            (r1 or "").strip()
                            and (r2 or "").strip()
                            and not _is_empty_or_dash(r1)
                            and not _is_empty_or_dash(r2)
                            and not _is_prompt_echo(r1)
                            and not _is_prompt_echo(r2)
                        ):
                            p1, p2 = r1, r2
                            entries = add_entry(entries, f"  {path_str} retry parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                        else:
                            entries = add_entry(entries, f"  {path_str} retry empty; keeping first expansion.", level="error")
                    except Exception as retry_err:
                        entries = add_entry(entries, f"  {path_str} retry failed ({retry_err}); keeping first expansion.", level="error")
                current_steps = set_leaf_at_path(current_steps, path, p1, p2)
                entry: HistoryEntry = {
                    "path_label": path_str,
                    "original": text,
                    "left": p1,
                    "right": p2,
                    "step_index": step_idx,
                    "paragraph_key": key,
                    "indices": list(indices),
                }
                new_history.append(entry)
                status_parts.append(path_str)
                path_succeeded = True
                break
            except Exception as e:
                entries = add_entry(
                    entries,
                    f"  {path_str} failed (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1}): {e}",
                    level="error",
                )
                if attempt >= MAX_EXPANSION_RETRIES:
                    round_stop_error = str(e)
                    break
        if not path_succeeded:
            break

    try:
        precis, _, _ = load_story()
        save_story(precis, current_steps, new_history)
    except Exception as e:
        entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
    actual_leaves = len(get_all_leaf_paths(current_steps))
    if len(status_parts) == len(all_leaves):
        status_msg = f"Round: {len(all_leaves)} → {actual_leaves} paragraphs."
    elif round_stop_error:
        status_msg = f"Round: {len(all_leaves)} → {actual_leaves} paragraphs (stopped: error — {round_stop_error})."
    else:
        status_msg = f"Round: {len(all_leaves)} → {actual_leaves} paragraphs (stopped: word limit)."
    entries = add_entry(entries, f"Round done — expanded: {', '.join(status_parts) or 'none'}")
    return (
        current_steps,
        new_history,
        build_current_story_html(current_steps),
        build_history_markdown(new_history),
        build_output_paragraphs_markdown(current_steps),
        build_output_copy_button_html(current_steps),
        build_full_history_copy_button_html(current_steps, new_history),
        build_full_history_text(current_steps, new_history),
        status_msg,
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(current_steps, word_limit),
    )


def _auto_expand_worker(
    steps: list[Step],
    history: list[HistoryEntry],
    entries: list[str],
    word_limit: int | float | None,
    debug_pause: bool,
    result_queue: queue.Queue,
) -> None:
    """Run expand-round in a loop (2→4→8→…) until stop requested, word limit, or no leaf. Puts 13-tuples (incl. output_md, run_btn + Write-tab updates) then 'done'. When debug_pause is True, sleeps 3s after each expansion so output can be seen."""
    global _auto_stop_requested
    current_steps = steps
    current_history = history
    current_entries = entries
    limit = int(word_limit) if word_limit is not None else 0
    run_btn_disable = gr.update(interactive=False)
    run_btn_enable = gr.update(interactive=True)
    start_btn_disable = gr.update(interactive=False)
    start_btn_enable = gr.update(interactive=True)
    expand_undo_disable = gr.update(interactive=False)
    expand_undo_enable = gr.update(interactive=True)
    write_btns_enable = (start_btn_enable, expand_undo_enable, expand_undo_enable)
    write_btns_disable = (start_btn_disable, expand_undo_disable, expand_undo_disable)
    while True:
        if _auto_stop_requested:
            result_queue.put(
                (
                    current_steps,
                    current_history,
                    build_current_story_html(current_steps),
                    build_history_markdown(current_history),
                    build_output_paragraphs_markdown(current_steps),
                    build_output_copy_button_html(current_steps),
                    build_full_history_copy_button_html(current_steps, current_history),
                    build_full_history_text(current_steps, current_history),
                    "Paused.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                )
            )
            result_queue.put("done")
            return
        if limit > 0 and count_words_in_steps(current_steps) >= limit:
            result_queue.put(
                (
                    current_steps,
                    current_history,
                    build_current_story_html(current_steps),
                    build_history_markdown(current_history),
                    build_output_paragraphs_markdown(current_steps),
                    build_output_copy_button_html(current_steps),
                    build_full_history_copy_button_html(current_steps, current_history),
                    build_full_history_text(current_steps, current_history),
                    "Word limit reached. Auto stopped.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                )
            )
            result_queue.put("done")
            return
        all_leaves = get_all_leaf_paths(current_steps)
        if not all_leaves:
            result_queue.put(
                (
                    current_steps,
                    current_history,
                    build_current_story_html(current_steps),
                    build_history_markdown(current_history),
                    build_output_paragraphs_markdown(current_steps),
                    build_output_copy_button_html(current_steps),
                    build_full_history_copy_button_html(current_steps, current_history),
                    build_full_history_text(current_steps, current_history),
                    "No more paragraphs. Auto stopped.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                )
            )
            result_queue.put("done")
            return
        result = do_expand_round(
            current_steps,
            current_history,
            current_entries,
            word_limit,
        )
        (
            current_steps,
            current_history,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            current_entries,
            _,
        ) = result
        result_queue.put((*result, run_btn_disable, *write_btns_disable))
        if debug_pause:
            time.sleep(3)
    # Loop exits only via return above; no code after loop.


def do_auto_expand_next(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
    log_entries: list[str] | None,
    word_limit: int | float | None,
    debug_pause: bool = False,
) -> Iterator[
    tuple[
        list[Step],
        list[HistoryEntry],
        str,
        str,
        str,
        str,
        str,
        list[str],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]
]:
    """
    Generator: run expand_round in a background thread until word limit, no leaf, or Pause.
    Yields 13-tuples: current_md, history_md, output_md, status_md, log_md, entries, expand_next_btn, run_btn, start_btn, expand_btn, undo_btn. When debug_pause is True, worker sleeps 3s after each expansion.
    """
    global _auto_stop_requested
    _auto_stop_requested = False
    steps = steps or []
    history = history or []
    entries = add_entry(log_entries or [], "Auto expand started.")
    result_queue: queue.Queue = queue.Queue()
    thread = threading.Thread(
        target=_auto_expand_worker,
        args=(steps, history, entries, word_limit, debug_pause, result_queue),
        daemon=True,
    )
    thread.start()
    yield (
        steps,
        history,
        build_current_story_html(steps),
        build_history_markdown(history),
        build_output_paragraphs_markdown(steps),
        build_output_copy_button_html(steps),
        build_full_history_copy_button_html(steps, history),
        build_full_history_text(steps, history),
        "Running…",
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(steps, word_limit),
        gr.update(interactive=False),   # run_btn
        gr.update(interactive=False),   # start_btn
        gr.update(interactive=False),   # expand_btn
        gr.update(interactive=False),   # undo_btn
    )
    while True:
        item = result_queue.get()
        if item == "done":
            break
        yield item


def do_pause_auto() -> None:
    """Set flag so the auto-expand thread stops after the current expansion."""
    global _auto_stop_requested
    _auto_stop_requested = True
