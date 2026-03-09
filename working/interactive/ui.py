"""
Interactive mode UI: path tree HTML, prose display.
"""

from __future__ import annotations

from typing import Any

from .tree_utils import get_prose_to_node


def build_path_tree_html(
    nodes: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    current_node_id: int,
) -> str:
    """
    Build HTML for the path tree tab: collapsible tree showing nodes and A/B branches.
    Unexplored branches show "Continue" button.
    """
    if not nodes:
        return "<p><em>No story yet.</em></p>"
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    choice_by_node = {c["node_id"]: c for c in choices if isinstance(c, dict)}
    children_of: dict[int, list[tuple[str, int]]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        pid = n.get("parent_id")
        if pid is None:
            continue
        label = n.get("choice_label") or "?"
        if pid not in children_of:
            children_of[pid] = []
        children_of[pid].append((label, n["id"]))

    def _render_node(node_id: int, depth: int) -> str:
        node = by_id.get(node_id)
        if not node:
            return ""
        prose_preview = (node.get("prose_text") or "")[:250].replace("\n", " ")
        if len((node.get("prose_text") or "")) > 250:
            prose_preview += "…"
        choice = choice_by_node.get(node_id)
        children = children_of.get(node_id, [])
        children_by_label = {lbl: nid for lbl, nid in children}
        is_current = node_id == current_node_id
        current_mark = " <strong>(current)</strong>" if is_current else ""
        html = f'<div style="margin-left:{depth * 20}px; margin-bottom:8px;">'
        html += f'<span>Node {node_id}{current_mark}: {prose_preview or "(root)"}</span>'
        if choice:
            has_a = "A" in children_by_label
            has_b = "B" in children_by_label
            html += "<ul style='margin:4px 0;'>"
            a_txt = (choice.get('choice_a_text', '') or '')[:120]
            b_txt = (choice.get('choice_b_text', '') or '')[:120]
            html += f"<li>A: {a_txt}{'…' if len(choice.get('choice_a_text', '') or '') > 120 else ''} " + ("✓" if has_a else "<em>Continue</em>") + "</li>"
            html += f"<li>B: {b_txt}{'…' if len(choice.get('choice_b_text', '') or '') > 120 else ''} " + ("✓" if has_b else "<em>Continue</em>") + "</li>"
            html += "</ul>"
        for lbl, cid in sorted(children, key=lambda x: x[0]):
            html += _render_node(cid, depth + 1)
        html += "</div>"
        return html

    root = next((n for n in nodes if n.get("parent_id") is None), nodes[0] if nodes else None)
    if not root:
        return "<p><em>No root node.</em></p>"
    return '<div class="path-tree">' + _render_node(root["id"], 0) + "</div>"
