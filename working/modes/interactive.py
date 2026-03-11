"""
Interactive mode handler: binary choices, branching, replay.
"""

from __future__ import annotations

from typing import Any

from ..interactive.handlers import do_interactive_start, do_interactive_step
from ..interactive.tree_utils import get_prose_to_node, get_unexplored_nodes
from ..interactive.ui import build_interactive_prose_html, build_path_tree_html


class InteractiveModeHandler:
    """Handler for interactive story mode (binary choices, branching, replay)."""

    def supports_auto_run(self) -> bool:
        return False

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
        """Start interactive story. Returns generator yielding once for UI compatibility."""
        result = do_interactive_start(idea, log_entries, content_is_beats)
        precis, beats, name, nodes, choices, current_node_id, choice_a, choice_b, entries = result
        interactive_state = {
            "precis": precis,
            "beats": beats,
            "name": name,
            "nodes": nodes,
            "choices": choices,
            "current_node_id": current_node_id,
            "choice_a": choice_a,
            "choice_b": choice_b,
        }
        prose = get_prose_to_node(nodes, current_node_id) if nodes and current_node_id else ""
        prose_html = build_interactive_prose_html(prose, choice_a, choice_b)
        path_tree = build_path_tree_html(nodes, choices, current_node_id)
        unexplored = [nid for nid in get_unexplored_nodes(nodes, choices) if nid != current_node_id]
        jump_choices = [("— Select branch —", "")] + [(f"Node {nid}", str(nid)) for nid in unexplored]
        import gradio as gr
        from log import build_log_markdown
        from .. import build_erl_tab_content
        from ..steps_ui import (
            build_full_history_copy_button_html,
            build_full_history_text,
            build_output_copy_button_html,
        )
        erl_tab = build_erl_tab_content({})
        empty_steps = steps or []
        empty_history = history or []
        yield (
            empty_steps,
            prose_html,
            "",  # working_history_md (unused for interactive)
            prose,
            build_output_copy_button_html([]),
            build_full_history_copy_button_html(empty_steps, empty_history),
            build_full_history_text(empty_steps, empty_history),
            erl_tab[0],
            erl_tab[1],
            erl_tab[2],
            "Interactive story started." if nodes else "Enter an idea first.",
            "",
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            build_log_markdown(entries),
            entries,
            gr.update(interactive=True),
            gr.update(interactive=True),
            precis_undo,
            gr.update(interactive=precis_undo is not None),
            empty_history,
            {},
            content_is_beats,
            path_tree,
            interactive_state,
            gr.update(choices=jump_choices),
        )

    def step(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        erl_state: dict[str, Any] | None,
    ) -> Any:
        """Step not used for interactive; choice handling is via separate handlers."""
        raise NotImplementedError("Use do_interactive_step with choice_label/choice_text")

    def step_round(
        self,
        steps: list[Any] | None,
        history: list[Any] | None,
        log_entries: list[str] | None,
        word_limit: int | float | None,
        progress_callback: Any = None,
    ) -> Any:
        """No-op for interactive (no auto-run)."""
        import gradio as gr
        from log import build_log_markdown
        return (
            steps or [],
            history or [],
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            {},
            {},
            {},
            "Interactive mode has no auto-run.",
            build_log_markdown(log_entries or []),
            log_entries or [],
            gr.update(),
            False,
        )
