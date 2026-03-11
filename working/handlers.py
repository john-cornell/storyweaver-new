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

import logging
import queue
import threading
import time
from typing import Any, Callable, Iterator

import gradio as gr

logger = logging.getLogger(__name__)

from config import ExpansionConfig, HumanizeConfig
from db import load_erl, load_story, save_erl, save_story
from llm import complete, log_llm_outcome, LLMTaskType
from log import add_entry, build_log_markdown

from .beat_extractor import extract_beats
from .classifier import classify_block
from .erl import build_erl_constraint_injections, empty_erl, erl_to_json
from .erl_extractor import extract_state_updates
from .erl_init import initialize_erl
from .erl_ui import build_erl_tab_content
from .parsing import parse_two_paragraphs, split_prose_into_two_paragraphs
from .prompts import (
    BEAT_OUTLINE_SYSTEM,
    EXPAND_SYSTEM,
    HUMANIZE_SYSTEM,
    PRECIS_FROM_BEATS_SYSTEM,
    PRECIS_SYSTEM,
    TITLE_FROM_PRECIS_SYSTEM,
    VALIDATE_EXPANSION_SYSTEM,
    get_scene_expand_system,
    get_scene_reifier_system,
    get_transition_expand_system,
)
from .banned import replace_ai_phrases, replace_emdash
from .validate import contains_banned_chars, get_first_banned_char, get_first_rejected_char, is_english_only
from .steps_ui import (
    build_current_story_html,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
    EMPTY_STORY_PLACEHOLDER,
)
from .tree_utils import (
    count_words_in_steps,
    get_all_leaf_paths,
    get_first_leaf_path,
    get_previous_leaf_in_reading_order,
    is_first_leaf_in_reading_order,
    path_label,
    set_leaf_at_path,
)
from .types import HistoryEntry, Step
from .vetting import vet_consistency, vet_similarity

# Set by do_pause_auto; read by auto-expand thread. Single-process, single-session only.
_auto_stop_requested = False

# Total attempts = 1 initial + MAX_EXPANSION_RETRIES retries before giving up.
MAX_EXPANSION_RETRIES = 10

# Marker in status_msg when round had recoverable error; worker uses this to detect auto-continue path.
_RECOVERABLE_ERROR_MARKER = "recoverable error"

# Max consecutive recoverable failures before treating as fatal (prevents infinite loop on same path).
_MAX_CONSECUTIVE_RECOVERABLE = 3

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


def _is_truncated(text: str) -> bool:
    """True if paragraph appears cut off (does not end with sentence-ending punctuation)."""
    t = (text or "").strip()
    if not t:
        return True
    last = t[-1]
    return last not in ".!?\"')\u201d\u2014"  # period, !, ?, ", ', ), ", —


def _is_too_short(original: str, p1: str, p2: str) -> bool:
    """True if combined expansion is less than 60% of source length (indicates plot loss)."""
    orig_len = len((original or "").strip())
    if orig_len <= 0:
        return False
    combined = len((p1 or "").strip()) + len((p2 or "").strip())
    return combined < 0.6 * orig_len


def _is_fatal_error(e: Exception) -> bool:
    """
    True if error is fatal (API/DB down, connection/timeout); False if recoverable (parse/validation).
    Fatal errors mean we cannot make progress; recoverable are LLM output quality issues.
    """
    if isinstance(e, (ConnectionError, TimeoutError, OSError, RuntimeError)):
        return True
    mod = type(e).__module__
    if (
        mod.startswith("anthropic")
        or mod.startswith("openai")
        or "google.api_core" in mod
        or "google.genai" in mod
        or mod.startswith("db")
    ):
        return True
    return False


def _generate_story_name(precis: str) -> str:
    """
    Generate a short title from précis via LLM. On failure, fall back to first 50 chars of first line.
    """
    precis = (precis or "").strip()
    if not precis:
        return "Untitled"
    try:
        result = complete(precis, system=TITLE_FROM_PRECIS_SYSTEM, purpose="title_from_precis", task_type=LLMTaskType.PLAN)
        raw = result.text
        title = (raw or "").strip()
        # Take first line, remove quotes, limit length
        if title:
            first_line = title.split("\n")[0].strip().strip("'\"")
            if first_line:
                log_llm_outcome(result.call_id, True)
                return first_line[:80] if len(first_line) > 80 else first_line
        log_llm_outcome(result.call_id, False, "empty or unusable")
    except Exception as e:
        logger.warning("Title generation failed, using heuristic: %s", e)
    # Fallback: first 50 chars of first non-empty line
    for line in precis.split("\n"):
        line = line.strip()
        if line:
            return (line[:50] + "…") if len(line) > 50 else line
    return "Untitled"


def _rewrite_precis_from_beats(beats_text: str, entries: list[str]) -> str:
    """
    Rewrite beat outline into a narrative précis. Returns the rewritten précis.
    On failure, returns the original text. Mutates entries with log lines.
    """
    beats_text = (beats_text or "").strip()
    if not beats_text:
        return beats_text
    try:
        entries[:] = add_entry(entries, "Rewriting précis from beats (background)…")
        result = complete(beats_text, system=PRECIS_FROM_BEATS_SYSTEM, purpose="precis_from_beats", task_type=LLMTaskType.PLAN)
        raw = result.text
        precis = (raw or "").strip()
        if precis:
            log_llm_outcome(result.call_id, True)
            if _should_humanize("precis"):
                precis = _humanize_prose(precis, entries, "Précis")
            entries[:] = add_entry(entries, "Précis rewritten.")
            return precis
        log_llm_outcome(result.call_id, False, "empty")
        entries[:] = add_entry(entries, "Précis rewrite returned empty; using original.", level="error")
        return beats_text
    except Exception as e:
        logger.warning("Précis rewrite from beats failed: %s", e)
        entries[:] = add_entry(entries, f"Précis rewrite failed ({e}); using original.", level="error")
        return beats_text


