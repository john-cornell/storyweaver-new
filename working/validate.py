"""
Validate LLM output: reject non-English / non-Latin characters (do not sanitize).
Used to decide whether to accept a response or request a new one.
Allows common English typography (en-dash, smart quotes, ellipsis) in addition to ASCII.
Em-dash is banned; use contains_banned_chars for that check.
"""

from __future__ import annotations

from .banned import BANNED_CHARS

# Common English typography that LLMs often produce; reject only actual non-Latin (CJK, etc.).
# Excludes em-dash (U+2014) which is in BANNED_CHARS.
# Latin-1 Supplement (U+00A0-U+00FF): non-breaking space, accented letters (café, résumé, naïve).
_ALLOWED_TYPOGRAPHY = frozenset(
    "\u2013\u2018\u2019\u201c\u201d\u2026"  # en-dash, smart quotes, ellipsis
)
# Latin-1 Supplement: allow accented Latin letters and common symbols used in English.
_LATIN1_ALLOWED = frozenset(chr(c) for c in range(0x00A0, 0x0100) if chr(c) != "\u2014")  # exclude em-dash


def _is_char_allowed(c: str) -> bool:
    """True if char is ASCII printable, whitespace, or allowed typography."""
    if ord(c) >= 32 and ord(c) <= 126:
        return True
    if c in "\n\t\r":
        return True
    if c in _ALLOWED_TYPOGRAPHY:
        return True
    if c in _LATIN1_ALLOWED:
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


def contains_banned_chars(text: str) -> bool:
    """True if text contains any character in BANNED_CHARS."""
    if not text:
        return False
    for c in text:
        if c in BANNED_CHARS:
            return True
    return False


def get_first_banned_char(text: str) -> tuple[int, str] | None:
    """Return (index, char_info) of first banned character, or None."""
    for i, c in enumerate(text):
        if c in BANNED_CHARS:
            return (i, f"U+{ord(c):04X}")
    return None
