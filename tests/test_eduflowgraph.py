"""Tests for the restructured EduFlowGraph package."""

import json
import tempfile
import unittest
from pathlib import Path

from EduFlowGraph.config import Settings, load_settings_from_mapping
from EduFlowGraph.llm import LLMClient
from EduFlowGraph.memory.buffer import BufferManager, EpisodeBoundaryDetector
from EduFlowGraph.memory.episode_extractor import (
    HeuristicEpisodeExtractor,
    coerce_episode_from_llm,
    finalize_episode,
)
from EduFlowGraph.memory.concept_extractor import (
    HeuristicConceptExtractor,
    coerce_concept_payload_from_llm,
    is_banned_concept_name,
    sanitize_concept_payload,
)
from EduFlowGraph.memory import skill_pipeline
from EduFlowGraph.memory.skill_pipeline import (
    HeuristicSkillDistiller,
    HeuristicSkillEvidenceExtractor,
    coerce_skill_distillation_payload_from_llm,
    same_concept_family,
    skill_matches_candidate,
    skill_matches_evidence,
)
from EduFlowGraph.memory.retriever import MemoryRetriever
from EduFlowGraph.prompts import (
    CONCEPT_EXTRACTION_PROMPT,
    EPISODE_DETECTION_PROMPT,
    EPISODE_EXTRACTION_PROMPT,
    RERANK_FALLBACK_PROMPT,
    PROFILE_UPDATE_PROMPT,
    PROFILE_CONDENSE_PROMPT,
    SKILL_DISTILLATION_PROMPT,
    SKILL_EVIDENCE_EXTRACTION_PROMPT,
    TUTOR_MEMORY_AUGMENTED_USER_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    TUTOR_USER_PROMPT,
)
from EduFlowGraph.schemas import Turn, MemoryEvent, make_id, utc_now
from EduFlowGraph.skills import (
    DIFFICULTY_PATTERNS,
    TEACHING_ACTIONS,
    teaching_action_taxonomy,
    difficulty_pattern_taxonomy,
)
from EduFlowGraph.store.conversation_log import ConversationLog
from EduFlowGraph.store.graph_store import GraphStore
from EduFlowGraph.store.memory_flow import MemoryFlow
from EduFlowGraph.store.profile_store import LearnerProfileStore
from EduFlowGraph.store.skill_adaptation_store import SkillAdaptationStore
from EduFlowGraph.profile.dimensions import (
    PROFILE_MODELS,
    MODEL_NAMES,
    EPISODE_MODELS,
    TURN_MODEL,
    MAX_RECENT_CHANGES,
    model_budget,
    skill_adaptation_budget,
)
from EduFlowGraph.profile.aggregator import summarize_profile, profile_is_populated
from EduFlowGraph.profile.consolidator import ProfileConsolidator
from EduFlowGraph.profile.retriever import render_profile_context


class LLMClientTest(unittest.TestCase):
    def test_post_json_retries_transient_failure(self):
        client = LLMClient(
            "openai",
            "test-key",
            "https://example.com/v1",
            "gpt-4o-mini",
            "text-embedding-3-small",
        )
        attempts = {"count": 0}

        def fake_urlopen(req, timeout=60):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise OSError("temporary network failure")

            class _Resp:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {"choices": [{"message": {"content": "OK"}}]}
                    ).encode("utf-8")

            return _Resp()

        from unittest.mock import patch

        with patch("EduFlowGraph.llm.request.urlopen", side_effect=fake_urlopen):
            content = client.chat([{"role": "user", "content": "ping"}])
        self.assertEqual(content, "OK")
        self.assertEqual(attempts["count"], 3)


class SchemasTest(unittest.TestCase):
    def test_make_id_has_prefix(self):
        eid = make_id("episode")
        self.assertTrue(eid.startswith("episode_"))

    def test_utc_now_returns_iso(self):
        ts = utc_now()
        self.assertIn("T", ts)

    def test_turn_to_dict(self):
        turn = Turn(
            turn_index=1,
            timestamp="2026-06-17T00:00:00+00:00",
            session_id="s1",
            user_message="hello",
            assistant_message="hi",
        )
        d = turn.to_dict()
        self.assertEqual(d["turn_index"], 1)
        self.assertEqual(d["user_message"], "hello")

    def test_memory_event_to_dict(self):
        ev = MemoryEvent(
            event_id="mf_001",
            timestamp="2026-06-17T00:00:00+00:00",
            event_type="episode_created",
            session_id="s1",
            payload={"episode_id": "ep1"},
        )
        d = ev.to_dict()
        self.assertEqual(d["event_type"], "episode_created")


class SkillsTest(unittest.TestCase):
    def test_teaching_actions_include_new_entries(self):
        self.assertIn("guided_practice", TEACHING_ACTIONS)
        self.assertIn("error_correction", TEACHING_ACTIONS)
        self.assertIn("concrete_example", TEACHING_ACTIONS)
        self.assertIn("step_by_step_guidance", TEACHING_ACTIONS)
        self.assertIn("self_explanation_prompt", TEACHING_ACTIONS)

    def test_difficulty_patterns_include_conceptual_confusion(self):
        self.assertIn("conceptual_confusion", DIFFICULTY_PATTERNS)

    def test_taxonomy_returns_deep_copy(self):
        a = teaching_action_taxonomy()
        b = teaching_action_taxonomy()
        a["contrastive_explanation"]["label"] = "modified"
        self.assertNotEqual(
            a["contrastive_explanation"]["label"],
            b["contrastive_explanation"]["label"],
        )


