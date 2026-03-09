"""Tests for mode registry and handlers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from working.modes import GenerationMode, get_handler
from working.modes.expansion import ExpansionModeHandler
from working.modes.interactive import InteractiveModeHandler


def test_get_handler_expansion() -> None:
    """get_handler(EXPANSION) returns ExpansionModeHandler."""
    handler = get_handler(GenerationMode.EXPANSION)
    assert isinstance(handler, ExpansionModeHandler)
    assert handler.supports_auto_run() is True


def test_get_handler_interactive() -> None:
    """get_handler(INTERACTIVE) returns InteractiveModeHandler stub."""
    handler = get_handler(GenerationMode.INTERACTIVE)
    assert isinstance(handler, InteractiveModeHandler)
    assert handler.supports_auto_run() is False


@patch("working.interactive.handlers.save_interactive_story")
@patch("working.interactive.handlers.complete")
def test_interactive_start_returns_generator(mock_complete: MagicMock, mock_save: MagicMock) -> None:
    """Interactive mode start returns a generator yielding UI tuple."""
    mock_complete.side_effect = [
        MagicMock(text="Opening.", call_id="o"),
        MagicMock(text="A: One\nB: Two", call_id="c"),
    ]
    handler = get_handler(GenerationMode.INTERACTIVE)
    result = handler.start("Précis", [], [], None, [], 10000, False)
    assert hasattr(result, "__iter__") and hasattr(result, "__next__")
    first = next(result)
    assert isinstance(first, tuple)
    assert len(first) == 28


def test_interactive_step_raises() -> None:
    """Interactive mode step raises NotImplementedError (use choice handlers instead)."""
    handler = get_handler(GenerationMode.INTERACTIVE)
    with pytest.raises(NotImplementedError, match="do_interactive_step"):
        handler.step([], [], [], 10000, None)
