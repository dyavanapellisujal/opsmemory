"""Dedicated system prompts shipped with the platform."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt file bundled with the package.

    Args:
        name: File name, e.g. ``incident_meeting_extraction_prompt.txt``.
    """
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")
