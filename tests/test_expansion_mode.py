"""Tests for expansion mode handler delegation. Uses mocks for DB and LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from working.modes import GenerationMode, get_handler


def test_expansion_start_returns_generator() -> None:
    """Expansion mode start delegates to do_start_write and returns a generator."""
    handler = get_handler(GenerationMode.EXPANSION)
    result = handler.start("A précis.", [], [], None, [], 10000, False)
    assert hasattr(result, "__iter__") and hasattr(result, "__next__")
    # First yield produces a 28-element tuple (do_start_write + path_tree + interactive_state + jump_dropdown)
    first = next(result)
    assert isinstance(first, tuple)
    assert len(first) == 28


@patch("working.handlers.complete")
@patch("working.classifier.complete")
@patch("working.beat_extractor.complete")
@patch("working.erl_extractor.complete")
@patch("working.handlers.load_erl")
@patch("working.handlers.save_erl")
@patch("working.handlers.save_story")
def test_expansion_step_delegates_to_do_expand_next(
    mock_save_story: MagicMock,
    mock_save_erl: MagicMock,
    mock_load_erl: MagicMock,
    mock_erl_complete: MagicMock,
    mock_beats_complete: MagicMock,
    mock_classifier_complete: MagicMock,
    mock_handlers_complete: MagicMock,
) -> None:
    """Expansion mode step delegates to do_expand_next."""
    steps = [{"paragraph_1": "P1", "paragraph_2": "P2"}]
    mock_load_erl.return_value = {"entities": [], "relationships": [], "global_state": {}}
    llm_result = MagicMock(text="Left paragraph.\n\nRight paragraph.", call_id="test")
    mock_handlers_complete.return_value = llm_result
    mock_classifier_complete.return_value = llm_result
    mock_beats_complete.return_value = llm_result
    mock_erl_complete.return_value = llm_result

    handler = get_handler(GenerationMode.EXPANSION)
    result = handler.step(steps, [], [], 10000, None)

    assert len(result) >= 10
    new_steps, new_history, *_ = result
    assert isinstance(new_steps, list)
    assert isinstance(new_history, list)


def test_expansion_step_round_delegates() -> None:
    """Expansion mode step_round delegates to do_expand_round and returns correct shape."""
    handler = get_handler(GenerationMode.EXPANSION)
    steps = [{"paragraph_1": "P1", "paragraph_2": "P2"}]
    # step_round with word_limit=1 stops immediately (2 words >= 1)
    result = handler.step_round(steps, [], [], 1, None)
    assert len(result) >= 10
