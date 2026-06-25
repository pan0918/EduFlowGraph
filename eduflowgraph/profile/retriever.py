"""Lightweight profile rendering for the memory-augmented prompt.

Only the learner and current-context paragraphs are injected into the tutor context.
The teaching-adaptation paragraph is reserved for Skill personalization and must not
leak into the Tutor prompt as a complete block.
"""
from __future__ import annotations

from typing import Any

from .dimensions import PROFILE_MODELS

_PROMPT_MODEL_NAMES = ("learner_model", "context_model")

_SECTION_TITLES = {
    "learner_model": "[长期学习者画像]",
    "context_model": "[当前学习情境]",
}


def render_profile_context(profile: dict[str, Any]) -> str:
    """Render only prompt-safe profile paragraphs into a context block."""
    if not isinstance(profile, dict):
        return ""
    models = profile.get("models", {})
    if not isinstance(models, dict):
        return ""

    sections: list[str] = []
    for name in _PROMPT_MODEL_NAMES:
        entry = models.get(name, {})
        summary = ""
        if isinstance(entry, dict):
            summary = str(entry.get("summary", "")).strip()
        if not summary:
            continue
        title = _SECTION_TITLES.get(name, PROFILE_MODELS.get(name, {}).get("label", name))
        sections.append(f"{title}\n{summary}")

    return "\n\n".join(sections)
