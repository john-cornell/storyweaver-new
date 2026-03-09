"""
Types for generation modes: enum and protocol.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class GenerationMode(str, Enum):
    """Supported story generation modes."""

    EXPANSION = "expansion"
    INTERACTIVE = "interactive"


@runtime_checkable
class ModeHandler(Protocol):
    """
    Protocol for generation mode handlers.
    Expansion mode delegates to handlers.py; interactive mode is a stub.
    """

    def supports_auto_run(self) -> bool:
        """True if this mode supports Run (auto-expand loop)."""
        ...

    def start(
        self,
        idea: str,
        steps: list[Any] | None,
        log_entries: list[str] | None,
        precis_undo: str | None,
        history: list[Any] | None,
        word_limit: int | float | None,
        content_is_beats: bool,
    ) -> Any:
        """
        Kick off writing. Expansion: précis → two paragraphs, ERL init, save.
        Returns generator (expansion) or tuple (interactive stub).
        """
        ...

    def step(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        erl_state: dict[str, Any] | None,
    ) -> Any:
        """Single step: expand next (expansion) or handle choice (interactive)."""
        ...

    def step_round(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        progress_callback: Any = None,
    ) -> Any:
        """One round of expansion (expansion only; interactive returns stub result)."""
        ...
