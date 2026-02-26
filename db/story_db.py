"""
SQLite store for story: metadata (story), current paragraphs (paragraphs), expansion history (history).
Reserved for future use: entities, relationships (consistency check).
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

_STORY_ID = 1

# 1) Story: metadata only
_TABLE_STORY = """
CREATE TABLE IF NOT EXISTS story (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    precis TEXT,
    updated_at TEXT
);
"""

# 2) History: old text when no longer current; step index and paragraph position
_TABLE_HISTORY = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    step_index INTEGER NOT NULL,
    paragraph_key TEXT NOT NULL,
    indices_json TEXT NOT NULL,
    path_label TEXT NOT NULL,
    old_text TEXT NOT NULL,
    left_text TEXT NOT NULL,
    right_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (story_id) REFERENCES story(id)
);
CREATE INDEX IF NOT EXISTS ix_history_story_id ON history(story_id);
"""

# 3) Paragraphs: current leaf paragraphs only
_TABLE_PARAGRAPHS = """
CREATE TABLE IF NOT EXISTS paragraphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    step_index INTEGER NOT NULL,
    paragraph_key TEXT NOT NULL,
    indices_json TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (story_id) REFERENCES story(id),
    UNIQUE(story_id, step_index, paragraph_key, indices_json)
);
CREATE INDEX IF NOT EXISTS ix_paragraphs_story_id ON paragraphs(story_id);
"""

