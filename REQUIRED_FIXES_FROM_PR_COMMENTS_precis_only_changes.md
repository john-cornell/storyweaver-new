# Required Fixes From PR Comments — Précis-Only Changes

**Context:** Brutal PR review of "Expand idea to précis" (précis-only, no paragraphs) clarification.

---

## 1. Log message consistency — empty-idea path

**Comment:** When the idea is empty, the log says "Expand idea skipped — Idea empty". Everywhere else the action is named "Expand idea to précis". The skip message should use the same action name for consistency.

**Strict interpretation:** All log entries for this action use the same verb phrase.

**Required change:** In `do_expand_idea`, change the empty-idea log from `"Expand idea skipped — Idea empty"` to `"Expand idea to précis skipped — Idea empty"`.

---

## 2. Progress message grammar

**Comment:** "Précis updated only. No paragraphs added." is stilted. Prefer a single clear sentence.

**Strict interpretation:** User-facing progress text should read naturally.

**Required change:** Replace with: "Only the précis was updated; no paragraphs were added. Review/edit the précis, then press Start when ready. Undo restores the previous idea."

---

## 3. Placeholder length and special characters

**Comment:** The placeholder is long and uses « » which may not render in all fonts or may be truncated on small UIs.

**Strict interpretation:** Shorten placeholder; use ASCII or widely supported characters.

**Required change:** Shorten to something like: "Rough idea or précis. Use 'Expand idea to précis' to turn an idea into a précis only (no paragraphs)." Use straight quotes instead of « ».

---

## 4. Undo button label

**Comment:** For symmetry and clarity, the Undo button could be labeled "Undo précis" so it's explicit that we're undoing the précis expansion, not story steps.

**Strict interpretation:** Button label should make scope clear.

**Required change:** In `app.py`, change `undo_btn = gr.Button("Undo", ...)` to `undo_btn = gr.Button("Undo précis", ...)`.

---

## Summary

| # | File | Fix |
|---|------|-----|
| 1 | working/handlers.py | Empty-idea log: "Expand idea to précis skipped — Idea empty" |
| 2 | working/handlers.py | Progress message: natural grammar (only the précis was updated...) |
| 3 | app.py | Placeholder: shorter, straight quotes |
| 4 | app.py | Undo button label: "Undo précis" |

---

## Verification (Step 4 re-review)

- All 4 items implemented. Log copy consistent; progress message grammar fixed; placeholder shortened with straight quotes; Undo button labeled "Undo précis".
- **brutal-pr satisfied.** No remaining issues or nitpicks.
