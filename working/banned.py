"""
Banned characters in LLM story output. Em-dash is replaced with " - "; others cause reject/retry.
Rule-based replacement for high-signal AI phrases (cheap pre-pass before humanization).
"""

# Characters banned from LLM story output. Em-dash is auto-replaced; others would cause reject.
BANNED_CHARS: tuple[str, ...] = ("\u2014",)  # em dash (—); replaced with " - "
EM_DASH = "\u2014"
EM_DASH_REPLACEMENT = " - "

# AI-flag transitions to replace (phrase -> replacement). Order matters for overlapping patterns.
AI_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Moreover,", "And,"),
    ("Moreover, ", "And, "),
    ("Furthermore,", "Also,"),
    ("Furthermore, ", "Also, "),
    ("In conclusion,", "So,"),
    ("In conclusion, ", "So, "),
    ("On the other hand,", "But"),
    ("On the other hand, ", "But "),
    ("As a result,", "So,"),
    ("As a result, ", "So, "),
)


def replace_emdash(text: str) -> str:
    """Replace em-dash (—) with space-hyphen-space. Returns new string."""
    if not text or EM_DASH not in text:
        return text
    return text.replace(EM_DASH, EM_DASH_REPLACEMENT)


def replace_ai_phrases(text: str) -> str:
    """Replace high-signal AI transition phrases with natural alternatives. Cheap pre-pass before humanization."""
    if not text:
        return text
    out = text
    for phrase, replacement in AI_PHRASE_REPLACEMENTS:
        out = out.replace(phrase, replacement)
    return out


BANNED_PROMPT_INSTRUCTION = (
    "Do not use em dash. Use a regular hyphen (-) or \" - \" (space-hyphen-space) instead. "
    "ONLY em dash is banned. Keep apostrophes in contractions (don't, it's, we're); "
    "never replace apostrophes with space-hyphen-space."
)
