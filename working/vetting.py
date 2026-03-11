"""
Consistency and similarity checks for story output.
"""

from __future__ import annotations

import logging
from typing import Any

from config import VettingConfig
from llm import complete, log_llm_outcome, LLMTaskType

from .erl import ERL, erl_to_json
from .tree_utils import get_all_leaf_paths
from .types import Step

logger = logging.getLogger(__name__)

CONSISTENCY_TAGS = (
    "physical_state",
    "inventory",
    "current_goal",
    "relationship_dynamic",
    "global_state",
)

VET_CONSISTENCY_SYSTEM_FULL = """\
You are a story consistency checker. You will be given:
1. The Entity & Relationship Ledger (ERL) - current state of characters, injuries, inventory, relationships, location.
2. Story text (current leaf paragraphs).

Your job: identify any contradictions. For example, if the ERL says a character has an injured left arm, but the story text describes them using both arms normally, that is a contradiction.

Output a short list of issues, one per line. If there are no contradictions, output exactly: NONE
Do not invent issues. Only flag clear contradictions between the ERL and the story text."""

VET_CONSISTENCY_SYSTEM_SINGLE = """\
You are a story consistency checker. You will be given:
1. The Entity & Relationship Ledger (ERL) - current state of characters, injuries, inventory, relationships, location.
2. Story text (current leaf paragraphs).

Check each of these facets: physical_state, inventory, current_goal, relationship_dynamic, global_state.
Only flag clear contradictions between the ERL and the story text. Do not invent issues.

Output a short list of issues, one per line. If there are no contradictions, output exactly: NONE"""


def _build_story_text(steps: list[Step]) -> str:
    """Extract combined leaf text from steps. Returns empty string if no leaves."""
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return ""
    return "\n\n".join(t for _, t in leaves if (t or "").strip())


def _parse_consistency_response(raw: str) -> list[str]:
    """Parse LLM output. NONE -> []. Else return non-empty lines as issues."""
    if not (raw or "").strip():
        return []
    lines = [ln.strip() for ln in (raw or "").strip().splitlines() if ln.strip()]
    if not lines:
        return []
    first = lines[0].upper()
    if first == "NONE" or first.startswith("NONE "):
        return []
    return [ln for ln in lines if ln and not ln.upper().startswith("NONE")]


def _erl_subset_for_tag(erl: ERL | dict[str, Any], tag: str) -> dict[str, Any]:
    """Return minimal ERL dict with only the relevant key(s) for that tag."""
    entities = erl.get("entities") or []
    relationships = erl.get("relationships") or []
    global_state = erl.get("global_state") or {}

    if tag == "physical_state":
        filtered = [
            {"name": e.get("name", ""), "physical_state": e.get("physical_state", "")}
            for e in entities
            if isinstance(e, dict) and e.get("physical_state")
        ]
        return {"entities": filtered, "relationships": [], "global_state": {}}
    if tag == "inventory":
        filtered = [
            {"name": e.get("name", ""), "inventory": e.get("inventory", [])}
            for e in entities
            if isinstance(e, dict) and e.get("inventory")
        ]
        return {"entities": filtered, "relationships": [], "global_state": {}}
    if tag == "current_goal":
        filtered = [
            {"name": e.get("name", ""), "current_goal": e.get("current_goal", "")}
            for e in entities
            if isinstance(e, dict) and e.get("current_goal")
        ]
        return {"entities": filtered, "relationships": [], "global_state": {}}
    if tag == "relationship_dynamic":
        filtered = [r for r in relationships if isinstance(r, dict) and r.get("current_dynamic")]
        return {"entities": [], "relationships": filtered, "global_state": {}}
    if tag == "global_state":
        if not global_state or not isinstance(global_state, dict):
            return {"entities": [], "relationships": [], "global_state": {}}
        return {"entities": [], "relationships": [], "global_state": global_state}
    return {"entities": [], "relationships": [], "global_state": {}}


