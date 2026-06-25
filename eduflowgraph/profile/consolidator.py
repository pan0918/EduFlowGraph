"""Lightweight profile and Skill-adaptation consolidator.

Rewrites short memory-note paragraphs instead of accumulating evidence:

* ``consolidate_episode`` rewrites ``learner_model`` and
  ``skill_adaptation`` at episode boundaries in a single LLM call.
* ``update_context`` lightly rewrites ``context_model`` every turn (time-sensitive).

Both have a deterministic mock path (no live LLM) that performs real add/remove
behavior by merging a derived sentence into the paragraph and trimming to budget.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..llm import messages_for_prompt
from ..prompts import CONTEXT_UPDATE_PROMPT, PROFILE_CONDENSE_PROMPT, PROFILE_UPDATE_PROMPT
from ..skills import TEACHING_ACTIONS
from .dimensions import PROFILE_MODELS, SKILL_ADAPTATION_META, model_budget, skill_adaptation_budget

_SENTENCE_SPLIT = re.compile(r"[。；\n]+")

# Short Chinese labels for teaching actions used in Skill preferences.
_ACTION_LABELS: dict[str, str] = {
    "contrastive_explanation": "对比讲解",
    "step_by_step_guidance": "分步引导",
    "worked_example": "例题示范",
    "socratic_questioning": "苏格拉底追问",
    "concrete_example": "具体实例",
    "formula_decomposition": "公式拆解",
    "self_explanation_prompt": "让学生复述",
    "diagnostic_check": "诊断小测",
    "guided_practice": "引导练习",
}

_ACTION_VALIDATION_LABELS: dict[str, str] = {
    "worked_example": "相似题迁移",
    "contrastive_explanation": "让学生复述差异",
    "step_by_step_guidance": "逐步撤除提示后的独立完成",
    "socratic_questioning": "让学生自行总结规则",
    "concrete_example": "从具体例子映射回抽象概念",
    "formula_decomposition": "解释各公式项含义",
    "self_explanation_prompt": "学生复述与换例迁移",
    "diagnostic_check": "短诊断题",
    "guided_practice": "减少支架后的独立练习",
}


class ProfileConsolidator:
    def __init__(self, llm: Any):
        self.llm = llm

    # ── Episode-level: learner portrait + Skill adaptation ─────────

    def consolidate_episode(
        self,
        *,
        current: dict[str, str],
        episode: dict[str, Any],
        concept_result: dict[str, Any] | None = None,
        skill_evidence: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, str]]:
        concept_names = [
            str(c.get("name", "")).strip()
            for c in (concept_result or {}).get("concepts", [])
            if str(c.get("name", "")).strip()
        ]
        actions = [
            a
            for a in (skill_evidence or {}).get("teaching_actions", [])
            if a in TEACHING_ACTIONS
        ]
        if getattr(self.llm, "is_live", False):
            try:
                return self._episode_with_llm(current, episode, concept_names, actions)
            except Exception:
                return self._episode_mock(current, episode, concept_names, actions)
        return self._episode_mock(current, episode, concept_names, actions)

    def _episode_with_llm(
        self,
        current: dict[str, str],
        episode: dict[str, Any],
        concept_names: list[str],
        actions: list[str],
    ) -> dict[str, dict[str, str]]:
        learner = episode.get("learner", {})
        outcome = episode.get("outcome", {})
        tutor = episode.get("tutor", {})
        learner_evidence = [
            str(item).strip()
            for item in learner.get("evidence", [])
            if str(item).strip()
        ]
        prompt = PROFILE_UPDATE_PROMPT.format(
            learner_budget=model_budget("learner_model"),
            adaptation_budget=skill_adaptation_budget(),
            learner_current=current.get("learner_model", "") or "（暂无）",
            adaptation_current=current.get("skill_adaptation", "") or "（暂无）",
            episode_title=episode.get("title", ""),
            episode_summary=episode.get("summary", ""),
            episode_learner=f"目标：{learner.get('goal', '')}；障碍：{learner.get('obstacle', '')}",
            learner_evidence="；".join(learner_evidence) or "（无额外行为证据）",
            episode_outcome=f"{outcome.get('status', '')}：{outcome.get('evidence', '')}",
            episode_next_step=str(outcome.get("next_step", "")).strip() or "（无）",
            tutor_strategy=str(tutor.get("strategy", "")).strip() or "（无）",
            concept_names=", ".join(concept_names) or "（无）",
            teaching_actions=", ".join(actions) or "（无）",
        )
        raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
        payload = _extract_json(raw)
        updates: dict[str, dict[str, str]] = {}
        for model_name in ("learner_model", "skill_adaptation"):
            entry = payload.get(model_name)
            if isinstance(entry, dict):
                budget = (
                    skill_adaptation_budget()
                    if model_name == "skill_adaptation"
                    else model_budget(model_name)
                )
                summary = self._sanitize_summary(
                    str(entry.get("summary", "")).strip(),
                    model_name,
                    budget,
                )
                if summary:
                    updates[model_name] = {
                        "summary": summary,
                        "note": str(entry.get("note", "")).strip(),
                    }
        return updates

    def _episode_mock(
        self,
        current: dict[str, str],
        episode: dict[str, Any],
        concept_names: list[str],
        actions: list[str],
    ) -> dict[str, dict[str, str]]:
        updates: dict[str, dict[str, str]] = {}
        title = str(episode.get("title", "本轮学习")).strip() or "本轮学习"
        learner = episode.get("learner", {})
        obstacle = str(learner.get("obstacle", "")).strip()
        outcome = episode.get("outcome", {})
        status = str(outcome.get("status", "unresolved"))
        next_step = str(outcome.get("next_step", "")).strip()
        topic = concept_names[0] if concept_names else title

        # ── learner_model: long-term, hedged, no "懂了=掌握" ──
        if status == "success":
            if obstacle:
                learner_sentence = (
                    f"「{topic}」上曾反复出现{obstacle}，本轮口头确认理解，长期掌握尚待独立验证"
                )
            else:
                learner_sentence = (
                    f"「{topic}」本轮口头表示理解，仍待通过变式题或独立推理进一步确认"
                )
        elif status == "partial_success":
            if obstacle:
                learner_sentence = (
                    f"「{topic}」上仍有{obstacle}的迹象，本轮有进展但不宜视为已掌握"
                )
            else:
                learner_sentence = (
                    f"「{topic}」本轮有初步理解，掌握程度仍需后续巩固与检验"
                )
        elif status == "failed":
            learner_sentence = (
                f"「{topic}」上倾向于出现理解障碍"
                + (f"（{obstacle}）" if obstacle else "")
                + "，需多次不同情境验证"
            )
        else:
            learner_sentence = f"「{topic}」学习进展尚不明确，需更多观察"

        merged, note = _merge_sentence(
            current.get("learner_model", ""),
            learner_sentence,
            topic,
            budget=model_budget("learner_model"),
        )
        if note:
            updates["learner_model"] = {"summary": merged, "note": note}

        # ── skill_adaptation: generalized Skill selection evidence ──
        if actions or next_step:
            primary = actions[0] if actions else ""
            action_label = _ACTION_LABELS.get(primary, primary) if primary else "低认知负荷讲解"
            difficulty = obstacle or "类似学习困难"
            validation = _ACTION_VALIDATION_LABELS.get(primary, "简短理解检查")
            if status in ("success", "partial_success"):
                adaptation_sentence = (
                    f"当学生出现{difficulty}时，更适合优先选择{action_label}类 Skill，"
                    f"并通过{validation}确认适配效果；该偏好仍待跨主题验证"
                )
            elif status == "failed":
                adaptation_sentence = (
                    f"当学生出现{difficulty}时，应降低{action_label}类 Skill 的优先级，"
                    "优先尝试不同认知负荷或表达路径"
                )
            else:
                adaptation_sentence = (
                    f"学生出现{difficulty}时可谨慎尝试{action_label}类 Skill，"
                    f"并用{validation}继续收集适配证据"
                )

            merged_adaptation, adaptation_note = _merge_sentence(
                current.get("skill_adaptation", ""),
                adaptation_sentence,
                primary or difficulty,
                budget=skill_adaptation_budget(),
            )
            if adaptation_note:
                updates["skill_adaptation"] = {
                    "summary": merged_adaptation,
                    "note": adaptation_note,
                }

        return updates

    # ── Turn-level: context_model ───────────────────────────────────

    def update_context(
        self,
        *,
        current: str,
        user_message: str,
        assistant_message: str,
    ) -> dict[str, dict[str, str]]:
        if getattr(self.llm, "is_live", False):
            try:
                return self._context_with_llm(current, user_message, assistant_message)
            except Exception:
                return self._context_mock(current, user_message)
        return self._context_mock(current, user_message)

    def _context_with_llm(
        self, current: str, user_message: str, assistant_message: str
    ) -> dict[str, dict[str, str]]:
        prompt = CONTEXT_UPDATE_PROMPT.format(
            context_budget=model_budget("context_model"),
            context_current=current or "（暂无）",
            user_message=user_message,
            assistant_message=_trim(assistant_message, 400),
        )
        raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
        payload = _extract_json(raw)
        entry = payload.get("context_model")
        if isinstance(entry, dict):
            summary = self._sanitize_summary(
                str(entry.get("summary", "")).strip(),
                "context_model",
                model_budget("context_model"),
            )
            if summary:
                return {
                    "context_model": {
                        "summary": summary,
                        "note": str(entry.get("note", "")).strip(),
                    }
                }
        return {}

    def _context_mock(self, current: str, user_message: str) -> dict[str, dict[str, str]]:
        text = user_message.strip()
        if not text:
            return {}

        # Only situational: task + phase + emotion. No cognitive diagnosis.
        if any(t in text for t in ["练习", "做题", "测一下", "考考我", "出题"]):
            sentence = "当前任务：通过练习/测验检验掌握；阶段：评估；情绪：主动检验"
        elif any(t in text for t in ["换个说法", "再讲一次", "还是不懂", "没懂", "不明白"]):
            sentence = "当前任务：继续理解同一讲解内容；阶段：探索；情绪：困惑、尚未满意"
        elif any(t in text for t in ["懂了", "明白了", "会了", "原来如此"]):
            sentence = "当前任务：刚完成一轮理解确认；阶段：探索收尾；情绪：暂时放松/满意"
        elif any(t in text for t in ["解释", "讲讲", "什么是", "帮我理解", "怎么", "为什么"]):
            sentence = "当前任务：请求概念/原理解释；阶段：探索；情绪：主动提问"
        elif any(t in text for t in ["复习", "回顾", "总结"]):
            sentence = "当前任务：回顾已学内容；阶段：复习巩固；情绪：系统性梳理"
        elif any(t in text for t in ["Deadline", "deadline", "考试", "截止", "赶时间"]):
            sentence = "当前任务：备考/赶进度学习；阶段：应用/冲刺；情绪：有一定时间压力"
        else:
            return {}

        merged = _trim(sentence, model_budget("context_model"))
        if merged == (current or "").strip():
            return {}
        return {"context_model": {"summary": merged, "note": f"更新情境：{sentence}"}}

    def _sanitize_summary(self, text: str, model_name: str, budget: int) -> str:
        """Post-process LLM/mock output to enforce model-specific guardrails."""
        text = (text or "").strip()
        if not text:
            return ""
        if len(text) > budget:
            text = self._condense_summary(text, model_name, budget)
        text = _trim(text, budget)
        if model_name == "learner_model":
            text = _OVERCONFIDENT_PATTERNS.sub("理解尚待验证", text)
        return text.strip()

    def _condense_summary(self, text: str, model_name: str, budget: int) -> str:
        """Use LLM to compress over-budget summaries while preserving semantics."""
        meta = (
            SKILL_ADAPTATION_META
            if model_name == "skill_adaptation"
            else PROFILE_MODELS.get(model_name, {})
        )
        description = str(meta.get("description", "")).strip() or model_name
        current = text.strip()
        if len(current) <= budget:
            return current
        if not getattr(self.llm, "is_live", False):
            return _trim(current, budget)

        for _ in range(3):
            if len(current) <= budget:
                return current
            prompt = PROFILE_CONDENSE_PROMPT.format(
                model_name=model_name,
                model_description=description,
                char_budget=budget,
                current_summary=current,
            )
            try:
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
            except Exception:
                break
            condensed = (raw or "").strip().strip("`").strip()
            if condensed.startswith("{"):
                payload = _extract_json(condensed)
                condensed = str(payload.get("summary", "")).strip() or condensed
            if not condensed:
                break
            current = condensed
        return current


# ── helpers ─────────────────────────────────────────────────────────

# Phrases that imply overconfident mastery — strip from learner_model output.
_OVERCONFIDENT_PATTERNS = re.compile(
    r"(已建立较好理解|已掌握|完全理解|彻底搞懂|不会再看错|已经掌握|完全搞懂)"
)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s.strip()]


def _join_sentences(sentences: list[str]) -> str:
    return "。".join(sentences) + "。" if sentences else ""


def _merge_sentence(
    current: str, new_sentence: str, topic_key: str, *, budget: int
) -> tuple[str, str]:
    """Merge a derived sentence into a paragraph with real add/remove behavior."""
    sentences = _split_sentences(current)
    removed = False
    key = (topic_key or "").strip()
    if key:
        kept = []
        for s in sentences:
            if key and key in s and not removed:
                removed = True
                continue
            kept.append(s)
        sentences = kept

    if new_sentence in sentences:
        return _join_sentences(sentences), ""
    sentences.append(new_sentence)

    dropped = 0
    while len(_join_sentences(sentences)) > budget and len(sentences) > 1:
        sentences.pop(0)
        dropped += 1

    note_parts = [f"新增：{new_sentence}"]
    if removed:
        note_parts.append("替换同主题旧描述")
    if dropped:
        note_parts.append(f"删除{dropped}条过旧内容")
    return _join_sentences(sentences), "；".join(note_parts)


def _trim(text: str, budget: int) -> str:
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    sentences = _split_sentences(text)
    out: list[str] = []
    for s in sentences:
        candidate = _join_sentences(out + [s])
        if len(candidate) > budget:
            break
        out.append(s)
    return _join_sentences(out) if out else text[:budget]


def _extract_json(raw: str) -> dict[str, Any]:
    stripped = (raw or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.removeprefix("json").strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}
