from __future__ import annotations

import json
import re
from typing import Any, Callable

from ..schemas import make_id, utc_now, STRUCTURAL_ROLES, LEARNER_STATES
from ..prompts import CONCEPT_EXTRACTION_PROMPT
from ..llm import messages_for_prompt


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


def _normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.strip().lower())


BANNED_CONCEPT_NAMES = {
    "workedexample", "contrastiveexplanation", "stepbystepguidance",
    "socraticquestioning", "concreteexample", "formuladecomposition",
    "selfexplanationprompt", "diagnosticcheck", "guidedpractice",
    "errorcorrection", "studentconfidence", "learnerconfidence",
    "studentunderstanding", "learnerunderstanding", "learningmethod",
    "teachingmethod", "teachingstrategy", "practice", "assessment",
    "episode", "skill", "dataflow", "chat", "memory", "topic",
    "example", "explanation",
}

BANNED_FRAGMENTS = [
    "teaching", "tutorstrategy", "learningstatus", "confidence",
    "emotion", "dialogue", "episode", "skill", "dataflow",
    "workedexample", "diagnostic", "socratic",
    "讲解方式", "教学方式", "教学方法", "导师策略", "举例方式",
    "学习方式", "学习状态", "理解程度", "学生信心", "练习反馈",
    "对话", "片段", "图谱",
]


