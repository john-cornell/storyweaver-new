"""
Registry for generation mode handlers.
Returns the appropriate ModeHandler for a given GenerationMode.
"""

from __future__ import annotations

from .expansion import ExpansionModeHandler
from .interactive import InteractiveModeHandler
from .types import GenerationMode, ModeHandler

_handlers: dict[GenerationMode, ModeHandler] = {
    GenerationMode.EXPANSION: ExpansionModeHandler(),
    GenerationMode.INTERACTIVE: InteractiveModeHandler(),
}


def get_handler(mode: GenerationMode) -> ModeHandler:
    """Return the ModeHandler for the given generation mode."""
    return _handlers[mode]
