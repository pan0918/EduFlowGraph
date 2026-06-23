from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


def sample_episode() -> dict:
    return {
        "episode_id": "episode_1",
        "node_id": "episode_1",
        "node_type": "episode",
        "episode_type": "concept_explanation",
        "title": "条件概率方向",
        "summary": "学生区分两个条件概率。",
        "memory_value": "记录方向混淆。",
        "provenance": {
            "session_id": "session_a",
            "turn_range": [1, 1],
            "start_time": "2026-06-23T00:00:00+00:00",
            "end_time": "2026-06-23T00:00:01+00:00",
        },
        "learner": {
            "goal": "区分条件概率",
            "obstacle": "方向混淆",
            "initial_state": "partial",
            "evidence": ["分不清方向"],
        },
        "tutor": {
            "strategy": "contrastive_explanation",
            "key_moves": ["并排对比"],
        },
        "outcome": {
            "status": "partial_success",
            "evidence": "能够复述方向",
            "next_step": "变式练习",
        },
        "retrieval": {
            "embedding_text": "条件概率方向混淆",
            "keywords": ["条件概率"],
            "embedding_vector": [0.25, -0.5, 1.0, 0.0],
            "embedding_metadata": {
                "provider": "mock",
                "model_id": "mock-embedding",
                "dimensions": 4,
                "created_at": "2026-06-23T00:00:02+00:00",
            },
        },
    }


class SQLiteStorageContractTest(unittest.TestCase):
    def test_initialization_creates_schema_and_wal(self):
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(Path(tmp) / "eduflowgraph.db")

            self.assertEqual(storage.schema_version(), 1)
            self.assertEqual(storage.journal_mode(), "wal")
            self.assertEqual(storage.quick_check(), "ok")
            with storage.connect() as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertTrue(
                {
                    "sessions",
                    "turns",
                    "memory_events",
                    "nodes",
                    "edges",
                    "profile_models",
                    "profile_changes",
                    "embeddings",
                }.issubset(tables)
            )

    def test_transaction_rolls_back_all_writes(self):
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(Path(tmp) / "eduflowgraph.db")
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                with storage.transaction() as connection:
                    connection.execute(
                        "INSERT INTO sessions(session_id, created_at, updated_at) "
                        "VALUES (?, ?, ?)",
                        ("session_a", "2026-06-23T00:00:00+00:00", "2026-06-23T00:00:00+00:00"),
                    )
                    raise RuntimeError("force rollback")

            with storage.connect() as connection:
                count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            self.assertEqual(count, 0)

    def test_profile_rows_are_materialized_on_initialization(self):
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(Path(tmp) / "eduflowgraph.db")
            with storage.connect() as connection:
                names = [
                    row[0]
                    for row in connection.execute(
                        "SELECT model_name FROM profile_models ORDER BY model_name"
                    )
                ]
            self.assertEqual(
                names,
                ["context_model", "learner_model", "strategy_model"],
            )


class SQLiteCodecTest(unittest.TestCase):
    def test_vector_codec_round_trip(self):
        from EduFlowGraph.store.sqlite_storage import decode_vector, encode_vector

        encoded = encode_vector([0.25, -0.5, 1.0])

        self.assertEqual(encoded.dimensions, 3)
        self.assertEqual(len(encoded.blob), 12)
        np.testing.assert_allclose(
            decode_vector(encoded.blob, encoded.dimensions),
            [0.25, -0.5, 1.0],
            rtol=1e-6,
        )

    def test_vector_codec_rejects_corrupt_length(self):
        from EduFlowGraph.store.sqlite_storage import (
            StorageDecodeError,
            decode_vector,
            encode_vector,
        )

        encoded = encode_vector([0.25, -0.5, 1.0])
        with self.assertRaisesRegex(StorageDecodeError, "byte length"):
            decode_vector(encoded.blob[:-1], encoded.dimensions)

    def test_vector_codec_rejects_non_finite_values(self):
        from EduFlowGraph.store.sqlite_storage import StorageDecodeError, encode_vector

        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(StorageDecodeError, "finite"):
                    encode_vector([value])

    def test_json_codec_reports_context(self):
        from EduFlowGraph.store.sqlite_storage import StorageDecodeError, decode_json

        with self.assertRaisesRegex(StorageDecodeError, "nodes/concept_bad"):
            decode_json("{broken", expected_type=dict, context="nodes/concept_bad")


