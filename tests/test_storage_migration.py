from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.test_sqlite_storage import sample_episode


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def make_legacy_data(root: Path) -> None:
    conversations = root / "conversations"
    conversations.mkdir(parents=True, exist_ok=True)
    turn = {
        "turn_index": 1,
        "timestamp": "2026-06-23T00:00:00+00:00",
        "session_id": "session_a",
        "user_message": "为什么？",
        "assistant_message": "因为条件方向不同。",
        "metadata": {"usage": {"total_tokens": 12}},
    }
    (conversations / "session_a.jsonl").write_text(
        json.dumps(turn, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    episode = sample_episode()
    concept = {
        "concept_id": "concept_conditional_probability",
        "node_id": "concept_conditional_probability",
        "node_type": "concept",
        "name": "Conditional probability",
        "aliases": ["条件概率"],
        "description": "给定条件下事件发生的概率。",
        "retrieval": {
            "embedding_text": "Conditional probability 条件概率",
            "keywords": ["条件概率"],
            "embedding_vector": [1.0, 0.0, 0.0, 0.0],
            "embedding_metadata": {
                "provider": "mock",
                "model_id": "mock-embedding",
                "dimensions": 4,
                "created_at": "2026-06-23T00:00:02+00:00",
            },
        },
        "metadata": {
            "created_at": "2026-06-23T00:00:02+00:00",
            "updated_at": "2026-06-23T00:00:02+00:00",
        },
    }
    edge = {
        "edge_id": "edge_episode_1_concept_conditional_probability",
        "edge_type": "episode_concept",
        "source": "episode_1",
        "target": "concept_conditional_probability",
        "weight": 0.95,
        "evidence": "本轮核心概念",
        "metadata": {
            "structural_role": "main",
            "created_at": "2026-06-23T00:00:02+00:00",
        },
    }
    write_json(root / "graph_nodes.json", {"episode_1": episode, concept["node_id"]: concept})
    write_json(root / "graph_edges.json", [edge])
    events = [
        {
            "event_id": "mf_episode_1",
            "timestamp": "2026-06-23T00:00:02+00:00",
            "event_type": "episode_created",
            "session_id": "session_a",
            "payload": {"episode": episode, "segment_id": "segment_1"},
        },
        {
            "event_id": "mf_concept_1",
            "timestamp": "2026-06-23T00:00:03+00:00",
            "event_type": "concept_extracted",
            "session_id": "session_a",
            "payload": {"episode_id": "episode_1", "concepts": [concept], "edges": [edge]},
        },
    ]
    (root / "memory_flow.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    write_json(root / "learner_profile.json", {
        "models": {
            "learner_model": {
                "summary": "近期存在方向混淆。",
                "updated_at": "2026-06-23T00:00:04+00:00",
                "revisions": 1,
            },
            "strategy_model": {"summary": "", "updated_at": None, "revisions": 0},
            "context_model": {
                "summary": "当前正在复习。",
                "updated_at": "2026-06-23T00:00:05+00:00",
                "revisions": 1,
            },
        },
        "recent_changes": [
            {
                "at": "2026-06-23T00:00:05+00:00",
                "model": "context_model",
                "note": "更新情境",
            }
        ],
        "updated_at": "2026-06-23T00:00:05+00:00",
        "revision_count": 2,
        "health": {"status": "ok", "message": ""},
    })


class StorageMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        make_legacy_data(self.data_dir)
        self.database_path = self.data_dir / "eduflowgraph.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_validates_without_creating_database(self):
        from EduFlowGraph.store.migration import migrate_legacy_storage

        report = migrate_legacy_storage(
            self.data_dir,
            self.database_path,
            mode="dry-run",
        )

        self.assertFalse(self.database_path.exists())
        self.assertEqual(report["counts"], {
            "sessions": 1,
            "turns": 1,
            "events": 2,
            "nodes": 2,
            "edges": 1,
            "embeddings": 2,
            "profile_revisions": 2,
        })

    def test_apply_preserves_contract_and_removes_duplicate_vectors(self):
        from EduFlowGraph.store.migration import migrate_legacy_storage, verify_migration
        from EduFlowGraph.store.sqlite_conversation_log import SQLiteConversationLog
        from EduFlowGraph.store.sqlite_graph_store import SQLiteGraphStore
        from EduFlowGraph.store.sqlite_memory_flow import SQLiteMemoryFlow
        from EduFlowGraph.store.sqlite_profile_store import SQLiteLearnerProfileStore
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        verification = verify_migration(self.data_dir, self.database_path)
        self.assertEqual(verification["status"], "ok")

        storage = SQLiteStorage(self.database_path)
        self.assertEqual(len(SQLiteConversationLog(storage).list_turns("session_a")), 1)
        graph = SQLiteGraphStore(storage)
        self.assertEqual(set(graph.nodes), {"episode_1", "concept_conditional_probability"})
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(
            graph.nodes["episode_1"]["retrieval"]["embedding_vector"],
            sample_episode()["retrieval"]["embedding_vector"],
        )
        flow = SQLiteMemoryFlow(storage)
        event_text = json.dumps(flow.list_events(), ensure_ascii=False)
        self.assertNotIn("embedding_vector", event_text)
        self.assertEqual(SQLiteLearnerProfileStore(storage).load()["revision_count"], 2)

    def test_malformed_jsonl_aborts_without_database(self):
        from EduFlowGraph.store.migration import MigrationValidationError, migrate_legacy_storage

        (self.data_dir / "memory_flow.jsonl").write_text("{broken\n", encoding="utf-8")
        with self.assertRaisesRegex(MigrationValidationError, "memory_flow.jsonl:1"):
            migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        self.assertFalse(self.database_path.exists())

    def test_dangling_edge_aborts_without_database(self):
        from EduFlowGraph.store.migration import MigrationValidationError, migrate_legacy_storage

        edges = json.loads((self.data_dir / "graph_edges.json").read_text(encoding="utf-8"))
        edges[0]["target"] = "concept_missing"
        write_json(self.data_dir / "graph_edges.json", edges)
        with self.assertRaisesRegex(MigrationValidationError, "dangling edge"):
            migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        self.assertFalse(self.database_path.exists())

    def test_existing_destination_is_never_overwritten(self):
        from EduFlowGraph.store.migration import MigrationValidationError, migrate_legacy_storage

        self.database_path.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(MigrationValidationError, "already exists"):
            migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        self.assertEqual(self.database_path.read_bytes(), b"do not overwrite")

    def test_explicit_replace_empty_allows_initialized_but_unused_database(self):
        from EduFlowGraph.store.migration import migrate_legacy_storage, verify_migration
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        SQLiteStorage(self.database_path)
        report = migrate_legacy_storage(
            self.data_dir,
            self.database_path,
            mode="apply",
            replace_empty=True,
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(verify_migration(self.data_dir, self.database_path)["status"], "ok")

    def test_replace_empty_rejects_database_with_business_rows(self):
        from EduFlowGraph.store.migration import MigrationValidationError, migrate_legacy_storage
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        storage = SQLiteStorage(self.database_path)
        with storage.transaction() as connection:
            connection.execute(
                "INSERT INTO sessions(session_id, created_at, updated_at) VALUES ('live', 't', 't')"
            )
        with self.assertRaisesRegex(MigrationValidationError, "not empty"):
            migrate_legacy_storage(
                self.data_dir,
                self.database_path,
                mode="apply",
                replace_empty=True,
            )

    def test_edge_storage_order_is_not_treated_as_semantic_mismatch(self):
        from EduFlowGraph.store.migration import migrate_legacy_storage, verify_migration

        nodes = json.loads((self.data_dir / "graph_nodes.json").read_text(encoding="utf-8"))
        nodes["concept_alpha"] = {
            "concept_id": "concept_alpha",
            "node_id": "concept_alpha",
            "node_type": "concept",
            "name": "Alpha concept",
            "aliases": [],
            "description": "辅助概念。",
            "metadata": {
                "created_at": "2026-06-23T00:00:02+00:00",
                "updated_at": "2026-06-23T00:00:02+00:00",
            },
        }
        write_json(self.data_dir / "graph_nodes.json", nodes)
        edges = json.loads((self.data_dir / "graph_edges.json").read_text(encoding="utf-8"))
        edges.append({
            "edge_id": "aaa_edge",
            "edge_type": "episode_concept",
            "source": "episode_1",
            "target": "concept_alpha",
            "weight": 0.5,
            "evidence": "辅助概念",
            "metadata": {"created_at": "2026-06-23T00:00:02+00:00"},
        })
        write_json(self.data_dir / "graph_edges.json", edges)

        migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        self.assertEqual(
            verify_migration(self.data_dir, self.database_path)["status"],
            "ok",
        )

    def test_sqlite_export_recreates_readable_legacy_layout(self):
        from EduFlowGraph.store.migration import (
            export_sqlite_storage,
            load_legacy_snapshot,
            migrate_legacy_storage,
        )

        migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        export_dir = Path(self.tmp.name) / "exported-data"
        report = export_sqlite_storage(self.database_path, export_dir)

        self.assertEqual(report["status"], "ok")
        exported = load_legacy_snapshot(export_dir)
        self.assertEqual(exported.counts(), report["counts"])
        self.assertTrue((export_dir / "conversations" / "session_a.jsonl").exists())
        self.assertTrue(
            exported.nodes["episode_1"]["retrieval"]["embedding_vector"]
        )

    def test_sqlite_export_refuses_existing_destination(self):
        from EduFlowGraph.store.migration import (
            MigrationValidationError,
            export_sqlite_storage,
            migrate_legacy_storage,
        )

        migrate_legacy_storage(self.data_dir, self.database_path, mode="apply")
        export_dir = Path(self.tmp.name) / "exported-data"
        export_dir.mkdir()
        with self.assertRaisesRegex(MigrationValidationError, "already exists"):
            export_sqlite_storage(self.database_path, export_dir)


if __name__ == "__main__":
    unittest.main()
