"""Lightweight profile rendering for the memory-augmented prompt.

The profile is three short paragraphs, already consolidated and tiny, so there is no
scoring or graph fusion to do — the relevant paragraphs are simply injected directly
into the tutor context.
"""
from __future__ import annotations

from typing import Any

from .dimensions import MODEL_NAMES, PROFILE_MODELS

_SECTION_TITLES = {
    "learner_model": "[长期学习者画像]",
    "strategy_model": "[下一步教学策略]",
    "context_model": "[当前学习情境]",
}


def render_profile_context(profile: dict[str, Any]) -> str:
    """Render the three profile paragraphs into a context block for the prompt."""
    if not isinstance(profile, dict):
        return ""
    models = profile.get("models", {})
    if not isinstance(models, dict):
        return ""

    sections: list[str] = []
    for name in MODEL_NAMES:
        entry = models.get(name, {})
        summary = ""
        if isinstance(entry, dict):
            summary = str(entry.get("summary", "")).strip()
        if not summary:
            continue
        title = _SECTION_TITLES.get(name, PROFILE_MODELS.get(name, {}).get("label", name))
        sections.append(f"{title}\n{summary}")

    return "\n\n".join(sections)
