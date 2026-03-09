"""
Working panel UI: render current story tree and expansion history as markdown.

Any HTML output (e.g. copy button, tree view) escapes user-supplied content with html.escape
to prevent XSS when rendering story text in the browser.
"""

from __future__ import annotations

import html as html_module
import logging

# Direct db import: full history loads precis from DB for debug trace. Coupling acceptable
# for this debug view; callers do not typically have precis in scope.
from db import load_story

from .tree_utils import (
    count_words_in_steps,
    get_all_leaf_paths,
    get_all_nodes_with_lineage,
    get_story_prose_only,
    render_tree_to_html,
    render_tree_to_markdown,
)
from .types import HistoryEntry, Step

HISTORY_ORIGINAL_TRUNCATE = 500
HISTORY_CHILD_TRUNCATE = 400

# Single source for empty "latest story" placeholder (Write tab).
EMPTY_STORY_PLACEHOLDER = "*No story yet. Use **Start** to create the first two paragraphs.*"


def build_story_prose_only(steps: list[Step] | None) -> str:
    """Render latest story as plain prose only (no step/paragraph labels). For Write tab."""
    prose = get_story_prose_only(steps)
    return prose if prose else EMPTY_STORY_PLACEHOLDER


def build_latest_story_display(steps: list[Step] | None) -> str:
    """Render Latest story section: Story name, word count, and prose. For Write tab."""
    if not steps:
        return EMPTY_STORY_PLACEHOLDER
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return EMPTY_STORY_PLACEHOLDER
    try:
        _, _, _, name, _ = load_story()
    except Exception as e:
        logging.getLogger(__name__).warning("load_story failed for latest story display: %s", e)
        name = None
    word_count = count_words_in_steps(steps)
    prose = get_story_prose_only(steps)
    display_name = (name or "").strip() or "Untitled"
    return f"**Story:** *{display_name}* | {word_count} words\n\n{prose}"


def build_current_story_markdown(steps: list[Step] | None) -> str:
    """Render full paragraph tree as markdown (depth-first). Kept for compatibility."""
    return render_tree_to_markdown(steps)


def build_current_story_html(steps: list[Step] | None) -> str:
    """Render Current story tab: collapsible tree (Step → P1/P2 → L/R splits) for debugging."""
    return render_tree_to_html(steps)


def build_output_paragraphs_markdown(steps: list[Step] | None) -> str:
    """
    Render Output tab: all current leaf paragraphs in reading order as plain prose only.
    No "Paragraph N" labels are included so the reader only sees story text.
    """
    if not steps:
        return "*No paragraphs yet. Use **Start** then **Expand next** or **Run**.*"
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return "*No paragraphs yet.*"
    lines: list[str] = []
    for i, (_, text) in enumerate(leaves, 1):
        # Plain prose only; keep a blank line between paragraphs for readability.
        lines.append((text or "").strip() or "*—*")
        # Separate paragraphs with a single blank line except after the last one.
        if i < len(leaves):
            lines.append("")
    return "\n".join(lines).rstrip()


def build_output_copy_button_html(steps: list[Step] | None) -> str:
    """
    HTML for Output tab: Copy button at top that copies story as plain text only
    (no Paragraph N, no word counts — get_story_prose_only).
    All story text is HTML-escaped before insertion to prevent XSS.
    """
    prose = get_story_prose_only(steps)
    if not (prose or "").strip():
        return (
            '<div class="sw-output-copy" style="margin-bottom: 0.5em;">'
            '<button type="button" disabled title="No story to copy">Copy story (plain text)</button>'
            "</div>"
        )
    escaped = html_module.escape(prose)
    return (
        '<div class="sw-output-copy" style="margin-bottom: 0.5em;">'
        '<button type="button" onclick="'
        "var el = document.getElementById('sw-copy-prose'); "
        "var btn = this; "
        "if (el && navigator.clipboard) navigator.clipboard.writeText(el.innerText).then(function(){ btn.textContent = 'Copied!'; setTimeout(function(){ btn.textContent = 'Copy story (plain text)'; }, 1500); }).catch(function(){ btn.textContent = 'Copy failed'; setTimeout(function(){ btn.textContent = 'Copy story (plain text)'; }, 2000); });"
        '">Copy story (plain text)</button>'
        f'<pre id="sw-copy-prose" style="display:none;" aria-hidden="true">{escaped}</pre>'
        "</div>"
    )


def build_history_markdown(history: list[HistoryEntry] | None) -> str:
    """Render History tab: expansion log (path, original snippet, then two new paragraphs in story order)."""
    if not history:
        return "*No expansions yet. Use **Expand next** or **Run** to expand paragraphs.*"
    lines: list[str] = []
    for i, entry in enumerate(history, 1):
        path_display = entry.get("path_label") or f"#{i}"
        orig = (entry.get("original") or "").strip()
        left = (entry.get("left") or "").strip()
        right = (entry.get("right") or "").strip()
        # Show in story order: first paragraph then second. Label "First" and "Second" to match Output tab (avoids left/right confusion).
        first_text = left
        second_text = right
        lines.append(f"### Expansion {i}: {path_display}")
        lines.append("**Original:**")
        lines.append(
            orig[:HISTORY_ORIGINAL_TRUNCATE]
            + ("…" if len(orig) > HISTORY_ORIGINAL_TRUNCATE else "")
        )
        lines.append("")
        lines.append("**→ First:**")
        lines.append(
            first_text[:HISTORY_CHILD_TRUNCATE]
            + ("…" if len(first_text) > HISTORY_CHILD_TRUNCATE else "")
            or "*—*"
        )
        lines.append("")
        lines.append("**→ Second:**")
        lines.append(
            second_text[:HISTORY_CHILD_TRUNCATE]
            + ("…" if len(second_text) > HISTORY_CHILD_TRUNCATE else "")
            or "*—*"
        )
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip()


