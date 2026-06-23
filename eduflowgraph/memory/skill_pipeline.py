from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from ..schemas import utc_now
from ..skills import (
    ACTION_TO_SUCCESS_CRITERIA,
    DIFFICULTY_PATTERNS,
    DIFFICULTY_PATTERN_TAXONOMY,
    TEACHING_ACTIONS,
    TEACHING_ACTION_TAXONOMY,
)


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


def normalize_name(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value).strip().lower())


CONCEPT_FAMILY_MARKERS = {
    "probability_conditioning": (
        "conditionalprobability",
        "conditional",
        "baserate",
        "bayes",
        "bayestheorem",
        "bayesrule",
        "posterior",
        "priorprobability",
        "totalprobability",
        "falsepositive",
        "pab",
        "pba",
        "条件概率",
        "条件方向",
        "贝叶斯",
        "后验",
        "先验",
        "基率",
        "全概率",
        "假阳性",
        "检测准确率",
    ),
}


def concept_family_keys(value: str) -> set[str]:
    normalized = normalize_name(value)
    if not normalized:
        return set()
    keys = {normalized}
    for family, markers in CONCEPT_FAMILY_MARKERS.items():
        if any(marker in normalized for marker in markers):
            keys.add(family)
    return keys


def episode_outcome_level(result: str, score: float) -> int:
    if result == "success":
        return 3
    if result == "partial_success" and score >= 0.55:
        return 2
    if result == "partial_success":
        return 1
    if result == "unresolved":
        return 1
    return 0


def positive_outcome(result: str, score: float) -> bool:
    return episode_outcome_level(result, score) >= 2


class HeuristicSkillEvidenceExtractor:
    def extract(
        self,
        episode: dict[str, Any],
        turns: list[dict[str, Any]],
        *,
        concept_names: list[str],
        concept_ids: list[str],
    ) -> dict[str, Any]:
        learner = episode.get("learner", {})
        tutor = episode.get("tutor", {})
        outcome = episode.get("outcome", {})
        text = "\n".join(str(t.get("content", t.get("user_message", ""))) for t in turns)
        lower = text.lower()
        student_text = "\n".join(
            str(t.get("content", t.get("user_message", "")))
            for t in turns
            if str(t.get("actor", t.get("role", ""))).lower() in ("student", "user")
        )
        assistant_text = "\n".join(
            str(t.get("content", t.get("assistant_message", "")))
            for t in turns
            if str(t.get("actor", t.get("role", ""))).lower() in ("assistant", "tutor")
        )
        assistant_lower = assistant_text.lower()

        actions: list[str] = []

        def add_action(name: str) -> None:
            if name in TEACHING_ACTIONS and name not in actions:
                actions.append(name)

        main_strategy = str(tutor.get("strategy", "")).strip()
        add_action(main_strategy)

        if (
            "对比" in text
            or "区分" in text
            or "p(a|b)" in lower
            or "p(b|a)" in lower
        ):
            add_action("contrastive_explanation")
        if any(token in assistant_text for token in ["第一步", "第二步", "逐步", "一步一步", "分步骤"]):
            add_action("step_by_step_guidance")
        if any(token in assistant_text for token in ["例题", "完整解法", "示范", "按照这个例子"]) or "worked example" in assistant_lower:
            add_action("worked_example")
        if re.search(r"\b10\b|\b100\b", assistant_text) or "100人" in assistant_text or "小例子" in assistant_text or "心算" in assistant_text:
            add_action("concrete_example")
        if any(token in assistant_text for token in ["公式", "推导", "derive", "log-derivative", "log 导数"]):
            add_action("formula_decomposition")
        if any(token in assistant_text for token in ["复述", "用自己的话", "你来说说", "你能说出", "你自己解释"]):
            add_action("self_explanation_prompt")
        if any(
            token in assistant_text for token in ["检查", "练习", "判断", "确认", "小检查", "验证一下"]
        ):
            add_action("diagnostic_check")
        if "你觉得" in assistant_text or "为什么" in assistant_text:
            add_action("socratic_questioning")
        if any(token in assistant_text for token in ["相似任务", "自己试试", "独立完成", "减少提示"]):
            add_action("guided_practice")
        if any(token in assistant_text for token in ["错在", "纠正", "不对", "修正", "错误"]):
            add_action("error_correction")

        if not actions:
            add_action("worked_example")
        actions = actions[:4]

        obstacle = str(learner.get("obstacle", ""))
        title = str(episode.get("title", ""))

        difficulty_pattern = "unknown"
        if any(
            token in f"{text} {obstacle} {title}"
            for token in ["P(A|B)", "P(B|A)", "检测准确率", "后验概率", "方向差异", "条件方向"]
        ) or "direction" in lower:
            difficulty_pattern = "direction_confusion"
        elif any(token in text for token in ["公式", "符号", "记号"]) and any(
            token in student_text for token in ["不懂", "看不懂", "没懂", "含义"]
        ):
            difficulty_pattern = "symbol_grounding"
        elif any(token in student_text for token in ["不会做", "不知道怎么开始"]) or (
            main_strategy == "step_by_step_guidance"
            and any(token in assistant_text for token in ["逐步", "一步一步", "分步骤"])
        ):
            difficulty_pattern = "procedural_gap"
        elif any(token in student_text for token in ["换一个", "相似题", "迁移"]):
            difficulty_pattern = "transfer_failure"
        elif any(token in student_text for token in ["太抽象", "没直觉", "没有感觉"]) or (
            "concrete_example" in actions and difficulty_pattern == "unknown"
        ):
            difficulty_pattern = "abstraction_gap"
        elif any(token in student_text for token in ["搞不清", "混淆", "分不清"]) or (
            "混淆" in obstacle or "困惑" in obstacle
        ):
            difficulty_pattern = "conceptual_confusion"

        outcome_status = str(outcome.get("status", "unresolved"))
        outcome_evidence = str(outcome.get("evidence", ""))

        concept_scope_list = concept_names or []

        return {
            "episode_id": episode.get("episode_id", ""),
            "session_id": episode.get("provenance", {}).get("session_id", ""),
            "concept_ids": concept_ids,
            "concept_names": concept_names,
            "teaching_actions": actions,
            "difficulty_pattern": difficulty_pattern if difficulty_pattern in DIFFICULTY_PATTERNS else "unknown",
            "concept_scope": concept_scope_list,
            "outcome_signal": outcome_status,
            "outcome": {
                "result": outcome_status,
                "score": 0.0,
                "understanding_after": "unknown",
            },
            "learning_delta": outcome_status in {"success", "partial_success"},
            "evidence_summary": outcome_evidence or str(episode.get("summary", "")),
            "source_event_ids": [
                str(t.get("event_id"))
                for t in turns
                if str(t.get("event_id", "")).strip()
            ],
        }


