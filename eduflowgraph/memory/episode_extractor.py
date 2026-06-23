from __future__ import annotations

import json
import re
from typing import Any

from ..schemas import make_id, utc_now, EPISODE_TYPES, OUTCOME_STATUSES, INITIAL_STATES
from ..prompts import EPISODE_EXTRACTION_PROMPT
from ..llm import messages_for_prompt


class HeuristicEpisodeExtractor:
    """Rule-based fallback episode extraction."""

    def extract(self, turns: list[dict[str, Any]]) -> dict[str, Any]:
        episode_id = make_id("episode")
        text = "\n".join(
            f"{t.get('actor', t.get('role', 'unknown'))}: {t.get('content', t.get('user_message', ''))}"
            for t in turns
        )
        user_messages: list[str] = []
        for t in turns:
            msg = str(t.get("user_message", t.get("content", ""))).strip()
            actor = str(t.get("actor", t.get("role", ""))).lower()
            if actor in ("student", "user") or t.get("user_message"):
                if msg:
                    user_messages.append(msg)

        first_question = user_messages[0] if user_messages else ""
        misconceptions = self._detect_misconceptions(text)
        episode_type = self._detect_episode_type(text, misconceptions)
        strategy = self._detect_strategy(text)
        outcome = self._detect_outcome(text)
        title = self._make_title(first_question, misconceptions, episode_type)

        return {
            "episode_id": episode_id,
            "node_id": episode_id,
            "node_type": "episode",
            "episode_type": episode_type,
            "title": title,
            "summary": self._summarize(first_question, misconceptions, strategy, outcome["status"]),
            "learner": {
                "goal": first_question[:200] if first_question else "未明确",
                "obstacle": "；".join(misconceptions) if misconceptions else "未明确",
                "initial_state": "low" if misconceptions else "unclear",
                "evidence": misconceptions or ["需要更多诊断证据"],
            },
            "tutor": {
                "strategy": strategy,
                "key_moves": self._strategy_steps(strategy),
            },
            "outcome": {
                "status": outcome["status"],
                "evidence": outcome["evidence"],
                "next_step": self._follow_up(outcome["status"], first_question),
            },
            "memory_value": "记录了学习者在\u201c" + title[:30] + "\u201d上的学习过程，结果为" + outcome["status"] + "。",
        }

    def _detect_episode_type(self, text: str, misconceptions: list[str]) -> str:
        if "计划" in text or "安排" in text:
            return "planning"
        if "复习" in text or "回顾" in text:
            return "review"
        if "练习" in text or "检查" in text or "判断题" in text:
            return "assessment"
        if misconceptions:
            return "misconception_diagnosis"
        if "步骤" in text or "怎么做" in text or "求" in text:
            return "problem_solving"
        if "为什么" in text or "什么是" in text or "解释" in text:
            return "concept_explanation"
        return "other"

    def _detect_strategy(self, text: str) -> str:
        lowered = text.lower()
        if "p(a|b)" in lowered or "p(b|a)" in lowered or "区分" in text or "对比" in text:
            return "contrastive_explanation"
        if re.search(r"\b100\b|\b10\b", text) or "小例子" in text:
            return "concrete_example"
        if "为什么" in text or "你觉得" in text:
            return "socratic_questioning"
        if "步骤" in text or "第一" in text:
            return "step_by_step_guidance"
        return "worked_example"

    def _detect_misconceptions(self, text: str) -> list[str]:
        misconceptions: list[str] = []
        lowered = text.lower()
        if "检测准确率" in text or ("p(a|b)" in lowered and "p(b|a)" in lowered):
            misconceptions.append("把检测准确率当作后验概率")
        if "先验" in text and ("忽略" in text or "不考虑" in text):
            misconceptions.append("忽略先验概率")
        if "公式" in text and "不懂" in text:
            misconceptions.append("只记公式但缺少语义理解")
        return misconceptions

    def _detect_outcome(self, text: str) -> dict[str, Any]:
        if any(token in text for token in ["懂了", "明白了", "会了"]):
            return {"status": "success", "evidence": "学生明确表达已经理解。"}
        if any(token in text for token in ["还是不懂", "没懂", "不会"]):
            return {"status": "failed", "evidence": "学生仍然明确表达困惑或不会做。"}
        return {"status": "partial_success", "evidence": "完成了一轮有效讲解，但仍需后续检查。"}

    def _make_title(self, question: str, misconceptions: list[str], episode_type: str) -> str:
        if misconceptions:
            return misconceptions[0]
        if question:
            return question[:40]
        titles = {
            "concept_explanation": "概念讲解片段",
            "problem_solving": "解题推进片段",
            "misconception_diagnosis": "误区诊断片段",
            "assessment": "学习检测片段",
            "review": "回顾复习片段",
            "planning": "学习规划片段",
            "other": "教学片段",
        }
        return titles.get(episode_type, "教学片段")

    def _summarize(self, question: str, misconceptions: list[str], strategy: str, result: str) -> str:
        base = "学习者围绕\u201c" + question[:50] + "\u201d展开学习。"
        if misconceptions:
            base += f"暴露了{misconceptions[0]}。"
        base += f"导师采用{strategy}推进讲解，当前结果为{result}。"
        return base

    def _strategy_steps(self, strategy: str) -> list[str]:
        steps = {
            "contrastive_explanation": ["指出两类对象不同", "分别解释自然语言含义", "用同一情境做对比"],
            "concrete_example": ["设置小规模场景", "列出关键数量关系", "映射回问题本身"],
            "socratic_questioning": ["提出诊断问题", "根据回答追问", "让学生总结当前理解"],
            "step_by_step_guidance": ["拆解目标", "逐步解释", "检查每一步理解"],
            "worked_example": ["给出完整例题", "展示求解过程", "标出关键判断点"],
        }
        return steps.get(strategy, ["围绕当前问题进行讲解"])

    def _follow_up(self, result: str, question: str) -> str:
        if result == "success":
            return "可以切换到相邻概念或更高阶问题。"
        if result == "failed":
            return "下一轮先回到\u201c" + question[:30] + "\u201d中的核心误区，再用更小的例子重讲。"
        return "下一轮围绕\u201c" + question[:30] + "\u201d补一道检查题，确认学生能否独立迁移。"