class PromptsTest(unittest.TestCase):
    def test_all_prompts_are_nonempty_strings(self):
        for name, prompt in [
            ("EPISODE_DETECTION", EPISODE_DETECTION_PROMPT),
            ("EPISODE_EXTRACTION", EPISODE_EXTRACTION_PROMPT),
            ("CONCEPT_EXTRACTION", CONCEPT_EXTRACTION_PROMPT),
            ("SKILL_EVIDENCE", SKILL_EVIDENCE_EXTRACTION_PROMPT),
            ("SKILL_DISTILLATION", SKILL_DISTILLATION_PROMPT),
            ("RERANK_FALLBACK", RERANK_FALLBACK_PROMPT),
            ("TUTOR_SYSTEM", TUTOR_SYSTEM_PROMPT),
            ("TUTOR_USER", TUTOR_USER_PROMPT),
            ("TUTOR_MEMORY_AUGMENTED", TUTOR_MEMORY_AUGMENTED_USER_PROMPT),
        ]:
            with self.subTest(prompt=name):
                self.assertIsInstance(prompt, str)
                self.assertGreater(len(prompt), 5)


class ConfigTest(unittest.TestCase):
    def test_settings_has_new_paths(self):
        s = Settings()
        self.assertTrue(str(s.conversations_dir).endswith("conversations"))
        self.assertTrue(str(s.memory_flow_path).endswith("memory_flow.jsonl"))

    def test_load_settings_from_mapping(self):
        s = load_settings_from_mapping({"data_dir": "/tmp/test", "provider": "mock"})
        self.assertEqual(s.llm.provider, "mock")
        self.assertEqual(str(s.data_dir), "/tmp/test")


class ConversationLogTest(unittest.TestCase):
    def test_append_and_list_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = ConversationLog(Path(tmp) / "conversations")
            log.append_turn(
                session_id="s1",
                turn_index=1,
                user_message="hello",
                assistant_message="hi",
            )
            log.append_turn(
                session_id="s1",
                turn_index=2,
                user_message="what is bayes",
                assistant_message="bayes theorem is...",
            )
            turns = log.list_turns("s1")
            self.assertEqual(len(turns), 2)
            self.assertEqual(turns[0]["user_message"], "hello")
            self.assertEqual(turns[1]["turn_index"], 2)

    def test_session_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = ConversationLog(Path(tmp) / "conversations")
            log.append_turn(
                session_id="s1",
                turn_index=1,
                user_message="hello",
                assistant_message="hi",
            )
            messages = log.session_messages("s1")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[1]["role"], "assistant")


class MemoryFlowTest(unittest.TestCase):
    def test_emit_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            mf = MemoryFlow(Path(tmp) / "memory_flow.jsonl")
            mf.emit("episode_created", "s1", {"episode_id": "ep1"})
            mf.emit("concept_extracted", "s1", {"concepts": []})
            events = mf.list_events()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_type"], "episode_created")

    def test_filter_by_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            mf = MemoryFlow(Path(tmp) / "memory_flow.jsonl")
            mf.emit("episode_created", "s1", {"episode_id": "ep1"})
            mf.emit("concept_extracted", "s1", {"concepts": []})
            episodes = mf.list_events("episode_created")
            self.assertEqual(len(episodes), 1)


class GraphStoreTest(unittest.TestCase):
    def test_upsert_concept_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            gs = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            c1 = gs.upsert_concept(
                {"name": "Bayes theorem", "aliases": ["贝叶斯定理"], "description": "A prob rule."}
            )
            c2 = gs.upsert_concept(
                {"name": "贝叶斯定理", "aliases": ["Bayes rule"], "description": "Updated."}
            )
            self.assertEqual(c1["node_id"], c2["node_id"])
            self.assertIn("Bayes rule", c2["aliases"])

    def test_apply_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            gs = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            gs.apply_episode({
                "episode_id": "ep1",
                "node_id": "ep1",
                "node_type": "episode",
                "title": "Test episode",
            })
            episodes = gs.nodes_by_type("episode")
            self.assertIn("ep1", episodes)

    def test_reload_reads_latest_disk_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            nodes_path = Path(tmp) / "nodes.json"
            edges_path = Path(tmp) / "edges.json"
            gs = GraphStore(nodes_path, edges_path)
            gs.apply_episode(
                {
                    "episode_id": "ep_writer",
                    "node_id": "ep_writer",
                    "node_type": "episode",
                    "title": "Writer episode",
                }
            )
            gs.nodes = {}
            gs.edges = []
            self.assertNotIn("ep_writer", gs.nodes_by_type("episode"))
            gs.reload()
            self.assertIn("ep_writer", gs.nodes_by_type("episode"))

    def test_find_existing_concept_by_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            gs = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            gs.upsert_concept(
                {"name": "Conditional probability", "aliases": ["条件概率", "P(A|B)"], "description": ""}
            )
            found = gs.find_existing_concept("条件概率", [])
            self.assertIsNotNone(found)
            self.assertEqual(found["name"], "Conditional probability")


