"""
Working panel UI: render current story tree and expansion history as markdown.
"""

from __future__ import annotations

from .tree_utils import get_all_leaf_paths, get_story_prose_only, render_tree_to_markdown
from .types import HistoryEntry, Step

HISTORY_ORIGINAL_TRUNCATE = 500
HISTORY_CHILD_TRUNCATE = 400

# Single source for empty "latest story" placeholder (Write tab).
EMPTY_STORY_PLACEHOLDER = "*No story yet. Use **Start** to create the first two paragraphs.*"


def build_story_prose_only(steps: list[Step] | None) -> str:
    """Render latest story as plain prose only (no step/paragraph labels). For Write tab."""
    prose = get_story_prose_only(steps)
    return prose if prose else EMPTY_STORY_PLACEHOLDER


def build_current_story_markdown(steps: list[Step] | None) -> str:
    """Render Current story tab: full paragraph tree (depth-first)."""
    return render_tree_to_markdown(steps)


def build_output_paragraphs_markdown(steps: list[Step] | None) -> str:
    """
    Render Output tab: all current leaf paragraphs in reading order, labeled Paragraph 1, 2, … N.
    Step 1 → Paragraphs 1 & 2; Step 2 → 1–4; Step 3 → 1–8; etc.
    """
    if not steps:
        return "*No paragraphs yet. Use **Start** then **Expand next** or **Run**.*"
    leaves = get_all_leaf_paths(steps)
    if not leaves:
        return "*No paragraphs yet.*"
    lines: list[str] = []
    for i, (_, text) in enumerate(leaves, 1):
        lines.append(f"**Paragraph {i}**")
        lines.append((text or "").strip() or "*—*")
        lines.append("")
    return "\n".join(lines).rstrip()


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


def build_working_markdown(steps: list[Step] | None) -> str:
    """Legacy single-panel content: same as current story tree."""
    return build_current_story_markdown(steps)
