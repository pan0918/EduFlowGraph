from __future__ import annotations

import unittest

from EduFlowGraph.memory.skill_reranker import SkillPersonalizedReranker


def make_candidate(
    skill_id: str,
    *,
    confidence: float,
    base: float,
    episode: float,
    status: str = "candidate",
    action: str = "concrete_example",
) -> dict:
    return {
        "id": skill_id,
        "node": {
            "skill_id": skill_id,
            "node_id": skill_id,
            "node_type": "skill",
            "name": skill_id,
            "status": status,
            "trigger": "学生需要建立直观理解时",
            "difficulty_pattern": "abstraction_gap",
            "teaching_actions": [action],
            "procedure": ["先给具体例子", "再映射回抽象概念"],
            "success_criteria": ["学生能用自己的话复述"],
            "quality": {"confidence": confidence},
        },
        "base_raw_score": base,
        "episode_link_raw_score": episode,
        "episode_evidence": ["过去 Episode 中使用后认知负荷下降"],
    }


def scored_rerank(scores_by_id: dict[str, float]):
    def rerank(query: str, documents: list[dict], kind: str) -> list[dict]:
        ranked = sorted(
            documents,
            key=lambda item: scores_by_id[str(item["id"])],
            reverse=True,
        )
        return [
            {
                **item,
                "rerank": {
                    "rank": index,
                    "relevance_score": scores_by_id[str(item["id"])],
                    "provider": "siliconflow",
                    "model_id": "Qwen/Qwen3-Reranker-8B",
                    "source": "reranker",
                },
            }
            for index, item in enumerate(ranked)
        ]

    return rerank


