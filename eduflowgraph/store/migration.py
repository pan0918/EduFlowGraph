from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from .profile_store import LearnerProfileStore
from .skill_adaptation_store import LEGACY_MODEL_NAME, SkillAdaptationStore
from .sqlite_conversation_log import SQLiteConversationLog
from .sqlite_graph_store import SQLiteGraphStore
from .sqlite_memory_flow import SQLiteMemoryFlow, strip_embedding_vectors
from .sqlite_profile_store import SQLiteLearnerProfileStore
from .sqlite_skill_adaptation_store import SQLiteSkillAdaptationStore
from .sqlite_storage import SQLiteStorage, encode_json, encode_vector


class MigrationValidationError(RuntimeError):
    """Raised before switchover when legacy data is incomplete or inconsistent."""


@dataclass
class LegacySnapshot:
    turns: list[dict[str, Any]]
    events: list[dict[str, Any]]
    nodes: dict[str, dict[str, Any]]
    edges: list[dict[str, Any]]
    profile: dict[str, Any]
    skill_adaptation: dict[str, Any]

    def counts(self) -> dict[str, int]:
        return {
            "sessions": len({str(turn["session_id"]) for turn in self.turns}),
            "turns": len(self.turns),
            "events": len(self.events),
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "embeddings": sum(
                1
                for node in self.nodes.values()
                if node.get("retrieval", {}).get("embedding_vector")
            ),
            "profile_revisions": int(self.profile.get("revision_count", 0)),
        }


def _read_json(path: Path, default: Any, expected_type: type) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MigrationValidationError(f"{path.name}: invalid JSON: {exc}") from exc
    if not isinstance(value, expected_type):
        raise MigrationValidationError(
            f"{path.name}: expected {expected_type.__name__}, got {type(value).__name__}"
        )
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    values: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MigrationValidationError(
                f"{path.name}:{line_number}: invalid JSON: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise MigrationValidationError(
                f"{path.name}:{line_number}: expected object"
            )
        values.append(value)
    return values


def load_legacy_snapshot(data_dir: Path) -> LegacySnapshot:
    data_dir = Path(data_dir)
    turns: list[dict[str, Any]] = []
    conversations_dir = data_dir / "conversations"
    if conversations_dir.exists():
        for path in sorted(conversations_dir.glob("*.jsonl")):
            turns.extend(_read_jsonl(path))
    events = _read_jsonl(data_dir / "memory_flow.jsonl")
    nodes = _read_json(data_dir / "graph_nodes.json", {}, dict)
    edges = _read_json(data_dir / "graph_edges.json", [], list)
    raw_profile = _read_json(data_dir / "learner_profile.json", {}, dict)
    normalizer = LearnerProfileStore(data_dir)
    profile = normalizer._normalize_snapshot(raw_profile) if raw_profile else normalizer.empty_snapshot()
    skill_adaptation = _load_legacy_skill_adaptation(data_dir, raw_profile)
    snapshot = LegacySnapshot(
        turns=turns,
        events=events,
        nodes={str(key): value for key, value in nodes.items()},
        edges=edges,
        profile=profile,
        skill_adaptation=skill_adaptation,
    )
    validate_legacy_snapshot(snapshot)
    return snapshot


def _load_legacy_skill_adaptation(
    data_dir: Path,
    raw_profile: dict[str, Any],
) -> dict[str, Any]:
    store = SkillAdaptationStore(data_dir)
    raw_skill = _read_json(data_dir / "skill_adaptation.json", {}, dict)
    if raw_skill:
        return store._normalize_snapshot(raw_skill)

    models = raw_profile.get("models") if isinstance(raw_profile, dict) else None
    entry = models.get(LEGACY_MODEL_NAME) if isinstance(models, dict) else None
    if not isinstance(entry, dict):
        return store.empty_snapshot()
    summary = str(entry.get("summary", "")).strip()
    if not summary:
        return store.empty_snapshot()
    recent = raw_profile.get("recent_changes", [])
    if not isinstance(recent, list):
        recent = []
    return store._normalize_snapshot(
        {
            "summary": summary,
            "updated_at": entry.get("updated_at"),
            "revisions": int(entry.get("revisions", 0) or 0),
            "recent_changes": [
                {
                    "at": change.get("at"),
                    "note": str(change.get("note", "")),
                }
                for change in recent
                if isinstance(change, dict)
                and change.get("model") == LEGACY_MODEL_NAME
                and str(change.get("note", "")).strip()
            ],
            "health": {"status": "ok", "message": ""},
        }
    )


