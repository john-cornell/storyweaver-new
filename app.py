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
    do_expand_next,
    do_generate_beat_outline,
    do_pause_auto,
    do_regenerate_beat_outline,
    do_reset_write,
    do_start_write,
    do_undo_precis,
)


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
        ]
        nav_inputs = [steps_state, history_state, log_state]
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
        reset_btn.click(
            fn=do_reset_write,
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
            ],
        )
        start_btn.click(
            fn=do_start_write,
            inputs=[
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
            ],
        ).then(
            fn=do_auto_expand_next,
            inputs=[steps_state, history_state, log_state, word_slider, debug_pause_cb],
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
            fn=do_expand_next,
            inputs=[steps_state, history_state, log_state, word_slider, erl_state],
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
            fn=do_auto_expand_next,
            inputs=[steps_state, history_state, log_state, word_slider, debug_pause_cb],
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
