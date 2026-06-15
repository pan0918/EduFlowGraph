import json
import tempfile
import unittest
from pathlib import Path

from eduflowgraph.config import load_settings_from_mapping
from eduflowgraph.dataflow import DataFlowStore
from eduflowgraph.episode_detection import EpisodeBoundaryDetector
from eduflowgraph.extractor import HeuristicEpisodeExtractor
from eduflowgraph.graph_store import GraphStore
from eduflowgraph.pipeline import TutorPipeline
from eduflowgraph.prompts import (
    CONCEPT_EXTRACTION_PROMPT,
    EPISODE_EXTRACTION_PROMPT,
    RERANK_FALLBACK_PROMPT,
    SKILL_DISTILLATION_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    TUTOR_USER_PROMPT,
    TUTOR_MEMORY_AUGMENTED_USER_PROMPT,
)
from eduflowgraph.retriever import MemoryRetriever
from eduflowgraph.skill_extractor import (
    DIFFICULTY_PATTERNS,
    TEACHING_ACTIONS,
    HeuristicSkillDistiller,
    HeuristicSkillEvidenceExtractor,
    same_concept_family,
)


class MemoryPipelineTest(unittest.TestCase):
    def _make_episode(self) -> dict:
        return {
            "episode_id": "episode_001",
            "node_id": "episode_001",
            "node_type": "episode",
            "episode_type": "misconception_diagnosis",
            "provenance": {
                "segment_id": "segment_001",
                "session_id": "session_test",
                "source_event_ids": ["event_1", "event_2"],
                "start_time": "2026-06-03T10:00:00Z",
                "end_time": "2026-06-03T10:03:00Z",
            },
            "summary": {
                "title": "检测准确率和后验概率混淆",
                "topic_summary": "学生把检测准确率误当成患病概率。",
                "short_summary": "通过对比解释澄清条件方向。",
            },
            "learner_problem": {
                "student_question": "为什么不能直接把检测准确率当作患病概率？",
                "detected_problem": "学生混淆检测准确率与后验概率。",
                "misconceptions": ["把检测准确率当作后验概率"],
                "understanding_before": "low",
                "difficulty_signals": ["混淆 P(A|B) 与 P(B|A)"],
            },
            "tutor_action": {
                "main_strategy": "contrastive_explanation",
                "strategy_summary": "用自然语言对比两个条件概率。",
                "teaching_steps": ["解释 P(A|B)", "解释 P(B|A)", "做对比"],
                "used_examples": True,
                "used_assessment": False,
            },
            "learning_outcome": {
                "result": "partial_success",
                "understanding_after": "partial",
                "score": 0.64,
                "evidence": "学生能复述方向差异。",
                "needs_follow_up": True,
                "follow_up_suggestion": "补一道练习题。",
            },
            "retrieval": {
                "keywords": ["条件概率", "检测准确率", "后验概率"],
                "embedding_text": "学生把检测准确率误当成患病概率，导师用对比解释纠正。",
            },
            "extraction_metadata": {
                "extractor_version": "episode_extractor_v1",
                "boundary_reason": "learning_goal_completed",
                "boundary_confidence": 0.84,
                "extraction_confidence": 0.78,
                "created_at": "2026-06-03T10:05:40Z",
            },
        }

    def _make_retrieval(
        self,
        text: str,
        *,
        keywords: list[str] | None = None,
        vector: list[float] | None = None,
        model_id: str = "text-embedding-3-small",
        provider: str = "mock",
    ) -> dict:
        return {
            "keywords": keywords or [],
            "embedding_text": text,
            "embedding_vector": vector if vector is not None else [0.8, 0.2],
            "embedding_metadata": {
                "provider": provider,
                "model_id": model_id,
                "dimensions": len(vector if vector is not None else [0.8, 0.2]),
                "created_at": "2026-06-04T00:00:00Z",
            },
        }

    def test_episode_extraction_prompt_includes_type_boundaries_and_outcome_rules(self):
        self.assertIn("## Episode Type Boundary Examples", EPISODE_EXTRACTION_PROMPT)
        self.assertIn("## Learning Outcome Result Rules", EPISODE_EXTRACTION_PROMPT)
        self.assertIn("Prefer `misconception_diagnosis`", EPISODE_EXTRACTION_PROMPT)
        self.assertIn("Use `success` only when", EPISODE_EXTRACTION_PROMPT)
        self.assertIn("Return JSON only.", EPISODE_EXTRACTION_PROMPT)
        self.assertIn('"episode_type": "concept_explanation | problem_solving | misconception_diagnosis | assessment | review | planning | other"', EPISODE_EXTRACTION_PROMPT)
        self.assertIn('"title": string', EPISODE_EXTRACTION_PROMPT)
        self.assertIn('"score": float', EPISODE_EXTRACTION_PROMPT)
        self.assertIn("## Semantic Extraction Goal", EPISODE_EXTRACTION_PROMPT)
        self.assertNotIn('"episode": {', EPISODE_EXTRACTION_PROMPT)
        self.assertNotIn("```json", EPISODE_EXTRACTION_PROMPT)
        self.assertLessEqual(len(EPISODE_EXTRACTION_PROMPT.splitlines()), 130)

    def test_concept_extraction_prompt_uses_schema_style_output(self):
        self.assertIn("## Output", CONCEPT_EXTRACTION_PROMPT)
        self.assertIn("## Decision Heuristics", CONCEPT_EXTRACTION_PROMPT)
        self.assertIn("Return JSON only.", CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"name": string', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"aliases": [string]', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"description": string', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"concept_name": string', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"structural_role": "main | supporting | mentioned"', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"learner_relation": "confused | clarified | neutral"', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"importance_score": float', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"confidence": float', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn('"evidence": string', CONCEPT_EXTRACTION_PROMPT)
        self.assertIn("Do NOT extract teaching methods", CONCEPT_EXTRACTION_PROMPT)
        self.assertIn("Reject candidates like", CONCEPT_EXTRACTION_PROMPT)
        self.assertNotIn("```json", CONCEPT_EXTRACTION_PROMPT)
        self.assertNotIn("Bayes theorem", CONCEPT_EXTRACTION_PROMPT)

    def test_skill_distillation_prompt_requires_chinese_natural_language_fields(self):
        self.assertIn("Keep enum-like labels in English", SKILL_DISTILLATION_PROMPT)
        self.assertIn("Write learner-facing natural-language fields in Chinese", SKILL_DISTILLATION_PROMPT)
        self.assertIn("skill.name", SKILL_DISTILLATION_PROMPT)
        self.assertIn("skill.procedure", SKILL_DISTILLATION_PROMPT)
        self.assertIn("evidence_concept_scope", SKILL_DISTILLATION_PROMPT)
        self.assertNotIn('"concept_scope": [string]', SKILL_DISTILLATION_PROMPT)

    def test_tutor_prompt_is_loaded_from_prompt_folder_and_keeps_chat_direct(self):
        self.assertIn("通用 AI 助手", TUTOR_SYSTEM_PROMPT)
        self.assertIn("直接回答用户的问题", TUTOR_SYSTEM_PROMPT)
        self.assertNotIn("Teaching instruction", TUTOR_SYSTEM_PROMPT)
        self.assertNotIn("小检查", TUTOR_SYSTEM_PROMPT)
        self.assertIn("{user_query}", TUTOR_USER_PROMPT)
        self.assertNotIn("{memory_context}", TUTOR_USER_PROMPT)
        self.assertIn("{user_query}", TUTOR_MEMORY_AUGMENTED_USER_PROMPT)
        self.assertIn("{memory_context}", TUTOR_MEMORY_AUGMENTED_USER_PROMPT)

    def test_rerank_fallback_prompt_is_loaded_from_prompt_folder_and_uses_schema_output(self):
        self.assertIn("Return JSON only.", RERANK_FALLBACK_PROMPT)
        self.assertIn("{kind}", RERANK_FALLBACK_PROMPT)
        self.assertIn("{query}", RERANK_FALLBACK_PROMPT)
        self.assertIn("{candidates_json}", RERANK_FALLBACK_PROMPT)
        self.assertIn('"ordered_ids": [string]', RERANK_FALLBACK_PROMPT)

    def test_dataflow_appends_ledger_events_as_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DataFlowStore(Path(tmp) / "dataflow.jsonl")

            first = store.append_event(
                session_id="session_test",
                turn_index=1,
                actor="student",
                event_type="user_message",
                content="为什么不能直接用检测准确率当作患病概率？",
                correlation_id="corr_1",
            )
            second = store.append_event(
                session_id="session_test",
                turn_index=1,
                actor="assistant",
                event_type="assistant_message",
                content="因为 P(阳性|患病) 不等于 P(患病|阳性)。",
                causation_id=first.event_id,
                correlation_id="corr_1",
            )

            rows = [
                json.loads(line)
                for line in store.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([first.event_id, second.event_id], [row["event_id"] for row in rows])
            self.assertEqual([1, 2], [row["stream_index"] for row in rows])
            self.assertEqual("corr_1", rows[0]["correlation_id"])
            self.assertEqual(first.event_id, rows[1]["causation_id"])
            self.assertIsNone(rows[0]["segment_id"])

    def test_graph_store_persists_concepts_and_episode_concept_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                episode["episode_id"],
                concepts=[
                    {
                        "name": "Bayes theorem",
                        "aliases": ["Bayes rule", "贝叶斯公式"],
                        "description": "A probability rule for updating beliefs.",
                    },
                    {
                        "name": "贝叶斯公式",
                        "aliases": ["Bayes theorem", "贝叶斯定理"],
                        "description": "",
                    },
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                    },
                ],
                edges=[
                    {
                        "target_name": "Bayes theorem",
                        "weight": 0.92,
                        "evidence": "本轮围绕为什么检测准确率不能直接当作后验概率展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.88,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.84,
                        "evidence": "导师对比了 P(A|B) 和 P(B|A)。",
                        "metadata": {
                            "structural_role": "supporting",
                            "learner_relation": "clarified",
                            "confidence": 0.83,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                ],
            )
            self.assertEqual(1, len(graph.nodes_by_type("episode")))
            self.assertEqual(2, len(graph.nodes_by_type("concept")))
            merged = graph.nodes["concept_bayes_theorem"]
            self.assertEqual("Bayes theorem", merged["name"])
            self.assertIn("贝叶斯定理", merged["aliases"])
            self.assertEqual([], list(graph.nodes_by_type("skill").values()))
            self.assertEqual(2, len(graph.edges))
            self.assertEqual(
                ["main", "supporting"],
                [edge["metadata"]["structural_role"] for edge in graph.edges],
            )

    def test_graph_store_canonicalizes_bilingual_concept_variants_across_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            first = self._make_episode()
            second = self._make_episode()
            second["episode_id"] = "episode_002"
            second["node_id"] = "episode_002"
            graph.apply_episode(first, save=False)
            graph.apply_episode(second, save=False)

            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Bayes theorem",
                        "aliases": ["Bayes rule"],
                        "description": "A probability rule for updating beliefs.",
                    }
                ],
                edges=[
                    {
                        "target_name": "Bayes theorem",
                        "weight": 0.9,
                        "evidence": "第一轮用 Bayes theorem 解释后验概率。",
                        "metadata": {"structural_role": "main", "learner_relation": "clarified"},
                    }
                ],
                save=False,
            )
            graph.apply_concept_extraction(
                "episode_002",
                concepts=[
                    {
                        "name": "贝叶斯定理",
                        "aliases": ["贝叶斯公式"],
                        "description": "用先验和似然更新后验概率。",
                    }
                ],
                edges=[
                    {
                        "target_name": "贝叶斯公式",
                        "weight": 0.92,
                        "evidence": "第二轮用贝叶斯公式解释条件反向。",
                        "metadata": {"structural_role": "main", "learner_relation": "clarified"},
                    }
                ],
                save=False,
            )

            concepts = list(graph.nodes_by_type("concept").values())
            self.assertEqual(1, len(concepts))
            self.assertEqual("concept_bayes_theorem", concepts[0]["node_id"])
            self.assertEqual("Bayes theorem", concepts[0]["name"])
            self.assertIn("贝叶斯定理", concepts[0]["aliases"])
            self.assertIn("贝叶斯公式", concepts[0]["aliases"])
            self.assertEqual(
                ["concept_bayes_theorem", "concept_bayes_theorem"],
                [edge["target"] for edge in graph.edges],
            )

    def test_graph_store_normalizes_loaded_legacy_concepts_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            nodes_path = Path(tmp) / "nodes.json"
            edges_path = Path(tmp) / "edges.json"
            nodes_path.write_text(
                json.dumps(
                    {
                        "concept_bayes_theorem": {
                            "concept_id": "concept_bayes_theorem",
                            "node_id": "concept_bayes_theorem",
                            "node_type": "concept",
                            "name": "Bayes theorem",
                            "aliases": ["Bayes rule"],
                            "description": "A probability update rule.",
                        },
                        "concept_legacy_bayes": {
                            "concept_id": "concept_legacy_bayes",
                            "node_id": "concept_legacy_bayes",
                            "node_type": "concept",
                            "name": "贝叶斯定理",
                            "aliases": ["贝叶斯公式"],
                            "description": "",
                        },
                        "skill_direction": {
                            "skill_id": "skill_direction",
                        "node_id": "skill_direction",
                        "node_type": "skill",
                            "name": "Clarify direction confusion through contrastive explanation",
                            "status": "candidate",
                            "trigger": "Use when the learner shows directionally related concepts, conditions, or formulas around Conditional probability.",
                            "concept_scope": ["Conditional probability"],
                            "difficulty_pattern": "direction_confusion",
                            "teaching_actions": ["contrastive_explanation"],
                            "procedure": [
                                "Name the two easily confused objects.",
                                "Explain each object in natural language.",
                                "Contrast them under the same scenario.",
                                "Ask the learner to restate the idea.",
                            ],
                            "success_criteria": [
                                "The learner can explain the directional difference without reversing the two meanings.",
                                "The learner can correctly distinguish the two targets in a fresh scenario.",
                                "The learner can clearly state the difference between the two targets.",
                            ],
                            "metadata": {"source_episode_ids": ["episode_001"]},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            edges_path.write_text(
                json.dumps(
                    [
                        {
                            "edge_id": "edge_legacy_concept",
                            "edge_type": "episode_concept",
                            "source": "episode_001",
                            "target": "concept_legacy_bayes",
                            "weight": 0.9,
                            "evidence": "旧边指向中文贝叶斯节点。",
                            "metadata": {},
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            graph = GraphStore(nodes_path, edges_path)

            concepts = list(graph.nodes_by_type("concept").values())
            self.assertEqual(1, len(concepts))
            self.assertEqual("concept_bayes_theorem", concepts[0]["node_id"])
            self.assertIn("贝叶斯定理", concepts[0]["aliases"])
            self.assertEqual("concept_bayes_theorem", graph.edges[0]["target"])
            skill = graph.nodes["skill_direction"]
            self.assertEqual("用对比解释澄清方向混淆", skill["name"])
            self.assertEqual("当学习者出现有方向性的概念、条件或公式时使用。", skill["trigger"])
            self.assertNotIn("Conditional probability", skill["trigger"])
            self.assertNotIn("concept_scope", skill)
            self.assertEqual(
                ["Conditional probability"],
                skill["metadata"]["evidence_concept_scope"],
            )
            self.assertEqual(
                ["先点名两个容易混淆的对象。", "用自然语言分别解释两个对象。", "放到同一个场景里对比它们。"],
                skill["procedure"],
            )
            self.assertEqual(
                ["学习者能说明两个对象的方向差异，并且不再反着解释。", "学习者能在新场景中正确区分两个目标。"],
                skill["success_criteria"],
            )

    def test_heuristic_episode_extractor_outputs_pure_episode_schema(self):
        extractor = HeuristicEpisodeExtractor()
        events = [
            {
                "event_id": "event_1",
                "session_id": "session_test",
                "timestamp": "2026-06-03T10:00:00Z",
                "actor": "student",
                "content": "为什么不能直接用检测准确率当作患病概率？",
            },
            {
                "event_id": "event_2",
                "session_id": "session_test",
                "timestamp": "2026-06-03T10:01:00Z",
                "actor": "assistant",
                "content": "因为 P(阳性|患病) 不等于 P(患病|阳性)，我们可以先对比这两个条件概率。",
            },
        ]

        episode = extractor.extract(events)

        self.assertEqual(
            {
                "episode_id",
                "node_id",
                "node_type",
                "episode_type",
                "summary",
                "learner_problem",
                "tutor_action",
                "learning_outcome",
            },
            set(episode.keys()),
        )
        self.assertEqual("episode", episode["node_type"])
        self.assertIn(
            episode["episode_type"],
            {
                "concept_explanation",
                "problem_solving",
                "misconception_diagnosis",
                "assessment",
                "review",
                "planning",
                "other",
            },
        )
        self.assertIn(
            episode["learning_outcome"]["result"],
            {"success", "partial_success", "failed", "unresolved"},
        )
        self.assertNotIn("concepts", episode)
        self.assertNotIn("quality", episode)
        self.assertNotIn("student_state", episode)

    def test_skill_evidence_extractor_outputs_closed_taxonomy(self):
        episode = self._make_episode()
        events = [
            {
                "event_id": "event_1",
                "actor": "student",
                "content": "为什么不能直接把检测准确率当作后验概率？我还是分不清 P(A|B) 和 P(B|A)。",
            },
            {
                "event_id": "event_2",
                "actor": "assistant",
                "content": "我们先对比这两个条件概率，再用一个 100 人的小例子检查方向差异。",
            },
        ]

        evidence = HeuristicSkillEvidenceExtractor().extract(
            episode,
            events,
            concept_names=["Bayes theorem", "Conditional probability"],
            concept_ids=["concept_bayes_theorem", "concept_conditional_probability"],
        )

        self.assertEqual("episode_001", evidence["episode_id"])
        self.assertEqual("session_test", evidence["session_id"])
        self.assertIn(evidence["difficulty_pattern"], DIFFICULTY_PATTERNS)
        self.assertGreaterEqual(len(evidence["teaching_actions"]), 1)
        self.assertLessEqual(len(evidence["teaching_actions"]), 4)
        self.assertTrue(
            set(evidence["teaching_actions"]).issubset(set(TEACHING_ACTIONS))
        )
        self.assertEqual(
            ["event_1", "event_2"],
            evidence["source_event_ids"],
        )
        self.assertIn("outcome", evidence)
        self.assertIn("learning_delta", evidence)
        self.assertNotIn("step_by_step_explanation", evidence["teaching_actions"])

    def test_skill_distiller_specializes_symbol_grounding_skill(self):
        distiller = HeuristicSkillDistiller()
        episodes = [
            {
                "episode_id": "episode_symbol_1",
                "summary": {"title": "只记公式但不懂含义"},
            },
            {
                "episode_id": "episode_symbol_2",
                "summary": {"title": "开始能解释公式项的意义"},
            },
        ]
        evidences = [
            {
                "episode_id": "episode_symbol_1",
                "concept_names": ["Policy gradient"],
                "teaching_actions": ["formula_decomposition", "student_self_explanation"],
                "difficulty_pattern": "symbol_grounding",
                "outcome": {"result": "failed", "score": 0.28},
                "evidence_summary": "学生仍然说看不懂公式含义。",
            },
            {
                "episode_id": "episode_symbol_2",
                "concept_names": ["Policy gradient"],
                "teaching_actions": ["formula_decomposition", "student_self_explanation", "diagnostic_check"],
                "difficulty_pattern": "symbol_grounding",
                "outcome": {"result": "success", "score": 0.82},
                "evidence_summary": "学生已经能解释为什么这个项会出现。",
            },
        ]

        distilled = distiller.distill(episodes, evidences, {})

        self.assertIsNotNone(distilled)
        skill = distilled["skill"]
        self.assertEqual("symbol_grounding", skill["difficulty_pattern"])
        self.assertNotIn("Policy gradient", skill["trigger"])
        self.assertNotIn("Policy gradient", skill["embedding_text"])
        self.assertNotIn("concept_scope", skill)
        self.assertIn("Policy gradient", skill["metadata"]["evidence_concept_scope"])
        self.assertLessEqual(len(skill["procedure"]), 3)
        self.assertLessEqual(len(skill["success_criteria"]), 2)
        self.assertIn("符号含义", skill["name"])
        self.assertTrue(
            any("公式" in criterion and "含义" in criterion for criterion in skill["success_criteria"])
        )
        self.assertTrue(
            any("公式" in step or "项" in step for step in skill["procedure"])
        )

    def test_skill_distiller_specializes_transfer_failure_skill(self):
        distiller = HeuristicSkillDistiller()
        episodes = [
            {
                "episode_id": "episode_transfer_1",
                "summary": {"title": "会做原题但不会迁移"},
            },
            {
                "episode_id": "episode_transfer_2",
                "summary": {"title": "开始能迁移到相似题"},
            },
        ]
        evidences = [
            {
                "episode_id": "episode_transfer_1",
                "concept_names": ["Gradient descent"],
                "teaching_actions": ["worked_example", "diagnostic_check"],
                "difficulty_pattern": "transfer_failure",
                "outcome": {"result": "failed", "score": 0.28},
                "evidence_summary": "学生能跟着例题走，但换一个相似题就不会。",
            },
            {
                "episode_id": "episode_transfer_2",
                "concept_names": ["Gradient descent"],
                "teaching_actions": ["worked_example", "diagnostic_check"],
                "difficulty_pattern": "transfer_failure",
                "outcome": {"result": "partial_success", "score": 0.62},
                "evidence_summary": "学生开始能把例题方法迁移到相似题。",
            },
        ]

        distilled = distiller.distill(episodes, evidences, {})

        self.assertIsNotNone(distilled)
        skill = distilled["skill"]
        self.assertEqual("transfer_failure", skill["difficulty_pattern"])
        self.assertNotIn("Gradient descent", skill["trigger"])
        self.assertNotIn("Gradient descent", skill["embedding_text"])
        self.assertNotIn("concept_scope", skill)
        self.assertIn("Gradient descent", skill["metadata"]["evidence_concept_scope"])
        self.assertLessEqual(len(skill["procedure"]), 3)
        self.assertLessEqual(len(skill["success_criteria"]), 2)
        self.assertIn("迁移", skill["name"])
        self.assertNotIn("the learner", skill["trigger"].lower())
        self.assertTrue(
            any("相似" in criterion or "迁移" in criterion for criterion in skill["success_criteria"])
        )

    def test_retriever_returns_concepts_ranked_from_top_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            graph.apply_episode(self._make_episode(), save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Bayes theorem",
                        "aliases": ["Bayes rule", "贝叶斯公式"],
                        "description": "A probability rule for updating beliefs.",
                    },
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                    },
                ],
                edges=[
                    {
                        "target_name": "Bayes theorem",
                        "weight": 0.92,
                        "evidence": "本轮主要解释后验概率不能直接等于检测准确率。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.88,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.84,
                        "evidence": "导师对比了 P(A|B) 和 P(B|A)。",
                        "metadata": {
                            "structural_role": "supporting",
                            "learner_relation": "clarified",
                            "confidence": 0.83,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                ],
            )

            context = MemoryRetriever(graph).retrieve("我还是分不清检测准确率和患病概率")

            self.assertEqual("Bayes theorem", context["concepts"][0]["name"])
            self.assertEqual("Conditional probability", context["concepts"][1]["name"])
            self.assertGreaterEqual(len(context["episodes"]), 1)
            self.assertEqual("episode_001", context["episodes"][0]["node_id"])
            self.assertIn("memory_context_pack", context)
            self.assertIn("Current related concepts", context["memory_context_pack"])

    def test_retriever_returns_skill_and_action_oriented_context_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Bayes theorem and conditional probability confusion",
                keywords=["Bayes theorem", "Conditional probability", "检测准确率"],
                vector=[0.95, 0.05],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Bayes theorem",
                        "aliases": ["Bayes rule", "贝叶斯公式"],
                        "description": "A probability rule for updating beliefs.",
                        "retrieval": self._make_retrieval(
                            "Concept: Bayes theorem. Aliases: Bayes rule, 贝叶斯公式.",
                            keywords=["Bayes theorem", "Bayes rule", "贝叶斯公式"],
                            vector=[0.97, 0.03],
                        ),
                    },
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability. Alias: 条件概率.",
                            keywords=["Conditional probability", "条件概率"],
                            vector=[0.88, 0.12],
                        ),
                    },
                ],
                edges=[
                    {
                        "target_name": "Bayes theorem",
                        "weight": 0.92,
                        "evidence": "本轮主要解释后验概率不能直接等于检测准确率。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.88,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.84,
                        "evidence": "导师对比了 P(A|B) 和 P(B|A)。",
                        "metadata": {
                            "structural_role": "supporting",
                            "learner_relation": "clarified",
                            "confidence": 0.83,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-03T10:00:00Z",
                        },
                    },
                ],
                save=False,
            )
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_direction_confusion",
                    "node_id": "skill_direction_confusion",
                    "node_type": "skill",
                    "name": "Clarify direction confusion through contrastive explanation",
                    "status": "active",
                    "trigger": "Use this skill when the learner confuses directionally related concepts, conditions, or formulas.",
                    "concept_scope": ["Bayes theorem", "Conditional probability"],
                    "difficulty_pattern": "direction_confusion",
                    "teaching_actions": ["contrastive_explanation", "minimal_numeric_example"],
                    "procedure": [
                        "State the two conditional probabilities explicitly.",
                        "Contrast their directions under one scenario.",
                    ],
                    "success_criteria": [
                        "The learner can restate the directional difference.",
                    ],
                    "quality": {
                        "support_episode_count": 2,
                        "validation_success_count": 1,
                        "validation_fail_count": 0,
                        "confidence": 0.84,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_001", "episode_002"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use this skill when the learner struggles with Bayes theorem direction confusion. Teach through contrastive explanation and a short numeric example.",
                        keywords=["direction confusion", "Bayes theorem", "contrastive explanation"],
                        vector=[0.98, 0.02],
                    ),
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_direction_confusion",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_direction_confusion",
                        "weight": 0.91,
                        "evidence": "The learner resolved the direction confusion after contrastive explanation.",
                        "metadata": {
                            "role": "source_evidence",
                            "confidence": 0.87,
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "贝叶斯" in text or "Bayes" in text else [0.7, 0.3],
                rerank_fn=lambda query, candidates, kind: list(reversed(candidates)),
                embedding_signature={
                    "provider": "mock",
                    "model_id": "text-embedding-3-small",
                    "dimensions": 2,
                },
            )
            context = retriever.retrieve("我还是不懂贝叶斯公式，能再对比一下吗？")

            self.assertGreaterEqual(len(context["concepts"]), 1)
            self.assertGreaterEqual(len(context["episodes"]), 1)
            self.assertGreaterEqual(len(context["skills"]), 1)
            self.assertEqual("skill_direction_confusion", context["skills"][0]["node_id"])
            self.assertIn("Recommended pedagogical skill", context["memory_context_pack"])
            self.assertIn("Teaching instruction", context["memory_context_pack"])
            self.assertIn("对比解释", context["memory_context_pack"])

    def test_retriever_ignores_stale_vectors_but_keeps_keyword_and_graph_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability confusion",
                keywords=["条件概率", "检测准确率"],
                vector=[0.1, 0.9],
                model_id="old-embedding-model",
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["Conditional probability", "条件概率"],
                            vector=[0.1, 0.9],
                            model_id="old-embedding-model",
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.88,
                        "evidence": "本轮围绕条件概率展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0],
                embedding_signature={
                    "provider": "mock",
                    "model_id": "text-embedding-3-small",
                    "dimensions": 2,
                },
            )
            context = retriever.retrieve("我还是不懂条件概率")

            self.assertEqual("Conditional probability", context["concepts"][0]["name"])
            self.assertEqual("episode_001", context["episodes"][0]["node_id"])
            self.assertGreaterEqual(context["retrieval_summary"]["stale_vectors"], 1)

    def test_retriever_falls_back_to_keyword_and_graph_matches_when_query_embedding_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": {
                            "keywords": ["Conditional probability", "条件概率"],
                            "embedding_text": "Concept: Conditional probability",
                            "embedding_vector": [],
                            "embedding_metadata": {},
                        },
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_condition_contrast",
                    "node_id": "skill_condition_contrast",
                    "node_type": "skill",
                    "name": "Contrast conditional probability directions",
                    "status": "active",
                    "trigger": "Use this skill when the learner confuses conditional probability directions.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "direction_confusion",
                    "teaching_actions": ["contrastive_explanation"],
                    "procedure": ["Compare P(A|B) and P(B|A) in one scenario."],
                    "success_criteria": ["The learner can restate the direction difference."],
                    "quality": {
                        "support_episode_count": 2,
                        "validation_success_count": 1,
                        "validation_fail_count": 0,
                        "confidence": 0.82,
                    },
                    "retrieval": {
                        "keywords": ["条件概率", "direction confusion", "contrastive explanation"],
                        "embedding_text": "Contrast conditional probability directions.",
                        "embedding_vector": [],
                        "embedding_metadata": {},
                    },
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_condition_contrast",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_condition_contrast",
                        "weight": 0.91,
                        "evidence": "Contrast helped resolve the confusion.",
                        "metadata": {"role": "source_evidence", "confidence": 0.88},
                    }
                ],
                save=False,
            )

            def failing_embedding(_text: str) -> list[float]:
                raise RuntimeError("embedding service unavailable")

            context = MemoryRetriever(graph, embedding_fn=failing_embedding).retrieve(
                "我还是不懂条件概率，P(A|B) 和 P(B|A) 怎么区分？"
            )

            self.assertEqual("Conditional probability", context["concepts"][0]["name"])
            self.assertEqual("episode_001", context["episodes"][0]["node_id"])
            self.assertEqual("skill_condition_contrast", context["skills"][0]["node_id"])
            self.assertIn("embedding service unavailable", context["retrieval_summary"]["embedding_error"])
            self.assertIn("Recommended pedagogical skill", context["memory_context_pack"])

    def test_retriever_matches_chinese_alias_without_relying_on_embeddings(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = {
                "keywords": ["条件概率", "检测准确率"],
                "embedding_text": "学生混淆条件概率和后验概率。",
                "embedding_vector": [],
                "embedding_metadata": {},
            }
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": {
                            "keywords": ["Conditional probability", "条件概率"],
                            "embedding_text": "Concept: Conditional probability",
                            "embedding_vector": [],
                            "embedding_metadata": {},
                        },
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            context = MemoryRetriever(graph, embedding_fn=None).retrieve("我还是不懂条件概率为什么这样算")

            self.assertEqual("Conditional probability", context["concepts"][0]["name"])
            self.assertEqual("episode_001", context["episodes"][0]["node_id"])

    def test_retriever_falls_back_to_direct_episode_search_when_concept_recall_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["episode_id"] = "episode_pg_001"
            episode["node_id"] = "episode_pg_001"
            episode["summary"]["title"] = "log-derivative trick 推导"
            episode["summary"]["short_summary"] = "学生卡在 log-derivative trick 的由来。"
            episode["retrieval"] = self._make_retrieval(
                "Student struggled with the log-derivative trick in policy gradient derivation.",
                keywords=["policy gradient", "log-derivative trick", "策略梯度"],
                vector=[],
            )
            graph.apply_episode(episode, save=False)

            context = MemoryRetriever(graph, embedding_fn=None).retrieve("我还是不理解策略梯度里的 log trick")

            self.assertEqual("episode_pg_001", context["episodes"][0]["node_id"])
            self.assertEqual([], context["concepts"])
            self.assertIn("Relevant past episodes", context["memory_context_pack"])

    def test_retriever_does_not_surface_unrelated_concepts_from_prior_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Bayes theorem",
                        "aliases": ["Bayes rule"],
                        "description": "A probability rule for updating beliefs.",
                        "retrieval": {
                            "keywords": ["Bayes theorem", "Bayes rule"],
                            "embedding_text": "Concept: Bayes theorem",
                            "embedding_vector": [],
                            "embedding_metadata": {},
                        },
                    }
                ],
                edges=[
                    {
                        "target_name": "Bayes theorem",
                        "weight": 0.9,
                        "evidence": "本轮围绕贝叶斯定理展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            context = MemoryRetriever(graph, embedding_fn=None).retrieve("我想复习导数的几何意义")

            self.assertEqual([], context["concepts"])

    def test_fallback_boundary_waits_for_confirmation_and_auto_extracts_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 2}
            )
            pipeline = TutorPipeline(settings)

            pipeline.handle_user_message("session_a", "请解释一下条件概率。")
            pipeline.handle_user_message("session_b", "请解释一下导数。")
            pipeline.handle_user_message("session_a", "再举一个条件概率例子。")
            result = pipeline.handle_user_message("session_a", "我还是想再听一个例子。")

            self.assertFalse(result["boundary"]["decision"]["should_end"])
            self.assertEqual(6, len(pipeline.buffer.events_by_session["session_a"]))
            self.assertEqual(2, len(pipeline.buffer.events_by_session["session_b"]))
            self.assertEqual(0, len(pipeline.graph.nodes_by_type("episode")))

            confirmed = pipeline.handle_user_message(
                "session_a",
                "我明白了，这样用例子解释条件概率就清楚了。",
            )

            self.assertTrue(confirmed["boundary"]["decision"]["should_end"])
            self.assertEqual([], pipeline.buffer.events_by_session["session_a"])
            self.assertEqual(1, len(pipeline.graph.nodes_by_type("episode")))
            self.assertGreaterEqual(len(pipeline.graph.nodes_by_type("concept")), 1)
            self.assertEqual([], list(pipeline.graph.nodes_by_type("skill").values()))
            self.assertGreaterEqual(len(pipeline.graph.edges), 1)

            ledger = pipeline.dataflow.list_events("session_a")
            self.assertTrue(any(event["event_type"] == "boundary_evaluated" for event in ledger))
            self.assertTrue(any(event["event_type"] == "segment_closed" for event in ledger))
            self.assertTrue(any(event["event_type"] == "episode_extraction_completed" for event in ledger))
            self.assertTrue(any(event["event_type"] == "concept_extraction_completed" for event in ledger))
            episode_event = next(
                event for event in ledger if event["event_type"] == "episode_extraction_completed"
            )
            episode = episode_event["metadata"]["episode"]
            self.assertIn("provenance", episode)
            self.assertIn("retrieval", episode)
            self.assertIn("extraction_metadata", episode)
            self.assertIn("embedding_vector", episode["retrieval"])
            self.assertIn("embedding_metadata", episode["retrieval"])
            self.assertNotIn("concepts", episode)
            concept_event = next(
                event for event in ledger if event["event_type"] == "concept_extraction_completed"
            )
            self.assertGreaterEqual(len(concept_event["metadata"]["concepts"]), 1)
            self.assertGreaterEqual(len(concept_event["metadata"]["edges"]), 1)
            self.assertIn("retrieval", concept_event["metadata"]["concepts"][0])
            evidence_event = next(
                event for event in ledger if event["event_type"] == "skill_evidence_recorded"
            )
            self.assertEqual(
                episode_event["metadata"]["episode_id"],
                evidence_event["metadata"]["evidence"]["episode_id"],
            )
            self.assertGreaterEqual(
                len(evidence_event["metadata"]["evidence"]["source_event_ids"]), 1
            )
            self.assertFalse(
                any(event["event_type"] == "skill_distillation_completed" for event in ledger)
            )

    def test_pipeline_waits_for_student_confirmation_before_extracting_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_student_loop"

            pipeline.handle_user_message(session_id, "向我详细解释一下大数定律是什么？")
            second = pipeline.handle_user_message(
                session_id,
                "概念有点太多太复杂了，我是一个高中生，能不能通俗，多举一些例子向我解释？",
            )

            self.assertFalse(second["boundary"]["decision"]["should_end"])
            self.assertEqual(4, len(pipeline.buffer.events_by_session[session_id]))
            self.assertEqual(0, len(pipeline.graph.nodes_by_type("episode")))

            third = pipeline.handle_user_message(
                session_id,
                "我明白了，还是这样举例子的方法来的明了一点",
            )

            self.assertTrue(third["boundary"]["decision"]["should_end"])
            self.assertEqual([], pipeline.buffer.events_by_session[session_id])
            self.assertEqual(1, len(pipeline.graph.nodes_by_type("episode")))

            segment_event = next(
                event
                for event in pipeline.dataflow.list_events(session_id)
                if event["event_type"] == "segment_closed"
            )
            source_events = segment_event["metadata"]["event_refs"]
            self.assertEqual(6, len(source_events))
            self.assertEqual(
                [
                    "user_message",
                    "assistant_message",
                    "user_message",
                    "assistant_message",
                    "user_message",
                    "assistant_message",
                ],
                [
                    event["event_type"]
                    for event in pipeline.dataflow.events_by_ids(source_events)
                ],
            )

    def test_pipeline_keeps_assessment_and_confirmation_in_one_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_factorization"

            pipeline.handle_user_message(session_id, "向我解释一下什么是因式分解吧")
            pipeline.handle_user_message(session_id, "我还有点一知半解，你给我出点题目吧")
            pipeline.handle_user_message(session_id, "1.4x")
            fourth = pipeline.handle_user_message(
                session_id,
                "1. 4x(x-3) 2.(a-5)(a+5) 3.(y+5)(y+5) 4.(x+3)(x+4)",
            )

            self.assertFalse(fourth["boundary"]["decision"]["should_end"])
            self.assertEqual(8, len(pipeline.buffer.events_by_session[session_id]))
            self.assertEqual(0, len(pipeline.graph.nodes_by_type("episode")))

            fifth = pipeline.handle_user_message(
                session_id,
                "好我完全明白了，还是这种给我举例子的方式我学的快！",
            )

            self.assertTrue(fifth["boundary"]["decision"]["should_end"])
            self.assertEqual(1, len(pipeline.graph.nodes_by_type("episode")))
            segment_event = next(
                event
                for event in pipeline.dataflow.list_events(session_id)
                if event["event_type"] == "segment_closed"
            )
            self.assertEqual(10, len(segment_event["metadata"]["event_refs"]))

    def test_topic_shift_closes_previous_episode_and_keeps_new_messages_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_topic_shift"

            pipeline.handle_user_message(session_id, "为什么不能直接把检测准确率当作后验概率？")
            pipeline.handle_user_message(session_id, "我还是不懂 P(A|B) 和 P(B|A) 的区别。")
            shifted = pipeline.handle_user_message(session_id, "先换个话题，请解释一下导数。")

            self.assertTrue(shifted["boundary"]["decision"]["should_end"])
            self.assertEqual("topic_shift", shifted["boundary"]["decision"]["reason"])
            self.assertEqual(
                "exclude_new_messages",
                shifted["boundary"]["decision"]["closed_event_policy"],
            )
            self.assertEqual(1, len(pipeline.graph.nodes_by_type("episode")))
            self.assertEqual(2, len(pipeline.buffer.events_by_session[session_id]))

            segment_event = next(
                event
                for event in pipeline.dataflow.list_events(session_id)
                if event["event_type"] == "segment_closed"
            )
            self.assertEqual(4, len(segment_event["metadata"]["event_refs"]))
            open_contents = [
                event["content"]
                for event in pipeline.buffer.events_by_session[session_id]
            ]
            self.assertIn("先换个话题，请解释一下导数。", open_contents)

    def test_short_closure_without_learning_content_does_not_create_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)

            result = pipeline.handle_user_message("session_empty_closure", "懂了，谢谢。")

            self.assertFalse(result["boundary"]["decision"]["should_end"])
            self.assertEqual(0, len(pipeline.graph.nodes_by_type("episode")))
            self.assertEqual(2, len(pipeline.buffer.events_by_session["session_empty_closure"]))

    def test_concept_sanitizer_keeps_grounded_domain_concepts_and_rejects_pseudo_concepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            episode = self._make_episode()
            events = [
                {
                    "event_id": "event_1",
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "我分不清 P(A|B) 和 P(B|A)，条件概率方向总是混。",
                }
            ]
            payload = {
                "concepts": [
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率", "P(A|B)", "P(B|A)"],
                        "description": "Probability under a known condition.",
                    },
                    {
                        "name": "Worked example",
                        "aliases": ["例题讲解"],
                        "description": "A teaching method.",
                    },
                    {
                        "name": "Student confidence",
                        "aliases": ["学生信心"],
                        "description": "Learner affect.",
                    },
                    {
                        "name": "Bayes formula method",
                        "aliases": [],
                        "description": "Ungrounded vague method wording.",
                    },
                ],
                "edges": [
                    {
                        "concept_name": "Conditional probability",
                        "structural_role": "main",
                        "learner_relation": "confused",
                        "importance_score": 0.91,
                        "confidence": 0.88,
                        "evidence": "学生混淆 P(A|B) 和 P(B|A) 的条件方向。",
                    },
                    {
                        "concept_name": "Worked example",
                        "structural_role": "supporting",
                        "learner_relation": "neutral",
                        "importance_score": 0.95,
                        "confidence": 0.9,
                        "evidence": "导师使用例题讲解。",
                    },
                    {
                        "concept_name": "Student confidence",
                        "structural_role": "supporting",
                        "learner_relation": "neutral",
                        "importance_score": 0.95,
                        "confidence": 0.9,
                        "evidence": "学生说自己更有信心。",
                    },
                    {
                        "concept_name": "Bayes formula method",
                        "structural_role": "supporting",
                        "learner_relation": "neutral",
                        "importance_score": 0.9,
                        "confidence": 0.9,
                        "evidence": "没有在本轮明确落地。",
                    },
                ],
            }

            sanitized = pipeline._sanitize_concept_payload(
                payload,
                episode=episode,
                events=events,
            )

            self.assertEqual(
                ["Conditional probability"],
                [concept["name"] for concept in sanitized["concepts"]],
            )
            self.assertEqual(
                ["Conditional probability"],
                [edge["target_name"] for edge in sanitized["edges"]],
            )

    def test_pipeline_distills_skill_from_repeated_independent_episodes_and_replays_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_skill"

            pipeline.handle_user_message(session_id, "为什么不能直接把检测准确率当作后验概率？")
            pipeline.handle_user_message(session_id, "我还是不懂 P(A|B) 和 P(B|A) 的区别。")
            pipeline.handle_user_message(session_id, "懂了，我现在能说出这两个条件概率的方向差异。")
            self.assertEqual(1, len(pipeline.graph.nodes_by_type("episode")))
            self.assertEqual(0, len(pipeline.graph.nodes_by_type("skill")))

            pipeline.handle_user_message(session_id, "我又混淆了 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "请再用对比方式解释 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "懂了，这次我可以自己解释这两个方向了。")

            skills = list(pipeline.graph.nodes_by_type("skill").values())
            self.assertEqual(1, len(skills))
            skill = skills[0]
            self.assertEqual("candidate", skill["status"])
            self.assertEqual("direction_confusion", skill["difficulty_pattern"])
            self.assertIn("有方向性的概念", skill["trigger"])
            self.assertNotIn("directionally related", skill["trigger"])
            self.assertGreaterEqual(skill["quality"]["support_episode_count"], 2)
            self.assertEqual(0, skill["quality"]["validation_success_count"])
            self.assertIn("metadata", skill)
            self.assertGreaterEqual(len(skill["metadata"]["source_episode_ids"]), 2)
            self.assertIn("retrieval", skill)
            self.assertIn("embedding_vector", skill["retrieval"])

            skill_edges = [
                edge for edge in pipeline.graph.edges if edge["edge_type"] == "episode_skill"
            ]
            self.assertEqual(2, len(skill_edges))
            self.assertEqual(
                {"source_evidence"},
                {edge["metadata"]["role"] for edge in skill_edges},
            )

            ledger = pipeline.dataflow.list_events(session_id)
            self.assertTrue(
                any(event["event_type"] == "skill_distillation_completed" for event in ledger)
            )

            replayed = TutorPipeline(settings)
            replayed_skills = list(replayed.graph.nodes_by_type("skill").values())
            self.assertEqual(1, len(replayed_skills))
            self.assertEqual(skill["node_id"], replayed_skills[0]["node_id"])
            replayed_edges = [
                edge for edge in replayed.graph.edges if edge["edge_type"] == "episode_skill"
            ]
            self.assertEqual(2, len(replayed_edges))

    def test_concept_family_matching_groups_probability_conditioning_aliases(self):
        self.assertTrue(
            same_concept_family(
                ["Conditional Probability", "Base Rate"],
                ["Conditional Probability Directionality", "Base Rate Fallacy"],
            )
        )
        self.assertTrue(
            same_concept_family(
                ["贝叶斯定理"],
                ["Conditional Probability Directionality", "Base Rate Fallacy"],
            )
        )

    def test_refresh_backfills_skill_from_cross_session_related_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)

            def seed_closed_segment(
                *,
                session_id: str,
                segment_id: str,
                episode_id: str,
                concept_names: list[str],
                actions: list[str],
                title: str,
            ) -> None:
                user = pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=1,
                    actor="student",
                    event_type="user_message",
                    content="我总是分不清 P(A|B) 和 P(B|A)。",
                )
                assistant = pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=1,
                    actor="assistant",
                    event_type="assistant_message",
                    content="我们用同一个场景对比两个条件概率的分母。",
                    causation_id=user.event_id,
                )
                pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=1,
                    actor="system",
                    event_type="segment_closed",
                    content=title,
                    segment_id=segment_id,
                    metadata={
                        "decision": {
                            "should_end": True,
                            "reason": "learning_goal_completed",
                            "boundary_position": "after_new_messages",
                            "closed_event_policy": "include_new_messages",
                        },
                        "event_refs": [user.event_id, assistant.event_id],
                    },
                )
                episode = json.loads(json.dumps(self._make_episode()))
                episode["episode_id"] = episode_id
                episode["node_id"] = episode_id
                episode["provenance"]["session_id"] = session_id
                episode["provenance"]["source_event_ids"] = [user.event_id, assistant.event_id]
                episode["summary"]["title"] = title
                episode["summary"]["short_summary"] = f"{title}。"
                episode["learning_outcome"] = {
                    "result": "success",
                    "understanding_after": "good",
                    "score": 0.92,
                    "evidence": "学生能正确说出条件概率方向差异。",
                    "needs_follow_up": False,
                    "follow_up_suggestion": "",
                }
                pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=2,
                    actor="memory_agent",
                    event_type="episode_extraction_completed",
                    content=episode["summary"]["short_summary"],
                    segment_id=segment_id,
                    metadata={
                        "segment_id": segment_id,
                        "episode_id": episode_id,
                        "episode": episode,
                    },
                )
                pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=3,
                    actor="memory_agent",
                    event_type="concept_extraction_completed",
                    content="，".join(concept_names),
                    segment_id=segment_id,
                    metadata={
                        "episode_id": episode_id,
                        "concepts": [
                            {
                                "name": name,
                                "aliases": [],
                                "description": "A probability conditioning concept.",
                            }
                            for name in concept_names
                        ],
                        "edges": [
                            {
                                "target_name": concept_names[0],
                                "weight": 0.9,
                                "evidence": "本轮围绕条件概率方向混淆展开。",
                                "metadata": {
                                    "structural_role": "main",
                                    "learner_relation": "confused",
                                    "confidence": 0.9,
                                },
                            }
                        ],
                    },
                )
                pipeline.dataflow.append_event(
                    session_id=session_id,
                    turn_index=4,
                    actor="memory_agent",
                    event_type="skill_evidence_recorded",
                    content=",".join(actions),
                    segment_id=segment_id,
                    metadata={
                        "episode_id": episode_id,
                        "evidence": {
                            "episode_id": episode_id,
                            "session_id": session_id,
                            "concept_ids": [],
                            "concept_names": concept_names,
                            "teaching_actions": actions,
                            "difficulty_pattern": "direction_confusion",
                            "outcome": {
                                "result": "success",
                                "score": 0.92,
                                "understanding_after": "good",
                            },
                            "learning_delta": True,
                            "evidence_summary": "学生能正确说出条件概率方向差异。",
                            "source_event_ids": [user.event_id, assistant.event_id],
                        },
                    },
                )

            seed_closed_segment(
                session_id="session_first",
                segment_id="segment_first",
                episode_id="episode_first",
                concept_names=["Conditional Probability", "Base Rate"],
                actions=["contrastive_explanation", "worked_example", "student_self_explanation"],
                title="疾病检测中的条件概率方向混淆",
            )
            seed_closed_segment(
                session_id="session_second",
                segment_id="segment_second",
                episode_id="episode_second",
                concept_names=["贝叶斯定理"],
                actions=[
                    "contrastive_explanation",
                    "step_by_step_explanation",
                    "worked_example",
                    "student_self_explanation",
                ],
                title="工厂次品来源中的后验概率判断",
            )
            seed_closed_segment(
                session_id="session_third",
                segment_id="segment_third",
                episode_id="episode_third",
                concept_names=["Conditional Probability Directionality", "Base Rate Fallacy"],
                actions=["contrastive_explanation", "student_self_explanation"],
                title="竞赛成绩场景中的条件概率方向混淆",
            )

            replayed = TutorPipeline(settings)

            skills = list(replayed.graph.nodes_by_type("skill").values())
            self.assertEqual(1, len(skills))
            skill = skills[0]
            self.assertEqual("direction_confusion", skill["difficulty_pattern"])
            self.assertGreaterEqual(skill["quality"]["support_episode_count"], 2)
            self.assertNotIn("concept_scope", skill)
            self.assertIn(
                "Conditional Probability",
                skill["metadata"]["evidence_concept_scope"],
            )
            self.assertTrue(
                any(
                    event["event_type"] == "skill_distillation_completed"
                    for event in replayed.dataflow.list_events()
                )
            )

    def test_pipeline_can_rebuild_retrieval_embeddings_and_refresh_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {
                    "data_dir": tmp,
                    "provider": "mock",
                    "extraction_turns": 4,
                    "runtime": {
                        "embedding": {
                            "provider": "mock",
                            "name": "Mock Embedding",
                            "endpoint_url": "",
                            "api_key": "",
                            "model_id": "embed-v1",
                        }
                    },
                }
            )
            pipeline = TutorPipeline(settings)
            pipeline.handle_user_message("session_rebuild", "请解释一下条件概率。")
            pipeline.handle_user_message("session_rebuild", "再举一个条件概率例子。")
            pipeline.handle_user_message("session_rebuild", "我明白了，这样举例子就清楚了。")

            concept = next(iter(pipeline.graph.nodes_by_type("concept").values()))
            concept["retrieval"]["embedding_metadata"]["model_id"] = "stale-model"
            pipeline.graph.save()

            stats = pipeline.rebuild_retrieval_embeddings()

            refreshed = next(iter(pipeline.graph.nodes_by_type("concept").values()))
            self.assertEqual("embed-v1", refreshed["retrieval"]["embedding_metadata"]["model_id"])
            self.assertGreaterEqual(stats["rebuilt_nodes"], 1)

    def test_context_pack_summarizes_learning_progression_instead_of_listing_conflicting_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 2}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_progress"

            pipeline.handle_user_message(session_id, "为什么不能直接把检测准确率当作后验概率？")
            pipeline.handle_user_message(session_id, "我还是不懂 P(A|B) 和 P(B|A) 的区别。")
            pipeline.handle_user_message(session_id, "先换个话题，请解释一下导数。")
            pipeline.handle_user_message(session_id, "我明白导数了。")
            pipeline.handle_user_message(session_id, "我又分不清 P(A|B) 和 P(B|A) 了。")
            pipeline.handle_user_message(session_id, "请再对比一下 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "懂了，我现在能说出这两个条件概率的方向差异。")

            context = pipeline.retriever.retrieve("我又分不清 P(A|B) 和 P(B|A) 了，能换个方式再讲吗？")

            self.assertIn("Learner history:", context["memory_context_pack"])
            self.assertIn("previously", context["memory_context_pack"].lower())
            self.assertIn("later", context["memory_context_pack"].lower())
            self.assertNotIn("学生明确表达已经理解。", context["memory_context_pack"])

    def test_skill_recall_prefers_active_validated_skill_with_matching_difficulty_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability direction confusion around P(A|B) and P(B|A).",
                keywords=["Conditional probability", "P(A|B)", "P(B|A)"],
                vector=[0.95, 0.05],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["Conditional probability", "条件概率"],
                            vector=[0.92, 0.08],
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率方向差异展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_direction_active",
                    "node_id": "skill_direction_active",
                    "node_type": "skill",
                    "name": "Clarify direction confusion through contrastive explanation",
                    "status": "active",
                    "trigger": "Use when the learner confuses directionally related concepts, conditions, or formulas.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "direction_confusion",
                    "teaching_actions": ["contrastive_explanation", "minimal_numeric_example"],
                    "procedure": ["Contrast the two conditional meanings.", "Use one small-count example."],
                    "success_criteria": ["The learner can state the directional difference."],
                    "quality": {
                        "support_episode_count": 3,
                        "validation_success_count": 2,
                        "validation_fail_count": 0,
                        "confidence": 0.88,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_001"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use this skill when the learner confuses P(A|B) and P(B|A).",
                        keywords=["direction confusion", "P(A|B)", "P(B|A)"],
                        vector=[0.93, 0.07],
                    ),
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_direction_active",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_direction_active",
                        "weight": 0.9,
                        "evidence": "This strategy resolved the direction confusion.",
                        "metadata": {"role": "source_evidence", "confidence": 0.9},
                    }
                ],
                save=False,
            )
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_abstraction_candidate",
                    "node_id": "skill_abstraction_candidate",
                    "node_type": "skill",
                    "name": "Ground abstract ideas through concrete examples",
                    "status": "candidate",
                    "trigger": "Use when the learner lacks intuition for an abstract concept.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "abstraction_gap",
                    "teaching_actions": ["minimal_numeric_example"],
                    "procedure": ["Give a concrete example.", "Map it back to the concept."],
                    "success_criteria": ["The learner gains intuition for the concept."],
                    "quality": {
                        "support_episode_count": 2,
                        "validation_success_count": 0,
                        "validation_fail_count": 0,
                        "confidence": 0.62,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_009"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use concrete examples for abstract probability ideas.",
                        keywords=["concrete example", "intuition"],
                        vector=[0.99, 0.01],
                    ),
                },
                edges=[],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "P(A|B)" in text or "P(B|A)" in text or "条件概率" in text else [0.2, 0.8],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("我又分不清 P(A|B) 和 P(B|A) 了，能换个方式再讲吗？")

            self.assertEqual("skill_direction_active", context["skills"][0]["node_id"])

    def test_teaching_instruction_changes_for_assessment_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability explanation with a diagnostic check.",
                keywords=["条件概率", "检查"],
                vector=[0.9, 0.1],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_direction_check",
                    "node_id": "skill_direction_check",
                    "node_type": "skill",
                    "name": "Clarify direction confusion through contrastive explanation",
                    "status": "active",
                    "trigger": "Use when the learner confuses directionally related concepts, conditions, or formulas.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "direction_confusion",
                    "teaching_actions": ["contrastive_explanation", "diagnostic_check"],
                    "procedure": ["Contrast the two meanings.", "Ask the learner to explain the difference."],
                    "success_criteria": ["The learner can explain the directional difference."],
                    "quality": {
                        "support_episode_count": 3,
                        "validation_success_count": 2,
                        "validation_fail_count": 0,
                        "confidence": 0.85,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_001"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use this skill to contrast P(A|B) and P(B|A) and then run a short diagnostic check.",
                        keywords=["diagnostic check", "P(A|B)", "P(B|A)"],
                        vector=[0.92, 0.08],
                    ),
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_direction_check",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_direction_check",
                        "weight": 0.9,
                        "evidence": "This strategy resolved the direction confusion.",
                        "metadata": {"role": "source_evidence", "confidence": 0.9},
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "条件概率" in text or "检查" in text else [0.5, 0.5],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("你先别重新讲，先检查一下我是不是真的懂了条件概率。")

            self.assertIn("check", context["memory_context_pack"].lower())
            self.assertIn("before re-teaching", context["memory_context_pack"].lower())

    def test_comparison_intent_prefers_contrastive_skill_and_comparison_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability direction confusion around P(A|B) and P(B|A).",
                keywords=["条件概率", "P(A|B)", "P(B|A)", "区别"],
                vector=[0.94, 0.06],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["条件概率", "Conditional probability"],
                            vector=[0.93, 0.07],
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕 P(A|B) 和 P(B|A) 的区别展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_contrastive",
                    "node_id": "skill_contrastive",
                    "node_type": "skill",
                    "name": "Clarify direction confusion through contrastive explanation",
                    "status": "active",
                    "trigger": "Use when the learner confuses directionally related concepts, conditions, or formulas.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "direction_confusion",
                    "teaching_actions": ["contrastive_explanation", "diagnostic_check"],
                    "procedure": ["Name the two conditional meanings.", "Contrast them under one scenario."],
                    "success_criteria": ["The learner can explain the directional difference."],
                    "quality": {
                        "support_episode_count": 3,
                        "validation_success_count": 1,
                        "validation_fail_count": 0,
                        "confidence": 0.84,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_001"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use contrastive explanation to compare P(A|B) and P(B|A).",
                        keywords=["compare", "contrast", "P(A|B)", "P(B|A)"],
                        vector=[0.95, 0.05],
                    ),
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_contrastive",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_contrastive",
                        "weight": 0.9,
                        "evidence": "This strategy resolved the direction confusion.",
                        "metadata": {"role": "source_evidence", "confidence": 0.9},
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "P(A|B)" in text or "条件概率" in text else [0.2, 0.8],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("你帮我比较一下 P(A|B) 和 P(B|A) 到底差在哪")

            self.assertEqual("skill_contrastive", context["skills"][0]["node_id"])
            self.assertIn("compare", context["memory_context_pack"].lower())
            self.assertIn("contrast", context["memory_context_pack"].lower())

    def test_worked_example_intent_prefers_example_heavy_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Learner needed a small numeric example to understand conditional probability.",
                keywords=["条件概率", "例子", "数字"],
                vector=[0.9, 0.1],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_skill_distillation(
                skill={
                    "skill_id": "skill_numeric_example",
                    "node_id": "skill_numeric_example",
                    "node_type": "skill",
                    "name": "Ground conditional probability through a minimal numeric example",
                    "status": "active",
                    "trigger": "Use when the learner needs a concrete entry point before the formula.",
                    "concept_scope": ["Conditional probability"],
                    "difficulty_pattern": "symbol_grounding",
                    "teaching_actions": ["minimal_numeric_example", "step_by_step_explanation"],
                    "procedure": ["Start with a 100-person example.", "Map each number back to the symbols."],
                    "success_criteria": ["The learner can explain what each term means."],
                    "quality": {
                        "support_episode_count": 3,
                        "validation_success_count": 2,
                        "validation_fail_count": 0,
                        "confidence": 0.86,
                    },
                    "metadata": {
                        "created_at": "2026-06-04T00:00:00Z",
                        "updated_at": "2026-06-04T00:00:00Z",
                        "extractor_version": "skill_distiller_v1",
                        "source_episode_ids": ["episode_001"],
                    },
                    "retrieval": self._make_retrieval(
                        "Use a small worked example before introducing the formula symbols.",
                        keywords=["example", "worked example", "formula meaning"],
                        vector=[0.91, 0.09],
                    ),
                },
                edges=[
                    {
                        "edge_id": "edge_episode_001_skill_numeric_example",
                        "edge_type": "episode_skill",
                        "source": "episode_001",
                        "target": "skill_numeric_example",
                        "weight": 0.9,
                        "evidence": "A small numeric example clarified the formula.",
                        "metadata": {"role": "source_evidence", "confidence": 0.9},
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "例子" in text or "公式" in text else [0.4, 0.6],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("不要只讲定义，先给我一个具体例子再解释这个公式每一项是什么意思")

            self.assertEqual("skill_numeric_example", context["skills"][0]["node_id"])
            self.assertIn("example", context["memory_context_pack"].lower())
            self.assertIn("before", context["memory_context_pack"].lower())

    def test_retrieval_summary_exposes_structured_match_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability direction confusion around P(A|B) and P(B|A).",
                keywords=["条件概率", "P(A|B)", "P(B|A)"],
                vector=[0.95, 0.05],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["条件概率", "Conditional probability"],
                            vector=[0.92, 0.08],
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率方向差异展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "条件概率" in text or "P(A|B)" in text else [0.4, 0.6],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("我还是分不清 P(A|B) 和 P(B|A)")

            self.assertIn("top_matches", context["retrieval_summary"])
            self.assertGreaterEqual(len(context["retrieval_summary"]["top_matches"]["episodes"]), 1)
            top_episode = context["retrieval_summary"]["top_matches"]["episodes"][0]
            self.assertIn("match_reasons", top_episode)
            self.assertIn("matched_difficulty", top_episode)
            self.assertIn("intent", top_episode)

    def test_comparison_intent_without_skill_still_generates_comparison_fallback_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability direction confusion around P(A|B) and P(B|A).",
                keywords=["条件概率", "P(A|B)", "P(B|A)", "区别"],
                vector=[0.95, 0.05],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["条件概率", "Conditional probability"],
                            vector=[0.92, 0.08],
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率方向差异展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "条件概率" in text or "P(A|B)" in text else [0.3, 0.7],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("你帮我比较一下 P(A|B) 和 P(B|A) 到底差在哪")

            self.assertEqual([], context["skills"])
            self.assertIn("compare", context["memory_context_pack"].lower())

    def test_worked_example_intent_without_skill_still_generates_example_fallback_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Learner needed a small numeric example to understand conditional probability.",
                keywords=["条件概率", "例子", "数字"],
                vector=[0.9, 0.1],
            )
            graph.apply_episode(episode, save=False)

            retriever = MemoryRetriever(
                graph,
                embedding_fn=lambda text: [1.0, 0.0] if "例子" in text or "公式" in text else [0.4, 0.6],
                embedding_signature={"provider": "mock", "model_id": "text-embedding-3-small", "dimensions": 2},
            )
            context = retriever.retrieve("先给我一个具体例子再解释这个公式每一项是什么意思")

            self.assertEqual([], context["skills"])
            self.assertIn("example", context["memory_context_pack"].lower())

    def test_retriever_computes_query_embedding_once_per_retrieve(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = GraphStore(Path(tmp) / "nodes.json", Path(tmp) / "edges.json")
            episode = self._make_episode()
            episode["retrieval"] = self._make_retrieval(
                "Conditional probability confusion",
                keywords=["条件概率", "检测准确率"],
                vector=[1.0, 0.0],
            )
            graph.apply_episode(episode, save=False)
            graph.apply_concept_extraction(
                "episode_001",
                concepts=[
                    {
                        "name": "Conditional probability",
                        "aliases": ["条件概率"],
                        "description": "The probability of an event under a condition.",
                        "retrieval": self._make_retrieval(
                            "Concept: Conditional probability",
                            keywords=["条件概率", "Conditional probability"],
                            vector=[1.0, 0.0],
                        ),
                    }
                ],
                edges=[
                    {
                        "target_name": "Conditional probability",
                        "weight": 0.9,
                        "evidence": "本轮围绕条件概率展开。",
                        "metadata": {
                            "structural_role": "main",
                            "learner_relation": "confused",
                            "confidence": 0.9,
                            "extractor_version": "concept_extractor_v1",
                            "created_at": "2026-06-04T00:00:00Z",
                        },
                    }
                ],
                save=False,
            )
            calls = {"count": 0}

            def embedding_fn(text: str) -> list[float]:
                calls["count"] += 1
                return [1.0, 0.0]

            retriever = MemoryRetriever(graph, embedding_fn=embedding_fn)
            retriever.retrieve("我还是不懂条件概率")

            self.assertEqual(1, calls["count"])

    def test_positive_validation_promotes_skill_and_failed_validation_adds_no_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)
            session_id = "session_validate"

            pipeline.handle_user_message(session_id, "为什么不能直接把检测准确率当作后验概率？")
            pipeline.handle_user_message(session_id, "我还是不懂 P(A|B) 和 P(B|A) 的区别。")
            pipeline.handle_user_message(session_id, "懂了，我现在能说出这两个条件概率的方向差异。")

            pipeline.handle_user_message(session_id, "我又混淆了 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "请再用对比方式解释 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "懂了，这次我可以自己解释这两个方向了。")

            pipeline.handle_user_message(session_id, "请再对比一次 P(A|B) 和 P(B|A)，我想检查自己。")
            pipeline.handle_user_message(session_id, "懂了，这次我可以自己解释这两个方向了。")

            pipeline.handle_user_message(session_id, "我又混淆了 P(A|B) 和 P(B|A)。")
            pipeline.handle_user_message(session_id, "我还是不懂它们为什么不能互换。")
            pipeline.handle_user_message(session_id, "先换个话题，请解释一下导数。")

            skills = list(pipeline.graph.nodes_by_type("skill").values())
            self.assertEqual(1, len(skills))
            skill = skills[0]
            self.assertEqual("active", skill["status"])
            self.assertGreaterEqual(skill["quality"]["validation_success_count"], 1)
            self.assertGreaterEqual(skill["quality"]["validation_fail_count"], 1)
            self.assertGreaterEqual(skill["quality"]["confidence"], 0.7)

            skill_edges = [
                edge for edge in pipeline.graph.edges if edge["edge_type"] == "episode_skill"
            ]
            validation_edges = [
                edge for edge in skill_edges if edge["metadata"]["role"] == "validation"
            ]
            self.assertEqual(1, len(validation_edges))
            self.assertEqual(3, len(skill_edges))

            ledger = pipeline.dataflow.list_events(session_id)
            validation_events = [
                event
                for event in ledger
                if event["event_type"] == "skill_validation_recorded"
            ]
            self.assertGreaterEqual(len(validation_events), 2)
            self.assertTrue(any(event["metadata"]["matched"] for event in validation_events))
            self.assertTrue(any(not event["metadata"]["matched"] for event in validation_events))

    def test_boundary_detector_defers_completion_until_student_confirms(self):
        class FakeLLM:
            is_live = True

            def chat(self, messages, temperature=0):
                return json.dumps(
                    {
                        "should_end": True,
                        "should_wait": False,
                        "force_end": False,
                        "confidence": 0.91,
                        "reason": "learning_goal_completed",
                        "completion_status": "completed",
                        "topic_summary": "大数定律通俗解释",
                    }
                )

        detector = EpisodeBoundaryDetector(FakeLLM(), max_events=8)
        decision = detector.evaluate(
            history=[
                {
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "向我详细解释一下大数定律是什么？",
                    "timestamp": "2026-06-03T00:00:00+00:00",
                },
                {
                    "actor": "assistant",
                    "event_type": "assistant_message",
                    "content": "大数定律说明重复次数足够多时平均结果趋于稳定。",
                    "timestamp": "2026-06-03T00:00:01+00:00",
                },
            ],
            new_messages=[
                {
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "概念有点太多太复杂了，我是一个高中生，能不能通俗，多举一些例子向我解释？",
                    "timestamp": "2026-06-03T00:00:02+00:00",
                },
                {
                    "actor": "assistant",
                    "event_type": "assistant_message",
                    "content": "我们用掷硬币和投篮的例子来理解。",
                    "timestamp": "2026-06-03T00:00:03+00:00",
                },
            ],
        )

        self.assertFalse(decision["should_end"])
        self.assertTrue(decision["should_wait"])
        self.assertEqual("continue_current_episode", decision["reason"])

    def test_boundary_detector_defers_premature_buffer_too_long_from_live_llm(self):
        class FakeLLM:
            is_live = True

            def chat(self, messages, temperature=0):
                return json.dumps(
                    {
                        "should_end": True,
                        "should_wait": False,
                        "force_end": True,
                        "confidence": 0.95,
                        "reason": "buffer_too_long",
                        "completion_status": "completed",
                        "topic_summary": "因式分解基础知识和练习评估",
                    }
                )

        detector = EpisodeBoundaryDetector(FakeLLM(), max_events=4)
        history = []
        for index in range(3):
            history.extend(
                [
                    {
                        "actor": "student",
                        "event_type": "user_message",
                        "content": f"第 {index + 1} 轮我还在学因式分解",
                        "timestamp": f"2026-06-03T00:00:0{index}+00:00",
                    },
                    {
                        "actor": "assistant",
                        "event_type": "assistant_message",
                        "content": "继续讲解和练习。",
                        "timestamp": f"2026-06-03T00:00:1{index}+00:00",
                    },
                ]
            )

        decision = detector.evaluate(
            history=history,
            new_messages=[
                {
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "这是我做的题目答案，请你继续批改",
                    "timestamp": "2026-06-03T00:00:20+00:00",
                },
                {
                    "actor": "assistant",
                    "event_type": "assistant_message",
                    "content": "我已经批改完，但还可以等你反馈是否理解。",
                    "timestamp": "2026-06-03T00:00:21+00:00",
                },
            ],
        )

        self.assertFalse(decision["should_end"])
        self.assertTrue(decision["should_wait"])
        self.assertFalse(decision["force_end"])
        self.assertEqual("continue_current_episode", decision["reason"])

    def test_boundary_detector_uses_prompt_json_when_llm_is_live(self):
        class FakeLLM:
            is_live = True

            def __init__(self):
                self.prompt = ""

            def chat(self, messages, temperature=0):
                self.prompt = messages[-1]["content"]
                return json.dumps(
                    {
                        "should_end": True,
                        "should_wait": False,
                        "force_end": False,
                        "confidence": 0.91,
                        "reason": "learning_goal_completed",
                        "completion_status": "completed",
                        "topic_summary": "条件概率解释完成",
                    }
                )

        llm = FakeLLM()
        detector = EpisodeBoundaryDetector(llm, max_events=8)
        decision = detector.evaluate(
            history=[
                {
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "什么是条件概率？",
                    "timestamp": "2026-06-03T00:00:00+00:00",
                }
            ],
            new_messages=[
                {
                    "actor": "student",
                    "event_type": "user_message",
                    "content": "我明白了，现在能分清条件概率的方向了。",
                    "timestamp": "2026-06-03T00:00:01+00:00",
                },
                {
                    "actor": "assistant",
                    "event_type": "assistant_message",
                    "content": "条件概率是在某个条件已经发生时的概率。",
                    "timestamp": "2026-06-03T00:00:02+00:00",
                }
            ],
        )

        self.assertTrue(decision["should_end"])
        self.assertEqual("learning_goal_completed", decision["reason"])
        self.assertIn("Conversation buffer", llm.prompt)
        self.assertIn("New messages", llm.prompt)

    def test_tutor_chat_request_includes_prior_session_messages_for_cacheable_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            pipeline = TutorPipeline(settings)
            captured_messages: list[list[dict[str, str]]] = []

            def fake_chat(messages, temperature=0.2):
                captured_messages.append(messages)
                return "导师回答"

            pipeline.llm.chat = fake_chat  # type: ignore[method-assign]

            pipeline.handle_user_message("session_cache", "先解释一下条件概率。")
            pipeline.handle_user_message("session_cache", "再对比一下 P(A|B) 和 P(B|A)。")

            second_messages = captured_messages[-1]
            self.assertEqual("system", second_messages[0]["role"])
            self.assertIn(
                {"role": "user", "content": "先解释一下条件概率。"},
                second_messages,
            )
            self.assertIn(
                {"role": "assistant", "content": "导师回答"},
                second_messages,
            )
            self.assertEqual("user", second_messages[-1]["role"])
            self.assertEqual("再对比一下 P(A|B) 和 P(B|A)。", second_messages[-1]["content"])
            self.assertNotIn("Teaching instruction", second_messages[-1]["content"])
            self.assertNotIn("检索到的记忆", second_messages[-1]["content"])

    def test_memory_augmented_mode_injects_real_retrieval_context_into_chat_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            pipeline = TutorPipeline(settings)
            captured_messages: list[list[dict[str, str]]] = []

            def fake_chat(messages, temperature=0.2):
                captured_messages.append(messages)
                return "导师回答"

            pipeline.llm.chat = fake_chat  # type: ignore[method-assign]
            pipeline.retriever.retrieve = lambda query: {  # type: ignore[method-assign]
                "concepts": [{"name": "条件概率"}],
                "episodes": [],
                "skills": [],
                "memory_context_pack": "SHOULD_BE_REPLACED_BY_RENDER_CONTEXT",
            }
            pipeline.retriever.render_context = lambda context: (  # type: ignore[method-assign]
                "[Memory Context]\nCurrent related concepts:\n- 条件概率\n"
                "Relevant past episodes:\n- 学生之前混淆 P(A|B) 和 P(B|A)。"
            )

            pipeline.handle_user_message(
                "session_memory_mode",
                "再对比一下 P(A|B) 和 P(B|A)。",
                memory_mode="memory_augmented",
            )

            final_user_message = captured_messages[-1][-1]["content"]
            self.assertIn("再对比一下 P(A|B) 和 P(B|A)。", final_user_message)
            self.assertIn("Current related concepts", final_user_message)
            self.assertIn("学生之前混淆 P(A|B) 和 P(B|A)", final_user_message)
            self.assertNotIn("SHOULD_BE_REPLACED_BY_RENDER_CONTEXT", final_user_message)

    def test_streamed_assistant_event_persists_trace_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping({"data_dir": tmp, "provider": "mock"})
            pipeline = TutorPipeline(settings)
            retrieval_context = {
                "concepts": [{"node_id": "concept_probability", "name": "条件概率"}],
                "episodes": [],
                "skills": [],
            }

            pipeline.retriever.retrieve = lambda query: retrieval_context  # type: ignore[method-assign]
            pipeline.retriever.render_context = lambda context: "条件概率相关记忆"  # type: ignore[method-assign]
            pipeline.llm.stream_chat = lambda messages, temperature=0.2: iter(  # type: ignore[method-assign]
                [
                    {"type": "reasoning", "delta": "先检索相关记忆。"},
                    {"type": "delta", "delta": "条件概率"},
                    {"type": "delta", "delta": "需要区分方向。"},
                    {
                        "type": "usage",
                        "usage": {
                            "prompt_tokens": 120,
                            "completion_tokens": 30,
                            "prompt_tokens_details": {"cached_tokens": 80},
                        },
                    },
                ]
            )

            events = list(
                pipeline.stream_user_message(
                    "session_trace",
                    "为什么不能混淆 P(A|B) 和 P(B|A)？",
                    memory_mode="memory_augmented",
                )
            )

            final = events[-1]
            assistant_event = final["assistant_event"]
            metadata = assistant_event["metadata"]
            self.assertEqual("final", final["type"])
            self.assertEqual("条件概率需要区分方向。", assistant_event["content"])
            self.assertEqual("先检索相关记忆。", metadata["reasoning"])
            self.assertEqual(retrieval_context, metadata["retrieval_context"])
            self.assertEqual(80, metadata["usage"]["prompt_tokens_details"]["cached_tokens"])

    def test_pipeline_replays_episode_nodes_concepts_and_open_buffers_from_dataflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 2}
            )
            pipeline = TutorPipeline(settings)

            pipeline.handle_user_message("session_done", "为什么不能直接用检测准确率当作患病概率？")
            pipeline.handle_user_message("session_done", "请再举一个条件概率的例子。")
            pipeline.handle_user_message("session_done", "我明白了，现在能分清这两个方向了。")
            pipeline.handle_user_message("session_open", "请解释一下导数。")

            replayed = TutorPipeline(settings)

            self.assertGreaterEqual(len(replayed.graph.nodes_by_type("episode")), 1)
            self.assertIn("session_open", replayed.buffer.events_by_session)
            self.assertEqual(2, len(replayed.buffer.events_by_session["session_open"]))
            self.assertEqual([], replayed.buffer.events_by_session.get("session_done", []))
            self.assertGreaterEqual(len(replayed.graph.nodes_by_type("concept")), 1)
            self.assertGreaterEqual(len(replayed.graph.edges), 1)
            self.assertEqual([], list(replayed.graph.nodes_by_type("skill").values()))

            all_events = replayed.dataflow.list_events()
            extraction_event = next(
                event
                for event in all_events
                if event["event_type"] == "episode_extraction_completed"
            )
            episode = extraction_event["metadata"]["episode"]
            self.assertEqual(
                extraction_event["segment_id"],
                episode["provenance"]["segment_id"],
            )
            self.assertEqual(
                extraction_event["metadata"]["episode_id"],
                episode["episode_id"],
            )
            concept_event = next(
                event
                for event in all_events
                if event["event_type"] == "concept_extraction_completed"
            )
            self.assertGreaterEqual(len(concept_event["metadata"]["concepts"]), 1)
            self.assertGreaterEqual(len(concept_event["metadata"]["edges"]), 1)

    def test_force_extract_only_retries_closed_segment_without_successful_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)

            self.assertIsNone(pipeline.force_extract("session_none"))

    def test_dashboard_rebuilds_graph_after_storage_is_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings_from_mapping(
                {"data_dir": tmp, "provider": "mock", "extraction_turns": 4}
            )
            pipeline = TutorPipeline(settings)

            pipeline.handle_user_message("session_a", "为什么不能直接用检测准确率当作患病概率？")
            pipeline.handle_user_message("session_a", "我还是不懂贝叶斯公式。")
            pipeline.handle_user_message("session_a", "我明白了，现在能解释核心区别了。")

            self.assertGreaterEqual(len(pipeline.dashboard()["concepts"]), 1)
            settings.dataflow_path.write_text("", encoding="utf-8")
            settings.nodes_path.write_text("{}", encoding="utf-8")
            settings.edges_path.write_text("[]", encoding="utf-8")

            refreshed = pipeline.dashboard()
            self.assertEqual([], refreshed["events"])
            self.assertEqual([], refreshed["concepts"])
            self.assertEqual([], refreshed["episodes"])
            self.assertEqual([], refreshed["edges"])


if __name__ == "__main__":
    unittest.main()
