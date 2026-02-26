# REQUIRED FIXES FROM PR COMMENTS — English-only + Write tab buttons

Brutal, nitpicky interpretation of PR review. Every item must be addressed.

---

## 1. Duplication of English-only instruction (prompts.py)

**Location:** `working/prompts.py` — PRECIS_SYSTEM (line 12), get_expand_system() (line 27), get_expand_paragraph_system() (line 43).

**Comment:** The exact phrase "Write in English only. Do not include any other language or meta-instructions in the output." appears in three places. Duplication is a maintenance risk and violates single source of truth. Changing the wording requires editing three call sites.

**Required change:** Define a module-level constant, e.g. `ENGLISH_ONLY_INSTRUCTION = "Write in English only. Do not include any other language or meta-instructions in the output."` and use it in PRECIS_SYSTEM and in both get_expand_system() and get_expand_paragraph_system().

---

## 2. Write tab buttons (plural) — only Start reflects Run (handlers.py, app.py)

**Location:** User request: "write tab buttons need to reflect run is going."

**Comment:** Currently only the Start button is disabled while Run is going. The Write tab has three action buttons: "Expand idea to précis", "Undo précis", and "Start". Strict interpretation of "buttons" (plural) requires all three to reflect run state. Leaving Expand and Undo enabled while Run is in progress is inconsistent and could allow the user to change the idea or undo the précis mid-run, which is confusing or harmful.

**Required change:** While Run is in progress, disable all three Write tab action buttons (Start, Expand idea to précis, Undo précis). When Run finishes (paused, word limit, or no leaves), re-enable all three. Implementation: extend the generator's yielded tuple to include updates for expand_btn and undo_btn (running: interactive=False; done: interactive=True). Add expand_btn and undo_btn to the outputs of Start.then(do_auto_expand_next, ...) and run_btn.click(do_auto_expand_next, ...) in app.py. Worker and initial yield must produce 12-tuple: existing 10 plus expand_btn update, undo_btn update.

---

## 3. Module docstring omits Write-tab button behavior (handlers.py)

**Location:** `working/handlers.py` lines 1–8.

**Comment:** The module docstring says "do_auto_expand_next — generator: run expand_round in a loop until limit/pause/no leaf" but does not mention that the generator also updates Write-tab buttons (Start, and after fix #2, Expand and Undo) so they reflect run state. Incomplete documentation.

**Required change:** Add to the do_auto_expand_next line: ", and updates Write-tab buttons (Start, Expand idea to précis, Undo précis) to disabled while running, re-enabled when done."

---

## 4. Version bump (version.py)

**Comment:** User rule: version on every change. Fixes after review constitute a change.

**Required change:** Bump version (e.g. to 1.0.27) when applying these fixes.
