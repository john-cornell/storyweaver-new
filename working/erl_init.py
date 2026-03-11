"""
ERL initialization: bootstrap the Entity & Relationship Ledger from précis and first paragraphs.
"""

from __future__ import annotations

import logging

from llm import complete, log_llm_outcome, LLMTaskType

from .erl import ERL, empty_erl, json_to_erl, strip_markdown_json

logger = logging.getLogger(__name__)

INIT_SYSTEM = """\
You are the State Manager. Extract all characters, their physical states, inventory, goals, relationships, and environmental details from the provided text.

Output a valid JSON object with exactly these keys:
- entities: array of objects, each with name (string), physical_state (string), inventory (array of strings), current_goal (string)
- relationships: array of objects, each with entity_a (string), entity_b (string), current_dynamic (string)
- global_state: object with environment (string), location (string), time_elapsed (string), weather (string), plot_variables (object)

Include every named character as an entity. Include relationships between characters. Include location, weather, and other environmental details in global_state.
Output ONLY valid JSON—no explanation, no markdown, no other text."""


def initialize_erl(precis_text: str, initial_paragraphs: str) -> ERL:
    """
    Bootstrap ERL from précis and initial story paragraphs.
    Returns empty ERL on failure.
    """
    combined = f"{precis_text.strip()}\n\n{initial_paragraphs.strip()}".strip()
    if not combined:
        return empty_erl()
    logger.debug("ERL init: input %d chars", len(combined))
    try:
        llm_result = complete(combined, system=INIT_SYSTEM, purpose="erl_init", task_type=LLMTaskType.PLAN)
        raw = llm_result.text
        if not (raw or "").strip():
            log_llm_outcome(llm_result.call_id, False, "empty")
            return empty_erl()
        stripped = strip_markdown_json(raw)
        erl_result = json_to_erl(stripped, fallback=empty_erl())
        n_ent = len(erl_result.get("entities") or [])
        n_rel = len(erl_result.get("relationships") or [])
        log_llm_outcome(llm_result.call_id, n_ent > 0 or n_rel > 0)
        logger.debug("ERL init: entities=%d relationships=%d", n_ent, n_rel)
        return erl_result
    except Exception as e:
        logger.warning("ERL init failed: %s; using empty ERL", e)
        return empty_erl()