# Phrases that must not be stored as paragraph content (prompt echo); if a segment is only/mostly these, we reject and retry.
_PROMPT_ECHO_PHRASES = (
    "paragraph to expand:",
    "paragraph to expand",
    "previous paragraph (for continuity of tone only — do not reuse its events, imagery, or setting):",
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


def _should_humanize(scope_type: str) -> bool:
    """True if humanization is enabled and scope includes the given type (expansion, precis, interactive)."""
    cfg = HumanizeConfig.from_env()
    if not cfg.humanize_output:
        return False
    if cfg.humanize_scope == "all":
        return True
    if cfg.humanize_scope == "expansion_and_precis" and scope_type in ("expansion", "precis"):
        return True
    if cfg.humanize_scope == "expansion_only" and scope_type == "expansion":
        return True
    return False


def _humanize_prose(text: str, entries: list[str] | None, log_prefix: str) -> str:
    """
    Rewrite prose through humanization LLM pass. Returns humanized text, or original on failure.
    Mutates entries with log lines when entries is provided.
    """
    text = (text or "").strip()
    if not text:
        return text
    text = replace_ai_phrases(text)  # cheap pre-pass before LLM
    try:
        result = complete(text, system=HUMANIZE_SYSTEM, purpose="humanize_prose", task_type=LLMTaskType.WRITE)
        out = (result.text or "").strip()
        if out:
            log_llm_outcome(result.call_id, True)
            if entries is not None:
                entries[:] = add_entry(entries, f"{log_prefix}: humanized.")
            return replace_emdash(out)
        log_llm_outcome(result.call_id, False, "empty")
    except Exception as e:
        logger.warning("Humanization failed: %s", e)
        if entries is not None:
            entries[:] = add_entry(entries, f"{log_prefix}: humanization failed ({e}); using original.", level="error")
    return text


def humanize_prose_if_enabled(
    text: str,
    scope_type: str,
    entries: list[str] | None = None,
    log_prefix: str = "Humanize",
) -> str:
    """If humanization is enabled for scope_type, rewrite text; else return as-is. For use by interactive handlers."""
    if not _should_humanize(scope_type):
        return text
    return _humanize_prose(text, entries, log_prefix)


def _complete_english_only(
    prompt: str,
    system: str,
    entries: list[str],
    log_prefix: str,
    max_retries: int = 3,
    task_type: LLMTaskType = LLMTaskType.WRITE,
) -> str:
    """
    Call LLM until response passes is_english_only, or raise after max_retries.
    On reject, appends a log entry to entries (mutates the list) and retries with augmented system prompt; does not send rejected text back.
    """
    current_system = system
    purpose = log_prefix.lower().replace(" ", "_").replace("—", "_").replace("é", "e")
    for attempt in range(max_retries):
        if attempt > 0:
            logger.debug("%s: retry attempt %d/%d", log_prefix, attempt + 1, max_retries)
        result = complete(prompt, system=current_system, purpose=purpose, task_type=task_type)
        raw = replace_emdash(result.text)
        if _should_humanize("expansion"):
            raw = _humanize_prose(raw, entries, log_prefix)
        if is_english_only(raw):
            log_llm_outcome(result.call_id, True)
            return raw
        snippet = _truncate_for_debug(raw)
        rejected_info = get_first_rejected_char(raw)
        reason_detail = ""
        if rejected_info:
            idx, char_info = rejected_info
            reason_detail = f" first_rejected={char_info} at index {idx}"
        log_llm_outcome(result.call_id, False, f"non_english{reason_detail}")
        entries[:] = add_entry(
            entries,
            f"{log_prefix}: response contained non-English characters (attempt {attempt + 1}/{max_retries}); requesting new response.",
            level="error",
        )
        entries[:] = add_entry(
            entries,
            f"{log_prefix}: REJECTED snippet: {snippet}",
            level="error",
        )
        if rejected_info:
            idx, char_info = rejected_info
            entries[:] = add_entry(
                entries,
                f"{log_prefix}: first rejected char at index {idx}: {char_info}",
                level="error",
            )
        if attempt + 1 >= max_retries:
            raise ValueError(
                f"{log_prefix}: LLM returned text with disallowed characters after {max_retries} attempts. "
                f"Last response snippet: {snippet} "
                "Try again."
            )
        current_system = system + _REJECT_NON_ENGLISH_MESSAGE
    # Unreachable when max_retries > 0; loop always returns or raises above.
    raise ValueError("LLM did not return English-only text within retry limit.")


BANNED_CHARS_RETRY_HINT = (
    "\n\n[Do not use em dash. Use a regular hyphen (-) or \" - \" (space-hyphen-space) instead. "
    "ONLY em dash is banned. Keep apostrophes in contractions (don't, it's, we're); "
    "never replace apostrophes with space-hyphen-space.]"
)


def _validate_expansion(
    original_text: str,
    p1: str,
    p2: str,
    entries: list[str],
    log_label: str,
) -> bool:
    """
    Validation step: checker responds Yes/No (or true/false). On No, may include a
    second line "Reason: <explanation>". Returns True if accepted or on error (fail open);
    False if rejected. Mutates entries with log lines. Caller should retry expansion when False.
    """
    if not (original_text or "").strip():
        return True
    if not (p1 or "").strip() or not (p2 or "").strip():
        return True
    if contains_banned_chars(p1) or contains_banned_chars(p2):
        banned_info = get_first_banned_char(p1) or get_first_banned_char(p2)
        info_str = f" ({banned_info[1]})" if banned_info else ""
        entries[:] = add_entry(
            entries,
            f"{log_label}: banned character in output{info_str} — writer will retry.",
            level="error",
        )
        return False
    validate_prompt = (
        "ORIGINAL PARAGRAPH (that was expanded):\n\n"
        f"{original_text.strip()}\n\n"
        "TWO NEW PARAGRAPHS (the expansion):\n\n"
        "Paragraph 1:\n"
        f"{(p1 or '').strip()}\n\n"
        "Paragraph 2:\n"
        f"{(p2 or '').strip()}\n\n"
        "Answer: Yes or No. If No, add a second line starting with 'Reason:' and a brief explanation."
    )
    try:
        result = complete(validate_prompt, system=VALIDATE_EXPANSION_SYSTEM, purpose="validate_expansion", task_type=LLMTaskType.PLAN)
        raw = result.text
    except Exception as e:
        entries[:] = add_entry(entries, f"{log_label}: validation call failed ({e}); treating as accept.", level="error")
        return True
    lines = [ln.strip() for ln in (raw or "").strip().splitlines() if ln.strip()]
    first = lines[0] if lines else ""
    first_upper = first.upper()
    logger.debug("%s: validation raw=%s", log_label, (first_upper[:80] + "…") if len(first_upper) > 80 else first_upper)
    # Accept: Yes, true, 1, or legacy YAY
    if first_upper.startswith("YES") or first_upper == "TRUE" or first_upper == "1" or first_upper.startswith("YAY"):
        log_llm_outcome(result.call_id, True)
        entries[:] = add_entry(entries, f"{log_label}: validation accepted.")
        logger.debug("%s: validation accepted", log_label)
        return True
    # Extract reason from second line if present (e.g. "Reason: temporal leakage")
    reason = ""
    for ln in lines[1:]:
        if ln.upper().startswith("REASON:"):
            raw_reason = ln[7:].strip().replace("\n", " ")
            reason = raw_reason[:300] + ("…" if len(raw_reason) > 300 else "")
            break
    reason_str = f" — {reason}" if reason else ""
    log_llm_outcome(result.call_id, False, "validation_rejected")
    entries[:] = add_entry(entries, f"{log_label}: validation rejected{reason_str} — writer will retry.", level="error")
    logger.debug("%s: validation rejected%s", log_label, reason_str)
    return False


def _run_fallback_scene_expand(
    text: str,
    previous_text: str | None,
    current_erl: dict[str, Any],
    entries: list[str],
    log_prefix: str,
) -> tuple[str, str, dict[str, Any]]:
    """Single-call SCENE expand when Micro-Beat is skipped (no beats, exceeds max, or all empty)."""
    expand_prompt = (
        f"Previous paragraph (for continuity of tone only — do NOT reuse its events, imagery, or setting):\n\n{(previous_text or '').strip()}\n\nParagraph to expand:\n\n{text.strip()}"
        if (previous_text or "").strip()
        else f"Paragraph to expand:\n\n{text.strip()}"
    )
    erl_json = erl_to_json(current_erl)
    expand_system = get_scene_expand_system(erl_json)
    response = _complete_english_only(expand_prompt, expand_system, entries, log_prefix)
    p1, p2 = parse_two_paragraphs(response)
    p1 = _strip_leading_source_text(p1, text, previous_text)
    p2 = _strip_leading_source_text(p2, text, previous_text)
    combined = f"{p1}\n\n{p2}"
    updated_erl = extract_state_updates(combined, current_erl)
    return (p1, p2, updated_erl)


def _run_micro_beat_expansion(
    text: str,
    previous_text: str | None,
    current_erl: dict[str, Any],
    entries: list[str],
    log_prefix: str,
) -> tuple[str, str, dict[str, Any]]:
    """
    Micro-Beat Protocol: decompose into beats, reify each with ERL constraints, combine into 2 paragraphs.
    Falls back to single-call SCENE expand if beat extractor returns no beats or exceeds max_beats.
    Returns (p1, p2, updated_erl).
    """
    beats = extract_beats(text)
    logger.debug("%s: beats extracted=%d", log_prefix, len(beats))
    if not beats:
        entries[:] = add_entry(entries, f"{log_prefix}: no beats extracted; using fallback SCENE expand")
        return _run_fallback_scene_expand(text, previous_text, current_erl, entries, log_prefix)

    max_beats = ExpansionConfig.from_env().max_beats
    if len(beats) > max_beats:
        entries[:] = add_entry(
            entries,
            f"{log_prefix}: {len(beats)} beats exceeds max {max_beats}; using fallback SCENE expand",
        )
        return _run_fallback_scene_expand(text, previous_text, current_erl, entries, log_prefix)

    entries[:] = add_entry(entries, f"{log_prefix}: Micro-Beat Protocol — {len(beats)} beats")
    prose_chunks: list[str] = []
    working_erl = current_erl
    prev_stripped = (previous_text or "").strip()

    for i, beat in enumerate(beats):
        logger.debug("%s: beat %d/%d (len=%d)", log_prefix, i + 1, len(beats), len(beat))
        constraint_injections = build_erl_constraint_injections(working_erl)
        erl_json = erl_to_json(working_erl)
        reifier_system = get_scene_reifier_system(erl_json, constraint_injections)
        beat_prompt = (
            f"Previous paragraph (for continuity of tone only — do NOT reuse its events):\n\n{prev_stripped}\n\nBeat to expand:\n\n{beat}"
            if i == 0 and prev_stripped
            else f"Beat to expand:\n\n{beat}"
        )
        beat_prose = _complete_english_only(beat_prompt, reifier_system, entries, f"{log_prefix} beat {i + 1}")
        beat_prose = (beat_prose or "").strip()
        for prefix in ("Beat to expand:", "beat to expand:"):
            if beat_prose.startswith(prefix):
                beat_prose = beat_prose[len(prefix) :].strip()
                break
        if beat_prose:
            prose_chunks.append(beat_prose)
            working_erl = extract_state_updates(beat_prose, working_erl)
        prev_stripped = beat_prose  # next beat gets continuity from this one

    if not prose_chunks:
        logger.debug("%s: all beats empty; using fallback SCENE expand", log_prefix)
        entries[:] = add_entry(entries, f"{log_prefix}: all beats empty; using fallback SCENE expand", level="error")
        return _run_fallback_scene_expand(text, previous_text, current_erl, entries, log_prefix)

    combined_prose = "\n\n".join(prose_chunks)
    p1, p2 = split_prose_into_two_paragraphs(combined_prose)
    p1 = _strip_leading_source_text(p1, text, previous_text)
    p2 = _strip_leading_source_text(p2, text, previous_text)
    return (p1, p2, working_erl)


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
    content_is_beats: bool,
) -> tuple[str, str, str, list[str], str | None, dict[str, Any], bool]:
    """
    Pre-run only: turn rough idea into a story précis and update the Idea textbox.
    Does not add any paragraphs or steps; it only replaces the Idea content with the précis.
    Separate choice before Start. Saves previous idea for Undo.
    Returns (idea_text, progress, log_md, log_entries, new_precis_undo, undo_btn_update, content_is_beats).
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
            content_is_beats,
        )

    previous_idea = idea.strip()
    entries = add_entry(entries, f"Expand idea to précis requested ({len(previous_idea)} chars)")
    entries = add_entry(entries, "Calling LLM for précis only (no paragraphs added)…")

    try:
        precis = _complete_english_only(
            previous_idea, PRECIS_SYSTEM, entries, "Expand idea to précis", task_type=LLMTaskType.PLAN
        )
        entries = add_entry(entries, "Précis updated in Idea; no paragraphs added.")
        return (
            precis,
            "Only the précis was updated; no paragraphs were added. Review/edit the précis, then press Start when ready. Undo restores the previous idea.",
            build_log_markdown(entries),
            entries,
            previous_idea,
            gr.update(interactive=True),
            False,
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
            content_is_beats,
        )


def do_undo_precis(
    precis_undo: str | None,
    log_entries: list[str] | None,
    content_is_beats: bool,
) -> tuple[str, str, str, list[str], str | None, dict[str, Any], bool]:
    """
    Restore Idea text to what it was before the last Expand idea to précis or Generate beat outline.
    Returns (idea_text, progress, log_md, log_entries, new_precis_undo, undo_btn_update, content_is_beats).
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
            False,
        )

    entries = add_entry(entries, "Undo précis: restored previous idea")
    return (
        precis_undo,
        "Previous idea restored. You can edit and Expand again.",
        build_log_markdown(entries),
        entries,
        None,
        gr.update(interactive=False),
        False,
    )


