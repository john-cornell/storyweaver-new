"""Tests for Plan vs Write LLM provider resolution (get_provider_for_task)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from config import LLMConfig, LLMOverrideConfig, LLMProvider, LLMTaskType
from config.settings import OllamaConfig
from llm.client import get_provider_for_task


def _ollama_cfg() -> OllamaConfig:
    """Ollama config for tests."""
    return OllamaConfig(base_url="http://localhost:11434", model="llama3.2")


@patch("llm.client.LLMConfig.load")
@patch("config.settings.LLMOverrideConfig.from_env")
def test_plan_uses_default_when_no_override(
    mock_override_from_env: MagicMock,
    mock_llm_load: MagicMock,
) -> None:
    """Plan tasks use default when no override set."""
    mock_llm_load.return_value = LLMConfig(anthropic=None, gemini=None, openai=None, ollama=_ollama_cfg())
    mock_override_from_env.return_value = LLMOverrideConfig(default_provider=None, plan_override=None, write_override=None)
    cfg = LLMConfig.load()
    override = LLMOverrideConfig.from_env()
    prov, model = get_provider_for_task(cfg, override, LLMTaskType.PLAN)
    assert prov == LLMProvider.OLLAMA
    assert model == "llama3.2"


@patch("llm.client.LLMConfig.load")
@patch("config.settings.LLMOverrideConfig.from_env")
def test_plan_override_when_set(
    mock_override_from_env: MagicMock,
    mock_llm_load: MagicMock,
) -> None:
    """Plan tasks use override when set."""
    mock_llm_load.return_value = LLMConfig(anthropic=None, gemini=None, openai=None, ollama=_ollama_cfg())
    mock_override_from_env.return_value = LLMOverrideConfig(
        default_provider=None,
        plan_override=(LLMProvider.OLLAMA, "llama3.2"),
        write_override=None,
    )
    cfg = LLMConfig.load()
    override = LLMOverrideConfig.from_env()
    prov, model = get_provider_for_task(cfg, override, LLMTaskType.PLAN)
    assert prov == LLMProvider.OLLAMA
    assert model == "llama3.2"


@patch("llm.client.LLMConfig.load")
@patch("config.settings.LLMOverrideConfig.from_env")
def test_write_override_provider_only_uses_config_model(
    mock_override_from_env: MagicMock,
    mock_llm_load: MagicMock,
) -> None:
    """Write override with provider only uses config model."""
    mock_llm_load.return_value = LLMConfig(anthropic=None, gemini=None, openai=None, ollama=_ollama_cfg())
    mock_override_from_env.return_value = LLMOverrideConfig(
        default_provider=None,
        plan_override=None,
        write_override=(LLMProvider.OLLAMA, ""),
    )
    cfg = LLMConfig.load()
    override = LLMOverrideConfig.from_env()
    prov, model = get_provider_for_task(cfg, override, LLMTaskType.WRITE)
    assert prov == LLMProvider.OLLAMA
    assert model == "llama3.2"


@patch("llm.client.LLMConfig.load")
@patch("config.settings.LLMOverrideConfig.from_env")
def test_default_provider_preference(
    mock_override_from_env: MagicMock,
    mock_llm_load: MagicMock,
) -> None:
    """STORYWEAVER_LLM_DEFAULT sets preferred default provider."""
    mock_llm_load.return_value = LLMConfig(anthropic=None, gemini=None, openai=None, ollama=_ollama_cfg())
    mock_override_from_env.return_value = LLMOverrideConfig(
        default_provider=LLMProvider.OLLAMA,
        plan_override=None,
        write_override=None,
    )
    cfg = LLMConfig.load()
    override = LLMOverrideConfig.from_env()
    prov, model = get_provider_for_task(cfg, override, LLMTaskType.DEFAULT)
    assert prov == LLMProvider.OLLAMA
    assert model == "llama3.2"


def test_override_config_parses_provider_model() -> None:
    """LLMOverrideConfig parses provider:model format."""
    with patch.dict("os.environ", {"STORYWEAVER_LLM_PLAN": "anthropic:claude-3-5-sonnet"}, clear=False):
        override = LLMOverrideConfig.from_env()
        assert override.plan_override is not None
        prov, model = override.plan_override
        assert prov == LLMProvider.ANTHROPIC
        assert model == "claude-3-5-sonnet"
