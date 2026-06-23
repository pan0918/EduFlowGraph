from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"


EPISODE_TYPES = {
    "concept_explanation",
    "problem_solving",
    "misconception_diagnosis",
    "assessment",
    "review",
    "planning",
    "other",
}

OUTCOME_STATUSES = {"success", "partial_success", "failed", "unresolved"}

INITIAL_STATES = {"low", "partial", "mixed", "unclear", "unknown"}

STRUCTURAL_ROLES = {"main", "supporting", "context"}
LEARNER_STATES = {"confused", "clarified", "neutral"}


@dataclass
class Turn:
    """One complete user-assistant exchange persisted in ConversationLog."""
    turn_index: int
    timestamp: str
    session_id: str
    user_message: str
    assistant_message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryEvent:
    """One state-change entry persisted in MemoryFlow."""
    event_id: str
    timestamp: str
    event_type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
