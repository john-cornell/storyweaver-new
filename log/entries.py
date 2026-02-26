"""
Log entries: format and append (prepend) to running log.
Newest first; capped to avoid unbounded state growth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

LOG_LEVELS = Literal["info", "warn", "error"]
DEFAULT_MAX_ENTRIES = 500


def format_entry(message: str, level: LOG_LEVELS = "info") -> str:
    """Single log line: ISO timestamp + level + message."""
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"[{ts}] {level.upper()}: {message}"


def add_entry(
    entries: list[str],
    message: str,
    level: LOG_LEVELS = "info",
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> list[str]:
    """
    Prepend one entry to the log (newest first). Trims to max_entries.
    Does not mutate the input list.
    """
    line = format_entry(message, level=level)
    new_list = [line] + (entries or [])
    return new_list[:max_entries]