class ProfileStoreTest(unittest.TestCase):
    def test_empty_snapshot_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            snap = store.load()
            self.assertEqual(set(snap["models"].keys()), set(MODEL_NAMES))
            for name in MODEL_NAMES:
                self.assertEqual(snap["models"][name]["summary"], "")
            self.assertEqual(snap["revision_count"], 0)
            self.assertEqual(snap["recent_changes"], [])
            self.assertTrue(store.is_empty())

    def test_update_model_rewrites_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            store.update_model("learner_model", "学生在符号映射上有困难。", note="新增：符号映射困难")
            snap = store.load()
            self.assertEqual(
                snap["models"]["learner_model"]["summary"], "学生在符号映射上有困难。"
            )
            self.assertEqual(snap["models"]["learner_model"]["revisions"], 1)
            self.assertEqual(snap["revision_count"], 1)
            self.assertEqual(len(snap["recent_changes"]), 1)
            self.assertFalse(store.is_empty())

    def test_update_is_noop_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            store.update_model("context_model", "当前在探索阶段。")
            store.update_model("context_model", "当前在探索阶段。")
            self.assertEqual(store.load()["revision_count"], 1)

    def test_update_models_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            store.update_models(
                {
                    "learner_model": {"summary": "已掌握PPO基础。", "note": "新增：PPO"},
                    "context_model": {"summary": "当前在探索阶段。", "note": "更新情境"},
                }
            )
            snap = store.load()
            self.assertEqual(snap["models"]["learner_model"]["summary"], "已掌握PPO基础。")
            self.assertEqual(snap["models"]["context_model"]["summary"], "当前在探索阶段。")
            self.assertEqual(snap["revision_count"], 2)

    def test_legacy_strategy_and_adaptation_are_not_carried_into_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            normalized = store._normalize_snapshot(
                {
                    "models": {
                        "learner_model": {"summary": "学习者摘要"},
                        "strategy_model": {"summary": "旧教学程序"},
                        "teaching_adaptation_model": {"summary": "旧适配证据"},
                        "context_model": {"summary": "当前探索"},
                    }
                }
            )

            self.assertNotIn("teaching_adaptation_model", normalized["models"])
            self.assertNotIn("strategy_model", normalized["models"])

    def test_recent_changes_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            for i in range(MAX_RECENT_CHANGES + 5):
                store.update_model("learner_model", f"画像版本 {i}。", note=f"变更 {i}")
            snap = store.load()
            self.assertEqual(len(snap["recent_changes"]), MAX_RECENT_CHANGES)
            # newest first
            self.assertIn("变更", snap["recent_changes"][0]["note"])

    def test_legacy_migration_clean_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            # Simulate old artifacts.
            (data_dir / "profile_evidence.jsonl").write_text(
                '{"model": "learner_model", "label": "x"}\n', encoding="utf-8"
            )
            (data_dir / "learner_profile.json").write_text(
                json.dumps({"models": {"learner_model": [{"label": "old item"}]}}),
                encoding="utf-8",
            )
            store = LearnerProfileStore(data_dir)
            store.migrate_legacy_if_needed()
            self.assertFalse((data_dir / "profile_evidence.jsonl").exists())
            snap = store.load()
            for name in MODEL_NAMES:
                self.assertEqual(snap["models"][name]["summary"], "")

    def test_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnerProfileStore(Path(tmp))
            store.update_model("learner_model", "内容。")
            store.clear()
            self.assertTrue(store.is_empty())