def _normalize_episode_type(value: Any) -> str:
    candidate = str(value or "other").strip().lower()
    return candidate if candidate in EPISODE_TYPES else "other"


def _normalize_outcome_status(value: Any) -> str:
    candidate = str(value or "unresolved").strip().lower()
    if candidate in OUTCOME_STATUSES:
        return candidate
    legacy_map = {"fail": "failed", "unknown": "unresolved"}
    return legacy_map.get(candidate, "unresolved")


def _normalize_initial_state(value: Any) -> str:
    candidate = str(value or "unknown").strip().lower()
    return candidate if candidate in INITIAL_STATES else "unknown"


def coerce_episode_from_llm(raw: str, fallback_turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse LLM output (new prompt format) and normalize to internal episode dict."""
    fallback = HeuristicEpisodeExtractor().extract(fallback_turns)
    try:
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`").removeprefix("json").strip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return fallback
            payload = json.loads(stripped[start:end + 1])

        learner = payload.get("learner", {})
        tutor = payload.get("tutor", {})
        outcome = payload.get("outcome", {})

        return {
            "episode_id": fallback["episode_id"],
            "node_id": fallback["node_id"],
            "node_type": "episode",
            "episode_type": _normalize_episode_type(payload.get("episode_type")),
            "title": str(payload.get("title") or fallback["title"]),
            "summary": str(payload.get("summary") or fallback["summary"]),
            "learner": {
                "goal": str(learner.get("goal") or fallback["learner"]["goal"]),
                "obstacle": str(learner.get("obstacle") or fallback["learner"]["obstacle"]),
                "initial_state": _normalize_initial_state(learner.get("initial_state")),
                "evidence": [
                    str(item) for item in learner.get("evidence", fallback["learner"]["evidence"])
                    if str(item).strip()
                ] or fallback["learner"]["evidence"],
            },
            "tutor": {
                "strategy": str(tutor.get("strategy") or fallback["tutor"]["strategy"]),
                "key_moves": [
                    str(item) for item in tutor.get("key_moves", fallback["tutor"]["key_moves"])
                    if str(item).strip()
                ] or fallback["tutor"]["key_moves"],
            },
            "outcome": {
                "status": _normalize_outcome_status(outcome.get("status")),
                "evidence": str(outcome.get("evidence") or fallback["outcome"]["evidence"]),
                "next_step": str(outcome.get("next_step") or fallback["outcome"]["next_step"]),
            },
            "memory_value": str(payload.get("memory_value") or fallback["memory_value"]),
        }
    except Exception:
        return fallback


def finalize_episode(
    semantic_episode: dict[str, Any],
    *,
    segment_turns: list[dict[str, Any]],
    session_id: str,
    segment_id: str,
    extractor_version: str,
    extraction_confidence: float,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach provenance and retrieval metadata to a raw episode dict."""
    episode_id = str(semantic_episode.get("episode_id") or semantic_episode.get("node_id") or make_id("episode"))

    timestamps = [str(t.get("timestamp", "")) for t in segment_turns if t.get("timestamp")]
    start_time = timestamps[0] if timestamps else ""
    end_time = timestamps[-1] if timestamps else ""

    episode = dict(semantic_episode)
    episode["episode_id"] = episode_id
    episode["node_id"] = episode_id
    episode["node_type"] = "episode"
    turn_indices = [int(t.get("turn_index", 0)) for t in segment_turns if t.get("turn_index")]
    episode["provenance"] = {
        "segment_id": segment_id,
        "session_id": session_id,
        "start_time": start_time,
        "end_time": end_time,
        "turn_count": len(segment_turns),
        "turn_range": [min(turn_indices), max(turn_indices)] if turn_indices else [0, 0],
    }
    if retrieval:
        episode["retrieval"] = retrieval
    episode["extraction_metadata"] = {
        "extractor_version": extractor_version,
        "extraction_confidence": extraction_confidence,
        "created_at": utc_now(),
    }
    return episode
