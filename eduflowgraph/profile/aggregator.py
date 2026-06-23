"""Lightweight profile summary helpers for the three-paragraph profile."""
from __future__ import annotations

from typing import Any

from .dimensions import MODEL_NAMES, PROFILE_MODELS


def summarize_profile(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a concise per-model overview of the lightweight profile."""
    models = snapshot.get("models", {}) if isinstance(snapshot, dict) else {}
    summary: dict[str, Any] = {}
    for name in MODEL_NAMES:
        entry = models.get(name, {}) if isinstance(models, dict) else {}
        text = str(entry.get("summary", "")).strip() if isinstance(entry, dict) else ""
        summary[name] = {
            "label": PROFILE_MODELS[name]["label"],
            "has_content": bool(text),
            "length": len(text),
            "revisions": int(entry.get("revisions", 0) or 0) if isinstance(entry, dict) else 0,
            "summary": text,
        }
    return summary


def profile_is_populated(snapshot: dict[str, Any]) -> bool:
    """True when at least one model paragraph carries content."""
    models = snapshot.get("models", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(models, dict):
        return False
    return any(
        isinstance(entry, dict) and str(entry.get("summary", "")).strip()
        for entry in models.values()
    )
