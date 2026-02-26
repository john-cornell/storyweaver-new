"""
Paragraph tree: traverse, find first leaf, replace at path, render to markdown.
Tree = str (leaf) | {"left": Tree, "right": Tree} (branch).
Branch nodes must be dicts with exactly "left" and "right" keys.
Path = (step_idx: int, key: "paragraph_1"|"paragraph_2", indices: tuple[int, ...]).
"""

from __future__ import annotations

from typing import Any

from .types import Step

# Type alias for path: (step_index, "paragraph_1"|"paragraph_2", [0|1, ...])
LeafPath = tuple[int, str, tuple[int, ...]]


def _is_leaf(node: Any) -> bool:
    return isinstance(node, str)


def _get_tree(step: Step, key: str) -> Any:
    return step.get(key) or ""


def path_label(step_idx: int, key: str, indices: tuple[int, ...]) -> str:
    """Human-readable path for history (e.g. 'Step 1, P1, L, R')."""
    parts = [f"Step {step_idx + 1}", "P1" if key == "paragraph_1" else "P2"]
    for i in indices:
        parts.append("L" if i == 0 else "R")
    return ", ".join(parts)


def _traverse(
    node: Any,
    step_idx: int,
    key: str,
    indices: tuple[int, ...],
    path_out: list[LeafPath],
    text_out: list[str],
) -> None:
    if _is_leaf(node):
        path_out.append((step_idx, key, indices))
        text_out.append(node.strip() if isinstance(node, str) else "")
        return
    if isinstance(node, dict) and "left" in node and "right" in node:
        _traverse(node["left"], step_idx, key, indices + (0,), path_out, text_out)
        _traverse(node["right"], step_idx, key, indices + (1,), path_out, text_out)


def get_all_leaf_paths(steps: list[Step] | None) -> list[tuple[LeafPath, str]]:
    """
    All leaf paths in depth-first order across steps. Returns [(path, text), ...].
    Used for expand-round: split every current leaf (2→4→8→…).
    """
    if not steps:
        return []
    out: list[tuple[LeafPath, str]] = []
    for step_idx, step in enumerate(steps):
        for key in ("paragraph_1", "paragraph_2"):
            path_out: list[LeafPath] = []
            text_out: list[str] = []
            _traverse(_get_tree(step, key), step_idx, key, (), path_out, text_out)
            for p, t in zip(path_out, text_out):
                out.append((p, t))
    return out


def get_previous_leaf_in_reading_order(
    steps: list[Step] | None,
    path: LeafPath,
) -> str | None:
    """
    Text of the leaf that immediately precedes the given path in reading order (depth-first).
    Returns None if there is no previous leaf (e.g. first paragraph in the story).
    """
    if not steps:
        return None
    leaves = get_all_leaf_paths(steps)
    for i, (p, text) in enumerate(leaves):
        if p == path and i > 0:
            return leaves[i - 1][1]
    return None


def get_first_leaf_path(steps: list[Step] | None) -> tuple[LeafPath | None, str]:
    """
    Depth-first first leaf in steps. Returns (path, text) or (None, "").
    """
    if not steps:
        return (None, "")
    for step_idx, step in enumerate(steps):
        for key in ("paragraph_1", "paragraph_2"):
            tree = _get_tree(step, key)
            if _is_leaf(tree):
                path: LeafPath = (step_idx, key, ())
                text = (tree.strip() if isinstance(tree, str) else "")
                return (path, text)
            if isinstance(tree, dict) and "left" in tree and "right" in tree:
                path_out: list[LeafPath] = []
                text_out: list[str] = []
                _traverse(tree, step_idx, key, (), path_out, text_out)
                if path_out:
                    return (path_out[0], text_out[0])
    return (None, "")


def _set_at_path(
    node: Any,
    indices: tuple[int, ...],
    left_text: str,
    right_text: str,
) -> Any:
    if not indices:
        return {"left": left_text, "right": right_text}
    # Invalid path: at a leaf but indices non-empty; leave tree unchanged.
    if not isinstance(node, dict) or "left" not in node or "right" not in node:
        return node
    i, rest = indices[0], indices[1:]
    if i == 0:
        return {
            "left": _set_at_path(node["left"], rest, left_text, right_text),
            "right": node["right"],
        }
    return {
        "left": node["left"],
        "right": _set_at_path(node["right"], rest, left_text, right_text),
    }


def set_leaf_at_path(
    steps: list[Step],
    path: LeafPath,
    left_text: str,
    right_text: str,
) -> list[Step]:
    """Return new steps with the leaf at path replaced by a branch (left, right).
    path must be a leaf path from get_first_leaf_path.
    """
    step_idx, key, indices = path
    if step_idx >= len(steps):
        return list(steps)
    step = dict(steps[step_idx])
    tree = _get_tree(step, key)
    new_tree = _set_at_path(tree, indices, left_text, right_text)
    step[key] = new_tree
    return steps[:step_idx] + [step] + steps[step_idx + 1 :]


def _count_words_in_node(node: Any) -> int:
    """Sum word count for this node (leaf: len(s.split()); branch: recurse)."""
    if _is_leaf(node):
        return len((node or "").split()) if isinstance(node, str) else 0
    if isinstance(node, dict) and "left" in node and "right" in node:
        return _count_words_in_node(node["left"]) + _count_words_in_node(node["right"])
    return 0


def count_words_in_steps(steps: list[Step] | None) -> int:
    """Total word count across all leaf paragraphs in the story tree."""
    if not steps:
        return 0
    total = 0
    for step in steps:
        for key in ("paragraph_1", "paragraph_2"):
            total += _count_words_in_node(_get_tree(step, key))
    return total


def _render_tree(node: Any, depth: int, lines: list[str], indent: str = "  ") -> None:
    prefix = indent * depth
    if _is_leaf(node):
        text = (node or "").strip() or "*—*"
        lines.append(f"{prefix}{text}")
        return
    if isinstance(node, dict) and "left" in node and "right" in node:
        _render_tree(node["left"], depth + 1, lines, indent)
        _render_tree(node["right"], depth + 1, lines, indent)
        return
    lines.append(f"{prefix}*—*")


def get_story_prose_only(steps: list[Step] | None) -> str:
    """
    Return the current story as plain prose only: all leaf paragraphs in reading order,
    joined by double newlines. No step labels, no paragraph titles—just story text.
    """
    if not steps:
        return ""
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return ""
    return "\n\n".join((t or "").strip() for _, t in leaves).strip()


def render_tree_to_markdown(steps: list[Step] | None) -> str:
    """Render full story tree as markdown (depth-first, indented)."""
    if not steps:
        return "*No story yet. Use Write → Start to create the first two paragraphs.*"
    lines: list[str] = []
    for i, step in enumerate(steps):
        lines.append(f"### Step {i + 1}")
        p1 = _get_tree(step, "paragraph_1")
        p2 = _get_tree(step, "paragraph_2")
        lines.append("**Paragraph 1:**")
        _render_tree(p1, 0, lines)
        lines.append("**Paragraph 2:**")
        _render_tree(p2, 0, lines)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip()
