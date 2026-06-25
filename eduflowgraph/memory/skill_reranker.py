from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Callable

from .skill_pipeline import skill_difficulty_patterns


RerankFn = Callable[
    [str, list[dict[str, Any]], str],
    list[dict[str, Any]],
]

SUPPORTED_SKILL_STATUSES = {"seed", "candidate", "active"}
GENERIC_FALLBACK_INSTRUCTION = (
    "先建立直观理解，再逐步展开关键步骤，并用一个简短问题检查理解。"
)
_FIRST_SENTENCE = re.compile(r"^(.{1,120}?[。！？!?])", re.DOTALL)


@dataclass(frozen=True)
class SkillSelectionConfig:
    min_confidence: float = 0.60
    min_personal_fit: float = 0.35
    min_final_score: float = 0.50
    candidate_pool_size: int = 12
    max_selected: int = 4
    degraded_min_confidence: float = 0.75
    degraded_min_base: float = 0.60
    degraded_min_episode_link: float = 0.50


class SkillPersonalizedReranker:
    """Select prompt-worthy Skills using profile-aware reranking evidence."""

    def __init__(
        self,
        rerank_fn: RerankFn | None,
        config: SkillSelectionConfig | None = None,
    ) -> None:
        self.rerank_fn = rerank_fn
        self.config = config or SkillSelectionConfig()

    def select(
        self,
        *,
        query: str,
        context_summary: str,
        adaptation_summary: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pool = self._prepare_pool(candidates)
        if not pool:
            return self._result(
                skills=[],
                candidates=[],
                status="skipped",
                adaptation_summary=adaptation_summary,
            )

        reranked: list[dict[str, Any]] | None = None
        if self.rerank_fn is not None:
            try:
                personalized_query = self._build_query(
                    query=query,
                    context_summary=context_summary,
                    adaptation_summary=adaptation_summary,
                )
                reranked = self.rerank_fn(
                    personalized_query,
                    pool,
                    "skill_personalization",
                )
                if not self._is_complete_rerank(reranked, pool):
                    reranked = None
            except Exception:
                reranked = None

        if reranked is None:
            skills, trace = self._select_degraded(pool)
            return self._result(
                skills=skills,
                candidates=trace,
                status="degraded",
                adaptation_summary=adaptation_summary,
            )

        has_scores = all(
            item.get("rerank", {}).get("relevance_score") is not None
            for item in reranked
        )
        status = "ok" if has_scores else "rank_only"
        skills, trace = self._select_reranked(reranked, rank_only=not has_scores)
        return self._result(
            skills=skills,
            candidates=trace,
            status=status,
            adaptation_summary=adaptation_summary,
        )

    def _prepare_pool(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        copied = [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]
        copied.sort(key=lambda item: self._number(item.get("base_raw_score", item.get("score", 0.0))), reverse=True)
        copied = copied[: self.config.candidate_pool_size]
        max_base = max(
            (self._number(item.get("base_raw_score", item.get("score", 0.0))) for item in copied),
            default=0.0,
        )
        max_episode = max(
            (self._number(item.get("episode_link_raw_score", 0.0)) for item in copied),
            default=0.0,
        )
        prepared: list[dict[str, Any]] = []
        for candidate in copied:
            node = candidate.get("node") if isinstance(candidate.get("node"), dict) else {}
            item = dict(candidate)
            item["id"] = str(candidate.get("id") or node.get("node_id") or "")
            item["node"] = dict(node)
            item["base_skill_score"] = self._ratio(
                self._number(candidate.get("base_raw_score", candidate.get("score", 0.0))),
                max_base,
            )
            item["episode_link_score"] = self._ratio(
                self._number(candidate.get("episode_link_raw_score", 0.0)),
                max_episode,
            )
            item["text"] = self._build_document(item)
            prepared.append(item)
        return prepared

    @staticmethod
    def _build_query(
        *,
        query: str,
        context_summary: str,
        adaptation_summary: str,
    ) -> str:
        return "\n".join(
            [
                "任务：根据学生当前问题、当前学习情境和长期教学适配偏好，判断哪个教学 Skill 最适合本轮。",
                "若 Skill 与避免或降权偏好冲突，应显著降分；不要仅按主题词相似度排序。",
                "",
                f"学生当前问题：{query.strip() or '暂无'}",
                f"当前学习情境：{context_summary.strip() or '暂无'}",
                f"教学适配偏好：{adaptation_summary.strip() or '暂无稳定偏好'}",
            ]
        )

    @staticmethod
    def _build_document(candidate: dict[str, Any]) -> str:
        node = candidate.get("node", {})
        evidence = candidate.get("episode_evidence", [])
        return "\n".join(
            [
                f"Skill: {node.get('name', '')}",
                f"Status: {node.get('status', 'candidate')}",
                f"Trigger: {node.get('trigger', '')}",
                "Difficulty patterns: " + ", ".join(skill_difficulty_patterns(node)),
                "Teaching actions: " + ", ".join(str(item) for item in node.get("teaching_actions", [])),
                "Procedure: " + "；".join(str(item) for item in node.get("procedure", [])),
                "Success criteria: " + "；".join(str(item) for item in node.get("success_criteria", [])),
                "Episode evidence: " + "；".join(str(item) for item in evidence),
            ]
        ).strip()

    @staticmethod
    def _is_complete_rerank(
        reranked: list[dict[str, Any]],
        pool: list[dict[str, Any]],
    ) -> bool:
        if not isinstance(reranked, list) or len(reranked) != len(pool):
            return False
        returned_ids = {str(item.get("id", "")) for item in reranked}
        pool_ids = {str(item.get("id", "")) for item in pool}
        return bool(pool_ids) and returned_ids == pool_ids

    def _select_reranked(
        self,
        reranked: list[dict[str, Any]],
        *,
        rank_only: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        count = len(reranked)
        for index, candidate in enumerate(reranked):
            node = candidate.get("node", {})
            confidence = self._clamp(
                self._number(node.get("quality", {}).get("confidence", 0.0))
            )
            if rank_only:
                personal_fit = 1.0 - (index / count)
            else:
                personal_fit = self._normalize_relevance(
                    candidate.get("rerank", {}).get("relevance_score")
                )
            base = self._clamp(self._number(candidate.get("base_skill_score", 0.0)))
            episode = self._clamp(self._number(candidate.get("episode_link_score", 0.0)))
            final_score = (
                0.35 * base
                + 0.20 * episode
                + 0.15 * confidence
                + 0.30 * personal_fit
            )
            filter_reason = self._filter_reason(
                status=str(node.get("status", "candidate")),
                confidence=confidence,
                personal_fit=personal_fit,
                final_score=final_score,
            )
            records.append(
                self._trace_record(
                    candidate,
                    confidence=confidence,
                    personal_fit=personal_fit,
                    final_score=final_score,
                    selected=not filter_reason,
                    filter_reason=filter_reason,
                )
            )

        eligible = [record for record in records if record["selected"]]
        eligible.sort(key=lambda item: item["final_skill_score"], reverse=True)
        selected_ids = {
            record["skill_id"] for record in eligible[: self.config.max_selected]
        }
        for record in records:
            if record["selected"] and record["skill_id"] not in selected_ids:
                record["selected"] = False
                record["filter_reason"] = "outside_top_k"
        nodes_by_id = {
            str(item.get("id", "")): item.get("node", {}) for item in reranked
        }
        skills = [dict(nodes_by_id[record["skill_id"]]) for record in eligible[: self.config.max_selected]]
        records.sort(key=lambda item: item["final_skill_score"], reverse=True)
        return skills, records

    def _select_degraded(
        self,
        pool: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        for candidate in pool:
            node = candidate.get("node", {})
            status = str(node.get("status", "candidate"))
            confidence = self._clamp(
                self._number(node.get("quality", {}).get("confidence", 0.0))
            )
            base = self._clamp(self._number(candidate.get("base_skill_score", 0.0)))
            episode = self._clamp(self._number(candidate.get("episode_link_score", 0.0)))
            selected = (
                status in SUPPORTED_SKILL_STATUSES
                and confidence >= self.config.degraded_min_confidence
                and base >= self.config.degraded_min_base
                and (status == "active" or episode >= self.config.degraded_min_episode_link)
            )
            final_score = 0.35 * base + 0.20 * episode + 0.15 * confidence
            records.append(
                self._trace_record(
                    candidate,
                    confidence=confidence,
                    personal_fit=0.0,
                    final_score=final_score,
                    selected=selected,
                    filter_reason="" if selected else "degraded_gate_failed",
                )
            )
        records.sort(key=lambda item: item["final_skill_score"], reverse=True)
        selected_records = [item for item in records if item["selected"]][: self.config.max_selected]
        selected_ids = {item["skill_id"] for item in selected_records}
        for record in records:
            if record["selected"] and record["skill_id"] not in selected_ids:
                record["selected"] = False
                record["filter_reason"] = "outside_top_k"
        nodes_by_id = {str(item.get("id", "")): item.get("node", {}) for item in pool}
        return [dict(nodes_by_id[item["skill_id"]]) for item in selected_records], records

    def _filter_reason(
        self,
        *,
        status: str,
        confidence: float,
        personal_fit: float,
        final_score: float,
    ) -> str:
        if status not in SUPPORTED_SKILL_STATUSES:
            return "unsupported_status"
        if confidence < self.config.min_confidence:
            return "low_confidence"
        if personal_fit < self.config.min_personal_fit:
            return "low_personal_fit"
        if final_score < self.config.min_final_score:
            return "low_final_score"
        return ""

    @staticmethod
    def _trace_record(
        candidate: dict[str, Any],
        *,
        confidence: float,
        personal_fit: float,
        final_score: float,
        selected: bool,
        filter_reason: str,
    ) -> dict[str, Any]:
        node = candidate.get("node", {})
        rerank = candidate.get("rerank", {})
        return {
            "skill_id": str(candidate.get("id") or node.get("node_id") or ""),
            "status": str(node.get("status", "candidate")),
            "base_skill_score": round(float(candidate.get("base_skill_score", 0.0)), 6),
            "episode_link_score": round(float(candidate.get("episode_link_score", 0.0)), 6),
            "skill_confidence": round(confidence, 6),
            "personal_fit_score": round(personal_fit, 6),
            "final_skill_score": round(final_score, 6),
            "rerank_rank": rerank.get("rank"),
            "rerank_source": str(rerank.get("source", "degraded")),
            "selected": selected,
            "filter_reason": filter_reason,
        }

    def _result(
        self,
        *,
        skills: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        status: str,
        adaptation_summary: str,
    ) -> dict[str, Any]:
        return {
            "skills": skills,
            "skill_selection": {
                "candidate_count": len(candidates),
                "selected_count": len(skills),
                "reranker_status": status,
                "fallback_instruction": (
                    "" if skills else self._fallback_instruction(adaptation_summary)
                ),
                "candidates": candidates,
            },
        }

    @staticmethod
    def _fallback_instruction(adaptation_summary: str) -> str:
        summary = " ".join((adaptation_summary or "").split()).strip()
        if not summary:
            return GENERIC_FALLBACK_INSTRUCTION
        matched = _FIRST_SENTENCE.match(summary)
        if matched:
            return matched.group(1).strip()
        return summary[:120].strip()

    @staticmethod
    def _normalize_relevance(value: Any) -> float:
        score = SkillPersonalizedReranker._number(value)
        if 0.0 <= score <= 1.0:
            return score
        if score >= 0:
            return 1.0 / (1.0 + math.exp(-min(score, 700.0)))
        exp_score = math.exp(max(score, -700.0))
        return exp_score / (1.0 + exp_score)

    @staticmethod
    def _ratio(value: float, maximum: float) -> float:
        if maximum <= 0:
            return 0.0
        return SkillPersonalizedReranker._clamp(value / maximum)

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
