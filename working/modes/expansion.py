"""
Expansion mode handler: delegates to working.handlers (tree expansion).
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from ..handlers import do_expand_next, do_expand_round, do_start_write


class ExpansionModeHandler:
    """Mode handler for tree-expansion flow (précis → 2→4→8 paragraphs)."""

    def supports_auto_run(self) -> bool:
        return True

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
        """Delegate to do_start_write. Yields 27-element tuples (path_tree placeholder + interactive_state)."""
        for tup in do_start_write(
            idea,
            steps,
            log_entries,
            precis_undo,
            history,
            word_limit,
            content_is_beats,
        ):
            yield (*tup, "", {}, gr.update())

    def step(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        erl_state: dict[str, Any] | None,
    ) -> Any:
        """Delegate to do_expand_next."""
        return do_expand_next(
            steps,
            history,
            log_entries,
            word_limit,
            erl_state,
        )

    def step_round(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        progress_callback: Any = None,
    ) -> Any:
        """Delegate to do_expand_round."""
        return do_expand_round(
            steps,
            history,
            log_entries,
            word_limit,
            progress_callback,
        )
