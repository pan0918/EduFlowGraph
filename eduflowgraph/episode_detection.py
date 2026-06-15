import json
from pathlib import Path
from typing import Any

from .llm import messages_for_prompt


PROMPT_PATH = Path(__file__).resolve().parent / "Prompt" / "Episode_Detection_Prompt.md"

DEFAULT_DECISION = {
    "should_end": False,
    "should_wait": True,
    "force_end": False,
    "confidence": 0.5,
    "reason": "continue_current_episode",
    "completion_status": "unresolved",
    "topic_summary": "",
    "boundary_position": "none",
    "closed_event_policy": "none",
}

COMPLETION_REASONS = {
    "learning_goal_completed",
    "misconception_evidence",
    "assessment_completed",
    "problem_solving_closed",
}

BOUNDARY_REASONS = {
    "topic_shift",
    "intent_shift",
    "concept_shift",
    "time_gap",
    "buffer_too_long",
    "session_end",
}

SHIFT_REASONS = {"topic_shift", "intent_shift", "concept_shift", "time_gap"}

LEARNER_CONFIRMATION_MARKERS = [
    "我明白",
    "明白了",
    "我懂",
    "懂了",
    "理解了",
    "清楚了",
    "搞懂了",
    "会了",
    "学会了",
    "我现在能",
    "我可以解释",
    "我能解释",
    "这样清楚",
    "有用",
    "makes sense",
    "i understand",
    "got it",
]

LEARNER_UNRESOLVED_MARKERS = [
    "不懂",
    "没懂",
    "不明白",
    "没明白",
    "不理解",
    "没理解",
    "困惑",
    "迷糊",
    "复杂",
    "太多",
    "能不能",
    "可以再",
    "再解释",
    "再讲",
    "举例",
    "例子",
    "为什么",
    "怎么",
    "如何",
    "一知半解",
    "题目",
    "做题",
    "what",
    "why",
    "how",
    "confused",
]

LEARNER_REQUEST_MARKERS = [
    "解释",
    "讲",
    "教",
    "什么是",
    "为什么",
    "怎么",
    "如何",
    "题",
    "练习",
    "检查",
    "对比",
    "区分",
    "能不能",
    "可以",
    "explain",
    "why",
    "how",
]

CONTINUATION_MARKERS = [
    "再",
    "继续",
    "还是",
    "这个",
    "它",
    "刚才",
    "上面",
    "前面",
    "例子",
    "举例",
    "练习",
    "题目",
    "做题",
    "出题",
    "检查",
    "同样",
    "相似",
    "more",
    "again",
    "same",
    "this",
]

SOCIAL_CLOSURE_MARKERS = [
    "谢谢",
    "感谢",
    "好的",
    "好",
    "ok",
    "thanks",
    "thank you",
]

STOP_TOPIC_TERMS = {
    "我",
    "你",
    "帮",
    "请",
    "一下",
    "这个",
    "那个",
    "可以",
    "能不能",
    "为什么",
    "怎么",
    "如何",
    "解释",
    "讲",
    "再",
    "继续",
    "还是",
    "例子",
    "题目",
    "练习",
    "检查",
    "the",
    "and",
    "for",
    "what",
    "why",
    "how",
    "please",
    "explain",
}

LEARNER_NEGATIVE_MARKERS = [
    "不懂",
    "没懂",
    "不明白",
    "没明白",
    "不理解",
    "没理解",
    "困惑",
    "迷糊",
    "confused",
]


def _render_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "(empty)"
    lines = []
    for event in events:
        actor = event.get("actor", "unknown")
        event_type = event.get("event_type", "message")
        content = str(event.get("content", "")).strip()
        timestamp = event.get("timestamp", "")
        lines.append(f"[{timestamp}] {actor}/{event_type}: {content}")
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
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


