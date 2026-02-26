# Required Fixes From PR Comments — Story Expansion Feature

**Context:** Brutal PR review of the step-by-step paragraph expansion, tree model, history tab, and vetting stubs.

---

## 1. Type/documentation consistency — `tree_utils.py`

**Comment:** Docstring says `Path = (..., indices: list[int])` but `LeafPath` is `tuple[int, str, tuple[int, ...]]`. Indices are tuple, not list.

**Strict interpretation:** Docstring must match the type alias. Either change docstring to "tuple[int, ...]" or use list in the type (tuple is preferred for immutability).

**Required change:** Update the module docstring in `working/tree_utils.py` so that the Path description uses "tuple of 0|1" (or "tuple[int, ...]") instead of "list[int]".

---

## 2. Defensive path handling — `tree_utils.py`

**Comment:** In `_set_at_path`, when `node` is a leaf (str) and `indices` is non-empty, we return `node` unchanged. That can corrupt the tree if an invalid path is ever passed. Callers currently only pass paths from `get_first_leaf_path` (always leaves), but the function is not defensive.

**Strict interpretation:** When we are at a leaf and indices is not empty, the path is invalid; do not mutate. Document that `set_leaf_at_path` expects a path to a leaf (indices must be the path to that leaf, and the node at that path must be a leaf). Add a one-line comment in `set_leaf_at_path` or `_set_at_path` stating that path must point to a leaf.

**Required change:** In `set_leaf_at_path`, add a short comment: "path must be a leaf path from get_first_leaf_path." Optionally in `_set_at_path`, when node is a leaf and indices is not empty, return node unchanged and add a comment that this is invalid-path handling.

---

## 3. Malformed tree handling — `tree_utils.py`

**Comment:** If a node is a dict but does not have both "left" and "right", `get_first_leaf_path` and `_render_tree` either skip it or render "*—*". Malformed data is silently tolerated.

**Strict interpretation:** Document that branch nodes must have exactly "left" and "right". No requirement to add runtime validation in this PR, but the type or module docstring should state the invariant.

**Required change:** In `working/tree_utils.py` module docstring, add one line: "Branch nodes must be dicts with exactly 'left' and 'right' keys."

---

## 4. Magic numbers — `steps_ui.py`

**Comment:** `build_history_markdown` uses 500 and 400 as truncation lengths with no named constant. Magic numbers reduce maintainability.

**Strict interpretation:** Define module-level constants (e.g. `HISTORY_ORIGINAL_TRUNCATE = 500`, `HISTORY_CHILD_TRUNCATE = 400`) and use them.

**Required change:** In `working/steps_ui.py`, add constants and replace literals 500 and 400.

---

## 5. Variable shadowing — `steps_ui.py`

**Comment:** In `build_history_markdown`, the variable `path_label` shadows the key `"path_label"` from the entry (conceptually the same thing but the name is overloaded with the function `path_label` in tree_utils when reading the code).

**Strict interpretation:** Use a different local variable name so that "path_label" is not both a dict key and a variable name in the same block. E.g. use `path_display` or `label` for the value from the entry.

**Required change:** Rename the variable in the loop from `path_label` to `path_display` (or `expansion_path`).

---

## 6. Dead import — `handlers.py`

**Comment:** `build_working_markdown` is imported in `working/handlers.py` but never used (all call sites use `build_current_story_markdown` and `build_history_markdown`).

**Strict interpretation:** Remove unused imports to satisfy zero-tolerance for dead code.

**Required change:** Remove `build_working_markdown` from the import list in `working/handlers.py`.

---

## 7. Nav return type — `ui/nav.py`

**Comment:** `_nav_outputs` return type is `tuple[dict, dict, dict, dict, str, str, list[str]]` (7 elements) but the function returns 8 values: 4 dicts, current_md (str), history_md (str), log_md (str), entries (list[str]).

**Strict interpretation:** The annotated return type must match the actual return arity and types.

**Required change:** Change the return type of `_nav_outputs` to `tuple[dict, dict, dict, dict, str, str, str, list[str]]`.

---

## 8. Vetting return values ignored — `handlers.py`

**Comment:** `vet_consistency(new_steps)` and `vet_similarity(new_steps)` return `list[str]` but the return values are ignored. When these are implemented, issues will need to be surfaced in the UI.

**Strict interpretation:** Document that vetting results are intentionally unused for now, or assign to a variable with a comment that UI surfacing will be added later. Avoid the appearance of a bug.

**Required change:** In `do_expand_next`, assign results to variables and add a one-line comment: e.g. `_consistency_issues = vet_consistency(new_steps)` and `_similarity_issues = vet_similarity(new_steps)` with comment "# TODO: surface in UI when implemented".

---

## 9. Working status not cleared on Start — `app.py` + `handlers.py`

**Comment:** When the user clicks Start, the Working panel is shown with new story and empty history, but `working_status_md` still shows the previous "Expanded …" message if one was set. Status line should be cleared or set to a neutral message when starting a new story.

**Strict interpretation:** Start must update the Working status line so it does not show stale expansion status. Either clear it (empty string) or set to a single message like "Story started."

**Required change:** Add `working_status_md` to the outputs of `start_btn.click` in `app.py`. Extend `do_start_write` to return one more value: the status string for the Working panel (e.g. "" or "Story started."). Use that to update `working_status_md` when Start is clicked.

---

## 10. Tree type strictness — `types.py`

**Comment:** `Tree = str | dict[str, Any]` allows any dict. The tree_utils assume branch dicts have "left" and "right". No runtime enforcement.

**Strict interpretation:** Document the invariant in types.py so that future code and reviewers know the contract. Optionally use a TypedDict for the branch (would require tree_utils to accept that type).

**Required change:** In `working/types.py`, add a one-line comment above Tree: "Branch dicts must contain exactly 'left' and 'right' keys (see tree_utils)."

---

## Summary

| # | File | Fix |
|---|------|-----|
| 1 | working/tree_utils.py | Docstring: indices as tuple, not list |
| 2 | working/tree_utils.py | Comment: path must be leaf path |
| 3 | working/tree_utils.py | Docstring: branch = left+right only |
| 4 | working/steps_ui.py | Constants for 500/400; use them |
| 5 | working/steps_ui.py | Rename path_label → path_display in loop |
| 6 | working/handlers.py | Remove build_working_markdown import |
| 7 | ui/nav.py | Fix _nav_outputs return type to 8 elements |
| 8 | working/handlers.py | Assign vet results + TODO comment |
| 9 | app.py, working/handlers.py | working_status_md cleared/set on Start |
| 10 | working/types.py | Comment on Tree branch invariant |

---

## Verification (brutal-pr second pass)

- All 10 items implemented.
- Vetting: return values assigned to `_consistency_issues` and `_similarity_issues` with TODO comment (no assert, so future non-empty results remain valid).
- Lint: no errors.
- **brutal-pr satisfied.** No further issues.
