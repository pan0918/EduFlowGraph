from __future__ import annotations

from typing import Any, Iterator

from ..schemas import Turn, utc_now
from .sqlite_storage import SQLiteStorage, decode_json, encode_json


class SQLiteConversationLog:
    """SQLite implementation of the ConversationLog behavioral contract."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def append_turn(
        self,
        *,
        session_id: str,
        turn_index: int,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Turn:
        turn = Turn(
            turn_index=turn_index,
            timestamp=utc_now(),
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            metadata=metadata or {},
        )
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO sessions(session_id, created_at, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
                (session_id, turn.timestamp, turn.timestamp),
            )
            connection.execute(
                "INSERT INTO turns(session_id, turn_index, timestamp, user_message, "
                "assistant_message, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    turn_index,
                    turn.timestamp,
                    user_message,
                    assistant_message,
                    encode_json(turn.metadata),
                ),
            )
        return turn

    def iter_turns(self, session_id: str) -> Iterator[dict[str, Any]]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT session_id, turn_index, timestamp, user_message, "
                "assistant_message, metadata_json FROM turns "
                "WHERE session_id=? ORDER BY turn_index ASC",
                (session_id,),
            ).fetchall()
        for row in rows:
            yield {
                "turn_index": int(row["turn_index"]),
                "timestamp": str(row["timestamp"]),
                "session_id": str(row["session_id"]),
                "user_message": str(row["user_message"]),
                "assistant_message": str(row["assistant_message"]),
                "metadata": decode_json(
                    row["metadata_json"],
                    expected_type=dict,
                    context=f"turns/{row['session_id']}/{row['turn_index']}",
                ),
            }

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.iter_turns(session_id))

    def next_turn_index(self, session_id: str) -> int:
        with self.storage.connect() as connection:
            value = connection.execute(
                "SELECT COALESCE(MAX(turn_index), 0) + 1 FROM turns WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
        return int(value)

    def list_sessions(self) -> list[str]:
        with self.storage.connect() as connection:
            rows = connection.execute(
                "SELECT session_id FROM sessions "
                "WHERE EXISTS (SELECT 1 FROM turns WHERE turns.session_id=sessions.session_id) "
                "ORDER BY session_id ASC"
            ).fetchall()
        return [str(row["session_id"]) for row in rows]

    def session_messages(
        self, session_id: str, *, limit: int = 16
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in self.list_turns(session_id):
            user = str(turn.get("user_message", "")).strip()
            assistant = str(turn.get("assistant_message", "")).strip()
            if user:
                messages.append({"role": "user", "content": user})
            if assistant:
                messages.append({"role": "assistant", "content": assistant})
        return messages[-limit:]

    def render_for_extraction(self, session_id: str) -> str:
        lines: list[str] = []
        for turn in self.list_turns(session_id):
            timestamp = str(turn.get("timestamp", ""))
            user = str(turn.get("user_message", "")).strip()
            assistant = str(turn.get("assistant_message", "")).strip()
            if user:
                lines.append(f"[{timestamp}] student: {user}")
            if assistant:
                lines.append(f"[{timestamp}] assistant: {assistant}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

    def clear_all(self) -> None:
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM sessions")
