"""Tests for humanization: HumanizeConfig, replace_ai_phrases, _should_humanize, _humanize_prose."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from config import HumanizeConfig
from llm import LLMResult
from working.banned import replace_ai_phrases
from working.handlers import _humanize_prose, _should_humanize, humanize_prose_if_enabled


# --- HumanizeConfig ---


def test_humanize_config_default() -> None:
    """Default (0/false) -> humanize_output False."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "", "STORYWEAVER_HUMANIZE_SCOPE": ""}):
        cfg = HumanizeConfig.from_env()
        assert cfg.humanize_output is False
        assert cfg.humanize_scope == "expansion_only"


def test_humanize_config_enabled() -> None:
    """STORYWEAVER_HUMANIZE_OUTPUT=1 -> humanize_output True."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "1", "STORYWEAVER_HUMANIZE_SCOPE": "expansion_only"}):
        cfg = HumanizeConfig.from_env()
        assert cfg.humanize_output is True


def test_humanize_config_scope_all() -> None:
    """STORYWEAVER_HUMANIZE_SCOPE=all -> humanize_scope all."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "0", "STORYWEAVER_HUMANIZE_SCOPE": "all"}):
        cfg = HumanizeConfig.from_env()
        assert cfg.humanize_scope == "all"


def test_humanize_config_scope_invalid_fallback() -> None:
    """Invalid scope -> falls back to expansion_only."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_SCOPE": "invalid"}):
        cfg = HumanizeConfig.from_env()
        assert cfg.humanize_scope == "expansion_only"


# --- replace_ai_phrases ---


def test_replace_ai_phrases_empty() -> None:
    """Empty string -> returns as-is."""
    assert replace_ai_phrases("") == ""


def test_replace_ai_phrases_moreover() -> None:
    """Moreover, -> And,"""
    assert replace_ai_phrases("Moreover, the hero ran.") == "And, the hero ran."


def test_replace_ai_phrases_furthermore() -> None:
    """Furthermore, -> Also,"""
    assert replace_ai_phrases("Furthermore, she left.") == "Also, she left."


def test_replace_ai_phrases_as_a_result() -> None:
    """As a result, -> So,"""
    assert replace_ai_phrases("As a result, he won.") == "So, he won."


# --- _should_humanize ---


def test_should_humanize_disabled() -> None:
    """humanize_output off -> False for all scopes."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "0"}):
        assert _should_humanize("expansion") is False
        assert _should_humanize("precis") is False
        assert _should_humanize("interactive") is False


def test_should_humanize_expansion_only() -> None:
    """expansion_only scope -> True only for expansion."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "1", "STORYWEAVER_HUMANIZE_SCOPE": "expansion_only"}):
        assert _should_humanize("expansion") is True
        assert _should_humanize("precis") is False
        assert _should_humanize("interactive") is False


def test_should_humanize_expansion_and_precis() -> None:
    """expansion_and_precis scope -> True for expansion and precis."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "1", "STORYWEAVER_HUMANIZE_SCOPE": "expansion_and_precis"}):
        assert _should_humanize("expansion") is True
        assert _should_humanize("precis") is True
        assert _should_humanize("interactive") is False


def test_should_humanize_all() -> None:
    """all scope -> True for all."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "1", "STORYWEAVER_HUMANIZE_SCOPE": "all"}):
        assert _should_humanize("expansion") is True
        assert _should_humanize("precis") is True
        assert _should_humanize("interactive") is True


# --- _humanize_prose ---


@patch("working.handlers.complete")
def test_humanize_prose_success(mock_complete: MagicMock) -> None:
    """Successful humanization returns rewritten text."""
    mock_complete.return_value = LLMResult(text="She walked. The sun rose.", call_id="test")
    entries: list[str] = []
    result = _humanize_prose("Moreover, she walked. Furthermore, the sun rose.", entries, "Test")
    assert "Moreover" not in result
    assert "Furthermore" not in result
    assert "She walked" in result or "sun rose" in result
    mock_complete.assert_called_once()
    assert any("humanized" in e for e in entries)


@patch("working.handlers.complete")
def test_humanize_prose_empty_response_returns_original(mock_complete: MagicMock) -> None:
    """Empty LLM response -> returns original text."""
    mock_complete.return_value = LLMResult(text="", call_id="test")
    entries: list[str] = []
    original = "She ran fast."
    result = _humanize_prose(original, entries, "Test")
    assert result == original


@patch("working.handlers.complete")
def test_humanize_prose_failure_returns_original(mock_complete: MagicMock) -> None:
    """LLM raises -> returns original text."""
    mock_complete.side_effect = RuntimeError("API error")
    entries: list[str] = []
    original = "She ran fast."
    result = _humanize_prose(original, entries, "Test")
    assert result == original
    assert any("failed" in e for e in entries)


# --- humanize_prose_if_enabled ---


@patch("working.handlers.complete")
def test_humanize_prose_if_enabled_returns_original_when_disabled(mock_complete: MagicMock) -> None:
    """When humanization disabled -> returns original without calling LLM."""
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "0"}):
        result = humanize_prose_if_enabled("Original text.", "expansion", None, "Test")
        assert result == "Original text."
        mock_complete.assert_not_called()


@patch("working.handlers.complete")
def test_humanize_prose_if_enabled_calls_llm_when_enabled(mock_complete: MagicMock) -> None:
    """When humanization enabled for scope -> calls LLM."""
    mock_complete.return_value = LLMResult(text="Rewritten prose.", call_id="test")
    with patch.dict(os.environ, {"STORYWEAVER_HUMANIZE_OUTPUT": "1", "STORYWEAVER_HUMANIZE_SCOPE": "expansion_only"}):
        result = humanize_prose_if_enabled("Original.", "expansion", None, "Test")
        assert result == "Rewritten prose."
        mock_complete.assert_called_once()
