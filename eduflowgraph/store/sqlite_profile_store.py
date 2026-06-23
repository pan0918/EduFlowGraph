from __future__ import annotations

from typing import Any

from ..profile.dimensions import MAX_RECENT_CHANGES, MODEL_NAMES
from ..schemas import utc_now
from .profile_store import LearnerProfileStore
from .sqlite_storage import SQLiteStorage


class SQLiteLearnerProfileStore(LearnerProfileStore):
    """LearnerProfileStore-compatible materialized profile in SQLite."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage
        self.data_dir = storage.path.parent
        self.path = storage.path
        self._legacy_evidence_path = self.data_dir / "profile_evidence.jsonl"

    def load(self) -> dict[str, Any]:
        with self.storage.connect() as connection:
            model_rows = connection.execute(
                "SELECT model_name, summary, updated_at, revisions "
                "FROM profile_models"
            ).fetchall()
            change_rows = connection.execute(
                "SELECT changed_at, model_name, note FROM profile_changes "
                "ORDER BY change_id DESC LIMIT ?",
                (MAX_RECENT_CHANGES,),
            ).fetchall()

        models = {name: self._empty_model() for name in MODEL_NAMES}
        for row in model_rows:
            name = str(row["model_name"])
            if name not in models:
                continue
            models[name] = {
                "summary": str(row["summary"]),
                "updated_at": row["updated_at"],
                "revisions": int(row["revisions"]),
            }
        recent_changes = [
            {
                "at": row["changed_at"],
                "model": str(row["model_name"]),
                "note": str(row["note"]),
            }
            for row in change_rows
        ]
        updated_values = [
            str(entry["updated_at"])
            for entry in models.values()
            if entry.get("updated_at")
        ]
        return {
            "models": models,
            "recent_changes": recent_changes,
            "updated_at": max(updated_values) if updated_values else None,
            "revision_count": sum(int(entry["revisions"]) for entry in models.values()),
            "health": {"status": "ok", "message": ""},
        }

    def save(self, snapshot: dict[str, Any]) -> None:
        snapshot = self._normalize_snapshot(snapshot)
        snapshot["updated_at"] = utc_now()
        with self.storage.transaction() as connection:
            for name in MODEL_NAMES:
                entry = snapshot["models"][name]
                connection.execute(
                    "INSERT INTO profile_models(model_name, summary, updated_at, revisions) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(model_name) DO UPDATE SET summary=excluded.summary, "
                    "updated_at=excluded.updated_at, revisions=excluded.revisions",
                    (
                        name,
                        str(entry.get("summary", "")),
                        entry.get("updated_at"),
                        int(entry.get("revisions", 0)),
                    ),
                )
            connection.execute("DELETE FROM profile_changes")
            for change in reversed(snapshot.get("recent_changes", [])):
                model_name = str(change.get("model", ""))
                if model_name not in MODEL_NAMES:
                    continue
                connection.execute(
                    "INSERT INTO profile_changes(changed_at, model_name, note) VALUES (?, ?, ?)",
                    (
                        str(change.get("at") or snapshot["updated_at"]),
                        model_name,
                        str(change.get("note", "")),
                    ),
                )

    def clear(self) -> None:
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM profile_changes")
            connection.execute(
                "UPDATE profile_models SET summary='', updated_at=NULL, revisions=0"
            )

    def migrate_legacy_if_needed(self) -> None:
        return None
