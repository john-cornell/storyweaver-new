"""
Validate LLM output: reject non-English / non-Latin characters (do not sanitize).
Used to decide whether to accept a response or request a new one.
"""

from __future__ import annotations


def is_english_only(text: str) -> bool:
    """
    True iff text contains only ASCII printable (32-126) and newline/tab/carriage-return.
    Any other character (e.g. Chinese, CJK) causes False. Empty string is accepted.
    """
    if not text:
        return True
    for c in text:
        if ord(c) >= 32 and ord(c) <= 126:
            continue
        if c in "\n\t\r":
            continue
        return False
    return True