def do_generate_beat_outline(
    idea: str,
    log_entries: list[str] | None,
    precis_undo: str | None,
    content_is_beats: bool,
) -> tuple[str, str, str, list[str], str | None, dict[str, Any], bool]:
    """
    Two-step: (1) précis → beats, (2) beats → narrative précis. Updates Idea with the précis.
    Saves previous content to precis_undo_state so Undo restores it.
    Returns (idea_text, progress, log_md, log_entries, new_precis_undo, undo_btn_update, content_is_beats).
    """
    entries = log_entries or []

    if not (idea or "").strip():
        entries = add_entry(entries, "Generate beat outline skipped — Idea empty")
        return (
            idea,
            "Enter or expand a précis first.",
            build_log_markdown(entries),
            entries,
            precis_undo,
            gr.update(interactive=precis_undo is not None),
            content_is_beats,
        )

    previous_content = idea.strip()
    entries = add_entry(entries, f"Generate beat outline requested ({len(previous_content)} chars)")
    entries = add_entry(entries, "Calling LLM for beat outline…")

    try:
        outline = _complete_english_only(
            previous_content, BEAT_OUTLINE_SYSTEM, entries, "Generate beat outline", task_type=LLMTaskType.PLAN
        )
        outline = (outline or "").strip()
        if not outline:
            entries = add_entry(entries, "Generate beat outline: empty response; keeping previous content.", level="error")
            return (
                idea,
                "LLM returned empty outline.",
                build_log_markdown(entries),
                entries,
                precis_undo,
                gr.update(interactive=precis_undo is not None),
                content_is_beats,
            )
        entries = add_entry(entries, "Beat outline generated. Converting to précis…")
        precis = _rewrite_precis_from_beats(outline, entries)
        is_beats_format = "## Beginning" in precis or "## Middle" in precis or "## End" in precis
        if precis and precis.strip() and not is_beats_format:
            entries = add_entry(entries, "Précis refined from beat outline.")
            return (
                precis.strip(),
                "Précis refined from beat outline. Review/edit, then Start when ready.",
                build_log_markdown(entries),
                entries,
                previous_content,
                gr.update(interactive=True),
                False,
            )
        entries = add_entry(entries, "Précis rewrite empty; keeping beats. Start will retry rewrite.", level="error")
        return (
            outline,
            "Beats generated but précis rewrite failed. Start will retry. Or press Regenerate.",
            build_log_markdown(entries),
            entries,
            previous_content,
            gr.update(interactive=True),
            True,
        )
    except Exception as e:
        entries = add_entry(entries, f"Generate beat outline failed: {e}", level="error")
        return (
            idea,
            f"Error: {e}",
            build_log_markdown(entries),
            entries,
            precis_undo,
            gr.update(interactive=precis_undo is not None),
            content_is_beats,
        )


