"""
Paragraph tree: traverse, find first leaf, replace at path, render to markdown or HTML.
Tree = str (leaf) | {"left": Tree, "right": Tree} (branch).
Branch nodes must be dicts with exactly "left" and "right" keys.
Path = (step_idx: int, key: "paragraph_1"|"paragraph_2", indices: tuple[int, ...]).
"""

from __future__ import annotations

import html
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


def get_leaves_with_lineage(
    steps: list[Step] | None,
) -> list[tuple[int, int, int | None, int | None, str]]:
    """
    All leaves in depth-first order with lineage.
    Returns [(round, para_num, parent_round, parent_para_num, text), ...].
    Round 1 = roots; parent is None for roots.
    In a fully expanded tree all leaves are at the deepest round; use
    get_all_nodes_with_lineage for full-history trace including intermediate rounds.
    """
    if not steps:
        return []
    out: list[tuple[int, int, int | None, int | None, str]] = []
    round_counters: dict[int, int] = {}
    parent_stack: list[tuple[int, int]] = []

    def visit(
        node: Any,
        step_idx: int,
        key: str,
        indices: tuple[int, ...],
    ) -> None:
        depth = len(indices)
        round_num = depth + 1
        round_counters[round_num] = round_counters.get(round_num, 0) + 1
        para_num = round_counters[round_num]
        parent_round, parent_para = parent_stack[-1] if parent_stack else (None, None)

        if _is_leaf(node):
            text = (node or "").strip() if isinstance(node, str) else ""
            out.append((round_num, para_num, parent_round, parent_para, text))
            return
        if isinstance(node, dict) and "left" in node and "right" in node:
            parent_stack.append((round_num, para_num))
            visit(node["left"], step_idx, key, indices + (0,))
            visit(node["right"], step_idx, key, indices + (1,))
            parent_stack.pop()
            return
        # Malformed node: neither leaf nor branch; treat as empty leaf for robustness
        out.append((round_num, para_num, parent_round, parent_para, ""))

    for step_idx, step in enumerate(steps):
        for key in ("paragraph_1", "paragraph_2"):
            visit(_get_tree(step, key), step_idx, key, ())
    return out


PathToOriginal = dict[tuple[int, str, tuple[int, ...]], str]


def get_all_nodes_with_lineage(
    steps: list[Step] | None,
    path_to_original: PathToOriginal,
) -> list[tuple[int, int, int | None, int | None, str]]:
    """
    All nodes (branches and leaves) in depth-first order with lineage.
    For leaves: text = node content. For branches: text = path_to_original[path].
    Use for full-history trace so Steps 1–4 (branches) are shown, not only Step 5 (leaves).
    """
    if not steps:
        return []
    out: list[tuple[int, int, int | None, int | None, str]] = []
    round_counters: dict[int, int] = {}
    parent_stack: list[tuple[int, int]] = []

    def visit(
        node: Any,
        step_idx: int,
        key: str,
        indices: tuple[int, ...],
    ) -> None:
        depth = len(indices)
        round_num = depth + 1
        round_counters[round_num] = round_counters.get(round_num, 0) + 1
        para_num = round_counters[round_num]
        parent_round, parent_para = parent_stack[-1] if parent_stack else (None, None)
        path = (step_idx, key, indices)

        if _is_leaf(node):
            text = (node or "").strip() if isinstance(node, str) else ""
            out.append((round_num, para_num, parent_round, parent_para, text))
            return
        if isinstance(node, dict) and "left" in node and "right" in node:
            branch_text = path_to_original.get(path, "—")
            out.append((round_num, para_num, parent_round, parent_para, branch_text))
            parent_stack.append((round_num, para_num))
            visit(node["left"], step_idx, key, indices + (0,))
            visit(node["right"], step_idx, key, indices + (1,))
            parent_stack.pop()
            return
        out.append((round_num, para_num, parent_round, parent_para, ""))

    for step_idx, step in enumerate(steps):
        for key in ("paragraph_1", "paragraph_2"):
            visit(_get_tree(step, key), step_idx, key, ())
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


def is_first_leaf_in_reading_order(steps: list[Step] | None, path: LeafPath) -> bool:
    """True iff path is the first leaf in depth-first reading order."""
    if not steps:
        return False
    leaves = get_all_leaf_paths(steps)
    return bool(leaves) and leaves[0][0] == path


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


# Collapsible tree: summary preview length for leaf nodes.
_TREE_PREVIEW_CHARS = 72


def _node_to_html(
    node: Any,
    step_idx: int,
    key: str,
    indices: tuple[int, ...],
) -> str:
    """Recursively build <details>/<summary> HTML for one tree node. All leaf and path text is HTML-escaped to prevent XSS."""
    path_str = path_label(step_idx, key, indices)
    if _is_leaf(node):
        text = (node or "").strip() or ""
        preview = (text[: _TREE_PREVIEW_CHARS] + "…") if len(text) > _TREE_PREVIEW_CHARS else text
        safe_preview = html.escape(preview)
        safe_full = html.escape(text)
        return (
            f'<details class="sw-tree-leaf" style="margin-left: 0.5em;">'
            f"<summary><strong>{html.escape(path_str)}</strong> — {safe_preview}</summary>"
            f'<pre style="white-space: pre-wrap; margin: 0.4em 0 0 1em; font-size: 0.9em;">{safe_full}</pre>'
            "</details>"
        )
    if isinstance(node, dict) and "left" in node and "right" in node:
        left_html = _node_to_html(node["left"], step_idx, key, indices + (0,))
        right_html = _node_to_html(node["right"], step_idx, key, indices + (1,))
        return (
            f'<details class="sw-tree-branch" open style="margin-left: 0.5em;">'
            f"<summary><strong>{html.escape(path_str)}</strong> — split → L | R</summary>"
            f'<div style="margin-left: 0.5em;">{left_html}{right_html}</div>'
            "</details>"
        )
    return f'<details><summary>{html.escape(path_str)}</summary><em>—</em></details>'


def render_tree_to_html(steps: list[Step] | None) -> str:
    """
    Render full story tree as collapsible HTML (expand/collapse per node).
    Step → P1 / P2 (précis split), then each branch L/R openable for real debuggability.
    All user-supplied text (leaf content, path labels) is HTML-escaped to prevent XSS.
    """
    if not steps:
        return (
            "<p><em>No story yet. Use Write → Start to create the first two paragraphs.</em></p>"
        )
    parts: list[str] = []
    parts.append(
        '<div class="sw-tree-root" style="font-family: inherit; font-size: 0.95em;">'
    )
    for i, step in enumerate(steps):
        p1 = _get_tree(step, "paragraph_1")
        p2 = _get_tree(step, "paragraph_2")
        step_label = html.escape(f"Step {i + 1}")
        p1_html = _node_to_html(p1, i, "paragraph_1", ())
        p2_html = _node_to_html(p2, i, "paragraph_2", ())
        parts.append(
            f'<details class="sw-tree-step" open style="margin-bottom: 0.6em;">'
            f"<summary style=\"font-weight: bold;\">▶ {step_label} — P1 | P2 (précis split)</summary>"
            f'<div style="margin-left: 1em;">'
            f"<details open><summary><strong>P1</strong></summary><div style=\"margin-left: 0.5em;\">{p1_html}</div></details>"
            f"<details open><summary><strong>P2</strong></summary><div style=\"margin-left: 0.5em;\">{p2_html}</div></details>"
            f"</div></details>"
        )
    parts.append("</div>")
    return "\n".join(parts)
