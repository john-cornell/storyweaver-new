"""
Thin LLM client using configured provider (Anthropic, Gemini, OpenAI, Ollama).
Uses first available provider from config.
Logs every call to llm_calls.log with purpose, API outcome, and real-time flush.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import threading
import time
import uuid
from dataclasses import dataclass

from config import LLMConfig, LLMOverrideConfig, LLMProvider, LLMTaskType

logger = logging.getLogger(__name__)
_llm_logger_lock = threading.Lock()
_llm_log_buffer: list[str] = []
_llm_log_buffer_lock = threading.Lock()
_LLM_LOG_BUFFER_MAX = 200
_show_provider_in_log: bool = False


def set_show_provider_in_log(show: bool) -> None:
    """Set whether provider, model, and call_id appear in LLM log lines. Called from UI checkbox."""
    global _show_provider_in_log
    _show_provider_in_log = bool(show)


def _append_to_llm_buffer(line: str) -> None:
    """Append line to in-memory buffer for web UI; cap at max entries."""
    with _llm_log_buffer_lock:
        _llm_log_buffer.append(line)
        while len(_llm_log_buffer) > _LLM_LOG_BUFFER_MAX:
            _llm_log_buffer.pop(0)


def get_llm_log_buffer() -> list[str]:
    """Return copy of LLM log buffer for web UI (thread-safe)."""
    with _llm_log_buffer_lock:
        return list(_llm_log_buffer)


@dataclass(frozen=True)
class LLMResult:
    """Result of an LLM completion; includes call_id for outcome logging."""

    text: str
    call_id: str


class _FlushingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that flushes after each emit for real-time log visibility."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _get_llm_log_path() -> str:
    """Return path for llm_calls.log from env or default."""
    return os.environ.get("STORYWEAVER_LLM_LOG_PATH", "llm_calls.log")


def _get_llm_logger() -> logging.Logger:
    """Return dedicated logger for LLM calls; creates handler on first use (thread-safe)."""
    llm_logger = logging.getLogger("storyweaver.llm_calls")
    with _llm_logger_lock:
        if llm_logger.handlers:
            return llm_logger
        path = _get_llm_log_path()
        log_dir = os.path.dirname(path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handler = _FlushingRotatingFileHandler(
            path,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        llm_logger.addHandler(handler)
        llm_logger.setLevel(logging.INFO)
        llm_logger.propagate = False
    return llm_logger


def _complete_anthropic(cfg: LLMConfig, prompt: str, system: str | None, model_override: str | None = None) -> str:
    assert cfg.anthropic is not None
    import anthropic
    model = (model_override or "").strip() or cfg.anthropic.model
    try:
        c = anthropic.Anthropic(api_key=cfg.anthropic.api_key)
        kwargs: dict = {"model": model, "max_tokens": 8192, "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        r = c.messages.create(**kwargs)
        response = (r.content[0].text if r.content else "").strip()
        logger.debug("LLM response: len=%d", len(response))
        return response
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        raise


def _complete_gemini(cfg: LLMConfig, prompt: str, system: str | None, model_override: str | None = None) -> str:
    assert cfg.gemini is not None
    model = (model_override or "").strip() or cfg.gemini.model
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=cfg.gemini.api_key)
        config_kwargs: dict = {"max_output_tokens": 8192}
        if system:
            config_kwargs["system_instruction"] = system
        config = types.GenerateContentConfig(**config_kwargs)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        text = (response.text or "").strip()
        logger.debug("LLM response: len=%d", len(text))
        return text
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        raise


def _complete_openai(cfg: LLMConfig, prompt: str, system: str | None, model_override: str | None = None) -> str:
    assert cfg.openai is not None
    model = (model_override or "").strip() or cfg.openai.model
    try:
        from openai import OpenAI
        c = OpenAI(api_key=cfg.openai.api_key)
        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        r = c.chat.completions.create(model=model, messages=messages, max_tokens=8192)
        response = (r.choices[0].message.content or "").strip()
        logger.debug("LLM response: len=%d", len(response))
        return response
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        raise


def _complete_ollama(cfg: LLMConfig, prompt: str, system: str | None, model_override: str | None = None) -> str:
    assert cfg.ollama is not None
    model = (model_override or "").strip() or cfg.ollama.model
    try:
        from openai import OpenAI
        c = OpenAI(base_url=cfg.ollama.base_url.rstrip("/") + "/v1", api_key="ollama")
        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        r = c.chat.completions.create(model=model, messages=messages, max_tokens=8192)
        response = (r.choices[0].message.content or "").strip()
        logger.debug("LLM response: len=%d", len(response))
        return response
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        raise


def get_first_provider() -> LLMProvider | None:
    """Return first configured provider, or None if none available."""
    cfg = LLMConfig.load()
    for p in (LLMProvider.ANTHROPIC, LLMProvider.GEMINI, LLMProvider.OPENAI, LLMProvider.OLLAMA):
        if p == LLMProvider.ANTHROPIC and cfg.anthropic:
            return p
        if p == LLMProvider.GEMINI and cfg.gemini:
            return p
        if p == LLMProvider.OPENAI and cfg.openai:
            return p
        if p == LLMProvider.OLLAMA and cfg.ollama:
            return p
    return None


def _provider_configured(cfg: LLMConfig, provider: LLMProvider) -> bool:
    """Return True if provider is configured and available."""
    if provider == LLMProvider.ANTHROPIC and cfg.anthropic:
        return True
    if provider == LLMProvider.GEMINI and cfg.gemini:
        return True
    if provider == LLMProvider.OPENAI and cfg.openai:
        return True
    if provider == LLMProvider.OLLAMA and cfg.ollama:
        return True
    return False


def _first_provider_from_cfg(cfg: LLMConfig) -> LLMProvider | None:
    """Return first configured provider from cfg, or None."""
    for p in (LLMProvider.ANTHROPIC, LLMProvider.GEMINI, LLMProvider.OPENAI, LLMProvider.OLLAMA):
        if _provider_configured(cfg, p):
            return p
    return None


def get_provider_for_task(
    cfg: LLMConfig,
    override_cfg: LLMOverrideConfig,
    task_type: LLMTaskType,
) -> tuple[LLMProvider, str]:
    """
    Resolve provider and model for a task. Returns (provider, model).
    Uses plan/write overrides when set and valid; else default.
    """
    # Resolve default provider
    def _default() -> tuple[LLMProvider, str]:
        if override_cfg.default_provider and _provider_configured(cfg, override_cfg.default_provider):
            p = override_cfg.default_provider
            return (p, cfg.get_model_for_provider(p))
        first = _first_provider_from_cfg(cfg)
        if first is None:
            raise RuntimeError(
                "No LLM provider configured. Set one of ANTHROPIC_API_KEY, GEMINI_API_KEY, "
                "OPENAI_API_KEY, or Ollama (OLLAMA_BASE_URL)."
            )
        return (first, cfg.get_model_for_provider(first))

    if task_type == LLMTaskType.PLAN and override_cfg.plan_override:
        prov, model_part = override_cfg.plan_override
        if _provider_configured(cfg, prov):
            model = (model_part or "").strip() or cfg.get_model_for_provider(prov)
            return (prov, model)
        logger.warning("STORYWEAVER_LLM_PLAN override provider %s not configured; using default", prov)
    if task_type == LLMTaskType.WRITE and override_cfg.write_override:
        prov, model_part = override_cfg.write_override
        if _provider_configured(cfg, prov):
            model = (model_part or "").strip() or cfg.get_model_for_provider(prov)
            return (prov, model)
        logger.warning("STORYWEAVER_LLM_WRITE override provider %s not configured; using default", prov)
    return _default()


def complete(
    prompt: str,
    system: str | None = None,
    *,
    purpose: str,
    task_type: LLMTaskType = LLMTaskType.DEFAULT,
) -> LLMResult:
    """
    Run one completion using the configured LLM for the task type.
    Logs START and END to llm_calls.log and in-memory buffer for web UI.
    Raises RuntimeError if no provider is configured or on API errors.
    """
    from datetime import datetime, timezone

    cfg = LLMConfig.load()
    override_cfg = LLMOverrideConfig.from_env()
    provider, model = get_provider_for_task(cfg, override_cfg, task_type)
    call_id = uuid.uuid4().hex[:8]
    prompt_len = len(prompt)
    system_len = len(system) if system else 0

    llm_log = _get_llm_logger()
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if _show_provider_in_log:
        start_line = (
            f"[{ts}] LLM_START call_id={call_id} purpose={purpose} provider={str(provider)} "
            f"model={model} prompt_len={prompt_len} system_len={system_len}"
        )
    else:
        start_line = f"[{ts}] LLM_START purpose={purpose} prompt_len={prompt_len} system_len={system_len}"
    llm_log.info("%s", start_line)
    _append_to_llm_buffer(start_line)

    t0 = time.perf_counter()
    try:
        if provider == LLMProvider.ANTHROPIC and cfg.anthropic:
            result = _complete_anthropic(cfg, prompt, system, model_override=model)
        elif provider == LLMProvider.GEMINI and cfg.gemini:
            result = _complete_gemini(cfg, prompt, system, model_override=model)
        elif provider == LLMProvider.OPENAI and cfg.openai:
            result = _complete_openai(cfg, prompt, system, model_override=model)
        elif provider == LLMProvider.OLLAMA and cfg.ollama:
            result = _complete_ollama(cfg, prompt, system, model_override=model)
        else:
            raise RuntimeError("No LLM provider available.")
        elapsed = time.perf_counter() - t0
        ts_end = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if _show_provider_in_log:
            end_line = (
                f"[{ts_end}] LLM_END call_id={call_id} elapsed_s={elapsed:.3f} "
                f"response_len={len(result)} api_status=success"
            )
        else:
            end_line = f"[{ts_end}] LLM_END elapsed_s={elapsed:.3f} response_len={len(result)} api_status=success"
        llm_log.info("%s", end_line)
        _append_to_llm_buffer(end_line)
        logger.debug("LLM complete: provider=%s model=%s elapsed=%.2fs", provider, model, elapsed)
        return LLMResult(text=result, call_id=call_id)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        ts_end = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        err_msg = str(e).replace("\n", " ").replace("=", "-")[:200]
        if _show_provider_in_log:
            end_line = f"[{ts_end}] LLM_END call_id={call_id} elapsed_s={elapsed:.3f} api_status=error error={err_msg}"
        else:
            end_line = f"[{ts_end}] LLM_END elapsed_s={elapsed:.3f} api_status=error error={err_msg}"
        llm_log.info("%s", end_line)
        _append_to_llm_buffer(end_line)
        raise


def log_llm_outcome(call_id: str, accepted: bool, reason: str | None = None) -> None:
    """
    Log business-level outcome (accepted/rejected) for an LLM call.
    Writes to llm_calls.log and in-memory buffer for web UI.
    """
    from datetime import datetime, timezone

    llm_log = _get_llm_logger()
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    reason_str = (reason or "").replace("\n", " ").replace("=", "-")[:100]
    if _show_provider_in_log:
        outcome_line = f"[{ts}] LLM_OUTCOME call_id={call_id} accepted={str(accepted).lower()} reason={reason_str}"
    else:
        outcome_line = f"[{ts}] LLM_OUTCOME accepted={str(accepted).lower()} reason={reason_str}"
    llm_log.info("%s", outcome_line)
    _append_to_llm_buffer(outcome_line)
