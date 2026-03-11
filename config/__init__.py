"""
Config package: LLM settings and Config panel UI.
"""

from __future__ import annotations

from .settings import (
    ExpansionConfig,
    GenerationModeConfig,
    HumanizeConfig,
    HUMANIZE_SCOPES,
    LLMConfig,
    LLMOverrideConfig,
    LLMProvider,
    LLMTaskType,
    VET_CONSISTENCY_MODES,
    VettingConfig,
)
from .config_ui import build_config_markdown

__all__ = [
    "ExpansionConfig",
    "GenerationModeConfig",
    "HumanizeConfig",
    "HUMANIZE_SCOPES",
    "LLMConfig",
    "LLMOverrideConfig",
    "LLMProvider",
    "LLMTaskType",
    "VET_CONSISTENCY_MODES",
    "VettingConfig",
    "build_config_markdown",
]
