from __future__ import annotations

from typing import Any

from ..profile.dimensions import MAX_RECENT_CHANGES
from ..schemas import utc_now
from .skill_adaptation_store import SkillAdaptationStore
from .sqlite_storage import SQLiteStorage


class SQLiteSkillAdaptationStore(SkillAdaptationStore):
    """SQLite-backed Skill adaptation evidence store."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage
        self.data_dir = storage.path.parent
        self.path = storage.path
        self._legacy_profile_path = self.data_dir / "learner_profile.json"

    def load(self) -> dict[str, Any]:
        with self.storage.connect() as connection:
            row = connection.execute(
                "SELECT summary, updated_at, revisions "
                "FROM skill_adaptation WHERE key='default'"
            ).fetchone()
            change_rows = connection.execute(
                "SELECT changed_at, note FROM skill_adaptation_changes "
                "ORDER BY change_id DESC LIMIT ?",
                (MAX_RECENT_CHANGES,),
            ).fetchall()

        if row is None:
            snapshot = self.empty_snapshot()
        else:
            snapshot = {
                "summary": str(row["summary"]),
                "updated_at": row["updated_at"],
                "revisions": int(row["revisions"]),
                "recent_changes": [
                    {"at": change["changed_at"], "note": str(change["note"])}
                    for change in change_rows
                ],
                "health": {"status": "ok", "message": ""},
            }
        return self._normalize_snapshot(snapshot)

    def save(self, snapshot: dict[str, Any]) -> None:
        snapshot = self._normalize_snapshot(snapshot)
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO skill_adaptation(key, summary, updated_at, revisions) "
                "VALUES ('default', ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET summary=excluded.summary, "
                "updated_at=excluded.updated_at, revisions=excluded.revisions",
                (
                    str(snapshot.get("summary", "")),
                    snapshot.get("updated_at"),
                    int(snapshot.get("revisions", 0)),
                ),
            )
            connection.execute("DELETE FROM skill_adaptation_changes")
            for change in reversed(snapshot.get("recent_changes", [])):
                connection.execute(
                    "INSERT INTO skill_adaptation_changes(changed_at, note) "
                    "VALUES (?, ?)",
                    (
                        str(change.get("at") or snapshot.get("updated_at") or utc_now()),
                        str(change.get("note", "")),
                    ),
                )

    def update(self, summary: str, note: str = "") -> dict[str, Any]:
        snapshot = self.load()
        summary = (summary or "").strip()
        previous = str(snapshot.get("summary", "")).strip()
        if summary == previous:
            return snapshot

        ts = utc_now()
        note = (note or "").strip()
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO skill_adaptation(key, summary, updated_at, revisions) "
                "VALUES ('default', ?, ?, 1) "
                "ON CONFLICT(key) DO UPDATE SET summary=excluded.summary, "
                "updated_at=excluded.updated_at, revisions=revisions + 1",
                (summary, ts),
            )
            if note and note != "无变化":
                connection.execute(
                    "INSERT INTO skill_adaptation_changes(changed_at, note) "
                    "VALUES (?, ?)",
                    (ts, note),
                )
        updated = self.load()
        updated["recent_changes"] = updated.get("recent_changes", [])[:MAX_RECENT_CHANGES]
        return updated

    def clear(self) -> None:
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM skill_adaptation_changes")
            connection.execute(
                "UPDATE skill_adaptation SET summary='', updated_at=NULL, revisions=0 "
                "WHERE key='default'"
            )

    def migrate_legacy_if_needed(self) -> None:
        return None
