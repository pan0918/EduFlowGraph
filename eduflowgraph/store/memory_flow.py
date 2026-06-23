import json
from pathlib import Path
from typing import Any, Iterator

from ..schemas import MemoryEvent, make_id, utc_now


MEMORY_EVENT_TYPES = {
    "episode_created",
    "episode_extraction_failed",
    "concept_extracted",
    "concept_merged",
    "concept_extraction_failed",
    "skill_evidence_added",
    "skill_distilled",
    "skill_distillation_failed",
    "skill_validated",
    "profile_updated",
}


class MemoryFlow:
    """Append-only journal of memory graph state changes.

    No raw conversation content is stored here — only references
    (session_id, turn_range, episode_id, etc.) and state deltas.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def emit(
        self,
        event_type: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            event_id=make_id("mf"),
            timestamp=utc_now(),
            event_type=event_type,
            session_id=session_id,
            payload=payload or {},
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def iter_events(
        self, event_type: str | None = None
    ) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type is None or obj.get("event_type") == event_type:
                yield obj

    def list_events(
        self, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        return list(self.iter_events(event_type))

    def clear(self) -> None:
        self.path.write_text("", encoding="utf-8")

    def replay_episodes(self) -> list[dict[str, Any]]:
        """Return all episode payloads from episode_created events."""
        episodes = []
        for event in self.iter_events("episode_created"):
            episode = event.get("payload", {}).get("episode")
            if isinstance(episode, dict):
                episodes.append(episode)
        return episodes

    def replay_concept_extractions(self) -> list[dict[str, Any]]:
        """Return all concept extraction payloads."""
        results = []
        for event in self.iter_events("concept_extracted"):
            payload = event.get("payload", {})
            if payload:
                results.append(payload)
        return results

    def replay_skill_distillations(self) -> list[dict[str, Any]]:
        """Return all skill distillation payloads."""
        results = []
        for event in self.iter_events("skill_distilled"):
            payload = event.get("payload", {})
            if payload:
                results.append(payload)
        return results

    def replay_skill_validations(self) -> list[dict[str, Any]]:
        """Return all skill validation payloads."""
        results = []
        for event in self.iter_events("skill_validated"):
            payload = event.get("payload", {})
            if payload:
                results.append(payload)
        return results
