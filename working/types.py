"""
Types for the working draft: steps, paragraph tree, and expansion history.
"""

from __future__ import annotations

from typing import Any, TypedDict

# A paragraph is either a leaf (str) or an expanded node with two children.
# Branch dicts must contain exactly "left" and "right" keys (see tree_utils).
Tree = str | dict[str, Any]


class Step(TypedDict, total=False):
    """One working step: two paragraph roots (each a Tree)."""

    paragraph_1: Tree
    paragraph_2: Tree


class HistoryEntry(TypedDict, total=False):
    """One expansion event: which paragraph was expanded and the two replacements."""

    path_label: str
    original: str
    left: str
    right: str
    step_index: int
    paragraph_key: str
    indices: list[int]
