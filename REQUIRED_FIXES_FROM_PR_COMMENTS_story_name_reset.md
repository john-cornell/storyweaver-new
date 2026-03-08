# Required Fixes from PR Review — Story Name and Write Reset

## 1. _generate_story_name unused parameter (handlers.py)

**Issue:** `entries: list[str]` parameter was unused; dead code.

**Fix:** Remove parameter. Caller updated to `_generate_story_name(idea.strip())`.

**Status:** Applied.
