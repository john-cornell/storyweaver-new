"""
Interactive mode handlers: start, step (choice), vet custom option.
"""

from __future__ import annotations

import logging
from typing import Any

from db import save_interactive_story
from llm import complete, log_llm_outcome
from log import add_entry

from ..handlers import _generate_story_name, _rewrite_precis_from_beats
from .tree_utils import get_prose_to_node, parse_beats

from ..prompts import (
    INTERACTIVE_CHOICES_SYSTEM,
    INTERACTIVE_CONTINUE_SYSTEM,
    INTERACTIVE_OPENING_SYSTEM,
    INTERACTIVE_VET_CUSTOM_SYSTEM,
)

logger = logging.getLogger(__name__)


def _parse_choices(raw: str) -> tuple[str, str]:
    """Parse 'A: ...\\nB: ...' format. Returns (choice_a, choice_b)."""
    a_text, b_text = "", ""
    for line in (raw or "").strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("A:"):
            a_text = line[2:].strip()
        elif line.upper().startswith("B:"):
            b_text = line[2:].strip()
    return (a_text, b_text)


def vet_custom_option(precis: str, beats: list[str], user_text: str) -> tuple[bool, str]:
    """
    Vet user-provided choice against précis and beats.
    Returns (allowed, reason). If allowed, reason is empty.
    """
    if not (user_text or "").strip():
        return (False, "Empty choice.")
    combined = f"Précis:\n{precis or ''}\n\nBeats: " + "; ".join(beats[:20])
    prompt = f"{combined}\n\nReader choice: {user_text.strip()}\n\nIs this consistent?"
    try:
        result = complete(prompt, system=INTERACTIVE_VET_CUSTOM_SYSTEM, purpose="interactive_vet_custom")
        raw = (result.text or "").strip().upper()
        if raw.startswith("YES"):
            log_llm_outcome(result.call_id, True)
            return (True, "")
        log_llm_outcome(result.call_id, False)
        reason = raw.replace("NO", "").strip()
        if reason.lower().startswith("reason:"):
            reason = reason[7:].strip()
        return (False, reason or "Choice inconsistent with précis.")
    except Exception as e:
        logger.warning("Vet custom failed: %s", e)
        return (False, str(e))


def do_interactive_start(
    idea: str,
    log_entries: list[str] | None,
    content_is_beats: bool,
) -> tuple[
    str,
    list[str],
    str | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
    str,
    str,
    list[str],
]:
    """
    Start interactive story: précis → opening → choices.
    Returns (precis, beats, name, nodes, choices, current_node_id, choice_a, choice_b, log_entries).
    """
    entries = log_entries or []
    entries = add_entry(entries, "Interactive start requested")

    if not (idea or "").strip():
        entries = add_entry(entries, "Idea empty", level="error")
        return ("", [], None, [], [], 0, "", "", entries)

    precis = idea.strip()
    if content_is_beats:
        precis = _rewrite_precis_from_beats(precis, entries)
        if not precis.strip():
            entries = add_entry(entries, "Précis rewrite failed", level="error")
            return ("", [], None, [], [], 0, "", "", entries)

    beats = parse_beats(idea, content_is_beats)
    if not beats:
        beats = parse_beats(precis, False)

    entries = add_entry(entries, f"Generating opening (beats: {len(beats)})")
    prompt = f"Précis:\n{precis}\n\nBeats: " + "; ".join(beats[:15]) if beats else f"Précis:\n{precis}"
    try:
        result = complete(prompt, system=INTERACTIVE_OPENING_SYSTEM, purpose="interactive_opening")
        prose = (result.text or "").strip()
        if not prose:
            entries = add_entry(entries, "Opening empty", level="error")
            return (precis, beats, None, [], [], 0, "", "", entries)
        log_llm_outcome(result.call_id, True)
    except Exception as e:
        entries = add_entry(entries, f"Opening failed: {e}", level="error")
        return (precis, beats, None, [], [], 0, "", "", entries)

    entries = add_entry(entries, "Generating choices")
    choice_prompt = f"Précis:\n{precis}\n\nStory so far:\n{prose}\n\nPropose two ways to continue."
    try:
        result = complete(choice_prompt, system=INTERACTIVE_CHOICES_SYSTEM, purpose="interactive_choices")
        a_text, b_text = _parse_choices(result.text or "")
        if not a_text or not b_text:
            entries = add_entry(entries, "Choices parse failed", level="error")
            return (precis, beats, None, [], [], 0, "", "", entries)
        log_llm_outcome(result.call_id, True)
    except Exception as e:
        entries = add_entry(entries, f"Choices failed: {e}", level="error")
        return (precis, beats, None, [], [], 0, "", "", entries)

    name = _generate_story_name(precis)
    root = {"id": 1, "parent_id": None, "choice_label": None, "prose_text": prose}
    choice_rec = {"node_id": 1, "choice_a_text": a_text, "choice_b_text": b_text}
    nodes = [root]
    choices = [choice_rec]
    save_interactive_story(precis, beats, name, nodes, choices)
    entries = add_entry(entries, "Interactive story started")
    return (precis, beats, name, nodes, choices, 1, a_text, b_text, entries)


