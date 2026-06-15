import json
from pathlib import Path
from typing import Any, Iterator

from .schemas import Event, make_id, utc_now


RAW_EVENT_TYPES = {"user_message", "assistant_message"}


class DataFlowStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append_event(
        self,
        *,
        session_id: str,
        turn_index: int,
        actor: str,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        segment_id: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        event = Event(
            event_id=make_id("event"),
            stream_index=self.next_stream_index(),
            session_id=session_id,
            turn_index=turn_index,
            timestamp=utc_now(),
            actor=actor,
            event_type=event_type,
            content=content,
            segment_id=segment_id,
            causation_id=causation_id,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def append(
        self,
        session_id: str,
        turn_index: int,
        actor: str,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        return self.append_event(
            session_id=session_id,
            turn_index=turn_index,
            actor=actor,
            event_type=event_type,
            content=content,
            metadata=metadata,
        )

    def iter_events(self, session_id: str | None = None) -> Iterator[dict[str, Any]]:
        for index, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            event = self._normalize_event(raw, fallback_stream_index=index)
            if session_id is None or event["session_id"] == session_id:
                yield event

    def list_events(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return list(self.iter_events(session_id))

    def clear(self) -> None:
        self.path.write_text("", encoding="utf-8")

    def delete_event(self, event_id: str) -> int:
        target_id = str(event_id).strip()
        if not target_id:
            return 0
        events = self.list_events()
        segment_ids_to_remove: set[str] = set()
        for event in events:
            if event["event_id"] == target_id and event.get("segment_id"):
                segment_ids_to_remove.add(str(event["segment_id"]))
            refs = set(event.get("metadata", {}).get("event_refs", []))
            if event["event_type"] == "segment_closed" and target_id in refs:
                segment_id = str(event.get("segment_id") or "")
                if segment_id:
                    segment_ids_to_remove.add(segment_id)

        kept: list[dict[str, Any]] = []
        removed = 0
        for event in events:
            remove = event["event_id"] == target_id
            if event.get("segment_id") in segment_ids_to_remove:
                remove = True
            if event["event_type"] == "segment_closed" and event.get("segment_id") in segment_ids_to_remove:
                remove = True
            if remove:
                removed += 1
                continue
            kept.append(event)

        with self.path.open("w", encoding="utf-8") as handle:
            for event in kept:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return removed

    def events_by_ids(self, event_ids: list[str]) -> list[dict[str, Any]]:
        wanted = {str(event_id) for event_id in event_ids if str(event_id).strip()}
        if not wanted:
            return []
        return [event for event in self.iter_events() if event["event_id"] in wanted]

    def next_stream_index(self) -> int:
        last = 0
        for event in self.iter_events():
            last = max(last, int(event.get("stream_index", 0) or 0))
        return last + 1

    def next_turn_index(self, session_id: str) -> int:
        return len([event for event in self.list_events(session_id) if event["actor"] == "student"]) + 1

    def rebuild_open_buffers(self) -> dict[str, list[dict[str, Any]]]:
        open_buffers: dict[str, list[dict[str, Any]]] = {}
        for event in self.iter_events():
            if event["event_type"] in RAW_EVENT_TYPES:
                open_buffers.setdefault(event["session_id"], []).append(event)
                continue
            if event["event_type"] != "segment_closed":
                continue
            event_refs = set(event.get("metadata", {}).get("event_refs", []))
            session_id = event["session_id"]
            open_buffers[session_id] = [
                item
                for item in open_buffers.get(session_id, [])
                if item["event_id"] not in event_refs
            ]
        return open_buffers

    def replay_segments(self) -> list[dict[str, Any]]:
        raw_events: dict[str, dict[str, Any]] = {}
        boundary_events: dict[str, dict[str, Any]] = {}
        segments: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        for event in self.iter_events():
            if event["event_type"] in RAW_EVENT_TYPES:
                raw_events[event["event_id"]] = event
                continue
            if event["event_type"] == "boundary_evaluated":
                boundary_events[event["event_id"]] = event
                continue
            if event["event_type"] == "segment_closed":
                segment_id = event.get("segment_id") or make_id("segment")
                metadata = event.get("metadata", {})
                boundary_event = boundary_events.get(event.get("causation_id", ""))
                segment = {
                    "segment_id": segment_id,
                    "session_id": event["session_id"],
                    "closed_event": event,
                    "decision": metadata.get("decision")
                    or (boundary_event.get("metadata", {}).get("decision") if boundary_event else {})
                    or {},
                    "events": [
                        raw_events[event_id]
                        for event_id in metadata.get("event_refs", [])
                        if event_id in raw_events
                    ],
                }
                segments[segment_id] = segment
                order.append(segment_id)
                continue
            segment_id = event.get("segment_id")
            if not segment_id or segment_id not in segments:
                continue
            segments[segment_id][event["event_type"]] = event

        return [segments[segment_id] for segment_id in order]

    def _normalize_event(
        self,
        raw: dict[str, Any],
        *,
        fallback_stream_index: int,
    ) -> dict[str, Any]:
        return {
            "event_id": raw.get("event_id") or make_id("event"),
            "stream_index": int(raw.get("stream_index") or fallback_stream_index),
            "timestamp": raw.get("timestamp") or utc_now(),
            "session_id": raw.get("session_id") or "session",
            "turn_index": int(raw.get("turn_index") or 0),
            "segment_id": raw.get("segment_id"),
            "actor": raw.get("actor") or "system",
            "event_type": raw.get("event_type") or "unknown",
            "content": raw.get("content") or "",
            "metadata": raw.get("metadata") or {},
            "causation_id": raw.get("causation_id"),
            "correlation_id": raw.get("correlation_id"),
        }
