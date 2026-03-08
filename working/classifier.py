"""
Narrative block classifier: routes text to TRANSITION or SCENE expansion prompts.
"""

from __future__ import annotations

import logging
from typing import Literal

from llm import complete, log_llm_outcome

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM = """\
You are a Narrative Classifier. Analyze the following text block and output exactly one word: either TRANSITION or SCENE.
- Output TRANSITION if the text describes travel, the passage of time, or environmental shifts.
- Output SCENE if the text contains a character making a decision, discovering information, or interacting directly with another character/object."""


def classify_block(text: str) -> Literal["TRANSITION", "SCENE"]:
    """
    Classify a text block as TRANSITION (travel/time/environment) or SCENE (character interaction/decision).
    Defaults to SCENE if unclear (higher-quality output is the safer default).
    """
    if not (text or "").strip():
        return "SCENE"
    try:
        result = complete(text.strip(), system=CLASSIFIER_SYSTEM, purpose="classify_block")
        raw = result.text
        classification = (raw or "").strip().upper()
        block_type = "SCENE" if "SCENE" in classification else "TRANSITION"
        log_llm_outcome(result.call_id, True)
        logger.debug("Classified as %s (input %d chars)", block_type, len(text))
        return block_type
    except Exception as e:
        logger.warning("Classifier failed: %s; defaulting to SCENE", e)
        return "SCENE"