def _is_subset_empty(subset: dict[str, Any]) -> bool:
    """True if subset has no data to check."""
    entities = subset.get("entities") or []
    relationships = subset.get("relationships") or []
    global_state = subset.get("global_state") or {}
    return not entities and not relationships and not global_state


def _run_vet_full(erl: ERL | dict[str, Any], story_text: str) -> list[str]:
    """Full ERL dump, one LLM call (legacy behavior)."""
    erl_json = erl_to_json(erl)
    prompt = f"""<ERL>\n{erl_json}\n</ERL>\n\n<STORY_TEXT>\n{story_text}\n</STORY_TEXT>"""
    try:
        result = complete(prompt, system=VET_CONSISTENCY_SYSTEM_FULL, purpose="vet_consistency", task_type=LLMTaskType.PLAN)
        issues = _parse_consistency_response(result.text)
        log_llm_outcome(result.call_id, True)
        return issues
    except Exception as e:
        logger.warning("vet_consistency (full) failed: %s", e, exc_info=True)
        return []


def _run_vet_single(erl: ERL | dict[str, Any], story_text: str) -> list[str]:
    """One call with explicit tag checklist."""
    erl_json = erl_to_json(erl)
    prompt = f"""<ERL>\n{erl_json}\n</ERL>\n\n<STORY_TEXT>\n{story_text}\n</STORY_TEXT>"""
    try:
        result = complete(prompt, system=VET_CONSISTENCY_SYSTEM_SINGLE, purpose="vet_consistency", task_type=LLMTaskType.PLAN)
        issues = _parse_consistency_response(result.text)
        log_llm_outcome(result.call_id, True)
        return issues
    except Exception as e:
        logger.warning("vet_consistency (single) failed: %s", e, exc_info=True)
        return []


def _run_vet_multi(erl: ERL | dict[str, Any], story_text: str) -> list[str]:
    """Multiple calls, one per tag, each with filtered ERL."""
    all_issues: list[str] = []
    for tag in CONSISTENCY_TAGS:
        subset = _erl_subset_for_tag(erl, tag)
        if _is_subset_empty(subset):
            continue
        subset_json = erl_to_json(subset)
        prompt = f"""<ERL>\n{subset_json}\n</ERL>\n\n<STORY_TEXT>\n{story_text}\n</STORY_TEXT>"""
        system = f"""You are a story consistency checker for the facet: {tag}.
Compare the ERL (which contains only {tag}-related data) against the story text.
Identify contradictions for this facet only. Output issues one per line, or exactly: NONE"""
        try:
            result = complete(
                prompt, system=system, purpose=f"vet_consistency_{tag}", task_type=LLMTaskType.PLAN
            )
            issues = _parse_consistency_response(result.text)
            log_llm_outcome(result.call_id, True)
            for issue in issues:
                all_issues.append(f"[{tag}] {issue}")
        except Exception as e:
            logger.warning("vet_consistency (multi, %s) failed: %s", tag, e, exc_info=True)
    return all_issues


def vet_consistency(steps: list[Step] | None, erl: ERL | dict[str, Any] | None = None) -> list[str]:
    """
    Check story for internal consistency against the ERL (facts, character details, injuries, etc.).
    Returns list of issue descriptions; empty if none.
    Mode: full (legacy full ERL), single (checklist), multi (per-tag). See VET_CONSISTENCY_MODE.
    """
    if not steps:
        return []
    if not erl or not (erl.get("entities") or erl.get("relationships")):
        return []
    story_text = _build_story_text(steps)
    if not story_text.strip():
        return []
    logger.debug("vet_consistency: steps=%d", len(steps))
    mode = VettingConfig.from_env().consistency_mode
    if mode == "full":
        return _run_vet_full(erl, story_text)
    if mode == "multi":
        return _run_vet_multi(erl, story_text)
    return _run_vet_single(erl, story_text)


def vet_similarity(steps: list[Step] | None) -> list[str]:
    """
    Stub: check for style/tone similarity across paragraphs.
    Returns list of issue descriptions; empty if none.
    """
    _ = steps
    return []