class SkillAdaptationStoreTest(unittest.TestCase):
    def test_empty_snapshot_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SkillAdaptationStore(Path(tmp))
            snap = store.load()
            self.assertEqual(snap["summary"], "")
            self.assertEqual(snap["revisions"], 0)
            self.assertEqual(snap["recent_changes"], [])
            self.assertTrue(store.is_empty())

    def test_update_rewrites_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SkillAdaptationStore(Path(tmp))
            store.update("优先选择低认知负荷的类比 Skill。", note="新增适配证据")
            snap = store.load()
            self.assertEqual(snap["summary"], "优先选择低认知负荷的类比 Skill。")
            self.assertEqual(snap["revisions"], 1)
            self.assertEqual(snap["recent_changes"][0]["note"], "新增适配证据")
            self.assertFalse(store.is_empty())

    def test_migrates_legacy_teaching_adaptation_from_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "learner_profile.json").write_text(
                json.dumps(
                    {
                        "models": {
                            "learner_model": {"summary": "学习者摘要"},
                            "teaching_adaptation_model": {
                                "summary": "旧 Skill 适配证据。",
                                "updated_at": "2026-06-24T16:41:00Z",
                                "revisions": 3,
                            },
                            "context_model": {"summary": "当前探索"},
                        },
                        "recent_changes": [
                            {
                                "at": "2026-06-24T16:41:00Z",
                                "model": "teaching_adaptation_model",
                                "note": "旧适配变更",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = SkillAdaptationStore(data_dir)
            store.migrate_legacy_if_needed()
            snap = store.load()
            self.assertEqual(snap["summary"], "旧 Skill 适配证据。")
            self.assertEqual(snap["updated_at"], "2026-06-24T16:41:00Z")
            self.assertEqual(snap["revisions"], 3)
            self.assertEqual(snap["recent_changes"][0]["note"], "旧适配变更")


class ProfileConsolidatorTest(unittest.TestCase):
    def test_episode_mock_consolidation(self):
        class _MockLLM:
            is_live = False

        consolidator = ProfileConsolidator(_MockLLM())
        episode = {
            "title": "贝叶斯定理",
            "summary": "学生理解了条件概率方向。",
            "learner": {"goal": "理解贝叶斯", "obstacle": "方向混淆"},
            "outcome": {"status": "success", "evidence": "能自己复述"},
        }
        updates = consolidator.consolidate_episode(
            current={
                "learner_model": "",
                "skill_adaptation": "",
                "context_model": "",
            },
            episode=episode,
            concept_result={"concepts": [{"name": "贝叶斯定理"}]},
            skill_evidence={"teaching_actions": ["worked_example"]},
        )
        self.assertIn("learner_model", updates)
        summary = updates["learner_model"]["summary"]
        self.assertTrue(summary)
        # Must not overclaim mastery from a single success episode.
        self.assertNotIn("已建立较好理解", summary)
        self.assertNotIn("已掌握", summary)
        self.assertLessEqual(len(summary), model_budget("learner_model"))
        adaptation = updates.get("skill_adaptation", {}).get("summary", "")
        self.assertTrue(adaptation)
        self.assertIn("Skill", adaptation)
        self.assertIn("例题", adaptation)
        self.assertLessEqual(len(adaptation), skill_adaptation_budget())
        self.assertNotIn("teaching_adaptation_model", updates)
        self.assertNotIn("strategy_model", updates)
        self.assertNotIn("贝叶斯定理如何", adaptation)

    def test_profile_prompts_define_skill_selection_boundary(self):
        self.assertIn("skill_adaptation", PROFILE_UPDATE_PROMPT)
        self.assertIn("Skill", PROFILE_UPDATE_PROMPT)
        self.assertIn("不保存具体教学程序", PROFILE_UPDATE_PROMPT)
        self.assertIn("不属于用户画像", PROFILE_UPDATE_PROMPT)
        self.assertNotIn("teaching_adaptation_model", PROFILE_UPDATE_PROMPT)
        self.assertNotIn("strategy_model", PROFILE_UPDATE_PROMPT)
        self.assertIn("skill_adaptation", PROFILE_CONDENSE_PROMPT)
        self.assertNotIn("teaching_adaptation_model", PROFILE_CONDENSE_PROMPT)
        self.assertNotIn("strategy_model", PROFILE_CONDENSE_PROMPT)

    def test_context_mock_update(self):
        class _MockLLM:
            is_live = False

        consolidator = ProfileConsolidator(_MockLLM())
        updates = consolidator.update_context(
            current="",
            user_message="向我解释一下PPO算法",
            assistant_message="好的……",
        )
        self.assertIn("context_model", updates)
        ctx = updates["context_model"]["summary"]
        self.assertTrue(ctx)
        # Context should describe phase/task, not cognitive diagnosis.
        self.assertIn("阶段", ctx)
        self.assertNotIn("掌握", ctx)

    def test_over_budget_mock_uses_trim_fallback(self):
        class _MockLLM:
            is_live = False

        consolidator = ProfileConsolidator(_MockLLM())
        budget = model_budget("context_model")
        long_text = "。".join([f"情境描述{i}" for i in range(40)]) + "。"
        trimmed = consolidator._sanitize_summary(long_text, "context_model", budget)
        self.assertLessEqual(len(trimmed), budget)
        self.assertTrue(trimmed)

    def test_over_budget_live_uses_llm_condense(self):
        budget = model_budget("learner_model")
        long_text = "。".join(
            [f"「贝叶斯定理」上曾出现方向混淆，需在不同情境下反复验证理解深度，第{i}次观察" for i in range(12)]
        ) + "。"

        class _CondenseLLM:
            is_live = True

            def chat(self, messages, temperature=0.2):
                prompt = messages[-1]["content"]
                self.last_prompt = prompt
                return "「贝叶斯定理」方向混淆反复出现，掌握程度仍待变式题验证。"

        llm = _CondenseLLM()
        consolidator = ProfileConsolidator(llm)
        trimmed = consolidator._sanitize_summary(long_text, "learner_model", budget)
        self.assertLessEqual(len(trimmed), budget)
        self.assertIn("贝叶斯", trimmed)
        self.assertIn("记忆摘要压缩", llm.last_prompt)

    def test_render_profile_context(self):
        snapshot = {
            "models": {
                "learner_model": {"summary": "理解PPO基础。"},
                "context_model": {"summary": "当前处于探索阶段。"},
            }
        }
        rendered = render_profile_context(snapshot)
        self.assertIn("长期学习者画像", rendered)
        self.assertIn("理解PPO基础", rendered)
        self.assertIn("当前学习情境", rendered)
        self.assertIn("当前处于探索阶段", rendered)
        self.assertNotIn("Skill 适配", rendered)

    def test_aggregator_summary(self):
        snapshot = {
            "models": {
                "learner_model": {"summary": "理解PPO。", "revisions": 2},
                "context_model": {"summary": "练习阶段。", "revisions": 1},
            }
        }
        overview = summarize_profile(snapshot)
        self.assertEqual(set(overview), set(MODEL_NAMES))
        self.assertTrue(overview["learner_model"]["has_content"])
        self.assertEqual(overview["learner_model"]["revisions"], 2)
        self.assertTrue(profile_is_populated(snapshot))
        self.assertFalse(profile_is_populated({"models": {}}))


class EpisodeExtractorTest(unittest.TestCase):
    def test_heuristic_extraction(self):
        turns = [
            {"user_message": "为什么不能直接用检测准确率当患病概率？", "actor": "student"},
            {"user_message": "P(A|B)和P(B|A)不一样", "actor": "assistant"},
            {"user_message": "懂了", "actor": "student"},
        ]
        episode = HeuristicEpisodeExtractor().extract(turns)
        self.assertEqual(episode["node_type"], "episode")
        self.assertIn("title", episode)
        self.assertIn("learner", episode)
        self.assertIn("tutor", episode)
        self.assertIn("outcome", episode)
        self.assertIn(episode["outcome"]["status"], {"success", "partial_success", "failed", "unresolved"})

    def test_coerce_episode_from_llm_with_new_format(self):
        llm_output = json.dumps({
            "episode_type": "misconception_diagnosis",
            "title": "检测准确率与后验概率混淆",
            "summary": "学生混淆了P(A|B)和P(B|A)",
            "learner": {
                "goal": "理解条件概率方向",
                "obstacle": "混淆检测准确率和后验概率",
                "initial_state": "low",
                "evidence": ["把P(阳性|患病)当成P(患病|阳性)"],
            },
            "tutor": {
                "strategy": "contrastive_explanation",
                "key_moves": ["对比P(A|B)和P(B|A)", "用100人例子"],
            },
            "outcome": {
                "status": "partial_success",
                "evidence": "学生能复述方向差异但尚未迁移",
                "next_step": "补一道练习题",
            },
            "memory_value": "记录了条件概率方向混淆的澄清过程",
        })
        fallback_turns = [{"user_message": "test", "actor": "student"}]
        episode = coerce_episode_from_llm(llm_output, fallback_turns)
        self.assertEqual(episode["episode_type"], "misconception_diagnosis")
        self.assertEqual(episode["learner"]["initial_state"], "low")
        self.assertEqual(episode["outcome"]["status"], "partial_success")


class ConceptExtractorTest(unittest.TestCase):
    def test_banned_concept_names(self):
        self.assertTrue(is_banned_concept_name("worked_example"))
        self.assertTrue(is_banned_concept_name("diagnostic_check"))
        self.assertFalse(is_banned_concept_name("Bayes theorem"))

    def test_heuristic_extraction_finds_bayes(self):
        episode = {
            "title": "贝叶斯定理讲解",
            "summary": "学生学习贝叶斯定理",
            "learner": {"goal": "理解贝叶斯", "obstacle": "", "evidence": []},
            "tutor": {"strategy": "worked_example", "key_moves": []},
            "outcome": {"status": "success", "evidence": ""},
        }
        result = HeuristicConceptExtractor().extract(episode, [])
        concepts = result.get("concepts", [])
        names = [c["name"] for c in concepts]
        self.assertIn("Bayes theorem", names)


class SkillPipelineTest(unittest.TestCase):
    def _generalized_difficulty_helpers(self):
        compatible = getattr(skill_pipeline, "difficulty_patterns_compatible", None)
        normalized = getattr(skill_pipeline, "skill_difficulty_patterns", None)
        self.assertIsNotNone(compatible)
        self.assertIsNotNone(normalized)
        return compatible, normalized

    def test_same_concept_family_bayes(self):
        self.assertTrue(same_concept_family(["Bayes theorem"], ["贝叶斯定理"]))
        self.assertTrue(same_concept_family(["Conditional probability"], ["条件概率"]))
        self.assertFalse(same_concept_family(["Derivative"], ["Factorization"]))

    def test_heuristic_skill_evidence_extraction(self):
        episode = {
            "episode_id": "ep1",
            "title": "条件概率方向混淆",
            "summary": "学习者混淆了P(A|B)和P(B|A)的方向",
            "learner": {
                "goal": "理解条件概率",
                "obstacle": "混淆P(A|B)和P(B|A)",
                "evidence": ["方向混淆"],
            },
            "tutor": {
                "strategy": "contrastive_explanation",
                "key_moves": ["对比P(A|B)和P(B|A)"],
            },
            "outcome": {"status": "partial_success", "evidence": "学生能复述差异"},
            "provenance": {"session_id": "s1"},
        }
        turns = [
            {"user_message": "P(A|B)和P(B|A)有什么区别？", "actor": "student", "content": "P(A|B)和P(B|A)有什么区别？"},
            {"assistant_message": "对比：P(A|B)是...", "actor": "assistant", "content": "对比：P(A|B)是..."},
        ]
        evidence = HeuristicSkillEvidenceExtractor().extract(
            episode, turns, concept_names=["Conditional probability"], concept_ids=["c1"]
        )
        self.assertIn("teaching_actions", evidence)
        self.assertIn("contrastive_explanation", evidence["teaching_actions"])

    def test_distiller_builds_generic_skill_from_cross_concept_evidence(self):
        episodes = [
            {"episode_id": "ep_ellipse", "title": "椭圆面积推导"},
            {"episode_id": "ep_ppo", "title": "PPO目标函数推导"},
        ]
        evidences = [
            {
                "episode_id": "ep_ellipse",
                "concept_names": ["椭圆面积"],
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": [
                    "formula_decomposition",
                    "step_by_step_guidance",
                    "diagnostic_check",
                ],
                "outcome": {"result": "success", "score": 0.84},
                "evidence_summary": "拆解公式并逐步推导后，学生能独立解释各项。",
            },
            {
                "episode_id": "ep_ppo",
                "concept_names": ["PPO裁剪目标"],
                "difficulty_pattern": "procedural_gap",
                "teaching_actions": [
                    "formula_decomposition",
                    "step_by_step_guidance",
                    "self_explanation_prompt",
                ],
                "outcome": {"result": "success", "score": 0.86},
                "evidence_summary": "逐项解释并分步推导后，学生能复述目标函数。",
            },
        ]

        distilled = HeuristicSkillDistiller().distill(episodes, evidences, {})

        self.assertIsNotNone(distilled)
        skill = distilled["skill"]
        self.assertEqual(
            {"symbol_grounding", "procedural_gap"},
            set(skill["difficulty_patterns"]),
        )
        self.assertEqual(
            ["formula_decomposition", "step_by_step_guidance"],
            skill["teaching_actions"],
        )
        self.assertTrue(any("公式" in step or "项" in step for step in skill["procedure"]))
        self.assertTrue(
            any("步骤" in step or "一步" in step for step in skill["procedure"])
        )
        public_text = " ".join(
            [
                skill["name"],
                skill["trigger"],
                skill["embedding_text"],
                *skill["procedure"],
                *skill["success_criteria"],
            ]
        )
        self.assertNotIn("椭圆", public_text)
        self.assertNotIn("PPO", public_text)
        self.assertNotIn("ep_ellipse", public_text)
        self.assertNotIn("ep_ppo", public_text)
        self.assertEqual(
            {"椭圆面积", "PPO裁剪目标"},
            set(skill["metadata"]["evidence_concept_scope"]),
        )

    def test_distiller_generalizes_concrete_examples_across_subjects(self):
        episodes = [
            {"episode_id": "ep_consensus", "title": "分布式共识"},
            {"episode_id": "ep_law", "title": "法律概念边界"},
        ]
        evidences = [
            {
                "episode_id": "ep_consensus",
                "concept_names": ["分布式共识"],
                "difficulty_pattern": "abstraction_gap",
                "teaching_actions": ["concrete_example", "self_explanation_prompt"],
                "outcome": {"result": "partial_success", "score": 0.68},
                "evidence_summary": "具体场景帮助学生初步理解抽象机制。",
            },
            {
                "episode_id": "ep_law",
                "concept_names": ["表见代理"],
                "difficulty_pattern": "conceptual_confusion",
                "teaching_actions": ["concrete_example", "self_explanation_prompt"],
                "outcome": {"result": "success", "score": 0.82},
                "evidence_summary": "生活化案例帮助学生说清概念边界。",
            },
        ]

        skill = HeuristicSkillDistiller().distill(episodes, evidences, {})["skill"]

        self.assertEqual(
            {"abstraction_gap", "conceptual_confusion"},
            set(skill["difficulty_patterns"]),
        )
        self.assertEqual(
            ["concrete_example", "self_explanation_prompt"],
            skill["teaching_actions"],
        )
        self.assertNotIn("分布式", skill["embedding_text"])
        self.assertNotIn("表见代理", skill["embedding_text"])

    def test_llm_distillation_cannot_specialize_public_skill_to_evidence_concepts(self):
        episodes = [
            {"episode_id": "ep_ellipse", "title": "椭圆面积推导"},
            {"episode_id": "ep_ppo", "title": "PPO目标函数推导"},
        ]
        evidences = [
            {
                "episode_id": "ep_ellipse",
                "concept_names": ["椭圆面积"],
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "outcome": {"result": "success", "score": 0.84},
                "evidence_summary": "学生能解释公式项。",
            },
            {
                "episode_id": "ep_ppo",
                "concept_names": ["PPO裁剪目标"],
                "difficulty_pattern": "procedural_gap",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "outcome": {"result": "success", "score": 0.86},
                "evidence_summary": "学生能复述推导步骤。",
            },
        ]
        raw = json.dumps(
            {
                "should_create_skill": True,
                "skill": {
                    "name": "椭圆与PPO专用推导法",
                    "trigger": "学习椭圆或PPO时使用。",
                    "difficulty_pattern": "symbol_grounding",
                    "difficulty_patterns": ["symbol_grounding"],
                    "teaching_actions": [
                        "formula_decomposition",
                        "worked_example",
                    ],
                    "procedure": ["先写椭圆方程。", "再展开PPO目标函数。"],
                    "success_criteria": ["学习者能算出椭圆面积。"],
                    "embedding_text": "椭圆面积和PPO裁剪目标的专用教学方法。",
                },
                "edges": [],
            },
            ensure_ascii=False,
        )

        skill = coerce_skill_distillation_payload_from_llm(
            raw, episodes, evidences, {}
        )["skill"]

        public_text = " ".join(
            [
                skill["name"],
                skill["trigger"],
                skill["embedding_text"],
                *skill["procedure"],
                *skill["success_criteria"],
            ]
        )
        self.assertNotRegex(public_text, r"椭圆|PPO|ep_ellipse|ep_ppo")
        self.assertEqual(
            {"symbol_grounding", "procedural_gap"},
            set(skill["difficulty_patterns"]),
        )
        self.assertEqual(
            ["formula_decomposition", "step_by_step_guidance"],
            skill["teaching_actions"],
        )

    def test_distiller_supports_other_generic_patterns_across_concepts(self):
        episodes = [
            {"episode_id": "ep_causality", "title": "因果方向"},
            {"episode_id": "ep_dataflow", "title": "输入输出方向"},
        ]
        evidences = [
            {
                "episode_id": "ep_causality",
                "concept_names": ["因果关系"],
                "difficulty_pattern": "direction_confusion",
                "teaching_actions": ["contrastive_explanation", "socratic_questioning"],
                "outcome": {"result": "success", "score": 0.82},
                "evidence_summary": "对比和追问后能说明因果方向。",
            },
            {
                "episode_id": "ep_dataflow",
                "concept_names": ["数据流"],
                "difficulty_pattern": "direction_confusion",
                "teaching_actions": ["contrastive_explanation", "socratic_questioning"],
                "outcome": {"result": "partial_success", "score": 0.7},
                "evidence_summary": "对比和追问后能区分输入输出。",
            },
        ]

        skill = HeuristicSkillDistiller().distill(episodes, evidences, {})["skill"]

        self.assertEqual(["direction_confusion"], skill["difficulty_patterns"])
        self.assertEqual(
            ["contrastive_explanation", "socratic_questioning"],
            skill["teaching_actions"],
        )
        public_text = " ".join([skill["name"], skill["trigger"], skill["embedding_text"]])
        self.assertNotRegex(public_text, r"因果关系|数据流")

    def test_distiller_rejects_evidence_without_stable_core_action(self):
        episodes = [
            {"episode_id": "ep_a", "title": "主题甲"},
            {"episode_id": "ep_b", "title": "主题乙"},
        ]
        evidences = [
            {
                "episode_id": "ep_a",
                "concept_names": ["主题甲"],
                "difficulty_pattern": "abstraction_gap",
                "teaching_actions": ["concrete_example"],
                "outcome": {"result": "success", "score": 0.8},
            },
            {
                "episode_id": "ep_b",
                "concept_names": ["主题乙"],
                "difficulty_pattern": "conceptual_confusion",
                "teaching_actions": ["contrastive_explanation"],
                "outcome": {"result": "success", "score": 0.82},
            },
        ]

        self.assertIsNone(HeuristicSkillDistiller().distill(episodes, evidences, {}))

    def test_generalized_skill_id_is_stable_when_evidence_order_changes(self):
        episodes = [
            {"episode_id": "ep_symbol", "title": "形式化主题甲"},
            {"episode_id": "ep_steps", "title": "形式化主题乙"},
        ]
        evidences = [
            {
                "episode_id": "ep_symbol",
                "concept_names": ["形式化主题甲"],
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "outcome": {"result": "success", "score": 0.82},
            },
            {
                "episode_id": "ep_steps",
                "concept_names": ["形式化主题乙"],
                "difficulty_pattern": "procedural_gap",
                "teaching_actions": ["step_by_step_guidance", "formula_decomposition"],
                "outcome": {"result": "success", "score": 0.84},
            },
        ]

        forward = HeuristicSkillDistiller().distill(episodes, evidences, {})["skill"]
        reverse = HeuristicSkillDistiller().distill(
            list(reversed(episodes)), list(reversed(evidences)), {}
        )["skill"]

        self.assertEqual(forward["node_id"], reverse["node_id"])

    def test_distiller_does_not_stitch_actions_without_repeated_cooccurrence(self):
        episodes = [
            {"episode_id": "ep_both", "title": "主题一"},
            {"episode_id": "ep_formula", "title": "主题二"},
            {"episode_id": "ep_steps", "title": "主题三"},
        ]
        evidences = [
            {
                "episode_id": "ep_both",
                "concept_names": ["主题一"],
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "outcome": {"result": "success", "score": 0.82},
            },
            {
                "episode_id": "ep_formula",
                "concept_names": ["主题二"],
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": ["formula_decomposition"],
                "outcome": {"result": "success", "score": 0.84},
            },
            {
                "episode_id": "ep_steps",
                "concept_names": ["主题三"],
                "difficulty_pattern": "procedural_gap",
                "teaching_actions": ["step_by_step_guidance"],
                "outcome": {"result": "success", "score": 0.86},
            },
        ]

        actions = HeuristicSkillDistiller().distill(episodes, evidences, {})["skill"][
            "teaching_actions"
        ]

        self.assertEqual(1, len(actions))

    def test_skill_matching_uses_learning_situation_not_concept_family(self):
        difficulty_patterns_compatible, skill_difficulty_patterns = (
            self._generalized_difficulty_helpers()
        )
        skill = {
            "difficulty_pattern": "symbol_grounding",
            "difficulty_patterns": ["symbol_grounding", "procedural_gap"],
            "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
            "metadata": {"evidence_concept_scope": ["椭圆面积", "PPO裁剪目标"]},
        }
        gravity_evidence = {
            "difficulty_pattern": "procedural_gap",
            "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
            "concept_names": ["万有引力"],
        }

        self.assertTrue(skill_matches_evidence(skill, gravity_evidence))
        self.assertTrue(
            difficulty_patterns_compatible(
                skill_difficulty_patterns(skill),
                ["procedural_gap"],
            )
        )

    def test_skill_matching_rejects_unrelated_difficulty_or_weak_actions(self):
        skill = {
            "difficulty_pattern": "symbol_grounding",
            "difficulty_patterns": ["symbol_grounding", "procedural_gap"],
            "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
        }
        unrelated = {
            "difficulty_pattern": "direction_confusion",
            "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
            "concept_names": ["因果方向"],
        }
        weak_actions = {
            "difficulty_pattern": "procedural_gap",
            "teaching_actions": ["step_by_step_guidance", "worked_example"],
            "concept_names": ["新主题"],
        }

        self.assertFalse(skill_matches_evidence(skill, unrelated))
        self.assertFalse(skill_matches_evidence(skill, weak_actions))

    def test_legacy_single_pattern_skill_matches_new_concept(self):
        _, skill_difficulty_patterns = self._generalized_difficulty_helpers()
        legacy_skill = {
            "difficulty_pattern": "abstraction_gap",
            "teaching_actions": ["concrete_example"],
            "metadata": {"evidence_concept_scope": ["操作系统调度"]},
        }
        evidence = {
            "difficulty_pattern": "abstraction_gap",
            "teaching_actions": ["concrete_example"],
            "concept_names": ["机会成本"],
        }

        self.assertEqual(["abstraction_gap"], skill_difficulty_patterns(legacy_skill))
        self.assertTrue(skill_matches_evidence(legacy_skill, evidence))

    def test_candidate_deduplication_is_concept_agnostic(self):
        existing = {
            "difficulty_pattern": "abstraction_gap",
            "difficulty_patterns": ["abstraction_gap", "conceptual_confusion"],
            "teaching_actions": ["concrete_example", "self_explanation_prompt"],
            "metadata": {"evidence_concept_scope": ["分布式共识"]},
        }
        candidate = {
            "difficulty_pattern": "conceptual_confusion",
            "difficulty_patterns": ["conceptual_confusion"],
            "teaching_actions": ["concrete_example", "self_explanation_prompt"],
            "metadata": {"evidence_concept_scope": ["表见代理"]},
        }

        self.assertTrue(skill_matches_candidate(existing, candidate))

    def test_pipeline_evidence_window_accepts_cross_concept_compatible_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(
                load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            )
            current = {
                "episode_id": "ep_ppo",
                "difficulty_pattern": "procedural_gap",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "concept_names": ["PPO裁剪目标"],
            }
            ellipse = {
                "episode_id": "ep_ellipse",
                "difficulty_pattern": "symbol_grounding",
                "teaching_actions": ["formula_decomposition", "step_by_step_guidance"],
                "concept_names": ["椭圆面积"],
            }
            unrelated = {
                "episode_id": "ep_direction",
                "difficulty_pattern": "direction_confusion",
                "teaching_actions": ["contrastive_explanation"],
                "concept_names": ["条件概率"],
            }

            window = pipeline._build_evidence_window(
                current,
                [ellipse, unrelated, current],
            )

        self.assertEqual(["ep_ellipse", "ep_ppo"], [item["episode_id"] for item in window])

    def test_retriever_matches_any_generalized_difficulty_pattern(self):
        retriever = MemoryRetriever(graph=None)
        skill = {
            "difficulty_pattern": "symbol_grounding",
            "difficulty_patterns": ["symbol_grounding", "procedural_gap"],
        }

        self.assertEqual(
            0.18,
            retriever._difficulty_match_bonus(
                {"difficulty_hints": ["procedural_gap"]},
                skill,
            ),
        )


class BufferManagerTest(unittest.TestCase):
    def test_add_and_consume(self):
        bm = BufferManager()
        bm.add_turn("s1", {"turn_index": 1, "user_message": "hello"})
        bm.add_turn("s1", {"turn_index": 2, "user_message": "world"})
        self.assertEqual(bm.buffer_size("s1"), 2)
        consumed = bm.consume("s1")
        self.assertEqual(len(consumed), 2)
        self.assertEqual(bm.buffer_size("s1"), 0)

    def test_consume_prefix(self):
        bm = BufferManager()
        for i in range(5):
            bm.add_turn("s1", {"turn_index": i})
        prefix = bm.consume_prefix("s1", 3)
        self.assertEqual(len(prefix), 3)
        self.assertEqual(bm.buffer_size("s1"), 2)


class ProfileDimensionsTest(unittest.TestCase):
    def test_two_portrait_models_defined(self):
        self.assertEqual(MODEL_NAMES, ("learner_model", "context_model"))

    def test_model_triggers(self):
        self.assertEqual(set(EPISODE_MODELS), {"learner_model"})
        self.assertEqual(TURN_MODEL, "context_model")

    def test_model_budgets(self):
        for name in MODEL_NAMES:
            self.assertGreater(model_budget(name), 0)
        self.assertGreater(skill_adaptation_budget(), 0)
        self.assertEqual(len(PROFILE_MODELS), 2)


class PipelineIntegrationTest(unittest.TestCase):
    @staticmethod
    def _skill_candidate(skill_id: str = "skill_visual") -> dict:
        return {
            "id": skill_id,
            "node": {
                "skill_id": skill_id,
                "node_id": skill_id,
                "node_type": "skill",
                "name": "直观类比引入",
                "status": "active",
                "trigger": "学习全新抽象概念时",
                "difficulty_pattern": "abstraction_gap",
                "teaching_actions": ["concrete_example"],
                "procedure": ["先给生活化类比", "再映射到正式概念"],
                "success_criteria": ["学生能复述核心思想"],
                "quality": {"confidence": 0.86},
            },
            "base_raw_score": 0.9,
            "episode_link_raw_score": 0.8,
            "episode_evidence": ["类比后学生能够复述"],
        }

    @staticmethod
    def _retrieval_context(candidates: list[dict]) -> dict:
        return {
            "concepts": [],
            "episodes": [],
            "skills": [],
            "skill_candidates": candidates,
            "retrieval_summary": {
                "query_info": {"intent": "concept_explanation"},
                "concept_hits": 0,
                "episode_hits": 0,
                "skill_hits": len(candidates),
                "stale_vectors": 0,
                "top_matches": {"concepts": [], "episodes": [], "skills": []},
            },
        }

    def test_pipeline_mock_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock"}
            )
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(settings)
            result = pipeline.handle_user_message(
                "session_test",
                "为什么不能直接用检测准确率当患病概率？",
            )
            self.assertIn("answer", result)
            self.assertIsInstance(result["answer"], str)
            self.assertIn("context", result)
            self.assertIn("turn", result)

    def test_pipeline_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock"}
            )
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(settings)
            dash = pipeline.dashboard()
            self.assertIn("concepts", dash)
            self.assertIn("episodes", dash)
            self.assertIn("skills", dash)
            self.assertIn("profile", dash)
            self.assertIn("skill_adaptation", dash)

    def test_dashboard_reloads_graph_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock"}
            )
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(settings)
            pipeline.graph.apply_episode(
                {
                    "episode_id": "ep_disk",
                    "node_id": "ep_disk",
                    "node_type": "episode",
                    "title": "Disk episode",
                }
            )
            pipeline.graph.nodes = {}
            pipeline.graph.edges = []
            dash = pipeline.dashboard()
            episode_ids = {item.get("node_id") for item in dash["episodes"]}
            self.assertIn("ep_disk", episode_ids)

    def test_pipeline_reset_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock"}
            )
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(settings)
            pipeline.handle_user_message("s1", "test message")
            result = pipeline.reset_memory()
            self.assertIn("deleted", result)

    def test_pipeline_personalizes_skill_candidates_without_prompting_full_adaptation(self):
        with tempfile.TemporaryDirectory() as tmp:
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(
                load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            )
            pipeline.profile_store.update_model(
                "context_model",
                "当前处于探索阶段。",
                note="更新情境",
            )
            pipeline.skill_adaptation_store.update(
                "优先选择低认知负荷的类比 Skill。避免一开始堆叠公式。",
                note="新增适配偏好",
            )
            pipeline.retriever.retrieve = lambda query: self._retrieval_context(  # type: ignore[method-assign]
                [self._skill_candidate()]
            )

            turn = pipeline._start_tutor_turn(
                "session_adaptation",
                "请解释一个新概念",
                memory_mode="memory_augmented",
            )
            context = turn["context"]

            self.assertEqual(context["skills"][0]["node_id"], "skill_visual")
            self.assertEqual(context["skill_selection"]["selected_count"], 1)
            self.assertNotIn("优先选择低认知负荷", context["profile_context"])
            self.assertNotIn("避免一开始堆叠公式", context["memory_context_pack"])
            self.assertIn("先给生活化类比", context["memory_context_pack"])

    def test_pipeline_without_skill_injects_only_one_short_fallback_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(
                load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            )
            pipeline.skill_adaptation_store.update(
                "先用直观类比建立理解。随后逐步进入形式化推导。",
                note="新增适配偏好",
            )
            pipeline.retriever.retrieve = lambda query: self._retrieval_context([])  # type: ignore[method-assign]

            turn = pipeline._start_tutor_turn(
                "session_fallback",
                "请解释一个新概念",
                memory_mode="memory_augmented",
            )
            context = turn["context"]

            self.assertEqual(context["skills"], [])
            self.assertEqual(
                context["skill_selection"]["fallback_instruction"],
                "先用直观类比建立理解。",
            )
            self.assertIn("先用直观类比建立理解。", context["memory_context_pack"])
            self.assertNotIn("随后逐步进入形式化推导", context["memory_context_pack"])

    def test_pipeline_reranker_failure_uses_strong_degraded_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            from EduFlowGraph.pipeline import TutorPipeline

            pipeline = TutorPipeline(
                load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            )
            pipeline.retriever.retrieve = lambda query: self._retrieval_context(  # type: ignore[method-assign]
                [self._skill_candidate("skill_degraded")]
            )
            pipeline.skill_reranker.rerank_fn = (  # type: ignore[attr-defined]
                lambda query, documents, kind: (_ for _ in ()).throw(TimeoutError("timeout"))
            )

            context = pipeline._start_tutor_turn(
                "session_degraded",
                "请解释一个新概念",
                memory_mode="memory_augmented",
            )["context"]

            self.assertEqual(context["skills"][0]["node_id"], "skill_degraded")
            self.assertEqual(context["skill_selection"]["reranker_status"], "degraded")


try:
    from fastapi.testclient import TestClient
    from EduFlowGraph.web_app import app
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "fastapi not installed")
class WebAppApiTest(unittest.TestCase):
    def test_health_endpoint(self):
        client = TestClient(app)
        response = client.get("/api/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_cors_preflight(self):
        client = TestClient(app)
        response = client.options(
            "/api/chat",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(200, response.status_code)


if __name__ == "__main__":
    unittest.main()
