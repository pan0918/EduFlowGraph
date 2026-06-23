from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from ..schemas import utc_now
from .graph_store import GraphStore
from .sqlite_storage import (
    SQLiteStorage,
    StorageDecodeError,
    decode_json,
    decode_vector,
    encode_json,
    encode_vector,
)


class SQLiteGraphStore(GraphStore):
    """GraphStore-compatible cache persisted in normalized SQLite tables."""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage
        self.nodes_path = storage.path
        self.edges_path = storage.path
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        with self.storage.connect() as connection:
            node_rows = connection.execute(
                "SELECT n.node_id, n.payload_json, e.vector_blob, e.dimensions, "
                "e.dtype, e.provider, e.model_id, e.created_at AS embedding_created_at "
                "FROM nodes n LEFT JOIN embeddings e ON e.node_id=n.node_id "
                "ORDER BY n.created_at ASC, n.node_id ASC"
            ).fetchall()
            edge_rows = connection.execute(
                "SELECT edge_id, edge_type, source, target, weight, evidence, metadata_json "
                "FROM edges ORDER BY created_at ASC, edge_id ASC"
            ).fetchall()

        for row in node_rows:
            node_id = str(row["node_id"])
            node = decode_json(
                row["payload_json"],
                expected_type=dict,
                context=f"nodes/{node_id}",
            )
            if row["vector_blob"] is not None:
                if str(row["dtype"]) != "float32-le":
                    raise StorageDecodeError(
                        f"Unsupported embedding dtype at embeddings/{node_id}: {row['dtype']}"
                    )
                retrieval = dict(node.get("retrieval", {}))
                retrieval["embedding_vector"] = decode_vector(
                    bytes(row["vector_blob"]), int(row["dimensions"])
                )
                metadata = dict(retrieval.get("embedding_metadata", {}))
                metadata.update({
                    "provider": str(row["provider"]),
                    "model_id": str(row["model_id"]),
                    "dimensions": int(row["dimensions"]),
                    "created_at": str(row["embedding_created_at"]),
                })
                retrieval["embedding_metadata"] = metadata
                node["retrieval"] = retrieval
            nodes[node_id] = node

        for row in edge_rows:
            edge_id = str(row["edge_id"])
            edges.append({
                "edge_id": edge_id,
                "edge_type": str(row["edge_type"]),
                "source": str(row["source"]),
                "target": str(row["target"]),
                "weight": float(row["weight"]),
                "evidence": str(row["evidence"]),
                "metadata": decode_json(
                    row["metadata_json"],
                    expected_type=dict,
                    context=f"edges/{edge_id}",
                ),
            })

        self.nodes = nodes
        self.edges = edges

    def save(self) -> None:
        now = utc_now()
        node_ids = set(self.nodes)
        edge_ids = {
            str(edge.get("edge_id", "")).strip()
            for edge in self.edges
            if str(edge.get("edge_id", "")).strip()
        }
        with self.storage.transaction() as connection:
            for node_id, source_node in self.nodes.items():
                node = deepcopy(source_node)
                retrieval = dict(node.get("retrieval", {}))
                vector = retrieval.pop("embedding_vector", None)
                if retrieval or "retrieval" in node:
                    node["retrieval"] = retrieval
                metadata = node.get("metadata", {})
                extraction_metadata = node.get("extraction_metadata", {})
                created_at = str(
                    metadata.get("created_at")
                    or extraction_metadata.get("created_at")
                    or now
                )
                updated_at = str(metadata.get("updated_at") or now)
                connection.execute(
                    "INSERT INTO nodes(node_id, node_type, payload_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(node_id) DO UPDATE SET "
                    "node_type=excluded.node_type, payload_json=excluded.payload_json, "
                    "updated_at=excluded.updated_at",
                    (
                        node_id,
                        str(node.get("node_type", "")),
                        encode_json(node),
                        created_at,
                        updated_at,
                    ),
                )
                if vector:
                    encoded = encode_vector(list(vector))
                    embedding_metadata = retrieval.get("embedding_metadata", {})
                    embedding_text = str(retrieval.get("embedding_text", ""))
                    content_hash = hashlib.sha256(
                        embedding_text.encode("utf-8")
                    ).hexdigest()
                    connection.execute(
                        "INSERT INTO embeddings(node_id, vector_blob, dimensions, dtype, "
                        "provider, model_id, content_hash, created_at) "
                        "VALUES (?, ?, ?, 'float32-le', ?, ?, ?, ?) "
                        "ON CONFLICT(node_id) DO UPDATE SET "
                        "vector_blob=excluded.vector_blob, dimensions=excluded.dimensions, "
                        "dtype=excluded.dtype, provider=excluded.provider, "
                        "model_id=excluded.model_id, content_hash=excluded.content_hash, "
                        "created_at=excluded.created_at",
                        (
                            node_id,
                            encoded.blob,
                            encoded.dimensions,
                            str(embedding_metadata.get("provider", "")),
                            str(embedding_metadata.get("model_id", "")),
                            content_hash,
                            str(embedding_metadata.get("created_at") or now),
                        ),
                    )
                else:
                    connection.execute("DELETE FROM embeddings WHERE node_id=?", (node_id,))

            for edge in self.edges:
                edge_id = str(edge.get("edge_id", "")).strip()
                if not edge_id:
                    continue
                metadata = dict(edge.get("metadata", {}))
                created_at = str(metadata.get("created_at") or now)
                connection.execute(
                    "INSERT INTO edges(edge_id, edge_type, source, target, weight, evidence, "
                    "metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(edge_id) DO UPDATE SET "
                    "edge_type=excluded.edge_type, source=excluded.source, target=excluded.target, "
                    "weight=excluded.weight, evidence=excluded.evidence, "
                    "metadata_json=excluded.metadata_json, updated_at=excluded.updated_at",
                    (
                        edge_id,
                        str(edge.get("edge_type", "edge")),
                        str(edge.get("source", "")),
                        str(edge.get("target", "")),
                        float(edge.get("weight", 0.0)),
                        str(edge.get("evidence", "")),
                        encode_json(metadata),
                        created_at,
                        now,
                    ),
                )

            existing_edge_ids = {
                str(row[0])
                for row in connection.execute("SELECT edge_id FROM edges").fetchall()
            }
            stale_edges = existing_edge_ids - edge_ids
            connection.executemany(
                "DELETE FROM edges WHERE edge_id=?",
                [(edge_id,) for edge_id in stale_edges],
            )
            existing_node_ids = {
                str(row[0])
                for row in connection.execute("SELECT node_id FROM nodes").fetchall()
            }
            stale_nodes = existing_node_ids - node_ids
            connection.executemany(
                "DELETE FROM nodes WHERE node_id=?",
                [(node_id,) for node_id in stale_nodes],
            )
