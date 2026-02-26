# REQUIRED FIXES FROM PR COMMENTS — Expansion 2→4→8 + SQLite

Brutal, nitpicky interpretation of PR review. Every item must be addressed.

---

## 1. Stale module docstring (handlers.py)

**Location:** `working/handlers.py` lines 1–8.

**Comment:** Module docstring says "do_auto_expand_next — generator: run **expand_next** in a loop" but implementation runs **expand_round** in a loop. Misleading and wrong.

**Required change:** Update docstring to say "run **expand_round** in a loop (2→4→8→…) until limit/pause/no leaf." Keep other lines accurate.

---

## 2. Stale do_auto_expand_next docstring (handlers.py)

**Location:** `working/handlers.py` lines 416–418.

**Comment:** Docstring says "run **expand_next** in a background thread". Implementation runs **expand_round**. Zero tolerance for wrong docs.

**Required change:** Replace with: "Generator: run **expand_round** in a background thread until word limit, no leaf, or Pause. Each iteration doubles paragraph count (2→4→8→…)."

---

## 3. DB connection pattern (db/story_db.py)

**Comment:** Every `save_story` calls `_init()` which opens a connection, then `_get_conn()` opens again. So two connections per save. Wasteful; under concurrency could contribute to "database is locked". `load_story` also calls `_init()` then `_get_conn()`.

**Required change:** Call `_init()` only once per process (e.g. at first use). Use a single `_get_conn()` per operation; ensure `_init()` runs before first read/write without opening redundant connections. Option: have `_init()` create table using the same connection that will be used for the following operation (e.g. `_init(conn)` or init-on-first-connect).

---

## 4. JSON and DB error handling (db/story_db.py)

**Comment:** No handling of `json.dumps` or `json.loads` failures. Corrupted DB or non-serializable data will raise and crash the handler. Same for SQLite errors (disk full, permission).

**Required change:**  
- In `save_story`: wrap `json.dumps` and the write in try/except; on failure log (or re-raise with context) so callers can decide. Prefer not swallowing silently.  
- In `load_story`: wrap `json.loads` in try/except; on failure return `(None, [], [])` or re-raise with clear message. Document behavior.  
- Document that callers may see exceptions from `save_story` on I/O or serialization errors.

---

## 5. save_story exception handling in handlers (handlers.py)

**Comment:** If `save_story` or `load_story` raises (e.g. disk full, JSON error), the exception propagates and can break the Gradio event. UI state may already be updated in memory; DB and UI diverge.

**Required change:** In every place we call `save_story` or `load_story` (do_start_write, do_expand_next, do_expand_round), wrap in try/except. On failure: log to entries (add_entry with level="error"), do not re-raise so the UI still updates. Optionally set a status message like "Story saved to DB." / "Warning: could not save to DB."

---

## 6. do_expand_round status message when partial failure (handlers.py)

**Location:** `working/handlers.py` around line 419.

**Comment:** When we break mid-round (error or word limit), we still show "Round: 2 → 4 paragraphs" if `status_parts` is non-empty. That implies we doubled all; in reality we may have expanded only 1 of 2 and then stopped. Misleading.

**Required change:** Compute actual new leaf count after the loop (e.g. `get_all_leaf_paths(current_steps)` or track `len(all_leaves) - len(status_parts) + 2*len(status_parts)`). Message: if all expanded: "Round: N → 2N paragraphs." If partial: "Round: N → M paragraphs (stopped: limit or error)." with M = actual leaf count.

---

## 7. save_story API when precis is None (db/story_db.py)

**Comment:** Docstring says "If precis is None, keep existing precis". The implementation does that for UPDATE. For INSERT we pass `precis or ""`. So first save with precis=None and no row yields precis "". Then load_story returns None for "" (strip). OK. But the signature allows None and the comment says "keep existing" — there is no "existing" on first insert. Minor ambiguity.

**Required change:** Document explicitly: "On first insert, if precis is None use empty string (load_story will return None for empty precis). On update, if precis is None keep existing value."

---

## 8. Load from DB on startup (product/architecture)

**Comment:** We persist to DB on Start and on each expand, but we never load from DB when the app starts. So after restart, UI state is empty even if DB has a story. Persistence is "write-only" from the UI's perspective.

**Required change:** Either (a) add load-on-start: when app loads or when user opens Write/Working, if DB has a story, prefill steps_state and history_state (and idea_tb if precis present), or (b) document in code/README that DB is for audit/recovery only and UI does not auto-load. For "keep track" the minimum is (b); for better UX do (a). Reviewer requires at least (b) documented; (a) preferred.

---

## 9. Type / validation of loaded data (db/story_db.py)

**Comment:** `load_story` returns `list[Any]` from JSON. No validation that structure matches `list[Step]` or `list[HistoryEntry]`. Corrupted or legacy data could cause runtime errors in tree_utils or handlers.

**Required change:** Document that load_story returns raw JSON structure; callers assume valid shape. Optional: add a one-line comment in load_story: "No schema validation; callers must handle malformed data." No mandatory validation code for this PR unless we add load-on-start (then validate or tolerate gracefully).

---

## 10. Version bump (version.py)

**Comment:** User rule: version on every change. We are making fixes after the PR; this is a new change.

**Required change:** Bump version (e.g. to 1.0.24) when applying these fixes.
