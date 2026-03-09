"""Tests for save_story/load_story mode round-trip."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path: Path) -> None:
    """Use a temporary DB file for each test."""
    import db.story_db as story_db

    test_db = tmp_path / "test_storyweaver.db"
    orig_init = story_db._init_done
    story_db._init_done = False
    try:
        with patch.object(story_db, "_DB_PATH", test_db):
            yield
    finally:
        story_db._init_done = orig_init


def test_save_load_story_mode_round_trip() -> None:
    """save_story with mode and load_story return the same mode."""
    from db import load_story, save_story

    steps = [{"paragraph_1": "A", "paragraph_2": "B"}]
    history: list = []

    save_story("precis", steps, history, name="Test", mode="expansion")
    precis, loaded_steps, loaded_history, name, mode = load_story()
    assert mode == "expansion"
    assert precis == "precis"
    assert name == "Test"

    save_story("precis2", steps, history, name="Test2", mode="interactive")
    _, _, _, _, mode2 = load_story()
    assert mode2 == "interactive"


def test_load_story_empty_returns_expansion() -> None:
    """load_story on empty DB returns mode='expansion'."""
    from db.story_db import _ensure_init, _get_conn

    _ensure_init()
    with _get_conn() as conn:
        conn.execute("DELETE FROM story WHERE id = 1")
        conn.commit()

    from db import load_story

    precis, steps, history, name, mode = load_story()
    assert mode == "expansion"
    assert precis is None
    assert steps == []
    assert history == []


def test_db_interactive_save_load_round_trip() -> None:
    """save_interactive_story and load_interactive_story round-trip."""
    from db import load_interactive_story, save_interactive_story

    precis = "A hero's journey."
    beats = ["Start", "Middle", "End"]
    nodes = [
        {"id": 1, "parent_id": None, "choice_label": None, "prose_text": "Opening."},
        {"id": 2, "parent_id": 1, "choice_label": "A", "prose_text": "Chose A."},
    ]
    choices = [
        {"node_id": 1, "choice_a_text": "Go A", "choice_b_text": "Go B"},
        {"node_id": 2, "choice_a_text": "A2", "choice_b_text": "B2"},
    ]
    save_interactive_story(precis, beats, "TestStory", nodes, choices)
    loaded_precis, loaded_beats, loaded_name, loaded_nodes, loaded_choices = load_interactive_story()
    assert loaded_precis == precis
    assert loaded_beats == beats
    assert loaded_name == "TestStory"
    assert len(loaded_nodes) == 2
    assert loaded_nodes[0]["prose_text"] == "Opening."
    assert loaded_nodes[1]["choice_label"] == "A"
    assert len(loaded_choices) == 2
    assert loaded_choices[0]["choice_a_text"] == "Go A"
