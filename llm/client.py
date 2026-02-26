"""
Thin LLM client using configured provider (Anthropic, Gemini, OpenAI, Ollama).
Uses first available provider from config.
"""

from __future__ import annotations

from config import LLMConfig, LLMProvider


def _complete_anthropic(cfg: LLMConfig, prompt: str, system: str | None) -> str:
    assert cfg.anthropic is not None
    import anthropic
    c = anthropic.Anthropic(api_key=cfg.anthropic.api_key)
    kwargs: dict = {"model": cfg.anthropic.model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    r = c.messages.create(**kwargs)
    return (r.content[0].text if r.content else "").strip()


def _complete_gemini(cfg: LLMConfig, prompt: str, system: str | None) -> str:
    assert cfg.gemini is not None
    import google.generativeai as genai
    genai.configure(api_key=cfg.gemini.api_key)
    full = f"{system}\n\n{prompt}" if system else prompt
    model = genai.GenerativeModel(cfg.gemini.model)
    r = model.generate_content(full)
    return (r.text or "").strip()


def _complete_openai(cfg: LLMConfig, prompt: str, system: str | None) -> str:
    assert cfg.openai is not None
    from openai import OpenAI
    c = OpenAI(api_key=cfg.openai.api_key)
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})
    r = c.chat.completions.create(model=cfg.openai.model, messages=messages, max_tokens=4096)
    return (r.choices[0].message.content or "").strip()


def _complete_ollama(cfg: LLMConfig, prompt: str, system: str | None) -> str:
    assert cfg.ollama is not None
    from openai import OpenAI
    c = OpenAI(base_url=cfg.ollama.base_url.rstrip("/") + "/v1", api_key="ollama")
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages.insert(0, {"role": "system", "content": system})
    r = c.chat.completions.create(model=cfg.ollama.model, messages=messages, max_tokens=4096)
    return (r.choices[0].message.content or "").strip()


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


def complete(prompt: str, system: str | None = None) -> str:
    """
    Run one completion using the first configured LLM.
    Raises RuntimeError if no provider is configured or on API errors.
    """
    cfg = LLMConfig.load()
    provider = get_first_provider()
    if provider is None:
        raise RuntimeError(
            "No LLM provider configured. Set one of ANTHROPIC_API_KEY, GEMINI_API_KEY, "
            "OPENAI_API_KEY, or Ollama (OLLAMA_BASE_URL)."
        )
    if provider == LLMProvider.ANTHROPIC and cfg.anthropic:
        return _complete_anthropic(cfg, prompt, system)
    if provider == LLMProvider.GEMINI and cfg.gemini:
        return _complete_gemini(cfg, prompt, system)
    if provider == LLMProvider.OPENAI and cfg.openai:
        return _complete_openai(cfg, prompt, system)
    if provider == LLMProvider.OLLAMA and cfg.ollama:
        return _complete_ollama(cfg, prompt, system)
    raise RuntimeError("No LLM provider available.")
