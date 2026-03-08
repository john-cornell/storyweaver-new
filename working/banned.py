"""
Banned characters in LLM story output. Em-dash is replaced with " - "; others cause reject/retry.
"""

# Characters banned from LLM story output. Em-dash is auto-replaced; others would cause reject.
BANNED_CHARS: tuple[str, ...] = ("\u2014",)  # em dash (—); replaced with " - "
EM_DASH = "\u2014"
EM_DASH_REPLACEMENT = " - "


def replace_emdash(text: str) -> str:
    """Replace em-dash (—) with space-hyphen-space. Returns new string."""
    if not text or EM_DASH not in text:
        return text
    return text.replace(EM_DASH, EM_DASH_REPLACEMENT)

BANNED_PROMPT_INSTRUCTION = (
    "Do not use em dash. Use a regular hyphen (-) or \" - \" (space-hyphen-space) instead. "
    "ONLY em dash is banned. Keep apostrophes in contractions (don't, it's, we're); "
    "never replace apostrophes with space-hyphen-space."
)
