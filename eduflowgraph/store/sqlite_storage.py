from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterator, TypeVar

import numpy as np


class StorageError(RuntimeError):
    """Base class for durable storage failures."""


class StorageDecodeError(StorageError):
    """Raised when persisted JSON or vector bytes cannot be decoded safely."""


class StorageIntegrityError(StorageError):
    """Raised when SQLite integrity checks fail."""


@dataclass(frozen=True)
class EncodedVector:
    blob: bytes
    dimensions: int


T = TypeVar("T")


def encode_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StorageDecodeError(f"JSON value is not serializable: {exc}") from exc


def decode_json(
    raw: str,
    *,
    expected_type: type[T],
    context: str,
) -> T:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise StorageDecodeError(f"Invalid JSON at {context}: {exc}") from exc
    if not isinstance(value, expected_type):
        raise StorageDecodeError(
            f"Invalid JSON type at {context}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def encode_vector(vector: list[float]) -> EncodedVector:
    try:
        values = np.asarray(vector, dtype="<f4")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StorageDecodeError(f"Embedding vector cannot be encoded: {exc}") from exc
    if values.ndim != 1:
        raise StorageDecodeError("Embedding vector must be one-dimensional")
    if values.size <= 0:
        raise StorageDecodeError("Embedding vector must not be empty")
    if not np.isfinite(values).all():
        raise StorageDecodeError("Embedding vector values must be finite")
    return EncodedVector(blob=values.tobytes(order="C"), dimensions=int(values.size))


def decode_vector(blob: bytes, dimensions: int) -> list[float]:
    if dimensions <= 0:
        raise StorageDecodeError("Embedding dimensions must be positive")
    expected_bytes = dimensions * 4
    if len(blob) != expected_bytes:
        raise StorageDecodeError(
            f"Embedding byte length mismatch: expected {expected_bytes}, got {len(blob)}"
        )
    values = np.frombuffer(blob, dtype="<f4", count=dimensions)
    if not np.isfinite(values).all():
        raise StorageDecodeError("Embedding vector values must be finite")
    return values.astype(float).tolist()


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, turn_index),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_turns_session_timestamp
ON turns(session_id, timestamp);

CREATE TABLE IF NOT EXISTS memory_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memory_events_type_sequence
ON memory_events(event_type, sequence);
CREATE INDEX IF NOT EXISTS idx_memory_events_session_sequence
ON memory_events(session_id, sequence);

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL CHECK (node_type IN ('concept', 'episode', 'skill')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_type_updated
ON nodes(node_type, updated_at);

CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target) REFERENCES nodes(node_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edges_source_type ON edges(source, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target_type ON edges(target, edge_type);

CREATE TABLE IF NOT EXISTS profile_models (
    model_name TEXT PRIMARY KEY CHECK (
        model_name IN ('learner_model', 'strategy_model', 'context_model')
    ),
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    revisions INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,
    model_name TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (model_name) REFERENCES profile_models(model_name)
);
CREATE INDEX IF NOT EXISTS idx_profile_changes_recent
ON profile_changes(change_id DESC);

CREATE TABLE IF NOT EXISTS embeddings (
    node_id TEXT PRIMARY KEY,
    vector_blob BLOB NOT NULL,
    dimensions INTEGER NOT NULL,
    dtype TEXT NOT NULL DEFAULT 'float32-le',
    provider TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_embeddings_signature
ON embeddings(provider, model_id, dimensions);
"""


class SQLiteStorage:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)
        self._active_connection: ContextVar[sqlite3.Connection | None] = ContextVar(
            f"eduflow_sqlite_connection_{id(self)}",
            default=None,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, self.SCHEMA_VERSION}:
                raise StorageIntegrityError(
                    f"Unsupported SQLite schema version {version}; "
                    f"expected {self.SCHEMA_VERSION}"
                )
            if version == 0:
                connection.executescript(SCHEMA_V1)
                connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            connection.executemany(
                "INSERT OR IGNORE INTO profile_models"
                "(model_name, summary, updated_at, revisions) VALUES (?, '', NULL, 0)",
                [
                    ("learner_model",),
                    ("strategy_model",),
                    ("context_model",),
                ],
            )
            connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        active = self._active_connection.get()
        if active is not None:
            yield active
            return
        connection = self.connect()
        token = self._active_connection.set(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._active_connection.reset(token)
            connection.close()

    def schema_version(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def journal_mode(self) -> str:
        with self.connect() as connection:
            return str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def quick_check(self) -> str:
        with self.connect() as connection:
            result = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        if result.lower() != "ok":
            raise StorageIntegrityError(f"SQLite quick_check failed: {result}")
        return result.lower()

    def health(self) -> dict[str, Any]:
        wal_path = Path(f"{self.path}-wal")
        return {
            "backend": "sqlite",
            "schema_version": self.schema_version(),
            "journal_mode": self.journal_mode(),
            "database_size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "wal_size_bytes": wal_path.stat().st_size if wal_path.exists() else 0,
            "integrity": self.quick_check(),
        }
