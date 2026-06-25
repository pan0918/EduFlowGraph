"""Skill adaptation evidence store.

This state is used only for Skill retrieval/reranking. It is deliberately
separate from the learner portrait so UI and prompt boundaries stay clear.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..profile.dimensions import MAX_RECENT_CHANGES
from ..schemas import utc_now


LEGACY_MODEL_NAME = "teaching_adaptation_model"


class SkillAdaptationStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "skill_adaptation.json"
        self._legacy_profile_path = self.data_dir / "learner_profile.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def empty_snapshot(self) -> dict[str, Any]:
        return {
            "summary": "",
            "updated_at": None,
            "revisions": 0,
            "recent_changes": [],
            "health": {"status": "ok", "message": ""},
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.empty_snapshot()
        text = self.path.read_text(encoding="utf-8").strip()
        if not text:
            return self.empty_snapshot()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {
                **self.empty_snapshot(),
                "health": {"status": "error", "message": "invalid JSON"},
            }
        if not isinstance(payload, dict):
            return self.empty_snapshot()
        return self._normalize_snapshot(payload)

    def save(self, snapshot: dict[str, Any]) -> None:
        snapshot = self._normalize_snapshot(snapshot)
        self.path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def update(self, summary: str, note: str = "") -> dict[str, Any]:
        snapshot = self.load()
        summary = (summary or "").strip()
        previous = str(snapshot.get("summary", "")).strip()
        if summary == previous:
            return snapshot

        ts = utc_now()
        snapshot["summary"] = summary
        snapshot["updated_at"] = ts
        snapshot["revisions"] = int(snapshot.get("revisions", 0) or 0) + 1
        note = (note or "").strip()
        if note and note != "无变化":
            changes = list(snapshot.get("recent_changes", []))
            changes.insert(0, {"at": ts, "note": note})
            snapshot["recent_changes"] = changes[:MAX_RECENT_CHANGES]
        self.save(snapshot)
        return snapshot

    def summary(self) -> str:
        return str(self.load().get("summary", "")).strip()

    def is_empty(self) -> bool:
        return not bool(self.summary())

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def migrate_legacy_if_needed(self) -> None:
        """Copy old profile-contained adaptation evidence into the new store."""
        if self.path.exists() and str(self.load().get("summary", "")).strip():
            return
        if not self._legacy_profile_path.exists():
            return
        try:
            payload = json.loads(
                self._legacy_profile_path.read_text(encoding="utf-8") or "{}"
            )
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        models = payload.get("models")
        if not isinstance(models, dict):
            return
        entry = models.get(LEGACY_MODEL_NAME)
        if not isinstance(entry, dict):
            return
        summary = str(entry.get("summary", "")).strip()
        if not summary:
            return
        recent = payload.get("recent_changes", [])
        if not isinstance(recent, list):
            recent = []
        changes = [
            {
                "at": change.get("at"),
                "note": str(change.get("note", "")),
            }
            for change in recent
            if isinstance(change, dict)
            and change.get("model") == LEGACY_MODEL_NAME
            and str(change.get("note", "")).strip()
        ][:MAX_RECENT_CHANGES]
        self.save(
            {
                "summary": summary,
                "updated_at": entry.get("updated_at"),
                "revisions": int(entry.get("revisions", 0) or 0),
                "recent_changes": changes,
                "health": {"status": "ok", "message": ""},
            }
        )

    def _normalize_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        health = payload.get("health")
        if not isinstance(health, dict):
            health = {"status": "ok", "message": ""}

        recent = payload.get("recent_changes", [])
        if not isinstance(recent, list):
            recent = []
        clean_recent = [
            {
                "at": change.get("at"),
                "note": str(change.get("note", "")),
            }
            for change in recent
            if isinstance(change, dict)
        ][:MAX_RECENT_CHANGES]

        return {
            "summary": str(payload.get("summary", "")).strip(),
            "updated_at": payload.get("updated_at"),
            "revisions": int(payload.get("revisions", 0) or 0),
            "recent_changes": clean_recent,
            "health": health,
        }