def coerce_skill_evidence_payload_from_llm(
    raw: str,
    episode: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    concept_names: list[str],
    concept_ids: list[str],
) -> dict[str, Any]:
    fallback = HeuristicSkillEvidenceExtractor().extract(
        episode,
        turns,
        concept_names=concept_names,
        concept_ids=concept_ids,
    )
    try:
        payload = _normalize_json_payload(raw)
        actions = []
        for item in payload.get("teaching_actions", []):
            name = str(item).strip()
            if name in TEACHING_ACTIONS and name not in actions:
                actions.append(name)
        difficulty_pattern = str(payload.get("difficulty_pattern", "unknown")).strip()
        if difficulty_pattern not in DIFFICULTY_PATTERNS:
            difficulty_pattern = "unknown"
        if not actions:
            return fallback
        fallback["teaching_actions"] = actions[:4]
        fallback["difficulty_pattern"] = difficulty_pattern
        concept_scope = [
            str(item).strip()
            for item in payload.get("concept_scope", fallback.get("concept_scope", []))
            if str(item).strip()
        ]
        if concept_scope:
            fallback["concept_scope"] = concept_scope
        fallback["outcome_signal"] = str(
            payload.get("outcome_signal") or fallback.get("outcome_signal", "unresolved")
        ).strip()
        fallback["evidence_summary"] = str(
            payload.get("evidence_summary") or fallback["evidence_summary"]
        ).strip()
        return fallback
    except Exception:
        return fallback


def _difficulty_phrase(pattern: str) -> str:
    return DIFFICULTY_PATTERN_TAXONOMY.get(pattern, DIFFICULTY_PATTERN_TAXONOMY["unknown"]).get(
        "trigger_phrase",
        "the learner difficulty pattern is still unclear",
    )