def validate_legacy_snapshot(snapshot: LegacySnapshot) -> None:
    turn_keys: set[tuple[str, int]] = set()
    for turn in snapshot.turns:
        try:
            key = (str(turn["session_id"]), int(turn["turn_index"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise MigrationValidationError(f"invalid Turn record: {turn!r}") from exc
        if key in turn_keys:
            raise MigrationValidationError(f"duplicate Turn key: {key}")
        turn_keys.add(key)

    event_ids: set[str] = set()
    for event in snapshot.events:
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            raise MigrationValidationError("memory event is missing event_id")
        if event_id in event_ids:
            raise MigrationValidationError(f"duplicate event_id: {event_id}")
        event_ids.add(event_id)

    for node_id, node in snapshot.nodes.items():
        if not isinstance(node, dict):
            raise MigrationValidationError(f"node {node_id} is not an object")
        if str(node.get("node_id") or node.get("episode_id") or node_id) != node_id:
            raise MigrationValidationError(f"node key/id mismatch: {node_id}")
        vector = node.get("retrieval", {}).get("embedding_vector", [])
        if vector:
            encoded = encode_vector(list(vector))
            metadata_dimensions = int(
                node.get("retrieval", {})
                .get("embedding_metadata", {})
                .get("dimensions", encoded.dimensions)
                or encoded.dimensions
            )
            if metadata_dimensions != encoded.dimensions:
                raise MigrationValidationError(
                    f"embedding dimension mismatch for {node_id}: "
                    f"metadata={metadata_dimensions}, actual={encoded.dimensions}"
                )

    edge_ids: set[str] = set()
    node_ids = set(snapshot.nodes)
    for edge in snapshot.edges:
        if not isinstance(edge, dict):
            raise MigrationValidationError("graph edge is not an object")
        edge_id = str(edge.get("edge_id", "")).strip()
        if not edge_id or edge_id in edge_ids:
            raise MigrationValidationError(f"missing or duplicate edge_id: {edge_id}")
        edge_ids.add(edge_id)
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source not in node_ids or target not in node_ids:
            raise MigrationValidationError(
                f"dangling edge {edge_id}: {source} -> {target}"
            )

    for event in snapshot.events:
        payload = event.get("payload", {})
        if event.get("event_type") == "episode_created":
            episode = payload.get("episode") if isinstance(payload, dict) else None
            episode_id = str((episode or {}).get("node_id") or (episode or {}).get("episode_id") or "")
            if episode_id and episode_id not in node_ids:
                raise MigrationValidationError(
                    f"MemoryFlow episode {episode_id} is absent from graph snapshot"
                )


def _import_snapshot(snapshot: LegacySnapshot, database_path: Path) -> None:
    storage = SQLiteStorage(database_path)
    with storage.transaction() as connection:
        session_times: dict[str, tuple[str, str]] = {}
        for turn in snapshot.turns:
            session_id = str(turn["session_id"])
            timestamp = str(turn.get("timestamp", ""))
            if session_id not in session_times:
                session_times[session_id] = (timestamp, timestamp)
            else:
                first, last = session_times[session_id]
                session_times[session_id] = (min(first, timestamp), max(last, timestamp))
        connection.executemany(
            "INSERT INTO sessions(session_id, created_at, updated_at) VALUES (?, ?, ?)",
            [(session_id, times[0], times[1]) for session_id, times in session_times.items()],
        )
        connection.executemany(
            "INSERT INTO turns(session_id, turn_index, timestamp, user_message, "
            "assistant_message, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    str(turn["session_id"]),
                    int(turn["turn_index"]),
                    str(turn.get("timestamp", "")),
                    str(turn.get("user_message", "")),
                    str(turn.get("assistant_message", "")),
                    encode_json(turn.get("metadata", {})),
                )
                for turn in snapshot.turns
            ],
        )
        connection.executemany(
            "INSERT INTO memory_events(event_id, timestamp, event_type, session_id, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    str(event["event_id"]),
                    str(event.get("timestamp", "")),
                    str(event.get("event_type", "")),
                    str(event.get("session_id", "")),
                    encode_json(strip_embedding_vectors(event.get("payload", {}))),
                )
                for event in snapshot.events
            ],
        )

    graph = SQLiteGraphStore(storage)
    graph.nodes = {node_id: dict(node) for node_id, node in snapshot.nodes.items()}
    graph.edges = [dict(edge) for edge in snapshot.edges]
    graph.save()
    SQLiteLearnerProfileStore(storage).save(snapshot.profile)
    SQLiteSkillAdaptationStore(storage).save(snapshot.skill_adaptation)


