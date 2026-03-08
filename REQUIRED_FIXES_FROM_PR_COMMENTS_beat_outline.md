# Required Fixes from PR Review — Beat Outline Step

## 1. do_undo_precis docstring (handlers.py)

**Issue:** Docstring said "before the last Expand idea to précis" but Undo also restores after Generate beat outline.

**Fix:** Updated to "before the last Expand idea to précis or Generate beat outline."

**Status:** Applied.

## 2. BEAT_OUTLINE_SYSTEM missing ENGLISH_ONLY_INSTRUCTION (prompts.py)

**Issue:** Cross-file consistency — PRECIS_SYSTEM and TITLE_FROM_PRECIS_SYSTEM use ENGLISH_ONLY_INSTRUCTION to avoid non-English output. BEAT_OUTLINE_SYSTEM did not.

**Fix:** Added ENGLISH_ONLY_INSTRUCTION to BEAT_OUTLINE_SYSTEM.

**Status:** Applied.
