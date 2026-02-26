# REQUIRED FIXES FROM PR COMMENTS — Reject-and-retry (no sanitize)

Brutal, nitpicky interpretation of PR review. Every item must be addressed.

---

## 1. Unreachable code in _complete_english_only (handlers.py)

**Location:** `working/handlers.py` — after the for loop in _complete_english_only, line ~75.

**Comment:** The loop either returns (when is_english_only(raw)) or raises (when attempt + 1 >= max_retries). The final `raise ValueError("LLM did not return English-only text within retry limit.")` is therefore unreachable. Dead code is a maintenance hazard and suggests incomplete reasoning.

**Required change:** Remove the unreachable raise or document it as defensive. (Addressed: kept raise for type satisfaction and added comment that it is unreachable when max_retries > 0.)

---

## 2. Document mutation of entries in _complete_english_only (handlers.py)

**Location:** `working/handlers.py` — docstring of _complete_english_only.

**Comment:** The function mutates the caller's `entries` list (entries[:] = add_entry(...)) when a response is rejected. Callers need to know that the log list they pass will be modified. The docstring does not mention this.

**Required change:** Add to the docstring: "On reject, appends a log entry to entries (mutates the list) before retrying."

---

## 3. Version bump (version.py)

**Comment:** Version was bumped to 1.0.29 for the reject-and-retry change. After addressing review fixes, bump again (e.g. 1.0.30).