class SQLiteConversationLogTest(unittest.TestCase):
    def setUp(self):
        from EduFlowGraph.store.sqlite_conversation_log import SQLiteConversationLog
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        self.tmp = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(Path(self.tmp.name) / "eduflowgraph.db")
        self.log = SQLiteConversationLog(self.storage)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_conversation_read_interfaces_keep_current_shape(self):
        turn = self.log.append_turn(
            session_id="session_a",
            turn_index=1,
            user_message="为什么？",
            assistant_message="因为条件方向不同。",
            metadata={"usage": {"total_tokens": 12}},
        )

        self.assertEqual(self.log.list_turns("session_a"), [turn.to_dict()])
        self.assertEqual(list(self.log.iter_turns("session_a")), [turn.to_dict()])
        self.assertEqual(self.log.next_turn_index("session_a"), 2)
        self.assertEqual(self.log.list_sessions(), ["session_a"])
        self.assertEqual(
            self.log.session_messages("session_a"),
            [
                {"role": "user", "content": "为什么？"},
                {"role": "assistant", "content": "因为条件方向不同。"},
            ],
        )
        rendered = self.log.render_for_extraction("session_a")
        self.assertIn("student: 为什么？", rendered)
        self.assertIn("assistant: 因为条件方向不同。", rendered)

    def test_clear_session_and_clear_all_remove_sessions(self):
        for session_id in ("session_a", "session_b"):
            self.log.append_turn(
                session_id=session_id,
                turn_index=1,
                user_message=session_id,
                assistant_message="answer",
            )
        self.log.clear_session("session_a")
        self.assertEqual(self.log.list_sessions(), ["session_b"])
        self.log.clear_all()
        self.assertEqual(self.log.list_sessions(), [])


class SQLiteMemoryFlowTest(unittest.TestCase):
    def setUp(self):
        from EduFlowGraph.store.sqlite_memory_flow import SQLiteMemoryFlow
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        self.tmp = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(Path(self.tmp.name) / "eduflowgraph.db")
        self.flow = SQLiteMemoryFlow(self.storage)

    def tearDown(self):
        self.tmp.cleanup()

    def test_events_keep_order_and_strip_embedding_vectors(self):
        first = self.flow.emit(
            "episode_created",
            "session_a",
            {"episode": sample_episode(), "segment_id": "segment_1"},
        )
        second = self.flow.emit(
            "profile_updated",
            "session_a",
            {"episode_id": "episode_1", "updated_models": ["learner_model"]},
        )

        events = self.flow.list_events()
        self.assertEqual(
            [event["event_id"] for event in events],
            [first.event_id, second.event_id],
        )
        retrieval = events[0]["payload"]["episode"]["retrieval"]
        self.assertNotIn("embedding_vector", retrieval)
        self.assertEqual(
            self.flow.replay_episodes()[0]["episode_id"],
            "episode_1",
        )
        self.assertEqual(
            [event["event_type"] for event in self.flow.list_events("profile_updated")],
            ["profile_updated"],
        )

    def test_clear_removes_all_events(self):
        self.flow.emit("profile_updated", "session_a", {"episode_id": "episode_1"})
        self.flow.clear()
        self.assertEqual(self.flow.list_events(), [])


