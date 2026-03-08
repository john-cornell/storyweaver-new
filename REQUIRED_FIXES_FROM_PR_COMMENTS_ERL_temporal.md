# REQUIRED_FIXES_FROM_PR_COMMENTS — ERL Temporal Context Fix (Brutal Review)

## Review Scope
ERL temporal context fix: is_first_leaf_in_reading_order, precis-only ERL for first leaf, NARRATIVE POSITION prompt constraint.

---

## 1. [NITPICK] working/handlers.py — Redundant load_story when not first leaf

**Issue:** In do_expand_next we call `precis, _, _ = load_story()` on every expansion. When it's not the first leaf, we discard precis and use erl_state/load_erl(). We still pay the DB cost for load_story.

**Fix:** Only call load_story when is_first_leaf_in_reading_order is True. Refactor:
```python
if is_first_leaf_in_reading_order(steps, path):
    precis, _, _ = load_story()
    current_erl = extract_state_updates(precis or "", empty_erl())
else:
    current_erl = erl_state if _valid_erl(erl_state) else load_erl()
```

---

## 2. [NITPICK] working/tree_utils.py — Consider exporting is_first_leaf_in_reading_order

**Issue:** New function is_first_leaf_in_reading_order is not in any __all__ if tree_utils has one. Handlers imports it directly; no change needed if tree_utils has no __all__. Verify tree_utils exports.

**Fix:** If tree_utils has __all__, add is_first_leaf_in_reading_order. Otherwise no change.

---

## 3. [VERIFY] working/handlers.py — do_expand_round load_story before loop

**Issue:** We call load_story() at the start of the round. If the DB is empty or corrupted, we could get (None, [], []). precis or "" handles None. extract_state_updates("", empty_erl()) returns empty_erl() without LLM call (short-circuit). Good.

**Fix:** No change. Verified.

---

## Summary

| # | Severity | File | Action |
|---|----------|------|--------|
| 1 | NITPICK | working/handlers.py | Only call load_story when first leaf |
| 2 | NITPICK | working/tree_utils.py | Add to __all__ if exists |
| 3 | VERIFY | — | No change |
