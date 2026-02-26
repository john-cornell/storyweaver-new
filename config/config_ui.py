"""
Config panel UI: builds the markdown shown on the Config screen.
"""

from __future__ import annotations

from .settings import LLMConfig


def build_config_markdown() -> str:
    """Build markdown for the Config panel (provider status table)."""
    cfg = LLMConfig.load()
    lines = [
        "## LLM configuration",
        "",
        "| Provider | Status | Model / URL |",
        "|----------|--------|-------------|",
    ]
    if cfg.anthropic:
        lines.append(f"| **Anthropic (Claude)** | enabled | `{cfg.anthropic.model}` |")
    else:
        lines.append("| Anthropic (Claude) | not configured | set `ANTHROPIC_API_KEY` |")
    if cfg.gemini:
        lines.append(f"| **Gemini** | enabled | `{cfg.gemini.model}` |")
    else:
        lines.append("| Gemini | not configured | set `GEMINI_API_KEY` |")
    if cfg.openai:
        lines.append(f"| **OpenAI** | enabled | `{cfg.openai.model}` |")
    else:
        lines.append("| OpenAI | not configured | set `OPENAI_API_KEY` |")
    if cfg.ollama:
        lines.append(f"| **Ollama** | enabled | `{cfg.ollama.model}` @ `{cfg.ollama.base_url}` |")
    else:
        lines.append("| Ollama | not configured | optional `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |")
    lines.extend(["", "**Allowed providers:** " + ", ".join(p.value for p in cfg.allowed_providers())])
    return "\n".join(lines)