def _get_expanded_text(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
) -> str:
    """Reconstruct the initial two paragraphs (expanded from précis) for full-history trace."""
    if not steps:
        return ""
    history = history or []
    path_to_original: dict[tuple[int, str, tuple[int, ...]], str] = {}
    for entry in history:
        si = int(entry.get("step_index", 0)) if entry.get("step_index") is not None else 0
        key = entry.get("paragraph_key") or "paragraph_1"
        idx = entry.get("indices")
        indices = tuple(idx) if isinstance(idx, list) else ()
        path_to_original[(si, key, indices)] = (entry.get("original") or "").strip()

    def get_root_text(step_idx: int, key: str) -> str:
        if step_idx >= len(steps):
            return ""
        path = (step_idx, key, ())
        if path in path_to_original:
            return path_to_original[path]
        step = steps[step_idx]
        tree = step.get(key)
        if isinstance(tree, str):
            return (tree or "").strip()
        return ""

    p1 = get_root_text(0, "paragraph_1")
    p2 = get_root_text(0, "paragraph_2")
    parts = [p for p in (p1, p2) if p]
    return "\n\n".join(parts)


def build_full_history_text(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
) -> str:
    """
    Render full history trace for debugging: Precis, Expanded, then Step N paragraphs
    with lineage (From Step X Paragraph Y).
    """
    precis = ""
    try:
        p, _, _, _, _ = load_story()
        precis = (p or "").strip()
    except Exception as e:
        logging.getLogger(__name__).warning("load_story failed for full history precis: %s", e)

    lines: list[str] = []
    lines.append("**Precis:**")
    lines.append(precis if precis else "*—*")
    lines.append("")
    lines.append("**Expanded:**")
    expanded = _get_expanded_text(steps, history)
    lines.append(expanded if expanded else "*—*")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not steps:
        lines.append("*No steps yet. Use **Start** to create the first two paragraphs.*")
        return "\n".join(lines)

    history = history or []
    path_to_original: dict[tuple[int, str, tuple[int, ...]], str] = {}
    for entry in history:
        si = int(entry.get("step_index", 0)) if entry.get("step_index") is not None else 0
        key = entry.get("paragraph_key") or "paragraph_1"
        idx = entry.get("indices")
        indices = tuple(idx) if isinstance(idx, list) else ()
        path_to_original[(si, key, indices)] = (entry.get("original") or "").strip()

    nodes = get_all_nodes_with_lineage(steps, path_to_original)
    if not nodes:
        lines.append("*No paragraphs yet.*")
        return "\n".join(lines)

    # Sort by round then paragraph number so Step 1 appears before Step 2
    nodes_sorted = sorted(nodes, key=lambda x: (x[0], x[1]))
    current_round = 0
    for round_num, para_num, parent_round, parent_para, text in nodes_sorted:
        if round_num != current_round:
            if current_round > 0:
                lines.append("")
            current_round = round_num

        lineage = ""
        if parent_round is not None and parent_para is not None:
            lineage = f" (From Step {parent_round} Paragraph {parent_para})"
        label = f"Step {round_num}: Paragraph {para_num}{lineage}"
        content = (text or "").strip() or "*—*"
        lines.append(f"{label}:")
        lines.append(content)
        lines.append("")

    return "\n".join(lines).rstrip()


def build_full_history_copy_button_html(
    steps: list[Step] | None,
    history: list[HistoryEntry] | None,
) -> str:
    """
    HTML for Full history tab: Copy button that copies the full history trace.
    All text is HTML-escaped to prevent XSS.
    """
    content = build_full_history_text(steps, history)
    if not (content or "").strip():
        return (
            '<div class="sw-full-history-copy" style="margin-bottom: 0.5em;">'
            '<button type="button" disabled title="No history to copy">Copy to clipboard</button>'
            "</div>"
        )
    escaped = html_module.escape(content)
    return (
        '<div class="sw-full-history-copy" style="margin-bottom: 0.5em;">'
        '<button type="button" onclick="'
        "var el = document.getElementById('sw-copy-full-history'); "
        "var btn = this; "
        "if (el && navigator.clipboard) navigator.clipboard.writeText(el.innerText).then(function(){ btn.textContent = 'Copied!'; setTimeout(function(){ btn.textContent = 'Copy to clipboard'; }, 1500); }).catch(function(){ btn.textContent = 'Copy failed'; setTimeout(function(){ btn.textContent = 'Copy to clipboard'; }, 2000); });"
        '">Copy to clipboard</button>'
        f'<pre id="sw-copy-full-history" style="display:none;" aria-hidden="true">{escaped}</pre>'
        "</div>"
    )


def build_working_markdown(steps: list[Step] | None) -> str:
    """Legacy single-panel content: same as current story tree."""
    return build_current_story_markdown(steps)
