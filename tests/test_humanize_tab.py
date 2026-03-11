"""Tests for Humanize tab: do_humanize_pasted_text, _split_into_paragraphs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from llm import LLMResult

from humanize.handlers import _split_into_paragraphs, do_humanize_pasted_text


def test_split_into_paragraphs_empty() -> None:
    """Empty or whitespace -> empty list."""
    assert _split_into_paragraphs("") == []
    assert _split_into_paragraphs("   \n\n   ") == []


def test_split_into_paragraphs_single() -> None:
    """Single block -> one paragraph."""
    assert _split_into_paragraphs("One paragraph.") == ["One paragraph."]


def test_split_into_paragraphs_two() -> None:
    """Two blocks separated by blank line -> two paragraphs."""
    text = "First para.\n\nSecond para."
    assert _split_into_paragraphs(text) == ["First para.", "Second para."]


def test_split_into_paragraphs_three() -> None:
    """Three blocks -> three paragraphs."""
    text = "A\n\nB\n\nC"
    assert _split_into_paragraphs(text) == ["A", "B", "C"]


def test_do_humanize_empty_input() -> None:
    """Empty input -> yields empty output and status message."""
    results = list(do_humanize_pasted_text("", True, False))
    assert len(results) == 1
    out, status = results[0]
    assert out == ""
    assert "No paragraphs" in status


def test_do_humanize_rule_based_only() -> None:
    """rule_based=True, llm_humanize=False -> replace_ai_phrases only, no LLM call."""
    results = list(do_humanize_pasted_text("Moreover, she ran.\n\nFurthermore, he left.", True, False))
    assert len(results) == 3  # 2 paragraphs + final done
    out, _ = results[-1]
    assert "Moreover" not in out
    assert "Furthermore" not in out
    assert "And," in out or "Also," in out


@patch("humanize.handlers.complete")
def test_do_humanize_llm_only(mock_complete: MagicMock) -> None:
    """rule_based=False, llm_humanize=True -> LLM call only."""
    mock_complete.return_value = LLMResult(text="She ran fast.", call_id="test")
    results = list(do_humanize_pasted_text("She ran.", False, True))
    assert len(results) == 2  # 1 paragraph + done
    out, status = results[-1]
    assert "She ran fast" in out
    mock_complete.assert_called_once()


@patch("humanize.handlers.complete")
def test_do_humanize_both_options(mock_complete: MagicMock) -> None:
    """rule_based=True, llm_humanize=True -> rule-based then LLM."""
    mock_complete.return_value = LLMResult(text="And, she ran.", call_id="test")
    results = list(do_humanize_pasted_text("Moreover, she ran.", True, True))
    assert len(results) == 2
    out, _ = results[-1]
    assert "Moreover" not in out
    mock_complete.assert_called_once()


@patch("humanize.handlers.complete")
def test_do_humanize_neither_option(mock_complete: MagicMock) -> None:
    """rule_based=False, llm_humanize=False -> pass through unchanged."""
    text = "Moreover, she ran.\n\nOriginal."
    results = list(do_humanize_pasted_text(text, False, False))
    assert len(results) == 3
    out, _ = results[-1]
    assert out == text
    mock_complete.assert_not_called()


@patch("humanize.handlers.complete")
def test_do_humanize_yields_progressively(mock_complete: MagicMock) -> None:
    """Generator yields after each paragraph."""
    mock_complete.side_effect = [
        LLMResult(text="First done.", call_id="1"),
        LLMResult(text="Second done.", call_id="2"),
    ]
    results = list(do_humanize_pasted_text("A\n\nB", False, True))
    assert len(results) == 3  # para1, para2, done
    out1, status1 = results[0]
    assert "First done" in out1
    assert "1" in status1 and "2" in status1
    out2, status2 = results[1]
    assert "First done" in out2 and "Second done" in out2
