"""
Parse LLM output into structured paragraphs.
"""

from __future__ import annotations

import re

P2_MARKERS = (
    "Paragraph 2:",
    "paragraph 2:",
    "Paragraph 2 :",
    "**Paragraph 2**",
    "**Paragraph 2:**",
    "Second paragraph:",
    "Paragraph two:",
)

# Prompt fragments the model sometimes echoes; strip from start of raw so they never become paragraph content.
_PROMPT_ECHO_PREFIXES = (
    "Previous paragraph (for flow):",
    "Previous paragraph (for flow):\n",
    "Paragraph to expand:",
    "Paragraph to expand:\n",
)

# Same phrases stripped from the start of each parsed segment (p1/p2) so we never store them as content.
_PROMPT_ECHO_SEGMENT_PREFIXES = (
    "Previous paragraph (for flow):",
    "Paragraph to expand:",
)


def _strip_prompt_echo_from_segment(text: str) -> str:
    """Strip leading prompt-echo phrases from a segment until none remain (case-insensitive)."""
    t = (text or "").strip()
    while True:
        changed = False
        for prefix in _PROMPT_ECHO_SEGMENT_PREFIXES:
            if t.lower().startswith(prefix.lower()):
                t = t[len(prefix) :].strip()
                changed = True
                break
        if not changed:
            break
    return t


def _strip_p1_label(text: str) -> str:
    for label in ("Paragraph 1:", "paragraph 1:", "Paragraph 1 :"):
        text = text.replace(label, "", 1).strip()
    return text


def _strip_leading_label(text: str) -> str:
    """Remove leading 'Paragraph 1:' or 'Paragraph 2:' so we never store labels as content."""
    t = (text or "").strip()
    for label in (
        "Paragraph 1:",
        "paragraph 1:",
        "Paragraph 1 :",
        "Paragraph 2:",
        "paragraph 2:",
        "Paragraph 2 :",
    ):
        if t.startswith(label):
            t = t[len(label) :].strip()
            break
    return t


def _strip_prompt_echoes(raw: str) -> str:
    """Remove common prompt echoes from the start of the LLM response."""
    text = (raw or "").strip()
    for prefix in _PROMPT_ECHO_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text


def parse_two_paragraphs(raw: str) -> tuple[str, str]:
    """
    Split LLM output into paragraph 1 and 2.
    Tries explicit markers first, then double newline, then regex for "Paragraph 2" variants.
    Strips prompt echoes and leading paragraph labels so stored content is prose only.
    """
    raw = _strip_prompt_echoes(raw or "")
    raw = raw.strip()
    p1 = raw
    p2 = ""

    for marker in P2_MARKERS:
        if marker in raw:
            a, _, b = raw.partition(marker)
            p1 = _strip_p1_label(a)
            p2 = b.strip()
            break

    if not p2 and "\n\n" in raw:
        parts = raw.split("\n\n", 1)
        p1 = _strip_p1_label(parts[0])
        p2 = (parts[1].strip() if len(parts) > 1 else "").lstrip()

    # Fallback: look for "paragraph 2" (case-insensitive) anywhere so we split there
    if not p2 and len(raw) > 100:
        match = re.search(r"\bparagraph\s+2\s*:?\s*", raw, re.IGNORECASE)
        if match:
            idx = match.start()
            p1 = _strip_p1_label(raw[:idx].strip())
            p2 = raw[match.end() :].strip()

    if not p2 and p1:
        p2 = ""

    # Remove any leading "Paragraph 1:" / "Paragraph 2:" so we never store labels as content (e.g. model mislabels second block as "Paragraph 1:")
    p1 = _strip_leading_label(p1 or "")
    p2 = _strip_leading_label(p2 or "")

    # Strip prompt-echo phrases from the start of each segment so "Paragraph to expand:\n\n..." never becomes stored content
    p1 = _strip_prompt_echo_from_segment(p1 or "")
    p2 = _strip_prompt_echo_from_segment(p2 or "")

    # If the model output multiple blocks under one label (e.g. four paragraphs after "Paragraph 2:"), keep only the first block so we never store concatenated paragraphs as one.
    if "\n\n" in (p1 or ""):
        p1 = (p1 or "").split("\n\n", 1)[0].strip()
    if "\n\n" in (p2 or ""):
        p2 = (p2 or "").split("\n\n", 1)[0].strip()

    # As a final cleanup, drop any standalone heading lines like "Paragraph 1:" / "Paragraph 2:" that may still be present.
    def _remove_paragraph_heading_lines(text: str) -> str:
        lines = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if stripped.lower() in ("paragraph 1:", "paragraph 2:"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    p1 = _remove_paragraph_heading_lines(p1)
    p2 = _remove_paragraph_heading_lines(p2)

    return (p1 or raw, p2 or "")