def _without_vectors(value: Any) -> Any:
    return strip_embedding_vectors(value)


def verify_migration(data_dir: Path, database_path: Path) -> dict[str, Any]:
    snapshot = load_legacy_snapshot(Path(data_dir))
    storage = SQLiteStorage(Path(database_path))
    log = SQLiteConversationLog(storage)
    flow = SQLiteMemoryFlow(storage)
    graph = SQLiteGraphStore(storage)
    profile = SQLiteLearnerProfileStore(storage).load()
    skill_adaptation = SQLiteSkillAdaptationStore(storage).load()

    sqlite_turns = [
        turn
        for session_id in log.list_sessions()
        for turn in log.list_turns(session_id)
    ]
    legacy_turns = sorted(
        snapshot.turns,
        key=lambda item: (str(item["session_id"]), int(item["turn_index"])),
    )
    if sqlite_turns != legacy_turns:
        raise MigrationValidationError("Turn verification mismatch")
    if flow.list_events() != [
        {
            "event_id": str(event["event_id"]),
            "timestamp": str(event.get("timestamp", "")),
            "event_type": str(event.get("event_type", "")),
            "session_id": str(event.get("session_id", "")),
            "payload": _without_vectors(event.get("payload", {})),
        }
        for event in snapshot.events
    ]:
        raise MigrationValidationError("MemoryEvent verification mismatch")

    if _without_vectors(graph.nodes) != _without_vectors(snapshot.nodes):
        raise MigrationValidationError("node payload verification mismatch")
    sqlite_edges = sorted(graph.edges, key=lambda edge: str(edge.get("edge_id", "")))
    legacy_edges = sorted(snapshot.edges, key=lambda edge: str(edge.get("edge_id", "")))
    if sqlite_edges != legacy_edges:
        raise MigrationValidationError("edge verification mismatch")
    for node_id, legacy_node in snapshot.nodes.items():
        legacy_vector = legacy_node.get("retrieval", {}).get("embedding_vector", [])
        sqlite_vector = graph.nodes[node_id].get("retrieval", {}).get("embedding_vector", [])
        if legacy_vector and not np.allclose(
            np.asarray(sqlite_vector, dtype=float),
            np.asarray(legacy_vector, dtype=float),
            rtol=1e-6,
            atol=1e-7,
        ):
            raise MigrationValidationError(f"embedding verification mismatch: {node_id}")

    if profile["models"] != snapshot.profile["models"]:
        raise MigrationValidationError("profile model verification mismatch")
    if profile["recent_changes"] != snapshot.profile["recent_changes"]:
        raise MigrationValidationError("profile changes verification mismatch")
    if profile["revision_count"] != snapshot.profile["revision_count"]:
        raise MigrationValidationError("profile revision verification mismatch")
    if skill_adaptation != snapshot.skill_adaptation:
        raise MigrationValidationError("skill adaptation verification mismatch")
    return {"status": "ok", "counts": snapshot.counts()}


