# REQUIRED FIXES — Stop LLM on Story Error (brutal-pr review)

**Status: All items addressed (v1.0.94)**

## 1. [BLOCKER] Infinite loop on recoverable error

**Location:** `working/handlers.py` — `_auto_expand_worker`, recoverable-error path.

**Comment:** When a path fails with a recoverable error, we `break` out of the path loop. `current_steps` is unchanged (no path succeeded). Next round: same leaves, same first path. We call `do_expand_round` again → same failure → same recoverable result → we continue the loop. **Infinite loop.** The worker will hammer the LLM forever on the same failing path.

**Required change:** Add a consecutive-recoverable-failure counter. When we get a recoverable error, increment it. If it exceeds a threshold (e.g. 3), treat as fatal and stop. When we get a successful round (no error) or a fatal error, reset the counter to 0. This prevents infinite retry on a persistently failing path.

---

## 2. [MAJOR] _is_fatal_error: missing google.genai module

**Location:** `working/handlers.py` — `_is_fatal_error`, line ~109.

**Comment:** The plan lists `google.api_core.exceptions.*`. The newer `google.genai` SDK may raise from `google.genai` or `google.genai.types` modules. We only check `"google.api_core" in mod`. If Gemini uses `google.genai` exceptions, those would be misclassified as recoverable.

**Required change:** Add `"google.genai" in mod` to the fatal-error check so Gemini client errors are treated as fatal.

---

## 3. [MAJOR] _is_fatal_error: DB module not covered

**Location:** `working/handlers.py` — `_is_fatal_error`.

**Comment:** The plan explicitly says "DB unavailable" is fatal. Exceptions from `db` (e.g. `save_story`, `load_story`) could be `OSError`, custom DB errors, or SQLite/DB driver exceptions. We do not check for the project's `db` module.

**Required change:** Add a check for `"db" in mod` or `mod.startswith("db.")` so that exceptions originating from the db package are treated as fatal. Use the actual db module path (e.g. `type(e).__module__.startswith("db")` or similar) to avoid false positives on unrelated modules containing "db".

---

## 4. [MINOR] Magic string for recoverable status

**Location:** `working/handlers.py` — `_auto_expand_worker`, line ~1370.

**Comment:** We check `if "recoverable error" in (result[11] or "")`. This is a magic string. If the status message in `do_expand_round` changes, the worker logic breaks silently.

**Required change:** Define a module-level constant, e.g. `_RECOVERABLE_ERROR_MARKER = "recoverable error"`, and use it in both `do_expand_round` (when building the status) and `_auto_expand_worker` (when checking). Ensures consistency and single source of truth.

---

## 5. [NITPICK] Worker docstring: "17-tuples" is outdated

**Location:** `working/handlers.py` — `_auto_expand_worker` docstring, line ~1191.

**Comment:** Docstring says "Puts 17-tuples". The actual tuple has 20 elements (15 from result + run_btn + 3 write_btns + erl_state). Misleading.

**Required change:** Update docstring to "Puts 20-tuples" or "Puts tuples of 20 elements" and briefly list the structure (steps, history, UI strings, status, log, entries, expand_btn, run_btn, write_btns, erl_state).

---

## 6. [NITPICK] Exception handler: redundant save_erl(load_erl())

**Location:** `working/handlers.py` — `_auto_expand_worker` exception handler, lines ~1314–1315.

**Comment:** `save_erl(load_erl())` reads ERL from DB and writes it back. When `do_expand_round` raises, we never persisted any new ERL from that round. The DB already has the last good ERL. This is a no-op. Not wrong, but redundant.

**Required change:** Either remove `save_erl(load_erl())` (since we're not adding new ERL data) or add a one-line comment: `# Persist last known ERL (no new data from failed round).` to clarify intent. Prefer the comment for defensive clarity.
