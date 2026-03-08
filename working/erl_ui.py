"""
ERL tab UI: graph visualization and markdown builders for Entity/Relationship Ledger.
"""

from __future__ import annotations

import html as html_module
import logging
from pathlib import Path

from .erl import ERL

logger = logging.getLogger(__name__)

# DO NOT use a dotfile (e.g. .erl_graph_cache.png): Gradio rejects paths whose basename
# starts with "." when moving files to cache (security). Use erl_graph_cache.png instead.
_GRAPH_CACHE_PATH = Path(__file__).resolve().parent.parent / "erl_graph_cache.png"

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx
    _HAS_GRAPH_DEPS = True
except ImportError:
    _HAS_GRAPH_DEPS = False

_EDGE_LABEL_TRUNCATE = 30
_MAX_DISPLAY_NODES = 20


def _escape_md(text: str) -> str:
    """Escape user-supplied text for safe markdown display (prevent XSS)."""
    return html_module.escape((text or "").strip())


def build_erl_graph_image(erl: ERL) -> str | None:
    """
    Generate PNG graph via networkx + matplotlib.
    Returns path to cache file for gr.Image, or None when empty.
    """
    if not _HAS_GRAPH_DEPS:
        return None
    entities = erl.get("entities") or []
    relationships = erl.get("relationships") or []
    if not entities and not relationships:
        return None
    entities = [e for e in entities if isinstance(e, dict) and (e.get("name") or "").strip()]
    if not entities:
        return None
    # Limit nodes for performance
    entity_names = list({(e.get("name") or "").strip() or "(unnamed)" for e in entities})[: _MAX_DISPLAY_NODES]
    G = nx.DiGraph()
    G.add_nodes_from(entity_names)
    for r in relationships:
        if not isinstance(r, dict):
            continue
        a = (r.get("entity_a") or "").strip() or "(unknown)"
        b = (r.get("entity_b") or "").strip() or "(unknown)"
        if a in entity_names and b in entity_names:
            G.add_edge(a, b)
    fig, ax = plt.subplots(figsize=(8, 6))
    pos = nx.spring_layout(G, k=2, seed=42)
    nx.draw_networkx_nodes(G, pos, node_color="lightblue", node_size=800, ax=ax)
    nx.draw_networkx_labels(G, pos, font_size=9, ax=ax)
    edge_labels = {}
    for r in relationships:
        if not isinstance(r, dict):
            continue
        a = (r.get("entity_a") or "").strip() or "(unknown)"
        b = (r.get("entity_b") or "").strip() or "(unknown)"
        if a in entity_names and b in entity_names and G.has_edge(a, b):
            dyn = (r.get("current_dynamic") or "").strip()
            if dyn:
                edge_labels[(a, b)] = dyn[:_EDGE_LABEL_TRUNCATE] + ("…" if len(dyn) > _EDGE_LABEL_TRUNCATE else "")
    if edge_labels:
        nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=7, ax=ax)
    nx.draw_networkx_edges(G, pos, ax=ax, arrows=True, arrowsize=15)
    ax.axis("off")
    plt.tight_layout()
    path = str(_GRAPH_CACHE_PATH)
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path


def build_erl_entities_markdown(erl: ERL) -> str:
    """Markdown for entity cards: name, physical_state, inventory, current_goal."""
    entities = erl.get("entities") or []
    if not entities:
        return "*No entities yet. Start a story to populate the ledger.*"
    lines: list[str] = []
    has_valid = False
    for e in entities:
        if not isinstance(e, dict):
            continue
        has_valid = True
        name = _escape_md(e.get("name") or "(unnamed)")
        physical = _escape_md(e.get("physical_state") or "")
        goal = _escape_md(e.get("current_goal") or "")
        inv = e.get("inventory")
        inv_list = inv if isinstance(inv, list) else []
        inv_str = ", ".join(_escape_md(str(x)) for x in inv_list[:10])
        if len(inv_list) > 10:
            inv_str += ", …"
        lines.append(f"### {name}")
        if physical:
            lines.append(f"- **State:** {physical}")
        if inv_str:
            lines.append(f"- **Inventory:** {inv_str}")
        if goal:
            lines.append(f"- **Goal:** {goal}")
        lines.append("")
    if not has_valid:
        return "*No entities yet. Start a story to populate the ledger.*"
    return "\n".join(lines).rstrip()


def build_erl_global_state_markdown(erl: ERL) -> str:
    """Markdown for global_state: environment, location, time_elapsed, weather, plot_variables."""
    gs = erl.get("global_state") or {}
    if not isinstance(gs, dict):
        return "*No global state recorded.*"
    parts: list[str] = []
    for key in ("environment", "location", "time_elapsed", "weather"):
        val = gs.get(key)
        if val and str(val).strip():
            parts.append(f"- **{_escape_md(key.replace('_', ' ').title())}:** {_escape_md(str(val))}")
    pv = gs.get("plot_variables")
    if isinstance(pv, dict) and pv:
        for k, v in list(pv.items())[:10]:
            if v is not None and (v != "" or not isinstance(v, str)):
                parts.append(f"- **{_escape_md(str(k))}:** {_escape_md(str(v))}")
    if not parts:
        return "*No global state recorded.*"
    return "**Global state**\n\n" + "\n".join(parts)


def build_erl_tab_content(erl: ERL) -> tuple[str | None, str, str]:
    """
    Returns (graph_image_path, entities_md, global_state_md) for the ERL tab.
    graph_image_path is None when empty; entities_md and global_state_md are never None.
    On any exception, returns safe fallbacks so the UI never crashes.
    """
    n = len(erl.get("entities") or [])
    if n > 0:
        logger.debug("ERL tab build: entities=%d", n)
    try:
        graph_path = build_erl_graph_image(erl)
        entities_md = build_erl_entities_markdown(erl)
        global_md = build_erl_global_state_markdown(erl)
        return (graph_path, entities_md, global_md)
    except Exception as e:
        logger.exception("ERL tab build failed: %s", e)
        return (None, "*Error building ERL view — check console for details.*", "*Error building ERL view.*")
