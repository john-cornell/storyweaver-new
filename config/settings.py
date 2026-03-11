"""
LLM configuration loaded from environment.
Allowed providers: Anthropic (Claude), Google (Gemini), OpenAI, Ollama.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from dotenv import load_dotenv

load_dotenv()


class LLMProvider(str, Enum):
    """Allowed LLM providers."""

    ANTHROPIC = "anthropic"   # Claude
    GEMINI = "gemini"        # Google Gemini
    OPENAI = "openai"
    OLLAMA = "ollama"


class LLMTaskType(str, Enum):
    """Task type for LLM routing: plan vs write vs default."""

    DEFAULT = "default"
    PLAN = "plan"
    WRITE = "write"


@dataclass(frozen=True)
class AnthropicConfig:
    """Anthropic (Claude) configuration."""

    api_key: str
    model: str = "claude-3-5-sonnet-20241022"

    @classmethod
    def from_env(cls) -> Optional[AnthropicConfig]:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        model = os.environ.get("ANTHROPIC_MODEL", cls.model).strip() or cls.model
        return cls(api_key=key, model=model)


@dataclass(frozen=True)
class GeminiConfig:
    """Google Gemini configuration."""

    api_key: str
    model: str = "gemini-1.5-flash"

    @classmethod
    def from_env(cls) -> Optional[GeminiConfig]:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        model = os.environ.get("GEMINI_MODEL", cls.model).strip() or cls.model
        return cls(api_key=key, model=model)


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI configuration."""

    api_key: str
    model: str = "gpt-4o"

    @classmethod
    def from_env(cls) -> Optional[OpenAIConfig]:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        model = os.environ.get("OPENAI_MODEL", cls.model).strip() or cls.model
        return cls(api_key=key, model=model)


VET_CONSISTENCY_MODES = ("full", "single", "multi")

GENERATION_MODES = ("expansion", "interactive")


@dataclass(frozen=True)
class GenerationModeConfig:
    """Generation mode: expansion (tree) or interactive (binary choices, replay)."""

    mode: str  # "expansion" | "interactive"

    @classmethod
    def from_env(cls) -> GenerationModeConfig:
        raw = os.environ.get("STORYWEAVER_GENERATION_MODE", "expansion").strip().lower()
        mode = raw if raw in GENERATION_MODES else "expansion"
        return cls(mode=mode)


@dataclass(frozen=True)
class VettingConfig:
    """Vetting settings: consistency check mode (full | single | multi)."""

    consistency_mode: str  # "full" | "single" | "multi"

    @classmethod
    def from_env(cls) -> VettingConfig:
        raw = os.environ.get("VET_CONSISTENCY_MODE", "single").strip().lower()
        mode = raw if raw in VET_CONSISTENCY_MODES else "single"
        return cls(consistency_mode=mode)


HUMANIZE_SCOPES = ("expansion_only", "expansion_and_precis", "all")


@dataclass(frozen=True)
class ExpansionConfig:
    """Expansion settings: beat cap, etc."""

    max_beats: int = 2

    @classmethod
    def from_env(cls) -> ExpansionConfig:
        raw = os.environ.get("BEAT_MAX_BEATS", "2").strip()
        try:
            val = int(raw)
            return cls(max_beats=max(1, val))
        except ValueError:
            return cls(max_beats=2)


@dataclass(frozen=True)
class HumanizeConfig:
    """Humanization settings: AI checker evasion for LLM output."""

    humanize_output: bool = False
    humanize_scope: str = "expansion_only"

    @classmethod
    def from_env(cls) -> HumanizeConfig:
        raw = os.environ.get("STORYWEAVER_HUMANIZE_OUTPUT", "0").strip().lower()
        humanize_output = raw in ("1", "true", "yes")
        scope_raw = os.environ.get("STORYWEAVER_HUMANIZE_SCOPE", "expansion_only").strip().lower()
        humanize_scope = scope_raw if scope_raw in HUMANIZE_SCOPES else "expansion_only"
        return cls(humanize_output=humanize_output, humanize_scope=humanize_scope)


