from __future__ import annotations

from typing import Any, Iterator

from ..schemas import MemoryEvent, make_id, utc_now
from .sqlite_storage import SQLiteStorage, decode_json, encode_json


def strip_embedding_vectors(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): strip_embedding_vectors(item)
            for key, item in value.items()
            if str(key) != "embedding_vector"
        }
    if isinstance(value, list):
        return [strip_embedding_vectors(item) for item in value]
    if isinstance(value, tuple):
        return [strip_embedding_vectors(item) for item in value]
    return value


class SQLiteMemoryFlow:
    """Append-only SQLite journal with legacy-compatible event payloads."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def emit(
        self,
        event_type: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        clean_payload = strip_embedding_vectors(payload or {})
        event = MemoryEvent(
            event_id=make_id("mf"),
            timestamp=utc_now(),
            event_type=event_type,
            session_id=session_id,
            payload=clean_payload,
        )
        with self.storage.transaction() as connection:
            connection.execute(
                "INSERT INTO memory_events(event_id, timestamp, event_type, session_id, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.timestamp,
                    event.event_type,
                    event.session_id,
                    encode_json(event.payload),
                ),
            )
        return event

    def iter_events(self, event_type: str | None = None) -> Iterator[dict[str, Any]]:
        query = (
            "SELECT event_id, timestamp, event_type, session_id, payload_json "
            "FROM memory_events"
        )
        params: tuple[Any, ...] = ()
        if event_type is not None:
            query += " WHERE event_type=?"
            params = (event_type,)
        query += " ORDER BY sequence ASC"
        with self.storage.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        for row in rows:
            yield {
                "event_id": str(row["event_id"]),
                "timestamp": str(row["timestamp"]),
                "event_type": str(row["event_type"]),
                "session_id": str(row["session_id"]),
                "payload": decode_json(
                    row["payload_json"],
                    expected_type=dict,
                    context=f"memory_events/{row['event_id']}",
                ),
            }

    def list_events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        return list(self.iter_events(event_type))

    def clear(self) -> None:
        with self.storage.transaction() as connection:
            connection.execute("DELETE FROM memory_events")

    def replay_episodes(self) -> list[dict[str, Any]]:
        return [
            episode
            for event in self.iter_events("episode_created")
            for episode in [event.get("payload", {}).get("episode")]
            if isinstance(episode, dict)
        ]

    def replay_concept_extractions(self) -> list[dict[str, Any]]:
        return [
            payload
            for event in self.iter_events("concept_extracted")
            for payload in [event.get("payload", {})]
            if payload
        ]

    def replay_skill_distillations(self) -> list[dict[str, Any]]:
        return [
            payload
            for event in self.iter_events("skill_distilled")
            for payload in [event.get("payload", {})]
            if payload
        ]

    def replay_skill_validations(self) -> list[dict[str, Any]]:
        return [
            payload
            for event in self.iter_events("skill_validated")
            for payload in [event.get("payload", {})]
            if payload
        ]
