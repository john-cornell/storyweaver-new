"""
SQLite store for current story: précis, steps (JSON), history (JSON).
Single row (id=1); save_story updates it, load_story returns (precis, steps, history) or (None, [], []).
Persistence is write-only from UI: the app does not auto-load from DB on startup (audit/recovery use).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# DB file next to project root (parent of db/)
_DB_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _DB_DIR / "storyweaver.db"

_TABLE = """
CREATE TABLE IF NOT EXISTS story (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    precis TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',
    history_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT
);
"""

_init_done = False


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_init() -> None:
    """Create table if not exists. Called once per process before first read/write."""
    global _init_done
    if _init_done:
        return
    with _get_conn() as conn:
        conn.executescript(_TABLE)
        conn.commit()
    _init_done = True


def save_story(
    precis: str | None,
    steps: list[Any],
    history: list[Any],
) -> None:
    """
    Persist current story. Always update steps and history.
    On first insert, if precis is None use empty string (load_story will return None for empty precis).
    On update, if precis is None keep existing value.
    May raise on I/O or JSON serialization errors; callers should catch and log.
    """
    _ensure_init()
    try:
        steps_json = json.dumps(steps)
        history_json = json.dumps(history)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Story not JSON-serializable: {e}") from e
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _get_conn() as conn:
        try:
            cur = conn.execute(
                "SELECT id, precis FROM story WHERE id = 1",
            )
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO story (id, precis, steps_json, history_json, updated_at) VALUES (1, ?, ?, ?, ?)",
                    (precis or "", steps_json, history_json, updated_at),
                )
            else:
                keep_precis = precis if precis is not None else (row["precis"] or "")
                conn.execute(
                    "UPDATE story SET precis = ?, steps_json = ?, history_json = ?, updated_at = ? WHERE id = 1",
                    (keep_precis, steps_json, history_json, updated_at),
                )
            conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"DB write failed: {e}") from e


def load_story() -> tuple[str | None, list[Any], list[Any]]:
    """
    Load current story from DB. Returns (precis, steps, history). Empty state: (None, [], []).
    No schema validation; callers must handle malformed data. Returns (None, [], []) on missing row or JSON decode error.
    """
    _ensure_init()
    with _get_conn() as conn:
        cur = conn.execute(
            "SELECT precis, steps_json, history_json FROM story WHERE id = 1",
        )
        row = cur.fetchone()
    if row is None:
        return (None, [], [])
    precis = row["precis"] if (row["precis"] or "").strip() else None
    try:
        steps = json.loads(row["steps_json"] or "[]")
        history = json.loads(row["history_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return (None, [], [])
    return (precis, steps, history)
