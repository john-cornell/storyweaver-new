# Beat State Instead of Format Detection — Implementation Plan

## Overview

Replace fragile format detection (`_is_beat_outline()` checking for `## Beginning`, `## Middle`, `## End`) with an explicit state flag. When the user runs "Generate beat outline" or "Regenerate," we set `content_is_beats_state = True`. When Start runs with that flag True, we always run `_rewrite_precis_from_beats()` before expansion, regardless of LLM output format.

---

WHEN IMPLEMENTING USE brutal-coder skill

AFTER IMPLEMENTATION use brutal-pr skill to review work and brutal-address-pr skill to address issues and loop until ALL issues, no matter how trivial are addressed

---

## Problem

`_is_beat_outline()` in [`working/handlers.py`](working/handlers.py) (lines 156–159) only matches `## Beginning`, `## Middle`, `## End`. If the LLM outputs `Beginning`, `Middle`, `End` without `##`, the précis rewrite is skipped and expansion starts from the wrong place.

## Solution

Track state explicitly. A `content_is_beats_state` (Gradio `gr.State`) is True when the Idea textbox content was produced by Generate beat outline or Regenerate. Start checks this flag; if True, it runs `_rewrite_precis_from_beats()` before expansion.

## Architecture

| Action | Sets `content_is_beats_state` to |
|--------|----------------------------------|
| Generate beat outline (success) | `True` |
| Regenerate (success) | `True` |
| Expand idea to précis (success) | `False` |
| Undo précis | `False` |
| Reset | `False` |
| Start (after rewrite) | `False` (beats consumed) |

## Implementation Steps

### 1. Add state in `app.py`

- Add `content_is_beats_state = gr.State(False)` near other Write-page state (e.g. after `precis_undo_state`).
- No nav wiring needed: Write-page state (idea_tb, precis_undo_state) persists across panel switches; `content_is_beats_state` behaves the same.

### 2. Wire `content_is_beats_state` to handlers

**Generate beat outline** (`gen_beats_btn.click`):

- Inputs: add `content_is_beats_state` (to pass through on failure).
- Outputs: add `content_is_beats_state`.
- Handler `do_generate_beat_outline`: add parameter `content_is_beats: bool`, return `(..., content_is_beats)`. On success: `True`; on skip/failure: `content_is_beats` (unchanged).

**Regenerate** (`regen_btn.click`):

- Inputs: add `content_is_beats_state`.
- Outputs: add `content_is_beats_state`.
- Handler `do_regenerate_beat_outline`: add parameter `content_is_beats: bool`, return `(..., content_is_beats)`. On success: `True`; on skip/failure: `content_is_beats` (unchanged).

**Expand idea to précis** (`expand_btn.click`):

- Inputs: add `content_is_beats_state`.
- Outputs: add `content_is_beats_state`.
- Handler `do_expand_idea`: add parameter `content_is_beats: bool`, return `(..., content_is_beats)`. On success: `False`; on skip/failure: `content_is_beats` (unchanged).

**Undo précis** (`undo_btn.click`):

- Inputs: add `content_is_beats_state`.
- Outputs: add `content_is_beats_state`.
- Handler `do_undo_precis`: add parameter `content_is_beats: bool`, return `(..., content_is_beats)`. Always return `False` (undo restores pre-beats content).

**Reset** (`reset_btn.click`):

- Outputs: add `content_is_beats_state`.
- Handler `do_reset_write`: add `False` as last return value.

**Start** (`start_btn.click`):

- Inputs: add `content_is_beats_state`.
- Outputs: add `content_is_beats_state`.
- Handler `do_start_write`: add parameter `content_is_beats: bool`, return `(..., content_is_beats)`. Replace `if _is_beat_outline(idea):` with `if content_is_beats:`. After rewrite (or when not rewriting), return `False` (beats consumed or never present).

### 3. Remove format detection

- Delete `_is_beat_outline()` from [`working/handlers.py`](working/handlers.py).
- Remove any imports or references to it.

## Files to Modify

| File | Changes |
|------|---------|
| [`app.py`](app.py) | Add `content_is_beats_state`, wire to all six handlers, add to nav outputs if needed |
| [`working/handlers.py`](working/handlers.py) | Add `content_is_beats` param and return to `do_generate_beat_outline`, `do_regenerate_beat_outline`, `do_expand_idea`, `do_undo_precis`, `do_reset_write`, `do_start_write`; replace `_is_beat_outline(idea)` with `content_is_beats` in `do_start_write`; delete `_is_beat_outline` |
| [`version.py`](version.py) | Bump version |

## Verification

1. Generate beat outline → Start: précis rewrite runs (check log for "Rewriting précis from beats").
2. Regenerate → Start: same.
3. Expand idea to précis → Start: no rewrite.
4. Undo précis (after beats) → Start: no rewrite (content restored to précis).
5. Reset → Start: no rewrite.

---

## TODO List

- [ ] Add `content_is_beats_state = gr.State(False)` in `app.py`
- [ ] Wire `content_is_beats_state` to `gen_beats_btn`, `regen_btn`, `expand_btn`, `undo_btn`, `reset_btn`, `start_btn` (inputs/outputs as specified)
- [ ] Update `do_generate_beat_outline`, `do_regenerate_beat_outline`, `do_expand_idea`, `do_undo_precis`, `do_reset_write`, `do_start_write` with new param/return
- [ ] Replace `_is_beat_outline(idea)` with `content_is_beats` in `do_start_write`
- [ ] Delete `_is_beat_outline` from `handlers.py`
- [ ] Bump version in `version.py`
- [ ] **brutal-pr** — Run brutal-pr skill to review work
- [ ] **brutal-address-pr** — Use brutal-address-pr skill to address all issues from review
- [ ] **brutal-pr-review-loop** — Finally use the brutal-pr-review-loop skill to confirm that has run properly