def do_regenerate_beat_outline(
    precis_undo: str | None,
    idea: str,
    log_entries: list[str] | None,
    content_is_beats: bool,
) -> tuple[str, str, str, list[str], dict[str, Any], bool]:
    """
    Two-step: (1) précis → beats, (2) beats → narrative précis. Updates Idea with the précis.
    Uses precis_undo as source; if None, falls back to current idea_tb.
    Returns (idea_text, progress, log_md, log_entries, undo_btn_update, content_is_beats).
    """
    entries = log_entries or []
    source = (precis_undo or idea or "").strip()

    if not source:
        entries = add_entry(entries, "Regenerate skipped — no précis to regenerate from")
        return (
            idea,
            "Nothing to regenerate from.",
            build_log_markdown(entries),
            entries,
            gr.update(interactive=precis_undo is not None),
            content_is_beats,
        )

    entries = add_entry(entries, f"Regenerate beat outline requested ({len(source)} chars)")
    entries = add_entry(entries, "Calling LLM…")

    try:
        outline = _complete_english_only(
            source, BEAT_OUTLINE_SYSTEM, entries, "Regenerate beat outline", task_type=LLMTaskType.PLAN
        )
        outline = (outline or "").strip()
        if not outline:
            entries = add_entry(entries, "Regenerate: empty response; keeping previous content.", level="error")
            return (
                idea,
                "LLM returned empty outline.",
                build_log_markdown(entries),
                entries,
                gr.update(interactive=precis_undo is not None),
                content_is_beats,
            )
        entries = add_entry(entries, "Beat outline regenerated. Converting to précis…")
        precis = _rewrite_precis_from_beats(outline, entries)
        is_beats_format = "## Beginning" in precis or "## Middle" in precis or "## End" in precis
        if precis and precis.strip() and not is_beats_format:
            entries = add_entry(entries, "Précis refined from beat outline.")
            return (
                precis.strip(),
                "New précis from beat outline. Edit if needed or Start when ready.",
                build_log_markdown(entries),
                entries,
                gr.update(interactive=precis_undo is not None),
                False,
            )
        entries = add_entry(entries, "Précis rewrite empty; keeping beats. Start will retry rewrite.", level="error")
        return (
            outline,
            "Beats regenerated but précis rewrite failed. Start will retry. Or press Regenerate.",
            build_log_markdown(entries),
            entries,
            gr.update(interactive=precis_undo is not None),
            True,
        )
    except Exception as e:
        entries = add_entry(entries, f"Regenerate beat outline failed: {e}", level="error")
        return (
            idea,
            f"Error: {e}",
            build_log_markdown(entries),
            entries,
            gr.update(interactive=precis_undo is not None),
            content_is_beats,
        )


def _start_output_tuple(
    steps: list[Step],
    history: list[HistoryEntry],
    entries: list[str],
    erl: dict[str, Any],
    status_msg: str,
    progress_msg: str,
    expand_disabled: dict[str, Any],
    undo_disabled: dict[str, Any],
    precis_undo: str | None,
    content_is_beats: bool,
    word_limit: int | float | None = None,
    write_visible: bool = False,
    working_visible: bool = True,
) -> tuple[
    list[Step],
    str,
    str,
    str,
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    str,
    list[str],
    dict[str, Any],
    dict[str, Any],
    str | None,
    dict[str, Any],
    list[HistoryEntry],
    dict[str, Any],
    bool,
]:
    """Build the 25-element output tuple for do_start_write (used for yields and final return)."""
    erl_tab = build_erl_tab_content(erl)
    return (
        steps,
        build_current_story_html(steps),
        build_history_markdown(history),
        build_output_paragraphs_markdown(steps),
        build_output_copy_button_html(steps),
        build_full_history_copy_button_html(steps, history),
        build_full_history_text(steps, history),
        erl_tab[0],
        erl_tab[1],
        erl_tab[2],
        status_msg,
        progress_msg,
        gr.update(visible=write_visible),
        gr.update(visible=working_visible),
        gr.update(visible=False),
        gr.update(visible=False),
        build_log_markdown(entries),
        entries,
        expand_disabled,
        _expand_next_btn_update(steps, word_limit),
        precis_undo,
        undo_disabled,
        history,
        erl,
        content_is_beats,
    )


