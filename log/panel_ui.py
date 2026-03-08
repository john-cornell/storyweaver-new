"""
Log panel UI: render log entries as markdown (newest at top).
"""

from __future__ import annotations

from llm import get_llm_log_buffer


def build_llm_log_markdown() -> str:
    """Render LLM call log buffer for web UI (real-time). Newest at bottom."""
    lines = get_llm_log_buffer()
    if not lines:
        return "## LLM Calls (real-time)\n\n*No LLM calls yet. Start writing to see them here.*"
    escaped = [line.replace("`", "'") for line in lines]
    return "## LLM Calls (real-time)\n\n```\n" + "\n".join(escaped) + "\n```"


def build_log_markdown(entries: list[str] | None) -> str:
    """Render running log for the Log panel. Newest first; empty state has placeholder."""
    if not entries:
        return "*Log is empty. Navigation and actions will appear here (newest at top).*"
    return "```\n" + "\n".join(entries) + "\n```"