# 4) Entities: reserved for consistency check (not used yet)
_TABLE_ENTITIES = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    FOREIGN KEY (story_id) REFERENCES story(id)
);
"""

# 5) Relationships: reserved for consistency check (not used yet)
_TABLE_RELATIONSHIPS = """
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    FOREIGN KEY (story_id) REFERENCES story(id)
);
"""

_init_done = False


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _is_leaf(node: Any) -> bool:
    return isinstance(node, str)


def _traverse_leaves(
    node: Any,
    step_idx: int,
    key: str,
    indices: tuple[int, ...],
    out: list[tuple[int, str, tuple[int, ...], str]],
) -> None:
    """Append (step_index, paragraph_key, indices, text) for every leaf."""
    if _is_leaf(node):
        text = (node.strip() if isinstance(node, str) else "")
        out.append((step_idx, key, indices, text))
        return
    if isinstance(node, dict) and "left" in node and "right" in node:
        _traverse_leaves(node["left"], step_idx, key, indices + (0,), out)
        _traverse_leaves(node["right"], step_idx, key, indices + (1,), out)


def _steps_to_paragraph_rows(steps: list[Any]) -> list[tuple[int, str, str, str]]:
    """Flatten steps tree to (step_index, paragraph_key, indices_json, text)."""
    rows: list[tuple[int, str, str, str]] = []
    for step_idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        for key in ("paragraph_1", "paragraph_2"):
            node = step.get(key) or ""
            leaves: list[tuple[int, str, tuple[int, ...], str]] = []
            _traverse_leaves(node, step_idx, key, (), leaves)
            for si, k, ind, text in leaves:
                indices_json = json.dumps(list(ind))
                rows.append((si, k, indices_json, text))
    return rows


def _build_tree_from_leaves(
    leaves: list[tuple[int, str, tuple[int, ...], str]],
    step_idx: int,
    key: str,
    indices: tuple[int, ...],
) -> Any:
    """Build one tree (str or dict) for step_idx/key from leaves whose (step_idx, key) match and indices prefix."""
    matching = [(ind, text) for si, k, ind, text in leaves if si == step_idx and k == key and ind == indices]
    if matching:
        (_, text) = matching[0]
        return text
    # Check for children (indices + (0,) and indices + (1,))
    child0 = _build_tree_from_leaves(leaves, step_idx, key, indices + (0,))
    child1 = _build_tree_from_leaves(leaves, step_idx, key, indices + (1,))
    if child0 is None and child1 is None:
        return None
    if child0 is not None and child1 is not None:
        return {"left": child0, "right": child1}
    return child0 if child0 is not None else child1


def _paragraph_rows_to_steps(rows: list[tuple[int, str, str, str]]) -> list[Any]:
    """Build steps list from (step_index, paragraph_key, indices_json, text) rows."""
    if not rows:
        return []
    leaves: list[tuple[int, str, tuple[int, ...], str]] = []
    for step_idx, key, indices_json, text in rows:
        try:
            ind = tuple(json.loads(indices_json))
        except (json.JSONDecodeError, TypeError):
            ind = ()
        leaves.append((step_idx, key, ind, text))
    step_indices = sorted({si for si, _, _, _ in leaves})
    steps: list[Any] = []
    for step_idx in step_indices:
        p1 = _build_tree_from_leaves(leaves, step_idx, "paragraph_1", ())
        p2 = _build_tree_from_leaves(leaves, step_idx, "paragraph_2", ())
        steps.append({"paragraph_1": p1 or "", "paragraph_2": p2 or ""})
    return steps


def _has_old_schema(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("PRAGMA table_info(story)")
    columns = [row[1] for row in cur.fetchall()]
    return "steps_json" in columns


def _migrate_from_old_schema(conn: sqlite3.Connection) -> None:
    """Migrate single row from old story(steps_json, history_json) to story + paragraphs + history."""
    cur = conn.execute("SELECT id, precis, steps_json, history_json, updated_at FROM story WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        return
    precis = row["precis"] or ""
    updated_at = row["updated_at"] or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    steps_json = row["steps_json"] or "[]"
    history_json = row["history_json"] or "[]"
    try:
        steps = json.loads(steps_json)
    except (json.JSONDecodeError, TypeError):
        steps = []
    try:
        history = json.loads(history_json)
    except (json.JSONDecodeError, TypeError):
        history = []
    conn.execute("DROP TABLE story")
    conn.execute(_TABLE_STORY.strip())
    conn.execute("INSERT INTO story (id, precis, updated_at) VALUES (?, ?, ?)", (_STORY_ID, precis, updated_at))
    for step_idx, key, indices_json, text in _steps_to_paragraph_rows(steps):
        conn.execute(
            "INSERT INTO paragraphs (story_id, step_index, paragraph_key, indices_json, text) VALUES (?, ?, ?, ?, ?)",
            (_STORY_ID, step_idx, key, indices_json, text),
        )
    for entry in history:
        if not isinstance(entry, dict):
            continue
        path_label = entry.get("path_label") or ""
        old_text = entry.get("original") or ""
        left_text = entry.get("left") or ""
        right_text = entry.get("right") or ""
        step_index = 0
        paragraph_key = "paragraph_1"
        indices_json = "[]"
        conn.execute(
            "INSERT INTO history (story_id, step_index, paragraph_key, indices_json, path_label, old_text, left_text, right_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_STORY_ID, step_index, paragraph_key, indices_json, path_label, old_text, left_text, right_text, updated_at),
        )


def _ensure_init() -> None:
    """Create tables if not exist; migrate from old schema when needed."""
    global _init_done
    if _init_done:
        return
    with _get_conn() as conn:
        # Story must exist first (FK target for history, paragraphs, entities, relationships).
        conn.execute(_TABLE_STORY.strip())
        conn.executescript(_TABLE_HISTORY)
        conn.executescript(_TABLE_PARAGRAPHS)
        conn.executescript(_TABLE_ENTITIES)
        conn.executescript(_TABLE_RELATIONSHIPS)
        if _has_old_schema(conn):
            _migrate_from_old_schema(conn)
        conn.commit()
    _init_done = True


def save_story(
    precis: str | None,
    steps: list[Any],
    history: list[Any],
) -> None:
    """
    Persist current story: update story metadata, replace paragraphs, replace history.
    On first insert, if precis is None use empty string (load_story returns None for empty precis).
    On update, if precis is None keep existing value.
    May raise on I/O or JSON serialization errors; callers should catch and log.
    """
    _ensure_init()
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _get_conn() as conn:
        try:
            cur = conn.execute("SELECT id, precis FROM story WHERE id = ?", (_STORY_ID,))
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO story (id, precis, updated_at) VALUES (?, ?, ?)",
                    (_STORY_ID, precis or "", updated_at),
                )
            else:
                keep_precis = precis if precis is not None else (row["precis"] or "")
                conn.execute(
                    "UPDATE story SET precis = ?, updated_at = ? WHERE id = ?",
                    (keep_precis, updated_at, _STORY_ID),
                )
            conn.execute("DELETE FROM paragraphs WHERE story_id = ?", (_STORY_ID,))
            for step_idx, key, indices_json, text in _steps_to_paragraph_rows(steps):
                conn.execute(
                    "INSERT INTO paragraphs (story_id, step_index, paragraph_key, indices_json, text) VALUES (?, ?, ?, ?, ?)",
                    (_STORY_ID, step_idx, key, indices_json, text),
                )
            conn.execute("DELETE FROM history WHERE story_id = ?", (_STORY_ID,))
            for entry in history:
                if not isinstance(entry, dict):
                    continue
                path_label = entry.get("path_label") or ""
                old_text = entry.get("original") or ""
                left_text = entry.get("left") or ""
                right_text = entry.get("right") or ""
                try:
                    step_index = int(entry["step_index"]) if "step_index" in entry else 0
                except (TypeError, ValueError):
                    step_index = 0
                paragraph_key = entry.get("paragraph_key") or "paragraph_1"
                indices = entry.get("indices")
                indices_json = json.dumps(indices) if isinstance(indices, list) else "[]"
                conn.execute(
                    "INSERT INTO history (story_id, step_index, paragraph_key, indices_json, path_label, old_text, left_text, right_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (_STORY_ID, step_index, paragraph_key, indices_json, path_label, old_text, left_text, right_text, updated_at),
                )
            conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"DB write failed: {e}") from e


def load_story() -> tuple[str | None, list[Any], list[Any]]:
    """
    Load current story from DB. Returns (precis, steps, history). Empty state: (None, [], []).
    No schema validation; callers must handle malformed data. Returns (None, [], []) on missing row or decode error.
    """
    _ensure_init()
    with _get_conn() as conn:
        cur = conn.execute("SELECT precis, updated_at FROM story WHERE id = ?", (_STORY_ID,))
        row = cur.fetchone()
    if row is None:
        return (None, [], [])
    precis = row["precis"] if (row["precis"] or "").strip() else None
    with _get_conn() as conn:
        cur = conn.execute(
            "SELECT step_index, paragraph_key, indices_json, text FROM paragraphs WHERE story_id = ? ORDER BY step_index, paragraph_key, indices_json",
            (_STORY_ID,),
        )
        p_rows = [tuple(r) for r in cur.fetchall()]
    try:
        steps = _paragraph_rows_to_steps(p_rows)
    except (json.JSONDecodeError, TypeError):
        steps = []
    with _get_conn() as conn:
        cur = conn.execute(
            "SELECT step_index, paragraph_key, indices_json, path_label, old_text, left_text, right_text FROM history WHERE story_id = ? ORDER BY id",
            (_STORY_ID,),
        )
        h_rows = cur.fetchall()
    history: list[Any] = []
    for r in h_rows:
        history.append({
            "step_index": r["step_index"],
            "paragraph_key": r["paragraph_key"],
            "indices": json.loads(r["indices_json"]) if r["indices_json"] else [],
            "path_label": r["path_label"],
            "original": r["old_text"],
            "left": r["left_text"],
            "right": r["right_text"],
        })
    return (precis, steps, history)
