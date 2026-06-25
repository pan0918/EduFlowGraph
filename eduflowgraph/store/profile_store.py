"""Lightweight learner profile store.

The profile is two short paragraphs ("memory notes"), one per portrait. Each update
*rewrites* the relevant paragraph (adding new content, removing stale content) instead
of appending to an ever-growing evidence log. A small bounded change-log is kept purely
for UI transparency.

Snapshot shape::

    {
      "models": {
        "learner_model":  {"summary": "...", "updated_at": "...", "revisions": 3},
        "context_model":  {"summary": "...", "updated_at": "...", "revisions": 5}
      },
      "recent_changes": [{"at": "...", "model": "...", "note": "新增…；删除…"}],
      "updated_at": "...",
      "revision_count": 10,
      "health": {"status": "ok", "message": ""}
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..profile.dimensions import MAX_RECENT_CHANGES, MODEL_NAMES
from ..schemas import utc_now


class LearnerProfileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "learner_profile.json"
        # Legacy artifacts from the old evidence-accumulation design.
        self._legacy_evidence_path = data_dir / "profile_evidence.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)

    # ── Snapshot load / save ────────────────────────────────────────

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
        snapshot["updated_at"] = utc_now()
        self.path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def empty_snapshot(self) -> dict[str, Any]:
        return {
            "models": {name: self._empty_model() for name in MODEL_NAMES},
            "recent_changes": [],
            "updated_at": None,
            "revision_count": 0,
            "health": {"status": "ok", "message": ""},
        }

    @staticmethod
    def _empty_model() -> dict[str, Any]:
        return {"summary": "", "updated_at": None, "revisions": 0}

    # ── Updates ─────────────────────────────────────────────────────

    def update_model(self, model_name: str, summary: str, note: str = "") -> dict[str, Any]:
        """Rewrite a single model's paragraph and log a bounded change entry."""
        if model_name not in MODEL_NAMES:
            return self.load()
        snapshot = self.load()
        summary = (summary or "").strip()
        model = snapshot["models"].get(model_name, self._empty_model())
        previous = str(model.get("summary", "")).strip()

        # Skip no-op rewrites (same text or explicit "no change" with empty content).
        if summary == previous:
            return snapshot

        ts = utc_now()
        snapshot["models"][model_name] = {
            "summary": summary,
            "updated_at": ts,
            "revisions": int(model.get("revisions", 0)) + 1,
        }
        snapshot["revision_count"] = int(snapshot.get("revision_count", 0)) + 1
        note = (note or "").strip()
        if note and note != "无变化":
            changes = list(snapshot.get("recent_changes", []))
            changes.insert(0, {"at": ts, "model": model_name, "note": note})
            snapshot["recent_changes"] = changes[:MAX_RECENT_CHANGES]
        self.save(snapshot)
        return snapshot

    def update_models(self, updates: dict[str, dict[str, str]]) -> dict[str, Any]:
        """Apply rewrites to multiple models in one pass (single write)."""
        snapshot = self.load()
        ts = utc_now()
        changes = list(snapshot.get("recent_changes", []))
        changed_any = False

        for model_name, payload in updates.items():
            if model_name not in MODEL_NAMES or not isinstance(payload, dict):
                continue
            summary = str(payload.get("summary", "")).strip()
            model = snapshot["models"].get(model_name, self._empty_model())
            previous = str(model.get("summary", "")).strip()
            if not summary or summary == previous:
                continue
            snapshot["models"][model_name] = {
                "summary": summary,
                "updated_at": ts,
                "revisions": int(model.get("revisions", 0)) + 1,
            }
            snapshot["revision_count"] = int(snapshot.get("revision_count", 0)) + 1
            changed_any = True
            note = str(payload.get("note", "")).strip()
            if note and note != "无变化":
                changes.insert(0, {"at": ts, "model": model_name, "note": note})

        if not changed_any:
            return snapshot
        snapshot["recent_changes"] = changes[:MAX_RECENT_CHANGES]
        self.save(snapshot)
        return snapshot

    # ── Accessors ───────────────────────────────────────────────────

    def summary(self, model_name: str) -> str:
        return str(self.load()["models"].get(model_name, {}).get("summary", "")).strip()

    def summaries(self) -> dict[str, str]:
        models = self.load()["models"]
        return {name: str(models.get(name, {}).get("summary", "")).strip() for name in MODEL_NAMES}

    def is_empty(self) -> bool:
        return not any(self.summaries().values())

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        if self._legacy_evidence_path.exists():
            self._legacy_evidence_path.unlink()

    # ── Migration ───────────────────────────────────────────────────

    def migrate_legacy_if_needed(self) -> None:
        """Clean-reset migration from the old evidence-accumulation design.

        The previous design stored ``profile_evidence.jsonl`` plus an item-list
        snapshot. We discard both and start from a blank lightweight profile; the
        profile regenerates naturally from the next conversations.
        """
        legacy_removed = False
        if self._legacy_evidence_path.exists():
            self._legacy_evidence_path.unlink()
            legacy_removed = True
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {}
            if self._is_legacy_snapshot(payload):
                self.path.unlink()
                legacy_removed = True
        if legacy_removed and not self.path.exists():
            self.save(self.empty_snapshot())

    @staticmethod
    def _is_legacy_snapshot(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if "items" in payload or "dimensions" in payload:
            return True
        models = payload.get("models")
        if isinstance(models, dict):
            for value in models.values():
                # New format stores a dict per model; legacy stored a list of items.
                if isinstance(value, list):
                    return True
        return False

    def _normalize_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        empty = self.empty_snapshot()
        models_in = payload.get("models")
        models: dict[str, Any] = {}
        for name in MODEL_NAMES:
            entry = models_in.get(name) if isinstance(models_in, dict) else None
            if isinstance(entry, dict):
                models[name] = {
                    "summary": str(entry.get("summary", "")).strip(),
                    "updated_at": entry.get("updated_at"),
                    "revisions": int(entry.get("revisions", 0) or 0),
                }
            else:
                models[name] = self._empty_model()

        recent = payload.get("recent_changes", [])
        if not isinstance(recent, list):
            recent = []
        clean_recent = [
            {
                "at": c.get("at"),
                "model": c.get("model"),
                "note": str(c.get("note", "")),
            }
            for c in recent
            if isinstance(c, dict) and c.get("model") in MODEL_NAMES
        ][:MAX_RECENT_CHANGES]

        health = payload.get("health")
        if not isinstance(health, dict):
            health = empty["health"]

        return {
            "models": models,
            "recent_changes": clean_recent,
            "updated_at": payload.get("updated_at"),
            "revision_count": sum(
                int(entry.get("revisions", 0) or 0) for entry in models.values()
            ),
            "health": health,
        }