def _skill_name(pattern: str, primary_action: str) -> str:
    templates = {
        "direction_confusion": "用对比解释澄清方向混淆",
        "symbol_grounding": "通过公式拆解和复述落地符号含义",
        "transfer_failure": "用例题示范支持迁移到相似题",
        "procedural_gap": "通过引导拆解建立可执行步骤",
        "abstraction_gap": "用具体例子落地抽象概念",
        "conceptual_confusion": "通过对比和追问澄清概念混淆",
    }
    return templates.get(pattern, f"用{primary_action}处理{pattern.replace('_', ' ')}")


def _pattern_success_criteria(pattern: str) -> list[str]:
    criteria = {
        "direction_confusion": [
            "学习者能说明两个对象的方向差异，并且不再反着解释。",
            "学习者能在新场景中正确区分两个目标。",
        ],
        "symbol_grounding": [
            "学习者能解释公式中每一项的含义。",
            "学习者能用日常语言把公式连回背后的思想。",
        ],
        "transfer_failure": [
            "学习者能把方法迁移到相似题，而不是照抄原例。",
            "学习者能说明相似例子中哪些不变、哪些改变。",
        ],
        "procedural_gap": [
            "学习者能按顺序说出关键步骤。",
            "学习者能自己开始拆解相似问题。",
        ],
        "abstraction_gap": [
            "学习者能把具体例子映射回抽象概念。",
            "学习者能在看过例子后复述抽象思想。",
        ],
        "conceptual_confusion": [
            "学习者能清楚区分容易混淆的概念。",
            "学习者能用自己的话解释核心概念的定义和边界。",
        ],
    }
    return criteria.get(pattern, [])


def _build_skill_id(pattern: str, actions: list[str], concept_scope: list[str]) -> str:
    slug_parts = [pattern, *actions[:2]]
    slug = re.sub(r"[^a-z0-9]+", "_", "_".join(slug_parts).lower()).strip("_")
    if slug:
        return f"skill_{slug}"
    scope = "|".join(concept_scope)
    digest = hashlib.md5(f"{pattern}|{scope}".encode("utf-8")).hexdigest()[:10]
    return f"skill_{digest}"


def _edge_weight_from_evidence(evidence: dict[str, Any]) -> float:
    result = str(evidence.get("outcome", {}).get("result", evidence.get("outcome_signal", "unresolved")))
    score = float(evidence.get("outcome", {}).get("score", 0.0))
    level = episode_outcome_level(result, score)
    if level >= 3:
        return max(0.9, min(1.0, score + 0.08))
    if level == 2:
        return max(0.78, min(0.89, score + 0.12))
    return max(0.55, min(0.74, score + 0.15))


def _confidence_from_window(evidences: list[dict[str, Any]]) -> float:
    if not evidences:
        return 0.0
    avg_score = sum(float(item.get("outcome", {}).get("score", 0.0)) for item in evidences) / len(evidences)
    bonus = 0.08 * min(len(evidences), 4)
    if has_learning_improvement(evidences):
        bonus += 0.1
    elif has_repeated_success(evidences):
        bonus += 0.06
    return max(0.45, min(0.95, avg_score + bonus))


def has_learning_improvement(evidences: list[dict[str, Any]]) -> bool:
    if len(evidences) < 2:
        return False
    levels = [
        episode_outcome_level(
            str(item.get("outcome", {}).get("result", item.get("outcome_signal", "unresolved"))),
            float(item.get("outcome", {}).get("score", 0.0)),
        )
        for item in evidences
    ]
    return min(levels[:-1]) <= 1 and levels[-1] >= 2 and levels[-1] > levels[0]


def has_repeated_success(evidences: list[dict[str, Any]]) -> bool:
    if len(evidences) < 2:
        return False
    positive = [
        item
        for item in evidences
        if positive_outcome(
            str(item.get("outcome", {}).get("result", item.get("outcome_signal", "unresolved"))),
            float(item.get("outcome", {}).get("score", 0.0)),
        )
    ]
    return len(positive) >= 2


def same_concept_family(left: list[str], right: list[str]) -> bool:
    left_set = set().union(*(concept_family_keys(item) for item in left)) if left else set()
    right_set = set().union(*(concept_family_keys(item) for item in right)) if right else set()
    if not left_set or not right_set:
        return False
    return bool(left_set & right_set)


def skill_evidence_concept_scope(skill: dict[str, Any]) -> list[str]:
    metadata = skill.get("metadata", {})
    scope = metadata.get("evidence_concept_scope", skill.get("concept_scope", []))
    return [str(item) for item in scope if str(item).strip()]


