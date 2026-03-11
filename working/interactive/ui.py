"""
Interactive mode UI: path tree HTML, prose display.

Note on styling: Inline styles are used because Gradio's gr.HTML component does not
reliably support external CSS classes. This is a Gradio limitation, not a design choice.

Note on theming: Colors assume light mode. Dark mode support would require Gradio CSS
variables or theme detection, which is not currently implemented.
"""

from __future__ import annotations

import html as html_module
from typing import Any

# Color constants for interactive prose display (light mode)
CHOICE_A_COLOR = "#d35400"  # Orange for Choice A label
CHOICE_B_COLOR = "#2980b9"  # Blue for Choice B label
CHOICE_BOX_BG = "#f5f5f5"   # Light gray background for choices container
SEPARATOR_COLOR = "#ccc"    # Horizontal rule color

# Spacing constants (em units for relative sizing)
PARAGRAPH_MARGIN = "1em"
PARAGRAPH_LINE_HEIGHT = "1.6"
CHOICE_BOX_PADDING = "1.5em"
CHOICE_BOX_RADIUS = "8px"
SEPARATOR_MARGIN = "2em"
CHOICE_LABEL_SIZE = "1.1em"
CHOICE_TEXT_MARGIN = "0.5em"
CHOICE_TEXT_LINE_HEIGHT = "1.5"
CHOICE_SPACING = "1.5em"


def build_interactive_prose_html(
    prose: str | None,
    choice_a: str | None = None,
    choice_b: str | None = None,
) -> str:
    """Convert interactive mode prose and choices to properly formatted HTML.

    Converts paragraph breaks to HTML paragraphs and formats choices with
    clear visual separation and styling. All user content is HTML-escaped
    to prevent XSS attacks.

    Args:
        prose: Story prose text with paragraphs separated by blank lines.
               None or empty string shows "No story yet" placeholder.
        choice_a: Text for Choice A option. None or empty omits this choice.
        choice_b: Text for Choice B option. None or empty omits this choice.

    Returns:
        HTML string safe for rendering in gr.HTML component.
    """
    if not (prose or "").strip():
        return "<p><em>No story yet.</em></p>"

    paragraphs = prose.strip().split("\n\n")
    html_parts: list[str] = []

    for para in paragraphs:
        para = para.strip()
        if para:
            escaped = html_module.escape(para)
            html_parts.append(
                f'<p style="margin-bottom: {PARAGRAPH_MARGIN}; '
                f'line-height: {PARAGRAPH_LINE_HEIGHT};">{escaped}</p>'
            )

    a = (choice_a or "").strip()
    b = (choice_b or "").strip()
    if a or b:
        html_parts.append(
            f'<hr style="margin: {SEPARATOR_MARGIN} 0; border: none; '
            f'border-top: 2px solid {SEPARATOR_COLOR};">'
        )
        html_parts.append(
            f'<div style="background: {CHOICE_BOX_BG}; padding: {CHOICE_BOX_PADDING}; '
            f'border-radius: {CHOICE_BOX_RADIUS};" role="region" aria-label="Story choices">'
        )
        if a:
            escaped_a = html_module.escape(a)
            html_parts.append(
                f'<div style="margin-bottom: {CHOICE_SPACING};">'
                f'<strong style="color: {CHOICE_A_COLOR}; font-size: {CHOICE_LABEL_SIZE};">'
                f'Choice A:</strong>'
                f'<p style="margin-top: {CHOICE_TEXT_MARGIN}; '
                f'line-height: {CHOICE_TEXT_LINE_HEIGHT};">{escaped_a}</p>'
                f'</div>'
            )
        if b:
            escaped_b = html_module.escape(b)
            html_parts.append(
                f'<div>'
                f'<strong style="color: {CHOICE_B_COLOR}; font-size: {CHOICE_LABEL_SIZE};">'
                f'Choice B:</strong>'
                f'<p style="margin-top: {CHOICE_TEXT_MARGIN}; '
                f'line-height: {CHOICE_TEXT_LINE_HEIGHT};">{escaped_b}</p>'
                f'</div>'
            )
        html_parts.append('</div>')

    return "".join(html_parts)


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
