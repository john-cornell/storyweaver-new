"""
Tree utilities for interactive branching story: path traversal, node lookup.
"""

from __future__ import annotations

from typing import Any


def _parse_beats_from_outline(text: str) -> list[str]:
    """
    Parse beat outline (## Beginning, ## Middle, ## End) into list of beat strings.
    Falls back to beat_extractor-style numbered list parsing.
    """
    if not (text or "").strip():
        return []
    lines = text.strip().split("\n")
    beats: list[str] = []
    import re
    pattern = re.compile(r"^\s*(?:\d+[\.\)]\s*|[-*]\s*)(.+)$")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("##"):
            continue
        m = pattern.match(line)
        if m:
            beat = m.group(1).strip()
            if beat:
                beats.append(beat)
        elif len(line) < 150 and not line.lower().startswith("output"):
            beats.append(line)
    return beats


def get_prose_to_node(
    nodes: list[dict[str, Any]],
    node_id: int,
) -> str:
    """Get full prose from root to the given node (inclusive), in reading order."""
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    if node_id not in by_id:
        return ""
    path: list[dict[str, Any]] = []
    current = by_id.get(node_id)
    while current:
        path.append(current)
        pid = current.get("parent_id")
        current = by_id.get(pid) if pid is not None else None
    path.reverse()
    return "\n\n".join((n.get("prose_text") or "").strip() for n in path if (n.get("prose_text") or "").strip())


def get_unexplored_nodes(
    nodes: list[dict[str, Any]],
    choices: list[dict[str, Any]],
) -> list[int]:
    """
    Return node ids that have choices but no child for one or both options.
    A node is unexplored if it has a choice record but we haven't generated prose for one/both branches.
    """
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    choice_by_node = {c["node_id"]: c for c in choices if isinstance(c, dict) and c.get("node_id") is not None}
    children_of: dict[int, set[str]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        pid = n.get("parent_id")
        if pid is None:
            continue
        label = n.get("choice_label") or ""
        if pid not in children_of:
            children_of[pid] = set()
        children_of[pid].add(label)
    unexplored: list[int] = []
    for node_id, c in choice_by_node.items():
        children = children_of.get(node_id, set())
        if "A" not in children or "B" not in children:
            unexplored.append(node_id)
    return unexplored


def parse_beats(idea: str, content_is_beats: bool) -> list[str]:
    """Parse beats from idea text. If content_is_beats, parse from outline format; else use beat_extractor."""
    if not (idea or "").strip():
        return []
    if content_is_beats:
        return _parse_beats_from_outline(idea.strip())
    from ..beat_extractor import extract_beats
    return extract_beats(idea.strip())