def migrate_legacy_storage(
    data_dir: Path,
    database_path: Path,
    *,
    mode: str,
    replace_empty: bool = False,
) -> dict[str, Any]:
    if mode not in {"dry-run", "apply", "verify"}:
        raise ValueError("mode must be dry-run, apply, or verify")
    data_dir = Path(data_dir)
    database_path = Path(database_path)
    if mode == "verify":
        if not database_path.exists():
            raise MigrationValidationError(f"database does not exist: {database_path}")
        return verify_migration(data_dir, database_path)

    replacing_empty = False
    if mode == "apply" and database_path.exists():
        if not replace_empty:
            raise MigrationValidationError(f"destination already exists: {database_path}")
        try:
            existing = SQLiteStorage(database_path)
            with existing.connect() as connection:
                counts = connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM sessions), "
                    "(SELECT COUNT(*) FROM turns), "
                    "(SELECT COUNT(*) FROM memory_events), "
                    "(SELECT COUNT(*) FROM nodes), "
                    "(SELECT COUNT(*) FROM edges), "
                    "(SELECT COALESCE(SUM(revisions), 0) FROM profile_models), "
                    "(SELECT COALESCE(SUM(revisions), 0) FROM skill_adaptation)"
                ).fetchone()
            if any(int(value) != 0 for value in counts):
                raise MigrationValidationError(
                    f"destination database is not empty: {database_path}"
                )
            replacing_empty = True
        except MigrationValidationError:
            raise
        except Exception as exc:
            raise MigrationValidationError(
                f"destination is not a valid empty EduFlowGraph database: {database_path}"
            ) from exc
    snapshot = load_legacy_snapshot(data_dir)
    report = {"status": "ok", "mode": mode, "counts": snapshot.counts()}
    if mode == "dry-run":
        return report

    temporary_path = Path(f"{database_path}.tmp")
    if temporary_path.exists():
        raise MigrationValidationError(f"temporary destination already exists: {temporary_path}")
    _import_snapshot(snapshot, temporary_path)
    verify_migration(data_dir, temporary_path)
    storage = SQLiteStorage(temporary_path)
    with storage.connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    if replacing_empty:
        existing = SQLiteStorage(database_path)
        with existing.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        for suffix in ("-wal", "-shm"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    os.replace(temporary_path, database_path)
    for suffix in ("-wal", "-shm"):
        Path(f"{temporary_path}{suffix}").unlink(missing_ok=True)
    SQLiteStorage(database_path)
    return report


def export_sqlite_storage(
    database_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    database_path = Path(database_path)
    output_dir = Path(output_dir)
    if not database_path.exists():
        raise MigrationValidationError(f"database does not exist: {database_path}")
    if output_dir.exists():
        raise MigrationValidationError(f"export destination already exists: {output_dir}")
    temporary_dir = Path(f"{output_dir}.tmp")
    if temporary_dir.exists():
        raise MigrationValidationError(
            f"temporary export destination already exists: {temporary_dir}"
        )

    storage = SQLiteStorage(database_path)
    log = SQLiteConversationLog(storage)
    flow = SQLiteMemoryFlow(storage)
    graph = SQLiteGraphStore(storage)
    profile = SQLiteLearnerProfileStore(storage).load()
    skill_adaptation = SQLiteSkillAdaptationStore(storage).load()

    conversations_dir = temporary_dir / "conversations"
    conversations_dir.mkdir(parents=True)
    for session_id in log.list_sessions():
        safe_session_id = session_id.replace("/", "_").replace("\\", "_")
        turns = log.list_turns(session_id)
        (conversations_dir / f"{safe_session_id}.jsonl").write_text(
            "".join(
                json.dumps(turn, ensure_ascii=False, allow_nan=False) + "\n"
                for turn in turns
            ),
            encoding="utf-8",
        )
    (temporary_dir / "memory_flow.jsonl").write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
            for event in flow.list_events()
        ),
        encoding="utf-8",
    )
    (temporary_dir / "graph_nodes.json").write_text(
        json.dumps(graph.nodes, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    (temporary_dir / "graph_edges.json").write_text(
        json.dumps(graph.edges, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    (temporary_dir / "learner_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (temporary_dir / "skill_adaptation.json").write_text(
        json.dumps(skill_adaptation, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    exported = load_legacy_snapshot(temporary_dir)
    expected_counts = {
        "sessions": len(log.list_sessions()),
        "turns": sum(len(log.list_turns(session_id)) for session_id in log.list_sessions()),
        "events": len(flow.list_events()),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "embeddings": sum(
            1
            for node in graph.nodes.values()
            if node.get("retrieval", {}).get("embedding_vector")
        ),
        "profile_revisions": int(profile.get("revision_count", 0)),
    }
    if exported.counts() != expected_counts:
        raise MigrationValidationError(
            f"export verification mismatch: expected {expected_counts}, "
            f"got {exported.counts()}"
        )
    os.replace(temporary_dir, output_dir)
    return {"status": "ok", "counts": expected_counts}