class SQLiteGraphStoreTest(unittest.TestCase):
    def setUp(self):
        from EduFlowGraph.store.sqlite_graph_store import SQLiteGraphStore
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        self.tmp = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(Path(self.tmp.name) / "eduflowgraph.db")
        self.graph = SQLiteGraphStore(self.storage)

    def tearDown(self):
        self.tmp.cleanup()

    def test_graph_round_trip_separates_and_reinjects_embedding(self):
        episode = sample_episode()
        concept = {
            "name": "Conditional probability",
            "aliases": ["条件概率"],
            "description": "给定条件下事件发生的概率。",
            "retrieval": {
                "embedding_text": "Conditional probability 条件概率",
                "keywords": ["Conditional probability", "条件概率"],
                "embedding_vector": [1.0, 0.0, 0.0, 0.0],
                "embedding_metadata": {
                    "provider": "mock",
                    "model_id": "mock-embedding",
                    "dimensions": 4,
                    "created_at": "2026-06-23T00:00:02+00:00",
                },
            },
        }
        self.graph.apply_episode(episode)
        result = self.graph.apply_concept_extraction(
            episode["episode_id"],
            concepts=[concept],
            edges=[{
                "concept_name": "Conditional probability",
                "weight": 0.95,
                "evidence": "本轮核心概念",
                "metadata": {"structural_role": "main"},
            }],
        )
        concept_id = result["edges"][0]["target"]

        with self.storage.connect() as connection:
            raw_payload = connection.execute(
                "SELECT payload_json FROM nodes WHERE node_id=?",
                (episode["node_id"],),
            ).fetchone()[0]
            embedding = connection.execute(
                "SELECT dimensions, length(vector_blob) FROM embeddings WHERE node_id=?",
                (episode["node_id"],),
            ).fetchone()
        self.assertNotIn("embedding_vector", raw_payload)
        self.assertEqual((embedding[0], embedding[1]), (4, 16))

        self.graph.reload()
        self.assertEqual(
            self.graph.nodes[episode["node_id"]]["retrieval"]["embedding_vector"],
            episode["retrieval"]["embedding_vector"],
        )
        self.assertEqual(
            self.graph.nodes[concept_id]["retrieval"]["embedding_vector"],
            concept["retrieval"]["embedding_vector"],
        )
        self.assertEqual(len(self.graph.edges), 1)

    def test_mutable_cache_save_reload_and_reset_keep_legacy_semantics(self):
        episode = sample_episode()
        self.graph.apply_episode(episode)
        self.graph.nodes[episode["node_id"]]["title"] = "更新后的标题"
        self.graph.save()
        self.graph.reload()
        self.assertEqual(self.graph.nodes[episode["node_id"]]["title"], "更新后的标题")

        self.graph.reset()
        self.graph.save()
        self.graph.reload()
        self.assertEqual(self.graph.nodes, {})
        self.assertEqual(self.graph.edges, [])

    def test_retrieval_health_uses_reinjected_embedding_metadata(self):
        self.graph.apply_episode(sample_episode())
        self.assertEqual(
            self.graph.retrieval_health({
                "provider": "mock",
                "model_id": "mock-embedding",
                "dimensions": 4,
            }),
            {"total_nodes": 1, "valid_vectors": 1, "stale_vectors": 0},
        )


class SQLiteProfileStoreTest(unittest.TestCase):
    def setUp(self):
        from EduFlowGraph.store.sqlite_profile_store import SQLiteLearnerProfileStore
        from EduFlowGraph.store.sqlite_storage import SQLiteStorage

        self.tmp = tempfile.TemporaryDirectory()
        self.storage = SQLiteStorage(Path(self.tmp.name) / "eduflowgraph.db")
        self.profile = SQLiteLearnerProfileStore(self.storage)

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_shape_updates_and_clear_match_current_contract(self):
        empty = self.profile.load()
        self.assertEqual(
            set(empty["models"]),
            {"learner_model", "strategy_model", "context_model"},
        )
        self.assertEqual(empty["revision_count"], 0)

        updated = self.profile.update_models({
            "learner_model": {"summary": "近期存在方向混淆。", "note": "新增画像"},
            "context_model": {"summary": "当前正在复习。", "note": "更新情境"},
        })
        self.assertEqual(updated["revision_count"], 2)
        self.assertEqual(len(updated["recent_changes"]), 2)
        self.assertEqual(self.profile.summary("learner_model"), "近期存在方向混淆。")
        self.assertFalse(self.profile.is_empty())

        self.profile.clear()
        cleared = self.profile.load()
        self.assertEqual(cleared["revision_count"], 0)
        self.assertEqual(cleared["recent_changes"], [])
        self.assertTrue(self.profile.is_empty())


class SQLitePipelineTest(unittest.TestCase):
    def test_settings_resolve_backend_and_database_path(self):
        from EduFlowGraph.config import load_settings_from_mapping

        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({
                "data_dir": tmp,
                "storage_backend": "sqlite",
            })
            self.assertEqual(settings.storage_backend, "sqlite")
            self.assertEqual(
                settings.resolved_database_path,
                Path(tmp) / "eduflowgraph.db",
            )

            explicit = load_settings_from_mapping({
                "data_dir": tmp,
                "storage_backend": "sqlite",
                "database_path": str(Path(tmp) / "custom.db"),
            })
            self.assertEqual(explicit.resolved_database_path, Path(tmp) / "custom.db")

    def test_settings_reject_unknown_backend(self):
        from EduFlowGraph.config import load_settings_from_mapping

        with self.assertRaisesRegex(ValueError, "storage_backend"):
            load_settings_from_mapping({"storage_backend": "remote-magic"})

    def test_pipeline_sqlite_empty_dashboard_and_chat_contract(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline

        with tempfile.TemporaryDirectory() as tmp:
            pipeline = TutorPipeline(load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            }))
            snapshot = pipeline.dashboard()
            self.assertEqual(snapshot["concepts"], [])
            self.assertEqual(snapshot["episodes"], [])
            self.assertEqual(snapshot["skills"], [])
            self.assertEqual(snapshot["edges"], [])
            self.assertEqual(snapshot["memory_events"], [])
            self.assertEqual(snapshot["memory_flow_count"], 0)
            self.assertEqual(snapshot["storage_health"]["backend"], "sqlite")

            result = pipeline.handle_user_message("session_a", "请解释条件概率。")
            self.assertTrue(result["answer"])
            turns = pipeline.conv_log.list_turns("session_a")
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["user_message"], "请解释条件概率。")

            restarted = TutorPipeline(pipeline.settings)
            self.assertEqual(len(restarted.conv_log.list_turns("session_a")), 1)

    def test_pipeline_legacy_json_backend_remains_available(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline
        from EduFlowGraph.store.conversation_log import ConversationLog

        with tempfile.TemporaryDirectory() as tmp:
            pipeline = TutorPipeline(load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "json",
            }))
            self.assertIsInstance(pipeline.conv_log, ConversationLog)


