"""
State extraction: parse newly generated text and update the Entity & Relationship Ledger.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from llm import complete, log_llm_outcome

from .erl import ERL, erl_to_json, json_to_erl, strip_markdown_json

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM = """\
You are the State Manager. Compare the NEW_TEXT against the OLD_STATE.
Identify any changes to entity health, inventory, location, or relationship dynamics.
Output an updated, valid JSON object reflecting these changes. If no changes occurred, output the original JSON.
Output ONLY valid JSON—no explanation, no markdown, no other text. The JSON must have keys: entities (array), relationships (array), global_state (object)."""


def extract_state_updates(new_text: str, current_erl: ERL) -> ERL:
    """
    Parse new_text for state changes and merge into current_erl.
    Returns updated ERL; on parse failure, returns current_erl unchanged.
    """
    if not (new_text or "").strip():
        return current_erl
    n_before = len(current_erl.get("entities") or [])
    old_state_json = erl_to_json(current_erl)
    user_prompt = f"""<OLD_STATE>\n{old_state_json}\n</OLD_STATE>\n\n<NEW_TEXT>\n{new_text.strip()}\n</NEW_TEXT>"""
    try:
        result = complete(user_prompt, system=EXTRACTOR_SYSTEM, purpose="extract_state_updates")
        raw = result.text
        if not (raw or "").strip():
            log_llm_outcome(result.call_id, False, "empty")
            return current_erl
        stripped = strip_markdown_json(raw)
        updated = json_to_erl(stripped, fallback=current_erl)
        n_after = len(updated.get("entities") or [])
        log_llm_outcome(result.call_id, updated != current_erl)
        logger.debug("ERL extract: input %d chars, entities before=%d after=%d", len(new_text), n_before, n_after)
        return updated
    except Exception as e:
        logger.warning("ERL state extraction failed: %s; retaining previous state", e)
        return current_erl