def actions_signature(actions: list[str]) -> tuple[str, ...]:
    return tuple(sorted({item for item in actions if item in TEACHING_ACTIONS}))


def action_overlap(left: list[str], right: list[str]) -> float:
    left_set = set(actions_signature(left))
    right_set = set(actions_signature(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def skill_matches_evidence(skill: dict[str, Any], evidence: dict[str, Any]) -> bool:
    if skill.get("difficulty_pattern") != evidence.get("difficulty_pattern"):
        return False
    if action_overlap(skill.get("teaching_actions", []), evidence.get("teaching_actions", [])) < 0.6:
        return False
    return same_concept_family(skill_evidence_concept_scope(skill), evidence.get("concept_names", []))


def skill_matches_candidate(existing: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if existing.get("difficulty_pattern") != candidate.get("difficulty_pattern"):
        return False
    if action_overlap(existing.get("teaching_actions", []), candidate.get("teaching_actions", [])) < 0.6:
        return False
    return same_concept_family(
        skill_evidence_concept_scope(existing),
        skill_evidence_concept_scope(candidate),
    )


class HeuristicSkillDistiller:
    def distill(
        self,
        episodes: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        raw_events_by_episode: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        if len(episodes) < 2 or len(evidences) < 2:
            return None
        source_episode_ids = [
            str(evidence.get("episode_id", "")).strip()
            for evidence in evidences
            if str(evidence.get("episode_id", "")).strip()
        ]
        if len(set(source_episode_ids)) < 2:
            return None
        pattern = str(evidences[-1].get("difficulty_pattern", "unknown"))
        if pattern == "unknown":
            return None
        if not (has_learning_improvement(evidences) or has_repeated_success(evidences)):
            return None

        concept_counter: Counter[str] = Counter()
        action_counter: Counter[str] = Counter()
        source_episode_ids = []
        for evidence in evidences:
            for name in evidence.get("concept_names", []):
                normalized = normalize_name(name)
                if normalized and normalized not in {"unknown", "learningconcept", "untitledconcept"}:
                    concept_counter[name] += 1
            for action in evidence.get("teaching_actions", []):
                if action in TEACHING_ACTIONS:
                    action_counter[action] += 1
            episode_id = str(evidence.get("episode_id", "")).strip()
            if episode_id and episode_id not in source_episode_ids:
                source_episode_ids.append(episode_id)

        concept_scope = [
            name for name, _ in concept_counter.most_common(3)
        ]
        if not concept_scope:
            return None
        teaching_actions = [
            name for name, _ in action_counter.most_common(4)
        ] or ["worked_example"]

        action_labels = [
            TEACHING_ACTION_TAXONOMY[action]["label"].lower()
            for action in teaching_actions
            if action in TEACHING_ACTION_TAXONOMY
        ]
        primary_action = action_labels[0] if action_labels else "引导式教学"
        name = _skill_name(pattern, primary_action)
        trigger = f"当学习者出现{_difficulty_phrase(pattern)}时使用。"

        procedure: list[str] = []
        for action in teaching_actions:
            for step in TEACHING_ACTION_TAXONOMY.get(action, {}).get("procedure_steps", []):
                if step not in procedure:
                    procedure.append(step)
        procedure = procedure[:3] or ["用可复用的讲解流程引导学习者。"]

        success_criteria = _pattern_success_criteria(pattern)
        for action in teaching_actions:
            criterion = ACTION_TO_SUCCESS_CRITERIA.get(action)
            if criterion and criterion not in success_criteria:
                success_criteria.append(criterion)
        success_criteria = success_criteria[:2] or [
            "学习者能在新例子中正确解释核心思想。"
        ]

        confidence = _confidence_from_window(evidences)
        now = utc_now()
        skill_id = _build_skill_id(pattern, teaching_actions, concept_scope)
        skill = {
            "skill_id": skill_id,
            "node_id": skill_id,
            "node_type": "skill",
            "name": name,
            "status": "candidate",
            "trigger": trigger,
            "difficulty_pattern": pattern,
            "teaching_actions": teaching_actions,
            "procedure": procedure,
            "success_criteria": success_criteria,
            "quality": {
                "support_episode_count": len(source_episode_ids),
                "validation_success_count": 0,
                "validation_fail_count": 0,
                "confidence": confidence,
                "last_validated_at": None,
            },
            "metadata": {
                "created_at": now,
                "updated_at": now,
                "extractor_version": "skill_distiller_v1_fallback",
                "source_episode_ids": source_episode_ids,
                "evidence_concept_scope": concept_scope,
            },
            "embedding_text": (
                f"教学技能：{name}。适用困难：{_difficulty_phrase(pattern)}。"
                f"教学动作：{', '.join(teaching_actions)}。"
            ),
        }

        edges = []
        for evidence in evidences:
            episode_id = str(evidence.get("episode_id", "")).strip()
            if not episode_id:
                continue
            edges.append(
                {
                    "edge_id": f"edge_{episode_id}_{skill_id}",
                    "edge_type": "episode_skill",
                    "source": episode_id,
                    "target": skill_id,
                    "weight": _edge_weight_from_evidence(evidence),
                    "evidence": evidence.get("evidence_summary", ""),
                    "metadata": {
                        "role": "source_evidence",
                        "confidence": max(0.7, confidence - 0.04),
                        "extractor_version": "skill_distiller_v1_fallback",
                        "created_at": now,
                    },
                }
            )
        return {"skill": skill, "edges": edges}


def coerce_skill_distillation_payload_from_llm(
    raw: str,
    episodes: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    raw_events_by_episode: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    fallback = HeuristicSkillDistiller().distill(episodes, evidences, raw_events_by_episode)
    try:
        payload = _normalize_json_payload(raw)
        if payload.get("should_create_skill") is False:
            return None
        skill_payload = payload.get("skill", {})
        edges_payload = payload.get("edges", [])
        if fallback is None:
            return None
        skill = dict(fallback["skill"])
        skill["name"] = str(skill_payload.get("name") or skill["name"]).strip()
        skill["status"] = "candidate"
        skill["trigger"] = str(skill_payload.get("trigger") or skill["trigger"]).strip()
        metadata = dict(skill.get("metadata", {}))
        evidence_scope = [
            str(item).strip()
            for item in skill_payload.get(
                "evidence_concept_scope",
                skill_payload.get("concept_scope", metadata.get("evidence_concept_scope", [])),
            )
            if str(item).strip()
        ][:3]
        if evidence_scope:
            metadata["evidence_concept_scope"] = evidence_scope
        skill["metadata"] = metadata
        skill.pop("concept_scope", None)
        difficulty_pattern = str(
            skill_payload.get("difficulty_pattern", skill["difficulty_pattern"])
        ).strip()
        if difficulty_pattern in DIFFICULTY_PATTERNS:
            skill["difficulty_pattern"] = difficulty_pattern
        actions = []
        for action in skill_payload.get("teaching_actions", skill["teaching_actions"]):
            name = str(action).strip()
            if name in TEACHING_ACTIONS and name not in actions:
                actions.append(name)
        if actions:
            skill["teaching_actions"] = actions[:4]
        procedure = [
            str(item).strip()
            for item in skill_payload.get("procedure", skill["procedure"])
            if str(item).strip()
        ]
        if procedure:
            skill["procedure"] = procedure[:3]
        criteria = [
            str(item).strip()
            for item in skill_payload.get("success_criteria", skill["success_criteria"])
            if str(item).strip()
        ]
        if criteria:
            skill["success_criteria"] = criteria[:2]
        skill["embedding_text"] = str(
            skill_payload.get("embedding_text") or skill["embedding_text"]
        ).strip()

        edge_map = {edge["source"]: dict(edge) for edge in fallback["edges"]}
        normalized_edges = []
        for item in edges_payload:
            episode_id = str(item.get("episode_id") or item.get("source") or "").strip()
            if episode_id not in edge_map:
                continue
            edge = dict(edge_map[episode_id])
            try:
                weight = float(item.get("weight", edge["weight"]))
            except (TypeError, ValueError):
                weight = edge["weight"]
            edge["weight"] = max(0.0, min(1.0, weight))
            edge["evidence"] = str(item.get("evidence") or edge.get("evidence", "")).strip()
            edge_metadata = dict(edge.get("metadata", {}))
            item_metadata = item.get("metadata", {})
            if isinstance(item_metadata, dict):
                try:
                    confidence = float(item_metadata.get("confidence", edge_metadata.get("confidence", 0.0)))
                except (TypeError, ValueError):
                    confidence = float(edge_metadata.get("confidence", 0.0))
                edge_metadata["confidence"] = max(0.0, min(1.0, confidence))
            edge_metadata["role"] = "source_evidence"
            edge["metadata"] = edge_metadata
            normalized_edges.append(edge)
        return {"skill": skill, "edges": normalized_edges or fallback["edges"]}
    except Exception:
        return fallback


def merge_skill_candidate(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["teaching_actions"] = list(
        dict.fromkeys([*existing.get("teaching_actions", []), *candidate.get("teaching_actions", [])])
    )[:4]
    merged["procedure"] = list(
        dict.fromkeys([*existing.get("procedure", []), *candidate.get("procedure", [])])
    )[:3]
    merged["success_criteria"] = list(
        dict.fromkeys(
            [*existing.get("success_criteria", []), *candidate.get("success_criteria", [])]
        )
    )[:2]
    merged["trigger"] = candidate.get("trigger") or existing.get("trigger", "")
    quality = dict(existing.get("quality", {}))
    candidate_quality = candidate.get("quality", {})
    quality["support_episode_count"] = max(
        int(quality.get("support_episode_count", 0)),
        int(candidate_quality.get("support_episode_count", 0)),
    )
    quality["confidence"] = max(
        float(quality.get("confidence", 0.0)),
        float(candidate_quality.get("confidence", 0.0)),
    )
    quality.setdefault("validation_success_count", int(existing.get("quality", {}).get("validation_success_count", 0)))
    quality.setdefault("validation_fail_count", int(existing.get("quality", {}).get("validation_fail_count", 0)))
    quality.setdefault("last_validated_at", existing.get("quality", {}).get("last_validated_at"))
    merged["quality"] = quality
    metadata = dict(existing.get("metadata", {}))
    candidate_metadata = candidate.get("metadata", {})
    metadata["source_episode_ids"] = list(
        dict.fromkeys(
            [*metadata.get("source_episode_ids", []), *candidate_metadata.get("source_episode_ids", [])]
        )
    )
    metadata["evidence_concept_scope"] = list(
        dict.fromkeys(
            [
                *skill_evidence_concept_scope(existing),
                *skill_evidence_concept_scope(candidate),
            ]
        )
    )[:3]
    metadata.setdefault("created_at", candidate_metadata.get("created_at") or utc_now())
    metadata["updated_at"] = utc_now()
    metadata["extractor_version"] = candidate_metadata.get(
        "extractor_version",
        metadata.get("extractor_version", "skill_distiller_v1_fallback"),
    )
    merged["metadata"] = metadata
    merged.pop("concept_scope", None)
    merged["embedding_text"] = candidate.get("embedding_text") or existing.get("embedding_text", "")
    return merged


def apply_skill_validation_result(skill: dict[str, Any], *, success: bool) -> dict[str, Any]:
    updated = dict(skill)
    quality = dict(skill.get("quality", {}))
    if success:
        quality["validation_success_count"] = int(quality.get("validation_success_count", 0)) + 1
        quality["last_validated_at"] = utc_now()
        quality["confidence"] = min(0.95, float(quality.get("confidence", 0.0)) + 0.08)
    else:
        quality["validation_fail_count"] = int(quality.get("validation_fail_count", 0)) + 1
        quality["confidence"] = max(0.35, float(quality.get("confidence", 0.0)) - 0.06)
    updated["quality"] = quality
    if (
        int(quality.get("support_episode_count", 0)) >= 2
        and int(quality.get("validation_success_count", 0)) >= 1
        and float(quality.get("confidence", 0.0)) >= 0.7
    ):
        updated["status"] = "active"
    metadata = dict(skill.get("metadata", {}))
    metadata["updated_at"] = utc_now()
    updated["metadata"] = metadata
    return updated


def make_validation_edge(skill: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    episode_id = str(evidence.get("episode_id", "")).strip()
    now = utc_now()
    return {
        "edge_id": f"edge_{episode_id}_{skill['node_id']}",
        "edge_type": "episode_skill",
        "source": episode_id,
        "target": skill["node_id"],
        "weight": max(0.75, _edge_weight_from_evidence(evidence)),
        "evidence": evidence.get("evidence_summary", ""),
        "metadata": {
            "role": "validation",
            "confidence": max(0.7, float(skill.get("quality", {}).get("confidence", 0.0))),
            "extractor_version": skill.get("metadata", {}).get(
                "extractor_version",
                "skill_distiller_v1_fallback",
            ),
            "created_at": now,
        },
    }