def do_interactive_step(
    precis: str,
    beats: list[str],
    nodes: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    current_node_id: int,
    choice_label: str,
    choice_text: str,
    log_entries: list[str] | None,
    is_custom: bool = False,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
    str,
    str,
    list[str],
]:
    """
    Apply choice and generate continuation. Returns (nodes, choices, new_node_id, choice_a, choice_b, log_entries).
    If is_custom, vet first; then generate complementary option.
    """
    entries = log_entries or []
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    choice_by_node = {c["node_id"]: c for c in choices if isinstance(c, dict)}

    if current_node_id not in by_id:
        entries = add_entry(entries, "Invalid node", level="error")
        return (nodes, choices, current_node_id, "", "", entries)

    current_choice = choice_by_node.get(current_node_id)
    if not current_choice:
        entries = add_entry(entries, "No choices at this node", level="error")
        return (nodes, choices, current_node_id, "", "", entries)

    if is_custom:
        allowed, reason = vet_custom_option(precis, beats, choice_text)
        if not allowed:
            entries = add_entry(entries, f"Custom choice rejected: {reason}", level="error")
            return (nodes, choices, current_node_id, current_choice["choice_a_text"], current_choice["choice_b_text"], entries)
        a_text, b_text = choice_text.strip(), ""
        entries = add_entry(entries, "Generating complementary option")
        story_so_far = get_prose_to_node(nodes, current_node_id)
        prompt = f"Précis:\n{precis}\n\nStory so far:\n{story_so_far}\n\nOne option must be: {a_text}\n\nGenerate the other option (B)."
        try:
            result = complete(prompt, system=INTERACTIVE_CHOICES_SYSTEM, purpose="interactive_choices_complement")
            _, b_text = _parse_choices(result.text or "")
            if not b_text:
                b_text = "Continue."
            log_llm_outcome(result.call_id, True)
        except Exception as e:
            entries = add_entry(entries, f"Complement failed: {e}", level="error")
            b_text = "Continue."
        current_choice = {"node_id": current_node_id, "choice_a_text": a_text, "choice_b_text": b_text}
        choice_label = "A"
    else:
        a_text = current_choice["choice_a_text"]
        b_text = current_choice["choice_b_text"]
        if choice_label.upper() == "A":
            choice_text = a_text
        else:
            choice_text = b_text
            choice_label = "B"

    max_id = max((n.get("id") or 0) for n in nodes) if nodes else 0
    new_id = max_id + 1

    entries = add_entry(entries, f"Generating continuation for choice {choice_label}")
    story_so_far = get_prose_to_node(nodes, current_node_id)
    prompt = f"Précis:\n{precis}\n\nStory so far:\n{story_so_far}\n\nChosen option: {choice_text}\n\nWrite the next 1-2 paragraphs."
    try:
        result = complete(prompt, system=INTERACTIVE_CONTINUE_SYSTEM, purpose="interactive_continue")
        prose = (result.text or "").strip()
        if not prose:
            entries = add_entry(entries, "Continuation empty", level="error")
            return (nodes, choices, current_node_id, a_text, b_text, entries)
        log_llm_outcome(result.call_id, True)
    except Exception as e:
        entries = add_entry(entries, f"Continuation failed: {e}", level="error")
        return (nodes, choices, current_node_id, a_text, b_text, entries)

    new_node = {"id": new_id, "parent_id": current_node_id, "choice_label": choice_label, "prose_text": prose}
    new_nodes = list(nodes)
    new_nodes.append(new_node)

    entries = add_entry(entries, "Generating next choices")
    full_prose = get_prose_to_node(new_nodes, new_id)
    choice_prompt = f"Précis:\n{precis}\n\nStory so far:\n{full_prose}\n\nPropose two ways to continue."
    try:
        result = complete(choice_prompt, system=INTERACTIVE_CHOICES_SYSTEM, purpose="interactive_choices")
        next_a, next_b = _parse_choices(result.text or "")
        if not next_a:
            next_a = "Continue."
        if not next_b:
            next_b = "Continue."
        log_llm_outcome(result.call_id, True)
    except Exception as e:
        next_a, next_b = "Continue.", "Continue."

    new_choices = [c for c in choices if c.get("node_id") != current_node_id]
    new_choices.append({"node_id": current_node_id, "choice_a_text": a_text, "choice_b_text": b_text})
    new_choices.append({"node_id": new_id, "choice_a_text": next_a, "choice_b_text": next_b})

    save_interactive_story(precis, beats, None, new_nodes, new_choices)
    entries = add_entry(entries, "Step saved")
    return (new_nodes, new_choices, new_id, next_a, next_b, entries)
