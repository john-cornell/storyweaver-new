# REQUIRED_FIXES: Full History Shows Only Step 5 (Missing Steps 1–4)

## Brutal PR Review Findings

### BLOCKER: Full History omits Steps 1–4 in fully expanded tree

**Root cause:** `get_leaves_with_lineage` returns only **leaves**. In a fully expanded tree, all leaves are at the deepest depth (round 5). Nodes at rounds 1–4 are **branches** (internal nodes), so they are never appended to the output. Result: user sees only "Step 5: Paragraph N" and never "Step 1", "Step 2", "Step 3", "Step 4".

**Location:** `working/tree_utils.py` (`get_leaves_with_lineage`), `working/steps_ui.py` (`build_full_history_text`)

**Required change:**
1. Add `get_all_nodes_with_lineage(steps, path_to_original)` in tree_utils that traverses the tree and outputs **every node** (branch and leaf) with (round, para_num, parent_round, parent_para, text).
2. For **leaves**: text = node content.
3. For **branches**: text = `path_to_original.get(path, "—")` (original from history before expansion).
4. Build `path_to_original` in `build_full_history_text` from history (all entries, not just roots).
5. Replace `get_leaves_with_lineage(steps)` with `get_all_nodes_with_lineage(steps, path_to_original)` in `build_full_history_text`.

### MINOR: Docstring clarity

**Location:** `get_leaves_with_lineage` docstring

**Required change:** Add note: "Returns only leaves; in a fully expanded tree all leaves are at the deepest round. Use get_all_nodes_with_lineage for full-history trace including intermediate rounds."

---

## Implementation Notes

- `path_to_original` key: `(step_index, paragraph_key, tuple(indices))` from history entries.
- Preserve existing `get_leaves_with_lineage` for any other callers (grep shows it's only used by build_full_history_text).
- Version bump required.
