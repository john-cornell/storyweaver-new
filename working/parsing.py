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


def _strip_p1_label(text: str) -> str:
    for label in ("Paragraph 1:", "paragraph 1:", "Paragraph 1 :"):
        text = text.replace(label, "", 1).strip()
    return text


def parse_two_paragraphs(raw: str) -> tuple[str, str]:
    """
    Split LLM output into paragraph 1 and 2.
    Tries explicit markers first, then double newline, then regex for "Paragraph 2" variants.
    Ensures we return two segments when the text clearly has two parts so both show in the UI.
    """
    raw = (raw or "").strip()
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

    return (p1 or raw, p2 or "")