def do_start_write(
    idea: str,
    steps: list[Step] | None,
    log_entries: list[str] | None,
    precis_undo: str | None,
    history: list[HistoryEntry] | None,
    word_limit: int | float | None,
    content_is_beats: bool,
) -> Iterator[
    tuple[
        list[Step],
        str,
        str,
        str,
        str,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        str,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        str,
        list[str],
        dict[str, Any],
        dict[str, Any],
        str | None,
        dict[str, Any],
        list[HistoryEntry],
        dict[str, Any],
        bool,
    ]
]:
    """
    Kick off writing: expand précis into two paragraphs, show Working.
    Generator: yields after each log update for real-time UI.
    """
    steps = steps or []
    expand_disabled = gr.update(interactive=False)
    undo_disabled = gr.update(interactive=False)
    empty_history: list[HistoryEntry] = []

    if not (idea or "").strip():
        entries = add_entry(log_entries or [], "Start skipped — Idea empty")
        yield _start_output_tuple(
            steps, history or [], entries, {}, "", "Enter or expand an idea first.",
            expand_disabled, undo_disabled, None, False, word_limit,
            write_visible=True, working_visible=False
        )
        return

    erl: dict[str, Any] = {}
    entries: list[str] = []
    precis_len = len(idea.strip())
    entries = add_entry(entries, f"Start write requested (précis: {precis_len} chars)")
    yield _start_output_tuple(
        steps, empty_history, entries, {}, "", "Running…",
        expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
    )
    if content_is_beats:
        idea = _rewrite_precis_from_beats(idea.strip(), entries)
        entries = add_entry(entries, "Précis rewritten; expanding into first two paragraphs…")
        yield _start_output_tuple(
            steps, empty_history, entries, {}, "", "Running…",
            expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
        )
    entries = add_entry(entries, "Calling LLM…")
    yield _start_output_tuple(
        steps, empty_history, entries, {}, "", "Calling LLM…",
        expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
    )
    last_error: Exception | None = None
    p1, p2 = "", ""
    retry_hint = ""
    try:
        for attempt in range(MAX_EXPANSION_RETRIES + 1):
            try:
                prompt = idea.strip()
                if attempt > 0:
                    prompt += (
                        retry_hint
                        if retry_hint
                        else (
                            "\n\n[Your previous response had an empty or invalid second paragraph "
                            "(e.g. a dash or placeholder). You MUST output exactly two full paragraphs "
                            "of prose, each substantial. Do not truncate. Do not use a dash as a placeholder.]"
                        )
                    )
                response = _complete_english_only(
                    prompt, EXPAND_SYSTEM, entries, "Start write"
                )
                entries = add_entry(entries, "LLM response received; parsing paragraphs")
                yield _start_output_tuple(
                    steps, empty_history, entries, {}, "", "Parsing…",
                    expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
                )
                p1, p2 = parse_two_paragraphs(response)
                entries = add_entry(entries, f"Parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                yield _start_output_tuple(
                    steps, empty_history, entries, {}, "", "Running…",
                    expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
                )
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
                if _is_truncated(p1) or _is_truncated(p2):
                    raise ValueError("Paragraph appears truncated (incomplete sentence); retrying.")
                if contains_banned_chars(p1) or contains_banned_chars(p2):
                    raise ValueError("Banned character in output; retrying.")
                break
            except Exception as e:
                last_error = e
                if "truncated" in str(e).lower():
                    retry_hint = (
                        "\n\n[Your previous response was cut off. Finish both paragraphs completely "
                        "with proper punctuation.]"
                    )
                elif "banned character" in str(e).lower():
                    retry_hint = BANNED_CHARS_RETRY_HINT
                msg = (
                    f"Start write: invalid output, retrying (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1})"
                    if isinstance(e, ValueError) and "retrying" in str(e).lower()
                    else f"Start write failed (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1}): {e}"
                )
                entries = add_entry(entries, msg, level="error")
                yield _start_output_tuple(
                    steps, empty_history, entries, {}, "", "Retrying…",
                    expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
                )
                if attempt >= MAX_EXPANSION_RETRIES:
                    raise last_error
        new_steps: list[Step] = [{"paragraph_1": p1, "paragraph_2": p2}]
        entries = add_entry(entries, "Generating story title…")
        yield _start_output_tuple(
            steps, empty_history, entries, {}, "", "Generating story title…",
            expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
        )
        story_name = _generate_story_name(idea.strip())
        entries = add_entry(entries, f"Story title: {story_name}")
        yield _start_output_tuple(
            new_steps, empty_history, entries, {}, "", "Initializing ERL…",
            expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
        )
        try:
            erl = initialize_erl(idea.strip(), f"{p1}\n\n{p2}")
            n_ent = len(erl.get("entities") or [])
            n_rel = len(erl.get("relationships") or [])
            entries = add_entry(entries, f"ERL initialized: {n_ent} entities, {n_rel} relationships")
            save_erl(erl)
            save_story(idea.strip(), new_steps, empty_history, name=story_name)
        except Exception as e:
            entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
            yield _start_output_tuple(
                new_steps, empty_history, entries, erl if erl else {}, "", f"Error: {e}",
                expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit
            )
        entries = add_entry(entries, f"Start completed — step {len(new_steps)} (two paragraphs) added")
        status_msg = f"**Story:** *{story_name}*\n\nStory started."
        progress_msg = f"Done. Step {len(new_steps)}: two paragraphs added. Use **Expand next** or **Run** in Working to expand further. **Run** continues until you press **Pause** or the word count is reached."
        yield _start_output_tuple(
            new_steps, empty_history, entries, erl, status_msg, progress_msg,
            expand_disabled, undo_disabled, None, False, word_limit
        )
    except Exception as e:
        entries = add_entry(entries, f"Start write failed: {e}", level="error")
        yield _start_output_tuple(
            steps, empty_history, entries, {}, "", f"Error: {e}",
            expand_disabled, undo_disabled, precis_undo, content_is_beats, word_limit,
            write_visible=True, working_visible=False
        )


def do_reset_write() -> tuple[
    str,
    str,
    str,
    list[str],
    None,
    list[Step],
    list[HistoryEntry],
    dict[str, Any],
    str,
    dict[str, Any],
    dict[str, Any],
    bool,
]:
    """
    Reset Write page: clear all state so the user can start fresh.
    Returns (idea_tb, progress_tb, log_md, log_state, precis_undo_state, steps_state,
    history_state, erl_state, latest_story_md, expand_btn, undo_btn, content_is_beats).
    """
    entries = add_entry([], "Reset — starting fresh")
    return (
        "",
        "",
        build_log_markdown(entries),
        entries,
        None,
        [],
        [],
        {},
        EMPTY_STORY_PLACEHOLDER,
        gr.update(interactive=True),
        gr.update(interactive=False),
        False,
    )


