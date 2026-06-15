from __future__ import annotations

import json
from typing import Any


STRUCTURAL_ROLES = {"main", "supporting", "mentioned"}
LEARNER_RELATIONS = {"confused", "clarified", "neutral"}


def _episode_text(episode: dict[str, Any], events: list[dict[str, Any]] | None = None) -> str:
    summary = episode.get("summary", {})
    learner_problem = episode.get("learner_problem", {})
    tutor_action = episode.get("tutor_action", {})
    outcome = episode.get("learning_outcome", {})
    parts = [
        summary.get("title", ""),
        summary.get("topic_summary", ""),
        summary.get("short_summary", ""),
        learner_problem.get("student_question", ""),
        learner_problem.get("detected_problem", ""),
        *learner_problem.get("misconceptions", []),
        *learner_problem.get("difficulty_signals", []),
        tutor_action.get("main_strategy", ""),
        tutor_action.get("strategy_summary", ""),
        *tutor_action.get("teaching_steps", []),
        outcome.get("result", ""),
        outcome.get("evidence", ""),
    ]
    if events:
        parts.extend(str(event.get("content", "")) for event in events)
    return "\n".join(str(part) for part in parts if str(part).strip())


def _normalize_json_payload(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


class HeuristicConceptExtractor:
    def extract(
        self,
        episode: dict[str, Any],
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        text = _episode_text(episode, events)
        lower = text.lower()
        outcome = episode.get("learning_outcome", {})
        learner_problem = episode.get("learner_problem", {})
        misconceptions = " ".join(str(item) for item in learner_problem.get("misconceptions", []))
        detected_problem = str(learner_problem.get("detected_problem", ""))

        concepts: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []

        def add_concept(
            *,
            name: str,
            aliases: list[str],
            description: str,
            structural_role: str,
            learner_relation: str,
            importance_score: float,
            confidence: float,
            evidence: str,
        ) -> None:
            if not any(item["name"] == name for item in concepts):
                concepts.append(
                    {
                        "name": name,
                        "aliases": aliases,
                        "description": description,
                    }
                )
            relations.append(
                {
                    "concept_name": name,
                    "structural_role": structural_role,
                    "learner_relation": learner_relation,
                    "importance_score": importance_score,
                    "confidence": confidence,
                    "evidence": evidence,
                }
            )

        bayes_context = any(
            token in text
            for token in ["贝叶斯", "检测准确率", "患病概率", "后验概率", "先验概率"]
        ) or "posterior" in lower
        conditional_context = any(
            token in text for token in ["条件概率", "P(A|B)", "P(B|A)", "P(阳性|患病)", "P(患病|阳性)"]
        ) or "conditional probability" in lower
        derivative_context = "导数" in text or "derivative" in lower
        factorization_context = "因式分解" in text or "factorization" in lower or "factoring" in lower

        if bayes_context:
            add_concept(
                name="Bayes theorem",
                aliases=["Bayes rule", "贝叶斯公式", "贝叶斯定理"],
                description="A probability rule for updating beliefs based on observed evidence.",
                structural_role="main",
                learner_relation="confused" if misconceptions or "混淆" in detected_problem else "neutral",
                importance_score=0.92,
                confidence=0.88,
                evidence="本轮主要讨论为什么检测准确率不能直接当作后验概率。",
            )
        if conditional_context:
            outcome_result = str(outcome.get("result", ""))
            relation = "clarified" if outcome_result in {"success", "partial_success"} else "confused"
            add_concept(
                name="Conditional probability",
                aliases=["条件概率", "P(A|B)", "P(B|A)"],
                description="The probability of an event under a known condition.",
                structural_role="supporting" if bayes_context else "main",
                learner_relation=relation,
                importance_score=0.84 if bayes_context else 0.9,
                confidence=0.83,
                evidence="导师重点对比了 P(A|B) 和 P(B|A) 的方向差异。",
            )
        if "先验概率" in text or "prior probability" in lower:
            add_concept(
                name="Prior probability",
                aliases=["先验概率"],
                description="The probability assigned before observing new evidence.",
                structural_role="mentioned",
                learner_relation="neutral",
                importance_score=0.72,
                confidence=0.78,
                evidence="对话提到了先验概率，但不是本轮核心讲解对象。",
            )
        if "后验概率" in text or "posterior probability" in lower:
            add_concept(
                name="Posterior probability",
                aliases=["后验概率"],
                description="The probability updated after observing evidence.",
                structural_role="mentioned",
                learner_relation="neutral",
                importance_score=0.74,
                confidence=0.79,
                evidence="对话提到了后验概率的含义，但主轴是贝叶斯推断整体。",
            )
        if derivative_context:
            add_concept(
                name="Derivative",
                aliases=["导数"],
                description="A measure of how a quantity changes with respect to another quantity.",
                structural_role="main",
                learner_relation="confused" if misconceptions or "不懂" in text else "neutral",
                importance_score=0.91,
                confidence=0.86,
                evidence="本轮围绕导数概念本身进行讲解。",
            )
        if factorization_context:
            add_concept(
                name="Factorization",
                aliases=["因式分解", "factoring"],
                description="Rewriting an expression as a product of simpler factors.",
                structural_role="main",
                learner_relation="clarified"
                if str(outcome.get("result", "")) in {"success", "partial_success"}
                else "confused",
                importance_score=0.91,
                confidence=0.86,
                evidence="本轮主要围绕因式分解的含义、例题或练习反馈展开。",
            )
        if factorization_context and "公因式" in text:
            add_concept(
                name="Common factor extraction",
                aliases=["提取公因式", "公因式"],
                description="Factoring by pulling out a factor shared by all terms.",
                structural_role="supporting",
                learner_relation="neutral",
                importance_score=0.82,
                confidence=0.78,
                evidence="对话涉及把共同因子提出来作为因式分解方法。",
            )
        if factorization_context and "平方差" in text:
            add_concept(
                name="Difference of squares",
                aliases=["平方差公式"],
                description="The identity a^2 - b^2 = (a - b)(a + b).",
                structural_role="supporting",
                learner_relation="neutral",
                importance_score=0.82,
                confidence=0.78,
                evidence="对话涉及平方差公式这一因式分解结构。",
            )
        return {"concepts": concepts, "edges": relations}


def coerce_concept_payload_from_llm(
    raw: str,
    episode: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    fallback = HeuristicConceptExtractor().extract(episode, events)
    try:
        payload = _normalize_json_payload(raw)
        raw_concepts = payload.get("concepts", [])
        raw_relations = payload.get("relations", payload.get("edges", []))
        concepts = []
        for item in raw_concepts:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            concepts.append(
                {
                    "name": name,
                    "aliases": [
                        str(alias)
                        for alias in item.get("aliases", [])
                        if str(alias).strip()
                    ],
                    "description": str(item.get("description", "")).strip(),
                }
            )
        relations = []
        for item in raw_relations:
            concept_name = str(
                item.get("concept_name")
                or item.get("name")
                or item.get("target_name")
                or ""
            ).strip()
            if not concept_name:
                continue
            structural_role = str(item.get("structural_role", "mentioned")).strip().lower()
            learner_relation = str(item.get("learner_relation", "neutral")).strip().lower()
            if structural_role not in STRUCTURAL_ROLES:
                structural_role = "mentioned"
            if learner_relation not in LEARNER_RELATIONS:
                learner_relation = "neutral"
            try:
                importance_score = float(item.get("importance_score", item.get("weight", 0.0)))
            except (TypeError, ValueError):
                importance_score = 0.0
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            relations.append(
                {
                    "concept_name": concept_name,
                    "structural_role": structural_role,
                    "learner_relation": learner_relation,
                    "importance_score": max(0.0, min(1.0, importance_score)),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "evidence": str(item.get("evidence", "")).strip(),
                }
            )
        if not concepts or not relations:
            return fallback
        return {"concepts": concepts, "edges": relations}
    except Exception:
        return fallback
