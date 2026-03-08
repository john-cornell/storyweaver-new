"""
Entity and Relationship Ledger (ERL) types and serialization.
Persistent state for narrative consistency across expansion iterations.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class Entity(TypedDict, total=False):
    """A character or significant object in the story."""

    name: str
    physical_state: str
    inventory: list[str]
    current_goal: str


class Relationship(TypedDict, total=False):
    """Relationship dynamic between two entities."""

    entity_a: str
    entity_b: str
    current_dynamic: str


class GlobalState(TypedDict, total=False):
    """Environment and plot-level state."""

    environment: str
    location: str
    time_elapsed: str
    weather: str
    plot_variables: dict[str, str]


class ERL(TypedDict, total=False):
    """Entity and Relationship Ledger: entities, relationships, global state."""

    entities: list[Entity]
    relationships: list[Relationship]
    global_state: GlobalState


def strip_markdown_json(raw: str) -> str:
    """Remove markdown code block wrapper (```) from LLM JSON output."""
    stripped = (raw or "").strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def extract_json_object(text: str) -> str:
    """
    Extract the first top-level JSON object from text.
    Handles LLM responses that prefix/suffix JSON with prose.
    Uses brace matching; does not parse strings, so {/} inside strings may break.
    """
    s = (text or "").strip()
    start = s.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    quote_char: str | None = None
    i = start
    while i < len(s):
        c = s[i]
        if escape:
            escape = False
            i += 1
            continue
        if c == "\\" and in_string:
            escape = True
            i += 1
            continue
        if in_string:
            if c == quote_char:
                in_string = False
                quote_char = None
            i += 1
            continue
        if c in ('"', "'"):
            in_string = True
            quote_char = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
        i += 1
    return ""


def repair_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] (invalid in JSON, common in LLM output)."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def empty_erl() -> ERL:
    """Return a blank ledger."""
    return {
        "entities": [],
        "relationships": [],
        "global_state": {},
    }


def erl_to_json(erl: ERL) -> str:
    """Serialize ERL for prompt injection."""
    return json.dumps(erl, indent=2)


def build_erl_constraint_injections(erl: ERL) -> list[str]:
    """
    Build constraint strings from ERL for injection into Scene Reifier prompts.
    E.g., physical_state "left_hand_injured" -> "Character cannot use left hand."
    """
    injections: list[str] = []
    entities = erl.get("entities") or []
    for e in entities:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        if not name:
            continue
        physical = (e.get("physical_state") or "").strip()
        if physical:
            injections.append(
                f"In this beat, {name} has physical state: {physical}. "
                f"Actions must respect this (e.g., if injured, use alternative limbs or methods)."
            )
        inventory = e.get("inventory")
        if isinstance(inventory, list) and inventory:
            items = ", ".join(str(i) for i in inventory if i)
            if items:
                injections.append(f"{name} has in inventory: {items}. Use only these items if relevant.")
    return injections


def _parse_erl_json(text: str, fallback: ERL | None) -> ERL | None:
    """Parse JSON text to ERL dict. Returns None on parse failure."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    fb = fallback or {}
    result: ERL = {}
    if "entities" in data and isinstance(data["entities"], list):
        result["entities"] = [e for e in data["entities"] if isinstance(e, dict)]
    else:
        result["entities"] = fb.get("entities", [])
    if "relationships" in data and isinstance(data["relationships"], list):
        result["relationships"] = [r for r in data["relationships"] if isinstance(r, dict)]
    else:
        result["relationships"] = fb.get("relationships", [])
    if "global_state" in data and isinstance(data["global_state"], dict):
        result["global_state"] = data["global_state"]
    else:
        result["global_state"] = fb.get("global_state", {})
    return result


def json_to_erl(raw: str, fallback: ERL | None = None) -> ERL:
    """
    Parse JSON string to ERL. Handles markdown-wrapped, prose-prefixed, and
    trailing-comma JSON from LLM output. On failure, return fallback or empty_erl().
    """
    if not (raw or "").strip():
        return fallback if fallback is not None else empty_erl()
    stripped = strip_markdown_json(raw)
    candidates: list[str] = [
        raw.strip(),
        stripped,
        repair_trailing_commas(raw.strip()),
        repair_trailing_commas(stripped),
    ]
    extracted = extract_json_object(stripped)
    if extracted:
        candidates.append(extracted)
        candidates.append(repair_trailing_commas(extracted))
    for c in candidates:
        parsed = _parse_erl_json(c, fallback)
        if parsed is not None:
            return parsed
    logger.warning("ERL JSON parse failed after extraction attempts; using fallback")
    return fallback if fallback is not None else empty_erl()
