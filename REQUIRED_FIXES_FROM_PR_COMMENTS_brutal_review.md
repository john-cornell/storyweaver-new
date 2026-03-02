# REQUIRED_FIXES_FROM_PR_COMMENTS — Brutal PR Review

## Review Scope
Full change set: Gemini migration, output prose-only, retry/validation, copy button, HTML tree.

---

## 1. [MINOR] working/handlers.py — Redundant variable assignment in do_expand_round

**Issue:** Inside the expansion loop, after `current_steps = set_leaf_at_path(...)`, the line `step_idx, key, indices = path` is redundant. These variables are already unpacked at the start of the loop (`for path, text in all_leaves:` followed by `step_idx, key, indices = path`).

**Fix:** Remove the redundant `step_idx, key, indices = path` inside the try block (the one immediately before building the `entry` dict). Use the existing `step_idx`, `key`, `indices` from the loop scope.

---

## 2. [NITPICK] storyweaver.db in diff

**Issue:** Binary database file `storyweaver.db` appears in the diff. User data or runtime state in version control can cause merge conflicts and bloat.

**Fix:** Add `storyweaver.db` to `.gitignore` if not already present. Do not commit the database file. (If the project intentionally tracks it, document that in a comment; otherwise exclude it.)

---

## 3. [NITPICK] llm/client.py — Client creation per call

**Issue:** A new `genai.Client` is created on every Gemini completion. The new SDK may support connection reuse for better performance under load.

**Fix:** Consider caching the client per process (e.g. module-level `_gemini_client: genai.Client | None = None` with lazy init). For a typical low-frequency story-writing app, this is optional. **Strict interpretation:** Add a brief comment that client-per-call is intentional for simplicity unless profiling shows benefit from reuse. (Low effort; prefer adding comment over full refactor for this review.)

---

## 4. [NITPICK] working/handlers.py — MAX_EXPANSION_RETRIES as magic number

**Issue:** `MAX_EXPANSION_RETRIES = 10` is a module-level constant but could be documented.

**Fix:** Add a one-line comment explaining the retry policy: e.g. "Total attempts = 1 initial + MAX_EXPANSION_RETRIES retries before giving up."

---

## 5. [VERIFY] ui/nav.py — Return tuple length and unpacking

**Issue:** `_nav_outputs` return type changed from 10 to 11 elements. All call sites must unpack correctly.

**Fix:** Audit all callers of `_nav_outputs` (nav_to_write, nav_to_working, nav_to_config, nav_to_log) to ensure the returned tuple is unpacked into the correct variables and that `output_copy_html` is passed to the correct output component. (From diff review this appears correct; no code change if verified.)

---

## 6. [NITPICK] requirements.txt — Pin google-genai for reproducibility

**Issue:** `google-genai>=1.0.0` allows any future 1.x release. Breaking changes in patch/minor could cause surprises.

**Fix:** Consider pinning to a specific version after verifying compatibility, e.g. `google-genai>=1.0.0,<2.0.0` or document the minimum tested version. For now, `>=1.0.0` is acceptable; add a comment in requirements or README: "google-genai: migrated from deprecated google-generativeai; requires 1.0+."

---

## Summary

| # | Severity | File | Action |
|---|----------|------|--------|
| 1 | MINOR | working/handlers.py | Remove redundant `step_idx, key, indices = path` in do_expand_round |
| 2 | NITPICK | .gitignore | Add storyweaver.db if not present |
| 3 | NITPICK | llm/client.py | Add comment on client-per-call |
| 4 | NITPICK | working/handlers.py | Add comment for MAX_EXPANSION_RETRIES |
| 5 | VERIFY | ui/nav.py | Confirm unpacking (no change if correct) |
| 6 | NITPICK | requirements.txt | Optional: add migration note comment |
