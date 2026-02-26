"""
Stubs for consistency and similarity checks. Will be implemented to vet story output.
"""

from __future__ import annotations

from .types import Step


def vet_consistency(steps: list[Step] | None) -> list[str]:
    """
    Stub: check story for internal consistency (facts, timeline, character details).
    Returns list of issue descriptions; empty if none.
    """
    _ = steps
    return []


def vet_similarity(steps: list[Step] | None) -> list[str]:
    """
    Stub: check for style/tone similarity across paragraphs.
    Returns list of issue descriptions; empty if none.
    """
    _ = steps
    return []