def do_expand_next(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
    log_entries: list[str] | None,
    word_limit: int | float | None,
    erl_state: dict | None = None,
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
    dict[str, Any],
]:
    """
    Expand the first leaf paragraph (depth-first) into two via LLM; update tree and history.
    Stops when story word count is at or above word_limit (from Word count slider).
    Returns (..., log_entries, expand_next_btn_update, erl_state).
    """
    steps = steps or []
    history = history or []
    entries = log_entries or []

    def _valid_erl(e: dict | None) -> bool:
        return isinstance(e, dict) and (e.get("entities") or e.get("relationships") or e.get("global_state"))

    limit = int(word_limit) if word_limit is not None else 0
    if limit > 0:
        current_words = count_words_in_steps(steps)
        if current_words >= limit:
            entries = add_entry(
                entries,
                f"Expand next: word limit reached ({current_words} >= {limit})",
            )
            _erl = erl_state if _valid_erl(erl_state) else load_erl()
            _erl_tab = build_erl_tab_content(_erl)
            return (
                steps,
                history,
                build_current_story_html(steps),
                build_history_markdown(history),
                build_output_paragraphs_markdown(steps),
                build_output_copy_button_html(steps),
                build_full_history_copy_button_html(steps, history),
                build_full_history_text(steps, history),
                _erl_tab[0],
                _erl_tab[1],
                _erl_tab[2],
                f"Word limit reached ({current_words} words). No further expansion.",
                build_log_markdown(entries),
                entries,
                _expand_next_btn_update(steps, word_limit),
                _erl,
            )

    path, text = get_first_leaf_path(steps)
    if path is not None and text:
        logger.debug("do_expand_next: path=%s text_len=%d", path_label(path[0], path[1], path[2]), len(text))
    if path is None or not text:
        entries = add_entry(entries, "Expand next: no leaf paragraph to expand")
        _erl = erl_state if _valid_erl(erl_state) else load_erl()
        _erl_tab = build_erl_tab_content(_erl)
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            _erl_tab[0],
            _erl_tab[1],
            _erl_tab[2],
            "No more paragraphs to expand.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
            _erl,
        )

    step_idx, key, indices = path
    path_str = path_label(step_idx, key, indices)
    entries = add_entry(entries, f"Expand next: {path_str} ({len(text)} chars)")
    entries = add_entry(entries, "Calling LLM…")

    previous_text = get_previous_leaf_in_reading_order(steps, path)
    prev_stripped = (previous_text or "").strip()
    if prev_stripped:
        expand_prompt = (
            f"Previous paragraph (for continuity of tone only — do NOT reuse its events, imagery, or setting):\n\n{prev_stripped}\n\n"
            f"Paragraph to expand:\n\n{text.strip()}"
        )
    else:
        expand_prompt = f"Paragraph to expand:\n\n{text.strip()}"

    if is_first_leaf_in_reading_order(steps, path):
        current_erl = empty_erl()
        logger.debug("do_expand_next: first leaf, using empty ERL")
    else:
        current_erl = erl_state if _valid_erl(erl_state) else load_erl()
        logger.debug("do_expand_next: loaded ERL entities=%d", len(current_erl.get("entities") or []))
    try:
        block_type = classify_block(text)
        entries = add_entry(entries, f"Expand next: classified as {block_type}")
    except Exception:
        block_type = "SCENE"
        entries = add_entry(entries, "Expand next: classification failed; using SCENE", level="error")
    erl_json = erl_to_json(current_erl)
    if block_type == "TRANSITION":
        expand_system = get_transition_expand_system(erl_json)
    else:
        expand_system = get_scene_expand_system(erl_json)

    last_error: Exception | None = None
    retry_hint = ""
    for attempt in range(MAX_EXPANSION_RETRIES + 1):
        try:
            if block_type == "SCENE":
                p1, p2, updated_erl = _run_micro_beat_expansion(
                    text, previous_text, current_erl, entries, "Expand next"
                )
            else:
                effective_prompt = expand_prompt + (retry_hint if attempt > 0 else "")
                response = _complete_english_only(
                    effective_prompt, expand_system, entries, "Expand next"
                )
                entries = add_entry(entries, "LLM response received; parsing paragraphs")
                p1, p2 = parse_two_paragraphs(response)
                p1 = _strip_leading_source_text(p1, text, previous_text)
                p2 = _strip_leading_source_text(p2, text, previous_text)
                updated_erl = extract_state_updates(f"{p1}\n\n{p2}", current_erl)
            entries = add_entry(entries, f"Parsed: P1={len(p1)} chars, P2={len(p2)} chars")
            if not (p1 or "").strip() or not (p2 or "").strip():
                raw_preview = (p1 or "") + (p2 or "")
                entries = add_entry(
                    entries,
                    f"Empty paragraph from parser — P1 empty: {not (p1 or '').strip()}, P2 empty: {not (p2 or '').strip()} (raw: {len(raw_preview)} chars)",
                    level="error",
                )
                snippet = raw_preview[:400].replace("\n", " ")
                entries = add_entry(entries, f"Raw response snippet: {snippet}…", level="error")
            if _is_empty_or_dash(p1) or _is_empty_or_dash(p2):
                raise ValueError("Empty or invalid paragraph (P1 or P2 empty/dash); retrying.")
            if _is_prompt_echo(p1) or _is_prompt_echo(p2):
                raise ValueError("Prompt echo or invalid content (P1 or P2); retrying.")
            if _is_truncated(p1) or _is_truncated(p2):
                raise ValueError("Paragraph appears truncated (incomplete sentence); retrying.")
            if _is_too_short(text, p1, p2):
                raise ValueError("Expansion too short; retrying.")
            if not _validate_expansion(text, p1, p2, entries, "Expand next"):
                entries = add_entry(entries, "Expand next: writer retry (validation rejected).")
                retry_hint_add = (
                    BANNED_CHARS_RETRY_HINT
                    if (contains_banned_chars(p1) or contains_banned_chars(p2))
                    else "\n\n[Your previous expansion failed validation (flow/consistency). Please try again: ensure the two paragraphs faithfully expand the paragraph above and are in chronological order.]"
                )
                retry_prompt = expand_prompt + retry_hint_add
                try:
                    response = _complete_english_only(retry_prompt, expand_system, entries, "Expand next retry")
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
                        and not _is_truncated(r1)
                        and not _is_truncated(r2)
                        and not _is_too_short(text, r1, r2)
                        and not contains_banned_chars(r1)
                        and not contains_banned_chars(r2)
                    ):
                        p1, p2 = r1, r2
                        entries = add_entry(entries, f"Retry parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                    else:
                        entries = add_entry(entries, "Retry returned empty or single paragraph; keeping first expansion.", level="error")
                except Exception as retry_err:
                    entries = add_entry(entries, f"Retry failed ({retry_err}); keeping first expansion.", level="error")
            new_steps = set_leaf_at_path(steps, path, p1, p2)
            combined_new = f"{p1}\n\n{p2}"
            erl_base = updated_erl if block_type == "SCENE" else current_erl
            updated_erl = extract_state_updates(combined_new, erl_base)
            try:
                save_erl(updated_erl)
                logger.debug("do_expand_next: saved ERL")
            except Exception as e:
                entries = add_entry(entries, f"Could not save ERL to DB: {e}", level="error")
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
                precis, _, _, _, _ = load_story()
                save_story(precis, new_steps, new_history)
            except Exception as e:
                entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
            consistency_issues = vet_consistency(new_steps, updated_erl)
            if consistency_issues:
                for issue in consistency_issues:
                    entries = add_entry(entries, f"Consistency: {issue}", level="error")
            else:
                entries = add_entry(entries, "Vetting: no consistency issues")
            _ = vet_similarity(new_steps)
            entries = add_entry(entries, f"Expanded — {path_str}")
            _erl_tab = build_erl_tab_content(updated_erl)
            return (
                new_steps,
                new_history,
                build_current_story_html(new_steps),
                build_history_markdown(new_history),
                build_output_paragraphs_markdown(new_steps),
                build_output_copy_button_html(new_steps),
                build_full_history_copy_button_html(new_steps, new_history),
                build_full_history_text(new_steps, new_history),
                _erl_tab[0],
                _erl_tab[1],
                _erl_tab[2],
                f"Expanded {path_str} into two paragraphs.",
                build_log_markdown(entries),
                entries,
                _expand_next_btn_update(new_steps, word_limit),
                updated_erl,
            )
        except Exception as e:
            last_error = e
            if "truncated" in str(e).lower():
                retry_hint = "\n\n[Your previous response was cut off. Finish both paragraphs completely with proper punctuation.]"
            elif "too short" in str(e).lower():
                retry_hint = "\n\n[Your previous expansion was too short and lost plot content. The combined output must be at least as long as the source paragraph. Preserve every plot beat.]"
            entries = add_entry(
                entries,
                f"Expand next failed (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1}): {e}",
                level="error",
            )
            if attempt >= MAX_EXPANSION_RETRIES:
                _erl_tab = build_erl_tab_content(current_erl)
                return (
                    steps,
                    history,
                    build_current_story_html(steps),
                    build_history_markdown(history),
                    build_output_paragraphs_markdown(steps),
                    build_output_copy_button_html(steps),
                    build_full_history_copy_button_html(steps, history),
                    build_full_history_text(steps, history),
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    f"Error: {e}",
                    build_log_markdown(entries),
                    entries,
                    _expand_next_btn_update(steps, word_limit),
                    current_erl,
                )
    err = last_error or ValueError("Expand next failed after retries")
    entries = add_entry(entries, f"Expand next failed: {err}", level="error")
    _erl_tab = build_erl_tab_content(current_erl)
    return (
        steps,
        history,
        build_current_story_html(steps),
        build_history_markdown(history),
        build_output_paragraphs_markdown(steps),
        build_output_copy_button_html(steps),
        build_full_history_copy_button_html(steps, history),
        build_full_history_text(steps, history),
        _erl_tab[0],
        _erl_tab[1],
        _erl_tab[2],
        f"Error: {err}",
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(steps, word_limit),
        current_erl,
    )


def do_expand_round(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
    log_entries: list[str] | None,
    word_limit: int | float | None,
    progress_callback: Callable[[list[Step], list[HistoryEntry], list[str]], None] | None = None,
) -> tuple[
    list[Step],
    list[HistoryEntry],
    str,
    str,
    str,
    str,
    list[str],
    dict[str, Any],
    bool,
]:
    """
    Expand every current leaf into two (one round). Progression: 2 → 4 → 8 → 16 …
    Stops when at/over word_limit or no leaves. Same return shape as do_expand_next.
    When progress_callback is provided (e.g. by auto-expand worker), it is called after
    each log entry so the UI can update in real time.
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
        _erl = load_erl()
        _erl_tab = build_erl_tab_content(_erl)
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            _erl_tab[0],
            _erl_tab[1],
            _erl_tab[2],
            f"Word limit reached. No further expansion.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
            False,
        )

    all_leaves = get_all_leaf_paths(steps)
    if not all_leaves:
        entries = add_entry(entries, "Expand round: no leaf paragraphs to expand")
        _erl = load_erl()
        _erl_tab = build_erl_tab_content(_erl)
        return (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            _erl_tab[0],
            _erl_tab[1],
            _erl_tab[2],
            "No more paragraphs to expand.",
            build_log_markdown(entries),
            entries,
            _expand_next_btn_update(steps, word_limit),
            False,
        )

    entries = add_entry(
        entries,
        f"Expand round: splitting {len(all_leaves)} paragraph(s) → {len(all_leaves) * 2}",
    )
    logger.debug("do_expand_round: leaves=%d", len(all_leaves))
    current_steps = steps
    new_history = list(history)
    if progress_callback is not None:
        progress_callback(current_steps, new_history, entries)
    status_parts: list[str] = []
    round_stop_error: str | None = None
    round_stop_fatal: bool = False
    current_erl = empty_erl()

    for path, text in all_leaves:
        if limit > 0 and count_words_in_steps(current_steps) >= limit:
            entries = add_entry(entries, "Expand round: word limit hit mid-round; stopping")
            if progress_callback is not None:
                progress_callback(current_steps, new_history, entries)
            break
        step_idx, key, indices = path
        path_str = path_label(step_idx, key, indices)
        entries = add_entry(entries, f"  {path_str} ({len(text)} chars)…")
        if progress_callback is not None:
            progress_callback(current_steps, new_history, entries)
        previous_text = get_previous_leaf_in_reading_order(current_steps, path)
        prev_stripped = (previous_text or "").strip()
        if prev_stripped:
            expand_prompt = (
                f"Previous paragraph (for continuity of tone only — do NOT reuse its events, imagery, or setting):\n\n{prev_stripped}\n\n"
                f"Paragraph to expand:\n\n{text.strip()}"
            )
        else:
            expand_prompt = f"Paragraph to expand:\n\n{text.strip()}"
        try:
            block_type = classify_block(text)
            entries = add_entry(entries, f"  {path_str}: classified as {block_type}")
            if progress_callback is not None:
                progress_callback(current_steps, new_history, entries)
        except Exception:
            block_type = "SCENE"
            entries = add_entry(entries, f"  {path_str}: classification failed; using SCENE", level="error")
            if progress_callback is not None:
                progress_callback(current_steps, new_history, entries)
        erl_json = erl_to_json(current_erl)
        expand_system = get_transition_expand_system(erl_json) if block_type == "TRANSITION" else get_scene_expand_system(erl_json)
        path_succeeded = False
        retry_hint = ""
        for attempt in range(MAX_EXPANSION_RETRIES + 1):
            try:
                if block_type == "SCENE":
                    p1, p2, path_erl = _run_micro_beat_expansion(
                        text, previous_text, current_erl, entries, f"  {path_str}"
                    )
                    current_erl = path_erl
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
                else:
                    effective_prompt = expand_prompt + (retry_hint if attempt > 0 else "")
                    response = _complete_english_only(
                        effective_prompt, expand_system, entries, "Expand round"
                    )
                    p1, p2 = parse_two_paragraphs(response)
                    p1 = _strip_leading_source_text(p1, text, previous_text)
                    p2 = _strip_leading_source_text(p2, text, previous_text)
                    current_erl = extract_state_updates(f"{p1}\n\n{p2}", current_erl)
                entries = add_entry(entries, f"  {path_str} parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                if progress_callback is not None:
                    progress_callback(current_steps, new_history, entries)
                if not (p1 or "").strip() or not (p2 or "").strip():
                    raw_preview = (p1 or "") + (p2 or "")
                    entries = add_entry(
                        entries,
                        f"  {path_str} WARNING: empty P1 or P2 — P1 empty: {not (p1 or '').strip()}, P2 empty: {not (p2 or '').strip()} (raw: {len(raw_preview)} chars)",
                        level="error",
                    )
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
                    snippet = raw_preview[:350].replace("\n", " ")
                    entries = add_entry(entries, f"  Raw snippet: {snippet}…", level="error")
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
                if _is_empty_or_dash(p1) or _is_empty_or_dash(p2):
                    raise ValueError("Empty or invalid paragraph (P1 or P2 empty/dash); retrying.")
                if _is_prompt_echo(p1) or _is_prompt_echo(p2):
                    raise ValueError("Prompt echo or invalid content (P1 or P2); retrying.")
                if _is_truncated(p1) or _is_truncated(p2):
                    raise ValueError("Paragraph appears truncated (incomplete sentence); retrying.")
                if _is_too_short(text, p1, p2):
                    raise ValueError("Expansion too short; retrying.")
                if not _validate_expansion(text, p1, p2, entries, f"  {path_str}"):
                    entries = add_entry(entries, f"  {path_str}: writer retry (validation rejected).")
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
                    retry_hint_add = (
                        BANNED_CHARS_RETRY_HINT
                        if (contains_banned_chars(p1) or contains_banned_chars(p2))
                        else "\n\n[Your previous expansion failed validation (flow/consistency). Please try again: ensure the two paragraphs faithfully expand the paragraph above and are in chronological order.]"
                    )
                    retry_prompt = expand_prompt + retry_hint_add
                    try:
                        response = _complete_english_only(retry_prompt, expand_system, entries, "Expand round retry")
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
                            and not _is_truncated(r1)
                            and not _is_truncated(r2)
                            and not _is_too_short(text, r1, r2)
                            and not contains_banned_chars(r1)
                            and not contains_banned_chars(r2)
                        ):
                            p1, p2 = r1, r2
                            entries = add_entry(entries, f"  {path_str} retry parsed: P1={len(p1)} chars, P2={len(p2)} chars")
                            if progress_callback is not None:
                                progress_callback(current_steps, new_history, entries)
                        else:
                            entries = add_entry(entries, f"  {path_str} retry empty; keeping first expansion.", level="error")
                            if progress_callback is not None:
                                progress_callback(current_steps, new_history, entries)
                    except Exception as retry_err:
                        entries = add_entry(entries, f"  {path_str} retry failed ({retry_err}); keeping first expansion.", level="error")
                        if progress_callback is not None:
                            progress_callback(current_steps, new_history, entries)
                else:
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
                current_steps = set_leaf_at_path(current_steps, path, p1, p2)
                combined_new = f"{p1}\n\n{p2}"
                current_erl = extract_state_updates(combined_new, current_erl)
                try:
                    save_erl(current_erl)
                except Exception as e:
                    entries = add_entry(entries, f"  {path_str}: could not save ERL: {e}", level="error")
                    if progress_callback is not None:
                        progress_callback(current_steps, new_history, entries)
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
                if progress_callback is not None:
                    progress_callback(current_steps, new_history, entries)
                break
            except Exception as e:
                if "truncated" in str(e).lower():
                    retry_hint = "\n\n[Your previous response was cut off. Finish both paragraphs completely with proper punctuation.]"
                elif "too short" in str(e).lower():
                    retry_hint = "\n\n[Your previous expansion was too short and lost plot content. The combined output must be at least as long as the source paragraph. Preserve every plot beat.]"
                entries = add_entry(
                    entries,
                    f"  {path_str} failed (attempt {attempt + 1}/{MAX_EXPANSION_RETRIES + 1}): {e}",
                    level="error",
                )
                if progress_callback is not None:
                    progress_callback(current_steps, new_history, entries)
                if attempt >= MAX_EXPANSION_RETRIES:
                    round_stop_error = str(e)
                    round_stop_fatal = _is_fatal_error(e)
                    break
        if not path_succeeded:
            break

    try:
        precis, _, _, _, _ = load_story()
        save_story(precis, current_steps, new_history)
    except Exception as e:
        entries = add_entry(entries, f"Could not save story to DB: {e}", level="error")
        if progress_callback is not None:
            progress_callback(current_steps, new_history, entries)
    actual_leaves = len(get_all_leaf_paths(current_steps))
    if len(status_parts) == len(all_leaves):
        status_msg = f"Round: {len(all_leaves)} → {actual_leaves} paragraphs."
    elif round_stop_error:
        if round_stop_fatal:
            status_msg = (
                f"Stopped: error. Progress saved. Click Run to resume or Expand next to continue manually. "
                f"Error: {round_stop_error}"
            )
        else:
            status_msg = (
                f"Round: {len(all_leaves)} → {actual_leaves} paragraphs "
                f"({_RECOVERABLE_ERROR_MARKER}, continuing…)."
            )
    else:
        status_msg = f"Round: {len(all_leaves)} → {actual_leaves} paragraphs (stopped: word limit)."
    entries = add_entry(entries, f"Round done — expanded: {', '.join(status_parts) or 'none'}")
    if progress_callback is not None:
        progress_callback(current_steps, new_history, entries)
    _erl_tab = build_erl_tab_content(current_erl)
    return (
        current_steps,
        new_history,
        build_current_story_html(current_steps),
        build_history_markdown(new_history),
        build_output_paragraphs_markdown(current_steps),
        build_output_copy_button_html(current_steps),
        build_full_history_copy_button_html(current_steps, new_history),
        build_full_history_text(current_steps, new_history),
        _erl_tab[0],
        _erl_tab[1],
        _erl_tab[2],
        status_msg,
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(current_steps, word_limit),
        round_stop_fatal,
    )


def _auto_expand_worker(
    steps: list[Step],
    history: list[HistoryEntry],
    entries: list[str],
    word_limit: int | float | None,
    debug_pause: bool,
    result_queue: queue.Queue,
) -> None:
    """Run expand-round in a loop (2→4→8→…) until stop requested, word limit, or no leaf. Puts 20-tuples (steps, history, UI strings, status, log, entries, expand_btn, run_btn, write_btns, erl_state) then 'done'. When debug_pause is True, sleeps 3s after each expansion so output can be seen."""
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
    round_num = 0
    consecutive_recoverable = 0
    while True:
        if _auto_stop_requested:
            _erl = load_erl()
            _erl_tab = build_erl_tab_content(_erl)
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
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    "Paused.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                    _erl,
                )
            )
            result_queue.put("done")
            return
        if limit > 0 and count_words_in_steps(current_steps) >= limit:
            _erl = load_erl()
            _erl_tab = build_erl_tab_content(_erl)
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
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    "Word limit reached. Auto stopped.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                    _erl,
                )
            )
            result_queue.put("done")
            return
        all_leaves = get_all_leaf_paths(current_steps)
        round_num += 1
        logger.debug("Auto expand round %d, leaves=%d", round_num, len(all_leaves))
        if not all_leaves:
            _erl = load_erl()
            _erl_tab = build_erl_tab_content(_erl)
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
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    "No more paragraphs. Auto stopped.",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                    _erl,
                )
            )
            result_queue.put("done")
            return
        def on_progress(
            steps: list[Step], history: list[HistoryEntry], entries: list[str]
        ) -> None:
            _erl = load_erl()
            _erl_tab = build_erl_tab_content(_erl)
            result_queue.put(
                (
                    steps,
                    history,
                    build_current_story_html(steps),
                    build_history_markdown(history),
                    build_output_paragraphs_markdown(steps),
                    build_output_copy_button_html(steps),
                    build_full_history_copy_button_html(steps, history),
                    build_full_history_text(steps, history),
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    "Running…",
                    build_log_markdown(entries),
                    entries,
                    _expand_next_btn_update(steps, word_limit),
                    run_btn_disable,
                    *write_btns_disable,
                    _erl,
                )
            )

        try:
            result = do_expand_round(
                current_steps,
                current_history,
                current_entries,
                word_limit,
                progress_callback=on_progress,
            )
        except Exception as e:
            current_entries = add_entry(
                current_entries, f"Auto expand failed: {e}", level="error"
            )
            try:
                precis, _, _, _, _ = load_story()
                save_story(precis, current_steps, current_history)
                save_erl(load_erl())  # Persist last known ERL (no new data from failed round)
            except Exception as save_err:
                current_entries = add_entry(
                    current_entries,
                    f"Could not save on error: {save_err}",
                    level="error",
                )
            _erl = load_erl()
            _erl_tab = build_erl_tab_content(_erl)
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
                    _erl_tab[0],
                    _erl_tab[1],
                    _erl_tab[2],
                    "Stopped: error. Progress saved. Click Run to resume or Expand next to continue manually. "
                    f"Error: {e}",
                    build_log_markdown(current_entries),
                    current_entries,
                    _expand_next_btn_update(current_steps, word_limit),
                    run_btn_enable,
                    *write_btns_enable,
                    _erl,
                )
            )
            result_queue.put("done")
            return

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
            _,
            _,
            _,
            current_entries,
            _,
            round_stop_fatal,
        ) = result
        current_erl = load_erl()

        if round_stop_fatal:
            result_queue.put(
                (*result[:15], run_btn_enable, *write_btns_enable, current_erl)
            )
            result_queue.put("done")
            return

        is_recoverable = _RECOVERABLE_ERROR_MARKER in (result[11] or "")
        if is_recoverable:
            consecutive_recoverable += 1
            if consecutive_recoverable >= _MAX_CONSECUTIVE_RECOVERABLE:
                current_entries = add_entry(
                    current_entries,
                    f"Stopped: {consecutive_recoverable} consecutive recoverable errors; treating as fatal.",
                    level="error",
                )
                stop_status = (
                    "Stopped: too many consecutive recoverable errors. Progress saved. Click Run to resume."
                )
                result_queue.put(
                    (
                        *result[:11],
                        stop_status,
                        build_log_markdown(current_entries),
                        current_entries,
                        result[14],
                        run_btn_enable,
                        *write_btns_enable,
                        current_erl,
                    )
                )
                result_queue.put("done")
                return
            time.sleep(2)
        else:
            consecutive_recoverable = 0

        result_queue.put((*result[:15], run_btn_disable, *write_btns_disable, current_erl))

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
    Yields 17-tuples: steps, history, working_current_md, ..., expand_next_btn, run_btn, start_btn, expand_btn, undo_btn, erl_state. When debug_pause is True, worker sleeps 3s after each expansion.
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
    _erl = load_erl()
    _erl_tab = build_erl_tab_content(_erl)
    yield (
        steps,
        history,
        build_current_story_html(steps),
        build_history_markdown(history),
        build_output_paragraphs_markdown(steps),
        build_output_copy_button_html(steps),
        build_full_history_copy_button_html(steps, history),
        build_full_history_text(steps, history),
        _erl_tab[0],
        _erl_tab[1],
        _erl_tab[2],
        "Running…",
        build_log_markdown(entries),
        entries,
        _expand_next_btn_update(steps, word_limit),
        gr.update(interactive=False),   # run_btn
        gr.update(interactive=False),   # start_btn
        gr.update(interactive=False),   # expand_btn
        gr.update(interactive=False),   # undo_btn
        _erl,
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
