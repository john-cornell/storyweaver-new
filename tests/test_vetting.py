"""Tests for vet_consistency and vetting helpers. Mocks LLM calls."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from llm import LLMResult
from working.vetting import (
    _build_story_text,
    _erl_subset_for_tag,
    _parse_consistency_response,
    vet_consistency,
)


def _minimal_steps() -> list[dict]:
    """One step with one leaf paragraph."""
    return [{"paragraph_1": "Alice walked through the forest.", "paragraph_2": ""}]


def _erl_fixture() -> dict:
    """ERL with one entity having physical_state."""
    return {
        "entities": [{"name": "Alice", "physical_state": "injured_left_arm"}],
        "relationships": [],
        "global_state": {},
    }


def test_vet_consistency_empty_steps() -> None:
    """steps=None -> returns []."""
    assert vet_consistency(None, _erl_fixture()) == []


def test_vet_consistency_empty_erl() -> None:
    """erl=None -> returns []."""
    assert vet_consistency(_minimal_steps(), None) == []


def test_vet_consistency_empty_entities_relationships() -> None:
    """erl with no entities and no relationships -> returns []."""
    empty_erl = {"entities": [], "relationships": [], "global_state": {}}
    assert vet_consistency(_minimal_steps(), empty_erl) == []


@patch("working.vetting.complete")
def test_vet_consistency_full_mode_none(mock_complete: MagicMock) -> None:
    """Full mode, NONE response -> returns []."""
    mock_complete.return_value = LLMResult(text="NONE", call_id="test")
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "full"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert result == []
    mock_complete.assert_called_once()
    assert "vet_consistency" in mock_complete.call_args.kwargs.get("purpose", "")


@patch("working.vetting.complete")
def test_vet_consistency_full_mode_issues(mock_complete: MagicMock) -> None:
    """Full mode, issues response -> returns issue list."""
    mock_complete.return_value = LLMResult(text="Issue 1", call_id="test")
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "full"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert result == ["Issue 1"]


@patch("working.vetting.complete")
def test_vet_consistency_single_mode_none(mock_complete: MagicMock) -> None:
    """Single mode, NONE response -> returns []."""
    mock_complete.return_value = LLMResult(text="NONE", call_id="test")
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "single"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert result == []


@patch("working.vetting.complete")
def test_vet_consistency_single_mode_issues(mock_complete: MagicMock) -> None:
    """Single mode, issues response -> returns issue list."""
    mock_complete.return_value = LLMResult(text="Issue 1\nIssue 2", call_id="test")
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "single"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert result == ["Issue 1", "Issue 2"]


@patch("working.vetting.complete")
def test_vet_consistency_multi_mode(mock_complete: MagicMock) -> None:
    """Multi mode, NONE for each tag -> returns [], verify call count."""
    mock_complete.return_value = LLMResult(text="NONE", call_id="test")
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "multi"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert result == []
    # ERL has physical_state only -> one tag with data
    assert mock_complete.call_count >= 1


@patch("working.vetting.complete")
def test_vet_consistency_multi_mode_tagged_issues(mock_complete: MagicMock) -> None:
    """Multi mode, one tag returns issue -> issues prefixed with [tag]."""
    def side_effect(*args, **kwargs):
        purpose = kwargs.get("purpose", "")
        if "physical_state" in purpose:
            return LLMResult(text="Contradiction: arm used", call_id="test")
        return LLMResult(text="NONE", call_id="test")

    mock_complete.side_effect = side_effect
    with patch.dict(os.environ, {"VET_CONSISTENCY_MODE": "multi"}):
        result = vet_consistency(_minimal_steps(), _erl_fixture())
    assert any("[physical_state]" in r for r in result)


def test_parse_consistency_response_none() -> None:
    """NONE -> []."""
    assert _parse_consistency_response("NONE") == []


def test_parse_consistency_response_none_with_newline() -> None:
    """NONE\\n -> []."""
    assert _parse_consistency_response("NONE\n") == []


def test_parse_consistency_response_issues() -> None:
    """Issue 1\\nIssue 2 -> [Issue 1, Issue 2]."""
    assert _parse_consistency_response("Issue 1\nIssue 2") == ["Issue 1", "Issue 2"]


def test_parse_consistency_response_empty() -> None:
    """Empty string -> []."""
    assert _parse_consistency_response("") == []
    assert _parse_consistency_response("   ") == []


def test_erl_subset_for_tag_physical_state() -> None:
    """physical_state tag: only entities with physical_state."""
    erl = {
        "entities": [
            {"name": "A", "physical_state": "injured"},
            {"name": "B", "inventory": ["sword"]},
        ],
        "relationships": [],
        "global_state": {},
    }
    subset = _erl_subset_for_tag(erl, "physical_state")
    assert len(subset["entities"]) == 1
    assert subset["entities"][0]["name"] == "A"
    assert subset["entities"][0]["physical_state"] == "injured"
    assert subset["relationships"] == []


def test_erl_subset_for_tag_inventory() -> None:
    """inventory tag: only entities with inventory."""
    erl = {
        "entities": [
            {"name": "A", "inventory": ["sword"]},
            {"name": "B", "physical_state": "fine"},
        ],
        "relationships": [],
        "global_state": {},
    }
    subset = _erl_subset_for_tag(erl, "inventory")
    assert len(subset["entities"]) == 1
    assert subset["entities"][0]["inventory"] == ["sword"]


def test_erl_subset_for_tag_relationship_dynamic() -> None:
    """relationship_dynamic tag: relationships only."""
    erl = {
        "entities": [],
        "relationships": [
            {"entity_a": "A", "entity_b": "B", "current_dynamic": "allies"},
        ],
        "global_state": {},
    }
    subset = _erl_subset_for_tag(erl, "relationship_dynamic")
    assert subset["entities"] == []
    assert len(subset["relationships"]) == 1
    assert subset["relationships"][0]["current_dynamic"] == "allies"


def test_erl_subset_for_tag_global_state() -> None:
    """global_state tag: global_state only."""
    erl = {
        "entities": [],
        "relationships": [],
        "global_state": {"location": "forest", "weather": "rain"},
    }
    subset = _erl_subset_for_tag(erl, "global_state")
    assert subset["entities"] == []
    assert subset["relationships"] == []
    assert subset["global_state"]["location"] == "forest"


def test_build_story_text() -> None:
    """_build_story_text extracts leaf text."""
    steps = _minimal_steps()
    text = _build_story_text(steps)
    assert "Alice" in text
    assert "forest" in text
