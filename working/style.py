"""
Story narrative style for expansion (POV, tense, etc.). Stub: single default for now; style selection UI later.
"""

from __future__ import annotations

# Default style used when expanding précis or paragraphs. Will be configurable later.
DEFAULT_STYLE: str = "third person past"


def get_style() -> str:
    """Return the current narrative style for story expansion. Stub: always returns DEFAULT_STYLE."""
    return DEFAULT_STYLE