def is_banned_concept_name(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return True
    if normalized in BANNED_CONCEPT_NAMES:
        return True
    return any(fragment in normalized for fragment in BANNED_FRAGMENTS)


def concept_is_grounded(
    concept: dict[str, Any],
    *,
    grounding_text: str,
) -> bool:
    normalized_text = _normalize_text(grounding_text)
    names = [
        str(concept.get("name", "")).strip(),
        *[str(alias).strip() for alias in concept.get("aliases", []) if str(alias).strip()],
    ]
    for name in names:
        normalized_name = _normalize_text(name)
        if len(normalized_name) >= 3 and normalized_name in normalized_text:
            return True
        if any("\u4e00" <= char <= "\u9fff" for char in name):
            compact_name = "".join(name.split())
            if len(compact_name) >= 2 and compact_name in grounding_text:
                return True
    return False


def build_grounding_text(
    episode: dict[str, Any],
    turns: list[dict[str, Any]],
    evidence: str = "",
) -> str:
    learner = episode.get("learner", {})
    tutor = episode.get("tutor", {})
    outcome = episode.get("outcome", {})
    parts = [
        episode.get("title", ""),
        episode.get("summary", ""),
        learner.get("goal", ""),
        learner.get("obstacle", ""),
        *learner.get("evidence", []),
        tutor.get("strategy", ""),
        *tutor.get("key_moves", []),
        outcome.get("evidence", ""),
        evidence,
    ]
    for turn in turns:
        parts.append(str(turn.get("user_message", turn.get("content", ""))))
        parts.append(str(turn.get("assistant_message", "")))
    return "\n".join(str(part) for part in parts if str(part).strip())


class HeuristicConceptExtractor:
    """Rule-based fallback concept extraction."""

    def extract(
        self,
        episode: dict[str, Any],
        turns: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        text = build_grounding_text(episode, turns or [])
        lower = text.lower()
        concepts: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []

        def add(*, name: str, aliases: list[str], description: str,
                role: str, learner_state: str, salience: float, evidence: str) -> None:
            if not any(c["name"] == name for c in concepts):
                concepts.append({"name": name, "aliases": aliases, "description": description})
            relations.append({
                "concept_name": name, "role": role,
                "learner_state": learner_state, "salience": salience, "evidence": evidence,
            })

        obstacle = str(episode.get("learner", {}).get("obstacle", ""))
        outcome_status = str(episode.get("outcome", {}).get("status", ""))
        bayes = any(t in text for t in ["贝叶斯", "检测准确率", "后验概率", "先验概率"]) or "posterior" in lower
        cond = any(t in text for t in ["条件概率", "P(A|B)", "P(B|A)"]) or "conditional probability" in lower
        deriv = "导数" in text or "derivative" in lower
        factor = "因式分解" in text or "factorization" in lower

        if bayes:
            add(name="Bayes theorem", aliases=["贝叶斯定理", "贝叶斯公式"],
                description="利用先验概率和似然更新信念的概率规则。",
                role="main", learner_state="confused" if "混淆" in obstacle else "neutral",
                salience=0.92, evidence="本轮主要讨论贝叶斯定理相关内容。")
        if cond:
            state = "clarified" if outcome_status in {"success", "partial_success"} else "confused"
            add(name="Conditional probability", aliases=["条件概率", "P(A|B)"],
                description="在已知某条件下事件发生的概率。",
                role="supporting" if bayes else "main", learner_state=state,
                salience=0.84 if bayes else 0.90, evidence="导师重点对比了条件概率的方向差异。")
        if deriv:
            add(name="Derivative", aliases=["导数"],
                description="度量一个量相对于另一个量变化速率的概念。",
                role="main", learner_state="confused" if "不懂" in text else "neutral",
                salience=0.91, evidence="本轮围绕导数概念进行讲解。")
        if factor:
            add(name="Factorization", aliases=["因式分解"],
                description="将表达式改写为更简单因子之积。",
                role="main",
                learner_state="clarified" if outcome_status in {"success", "partial_success"} else "confused",
                salience=0.91, evidence="本轮围绕因式分解展开。")

        return {"concepts": concepts, "relations": relations}


def coerce_concept_payload_from_llm(
    raw: str,
    episode: dict[str, Any],
    turns: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    fallback = HeuristicConceptExtractor().extract(episode, turns)
    try:
        payload = _normalize_json_payload(raw)
        raw_concepts = payload.get("concepts", [])
        raw_relations = payload.get("relations", [])
        concepts = []
        for item in raw_concepts:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            concepts.append({
                "name": name,
                "aliases": [str(a) for a in item.get("aliases", []) if str(a).strip()],
                "description": str(item.get("description", "")).strip(),
            })
        relations = []
        for item in raw_relations:
            concept_name = str(item.get("concept_name", "")).strip()
            if not concept_name:
                continue
            role = str(item.get("role", "context")).strip().lower()
            learner_state = str(item.get("learner_state", "neutral")).strip().lower()
            if role not in STRUCTURAL_ROLES:
                role = "context"
            if learner_state not in LEARNER_STATES:
                learner_state = "neutral"
            try:
                salience = float(item.get("salience", 0.0))
            except (TypeError, ValueError):
                salience = 0.0
            relations.append({
                "concept_name": concept_name,
                "role": role,
                "learner_state": learner_state,
                "salience": max(0.0, min(1.0, salience)),
                "evidence": str(item.get("evidence", "")).strip(),
            })
        if not concepts or not relations:
            return fallback
        return {"concepts": concepts, "relations": relations}
    except Exception:
        return fallback


def sanitize_concept_payload(
    payload: dict[str, list[dict[str, Any]]],
    *,
    episode: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Filter and validate extracted concepts against grounding text."""
    concepts = payload.get("concepts", [])
    relations = payload.get("relations", [])
    grounding = build_grounding_text(episode, turns)

    concept_lookup = {
        str(c.get("name", "")).strip(): c
        for c in concepts
        if str(c.get("name", "")).strip() and not is_banned_concept_name(str(c.get("name", "")))
    }

    kept_edges: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    main_assigned = False

    sorted_relations = sorted(relations, key=lambda r: float(r.get("salience", 0.0)), reverse=True)

    for rel in sorted_relations:
        concept_name = str(rel.get("concept_name", "")).strip()
        concept = concept_lookup.get(concept_name)
        if concept is None:
            continue
        if is_banned_concept_name(concept_name):
            continue
        if concept_name in seen_targets:
            continue

        salience = float(rel.get("salience", 0.0))
        role = str(rel.get("role", "context"))
        evidence = str(rel.get("evidence", "")).strip()

        if not evidence:
            continue
        if not concept_is_grounded(concept, grounding_text=grounding):
            continue

        if role == "main" and salience < 0.80:
            continue
        elif role == "supporting" and salience < 0.55:
            continue
        elif role == "context":
            continue

        if role == "main":
            if main_assigned:
                rel = {**rel, "role": "supporting"}
            else:
                main_assigned = True

        kept_edges.append({
            "target_name": concept_name,
            "weight": salience,
            "evidence": evidence,
            "metadata": {
                "structural_role": rel["role"],
                "learner_relation": rel.get("learner_state", "neutral"),
                "confidence": salience,
            },
        })
        seen_targets.add(concept_name)
        if len(kept_edges) == 3:
            break

    if kept_edges and not any(e["metadata"]["structural_role"] == "main" for e in kept_edges):
        kept_edges[0] = {
            **kept_edges[0],
            "metadata": {**kept_edges[0]["metadata"], "structural_role": "main"},
        }

    kept_names = {e["target_name"] for e in kept_edges}
    kept_concepts = [c for c in concepts if str(c.get("name", "")).strip() in kept_names]
    return {"concepts": kept_concepts, "edges": kept_edges}
