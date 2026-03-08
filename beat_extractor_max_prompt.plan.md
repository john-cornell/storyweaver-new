# Beat Extractor Max-Beats Prompt — Implementation Plan

## Overview

The beat extractor currently asks the LLM to "extract all Hidden Events" with no upper bound. With `BEAT_MAX_BEATS=16`, the extractor often returns 21, 28, or 41 beats, triggering fallback to single-call SCENE expand and losing the Micro-Beat Protocol. Logs show many "exceeds max 16" fallbacks and validation retries. Add an explicit max-beats instruction to the prompt so the LLM usually returns beats within the configured limit.

---

WHEN IMPLEMENTING USE brutal-coder skill

AFTER IMPLEMENTATION use brutal-pr skill to review work and brutal-address-pr skill to address issues and loop until ALL issues, no matter how trivial are addressed

---

## Problem (from log analysis)

- **Exceeds max fallbacks:** Step 1 P1 (41 beats), P2 (41 beats), P1,L (28), P2,L (28), P2,R (21) — all exceeded max 16.
- **Validation retries:** Step 1 P1, P2, P1,L, P1,R, P2,L, P2,R — multiple validation rejections.
- **Root cause:** [`working/beat_extractor.py`](working/beat_extractor.py) `BEAT_EXTRACTOR_SYSTEM` says "extract all" with no cap. The LLM returns as many as it finds.

## Solution

Inject `max_beats` (from `ExpansionConfig.from_env().max_beats`) into the beat extractor prompt. Instruct the LLM to output at most N beats, preferring the most plot-critical ones.

## Implementation Steps

### 1. Make beat extractor prompt dynamic

In [`working/beat_extractor.py`](working/beat_extractor.py):

- Add a function or template that builds the system prompt with `max_beats` injected, e.g.:

  ```
  ...Output at most {max_beats} atomic beats. If the text implies more, choose the most plot-critical ones. Output ONLY the numbered list...
  ```

- `extract_beats(text)` must obtain `max_beats` from `ExpansionConfig.from_env().max_beats` and pass it into the prompt builder.
- Add import: `from config import ExpansionConfig`.

### 2. Prompt wording

Append to the existing instructions (before "Output ONLY the numbered list"):

```
Output at most {max_beats} atomic beats. If the text implies more events, choose the most plot-critical ones.
```

Use the configured `max_beats` value. Do not hardcode a number.

### 3. Backward compatibility

If `max_beats` is 1, the instruction still makes sense ("at most 1 beat"). No special casing required.

### 4. Version bump

Update [`version.py`](version.py) per project rules.

## Files to Modify

| File | Changes |
|------|---------|
| [`working/beat_extractor.py`](working/beat_extractor.py) | Import ExpansionConfig; build system prompt with max_beats; inject into `complete()` call |
| [`version.py`](version.py) | Bump version |

## Verification

1. Set `BEAT_MAX_BEATS=16` in `.env`.
2. Run expansion on a dense paragraph.
3. Log should show "Micro-Beat Protocol — N beats" with N ≤ 16 more often, and fewer "exceeds max 16; using fallback SCENE expand" entries.

---

## TODO List

- [ ] Add `ExpansionConfig` import to `beat_extractor.py`
- [ ] Build `BEAT_EXTRACTOR_SYSTEM` dynamically with `max_beats` from config
- [ ] Add instruction: "Output at most {max_beats} atomic beats. If the text implies more events, choose the most plot-critical ones."
- [ ] Bump version in `version.py`
- [ ] **brutal-pr** — Run brutal-pr skill to review work
- [ ] **brutal-address-pr** — Use brutal-address-pr skill to address all issues from review
- [ ] **brutal-pr-review-loop** — Finally use the brutal-pr-review-loop skill to confirm that has run properly