def _latest_student_content(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("actor") == "student" or event.get("event_type") == "user_message":
            return str(event.get("content", "")).strip()
    return ""


def _student_contents(events: list[dict[str, Any]]) -> list[str]:
    return [
        str(event.get("content", "")).strip()
        for event in events
        if event.get("actor") == "student" or event.get("event_type") == "user_message"
    ]


def _has_learner_confirmation(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in LEARNER_NEGATIVE_MARKERS):
        return False
    return any(marker in normalized for marker in LEARNER_CONFIRMATION_MARKERS)


def _is_unresolved_learning_request(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in LEARNER_UNRESOLVED_MARKERS)


def _is_learning_request(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in LEARNER_REQUEST_MARKERS)


def _is_social_or_confirmation_only(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return True
    without_space = "".join(normalized.split())
    if len(without_space) > 24:
        return False
    return _has_learner_confirmation(normalized) or any(
        marker in normalized for marker in SOCIAL_CLOSURE_MARKERS
    )


def _has_extractable_learning_content(events: list[dict[str, Any]]) -> bool:
    student_messages = [
        content
        for content in _student_contents(events)
        if content and not _is_social_or_confirmation_only(content)
    ]
    if not student_messages:
        return False
    if any(_is_learning_request(content) for content in student_messages):
        return True
    return len(student_messages) >= 2


def _topic_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set()
    current = []
    for char in lowered:
        if char.isascii() and char.isalnum():
            current.append(char)
        else:
            if len(current) >= 3:
                token = "".join(current)
                if token not in STOP_TOPIC_TERMS:
                    terms.add(token)
            current = []
    if len(current) >= 3:
        token = "".join(current)
        if token not in STOP_TOPIC_TERMS:
            terms.add(token)

    chinese_chunks = []
    current_chunk = []
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            current_chunk.append(char)
        else:
            if current_chunk:
                chinese_chunks.append("".join(current_chunk))
            current_chunk = []
    if current_chunk:
        chinese_chunks.append("".join(current_chunk))
    for chunk in chinese_chunks:
        for size in (4, 3, 2):
            for index in range(0, max(0, len(chunk) - size + 1)):
                token = chunk[index : index + size]
                if token not in STOP_TOPIC_TERMS:
                    terms.add(token)
    return terms


def _looks_like_topic_shift(
    history: list[dict[str, Any]],
    new_messages: list[dict[str, Any]],
) -> bool:
    if not _has_extractable_learning_content(history):
        return False
    latest_student = _latest_student_content(new_messages)
    if not latest_student or not _is_learning_request(latest_student):
        return False
    if _has_learner_confirmation(latest_student):
        return False
    normalized = latest_student.lower()
    if any(marker in normalized for marker in CONTINUATION_MARKERS):
        return False

    history_text = "\n".join(_student_contents(history))
    history_terms = _topic_terms(history_text)
    new_terms = _topic_terms(latest_student)
    if not history_terms or not new_terms:
        return False
    overlap = len(history_terms & new_terms) / max(1, min(len(history_terms), len(new_terms)))
    return overlap < 0.18


class EpisodeBoundaryDetector:
    def __init__(self, llm: Any, max_events: int):
        self.llm = llm
        self.max_events = max(2, max_events)
        self.prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    @property
    def hard_max_events(self) -> int:
        return max(self.max_events * 3, self.max_events + 4)

    @property
    def emergency_max_events(self) -> int:
        return max(self.hard_max_events * 2, self.hard_max_events + 6)

    def evaluate(
        self,
        *,
        history: list[dict[str, Any]],
        new_messages: list[dict[str, Any]],
        time_gap: str = "unknown",
    ) -> dict[str, Any]:
        all_events = [*history, *new_messages]
        if getattr(self.llm, "is_live", False):
            try:
                prompt = (
                    self.prompt_template
                    .replace("{history}", _render_events(history))
                    .replace("{time_gap}", time_gap)
                    .replace("{new_messages}", _render_events(new_messages))
                    .replace(
                        "{buffer_stats}",
                        json.dumps(
                            {
                                "event_count": len(all_events),
                                "max_events": self.max_events,
                                "hard_max_events": self.hard_max_events,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                raw = self.llm.chat(
                    messages_for_prompt(prompt),
                    temperature=0,
                )
                decision = self._normalize_decision(_extract_json_object(raw))
                return self._apply_student_feedback_gate(decision, history, new_messages)
            except Exception:
                return self._fallback_decision(history, new_messages)
        return self._fallback_decision(history, new_messages)

    def _normalize_decision(self, raw: dict[str, Any]) -> dict[str, Any]:
        decision = {**DEFAULT_DECISION, **raw}
        decision["should_end"] = bool(decision.get("should_end"))
        decision["should_wait"] = bool(decision.get("should_wait"))
        decision["force_end"] = bool(decision.get("force_end"))
        try:
            confidence = float(decision.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        decision["confidence"] = max(0.0, min(1.0, confidence))
        decision["reason"] = str(decision.get("reason") or DEFAULT_DECISION["reason"])
        if decision["reason"] == "concept_shift":
            decision["reason"] = "topic_shift"
        decision["completion_status"] = str(
            decision.get("completion_status") or DEFAULT_DECISION["completion_status"]
        )
        decision["topic_summary"] = str(decision.get("topic_summary") or "")
        boundary_position = str(
            decision.get("boundary_position") or DEFAULT_DECISION["boundary_position"]
        )
        if boundary_position not in {"none", "before_new_messages", "after_new_messages"}:
            boundary_position = "none"
        if boundary_position == "none" and (
            decision["should_end"] or decision["force_end"]
        ):
            boundary_position = (
                "before_new_messages"
                if decision["reason"] in SHIFT_REASONS
                else "after_new_messages"
            )
        decision["boundary_position"] = boundary_position
        closed_event_policy = str(
            decision.get("closed_event_policy") or DEFAULT_DECISION["closed_event_policy"]
        )
        if closed_event_policy not in {"none", "include_new_messages", "exclude_new_messages"}:
            closed_event_policy = "none"
        if closed_event_policy == "none" and boundary_position != "none":
            closed_event_policy = (
                "exclude_new_messages"
                if boundary_position == "before_new_messages"
                else "include_new_messages"
            )
        decision["closed_event_policy"] = closed_event_policy
        return decision

    def _fallback_decision(
        self,
        history: list[dict[str, Any]],
        new_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        all_events = [*history, *new_messages]
        latest_student = _latest_student_content(new_messages) or _latest_student_content(all_events)
        if _looks_like_topic_shift(history, new_messages):
            return {
                **DEFAULT_DECISION,
                "should_end": True,
                "should_wait": False,
                "confidence": 0.72,
                "reason": "topic_shift",
                "completion_status": "interrupted",
                "topic_summary": "New learner message starts a different learning topic.",
                "boundary_position": "before_new_messages",
                "closed_event_policy": "exclude_new_messages",
            }

        if (
            _has_learner_confirmation(latest_student)
            and _has_extractable_learning_content(all_events)
            and _has_extractable_learning_content(history)
        ):
            return {
                **DEFAULT_DECISION,
                "should_end": True,
                "should_wait": False,
                "confidence": 0.78,
                "reason": "learning_goal_completed",
                "completion_status": "completed",
                "topic_summary": "Learner confirmed understanding.",
                "boundary_position": "after_new_messages",
                "closed_event_policy": "include_new_messages",
            }

        if len(all_events) >= self.hard_max_events:
            if _is_unresolved_learning_request(latest_student) and len(all_events) < self.emergency_max_events:
                return {**DEFAULT_DECISION}
            return {
                **DEFAULT_DECISION,
                "should_end": True,
                "should_wait": False,
                "force_end": True,
                "confidence": 0.55,
                "reason": "buffer_too_long",
                "completion_status": "partial",
                "topic_summary": "Fallback boundary triggered by buffer length.",
                "boundary_position": "after_new_messages",
                "closed_event_policy": "include_new_messages",
            }
        return {**DEFAULT_DECISION}

    def _apply_student_feedback_gate(
        self,
        decision: dict[str, Any],
        history: list[dict[str, Any]],
        new_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        events = [*history, *new_messages]
        latest_student = _latest_student_content(new_messages) or _latest_student_content(events)

        if decision.get("reason") in SHIFT_REASONS:
            if not _has_extractable_learning_content(history):
                return {**DEFAULT_DECISION}
            return {
                **decision,
                "should_end": True,
                "should_wait": False,
                "boundary_position": "before_new_messages",
                "closed_event_policy": "exclude_new_messages",
            }

        if decision.get("reason") == "buffer_too_long" and (
            len(events) < self.hard_max_events
            or (
                _is_unresolved_learning_request(latest_student)
                and len(events) < self.emergency_max_events
            )
        ):
            return {
                **decision,
                "should_end": False,
                "should_wait": True,
                "force_end": False,
                "confidence": min(float(decision.get("confidence", 0.5)), 0.62),
                "reason": "continue_current_episode",
                "completion_status": "unresolved",
                "topic_summary": decision.get("topic_summary") or "",
            }

        if decision.get("force_end") or decision.get("reason") in BOUNDARY_REASONS:
            return decision

        learner_confirmed = _has_learner_confirmation(latest_student)
        learner_still_working = _is_unresolved_learning_request(latest_student)

        if learner_confirmed:
            if not _has_extractable_learning_content(events) or not _has_extractable_learning_content(history):
                return {**DEFAULT_DECISION}
            if not decision.get("should_end"):
                return {
                    **decision,
                    "should_end": True,
                    "should_wait": False,
                    "reason": "learning_goal_completed",
                    "completion_status": "completed",
                    "confidence": max(float(decision.get("confidence", 0.0)), 0.76),
                    "topic_summary": decision.get("topic_summary")
                    or "Learner confirmed understanding.",
                    "boundary_position": "after_new_messages",
                    "closed_event_policy": "include_new_messages",
                }
            return {
                **decision,
                "should_wait": False,
                "boundary_position": "after_new_messages",
                "closed_event_policy": "include_new_messages",
            }

        if decision.get("should_end") and (
            decision.get("reason") in COMPLETION_REASONS or learner_still_working
        ):
            return {
                **decision,
                "should_end": False,
                "should_wait": True,
                "force_end": False,
                "confidence": min(float(decision.get("confidence", 0.5)), 0.62),
                "reason": "continue_current_episode",
                "completion_status": "unresolved",
                "topic_summary": decision.get("topic_summary") or "",
            }

        return decision
