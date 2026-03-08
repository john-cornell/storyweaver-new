# REQUIRED FIXES FROM PR COMMENTS — Expansion Shrinkage Fix

**Context**: Fix expansion shrinkage and plot loss (plan 23c6bdfe)  
**Review date**: 2025-03-02

---

## Review Summary

Implementation of the plan is complete. One nitpick was addressed during review:

### Addressed

1. **Parser join robustness** — Changed `" ".join((p1 or "").split("\n\n"))` to `" ".join(s.strip() for s in (p1 or "").split("\n\n") if s.strip())` to avoid double spaces and filter empty blocks.

### No Remaining Issues

- Prompts: Length targets, PLOT PRESERVATION, relaxed constraints applied correctly.
- Handlers: _is_too_short wired in both do_expand_next and do_expand_round with retry hints.
- Previous-paragraph label updated in both expansion paths.
- Validation prompt: Backward contamination and length checks added.
- Parsing: Join preserves content; echo prefixes updated for new label.
- Version: 1.0.81.
