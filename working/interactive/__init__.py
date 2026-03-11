"""
Interactive story mode: binary choices, branching, replay.
"""

from __future__ import annotations

from .handlers import do_interactive_start, do_interactive_step
from .tree_utils import get_prose_to_node, get_unexplored_nodes
from .ui import build_interactive_prose_html, build_path_tree_html

__all__ = [
    "build_interactive_prose_html",
    "build_path_tree_html",
    "do_interactive_start",
    "do_interactive_step",
    "get_prose_to_node",
    "get_unexplored_nodes",
]
