"""Tests for interactive mode: start, step, vet custom, path tree. Uses mocks for DB and LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from working.interactive.handlers import do_interactive_start, do_interactive_step, vet_custom_option
from working.interactive.tree_utils import (
    format_choices_block,
    get_prose_to_node,
    get_unexplored_nodes,
    parse_beats,
)
from working.interactive.ui import build_path_tree_html
from working.modes import GenerationMode, get_handler


@patch("working.interactive.handlers.save_interactive_story")
@patch("working.interactive.handlers.complete")
def test_interactive_start_returns_opening_and_choices(
    mock_complete: MagicMock,
    mock_save: MagicMock,
) -> None:
    """Interactive start: précis → opening + choices, both saved."""
    mock_complete.side_effect = [
        MagicMock(text="The opening scene began here.", call_id="opening"),
        MagicMock(text="A: Go left.\nB: Go right.", call_id="choices"),
    ]
    precis, beats, name, nodes, choices, current_id, choice_a, choice_b, entries = do_interactive_start(
        "A hero faces a choice.",
        [],
        False,
    )
    assert precis == "A hero faces a choice."
    assert len(beats) >= 0
    assert len(nodes) == 1
    assert nodes[0]["parent_id"] is None
    assert nodes[0]["prose_text"] == "The opening scene began here."
    assert len(choices) == 1
    assert choices[0]["node_id"] == 1
    assert current_id == 1
    assert "left" in choice_a.lower() or "right" in choice_b.lower()
    mock_save.assert_called_once()


def test_interactive_start_empty_idea_returns_empty() -> None:
    """Interactive start with empty idea returns empty state."""
    precis, beats, name, nodes, choices, current_id, choice_a, choice_b, entries = do_interactive_start(
        "",
        [],
        False,
    )
    assert precis == ""
    assert nodes == []
    assert choices == []
    assert current_id == 0


@patch("working.interactive.handlers.save_interactive_story")
@patch("working.interactive.handlers.complete")
def test_interactive_step_pick_a(
    mock_complete: MagicMock,
    mock_save: MagicMock,
) -> None:
    """Pick choice A → continuation + new choices."""
    nodes = [
        {"id": 1, "parent_id": None, "choice_label": None, "prose_text": "Opening."},
    ]
    choices_list = [
        {"node_id": 1, "choice_a_text": "Go left", "choice_b_text": "Go right"},
    ]
    mock_complete.side_effect = [
        MagicMock(text="She went left into the dark.", call_id="cont"),
        MagicMock(text="A: Continue.\nB: Turn back.", call_id="next"),
    ]
    new_nodes, new_choices, new_id, next_a, next_b, entries = do_interactive_step(
        "Précis",
        [],
        nodes,
        choices_list,
        1,
        "A",
        "Go left",
        [],
        is_custom=False,
    )
    assert len(new_nodes) == 2
    assert new_nodes[1]["parent_id"] == 1
    assert new_nodes[1]["choice_label"] == "A"
    assert "left" in new_nodes[1]["prose_text"].lower() or "dark" in new_nodes[1]["prose_text"].lower()
    assert new_id == 2
    mock_save.assert_called_once()


@patch("working.interactive.handlers.complete")
def test_interactive_vet_custom_yes(mock_complete: MagicMock) -> None:
    """Vet custom: YES allows."""
    mock_complete.return_value = MagicMock(text="YES", call_id="vet")
    allowed, reason = vet_custom_option("Précis here.", ["beat1"], "The hero runs away.")
    assert allowed is True
    assert reason == ""


@patch("working.interactive.handlers.complete")
def test_interactive_vet_custom_no(mock_complete: MagicMock) -> None:
    """Vet custom: NO disallows with reason."""
    mock_complete.return_value = MagicMock(text="NO. Reason: Out of character.", call_id="vet")
    allowed, reason = vet_custom_option("Précis here.", ["beat1"], "The hero flies to Mars.")
    assert allowed is False
    assert "character" in reason.lower() or "out" in reason.lower() or reason


def test_interactive_vet_custom_empty() -> None:
    """Vet custom: empty choice disallowed."""
    allowed, reason = vet_custom_option("Précis", [], "")
    assert allowed is False
    assert "empty" in reason.lower() or "Empty" in reason


def test_interactive_path_tree_builds_html() -> None:
    """Path tree: load story, render tree."""
    nodes = [
        {"id": 1, "parent_id": None, "choice_label": None, "prose_text": "Root."},
        {"id": 2, "parent_id": 1, "choice_label": "A", "prose_text": "Went A."},
    ]
    choices_list = [
        {"node_id": 1, "choice_a_text": "A", "choice_b_text": "B"},
        {"node_id": 2, "choice_a_text": "A2", "choice_b_text": "B2"},
    ]
    html = build_path_tree_html(nodes, choices_list, 2)
    assert "Node 1" in html
    assert "Node 2" in html
    assert "current" in html
    assert "Root" in html or "root" in html


def test_interactive_path_tree_empty() -> None:
    """Path tree: empty nodes returns placeholder."""
    html = build_path_tree_html([], [], 0)
    assert "No story" in html or "no story" in html


def test_interactive_get_prose_to_node() -> None:
    """get_prose_to_node concatenates prose from root to node."""
    nodes = [
        {"id": 1, "parent_id": None, "choice_label": None, "prose_text": "First."},
        {"id": 2, "parent_id": 1, "choice_label": "A", "prose_text": " Second."},
    ]
    prose = get_prose_to_node(nodes, 2)
    assert "First" in prose
    assert "Second" in prose


def test_format_choices_block() -> None:
    """format_choices_block produces clear separation with newlines and --- separator."""
    result = format_choices_block("Go left.", "Go right.")
    assert "---" in result
    assert "**Choice A:**" in result
    assert "**Choice B:**" in result
    assert "Go left." in result
    assert "Go right." in result
    # Double spacing: multiple newlines before/after separator
    assert "\n\n\n\n---" in result
    assert "---\n\n\n\n" in result
    # Choice A label on own line, then choice text
    assert "**Choice A:**\n\nGo left." in result
    assert "**Choice B:**\n\nGo right." in result


def test_format_choices_block_empty_returns_empty() -> None:
    """format_choices_block returns empty string when both choices empty."""
    assert format_choices_block("", "") == ""
    assert format_choices_block("", "  ") == ""
    assert format_choices_block("  ", "") == ""


def test_format_choices_block_one_empty_still_formats() -> None:
    """format_choices_block formats when one choice is empty (both labels shown)."""
    result = format_choices_block("Only A", "")
    assert "**Choice A:**" in result
    assert "**Choice B:**" in result
    assert "Only A" in result


def test_interactive_parse_beats() -> None:
    """parse_beats extracts beat strings from précis or outline."""
    beats = parse_beats("## Beginning\n- Beat one\n- Beat two\n## Middle\n- Beat three", True)
    assert len(beats) >= 2
    beats2 = parse_beats("A story about X. Then Y happens. Finally Z.", False)
    assert len(beats2) >= 0


def test_interactive_mode_handler_start_returns_generator() -> None:
    """Interactive mode handler start returns a generator."""
    with patch("working.interactive.handlers.complete") as mock_complete:
        mock_complete.side_effect = [
            MagicMock(text="Opening.", call_id="o"),
            MagicMock(text="A: One\nB: Two", call_id="c"),
        ]
        with patch("working.interactive.handlers.save_interactive_story"):
            handler = get_handler(GenerationMode.INTERACTIVE)
            result = handler.start("Précis", [], [], None, [], 10000, False)
            first = next(result)
            assert isinstance(first, tuple)
            assert len(first) == 28  # Same shape as expansion (path_tree + interactive_state + jump_dropdown)
