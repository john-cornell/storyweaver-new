"""
Humanize tab handlers: paragraph-by-paragraph humanization with progressive output.
"""

from __future__ import annotations

import logging
from typing import Iterator

from llm import complete, log_llm_outcome, LLMTaskType

logger = logging.getLogger(__name__)

from working.banned import replace_ai_phrases, replace_emdash
from working.prompts import HUMANIZE_SYSTEM


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text on double newline; return non-empty blocks."""
    blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
    return blocks


def _humanize_paragraph_llm(text: str) -> str:
    """Run LLM humanization on a single paragraph. Returns humanized text or original on failure."""
    text = (text or "").strip()
    if not text:
        return text
    try:
        result = complete(text, system=HUMANIZE_SYSTEM, purpose="humanize_tab", task_type=LLMTaskType.WRITE)
        out = (result.text or "").strip()
        if out:
            log_llm_outcome(result.call_id, True)
            return replace_emdash(out)
        log_llm_outcome(result.call_id, False, "empty")
    except Exception as e:
        logger.warning("Humanize tab LLM failed: %s", e)
    return text


def do_humanize_pasted_text(
    input_text: str,
    rule_based: bool,
    llm_humanize: bool,
) -> Iterator[tuple[str, str]]:
    """
    Humanize pasted text paragraph-by-paragraph. Yields (output_text, status_md) for each paragraph.
    If neither option is selected, passes text through unchanged.
    """
    paragraphs = _split_into_paragraphs(input_text or "")
    if not paragraphs:
        yield ("", "*No paragraphs found. Paste text with paragraphs separated by blank lines.*")
        return

    accumulated: list[str] = []
    total = len(paragraphs)

    for i, para in enumerate(paragraphs):
        current = para
        if rule_based:
            current = replace_ai_phrases(current)
        if llm_humanize:
            current = _humanize_paragraph_llm(current)
        accumulated.append(current)
        output_text = "\n\n".join(accumulated)
        status = f"*Processing paragraph {i + 1} of {total}...*"
        yield (output_text, status)

    status_done = f"*Done. Humanized {total} paragraph(s).*"
    yield ("\n\n".join(accumulated), status_done)
