# REQUIRED FIXES — Plan vs Write LLM (brutal-pr self-review)

## 1. Dead code: _get_model_for_provider in llm/client.py

**Location:** `llm/client.py` line 235

**Comment:** `_get_model_for_provider` is defined but never called. `complete()` obtains `model` from `get_provider_for_task()`. This is dead code.

**Required change:** Remove `_get_model_for_provider` from llm/client.py.

---

## 2. Redundant config loading in get_provider_for_task

**Location:** `llm/client.py` — `get_provider_for_task`, `_default()` calls `get_first_provider()`

**Comment:** `get_first_provider()` internally calls `LLMConfig.load()`. We already have `cfg` passed into `get_provider_for_task`. Loading config again is redundant and could cause inconsistency if env changes between calls.

**Required change:** Add `_first_provider_from_cfg(cfg: LLMConfig) -> LLMProvider | None` that iterates over providers using the passed cfg. Use it in `_default()` instead of `get_first_provider()`.

---

## 3. Unused import in tests

**Location:** `tests/test_llm_provider_resolution.py` line 8

**Comment:** `import pytest` is unused.

**Required change:** Remove `import pytest`.
