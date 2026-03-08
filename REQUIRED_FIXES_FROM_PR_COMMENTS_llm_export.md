# REQUIRED_FIXES_FROM_PR_COMMENTS — LLM Export Fix

## Brutal PR Review Findings

### 1. [BLOCKER] llm/__init__.py — set_show_provider_in_log not exported

**Issue:** app.py imports `set_show_provider_in_log` from llm, but llm/__init__.py did not export it. ImportError at runtime.

**Fix:** Add `set_show_provider_in_log` to llm/__init__.py imports and __all__.

---

### 2. [NITPICK] version.py — Bump for export fix

**Issue:** User rule: update version on every change.

**Fix:** Bump version (1.1.13 → 1.1.14).
