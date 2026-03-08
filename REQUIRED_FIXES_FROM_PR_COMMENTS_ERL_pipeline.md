# REQUIRED_FIXES_FROM_PR_COMMENTS — ERL Pipeline Brutal Review

## Review Scope
Full ERL pipeline implementation: classifier, prompts, extractor, init, handlers, vetting, db, app.

---

## 1. [BLOCKER] working/handlers.py — vet_consistency results never surfaced

**Issue:** `_consistency_issues = vet_consistency(new_steps, updated_erl)` is assigned but never used. The plan says "Wire Up Vetting" — we run the check but the results go nowhere. Users have no visibility into consistency problems.

**Fix:** Log consistency issues to entries when non-empty. In do_expand_next and do_expand_round, after `vet_consistency(...)`, add:
```python
if _consistency_issues:
    for issue in _consistency_issues:
        entries = add_entry(entries, f"Consistency: {issue}", level="error")
```

---

## 2. [MINOR] working/handlers.py — Dead import EXPAND_PARAGRAPH_SYSTEM

**Issue:** `EXPAND_PARAGRAPH_SYSTEM` is imported but never used. The routed prompts (transition/scene) replaced it entirely. The plan said "remain as fallback" but we never fall back — we default to SCENE prompt on classification failure.

**Fix:** Remove `EXPAND_PARAGRAPH_SYSTEM` from the imports in handlers.py. If fallback is desired later, add it back with explicit fallback logic.

---

## 3. [NITPICK] db/story_db.py — Lazy import inside load_erl

**Issue:** `from working.erl import empty_erl` is done inside `load_erl()` to avoid circular import. This is a code smell — lazy imports hide dependencies and make static analysis harder.

**Fix:** Move the import to module top with a TYPE_CHECKING guard, or accept the pattern with a brief comment: `# Lazy import to avoid circular dependency (db may be imported before working.erl in some paths).`

---

## 4. [NITPICK] working/erl_extractor.py — Redundant except json.JSONDecodeError

**Issue:** The `except json.JSONDecodeError` block is likely unreachable because `json_to_erl()` catches JSONDecodeError internally and returns fallback. The exception would never propagate.

**Fix:** Remove the redundant `except json.JSONDecodeError` branch; the generic `except Exception` suffices. Or keep both for defensive clarity — document that json_to_erl may raise if it changes.

---

## 5. [NITPICK] working/classifier.py — Silent exception swallowing

**Issue:** `except Exception: return "SCENE"` swallows all errors (network, API key, timeout) with no logging. Debugging failures is harder.

**Fix:** Add `logger.warning("Classifier failed: %s; defaulting to SCENE", e)` before returning. Requires `import logging` and `logger = logging.getLogger(__name__)`.

---

## 6. [NITPICK] working/erl_init.py — Silent exception swallowing

**Issue:** `except Exception: return empty_erl()` — same pattern. No visibility when ERL init fails.

**Fix:** Add logging: `logger.warning("ERL init failed: %s; using empty ERL", e)`.

---

## 7. [VERIFY] .gitignore — storyweaver.db

**Issue:** Database file should not be committed. Check .gitignore includes storyweaver.db.

**Fix:** Ensure `storyweaver.db` is in .gitignore. Unstage if already staged.

---

## 8. [NITPICK] version.py — Version bump

**Issue:** User rule: update version on every change. If applying fixes, bump version.

**Fix:** Bump version (e.g. 1.0.74 → 1.0.75).

---

## Summary

| # | Severity | File | Action |
|---|----------|------|--------|
| 1 | BLOCKER | working/handlers.py | Log vet_consistency issues to entries |
| 2 | MINOR | working/handlers.py | Remove dead EXPAND_PARAGRAPH_SYSTEM import |
| 3 | NITPICK | db/story_db.py | Add comment for lazy import |
| 4 | NITPICK | working/erl_extractor.py | Remove redundant JSONDecodeError branch or document |
| 5 | NITPICK | working/classifier.py | Add logging on exception |
| 6 | NITPICK | working/erl_init.py | Add logging on exception |
| 7 | VERIFY | .gitignore | Confirm storyweaver.db excluded |
| 8 | NITPICK | version.py | Bump version |