class SQLiteAtomicityTest(unittest.TestCase):
    def test_episode_and_event_roll_back_together_when_event_write_fails(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline

        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            })
            pipeline = TutorPipeline(settings)
            turns = [{
                "turn_index": 1,
                "timestamp": "2026-06-23T00:00:00+00:00",
                "session_id": "session_a",
                "user_message": "请解释条件概率。",
                "assistant_message": "条件概率是在给定条件下的概率。",
                "metadata": {},
            }]

            with patch.object(
                pipeline.memory_flow,
                "emit",
                side_effect=RuntimeError("event write failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "event write failed"):
                    pipeline._extract_segment(
                        turns,
                        session_id="session_a",
                        segment_id="segment_a",
                    )

            restarted = TutorPipeline(settings)
            self.assertEqual(restarted.dashboard()["episodes"], [])
            self.assertEqual(restarted.dashboard()["memory_flow_count"], 0)

    def test_profile_update_rolls_back_when_profile_event_fails(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline

        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            })
            pipeline = TutorPipeline(settings)
            episode = sample_episode()
            with patch.object(
                pipeline.memory_flow,
                "emit",
                side_effect=RuntimeError("profile event failed"),
            ):
                pipeline._consolidate_episode_profile(
                    episode=episode,
                    concept_result={"concepts": [{"name": "Conditional probability"}]},
                    skill_evidence={
                        "teaching_actions": ["contrastive_explanation"],
                    },
                )

            restarted = TutorPipeline(settings)
            self.assertTrue(restarted.profile_store.is_empty())
            self.assertEqual(restarted.memory_flow.list_events(), [])

    def test_reset_rolls_back_when_one_store_clear_fails(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline

        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            })
            pipeline = TutorPipeline(settings)
            pipeline.handle_user_message("session_a", "请解释条件概率。")
            with patch.object(
                pipeline.profile_store,
                "clear",
                side_effect=RuntimeError("profile clear failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "profile clear failed"):
                    pipeline.reset_memory()

            restarted = TutorPipeline(settings)
            self.assertEqual(len(restarted.conv_log.list_turns("session_a")), 1)


class SQLiteErrorContractTest(unittest.TestCase):
    def test_dashboard_storage_failure_returns_render_safe_shape(self):
        from EduFlowGraph.config import load_settings_from_mapping
        from EduFlowGraph.pipeline import TutorPipeline
        from EduFlowGraph.store.sqlite_storage import StorageDecodeError

        with tempfile.TemporaryDirectory() as tmp:
            pipeline = TutorPipeline(load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            }))
            for error in (
                StorageDecodeError("corrupt node payload"),
                sqlite3.DatabaseError("database disk image is malformed"),
            ):
                with self.subTest(error=type(error).__name__):
                    with patch.object(
                        pipeline.graph,
                        "reload",
                        side_effect=error,
                    ):
                        snapshot = pipeline.dashboard()

                    self.assertEqual(snapshot["concepts"], [])
                    self.assertEqual(snapshot["episodes"], [])
                    self.assertEqual(snapshot["skills"], [])
                    self.assertEqual(snapshot["edges"], [])
                    self.assertEqual(snapshot["memory_events"], [])
                    self.assertEqual(snapshot["memory_flow_count"], 0)
                    self.assertEqual(
                        set(snapshot["profile"]["models"]),
                        {"learner_model", "strategy_model", "context_model"},
                    )
                    self.assertEqual(snapshot["profile"]["health"]["status"], "error")
                    self.assertEqual(snapshot["storage_health"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