@dataclass(frozen=True)
class OllamaConfig:
    """Ollama local configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"

    @classmethod
    def from_env(cls) -> OllamaConfig:
        base_url = os.environ.get("OLLAMA_BASE_URL", cls.base_url).strip() or cls.base_url
        model = os.environ.get("OLLAMA_MODEL", cls.model).strip() or cls.model
        return cls(base_url=base_url, model=model)


@dataclass
class LLMConfig:
    """Aggregate config for all allowed LLMs. Only enabled providers are non-None."""

    anthropic: Optional[AnthropicConfig] = field(default=None)
    gemini: Optional[GeminiConfig] = field(default=None)
    openai: Optional[OpenAIConfig] = field(default=None)
    ollama: Optional[OllamaConfig] = field(default=None)

    @classmethod
    def load(cls) -> LLMConfig:
        return cls(
            anthropic=AnthropicConfig.from_env(),
            gemini=GeminiConfig.from_env(),
            openai=OpenAIConfig.from_env(),
            ollama=OllamaConfig.from_env(),
        )

    def allowed_providers(self) -> list[LLMProvider]:
        out: list[LLMProvider] = []
        if self.anthropic is not None:
            out.append(LLMProvider.ANTHROPIC)
        if self.gemini is not None:
            out.append(LLMProvider.GEMINI)
        if self.openai is not None:
            out.append(LLMProvider.OPENAI)
        if self.ollama is not None:
            out.append(LLMProvider.OLLAMA)
        return out

    def get_model_for_provider(self, provider: LLMProvider) -> str:
        """Return model name for provider from config."""
        if provider == LLMProvider.ANTHROPIC and self.anthropic:
            return self.anthropic.model
        if provider == LLMProvider.GEMINI and self.gemini:
            return self.gemini.model
        if provider == LLMProvider.OPENAI and self.openai:
            return self.openai.model
        if provider == LLMProvider.OLLAMA and self.ollama:
            return self.ollama.model
        return "?"


_PROVIDER_STR_MAP = {
    "anthropic": LLMProvider.ANTHROPIC,
    "gemini": LLMProvider.GEMINI,
    "openai": LLMProvider.OPENAI,
    "ollama": LLMProvider.OLLAMA,
}


def _parse_provider_model(raw: str) -> Optional[Tuple[LLMProvider, str]]:
    """Parse 'provider' or 'provider:model' into (LLMProvider, model). Returns None if invalid."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    parts = s.split(":", 1)
    provider_str = parts[0].strip()
    model_override = parts[1].strip() if len(parts) > 1 else None
    provider = _PROVIDER_STR_MAP.get(provider_str)
    if provider is None:
        return None
    if model_override:
        return (provider, model_override)
    return (provider, "")  # Caller uses config model when empty


@dataclass(frozen=True)
class LLMOverrideConfig:
    """Optional overrides for plan vs write LLM. Default provider preference."""

    default_provider: Optional[LLMProvider] = None  # If set, prefer this provider for default
    plan_override: Optional[Tuple[LLMProvider, str]] = None  # (provider, model) or (provider, "") for config model
    write_override: Optional[Tuple[LLMProvider, str]] = None

    @classmethod
    def from_env(cls) -> LLMOverrideConfig:
        default_raw = os.environ.get("STORYWEAVER_LLM_DEFAULT", "").strip().lower()
        default_provider = _PROVIDER_STR_MAP.get(default_raw) if default_raw else None

        plan_raw = os.environ.get("STORYWEAVER_LLM_PLAN", "").strip()
        plan_override = _parse_provider_model(plan_raw) if plan_raw else None

        write_raw = os.environ.get("STORYWEAVER_LLM_WRITE", "").strip()
        write_override = _parse_provider_model(write_raw) if write_raw else None

        return cls(
            default_provider=default_provider,
            plan_override=plan_override,
            write_override=write_override,
        )
