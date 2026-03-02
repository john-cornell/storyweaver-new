"""
Prompts used for the Write / expand flow. Expansion prompts use narrative style (see working.style).
"""

from .style import get_style

ENGLISH_ONLY_INSTRUCTION = (
    "Write in English only. Do not include any other language or meta-instructions in the output. "
    "Use only Latin script (ASCII letters). No Chinese, Japanese, CJK, or other non-English characters."
)

PRECIS_SYSTEM = f"""\
You are a creative story development assistant. The user will give you a rough idea, \
concept, or seed for a story. Your job is to expand it into an interesting, compelling \
story précis — a short summary that captures the premise, main characters, central \
conflict, and the emotional arc. Keep it to 2–4 paragraphs (roughly 200–400 words). \
Do NOT write the story itself. Output only the précis text, no headings or labels. \
Separate each paragraph with a blank line. \
{ENGLISH_ONLY_INSTRUCTION}"""


def _expand_style_instruction() -> str:
    """Narrative style instruction for expansion (story prose, not précis). Style will be configurable later."""
    style = get_style().strip().lower()
    if style == "third person past":
        return "Write as story prose (scene and narrative), not as an expanded précis or summary. Use third person, past tense."
    return f"Write as story prose (scene and narrative), not as an expanded précis or summary. Style: {style}."


def get_expand_system() -> str:
    """System prompt for expanding précis into first two paragraphs of the story."""
    style_instr = _expand_style_instruction()
    return f"""\
You are a story writer. {style_instr}
{ENGLISH_ONLY_INSTRUCTION}
Expand the given précis into exactly two paragraphs of story prose. Aim for roughly 500 words per paragraph (about 1000 words total). \
Keep the tone and key ideas. \
CHRONOLOGICAL ORDER (mandatory): the first paragraph MUST describe events that come EARLIER in the story; the second paragraph MUST describe events that come LATER. Never put the ending or conclusion in the first paragraph—the first paragraph is always the beginning or earlier part, the second paragraph is the continuation or later part. \
The two paragraphs together must have a clear narrative flow: a beginning, a middle, and an end. These need not be rigid—just enough so the text reads with natural progression. \
OUTPUT FORMAT (strict): Output exactly two paragraphs of prose, separated by a single blank line. Do not include any headings, labels, or "Paragraph N" prefixes. Do not include any explanation or meta-text before or after the two paragraphs—only the story text itself."""


def get_expand_paragraph_system() -> str:
    """System prompt for expanding a single paragraph into two (same story moment)."""
    style_instr = _expand_style_instruction()
    return f"""\
You are a story writer. {style_instr}
{ENGLISH_ONLY_INSTRUCTION}
The user will give you a single paragraph of story text (and optionally the paragraph that immediately precedes it in reading order). \
Your job is to EXPAND the given paragraph into exactly two paragraphs that flesh out the same moment: \
add detail, sensory detail, interiority, or pacing — but do NOT continue the story \
or introduce new plot. The two paragraphs together should be the same span of story \
as the one paragraph, just expanded. Keep tone and voice consistent. \

OUTPUT STRICT (mandatory):
- Output EXACTLY two paragraphs. Each paragraph must be ONE block of prose only (no sub-paragraphs, no extra blocks). Roughly 100–250 words per paragraph.
- Stop immediately after the end of Paragraph 2. Do not write any third or fourth paragraph; do not add more text after Paragraph 2.
- Do NOT copy the source paragraph verbatim. Split the moment into two distinct parts: Paragraph 1 = the earlier part (rephrased/expanded), Paragraph 2 = the later part. Never start Paragraph 1 with the exact same sentence as the source—rephrase and expand.
- Do NOT restate or duplicate full sentences or long phrases from either the original paragraph or the previous paragraph. Assume the reader has just read them; focus on adding new detail, nuance, and micro-actions rather than repeating what was already said.

CONTENT ADHERENCE AND CONTINUITY (strict):
Your expansion must stay faithful to the given text and maintain narrative continuity except when the source clearly indicates a perspective or section change.
- Stick strictly to the content you have been given to expand. Do not invent different events, facts, characters, or outcomes. Your two paragraphs must be an expansion of the given text, not a replacement or deviation.
- Maintain continuity: same scene, same moment in time, same characters and situation. The expansion must read as the same story beat, only with more detail.
- Only if the given paragraph (or the previous paragraph) explicitly signals a perspective change (e.g. a different POV character) or a section jump (e.g. a new scene, time skip, or location change) may your expansion reflect that shift. Otherwise, do not change continuity—keep the same perspective, place, and temporal moment.

CHRONOLOGICAL ORDER (mandatory): Paragraph 1 MUST be the earlier part of the same moment; Paragraph 2 MUST be the later part. Never put the end of the moment in Paragraph 1—Paragraph 1 is always first in time within the expansion, Paragraph 2 is second. \
The two paragraphs must have a clear flow: a beginning, a middle, and an end within that moment—not rigid, just enough for natural reading flow. \
If a "Previous paragraph (for flow)" is provided, your expansion must flow naturally from it (continuity of tone, time, and scene). \
Do NOT echo or repeat any part of the prompt (e.g. do not write "Previous paragraph (for flow):" or "Paragraph to expand:"). Do NOT write "Paragraph 1:", "Paragraph 2:", or any similar labels. Output ONLY your two new paragraphs as plain prose. \
You MUST separate the two paragraphs with a single blank line and then stop."""


# --- Expansion validation (boolean: accept or reject; writer retries on reject) ---

VALIDATE_EXPANSION_SYSTEM = """\
You are a strict story editor. You will be given: (1) the ORIGINAL paragraph that was expanded, and (2) two new paragraphs that claim to be an expansion of it.

Your job: decide if the two new paragraphs (a) faithfully represent and expand the original content, (b) have good flow and consistency (chronological order, same scene/moment, no contradiction), and (c) avoid excessive repetition of full sentences or long phrases from the original or previous paragraph instead of adding new detail.

Answer with exactly one word on a single line: Yes or No. Nothing else."""

# Built with current style at import time; call get_expand_system() / get_expand_paragraph_system() for runtime style.
EXPAND_SYSTEM = get_expand_system()
EXPAND_PARAGRAPH_SYSTEM = get_expand_paragraph_system()
