# REQUIRED_FIXES_FROM_PR_COMMENTS — Full History Feature

## 1. steps_ui.py: Redundant condition in _get_expanded_text

**Location:** `_get_expanded_text`, line ~136

**Issue:** `if not steps or len(steps) == 0` — when `not steps` is True (empty list), we short-circuit. `len(steps) == 0` is redundant.

**Required change:** Simplify to `if not steps:`.

---

## 2. steps_ui.py: Docstring inaccuracy in build_full_history_text

**Location:** `build_full_history_text` docstring

**Issue:** Docstring says "Includes copy-to-clipboard" but the copy button is built by a separate function `build_full_history_copy_button_html`. The docstring describes the wrong function.

**Required change:** Change docstring to: "Render full history trace for debugging: Precis, Expanded, then Step N paragraphs with lineage (From Step X Paragraph Y)."

---

## 3. steps_ui.py: Silent exception swallowing in build_full_history_text

**Location:** `build_full_history_text`, `try/except Exception: pass`

**Issue:** Catching all exceptions and silently passing hides DB/load failures. Debugging becomes harder when precis fails to load.

**Required change:** Log the exception (e.g. via `logging` or add to a debug path). Minimum: use `except Exception as e:` and at least `logging.warning("load_story failed for full history precis: %s", e)` or equivalent. If the project has no logging, document in a comment that failure is intentional (precis optional for display).

---

## 4. steps_ui.py: steps_ui → db coupling

**Location:** `from db import load_story` in steps_ui

**Issue:** steps_ui now directly depends on db. This increases coupling and makes unit testing harder (need to mock DB). Alternative: pass precis as a parameter from callers who already have it (handlers load from DB).

**Required change:** Consider passing `precis: str | None` as an optional third parameter to `build_full_history_text` and `build_full_history_copy_button_html`. If None, call load_story() internally (preserve current behavior). Callers that have precis (e.g. from load_story in handlers) can pass it to avoid double load. This is a design improvement; if too invasive, add a code comment explaining the coupling and that it's acceptable for this debug view.

---

## 5. tree_utils.py: get_leaves_with_lineage — no handling for malformed tree

**Location:** `get_leaves_with_lineage`, `visit` function

**Issue:** If a node is neither a leaf (str) nor a dict with left/right, we fall through without appending to `out` and without recursing. The function would silently skip such nodes. Edge case for malformed data.

**Required change:** Add an `else` branch: if not leaf and not valid branch, either (a) treat as leaf with empty text, or (b) log and skip. Prefer (a) for robustness: `else: out.append((round_num, para_num, parent_round, parent_para, ""))`.

---

## 6. tree_utils.py: get_leaves_with_lineage — step_idx unused in visit signature

**Location:** `visit(node, step_idx, key, indices)` — step_idx and key are passed but the function only uses indices for depth. For multi-step support, step_idx would matter. Currently the model has one step.

**Required change:** NITPICK. Add a brief comment that the function assumes single-step (step_idx 0) trees, or that step_idx is reserved for future multi-step expansion. No code change required if the model is intentionally single-step; document it.

---

## 7. steps_ui.py: _get_expanded_text — IndexError risk

**Location:** `get_root_text(step_idx, key)` accesses `steps[step_idx]`

**Issue:** We only call with step_idx=0. If steps is non-empty but we ever call with step_idx >= len(steps), we get IndexError. Defensive: add bounds check.

**Required change:** In `get_root_text`, add `if step_idx >= len(steps): return ""` before accessing `steps[step_idx]`.

---

## 8. version.py: Version bump

**Location:** version.py

**Issue:** User rule: update version on every change. If we're applying fixes, version should bump.

**Required change:** Bump version (e.g. 1.0.67 → 1.0.68) when applying these fixes.
