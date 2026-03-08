"""
Consistency and similarity checks for story output.
"""

from __future__ import annotations

import logging
from typing import Any

from llm import complete, log_llm_outcome

from .erl import ERL, erl_to_json
from .tree_utils import get_all_leaf_paths
from .types import Step

logger = logging.getLogger(__name__)

VET_CONSISTENCY_SYSTEM = """\
You are a story consistency checker. You will be given:
1. The Entity & Relationship Ledger (ERL) - current state of characters, injuries, inventory, relationships, location.
2. Story text (current leaf paragraphs).

Your job: identify any contradictions. For example, if the ERL says a character has an injured left arm, but the story text describes them using both arms normally, that is a contradiction.

Output a short list of issues, one per line. If there are no contradictions, output exactly: NONE
Do not invent issues. Only flag clear contradictions between the ERL and the story text."""


def vet_consistency(steps: list[Step] | None, erl: ERL | dict[str, Any] | None = None) -> list[str]:
    """
    Check story for internal consistency against the ERL (facts, character details, injuries, etc.).
    Returns list of issue descriptions; empty if none.
    """
    if not steps:
        return []
    if not erl or not (erl.get("entities") or erl.get("relationships")):
        return []
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return []
    logger.debug("vet_consistency: steps=%d leaves=%d", len(steps), len(leaves))
    combined_text = "\n\n".join(t for _, t in leaves if (t or "").strip())
    if not combined_text.strip():
        return []
    erl_json = erl_to_json(erl)
    prompt = f"""<ERL>\n{erl_json}\n</ERL>\n\n<STORY_TEXT>\n{combined_text}\n</STORY_TEXT>"""
    try:
        result = complete(prompt, system=VET_CONSISTENCY_SYSTEM, purpose="vet_consistency")
        raw = result.text
        if not (raw or "").strip():
            log_llm_outcome(result.call_id, True)
            return []
        lines = [ln.strip() for ln in (raw or "").strip().splitlines() if ln.strip()]
        if not lines:
            log_llm_outcome(result.call_id, True)
            return []
        first = lines[0].upper()
        if first == "NONE" or first.startswith("NONE "):
            log_llm_outcome(result.call_id, True)
            logger.debug("vet_consistency: 0 issues")
            return []
        issues = [ln for ln in lines if ln and not ln.upper().startswith("NONE")]
        log_llm_outcome(result.call_id, True)
        logger.debug("vet_consistency: %d issues", len(issues))
        return issues
    except Exception as e:
        logger.warning("vet_consistency failed: %s", e, exc_info=True)
        return []


def vet_similarity(steps: list[Step] | None) -> list[str]:
    """
    Stub: check for style/tone similarity across paragraphs.
    Returns list of issue descriptions; empty if none.
    """
    _ = steps
    return []
