from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from .skill_extractor import skill_evidence_concept_scope


class MemoryRetriever:
    def __init__(
        self,
        graph,
        embedding_fn: Callable[[str], list[float]] | None = None,
        rerank_fn: Callable[[str, list[dict[str, Any]], str], list[dict[str, Any]]] | None = None,
        embedding_signature: dict[str, Any] | None = None,
    ):
        self.graph = graph
        self.embedding_fn = embedding_fn
        self.rerank_fn = rerank_fn
        self.embedding_signature = embedding_signature or {}

    def retrieve(
        self,
        query: str,
        top_k_episodes: int = 3,
        top_k_concepts: int = 3,
        top_k_skills: int = 1,
    ) -> dict[str, Any]:
        query_info = self._understand_query(query)
        query_embedding, embedding_error = self._query_embedding(query)
        concept_candidates, concept_summary = self._recall_concepts(query, query_info, query_embedding)

        episode_candidates, episode_summary = self._expand_episodes(
            query,
            query_info,
            query_embedding,
            concept_candidates[:top_k_concepts],
            top_k_episodes=top_k_episodes,
        )
        if concept_candidates:
            ranked_concepts = [item["node"] for item in concept_candidates[:top_k_concepts]]
        else:
            concept_candidates = self._recover_concepts_from_episodes(
                query,
                episode_candidates[:top_k_episodes],
            )
            ranked_concepts = [item["node"] for item in concept_candidates[:top_k_concepts]]
        ranked_episodes = [item["node"] for item in episode_candidates[:top_k_episodes]]

        skill_candidates, skill_summary = self._recall_skills(
            query,
            query_info,
            query_embedding,
            ranked_concepts,
            episode_candidates[:top_k_episodes],
            top_k_skills=top_k_skills,
        )
        ranked_skills = [item["node"] for item in skill_candidates[:top_k_skills]]

        retrieval_summary = {
            "query_info": query_info,
            "embedding_error": embedding_error,
            "stale_vectors": concept_summary["stale_vectors"]
            + episode_summary["stale_vectors"]
            + skill_summary["stale_vectors"],
            "concept_hits": len(concept_candidates),
            "episode_hits": len(episode_candidates),
            "skill_hits": len(skill_candidates),
            "top_matches": {
                "concepts": [self._candidate_summary(item) for item in concept_candidates[:top_k_concepts]],
                "episodes": [self._candidate_summary(item) for item in episode_candidates[:top_k_episodes]],
                "skills": [self._candidate_summary(item) for item in skill_candidates[:top_k_skills]],
            },
        }
        memory_context_pack = self.render_context(
            {
                "concepts": ranked_concepts,
                "episodes": ranked_episodes,
                "skills": ranked_skills,
                "retrieval_summary": retrieval_summary,
            }
        )
        return {
            "concepts": ranked_concepts,
            "episodes": ranked_episodes,
            "skills": ranked_skills,
            "retrieval_summary": retrieval_summary,
            "memory_context_pack": memory_context_pack,
        }

    def _query_embedding(self, query: str) -> tuple[list[float], str | None]:
        if self.embedding_fn is None:
            return [], None
        try:
            return self.embedding_fn(query), None
        except Exception as exc:
            return [], str(exc)

    def _recover_concepts_from_episodes(
        self,
        query: str,
        episode_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        episode_ids = {item["node"]["node_id"] for item in episode_candidates}
        recovered: dict[str, dict[str, Any]] = {}
        for edge in self.graph.edges:
            if edge.get("edge_type") != "episode_concept":
                continue
            if edge.get("source") not in episode_ids:
                continue
            concept = self.graph.nodes.get(str(edge.get("target") or ""))
            if not concept or concept.get("node_type") != "concept":
                continue
            keyword_score = self._concept_keyword_score(query, concept)
            score = 0.75 * float(edge.get("weight", 0.0)) + 0.25 * keyword_score
            existing = recovered.get(concept["node_id"])
            payload = {
                "id": concept["node_id"],
                "node": concept,
                "score": score,
                "text": self._retrieval_text(concept),
                "reason": "episode_backfill",
                "stale": False,
            }
            if existing is None or score > existing["score"]:
                recovered[concept["node_id"]] = payload
        candidates = list(recovered.values())
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _understand_query(self, query: str) -> dict[str, Any]:
        query_lower = query.lower()
        learner_signal = "neutral"
        if any(token in query for token in ["还是不懂", "又忘了", "不明白", "分不清", "再讲一次"]):
            learner_signal = "still_confused"
        elif any(token in query for token in ["复习", "回顾", "总结"]):
            learner_signal = "review"

        intent = "concept_explanation"
        if any(token in query for token in ["检查", "测一下", "确认", "判断"]):
            intent = "assessment"
        elif any(token in query for token in ["比较", "对比", "区别", "差异", "分别"]):
            intent = "comparison"
        elif any(token in query for token in ["例子", "举例", "例题", "具体一点", "具体例子"]):
            intent = "worked_example"
        elif any(token in query for token in ["再讲", "重新讲", "换个说法"]):
            intent = "re_explanation"
        elif learner_signal == "review":
            intent = "review"
        elif any(token in query for token in ["公式", "每一项", "符号", "什么意思", "是什么意思"]):
            intent = "formula_grounding"

        difficulty_hints: list[str] = []
        if any(token in query_lower for token in ["p(a|b)", "p(b|a)", "条件概率", "后验概率", "检测准确率"]):
            difficulty_hints.append("direction_confusion")
        if any(token in query for token in ["符号", "公式", "每一项", "含义"]):
            difficulty_hints.append("symbol_grounding")
        if any(token in query for token in ["怎么开始", "步骤", "不会做"]):
            difficulty_hints.append("procedural_gap")
        if any(token in query for token in ["迁移", "相似题", "换个题"]):
            difficulty_hints.append("transfer_failure")
        if any(token in query for token in ["没直觉", "太抽象"]):
            difficulty_hints.append("abstraction_gap")

        return {
            "raw_query": query,
            "query_lower": query_lower,
            "learner_signal": learner_signal,
            "intent": intent,
            "difficulty_hints": difficulty_hints,
        }

    def _recall_concepts(
        self,
        query: str,
        query_info: dict[str, Any],
        query_embedding: list[float],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        candidates = []
        stale_vectors = 0
        for concept in self.graph.nodes_by_type("concept").values():
            keyword_score = self._concept_keyword_score(query, concept)
            similarity, stale = self._vector_similarity(query_embedding, concept)
            stale_vectors += 1 if stale else 0
            if keyword_score <= 0 and similarity <= 0:
                continue
            prior = self._concept_prior_score(concept["node_id"])
            precision_bonus = self._concept_precision_bonus(query, concept)
            score = 0.40 * keyword_score + 0.40 * similarity + 0.10 * prior + 0.10 * precision_bonus
            if score <= 0:
                continue
            match_reasons = []
            if keyword_score > 0:
                match_reasons.append("alias_or_keyword_match")
            if similarity > 0:
                match_reasons.append("semantic_match")
            if prior > 0:
                match_reasons.append("supported_by_episode_links")
            candidates.append(
                {
                    "id": concept["node_id"],
                    "node": concept,
                    "score": score,
                    "text": self._rerank_text(
                        concept,
                        match_reasons=match_reasons,
                        matched_concepts=[str(concept.get("name", ""))],
                        matched_difficulty=[str(item) for item in query_info.get("difficulty_hints", [])],
                        intent=str(query_info.get("intent", "")),
                    ),
                    "reason": "concept_match",
                    "stale": stale,
                    "match_reasons": match_reasons,
                    "matched_concepts": [str(concept.get("name", ""))],
                    "matched_difficulty": [str(item) for item in query_info.get("difficulty_hints", [])],
                    "intent": str(query_info.get("intent", "")),
                }
            )
        candidates.sort(
            key=lambda item: (
                item["score"],
                self._concept_prior_score(item["node"]["node_id"]),
            ),
            reverse=True,
        )
        return candidates, {"stale_vectors": stale_vectors}

    def _expand_episodes(
        self,
        query: str,
        query_info: dict[str, Any],
        query_embedding: list[float],
        concept_candidates: list[dict[str, Any]],
        *,
        top_k_episodes: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        del top_k_episodes
        scores_by_episode: dict[str, dict[str, Any]] = {}
        stale_vectors = 0
        concept_ids = {item["node"]["node_id"] for item in concept_candidates}
        if not concept_ids:
            return self._fallback_episode_recall(query, query_info, query_embedding), {"stale_vectors": 0}
        edge_lookup = defaultdict(list)
        for edge in self.graph.edges:
            if edge.get("edge_type") == "episode_concept" and edge.get("target") in concept_ids:
                edge_lookup[str(edge.get("source"))].append(edge)
        for episode_id, edges in edge_lookup.items():
            episode = self.graph.nodes.get(episode_id)
            if not episode or episode.get("node_type") != "episode":
                continue
            concept_weight = max(float(edge.get("weight", 0.0)) for edge in edges)
            semantic_similarity, stale = self._vector_similarity(query_embedding, episode)
            stale_vectors += 1 if stale else 0
            outcome_relevance = self._episode_outcome_relevance(query_info, episode)
            intent_bonus = self._episode_intent_bonus(query_info, episode)
            recency = self._recency_score(episode.get("provenance", {}).get("end_time", ""))
            score = (
                0.40 * semantic_similarity
                + 0.30 * concept_weight
                + 0.20 * outcome_relevance
                + 0.10 * recency
                + intent_bonus
            )
            if score <= 0:
                continue
            matched_concepts = []
            for edge in edges:
                concept = self.graph.nodes.get(str(edge.get("target") or ""))
                if concept and concept.get("name") and concept["name"] not in matched_concepts:
                    matched_concepts.append(concept["name"])
            match_reasons = ["concept_expansion"]
            if semantic_similarity > 0:
                match_reasons.append("semantic_match")
            if outcome_relevance >= 0.8:
                match_reasons.append("outcome_aligned")
            if intent_bonus > 0:
                match_reasons.append("intent_aligned")
            scores_by_episode[episode_id] = {
                "id": episode_id,
                "node": episode,
                "score": score,
                "text": self._rerank_text(
                    episode,
                    match_reasons=match_reasons,
                    matched_concepts=matched_concepts,
                    matched_difficulty=[str(item) for item in query_info.get("difficulty_hints", [])],
                    intent=str(query_info.get("intent", "")),
                ),
                "reason": "concept_expansion",
                "stale": stale,
                "match_reasons": match_reasons,
                "matched_concepts": matched_concepts,
                "matched_difficulty": [str(item) for item in query_info.get("difficulty_hints", [])],
                "intent": str(query_info.get("intent", "")),
            }

        candidates = list(scores_by_episode.values())
        candidates.sort(key=lambda item: item["score"], reverse=True)
        candidates = self._maybe_rerank(query, candidates, "episode")
        return candidates, {"stale_vectors": stale_vectors}

    def _fallback_episode_recall(
        self,
        query: str,
        query_info: dict[str, Any],
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        candidates = []
        for episode in self.graph.nodes_by_type("episode").values():
            semantic_similarity, stale = self._vector_similarity(query_embedding, episode)
            keyword_score = self._episode_keyword_score(query, episode)
            if keyword_score <= 0 and semantic_similarity <= 0:
                continue
            outcome_relevance = self._episode_outcome_relevance(query_info, episode)
            intent_bonus = self._episode_intent_bonus(query_info, episode)
            recency = self._recency_score(episode.get("provenance", {}).get("end_time", ""))
            score = (
                0.45 * semantic_similarity
                + 0.25 * keyword_score
                + 0.15 * outcome_relevance
                + 0.10 * recency
                + 0.05 * intent_bonus
            )
            match_reasons = ["direct_episode_fallback"]
            if semantic_similarity > 0:
                match_reasons.append("semantic_match")
            if keyword_score > 0:
                match_reasons.append("keyword_match")
            if intent_bonus > 0:
                match_reasons.append("intent_aligned")
            candidates.append(
                {
                    "id": episode["node_id"],
                    "node": episode,
                    "score": score,
                    "text": self._rerank_text(
                        episode,
                        match_reasons=match_reasons,
                        matched_concepts=[],
                        matched_difficulty=[str(item) for item in query_info.get("difficulty_hints", [])],
                        intent=str(query_info.get("intent", "")),
                    ),
                    "reason": "direct_episode_fallback",
                    "stale": stale,
                    "match_reasons": match_reasons,
                    "matched_concepts": [],
                    "matched_difficulty": [str(item) for item in query_info.get("difficulty_hints", [])],
                    "intent": str(query_info.get("intent", "")),
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return self._maybe_rerank(query, candidates, "episode")

    def _recall_skills(
        self,
        query: str,
        query_info: dict[str, Any],
        query_embedding: list[float],
        concepts: list[dict[str, Any]],
        episode_candidates: list[dict[str, Any]],
        *,
        top_k_skills: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        by_skill: dict[str, dict[str, Any]] = {}
        stale_vectors = 0
        episode_scores = {item["node"]["node_id"]: float(item["score"]) for item in episode_candidates}
        concept_names = {
            str(concept.get("name", "")).strip().lower()
            for concept in concepts
            if str(concept.get("name", "")).strip()
        }
        for edge in self.graph.edges:
            if edge.get("edge_type") != "episode_skill":
                continue
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in episode_scores:
                continue
            skill = self.graph.nodes.get(target)
            if not skill or skill.get("node_type") != "skill":
                continue
            semantic_similarity, stale = self._vector_similarity(query_embedding, skill)
            stale_vectors += 1 if stale else 0
            edge_weight = float(edge.get("weight", 0.0))
            confidence = float(skill.get("quality", {}).get("confidence", 0.0))
            quality_bonus = self._skill_quality_bonus(skill)
            difficulty_match = self._difficulty_match_bonus(query_info, skill)
            intent_bonus = self._skill_intent_bonus(query_info, skill)
            concept_scope_bonus = self._skill_concept_scope_bonus(concept_names, skill)
            score = (
                0.35 * semantic_similarity
                + 0.35 * episode_scores[source]
                + 0.20 * edge_weight
                + 0.10 * confidence
                + quality_bonus
                + difficulty_match
                + intent_bonus
                + concept_scope_bonus
            )
            match_reasons = ["episode_skill_expansion"]
            if semantic_similarity > 0:
                match_reasons.append("semantic_match")
            if difficulty_match > 0:
                match_reasons.append("difficulty_match")
            if intent_bonus > 0:
                match_reasons.append("intent_aligned")
            if quality_bonus > 0:
                match_reasons.append("validated_skill")
            existing = by_skill.get(target)
            payload = {
                "id": target,
                "node": skill,
                "score": score,
                "text": self._rerank_text(
                    skill,
                    match_reasons=match_reasons,
                    matched_concepts=skill_evidence_concept_scope(skill)[:3],
                    matched_difficulty=[str(skill.get("difficulty_pattern", ""))] if str(skill.get("difficulty_pattern", "")) else [],
                    intent=str(query_info.get("intent", "")),
                ),
                "reason": "episode_skill_expansion",
                "stale": stale,
                "match_reasons": match_reasons,
                "matched_concepts": skill_evidence_concept_scope(skill)[:3],
                "matched_difficulty": [str(skill.get("difficulty_pattern", ""))] if str(skill.get("difficulty_pattern", "")) else [],
                "intent": str(query_info.get("intent", "")),
            }
            if existing is None or payload["score"] > existing["score"]:
                by_skill[target] = payload

        for skill in self.graph.nodes_by_type("skill").values():
            semantic_similarity, stale = self._vector_similarity(query_embedding, skill)
            stale_vectors += 1 if stale else 0
            keyword_bonus = self._skill_keyword_score(query, skill)
            confidence = float(skill.get("quality", {}).get("confidence", 0.0))
            quality_bonus = self._skill_quality_bonus(skill)
            difficulty_match = self._difficulty_match_bonus(query_info, skill)
            intent_bonus = self._skill_intent_bonus(query_info, skill)
            concept_scope_bonus = self._skill_concept_scope_bonus(concept_names, skill)
            score = (
                0.60 * semantic_similarity
                + 0.25 * keyword_bonus
                + 0.15 * confidence
                + quality_bonus
                + difficulty_match
                + intent_bonus
                + concept_scope_bonus
            )
            if score <= 0:
                continue
            match_reasons = ["direct_skill_match"]
            if semantic_similarity > 0:
                match_reasons.append("semantic_match")
            if keyword_bonus > 0:
                match_reasons.append("keyword_match")
            if difficulty_match > 0:
                match_reasons.append("difficulty_match")
            if intent_bonus > 0:
                match_reasons.append("intent_aligned")
            if quality_bonus > 0:
                match_reasons.append("validated_skill")
            existing = by_skill.get(skill["node_id"])
            if existing is None or score > existing["score"]:
                by_skill[skill["node_id"]] = {
                    "id": skill["node_id"],
                    "node": skill,
                    "score": score,
                    "text": self._rerank_text(
                        skill,
                        match_reasons=match_reasons,
                        matched_concepts=skill_evidence_concept_scope(skill)[:3],
                        matched_difficulty=[str(skill.get("difficulty_pattern", ""))] if str(skill.get("difficulty_pattern", "")) else [],
                        intent=str(query_info.get("intent", "")),
                    ),
                    "reason": "direct_skill_match",
                    "stale": stale,
                    "match_reasons": match_reasons,
                    "matched_concepts": skill_evidence_concept_scope(skill)[:3],
                    "matched_difficulty": [str(skill.get("difficulty_pattern", ""))] if str(skill.get("difficulty_pattern", "")) else [],
                    "intent": str(query_info.get("intent", "")),
                }

        candidates = list(by_skill.values())
        candidates.sort(key=lambda item: item["score"], reverse=True)
        candidates = self._maybe_rerank(query, candidates, "skill")
        return candidates, {"stale_vectors": stale_vectors}

    def _maybe_rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        kind: str,
    ) -> list[dict[str, Any]]:
        if self.rerank_fn is None or len(candidates) <= 1:
            return candidates
        return self.rerank_fn(query, candidates, kind)

    def _vector_similarity(
        self,
        query_embedding: list[float],
        node: dict[str, Any],
    ) -> tuple[float, bool]:
        retrieval = node.get("retrieval", {})
        metadata = retrieval.get("embedding_metadata", {})
        vector = retrieval.get("embedding_vector", [])
        stale = self._is_stale_embedding(metadata, vector)
        if stale or not query_embedding or not vector:
            return 0.0, stale
        return self._cosine_similarity(query_embedding, vector), False

    def _is_stale_embedding(self, metadata: dict[str, Any], vector: list[float]) -> bool:
        if not vector:
            return False
        if not self.embedding_signature:
            return False
        checks = ["provider", "model_id"]
        if self.embedding_signature.get("dimensions"):
            checks.append("dimensions")
        return any(metadata.get(key) != self.embedding_signature.get(key) for key in checks)

    def _concept_prior_score(self, concept_id: str) -> float:
        matches = sum(
            1
            for edge in self.graph.edges
            if edge.get("edge_type") == "episode_concept" and edge.get("target") == concept_id
        )
        return min(1.0, matches / 3.0)

    def _episode_outcome_relevance(self, query_info: dict[str, Any], episode: dict[str, Any]) -> float:
        result = str(episode.get("learning_outcome", {}).get("result", "unresolved"))
        if query_info.get("learner_signal") == "still_confused":
            if result in {"failed", "unresolved"}:
                return 1.0
            if result == "partial_success":
                return 0.85
            return 0.45
        if query_info.get("intent") == "comparison":
            return 0.95 if result in {"success", "partial_success"} else 0.55
        if query_info.get("intent") in {"worked_example", "formula_grounding"}:
            return 1.0 if result == "success" else 0.75
        if query_info.get("intent") == "re_explanation":
            return 1.0 if result == "success" else 0.65
        return 0.7 if result in {"success", "partial_success"} else 0.5

    def _recency_score(self, timestamp: str) -> float:
        return 0.5 if timestamp else 0.0

    def _episode_intent_bonus(self, query_info: dict[str, Any], episode: dict[str, Any]) -> float:
        intent = str(query_info.get("intent", "concept_explanation"))
        tutor_action = episode.get("tutor_action", {})
        summary = episode.get("summary", {})
        learner_problem = episode.get("learner_problem", {})
        if intent == "assessment" and tutor_action.get("used_assessment"):
            return 0.12
        if intent == "comparison":
            text = " ".join(
                [
                    str(summary.get("topic_summary", "")),
                    str(summary.get("short_summary", "")),
                    str(learner_problem.get("detected_problem", "")),
                ]
            ).lower()
            if any(token in text for token in ["对比", "区别", "差异", "p(a|b)", "p(b|a)"]):
                return 0.12
        if intent in {"worked_example", "formula_grounding"} and tutor_action.get("used_examples"):
            return 0.12
        return 0.0

    def render_context(self, context: dict[str, Any]) -> str:
        concepts = context.get("concepts", [])
        episodes = context.get("episodes", [])
        skills = context.get("skills", [])
        query_info = context.get("retrieval_summary", {}).get("query_info", {})
        lines = ["[Memory Context]", ""]
        lines.append("Current related concepts:")
        if concepts:
            for concept in concepts[:3]:
                lines.append(f"- {concept.get('name', 'Untitled concept')}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("Learner history:")
        learner_history = self._learner_history_lines(episodes)
        if learner_history:
            lines.extend(f"- {item}" for item in learner_history[:3])
        else:
            lines.append("- No strong learner history retrieved.")

        lines.append("")
        lines.append("Relevant past episodes:")
        if episodes:
            for episode in episodes[:3]:
                summary = episode.get("summary", {})
                lines.append(
                    f"- {episode.get('node_id', 'episode')}: {summary.get('short_summary', summary.get('topic_summary', ''))}"
                )
        else:
            lines.append("- None")

        lines.append("")
        lines.append("Recommended pedagogical skill:")
        if skills:
            skill = skills[0]
            lines.append(f"- {skill.get('name', 'Untitled skill')}")
            for step in list(skill.get("procedure", []))[:3]:
                lines.append(f"  {step}")
        else:
            lines.append("- No reusable pedagogical skill retrieved.")

        lines.append("")
        lines.append("Teaching instruction:")
        lines.append(self._teaching_instruction(concepts, episodes, skills, query_info))
        return "\n".join(lines)

    def _learner_history_lines(self, episodes: list[dict[str, Any]]) -> list[str]:
        if not episodes:
            return []

        ranked = sorted(
            episodes[:3],
            key=lambda episode: self._outcome_rank(
                str(episode.get("learning_outcome", {}).get("result", "unresolved"))
            ),
        )
        earliest = ranked[0]
        latest = ranked[-1]
        earliest_problem = str(
            earliest.get("learner_problem", {}).get("detected_problem", "")
        ).strip()
        latest_evidence = str(
            latest.get("learning_outcome", {}).get("evidence", "")
        ).strip()
        latest_evidence = self._normalize_history_evidence(latest_evidence)
        lines: list[str] = []
        if earliest_problem and latest_evidence and earliest is not latest:
            lines.append(
                f"The learner previously struggled with {earliest_problem}, but later improved enough that {latest_evidence}"
            )

        misconceptions = []
        for episode in episodes[:3]:
            for item in episode.get("learner_problem", {}).get("misconceptions", []):
                text = str(item).strip()
                if text and text not in misconceptions:
                    misconceptions.append(text)
        if misconceptions:
            lines.append(f"A recurring confusion is: {misconceptions[0]}")

        if not lines:
            for episode in episodes[:3]:
                problem = episode.get("learner_problem", {})
                detected = str(problem.get("detected_problem", "")).strip()
                if detected and detected not in lines:
                    lines.append(detected)
        return lines[:3]

    def _teaching_instruction(
        self,
        concepts: list[dict[str, Any]],
        episodes: list[dict[str, Any]],
        skills: list[dict[str, Any]],
        query_info: dict[str, Any],
    ) -> str:
        concept_names = ", ".join(concept.get("name", "") for concept in concepts[:2] if concept.get("name"))
        intent = str(query_info.get("intent", "concept_explanation"))
        learner_signal = str(query_info.get("learner_signal", "neutral"))
        if skills:
            skill = skills[0]
            procedure = list(skill.get("procedure", []))
            actions = set(skill.get("teaching_actions", []))
            first_steps = "; ".join(procedure[:2])
            if intent == "assessment":
                return (
                    f"Start from {concept_names or 'the current concept focus'}, run a short check before re-teaching, "
                    f"use {first_steps} only if the learner misses the key distinction, and finish with one transfer check."
                )
            if intent == "comparison":
                return (
                    f"Start from {concept_names or 'the current concept focus'}, explicitly compare the two easily confused ideas side by side, "
                    f"use {first_steps}, say what each side means in the same scenario, and ask the learner to compare them back in one sentence."
                )
            if intent in {"worked_example", "formula_grounding"}:
                if "minimal_numeric_example" in actions:
                    return (
                        f"Start from {concept_names or 'the current concept focus'}, begin with a small worked example before definitions or formulas, "
                        f"use {first_steps}, map each symbol back to the example, and only then summarize the rule."
                    )
                return (
                    f"Start from {concept_names or 'the current concept focus'}, begin with one concrete worked example, "
                    f"use {first_steps}, and connect each step back to the formula meaning before abstracting."
                )
            if learner_signal == "still_confused" and intent == "re_explanation":
                if "minimal_numeric_example" in actions:
                    return (
                        f"Start from {concept_names or 'the current concept focus'}, switch to a different explanation path than before, "
                        f"use {first_steps}, then use a small numeric example and ask the learner to restate the difference in their own words."
                    )
                return (
                    f"Start from {concept_names or 'the current concept focus'}, switch to a different explanation path than before, "
                    f"use {first_steps}, and ask the learner to restate the difference in their own words before moving on."
                )
            example_hint = (
                " Use a small numeric example before checking understanding."
                if "minimal_numeric_example" in actions
                else " Ask the learner to restate the difference after the explanation."
            )
            return (
                f"Start from {concept_names or 'the current concept focus'}, follow the retrieved skill trigger "
                f"({skill.get('difficulty_pattern', 'unknown')}), use {first_steps}, avoid jumping straight to the final formula or answer,"
                f"{example_hint}"
            )
        if episodes:
            if intent == "comparison":
                return (
                    f"Start from {concept_names or 'the current concept focus'}, compare the two confusing ideas side by side, "
                    "reuse the clearer contrast pattern from the retrieved episodes, and finish by asking the learner to state the difference back."
                )
            if intent in {"worked_example", "formula_grounding"}:
                return (
                    f"Start from {concept_names or 'the current concept focus'}, begin with one concrete example before abstract definitions, "
                    "reuse the clearer explanation path from the retrieved episodes, and connect the example back to each formula part."
                )
            return (
                f"Start from {concept_names or 'the current concept focus'}, reuse the more effective explanation path from the retrieved episodes, "
                "avoid jumping directly to the final formula, and end with a short understanding check."
            )
        if intent == "comparison":
            return "Compare the two target ideas side by side, keep the contrast explicit, and end by asking the learner to state the difference back."
        if intent in {"worked_example", "formula_grounding"}:
            return "Start with one small worked example, then connect each step or symbol back to the concept before summarizing the rule."
        return "Explain the concept progressively, keep the answer short, and end with a short understanding check."

    def _difficulty_match_bonus(self, query_info: dict[str, Any], skill: dict[str, Any]) -> float:
        hints = set(query_info.get("difficulty_hints", []))
        if not hints:
            return 0.0
        return 0.18 if str(skill.get("difficulty_pattern", "")) in hints else 0.0

    def _skill_intent_bonus(self, query_info: dict[str, Any], skill: dict[str, Any]) -> float:
        intent = str(query_info.get("intent", "concept_explanation"))
        actions = {str(item) for item in skill.get("teaching_actions", [])}
        text = self._retrieval_text(skill).lower()
        if intent == "assessment" and "diagnostic_check" in actions:
            return 0.12
        if intent == "comparison" and (
            "contrastive_explanation" in actions or "contrast" in text or "compare" in text
        ):
            return 0.12
        if intent in {"worked_example", "formula_grounding"} and (
            "minimal_numeric_example" in actions or "step_by_step_explanation" in actions
        ):
            return 0.12
        if intent == "re_explanation" and "contrastive_explanation" in actions:
            return 0.06
        return 0.0

    def _skill_concept_scope_bonus(self, concept_names: set[str], skill: dict[str, Any]) -> float:
        if not concept_names:
            return 0.0
        scope = {
            str(item).strip().lower()
            for item in skill_evidence_concept_scope(skill)
            if str(item).strip()
        }
        return 0.08 if scope.intersection(concept_names) else 0.0

    def _skill_quality_bonus(self, skill: dict[str, Any]) -> float:
        quality = skill.get("quality", {})
        validation_success = int(quality.get("validation_success_count", 0) or 0)
        status = str(skill.get("status", "candidate"))
        bonus = min(0.08, validation_success * 0.03)
        if status == "active":
            bonus += 0.05
        return bonus

    def _outcome_rank(self, result: str) -> int:
        if result == "success":
            return 3
        if result == "partial_success":
            return 2
        if result == "unresolved":
            return 1
        return 0

    def _normalize_history_evidence(self, evidence: str) -> str:
        generic_map = {
            "学生明确表达已经理解。": "the learner could explain the key difference clearly",
            "学生仍然明确表达困惑或不会做。": "the learner was still clearly confused",
            "完成了一轮有效讲解，但仍需后续检查。": "the learner made progress but still needed a follow-up check",
        }
        return generic_map.get(evidence, evidence)

    def _candidate_summary(self, candidate: dict[str, Any]) -> dict[str, Any]:
        node = candidate.get("node", {})
        return {
            "id": str(candidate.get("id") or node.get("node_id") or ""),
            "node_type": str(node.get("node_type", "")),
            "score": round(float(candidate.get("score", 0.0)), 4),
            "reason": str(candidate.get("reason", "")),
            "match_reasons": [str(item) for item in candidate.get("match_reasons", [])],
            "matched_concepts": [str(item) for item in candidate.get("matched_concepts", []) if str(item)],
            "matched_difficulty": [str(item) for item in candidate.get("matched_difficulty", []) if str(item)],
            "intent": str(candidate.get("intent", "")),
        }

    def _rerank_text(
        self,
        node: dict[str, Any],
        *,
        match_reasons: list[str],
        matched_concepts: list[str],
        matched_difficulty: list[str],
        intent: str,
    ) -> str:
        parts = [
            f"node_type={node.get('node_type', '')}",
            f"intent={intent}",
            f"matched_concepts={', '.join(item for item in matched_concepts if item) or 'none'}",
            f"matched_difficulty={', '.join(item for item in matched_difficulty if item) or 'none'}",
            f"match_reasons={', '.join(match_reasons) or 'none'}",
            f"text={self._retrieval_text(node)}",
        ]
        return "\n".join(parts)

    def _retrieval_text(self, node: dict[str, Any]) -> str:
        retrieval = node.get("retrieval", {})
        text = str(retrieval.get("embedding_text", "")).strip()
        if text:
            return text
        if node.get("node_type") == "concept":
            return " ".join(
                [
                    str(node.get("name", "")),
                    *[str(item) for item in node.get("aliases", [])],
                    str(node.get("description", "")),
                ]
            ).strip()
        if node.get("node_type") == "skill":
            return " ".join(
                [
                    str(node.get("name", "")),
                    str(node.get("trigger", "")),
                    *[str(item) for item in node.get("procedure", [])],
                ]
            ).strip()
        summary = node.get("summary", {})
        return " ".join(
            [
                str(summary.get("title", "")),
                str(summary.get("topic_summary", "")),
                str(summary.get("short_summary", "")),
            ]
        ).strip()

    def _keyword_score(self, query: str, texts: list[str]) -> float:
        query_lower = query.lower()
        normalized_texts = [text.lower().strip() for text in texts if str(text).strip()]
        haystack = " ".join(normalized_texts)
        score = 0.0
        for token in query_lower.replace("，", " ").replace("。", " ").split():
            if token and token in haystack:
                score += 1.0
        if query_lower and query_lower in haystack:
            score += 2.0
        for text in normalized_texts:
            if not text:
                continue
            if text in query_lower:
                score += 2.0
            elif query_lower and len(query_lower) <= 24 and query_lower in text:
                score += 1.0
        return score

    def _episode_keyword_score(self, query: str, episode: dict[str, Any]) -> float:
        retrieval = episode.get("retrieval", {})
        summary = episode.get("summary", {})
        learner_problem = episode.get("learner_problem", {})
        return self._keyword_score(
            query,
            [
                str(summary.get("title", "")),
                str(summary.get("topic_summary", "")),
                str(summary.get("short_summary", "")),
                str(learner_problem.get("detected_problem", "")),
                str(retrieval.get("embedding_text", "")),
                *[str(item) for item in retrieval.get("keywords", [])],
            ],
        )

    def _concept_keyword_score(self, query: str, concept: dict[str, Any]) -> float:
        retrieval = concept.get("retrieval", {})
        return self._keyword_score(
            query,
            [
                str(concept.get("name", "")),
                str(concept.get("description", "")),
                *[str(alias) for alias in concept.get("aliases", [])],
                str(retrieval.get("embedding_text", "")),
                *[str(item) for item in retrieval.get("keywords", [])],
            ],
        )

    def _concept_precision_bonus(self, query: str, concept: dict[str, Any]) -> float:
        query_lower = query.lower().strip()
        if not query_lower:
            return 0.0
        names = [
            str(concept.get("name", "")).lower().strip(),
            *[str(alias).lower().strip() for alias in concept.get("aliases", [])],
        ]
        if any(name and name == query_lower for name in names):
            return 1.0
        if any(name and name in query_lower for name in names):
            return 0.8
        if len(query_lower) <= 12 and any(query_lower in name for name in names if name):
            return 0.5
        return 0.0

    def _skill_keyword_score(self, query: str, skill: dict[str, Any]) -> float:
        retrieval = skill.get("retrieval", {})
        return self._keyword_score(
            query,
            [
                str(skill.get("name", "")),
                str(skill.get("trigger", "")),
                str(skill.get("difficulty_pattern", "")),
                *skill_evidence_concept_scope(skill),
                *[str(item) for item in skill.get("teaching_actions", [])],
                str(retrieval.get("embedding_text", "")),
                *[str(item) for item in retrieval.get("keywords", [])],
            ],
        )

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        length = min(len(left), len(right))
        if length == 0:
            return 0.0
        dot = sum(left[index] * right[index] for index in range(length))
        left_norm = sum(value * value for value in left[:length]) ** 0.5
        right_norm = sum(value * value for value in right[:length]) ** 0.5
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
