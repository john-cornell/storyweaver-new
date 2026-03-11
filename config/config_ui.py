"""
Config panel UI: builds the markdown shown on the Config screen.
Shows all env vars: what's available and what's set.
"""

from __future__ import annotations

import os
from typing import Callable

from .settings import (
    ExpansionConfig,
    GenerationModeConfig,
    HumanizeConfig,
    LLMConfig,
    LLMOverrideConfig,
    VettingConfig,
)

# Registry: (section, env_var, description, secret, default)
ENV_REGISTRY: list[tuple[str, str, str, bool, str | None]] = [
    ("Logging", "STORYWEAVER_LOG_LEVEL", "DEBUG, INFO, WARNING, ERROR", False, "DEBUG"),
    ("Logging", "STORYWEAVER_LLM_LOG_PATH", "Path for LLM call log", False, "llm_calls.log"),
    ("Expansion", "BEAT_MAX_BEATS", "Max beats before SCENE fallback", False, "2"),
    ("Expansion", "STORYWEAVER_GENERATION_MODE", "expansion | interactive", False, "expansion"),
    ("Vetting", "VET_CONSISTENCY_MODE", "full | single | multi", False, "single"),
    ("Humanization", "STORYWEAVER_HUMANIZE_OUTPUT", "0 | 1 to enable", False, "0"),
    ("Humanization", "STORYWEAVER_HUMANIZE_SCOPE", "expansion_only | expansion_and_precis | all", False, "expansion_only"),
    ("Plan vs Write LLM", "STORYWEAVER_LLM_DEFAULT", "Default provider: anthropic | gemini | openai | ollama", False, None),
    ("Plan vs Write LLM", "STORYWEAVER_LLM_PLAN", "Override for plan tasks (precis, beats, vetting). provider or provider:model", False, None),
    ("Plan vs Write LLM", "STORYWEAVER_LLM_WRITE", "Override for write tasks (expansion prose, humanize). provider or provider:model", False, None),
    ("Anthropic", "ANTHROPIC_API_KEY", "API key", True, None),
    ("Anthropic", "ANTHROPIC_MODEL", "Model name", False, "claude-3-5-sonnet-20241022"),
    ("Gemini", "GEMINI_API_KEY", "API key", True, None),
    ("Gemini", "GEMINI_MODEL", "Model name", False, "gemini-1.5-flash"),
    ("OpenAI", "OPENAI_API_KEY", "API key", True, None),
    ("OpenAI", "OPENAI_MODEL", "Model name", False, "gpt-4o"),
    ("Ollama", "OLLAMA_BASE_URL", "Base URL", False, "http://localhost:11434"),
    ("Ollama", "OLLAMA_MODEL", "Model name", False, "llama3.2"),
]


def _resolve_value(
    env_var: str,
    secret: bool,
    default: str | None,
    resolver: Callable[[], str] | None,
) -> str:
    """Resolve display value for an env var. Secrets show 'set' or 'not set' only."""
    if secret:
        val = os.environ.get(env_var, "").strip()
        return "set" if val else "not set"
    if resolver:
        return resolver()
    val = os.environ.get(env_var, "").strip()
    if val:
        return val
    return f"(default: {default})" if default is not None else ""


def _override_display(val: object) -> str:
    """Display override value: provider or (provider, model)."""
    if val is None:
        return "(not set)"
    if isinstance(val, tuple):
        prov, model = val
        prov_str = prov.value if hasattr(prov, "value") else str(prov)
        if model:
            return f"{prov_str}:{model}"
        return prov_str
    return str(val.value) if hasattr(val, "value") else str(val)


def _build_resolvers(cfg: LLMConfig) -> dict[tuple[str, str], Callable[[], str]]:
    """Build resolver functions from config classes for accurate display."""
    exp = ExpansionConfig.from_env()
    vet = VettingConfig.from_env()
    gen = GenerationModeConfig.from_env()
    hum = HumanizeConfig.from_env()
    override_cfg = LLMOverrideConfig.from_env()
    return {
        ("Expansion", "BEAT_MAX_BEATS"): lambda: str(exp.max_beats),
        ("Expansion", "STORYWEAVER_GENERATION_MODE"): lambda: gen.mode,
        ("Vetting", "VET_CONSISTENCY_MODE"): lambda: vet.consistency_mode,
        ("Humanization", "STORYWEAVER_HUMANIZE_OUTPUT"): lambda: "1" if hum.humanize_output else "0",
        ("Humanization", "STORYWEAVER_HUMANIZE_SCOPE"): lambda: hum.humanize_scope,
        ("Plan vs Write LLM", "STORYWEAVER_LLM_DEFAULT"): lambda: _override_display(override_cfg.default_provider),
        ("Plan vs Write LLM", "STORYWEAVER_LLM_PLAN"): lambda: _override_display(override_cfg.plan_override),
        ("Plan vs Write LLM", "STORYWEAVER_LLM_WRITE"): lambda: _override_display(override_cfg.write_override),
        ("Anthropic", "ANTHROPIC_MODEL"): lambda: cfg.anthropic.model if cfg.anthropic else "(default: claude-3-5-sonnet-20241022)",
        ("Gemini", "GEMINI_MODEL"): lambda: cfg.gemini.model if cfg.gemini else "(default: gemini-1.5-flash)",
        ("OpenAI", "OPENAI_MODEL"): lambda: cfg.openai.model if cfg.openai else "(default: gpt-4o)",
        ("Ollama", "OLLAMA_BASE_URL"): lambda: cfg.ollama.base_url if cfg.ollama else "(default: http://localhost:11434)",
        ("Ollama", "OLLAMA_MODEL"): lambda: cfg.ollama.model if cfg.ollama else "(default: llama3.2)",
    }


def build_config_markdown() -> str:
    """Build markdown for the Config panel: all env vars and LLM provider status."""
    cfg = LLMConfig.load()
    resolvers = _build_resolvers(cfg)
    lines: list[str] = []

    # LLM provider summary (existing)
    lines.extend([
        "## LLM configuration",
        "",
        "| Provider | Status | Model / URL |",
        "|----------|--------|-------------|",
    ])
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

    # All env vars by section
    lines.extend(["", "---", "", "## All environment variables", ""])
    current_section = ""
    for section, env_var, description, secret, default in ENV_REGISTRY:
        if section != current_section:
            current_section = section
            lines.extend([f"### {section}", "", "| Env Var | Description | Value / Status |", "|---------|-------------|----------------|"])
        resolver = resolvers.get((section, env_var))
        value = _resolve_value(env_var, secret, default, resolver)
        lines.append(f"| **{env_var}** | {description} | `{value}` |")
    return "\n".join(lines)
