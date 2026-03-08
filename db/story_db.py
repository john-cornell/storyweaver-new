"""
SQLite store for story: metadata (story), current paragraphs (paragraphs), expansion history (history).
Entity and Relationship Ledger (ERL) for narrative consistency.
Persistence is write-only from UI: the app does not auto-load from DB on startup (audit/recovery use).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# DB file next to project root (parent of db/)
_DB_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _DB_DIR / "storyweaver.db"

_STORY_ID = 1

logger = logging.getLogger(__name__)

# 1) Story: metadata only
_TABLE_STORY = """
CREATE TABLE IF NOT EXISTS story (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    precis TEXT,
    name TEXT,
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

# 4) Entities: ERL entity records
_TABLE_ENTITIES = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    physical_state TEXT,
    inventory_json TEXT,
    current_goal TEXT,
    FOREIGN KEY (story_id) REFERENCES story(id)
);
CREATE INDEX IF NOT EXISTS ix_entities_story_id ON entities(story_id);
"""

# 5) Relationships: ERL relationship records
_TABLE_RELATIONSHIPS = """
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    entity_a TEXT NOT NULL,
    entity_b TEXT NOT NULL,
    current_dynamic TEXT,
    FOREIGN KEY (story_id) REFERENCES story(id)
);
CREATE INDEX IF NOT EXISTS ix_relationships_story_id ON relationships(story_id);
"""

# 6) Global state: ERL environment/plot state
_TABLE_GLOBAL_STATE = """
CREATE TABLE IF NOT EXISTS global_state (
    story_id INTEGER PRIMARY KEY,
    state_json TEXT NOT NULL,
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


def _has_old_erl_schema(conn: sqlite3.Connection) -> bool:
    """True if entities table exists but lacks 'name' column (old stub schema)."""
    try:
        cur = conn.execute("PRAGMA table_info(entities)")
        columns = [row[1] for row in cur.fetchall()]
        return "name" not in columns
    except sqlite3.OperationalError:
        return False


def _has_story_name_column(conn: sqlite3.Connection) -> bool:
    """True if story table has 'name' column."""
    cur = conn.execute("PRAGMA table_info(story)")
    columns = [row[1] for row in cur.fetchall()]
    return "name" in columns


def _migrate_add_story_name(conn: sqlite3.Connection) -> None:
    """Add name column to story table if missing."""
    if _has_story_name_column(conn):
        return
    conn.execute("ALTER TABLE story ADD COLUMN name TEXT")


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
    conn.execute(
        "INSERT INTO story (id, precis, name, updated_at) VALUES (?, ?, ?, ?)",
        (_STORY_ID, precis, "", updated_at),
    )
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


def _migrate_old_erl_schema(conn: sqlite3.Connection) -> None:
    """Drop old stub entities/relationships tables and recreate with ERL schema."""
    conn.execute("DROP TABLE IF EXISTS entities")
    conn.execute("DROP TABLE IF EXISTS relationships")
    for stmt in _TABLE_ENTITIES.strip().split(";"):
        if (s := stmt.strip()):
            conn.execute(s)
    for stmt in _TABLE_RELATIONSHIPS.strip().split(";"):
        if (s := stmt.strip()):
            conn.execute(s)


def _ensure_init() -> None:
    """Create tables if not exist; migrate from old schema when needed."""
    global _init_done
    if _init_done:
        return
    logger.debug("DB initialized at %s", _DB_PATH)
    with _get_conn() as conn:
        conn.execute(_TABLE_STORY.strip())
        conn.executescript(_TABLE_HISTORY)
        conn.executescript(_TABLE_PARAGRAPHS)
        if _has_old_schema(conn):
            _migrate_from_old_schema(conn)
        if _has_old_erl_schema(conn):
            _migrate_old_erl_schema(conn)
        else:
            conn.executescript(_TABLE_ENTITIES)
            conn.executescript(_TABLE_RELATIONSHIPS)
        conn.execute(_TABLE_GLOBAL_STATE.strip())
        _migrate_add_story_name(conn)
        conn.commit()
    _init_done = True


def save_story(
    precis: str | None,
    steps: list[Any],
    history: list[Any],
    name: str | None = None,
) -> None:
    """
    Persist current story: update story metadata, replace paragraphs, replace history.
    On first insert, if precis is None use empty string (load_story returns None for empty precis).
    On update, if precis is None keep existing value.
    If name is None on update, keep existing name.
    May raise on I/O or JSON serialization errors; callers should catch and log.
    """
    _ensure_init()
    n_steps = len(steps) if steps else 0
    n_history = len(history) if history else 0
    logger.debug("save_story: steps=%d history=%d", n_steps, n_history)
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _get_conn() as conn:
        try:
            cur = conn.execute("SELECT id, precis, name FROM story WHERE id = ?", (_STORY_ID,))
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO story (id, precis, name, updated_at) VALUES (?, ?, ?, ?)",
                    (_STORY_ID, precis or "", name or "", updated_at),
                )
            else:
                keep_precis = precis if precis is not None else (row["precis"] or "")
                keep_name = name if name is not None else (row["name"] or "")
                conn.execute(
                    "UPDATE story SET precis = ?, name = ?, updated_at = ? WHERE id = ?",
                    (keep_precis, keep_name, updated_at, _STORY_ID),
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


def load_story() -> tuple[str | None, list[Any], list[Any], str | None]:
    """
    Load current story from DB. Returns (precis, steps, history, name). Empty state: (None, [], [], None).
    No schema validation; callers must handle malformed data. Returns (None, [], [], None) on missing row or decode error.
    """
    _ensure_init()
    logger.debug("load_story: reading")
    with _get_conn() as conn:
        cur = conn.execute("SELECT precis, name, updated_at FROM story WHERE id = ?", (_STORY_ID,))
        row = cur.fetchone()
    if row is None:
        return (None, [], [], None)
    precis = row["precis"] if (row["precis"] or "").strip() else None
    name = (row["name"] or "").strip() or None
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
    n_steps = len(steps)
    n_history = len(history)
    logger.debug("load_story: precis=%s steps=%d history=%d name=%s", "present" if precis else "None", n_steps, n_history, "present" if name else "None")
    return (precis, steps, history, name)


def save_erl(erl: Any) -> None:
    """
    Persist Entity and Relationship Ledger. Replaces all ERL data for the story.
    erl must have keys: entities (list), relationships (list), global_state (dict).
    """
    _ensure_init()
    entities = erl.get("entities") or []
    relationships = erl.get("relationships") or []
    global_state = erl.get("global_state") or {}
    if not isinstance(entities, list):
        entities = []
    if not isinstance(relationships, list):
        relationships = []
    if not isinstance(global_state, dict):
        global_state = {}
    n_ent = len(entities)
    n_rel = len(relationships)
    logger.debug("save_erl: entities=%d relationships=%d", n_ent, n_rel)
    with _get_conn() as conn:
        conn.execute("DELETE FROM entities WHERE story_id = ?", (_STORY_ID,))
        for e in entities:
            if not isinstance(e, dict):
                continue
            name = (e.get("name") or "").strip() or "(unnamed)"
            physical_state = (e.get("physical_state") or "").strip() or None
            inv = e.get("inventory")
            inventory_json = json.dumps(inv) if isinstance(inv, list) else "[]"
            current_goal = (e.get("current_goal") or "").strip() or None
            conn.execute(
                "INSERT INTO entities (story_id, name, physical_state, inventory_json, current_goal) VALUES (?, ?, ?, ?, ?)",
                (_STORY_ID, name, physical_state, inventory_json, current_goal),
            )
        conn.execute("DELETE FROM relationships WHERE story_id = ?", (_STORY_ID,))
        for r in relationships:
            if not isinstance(r, dict):
                continue
            entity_a = (r.get("entity_a") or "").strip() or "(unknown)"
            entity_b = (r.get("entity_b") or "").strip() or "(unknown)"
            current_dynamic = (r.get("current_dynamic") or "").strip() or None
            conn.execute(
                "INSERT INTO relationships (story_id, entity_a, entity_b, current_dynamic) VALUES (?, ?, ?, ?)",
                (_STORY_ID, entity_a, entity_b, current_dynamic),
            )
        state_json = json.dumps(global_state)
        conn.execute(
            "INSERT OR REPLACE INTO global_state (story_id, state_json) VALUES (?, ?)",
            (_STORY_ID, state_json),
        )
        conn.commit()


def load_erl() -> Any:
    """
    Load Entity and Relationship Ledger from DB. Returns ERL dict (entities, relationships, global_state).
    Returns empty ERL if none stored.

    Uses lazy import of empty_erl to avoid circular dependency (db is imported before working.erl at startup).
    """
    _ensure_init()
    logger.debug("load_erl: reading")
    from working.erl import empty_erl  # Lazy: avoid circular import (db → working → db)

    with _get_conn() as conn:
        cur = conn.execute(
            "SELECT name, physical_state, inventory_json, current_goal FROM entities WHERE story_id = ?",
            (_STORY_ID,),
        )
        entity_rows = cur.fetchall()
        cur = conn.execute(
            "SELECT entity_a, entity_b, current_dynamic FROM relationships WHERE story_id = ?",
            (_STORY_ID,),
        )
        rel_rows = cur.fetchall()
        cur = conn.execute("SELECT state_json FROM global_state WHERE story_id = ?", (_STORY_ID,))
        row = cur.fetchone()

    entities: list[dict[str, Any]] = []
    for r in entity_rows:
        inv_json = r["inventory_json"] or "[]"
        try:
            inv = json.loads(inv_json)
        except (json.JSONDecodeError, TypeError):
            inv = []
        if not isinstance(inv, list):
            inv = []
        entities.append({
            "name": r["name"] or "",
            "physical_state": r["physical_state"] or "",
            "inventory": inv,
            "current_goal": r["current_goal"] or "",
        })
    relationships: list[dict[str, Any]] = []
    for r in rel_rows:
        relationships.append({
            "entity_a": r["entity_a"] or "",
            "entity_b": r["entity_b"] or "",
            "current_dynamic": r["current_dynamic"] or "",
        })
    global_state: dict[str, Any] = {}
    if row and row["state_json"]:
        try:
            global_state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            pass
        if not isinstance(global_state, dict):
            global_state = {}
    if not entities and not relationships and not global_state:
        logger.debug("load_erl: empty")
        return empty_erl()
    logger.debug("load_erl: entities=%d relationships=%d", len(entities), len(relationships))
    return {
        "entities": entities,
        "relationships": relationships,
        "global_state": global_state,
    }
