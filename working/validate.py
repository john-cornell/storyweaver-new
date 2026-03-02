"""
Validate LLM output: reject non-English / non-Latin characters (do not sanitize).
Used to decide whether to accept a response or request a new one.
Allows common English typography (em-dash, smart quotes, ellipsis) in addition to ASCII.
"""

from __future__ import annotations

# Common English typography that LLMs often produce; reject only actual non-Latin (CJK, etc.)
_ALLOWED_TYPOGRAPHY = frozenset(
    "\u2014\u2013\u2018\u2019\u201c\u201d\u2026"  # em-dash, en-dash, quotes, ellipsis
)


def _is_char_allowed(c: str) -> bool:
    """True if char is ASCII printable, whitespace, or allowed typography."""
    if ord(c) >= 32 and ord(c) <= 126:
        return True
    if c in "\n\t\r":
        return True
    if c in _ALLOWED_TYPOGRAPHY:
        return True
    return False


def is_english_only(text: str) -> bool:
    """
    True iff text contains only allowed characters: ASCII printable (32-126),
    newline/tab/carriage-return, and common English typography (em-dash, en-dash,
    smart quotes, ellipsis). CJK and other non-Latin scripts cause False.
    """
    if not text:
        return True
    for c in text:
        if not _is_char_allowed(c):
            return False
    return True


def get_first_rejected_char(text: str) -> tuple[int, str] | None:
    """
    Return (index, char_info) of first character not in allowed set, or None.
    char_info is e.g. "U+2014" for debugging.
    """
    for i, c in enumerate(text):
        if not _is_char_allowed(c):
            return (i, f"U+{ord(c):04X}")
    return None
