"""
LLM configuration loaded from environment.
Allowed providers: Anthropic (Claude), Google (Gemini), OpenAI, Ollama.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class LLMProvider(str, Enum):
    """Allowed LLM providers."""

    ANTHROPIC = "anthropic"   # Claude
    GEMINI = "gemini"        # Google Gemini
    OPENAI = "openai"
    OLLAMA = "ollama"


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
