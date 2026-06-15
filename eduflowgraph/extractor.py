import json
import re
from typing import Any

from .schemas import make_id


EPISODE_TYPES = {
    "concept_explanation",
    "problem_solving",
    "misconception_diagnosis",
    "assessment",
    "review",
    "planning",
    "other",
}

OUTCOME_RESULTS = {
    "success",
    "partial_success",
    "failed",
    "unresolved",
}


class HeuristicEpisodeExtractor:
    def extract(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        episode_id = make_id("episode")
        text = "\n".join(
            f"{event.get('actor', '')}: {event.get('content', '')}" for event in events
        )
        student_question = next(
            (event.get("content", "") for event in events if event.get("actor") == "student"),
            "",
        )
        misconceptions = self.detect_misconceptions(text)
        episode_type = self.detect_episode_type(text, misconceptions)
        strategy = self.detect_strategy(text)
        outcome = self.detect_outcome(text)
        title = self.make_title(student_question, misconceptions, episode_type)

        return {
            "episode_id": episode_id,
            "node_id": episode_id,
            "node_type": "episode",
            "episode_type": episode_type,
            "summary": {
                "title": title,
                "topic_summary": self.summarize_topic(student_question, misconceptions, strategy),
                "short_summary": self.summarize_short(misconceptions, strategy, outcome["result"]),
            },
            "learner_problem": {
                "student_question": student_question,
                "detected_problem": self.detect_problem(student_question, misconceptions),
                "misconceptions": misconceptions,
                "understanding_before": "low" if misconceptions else "partial",
                "difficulty_signals": self.difficulty_signals(text, misconceptions),
            },
            "tutor_action": {
                "main_strategy": strategy,
                "strategy_summary": self.strategy_summary(strategy),
                "teaching_steps": self.strategy_steps(strategy),
                "used_examples": "例" in text or "example" in text.lower() or "100" in text,
                "used_assessment": "检查" in text or "练习" in text or "题" in text,
            },
            "learning_outcome": {
                "result": outcome["result"],
                "understanding_after": outcome["understanding_after"],
                "score": outcome["score"],
                "evidence": outcome["evidence"],
                "needs_follow_up": outcome["result"] != "success",
                "follow_up_suggestion": self.follow_up_suggestion(outcome["result"], student_question),
            },
        }

    def detect_episode_type(self, text: str, misconceptions: list[str]) -> str:
        lowered = text.lower()
        if "计划" in text or "安排" in text:
            return "planning"
        if "复习" in text or "回顾" in text:
            return "review"
        if "练习" in text or "检查" in text or "判断题" in text or "小测" in text:
            return "assessment"
        if misconceptions:
            return "misconception_diagnosis"
        if "步骤" in text or "怎么做" in text or "求" in text:
            return "problem_solving"
        if "为什么" in text or "什么是" in text or "解释" in text or "explain" in lowered:
            return "concept_explanation"
        return "other"

    def detect_strategy(self, text: str) -> str:
        lowered = text.lower()
        if "p(a|b)" in lowered or "p(b|a)" in lowered or "区分" in text or "对比" in text:
            return "contrastive_explanation"
        if re.search(r"\b100\b|\b10\b", text) or "小例子" in text:
            return "minimal_numeric_example"
        if "为什么" in text or "你觉得" in text:
            return "socratic_questioning"
        if "步骤" in text or "第一" in text:
            return "step_by_step_explanation"
        return "worked_example"

    def detect_misconceptions(self, text: str) -> list[str]:
        misconceptions = []
        lowered = text.lower()
        if "检测准确率" in text or ("p(a|b)" in lowered and "p(b|a)" in lowered):
            misconceptions.append("把检测准确率当作后验概率")
        if "先验" in text and ("忽略" in text or "不考虑" in text):
            misconceptions.append("忽略先验概率")
        if "公式" in text and "不懂" in text:
            misconceptions.append("只记公式但缺少语义理解")
        return misconceptions

    def detect_problem(self, question: str, misconceptions: list[str]) -> str:
        if misconceptions:
            return "；".join(misconceptions)
        if question:
            return f"学生希望理解：{question[:80]}"
        return "当前片段以理解澄清为主。"

    def difficulty_signals(self, text: str, misconceptions: list[str]) -> list[str]:
        signals = list(misconceptions)
        if "还是不懂" in text or "没懂" in text:
            signals.append("学生明确表达仍然困惑")
        if "为什么" in text:
            signals.append("学生无法解释核心原因")
        if "不会" in text:
            signals.append("学生无法独立完成当前任务")
        return signals or ["需要更多诊断证据"]

    def detect_outcome(self, text: str) -> dict[str, Any]:
        if any(token in text for token in ["懂了", "明白了", "会了"]):
            return {
                "result": "success",
                "score": 0.82,
                "evidence": "学生明确表达已经理解。",
                "understanding_after": "good",
            }
        if any(token in text for token in ["还是不懂", "没懂", "不会"]):
            return {
                "result": "failed",
                "score": 0.28,
                "evidence": "学生仍然明确表达困惑或不会做。",
                "understanding_after": "low",
            }
        return {
            "result": "partial_success",
            "score": 0.62,
            "evidence": "完成了一轮有效讲解，但仍需后续检查。",
            "understanding_after": "partial",
        }

    def make_title(self, question: str, misconceptions: list[str], episode_type: str) -> str:
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

    def summarize_topic(
        self,
        question: str,
        misconceptions: list[str],
        strategy: str,
    ) -> str:
        if misconceptions:
            return f"学生围绕“{question[:50]}”暴露出{misconceptions[0]}，导师采用{strategy}进行澄清。"
        return f"导师围绕“{question[:50]}”开展解释，并采用{strategy}推进理解。"

    def summarize_short(
        self,
        misconceptions: list[str],
        strategy: str,
        result: str,
    ) -> str:
        base = "通过" + strategy + "推进讲解"
        if misconceptions:
            base += f"，聚焦{misconceptions[0]}"
        return f"{base}，当前结果为 {result}。"

    def strategy_summary(self, strategy: str) -> str:
        summaries = {
            "contrastive_explanation": "通过对比两个容易混淆的对象来澄清概念差异。",
            "minimal_numeric_example": "用一个最小数字例子把抽象概念落到具体情境中。",
            "socratic_questioning": "通过追问让学生暴露当前理解缺口。",
            "step_by_step_explanation": "把复杂问题拆成几个连续小步骤进行讲解。",
            "worked_example": "通过完整例题示范帮助学生建立整体理解。",
        }
        return summaries.get(strategy, "导师通过讲解推进本轮学习。")

    def strategy_steps(self, strategy: str) -> list[str]:
        steps = {
            "contrastive_explanation": ["指出两类对象不同", "分别解释自然语言含义", "用同一情境做对比"],
            "minimal_numeric_example": ["设置小规模场景", "列出关键数量关系", "映射回问题本身"],
            "socratic_questioning": ["提出诊断问题", "根据回答追问", "让学生总结当前理解"],
            "step_by_step_explanation": ["拆解目标", "逐步解释", "检查每一步理解"],
            "worked_example": ["给出完整例题", "展示求解过程", "标出关键判断点"],
        }
        return steps.get(strategy, ["围绕当前问题进行讲解"])

    def follow_up_suggestion(self, result: str, question: str) -> str:
        if result == "success":
            return "可以切换到相邻概念或更高阶问题。"
        if result == "failed":
            return f"下一轮先回到“{question[:30]}”中的核心误区，再用更小的例子重讲。"
        return f"下一轮围绕“{question[:30]}”补一道检查题，确认学生能否独立迁移。"


def _normalize_episode_type(value: Any) -> str:
    candidate = str(value or "other").strip().lower()
    return candidate if candidate in EPISODE_TYPES else "other"


def _normalize_outcome_result(value: Any) -> str:
    candidate = str(value or "unresolved").strip().lower()
    if candidate in OUTCOME_RESULTS:
        return candidate
    legacy_map = {"fail": "failed", "unknown": "unresolved"}
    return legacy_map.get(candidate, "unresolved")


def coerce_episode_from_llm(raw: str, fallback_events: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = HeuristicEpisodeExtractor().extract(fallback_events)
    try:
        payload = json.loads(raw)
        if payload.get("should_extract") is False:
            return fallback
        episode = payload.get("episode", payload)
        summary = episode.get("summary", {})
        learner_problem = episode.get("learner_problem", {})
        tutor_action = episode.get("tutor_action", {})
        learning_outcome = episode.get("learning_outcome", {})
        return {
            "episode_id": str(episode.get("episode_id") or fallback["episode_id"]),
            "node_id": str(episode.get("node_id") or episode.get("episode_id") or fallback["episode_id"]),
            "node_type": "episode",
            "episode_type": _normalize_episode_type(episode.get("episode_type")),
            "summary": {
                "title": str(summary.get("title") or fallback["summary"]["title"]),
                "topic_summary": str(
                    summary.get("topic_summary") or fallback["summary"]["topic_summary"]
                ),
                "short_summary": str(
                    summary.get("short_summary") or fallback["summary"]["short_summary"]
                ),
            },
            "learner_problem": {
                "student_question": str(
                    learner_problem.get("student_question")
                    or fallback["learner_problem"]["student_question"]
                ),
                "detected_problem": str(
                    learner_problem.get("detected_problem")
                    or fallback["learner_problem"]["detected_problem"]
                ),
                "misconceptions": [
                    str(item)
                    for item in learner_problem.get("misconceptions", fallback["learner_problem"]["misconceptions"])
                    if str(item).strip()
                ],
                "understanding_before": str(
                    learner_problem.get("understanding_before")
                    or fallback["learner_problem"]["understanding_before"]
                ),
                "difficulty_signals": [
                    str(item)
                    for item in learner_problem.get(
                        "difficulty_signals",
                        fallback["learner_problem"]["difficulty_signals"],
                    )
                    if str(item).strip()
                ],
            },
            "tutor_action": {
                "main_strategy": str(
                    tutor_action.get("main_strategy")
                    or fallback["tutor_action"]["main_strategy"]
                ),
                "strategy_summary": str(
                    tutor_action.get("strategy_summary")
                    or fallback["tutor_action"]["strategy_summary"]
                ),
                "teaching_steps": [
                    str(item)
                    for item in tutor_action.get(
                        "teaching_steps",
                        fallback["tutor_action"]["teaching_steps"],
                    )
                    if str(item).strip()
                ],
                "used_examples": bool(
                    tutor_action.get("used_examples", fallback["tutor_action"]["used_examples"])
                ),
                "used_assessment": bool(
                    tutor_action.get("used_assessment", fallback["tutor_action"]["used_assessment"])
                ),
            },
            "learning_outcome": {
                "result": _normalize_outcome_result(learning_outcome.get("result")),
                "understanding_after": str(
                    learning_outcome.get("understanding_after")
                    or fallback["learning_outcome"]["understanding_after"]
                ),
                "score": float(
                    learning_outcome.get("score", fallback["learning_outcome"]["score"])
                ),
                "evidence": str(
                    learning_outcome.get("evidence")
                    or fallback["learning_outcome"]["evidence"]
                ),
                "needs_follow_up": bool(
                    learning_outcome.get(
                        "needs_follow_up",
                        fallback["learning_outcome"]["needs_follow_up"],
                    )
                ),
                "follow_up_suggestion": str(
                    learning_outcome.get("follow_up_suggestion")
                    or fallback["learning_outcome"]["follow_up_suggestion"]
                ),
            },
        }
    except Exception:
        return fallback
