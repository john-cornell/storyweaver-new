"""
StoryWeaver: Gradio app entrypoint.
Layout and event wiring only; config, working draft, and nav live in packages.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _ensure_virtualenv() -> None:
    """
    Ensure the app is running inside a Python virtual environment (preferably the project's .venv).
    Raises RuntimeError with guidance if not.
    """
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env:
        return

    prefix = Path(sys.prefix).resolve()
    # Accept interpreters whose prefix is the .venv directory itself or its Scripts subdirectory (Windows).
    if prefix.name == ".venv" or prefix.parent.name == ".venv":
        return

    raise RuntimeError(
        "StoryWeaver must be run from a Python virtual environment (expected the project's .venv).\n"
        "Activate it first (for example: `.venv\\\\Scripts\\\\activate` on Windows) and then run this app."
    )


_ensure_virtualenv()

import gradio as gr

from config import build_config_markdown
from log import build_llm_log_markdown, build_log_markdown
from ui import nav_to_config, nav_to_log, nav_to_working, nav_to_write
from llm import set_show_provider_in_log
from version import VERSION
from working import (
    EMPTY_STORY_PLACEHOLDER,
    build_current_story_html,
    build_erl_tab_content,
    build_full_history_copy_button_html,
    build_full_history_text,
    build_history_markdown,
    build_output_copy_button_html,
    build_output_paragraphs_markdown,
    do_auto_expand_next,
    do_expand_idea,
    do_generate_beat_outline,
    do_pause_auto,
    do_regenerate_beat_outline,
    do_reset_write,
    do_undo_precis,
)
from working.interactive.handlers import do_interactive_step, vet_custom_option
from working.interactive.tree_utils import get_prose_to_node, get_unexplored_nodes
from working.interactive.ui import build_path_tree_html
from working.modes import GenerationMode, get_handler


def _update_mode_and_start(mode_val: str) -> tuple[str, dict]:
    """Update generation mode state and Start button interactivity."""
    mode = (mode_val or "expansion").strip() or "expansion"
    if mode not in (GenerationMode.EXPANSION.value, GenerationMode.INTERACTIVE.value):
        mode = GenerationMode.EXPANSION.value
    return mode, gr.update(interactive=True)


def _do_start_write_dispatched(
    mode_val: str,
    idea: str,
    steps: list,
    log_entries: list,
    precis_undo: str | None,
    history: list,
    word_limit: int | float,
    content_is_beats: bool,
):
    """Dispatch Start to the appropriate mode handler."""
    mode = (mode_val or "expansion").strip() or "expansion"
    try:
        mode_enum = GenerationMode(mode)
    except ValueError:
        mode_enum = GenerationMode.EXPANSION
    handler = get_handler(mode_enum)
    yield from handler.start(idea, steps, log_entries, precis_undo, history, word_limit, content_is_beats)


def _do_expand_next_dispatched(
    mode_val: str,
    steps: list,
    history: list,
    log_entries: list,
    word_limit: int | float,
    erl_state: dict,
    interactive_state: dict,
):
    """Dispatch Expand next to the appropriate mode handler."""
    mode = (mode_val or "expansion").strip() or "expansion"
    if mode == GenerationMode.INTERACTIVE.value:
        # Interactive uses Choice A/B; Expand next is a no-op that preserves state
        entries = log_entries or []
        if not interactive_state or not interactive_state.get("nodes"):
            erl_tab = build_erl_tab_content(erl_state or {})
            return (
                steps,
                history,
                build_current_story_html(steps),
                build_history_markdown(history),
                build_output_paragraphs_markdown(steps),
                build_output_copy_button_html(steps),
                build_full_history_copy_button_html(steps, history),
                build_full_history_text(steps, history),
                erl_tab[0],
                erl_tab[1],
                erl_tab[2],
                "",
                build_log_markdown(entries),
                entries,
                gr.update(),
                erl_state or {},
            )
        prose = get_prose_to_node(interactive_state["nodes"], interactive_state["current_node_id"])
        if interactive_state.get("choice_a") or interactive_state.get("choice_b"):
            prose += f"\n\n---\n\n**Choice A:** {interactive_state.get('choice_a', '')}\n\n**Choice B:** {interactive_state.get('choice_b', '')}"
        erl_tab = build_erl_tab_content(erl_state or {})
        return (
            steps,
            history,
            prose,
            "",
            prose,
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            erl_tab[0],
            erl_tab[1],
            erl_tab[2],
            "",
            build_log_markdown(entries),
            entries,
            gr.update(),
            erl_state or {},
        )
    try:
        mode_enum = GenerationMode(mode)
    except ValueError:
        mode_enum = GenerationMode.EXPANSION
    handler = get_handler(mode_enum)
    return handler.step(steps, history, log_entries, word_limit, erl_state)


def _do_interactive_choice(
    choice_label: str,
    interactive_state: dict,
    log_entries: list,
):
    """Handle choice A or B for interactive mode."""
    if not interactive_state or not interactive_state.get("nodes"):
        entries = log_entries or []
        return interactive_state, "", gr.update(), gr.update(), "", entries, build_log_markdown(entries), gr.update()
    result = do_interactive_step(
        interactive_state["precis"],
        interactive_state.get("beats", []),
        interactive_state["nodes"],
        interactive_state["choices"],
        interactive_state["current_node_id"],
        choice_label,
        interactive_state["choice_a"] if choice_label == "A" else interactive_state["choice_b"],
        log_entries,
        is_custom=False,
    )
    nodes, choices, new_id, choice_a, choice_b, entries = result
    new_state = dict(interactive_state)
    new_state["nodes"] = nodes
    new_state["choices"] = choices
    new_state["current_node_id"] = new_id
    new_state["choice_a"] = choice_a
    new_state["choice_b"] = choice_b
    prose = get_prose_to_node(nodes, new_id)
    path_tree = build_path_tree_html(nodes, choices, new_id)
    unexplored = [nid for nid in get_unexplored_nodes(nodes, choices) if nid != new_id]
    dropdown_choices = [("— Select branch —", "")] + [(f"Node {nid}", str(nid)) for nid in unexplored]
    return new_state, prose, gr.update(), gr.update(), path_tree, entries, build_log_markdown(entries), gr.update(choices=dropdown_choices)


def _do_interactive_custom(
    custom_text: str,
    interactive_state: dict,
    log_entries: list,
):
    """Handle custom option for interactive mode (vet + use)."""
    if not interactive_state or not interactive_state.get("nodes"):
        entries = log_entries or []
        return interactive_state, "", gr.update(), gr.update(), "", entries, build_log_markdown(entries), gr.update()
    result = do_interactive_step(
        interactive_state["precis"],
        interactive_state.get("beats", []),
        interactive_state["nodes"],
        interactive_state["choices"],
        interactive_state["current_node_id"],
        "A",
        custom_text,
        log_entries,
        is_custom=True,
    )
    nodes, choices, new_id, choice_a, choice_b, entries = result
    new_state = dict(interactive_state)
    new_state["nodes"] = nodes
    new_state["choices"] = choices
    new_state["current_node_id"] = new_id
    new_state["choice_a"] = choice_a
    new_state["choice_b"] = choice_b
    prose = get_prose_to_node(nodes, new_id)
    path_tree = build_path_tree_html(nodes, choices, new_id)
    unexplored = [nid for nid in get_unexplored_nodes(nodes, choices) if nid != new_id]
    dropdown_choices = [("— Select branch —", "")] + [(f"Node {nid}", str(nid)) for nid in unexplored]
    return new_state, prose, gr.update(), gr.update(), path_tree, entries, build_log_markdown(entries), gr.update(choices=dropdown_choices)


def _do_interactive_jump_to_node(
    node_id_str: str,
    interactive_state: dict,
) -> tuple[dict, str, str, list[tuple[str, str]]]:
    """Jump to an unexplored node; set current_node_id and refresh display."""
    if not interactive_state or not interactive_state.get("nodes"):
        return interactive_state or {}, "", "", []
    try:
        node_id = int(node_id_str or "0")
    except (ValueError, TypeError):
        return interactive_state, "", "", []
    by_id = {n["id"]: n for n in interactive_state["nodes"] if isinstance(n, dict) and n.get("id") is not None}
    if node_id not in by_id:
        return interactive_state, "", "", []
    choice_by_node = {c["node_id"]: c for c in interactive_state["choices"] if isinstance(c, dict)}
    choice_rec = choice_by_node.get(node_id)
    choice_a = (choice_rec.get("choice_a_text", "") or "").strip() if choice_rec else ""
    choice_b = (choice_rec.get("choice_b_text", "") or "").strip() if choice_rec else ""
    new_state = dict(interactive_state)
    new_state["current_node_id"] = node_id
    new_state["choice_a"] = choice_a
    new_state["choice_b"] = choice_b
    prose = get_prose_to_node(new_state["nodes"], node_id)
    if choice_a or choice_b:
        prose += f"\n\n---\n\n**Choice A:** {choice_a}\n\n**Choice B:** {choice_b}"
    path_tree = build_path_tree_html(new_state["nodes"], new_state["choices"], node_id)
    unexplored = [nid for nid in get_unexplored_nodes(new_state["nodes"], new_state["choices"]) if nid != node_id]
    choices_for_dropdown = [("— Select branch —", "")] + [(f"Node {nid}", str(nid)) for nid in unexplored]
    return new_state, prose, path_tree, choices_for_dropdown


def _do_interactive_vet_only(custom_text: str, interactive_state: dict) -> str:
    """Vet custom option and return message for display."""
    if not interactive_state or not interactive_state.get("nodes"):
        return ""
    allowed, reason = vet_custom_option(
        interactive_state["precis"],
        interactive_state.get("beats", []),
        custom_text,
    )
    if allowed:
        return "**Allowed** — choice is consistent with the précis."
    return f"**Rejected:** {reason}"


def _conditional_auto_expand(
    mode_val: str,
    steps: list,
    history: list,
    log_entries: list,
    word_limit: int | float,
    debug_pause: bool,
):
    """Run do_auto_expand_next only for expansion mode; yield once for interactive."""
    if (mode_val or "").strip() == GenerationMode.INTERACTIVE.value:
        erl_tab = build_erl_tab_content({})
        yield (
            steps,
            history,
            build_current_story_html(steps),
            build_history_markdown(history),
            build_output_paragraphs_markdown(steps),
            build_output_copy_button_html(steps),
            build_full_history_copy_button_html(steps, history),
            build_full_history_text(steps, history),
            erl_tab[0],
            erl_tab[1],
            erl_tab[2],
            "",
            build_log_markdown(log_entries),
            log_entries,
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            gr.update(interactive=True),
            {},
        )
        return
    yield from do_auto_expand_next(steps, history, log_entries, word_limit, debug_pause)


def create_ui() -> gr.Blocks:
    with gr.Blocks(title=f"StoryWeaver v{VERSION}") as demo:
        gr.Markdown(f"# StoryWeaver — **v{VERSION}**")
        with gr.Row():
            with gr.Column(scale=1, min_width=160):
                gr.Markdown("**Menu**")
                menu_write_btn = gr.Button("Write", variant="secondary", size="sm")
                menu_working_btn = gr.Button("Working", variant="secondary", size="sm")
                menu_config_btn = gr.Button("Config", variant="secondary", size="sm")
                menu_log_btn = gr.Button("Log", variant="secondary", size="sm")
            with gr.Column(scale=4):
                write_panel = gr.Column(visible=True)
                with write_panel:
                    idea_tb = gr.Textbox(
                        label="Idea / Précis",
                        lines=10,
                        placeholder="Rough idea or précis. Use 'Expand idea to précis' to turn an idea into a précis. Or use 'Generate beat outline' to create a beginning/middle/end structure from the précis.",
                        max_lines=20,
                    )
                    mode_dropdown = gr.Dropdown(
                        choices=[
                            ("Expansion", GenerationMode.EXPANSION.value),
                            ("Interactive", GenerationMode.INTERACTIVE.value),
                        ],
                        value=GenerationMode.EXPANSION.value,
                        label="Generation mode",
                        interactive=True,
                    )
                    with gr.Row():
                        expand_btn = gr.Button(
                            "Expand idea to précis", variant="secondary",
                        )
                        undo_btn = gr.Button("Undo précis", variant="secondary", interactive=False)
                        gen_beats_btn = gr.Button("Generate beat outline", variant="secondary")
                        regen_btn = gr.Button("Regenerate", variant="secondary")
                        start_btn = gr.Button("Start", variant="primary")
                        reset_btn = gr.Button("Reset", variant="secondary")
                    word_slider = gr.Slider(
                        minimum=500,
                        maximum=1_000_000,
                        value=10000,
                        step=1000,
                        label="Word count",
                    )
                    progress_tb = gr.Textbox(
                        label="Progress",
                        lines=8,
                        placeholder="Notes on what's happening…",
                        interactive=True,
                    )
                    gr.Markdown("**Latest story** *(prose only, no labels)*")
                    latest_story_md = gr.Markdown(EMPTY_STORY_PLACEHOLDER)
                working_panel = gr.Column(visible=False)
                with working_panel:
                    with gr.Tabs():
                        with gr.Tab("Current story"):
                            working_current_md = gr.HTML(
                                build_current_story_html([])
                            )
                            with gr.Row():
                                choice_a_btn = gr.Button("Choice A", variant="secondary")
                                choice_b_btn = gr.Button("Choice B", variant="secondary")
                            with gr.Row():
                                custom_option_tb = gr.Textbox(
                                    label="Add my option",
                                    placeholder="Type your choice and click Validate",
                                    lines=2,
                                )
                                validate_custom_btn = gr.Button("Validate", variant="secondary")
                                use_custom_btn = gr.Button("Use", variant="secondary")
                            custom_vet_md = gr.Markdown("")
                        with gr.Tab("Path tree"):
                            working_path_tree_html = gr.HTML("<p><em>No story yet.</em></p>")
                            with gr.Row():
                                jump_to_node_dropdown = gr.Dropdown(
                                    choices=[("— Select branch —", "")],
                                    value="",
                                    label="Jump to unexplored branch",
                                    allow_custom_value=False,
                                )
                                continue_from_btn = gr.Button("Continue from here", variant="secondary")
                        with gr.Tab("Output"):
                            working_output_copy_html = gr.HTML(
                                build_output_copy_button_html([])
                            )
                            working_output_md = gr.Markdown(
                                build_output_paragraphs_markdown([])
                            )
                        with gr.Tab("History"):
                            working_history_md = gr.Markdown(
                                build_history_markdown([])
                            )
                        with gr.Tab("Full history"):
                            working_full_history_copy_html = gr.HTML(
                                build_full_history_copy_button_html([], [])
                            )
                            working_full_history_md = gr.Markdown(
                                build_full_history_text([], [])
                            )
                        with gr.Tab("Entity/Relationship"):
                            _erl_empty = build_erl_tab_content({})
                            working_erl_graph = gr.Image(
                                value=_erl_empty[0],
                                label="Entities & relationships",
                                show_label=True,
                            )
                            working_erl_entities_md = gr.Markdown(_erl_empty[1])
                            working_erl_global_md = gr.Markdown(_erl_empty[2])
                    working_status_md = gr.Markdown("")
                    debug_pause_cb = gr.Checkbox(
                        label="Debug: pause after each step",
                        value=False,
                    )
                    with gr.Row():
                        expand_next_btn = gr.Button(
                            "Expand next", variant="secondary",
                        )
                        run_btn = gr.Button("Run", variant="primary")
                        pause_btn = gr.Button("Pause", variant="secondary")
                config_panel = gr.Column(visible=False)
                with config_panel:
                    config_md = gr.Markdown(build_config_markdown())
                log_panel = gr.Column(visible=False)
                with log_panel:
                    show_provider_cb = gr.Checkbox(
                        label="Show provider and call ID in LLM log",
                        value=False,
                    )
                    log_md = gr.Markdown(build_log_markdown([]))
                    llm_log_md = gr.Markdown(build_llm_log_markdown())
                    llm_log_timer = gr.Timer(1)
        gr.Markdown(f"---\n*Version: {VERSION}*")

        steps_state = gr.State([])
        log_state = gr.State([])
        precis_undo_state = gr.State(None)
        content_is_beats_state = gr.State(False)
        history_state = gr.State([])
        erl_state = gr.State({})
        generation_mode_state = gr.State(GenerationMode.EXPANSION.value)
        interactive_state = gr.State({})

        # Nav I/O contract: nav_outputs/nav_inputs counts MUST match ui.nav._nav_outputs return.
        # DO NOT change nav_outputs or nav_inputs without updating _nav_outputs in ui/nav.py.
        # DO NOT return file paths whose basename starts with "." to gr.Image — Gradio rejects
        # dotfiles in cwd for security (InvalidPathError), breaking all buttons.
        nav_outputs = [
            write_panel,
            working_panel,
            config_panel,
            log_panel,
            working_current_md,
            working_history_md,
            working_output_md,
            working_output_copy_html,
            working_full_history_copy_html,
            working_full_history_md,
            log_md,
            log_state,
            llm_log_md,
            latest_story_md,
            working_path_tree_html,
        ]
        nav_inputs = [steps_state, history_state, log_state, interactive_state, generation_mode_state]
        menu_write_btn.click(
            fn=nav_to_write,
            inputs=nav_inputs,
            outputs=nav_outputs,
        )
        menu_working_btn.click(
            fn=nav_to_working,
            inputs=nav_inputs,
            outputs=nav_outputs,
        )
        menu_config_btn.click(
            fn=nav_to_config,
            inputs=nav_inputs,
            outputs=nav_outputs,
        )
        menu_log_btn.click(
            fn=nav_to_log,
            inputs=nav_inputs,
            outputs=nav_outputs,
        )
        llm_log_timer.tick(fn=build_llm_log_markdown, outputs=[llm_log_md])
        show_provider_cb.change(
            fn=set_show_provider_in_log,
            inputs=[show_provider_cb],
            outputs=[],
        )
        mode_dropdown.change(
            fn=_update_mode_and_start,
            inputs=[mode_dropdown],
            outputs=[generation_mode_state, start_btn],
        )

        expand_btn.click(
            fn=do_expand_idea,
            inputs=[idea_tb, log_state, precis_undo_state, content_is_beats_state],
            outputs=[idea_tb, progress_tb, log_md, log_state, precis_undo_state, undo_btn, content_is_beats_state],
        )
        undo_btn.click(
            fn=do_undo_precis,
            inputs=[precis_undo_state, log_state, content_is_beats_state],
            outputs=[idea_tb, progress_tb, log_md, log_state, precis_undo_state, undo_btn, content_is_beats_state],
        )
        gen_beats_btn.click(
            fn=do_generate_beat_outline,
            inputs=[idea_tb, log_state, precis_undo_state, content_is_beats_state],
            outputs=[idea_tb, progress_tb, log_md, log_state, precis_undo_state, undo_btn, content_is_beats_state],
        )
        regen_btn.click(
            fn=do_regenerate_beat_outline,
            inputs=[precis_undo_state, idea_tb, log_state, content_is_beats_state],
            outputs=[idea_tb, progress_tb, log_md, log_state, undo_btn, content_is_beats_state],
        )
        def _do_reset_with_interactive():
            result = do_reset_write()
            return (*result, {})

        reset_btn.click(
            fn=_do_reset_with_interactive,
            inputs=[],
            outputs=[
                idea_tb,
                progress_tb,
                log_md,
                log_state,
                precis_undo_state,
                steps_state,
                history_state,
                erl_state,
                latest_story_md,
                expand_btn,
                undo_btn,
                content_is_beats_state,
                interactive_state,
            ],
        )
        start_btn.click(
            fn=_do_start_write_dispatched,
            inputs=[
                generation_mode_state,
                idea_tb,
                steps_state,
                log_state,
                precis_undo_state,
                history_state,
                word_slider,
                content_is_beats_state,
            ],
            outputs=[
                steps_state,
                working_current_md,
                working_history_md,
                working_output_md,
                working_output_copy_html,
                working_full_history_copy_html,
                working_full_history_md,
                working_erl_graph,
                working_erl_entities_md,
                working_erl_global_md,
                working_status_md,
                progress_tb,
                write_panel,
                working_panel,
                config_panel,
                log_panel,
                log_md,
                log_state,
                expand_btn,
                expand_next_btn,
                precis_undo_state,
                undo_btn,
                history_state,
                erl_state,
                content_is_beats_state,
                working_path_tree_html,
                interactive_state,
                jump_to_node_dropdown,
            ],
        ).then(
            fn=_conditional_auto_expand,
            inputs=[generation_mode_state, steps_state, history_state, log_state, word_slider, debug_pause_cb],
            outputs=[
                steps_state,
                history_state,
                working_current_md,
                working_history_md,
                working_output_md,
                working_output_copy_html,
                working_full_history_copy_html,
                working_full_history_md,
                working_erl_graph,
                working_erl_entities_md,
                working_erl_global_md,
                working_status_md,
                log_md,
                log_state,
                expand_next_btn,
                run_btn,
                start_btn,
                expand_btn,
                undo_btn,
                erl_state,
            ],
        )
        expand_next_btn.click(
            fn=_do_expand_next_dispatched,
            inputs=[generation_mode_state, steps_state, history_state, log_state, word_slider, erl_state, interactive_state],
            outputs=[
                steps_state,
                history_state,
                working_current_md,
                working_history_md,
                working_output_md,
                working_output_copy_html,
                working_full_history_copy_html,
                working_full_history_md,
                working_erl_graph,
                working_erl_entities_md,
                working_erl_global_md,
                working_status_md,
                log_md,
                log_state,
                expand_next_btn,
                erl_state,
            ],
        )
        run_btn.click(
            fn=lambda mode, s, h, l, w, d: _conditional_auto_expand(mode, s, h, l, w, d),
            inputs=[generation_mode_state, steps_state, history_state, log_state, word_slider, debug_pause_cb],
            outputs=[
                steps_state,
                history_state,
                working_current_md,
                working_history_md,
                working_output_md,
                working_output_copy_html,
                working_full_history_copy_html,
                working_full_history_md,
                working_erl_graph,
                working_erl_entities_md,
                working_erl_global_md,
                working_status_md,
                log_md,
                log_state,
                expand_next_btn,
                run_btn,
                start_btn,
                expand_btn,
                undo_btn,
                erl_state,
            ],
        )
        # Pause intentionally has no outputs; it only sets the stop flag for the auto thread.
        pause_btn.click(fn=do_pause_auto, inputs=[], outputs=[])

        # Interactive mode: Choice A/B, custom option, and Continue from here
        choice_a_btn.click(
            fn=lambda s, l: _do_interactive_choice("A", s, l),
            inputs=[interactive_state, log_state],
            outputs=[interactive_state, working_current_md, choice_a_btn, choice_b_btn, working_path_tree_html, log_state, log_md, jump_to_node_dropdown],
        )
        choice_b_btn.click(
            fn=lambda s, l: _do_interactive_choice("B", s, l),
            inputs=[interactive_state, log_state],
            outputs=[interactive_state, working_current_md, choice_a_btn, choice_b_btn, working_path_tree_html, log_state, log_md, jump_to_node_dropdown],
        )
        validate_custom_btn.click(
            fn=_do_interactive_vet_only,
            inputs=[custom_option_tb, interactive_state],
            outputs=[custom_vet_md],
        )
        use_custom_btn.click(
            fn=_do_interactive_custom,
            inputs=[custom_option_tb, interactive_state, log_state],
            outputs=[interactive_state, working_current_md, choice_a_btn, choice_b_btn, working_path_tree_html, log_state, log_md, jump_to_node_dropdown],
        ).then(
            fn=lambda: "",
            inputs=[],
            outputs=[custom_option_tb],
        ).then(
            fn=lambda: "",
            inputs=[],
            outputs=[custom_vet_md],
        )
        continue_from_btn.click(
            fn=_do_interactive_jump_to_node,
            inputs=[jump_to_node_dropdown, interactive_state],
            outputs=[interactive_state, working_current_md, working_path_tree_html, jump_to_node_dropdown],
        )
    return demo


def main() -> None:
    level_name = os.environ.get("STORYWEAVER_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("StoryWeaver v%s starting", VERSION)
    demo = create_ui()
    demo.launch()


if __name__ == "__main__":
    main()
