"""
Beat Extractor: decompose summary paragraphs into atomic Moment-Beats (Hidden Events).
Used by the Micro-Beat Protocol for vertical expansion (temporal stretching).
"""

from __future__ import annotations

import logging
import re

from llm import complete, log_llm_outcome

logger = logging.getLogger(__name__)

BEAT_EXTRACTOR_SYSTEM = """\
You are the Beat Extractor. Analyze the input text and extract all 'Hidden Events.'
A Hidden Event is any action that is currently summarized.
Generic rules: Every verb in a summary is a potential scene. Every transition word (e.g., "Eventually," "After," "Then") marks a "Missing Moment."
Output these as a numbered list of atomic beats. Each beat should be a short phrase (e.g., "Picking the lock." or "Scaling the wall.").
Output ONLY the numbered list—no headings, no explanation, no other text. Use the format: 1. Beat description. 2. Next beat. etc."""


def extract_beats(text: str) -> list[str]:
    """
    Extract atomic Moment-Beats (implicit actions / hidden events) from a summary paragraph.
    Returns a list of beat strings. Returns empty list on failure or empty input.
    """
    if not (text or "").strip():
        return []
    try:
        result = complete(text.strip(), system=BEAT_EXTRACTOR_SYSTEM, purpose="extract_beats")
        raw = result.text
        if not (raw or "").strip():
            log_llm_outcome(result.call_id, False, "empty")
            return []
        beats = _parse_beats(raw)
        log_llm_outcome(result.call_id, bool(beats), "empty" if not beats else None)
        logger.debug("Beat extractor: input %d chars, extracted %d beats", len(text), len(beats))
        return beats
    except Exception as e:
        logger.warning("Beat extractor failed: %s; returning empty list", e)
        return []


def _parse_beats(raw: str) -> list[str]:
    """
    Parse numbered list output into list of beat strings.
    Handles formats: "1. Beat.\n2. Next." or "1) Beat\n2) Next" or markdown.
    """
    lines = (raw or "").strip().split("\n")
    beats: list[str] = []
    # Match "1. text" or "1) text" or "- text" at start
    pattern = re.compile(r"^\s*(?:\d+[\.\)]\s*|[-*]\s*)(.+)$")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            beat = m.group(1).strip()
            if beat:
                beats.append(beat)
        else:
            # Line doesn't match pattern; skip meta-output (headings, markdown, etc.)
            skip = (
                line.startswith("```")
                or line.lower().startswith("here are")
                or line.lower().startswith("the hidden")
                or line.lower().startswith("the beats")
            )
            if not skip and len(line) < 120:
                beats.append(line)
    return beats
