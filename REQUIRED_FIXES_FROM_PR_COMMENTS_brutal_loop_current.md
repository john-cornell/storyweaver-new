# Required Fixes From PR Comments — Brutal PR Review Loop (Current Codebase)

**Context:** Full brutal-pr review of current StoryWeaver app, working, ui.

---

## 1. Undo précis log consistency — `working/handlers.py`

**Comment:** Log messages for the Undo action should use the same action name "Undo précis". Currently: "Undo skipped — nothing to restore" and "Undo: restored previous idea".

**Strict interpretation:** All log entries for this flow use "Undo précis" in the message.

**Required change:**
- In `do_undo_precis`, when nothing to restore: change log to `"Undo précis skipped — nothing to restore"`.
- When restoring: change log to `"Undo précis: restored previous idea"`.

---

## 2. do_undo_precis docstring — `working/handlers.py`

**Comment:** Docstring says "Restore Idea text to what it was before the last Expand." The action is "Expand idea to précis"; docstring should be explicit.

**Strict interpretation:** Docstring matches the named action.

**Required change:** In `do_undo_precis`, change docstring to: "Restore Idea text to what it was before the last Expand idea to précis."

---

## 3. Start completed log — `working/handlers.py`

**Comment:** Log says "Start completed — step {n} added". User-facing message says "two paragraphs added"; log should state the same for consistency.

**Strict interpretation:** Log entry reflects that the step contains two paragraphs.

**Required change:** In `do_start_write`, change the success log from `f"Start completed — step {len(new_steps)} added"` to `f"Start completed — step {len(new_steps)} (two paragraphs) added"`.

---

## 4. History tab empty state — `working/steps_ui.py`

**Comment:** Empty history message says "Use **Expand next** to expand a paragraph into two." Run is the automated option; message should mention both.

**Strict interpretation:** Copy matches available actions (Expand next and Run).

**Required change:** Change to: "Use **Expand next** or **Run** to expand paragraphs."

---

## Summary

| # | File | Fix |
|---|------|-----|
| 1 | working/handlers.py | Undo log: "Undo précis skipped…" and "Undo précis: restored…" |
| 2 | working/handlers.py | do_undo_precis docstring: "before the last Expand idea to précis" |
| 3 | working/handlers.py | Start log: "step {n} (two paragraphs) added" |
| 4 | working/steps_ui.py | History empty: mention Expand next and Run |

---

## Verification (Step 4 re-review)

- All 4 items implemented. Undo précis log and docstring consistent; Start log states two paragraphs; History empty state mentions both Expand next and Run.
- **brutal-pr satisfied.** No remaining issues or nitpicks.
