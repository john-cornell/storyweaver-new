"""
Log panel UI: render log entries as markdown (newest at top).
"""

from __future__ import annotations


def build_log_markdown(entries: list[str] | None) -> str:
    """Render running log for the Log panel. Newest first; empty state has placeholder."""
    if not entries:
        return "*Log is empty. Navigation and actions will appear here (newest at top).*"
    return "```\n" + "\n".join(entries) + "\n```"