class SkillPersonalizedRerankerTest(unittest.TestCase):
    def test_query_uses_context_and_adaptation_and_document_contains_skill_program(self):
        captured: dict[str, object] = {}

        def rerank(query: str, documents: list[dict], kind: str) -> list[dict]:
            captured["query"] = query
            captured["documents"] = documents
            captured["kind"] = kind
            return [
                {
                    **documents[0],
                    "rerank": {
                        "rank": 0,
                        "relevance_score": 0.9,
                        "source": "reranker",
                    },
                }
            ]

        selector = SkillPersonalizedReranker(rerank_fn=rerank)
        selector.select(
            query="解释一个新概念",
            context_summary="当前处于探索阶段",
            adaptation_summary="优先选择低认知负荷的类比 Skill",
            candidates=[make_candidate("skill_a", confidence=0.8, base=0.8, episode=0.8)],
        )

        query = str(captured["query"])
        document_text = str(captured["documents"][0]["text"])
        self.assertIn("解释一个新概念", query)
        self.assertIn("当前处于探索阶段", query)
        self.assertIn("低认知负荷", query)
        self.assertNotIn("learner_model", query)
        self.assertEqual(captured["kind"], "skill_personalization")
        self.assertIn("concrete_example", document_text)
        self.assertIn("先给具体例子", document_text)
        self.assertIn("过去 Episode", document_text)

    def test_document_includes_all_generalized_difficulty_patterns(self):
        captured: dict[str, object] = {}

        def rerank(query: str, documents: list[dict], kind: str) -> list[dict]:
            captured["text"] = documents[0]["text"]
            return [
                {
                    **documents[0],
                    "rerank": {"rank": 0, "relevance_score": 0.9, "source": "reranker"},
                }
            ]

        candidate = make_candidate("skill_general", confidence=0.8, base=0.8, episode=0.8)
        candidate["node"]["difficulty_patterns"] = [
            "abstraction_gap",
            "conceptual_confusion",
        ]
        SkillPersonalizedReranker(rerank_fn=rerank).select(
            query="解释一个晦涩概念",
            context_summary="探索阶段",
            adaptation_summary="适合具体例子",
            candidates=[candidate],
        )

        self.assertIn("abstraction_gap, conceptual_confusion", str(captured["text"]))

    def test_personal_fit_can_outweigh_slightly_higher_base_score(self):
        selector = SkillPersonalizedReranker(
            rerank_fn=scored_rerank({"semantic_best": 0.4, "personal_best": 0.95})
        )
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先低认知负荷类比",
            candidates=[
                make_candidate("semantic_best", confidence=0.8, base=1.0, episode=0.9),
                make_candidate("personal_best", confidence=0.8, base=0.8, episode=0.8),
            ],
        )

        self.assertEqual(result["skills"][0]["node_id"], "personal_best")
        self.assertEqual(result["skill_selection"]["reranker_status"], "ok")

    def test_low_confidence_is_filtered_even_when_ranked_first(self):
        selector = SkillPersonalizedReranker(
            rerank_fn=scored_rerank({"weak": 0.99})
        )
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先类比",
            candidates=[make_candidate("weak", confidence=0.4, base=1.0, episode=1.0)],
        )

        self.assertEqual(result["skills"], [])
        self.assertEqual(
            result["skill_selection"]["candidates"][0]["filter_reason"],
            "low_confidence",
        )

    def test_low_personal_fit_is_filtered(self):
        selector = SkillPersonalizedReranker(
            rerank_fn=scored_rerank({"mismatch": 0.2})
        )
        result = selector.select(
            query="需要直观解释",
            context_summary="探索阶段",
            adaptation_summary="避免公式密集 Skill",
            candidates=[make_candidate("mismatch", confidence=0.9, base=1.0, episode=1.0)],
        )

        self.assertEqual(result["skills"], [])
        self.assertEqual(
            result["skill_selection"]["candidates"][0]["filter_reason"],
            "low_personal_fit",
        )

    def test_rank_only_response_uses_monotonic_fallback_scores(self):
        def rank_only(query: str, documents: list[dict], kind: str) -> list[dict]:
            return [
                {
                    **item,
                    "rerank": {
                        "rank": index,
                        "relevance_score": None,
                        "source": "rank_only",
                    },
                }
                for index, item in enumerate(reversed(documents))
            ]

        selector = SkillPersonalizedReranker(rerank_fn=rank_only)
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先类比",
            candidates=[
                make_candidate("first", confidence=0.9, base=0.9, episode=0.9),
                make_candidate("second", confidence=0.9, base=0.9, episode=0.9),
            ],
        )

        trace = result["skill_selection"]
        self.assertEqual(trace["reranker_status"], "rank_only")
        by_id = {item["skill_id"]: item for item in trace["candidates"]}
        self.assertGreater(
            by_id["second"]["personal_fit_score"],
            by_id["first"]["personal_fit_score"],
        )

    def test_degraded_mode_selects_only_strong_supported_skill(self):
        def unavailable(query: str, documents: list[dict], kind: str) -> list[dict]:
            raise TimeoutError("reranker timeout")

        selector = SkillPersonalizedReranker(rerank_fn=unavailable)
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先类比",
            candidates=[
                make_candidate("strong", confidence=0.8, base=0.9, episode=0.8),
                make_candidate("weak", confidence=0.7, base=1.0, episode=1.0),
            ],
        )

        self.assertEqual([item["node_id"] for item in result["skills"]], ["strong"])
        self.assertEqual(result["skill_selection"]["reranker_status"], "degraded")

    def test_seed_candidate_and_active_are_supported(self):
        selector = SkillPersonalizedReranker(
            rerank_fn=scored_rerank({"seed": 0.9, "candidate": 0.9, "active": 0.9})
        )
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先类比",
            candidates=[
                make_candidate("seed", confidence=0.8, base=0.9, episode=0.9, status="seed"),
                make_candidate("candidate", confidence=0.8, base=0.9, episode=0.9),
                make_candidate("active", confidence=0.8, base=0.9, episode=0.9, status="active"),
            ],
        )

        self.assertEqual(
            {item["node_id"] for item in result["skills"]},
            {"seed", "candidate", "active"},
        )

    def test_at_most_four_skills_are_selected(self):
        scores = {f"skill_{index}": 0.9 for index in range(6)}
        selector = SkillPersonalizedReranker(rerank_fn=scored_rerank(scores))
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="优先类比",
            candidates=[
                make_candidate(
                    f"skill_{index}",
                    confidence=0.9,
                    base=1.0,
                    episode=1.0,
                )
                for index in range(6)
            ],
        )

        self.assertEqual(len(result["skills"]), 4)
        self.assertEqual(result["skill_selection"]["selected_count"], 4)
        self.assertEqual(
            sum(
                candidate["filter_reason"] == "outside_top_k"
                for candidate in result["skill_selection"]["candidates"]
            ),
            2,
        )

    def test_empty_candidates_return_one_short_adaptation_sentence(self):
        selector = SkillPersonalizedReranker(rerank_fn=None)
        result = selector.select(
            query="解释新概念",
            context_summary="探索阶段",
            adaptation_summary="先用直观类比建立理解。随后逐步进入形式化推导。",
            candidates=[],
        )

        self.assertEqual(result["skills"], [])
        trace = result["skill_selection"]
        self.assertEqual(trace["reranker_status"], "skipped")
        self.assertEqual(trace["fallback_instruction"], "先用直观类比建立理解。")
        self.assertLessEqual(len(trace["fallback_instruction"]), 120)

    def test_empty_adaptation_uses_generic_fallback(self):
        selector = SkillPersonalizedReranker(rerank_fn=None)
        result = selector.select(
            query="解释新概念",
            context_summary="",
            adaptation_summary="",
            candidates=[],
        )

        self.assertEqual(
            result["skill_selection"]["fallback_instruction"],
            "先建立直观理解，再逐步展开关键步骤，并用一个简短问题检查理解。",
        )


if __name__ == "__main__":
    unittest.main()
