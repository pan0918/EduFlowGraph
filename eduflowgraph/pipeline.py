import json
import re
from typing import Any

from .concept_extractor import (
    HeuristicConceptExtractor,
    coerce_concept_payload_from_llm,
)
from .config import Settings
from .dataflow import DataFlowStore
from .episode_detection import EpisodeBoundaryDetector
from .extractor import HeuristicEpisodeExtractor, coerce_episode_from_llm
from .graph_store import GraphStore
from .llm import LLMClient, messages_for_prompt
from .prompts import (
    CONCEPT_EXTRACTION_PROMPT,
    EPISODE_EXTRACTION_PROMPT,
    SKILL_DISTILLATION_PROMPT,
    TUTOR_MEMORY_AUGMENTED_USER_PROMPT,
    TEACHING_ACTIONS_EXTRACTION_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    TUTOR_USER_PROMPT,
)
from .retriever import MemoryRetriever
from .skill_extractor import (
    HeuristicSkillDistiller,
    HeuristicSkillEvidenceExtractor,
    action_overlap,
    apply_skill_validation_result,
    coerce_skill_evidence_payload_from_llm,
    coerce_skill_distillation_payload_from_llm,
    make_validation_edge,
    positive_outcome,
    same_concept_family,
    skill_evidence_concept_scope,
    skill_matches_candidate,
    skill_matches_evidence,
)
from .schemas import make_id, utc_now


class BufferManager:
    def __init__(self, max_events: int):
        self.max_events = max_events
        self.events_by_session: dict[str, list[dict[str, Any]]] = {}
        self.closed_segments: list[dict[str, Any]] = []

    def add(self, event: dict[str, Any]) -> None:
        session_events = self.events_by_session.setdefault(event["session_id"], [])
        session_events.append(event)

    def consume(self, session_id: str) -> list[dict[str, Any]]:
        events = self.events_by_session.get(session_id, [])
        self.events_by_session[session_id] = []
        return events

    def consume_prefix(self, session_id: str, count: int) -> list[dict[str, Any]]:
        events = self.events_by_session.get(session_id, [])
        consumed = events[: max(0, count)]
        self.events_by_session[session_id] = events[max(0, count) :]
        return consumed

    def pending_segment(self, session_id: str) -> dict[str, Any] | None:
        candidates = [
            segment
            for segment in self.closed_segments
            if segment.get("session_id") == session_id
            and "episode_extraction_completed" not in segment
        ]
        return candidates[-1] if candidates else None


class TutorPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.dataflow = DataFlowStore(settings.dataflow_path)
        self.graph = GraphStore(settings.nodes_path, settings.edges_path)
        self.extractor = HeuristicEpisodeExtractor()
        self.concept_extractor = HeuristicConceptExtractor()
        self.skill_evidence_extractor = HeuristicSkillEvidenceExtractor()
        self.skill_distiller = HeuristicSkillDistiller()
        self.llm = LLMClient(
            settings.llm.provider,
            settings.llm.api_key,
            settings.llm.base_url,
            settings.llm.model_id,
            settings.embedding.model_id,
            llm_name=settings.llm.name,
            llm_api_version=settings.llm.api_version,
            llm_extra_headers=settings.llm.extra_headers,
            embedding_provider=settings.embedding.provider,
            embedding_api_key=settings.embedding.api_key,
            embedding_endpoint_url=settings.embedding.endpoint_url,
            embedding_api_version=settings.embedding.api_version,
            embedding_extra_headers=settings.embedding.extra_headers,
            embedding_dimensions=settings.embedding.dimensions,
            embedding_send_dimensions=settings.embedding.send_dimensions,
            embedding_name=settings.embedding.name,
            reranker_provider=settings.reranker.provider,
            reranker_api_key=settings.reranker.api_key,
            reranker_endpoint_url=settings.reranker.endpoint_url,
            reranker_api_version=settings.reranker.api_version,
            reranker_extra_headers=settings.reranker.extra_headers,
            reranker_model_id=settings.reranker.model_id,
            reranker_name=settings.reranker.name,
        )
        self.retriever = MemoryRetriever(
            self.graph,
            embedding_fn=self.llm.embedding,
            rerank_fn=lambda query, candidates, kind: self.llm.rerank(query, candidates, kind=kind),
            embedding_signature=self._embedding_signature(),
        )
        self.buffer = BufferManager(settings.extraction_turns)
        self.boundary_detector = EpisodeBoundaryDetector(
            self.llm,
            settings.extraction_turns,
        )
        self.refresh_from_storage()

    def _segment_has_learning_content(self, events: list[dict[str, Any]]) -> bool:
        student_messages = [
            str(event.get("content", "")).strip()
            for event in events
            if event.get("actor") == "student" or event.get("event_type") == "user_message"
        ]
        substantive = []
        for message in student_messages:
            normalized = message.lower().strip()
            compact = "".join(normalized.split())
            if not compact:
                continue
            if len(compact) <= 24 and any(
                marker in normalized
                for marker in ["谢谢", "感谢", "好的", "ok", "thanks", "thank you", "明白", "懂了", "理解了"]
            ):
                continue
            substantive.append(message)
        if not substantive:
            return False
        learning_markers = [
            "解释",
            "什么是",
            "为什么",
            "怎么",
            "如何",
            "例子",
            "题目",
            "做题",
            "出题",
            "练习",
            "检查",
            "不懂",
            "不会",
            "混淆",
            "对比",
            "区分",
            "explain",
            "why",
            "how",
        ]
        return any(
            any(marker in message.lower() for marker in learning_markers)
            for message in substantive
        ) or len(substantive) >= 2

    def refresh_from_storage(self) -> None:
        self.buffer.events_by_session = self.dataflow.rebuild_open_buffers()
        self.buffer.closed_segments = self.dataflow.replay_segments()
        episodes = []
        concept_updates = []
        skill_updates = []
        validation_updates = []
        for segment in self.buffer.closed_segments:
            extraction = segment.get("episode_extraction_completed")
            if not extraction:
                continue
            episode = extraction.get("metadata", {}).get("episode")
            if episode:
                episodes.append(episode)
            concept_extraction = segment.get("concept_extraction_completed")
            if concept_extraction:
                concept_updates.append(concept_extraction.get("metadata", {}))
            skill_distillation = segment.get("skill_distillation_completed")
            if skill_distillation:
                skill_updates.append(skill_distillation.get("metadata", {}))
            skill_validation = segment.get("skill_validation_recorded")
            if skill_validation:
                validation_updates.append(skill_validation.get("metadata", {}))
        self.graph.reset()
        for episode in episodes:
            self.graph.apply_episode(episode, save=False)
        for update in concept_updates:
            episode_id = str(update.get("episode_id") or "")
            if not episode_id:
                continue
            self.graph.apply_concept_extraction(
                episode_id,
                concepts=list(update.get("concepts", [])),
                edges=list(update.get("edges", [])),
                save=False,
            )
        for update in skill_updates:
            skill = update.get("skill")
            if not isinstance(skill, dict):
                continue
            self.graph.apply_skill_distillation(
                skill=skill,
                edges=list(update.get("edges", [])),
                save=False,
            )
        for update in validation_updates:
            skill = update.get("skill")
            if not isinstance(skill, dict):
                continue
            self.graph.apply_skill_validation(
                skill=skill,
                edge=update.get("edge") if isinstance(update.get("edge"), dict) else None,
                save=False,
            )
        self._backfill_skill_distillations_from_evidence()
        self.graph.save()

    def _render_segment_for_extraction(self, events: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"[{event.get('timestamp', '')}] {event.get('actor', 'unknown')}: {event.get('content', '')}"
            for event in events
        )

    def _build_retrieval(self, episode: dict[str, Any]) -> dict[str, Any]:
        summary = episode["summary"]
        learner_problem = episode["learner_problem"]
        tutor_action = episode["tutor_action"]
        outcome = episode["learning_outcome"]
        keywords = []
        for value in [
            summary.get("title", ""),
            learner_problem.get("detected_problem", ""),
            *learner_problem.get("misconceptions", []),
            tutor_action.get("main_strategy", ""),
            episode.get("episode_type", ""),
            outcome.get("result", ""),
        ]:
            text = str(value).strip()
            if text and text not in keywords:
                keywords.append(text)
        embedding_text = (
            f"Episode类型：{episode.get('episode_type', 'other')}。"
            f"标题：{summary.get('title', '')}。"
            f"问题：{learner_problem.get('detected_problem', '')}。"
            f"导师动作：{tutor_action.get('strategy_summary', '')}。"
            f"结果：{outcome.get('evidence', '')}"
        )
        return self._make_retrieval_asset(embedding_text, keywords)

    def _embedding_signature(self) -> dict[str, Any]:
        return {
            "provider": self.settings.embedding.provider,
            "model_id": self.settings.embedding.model_id,
            "dimensions": self.settings.embedding.dimensions or 0,
        }

    def _make_retrieval_asset(self, embedding_text: str, keywords: list[str]) -> dict[str, Any]:
        vector: list[float] = []
        try:
            if embedding_text:
                vector = self.llm.embedding(embedding_text)
        except Exception:
            vector = []
        return {
            "embedding_text": embedding_text,
            "keywords": keywords,
            "embedding_vector": vector,
            "embedding_metadata": {
                "provider": self.settings.embedding.provider,
                "model_id": self.settings.embedding.model_id,
                "dimensions": self.settings.embedding.dimensions or len(vector),
                "created_at": utc_now(),
            },
        }

    def _build_concept_retrieval(self, concept: dict[str, Any]) -> dict[str, Any]:
        name = str(concept.get("name", "")).strip()
        aliases = [str(alias).strip() for alias in concept.get("aliases", []) if str(alias).strip()]
        description = str(concept.get("description", "")).strip()
        embedding_text = "\n".join(
            [
                f"Concept: {name}",
                f"Aliases: {', '.join(aliases)}" if aliases else "",
                f"Description: {description}" if description else "",
            ]
        ).strip()
        keywords = [item for item in [name, *aliases] if item]
        return self._make_retrieval_asset(embedding_text, keywords)

    def _build_skill_retrieval(self, skill: dict[str, Any]) -> dict[str, Any]:
        evidence_scope = skill_evidence_concept_scope(skill)
        procedure = [str(item) for item in skill.get("procedure", []) if str(item).strip()]
        success_criteria = [
            str(item) for item in skill.get("success_criteria", []) if str(item).strip()
        ]
        embedding_text = str(skill.get("embedding_text") or "").strip() or "\n".join(
            [
                f"Skill: {skill.get('name', '')}",
                f"Trigger: {skill.get('trigger', '')}",
                f"Difficulty pattern: {skill.get('difficulty_pattern', '')}",
                "Procedure: " + " ".join(procedure[:3]) if procedure else "",
                "Success criteria: " + " ".join(success_criteria[:2]) if success_criteria else "",
            ]
        ).strip()
        keywords = [
            str(skill.get("name", "")).strip(),
            str(skill.get("difficulty_pattern", "")).strip(),
            *[str(item) for item in skill.get("teaching_actions", []) if str(item).strip()],
            *evidence_scope,
        ]
        return self._make_retrieval_asset(embedding_text, [item for item in keywords if item])

    def _chat_history_messages(
        self,
        session_id: str,
        *,
        exclude_event_ids: set[str] | None = None,
        limit: int = 16,
    ) -> list[dict[str, str]]:
        excluded = exclude_event_ids or set()
        messages: list[dict[str, str]] = []
        for event in self.dataflow.list_events(session_id):
            if event["event_id"] in excluded:
                continue
            if event["event_type"] not in {"user_message", "assistant_message"}:
                continue
            content = str(event.get("content", "")).strip()
            if not content:
                continue
            role = "user" if event.get("actor") == "student" else "assistant"
            messages.append({"role": role, "content": content})
        return messages[-limit:]

    def _build_tutor_messages(
        self,
        *,
        session_id: str,
        user_query: str,
        memory_context: str,
        current_user_event_id: str,
        memory_mode: str = "ordinary",
    ) -> list[dict[str, str]]:
        template = (
            TUTOR_MEMORY_AUGMENTED_USER_PROMPT
            if memory_mode == "memory_augmented"
            else TUTOR_USER_PROMPT
        )
        prompt = template.format(
            user_query=user_query,
            memory_context=memory_context,
        ).strip()
        return [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            *self._chat_history_messages(
                session_id,
                exclude_event_ids={current_user_event_id},
            ),
            {"role": "user", "content": prompt},
        ]

    def _concept_prompt(self, episode: dict[str, Any], events: list[dict[str, Any]]) -> str:
        return (
            CONCEPT_EXTRACTION_PROMPT.replace(
                "{episode_json}",
                json.dumps(episode, ensure_ascii=False, indent=2),
            ).replace(
                "{buffer_text}",
                self._render_segment_for_extraction(events),
            )
        )

    def _teaching_actions_prompt(
        self,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
        concept_names: list[str],
    ) -> str:
        return (
            TEACHING_ACTIONS_EXTRACTION_PROMPT.replace(
                "{episode_json}",
                json.dumps(episode, ensure_ascii=False, indent=2),
            )
            .replace(
                "{concept_names}",
                json.dumps(concept_names, ensure_ascii=False),
            )
            .replace(
                "{buffer_text}",
                self._render_segment_for_extraction(events),
            )
        )

    def _skill_distillation_prompt(
        self,
        episodes: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        raw_events_by_episode: dict[str, list[dict[str, Any]]],
    ) -> str:
        raw_tracks = {
            episode_id: self._render_segment_for_extraction(events)
            for episode_id, events in raw_events_by_episode.items()
        }
        return (
            SKILL_DISTILLATION_PROMPT.replace(
                "{episodes_json}",
                json.dumps(episodes, ensure_ascii=False, indent=2),
            )
            .replace(
                "{evidences_json}",
                json.dumps(evidences, ensure_ascii=False, indent=2),
            )
            .replace(
                "{raw_tracks_json}",
                json.dumps(raw_tracks, ensure_ascii=False, indent=2),
            )
        )

    def _related_skill_segments(self, session_id: str | None = None) -> list[dict[str, Any]]:
        del session_id
        return [
            segment
            for segment in self.buffer.closed_segments
            if segment.get("episode_extraction_completed")
            and segment.get("skill_evidence_recorded")
        ]

    def _window_segments_for_skill(
        self,
        session_id: str,
        current_evidence: dict[str, Any],
    ) -> list[dict[str, Any]]:
        segments = self._related_skill_segments(session_id)
        if not segments:
            return []
        window: list[dict[str, Any]] = []
        current_concepts = list(current_evidence.get("concept_names", []))
        current_pattern = str(current_evidence.get("difficulty_pattern", "unknown"))
        current_actions = list(current_evidence.get("teaching_actions", []))
        for segment in reversed(segments):
            evidence = segment["skill_evidence_recorded"]["metadata"]["evidence"]
            if evidence.get("difficulty_pattern") != current_pattern:
                continue
            if not same_concept_family(current_concepts, list(evidence.get("concept_names", []))):
                continue
            if current_actions and action_overlap(current_actions, list(evidence.get("teaching_actions", []))) <= 0:
                continue
            window.append(segment)
            if len(window) == 4:
                break
        return list(reversed(window))

    def _backfill_skill_distillations_from_evidence(self) -> None:
        for segment in list(self.buffer.closed_segments):
            evidence_event = segment.get("skill_evidence_recorded")
            if not evidence_event or segment.get("skill_distillation_completed"):
                continue
            evidence = evidence_event.get("metadata", {}).get("evidence", {})
            if not isinstance(evidence, dict):
                continue
            if any(
                skill_matches_evidence(skill, evidence)
                for skill in self.graph.nodes_by_type("skill").values()
            ):
                continue
            window_segments = self._window_segments_for_skill(segment.get("session_id", ""), evidence)
            if len(window_segments) < 2:
                continue
            episodes = [
                item["episode_extraction_completed"]["metadata"]["episode"]
                for item in window_segments
            ]
            evidences = [
                item["skill_evidence_recorded"]["metadata"]["evidence"]
                for item in window_segments
            ]
            distilled = self.skill_distiller.distill(
                episodes,
                evidences,
                self._build_raw_tracks_for_window(window_segments),
            )
            if distilled is None:
                continue
            skill = distilled["skill"]
            skill["retrieval"] = self._build_skill_retrieval(skill)
            edges = distilled["edges"]
            if any(
                skill_matches_candidate(existing, skill)
                for existing in self.graph.nodes_by_type("skill").values()
            ):
                continue
            event = self.dataflow.append_event(
                session_id=segment["session_id"],
                turn_index=self.dataflow.next_turn_index(segment["session_id"]),
                actor="memory_agent",
                event_type="skill_distillation_completed",
                content=skill["name"],
                segment_id=segment["segment_id"],
                metadata={"skill": skill, "edges": edges},
                causation_id=evidence_event.get("event_id"),
                correlation_id=evidence_event.get("correlation_id"),
            )
            segment["skill_distillation_completed"] = event.to_dict()
            self.graph.apply_skill_distillation(skill=skill, edges=edges, save=False)

    def _record_skill_evidence(
        self,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        concept_result: dict[str, list[dict[str, Any]]] | None,
        segment_id: str,
        session_id: str,
        correlation_id: str,
        causation_id: str | None,
    ) -> dict[str, Any] | None:
        concept_names = [
            str(item.get("name", "")).strip()
            for item in (concept_result or {}).get("concepts", [])
            if str(item.get("name", "")).strip()
        ]
        concept_ids = [
            str(self.graph._find_existing_concept(name, [])["node_id"])
            for name in concept_names
            if self.graph._find_existing_concept(name, [])
        ]
        try:
            if self.llm.is_live:
                prompt = self._teaching_actions_prompt(episode, events, concept_names)
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                evidence = coerce_skill_evidence_payload_from_llm(
                    raw,
                    episode,
                    events,
                    concept_names=concept_names,
                    concept_ids=concept_ids,
                )
                extractor_version = "skill_evidence_extractor_v1_llm"
            else:
                evidence = self.skill_evidence_extractor.extract(
                    episode,
                    events,
                    concept_names=concept_names,
                    concept_ids=concept_ids,
                )
                extractor_version = "skill_evidence_extractor_v1_fallback"
        except Exception as error:
            failure = self.dataflow.append_event(
                session_id=session_id,
                turn_index=self.dataflow.next_turn_index(session_id),
                actor="memory_agent",
                event_type="skill_distillation_failed",
                content=str(error),
                segment_id=segment_id,
                metadata={"error": str(error), "episode_id": episode["episode_id"]},
                causation_id=causation_id,
                correlation_id=correlation_id,
            )
            return {"failed_event": failure.to_dict()}
        evidence["extractor_version"] = extractor_version
        event = self.dataflow.append_event(
            session_id=session_id,
            turn_index=self.dataflow.next_turn_index(session_id),
            actor="memory_agent",
            event_type="skill_evidence_recorded",
            content=",".join(evidence["teaching_actions"]) or "no teaching actions",
            segment_id=segment_id,
            metadata={"episode_id": episode["episode_id"], "evidence": evidence},
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        return {"event": event.to_dict(), "evidence": evidence}

    def _build_raw_tracks_for_window(self, segments: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        tracks: dict[str, list[dict[str, Any]]] = {}
        for segment in segments:
            episode = segment.get("episode_extraction_completed", {}).get("metadata", {}).get("episode", {})
            episode_id = str(episode.get("episode_id", "")).strip()
            source_event_ids = list(episode.get("provenance", {}).get("source_event_ids", []))
            if not episode_id or not source_event_ids:
                continue
            tracks[episode_id] = self.dataflow.events_by_ids(source_event_ids)
        return tracks

    def _attempt_skill_distillation(
        self,
        segment: dict[str, Any],
        *,
        evidence: dict[str, Any],
        correlation_id: str,
        causation_id: str | None,
    ) -> dict[str, Any] | None:
        window_segments = self._window_segments_for_skill(segment["session_id"], evidence)
        if len(window_segments) < 2:
            return None
        episodes = [
            item["episode_extraction_completed"]["metadata"]["episode"]
            for item in window_segments
        ]
        evidences = [
            item["skill_evidence_recorded"]["metadata"]["evidence"]
            for item in window_segments
        ]
        raw_events_by_episode = self._build_raw_tracks_for_window(window_segments)
        try:
            if self.llm.is_live:
                prompt = self._skill_distillation_prompt(episodes, evidences, raw_events_by_episode)
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                distilled = coerce_skill_distillation_payload_from_llm(
                    raw,
                    episodes,
                    evidences,
                    raw_events_by_episode,
                )
            else:
                distilled = self.skill_distiller.distill(episodes, evidences, raw_events_by_episode)
        except Exception as error:
            failure = self.dataflow.append_event(
                session_id=segment["session_id"],
                turn_index=self.dataflow.next_turn_index(segment["session_id"]),
                actor="memory_agent",
                event_type="skill_distillation_failed",
                content=str(error),
                segment_id=segment["segment_id"],
                metadata={"error": str(error), "episode_ids": [episode["episode_id"] for episode in episodes]},
                causation_id=causation_id,
                correlation_id=correlation_id,
            )
            return {"failed_event": failure.to_dict()}
        if distilled is None:
            failure = self.dataflow.append_event(
                session_id=segment["session_id"],
                turn_index=self.dataflow.next_turn_index(segment["session_id"]),
                actor="memory_agent",
                event_type="skill_distillation_failed",
                content="insufficient reusable trajectory",
                segment_id=segment["segment_id"],
                metadata={"episode_ids": [episode["episode_id"] for episode in episodes]},
                causation_id=causation_id,
                correlation_id=correlation_id,
            )
            return {"failed_event": failure.to_dict()}

        skill = distilled["skill"]
        skill["retrieval"] = self._build_skill_retrieval(skill)
        edges = distilled["edges"]
        existing_match = next(
            (
                node
                for node in self.graph.nodes_by_type("skill").values()
                if skill_matches_candidate(node, skill)
            ),
            None,
        )
        if existing_match is not None:
            return None

        event = self.dataflow.append_event(
            session_id=segment["session_id"],
            turn_index=self.dataflow.next_turn_index(segment["session_id"]),
            actor="memory_agent",
            event_type="skill_distillation_completed",
            content=skill["name"],
            segment_id=segment["segment_id"],
            metadata={"skill": skill, "edges": edges},
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        self.graph.apply_skill_distillation(skill=skill, edges=edges)
        return {"event": event.to_dict(), "skill": skill, "edges": edges}

    def _attempt_skill_validation(
        self,
        segment: dict[str, Any],
        *,
        evidence: dict[str, Any],
        correlation_id: str,
        causation_id: str | None,
    ) -> dict[str, Any] | None:
        matches = [
            skill
            for skill in self.graph.nodes_by_type("skill").values()
            if evidence.get("episode_id") not in set(skill.get("metadata", {}).get("source_episode_ids", []))
            and skill_matches_evidence(skill, evidence)
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda item: (
                action_overlap(item.get("teaching_actions", []), evidence.get("teaching_actions", [])),
                float(item.get("quality", {}).get("confidence", 0.0)),
            ),
            reverse=True,
        )
        skill = matches[0]
        success = positive_outcome(
            str(evidence.get("outcome", {}).get("result", "unresolved")),
            float(evidence.get("outcome", {}).get("score", 0.0)),
        )
        updated_skill = apply_skill_validation_result(skill, success=success)
        updated_skill["retrieval"] = self._build_skill_retrieval(updated_skill)
        edge = make_validation_edge(updated_skill, evidence) if success else None
        event = self.dataflow.append_event(
            session_id=segment["session_id"],
            turn_index=self.dataflow.next_turn_index(segment["session_id"]),
            actor="memory_agent",
            event_type="skill_validation_recorded",
            content=f"{updated_skill['name']} | {'success' if success else 'failed'}",
            segment_id=segment["segment_id"],
            metadata={
                "episode_id": evidence["episode_id"],
                "skill": updated_skill,
                "edge": edge,
                "matched": success,
            },
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        self.graph.apply_skill_validation(skill=updated_skill, edge=edge)
        return {"event": event.to_dict(), "skill": updated_skill, "edge": edge}

    def _finalize_episode(
        self,
        semantic_episode: dict[str, Any],
        segment: dict[str, Any],
        *,
        extractor_version: str,
        extraction_confidence: float,
    ) -> dict[str, Any]:
        episode_id = str(
            semantic_episode.get("episode_id")
            or semantic_episode.get("node_id")
            or make_id("episode")
        )
        summary = semantic_episode.get("summary", {})
        learner_problem = semantic_episode.get("learner_problem", {})
        tutor_action = semantic_episode.get("tutor_action", {})
        learning_outcome = semantic_episode.get("learning_outcome", {})
        events = segment.get("events", [])
        first_event = events[0] if events else {}
        last_event = events[-1] if events else {}
        decision = segment.get("decision", {})

        episode = {
            "episode_id": episode_id,
            "node_id": episode_id,
            "node_type": "episode",
            "episode_type": semantic_episode.get("episode_type", "other"),
            "provenance": {
                "segment_id": segment["segment_id"],
                "session_id": segment["session_id"],
                "source_event_ids": [event.get("event_id") for event in events if event.get("event_id")],
                "start_time": first_event.get("timestamp", ""),
                "end_time": last_event.get("timestamp", ""),
            },
            "summary": {
                "title": str(summary.get("title") or "教学片段"),
                "topic_summary": str(summary.get("topic_summary") or ""),
                "short_summary": str(summary.get("short_summary") or ""),
            },
            "learner_problem": {
                "student_question": str(learner_problem.get("student_question") or ""),
                "detected_problem": str(learner_problem.get("detected_problem") or ""),
                "misconceptions": [
                    str(item)
                    for item in learner_problem.get("misconceptions", [])
                    if str(item).strip()
                ],
                "understanding_before": str(
                    learner_problem.get("understanding_before") or "unknown"
                ),
                "difficulty_signals": [
                    str(item)
                    for item in learner_problem.get("difficulty_signals", [])
                    if str(item).strip()
                ],
            },
            "tutor_action": {
                "main_strategy": str(tutor_action.get("main_strategy") or "worked_example"),
                "strategy_summary": str(tutor_action.get("strategy_summary") or ""),
                "teaching_steps": [
                    str(item)
                    for item in tutor_action.get("teaching_steps", [])
                    if str(item).strip()
                ],
                "used_examples": bool(tutor_action.get("used_examples", False)),
                "used_assessment": bool(tutor_action.get("used_assessment", False)),
            },
            "learning_outcome": {
                "result": str(learning_outcome.get("result") or "unresolved"),
                "understanding_after": str(
                    learning_outcome.get("understanding_after") or "unknown"
                ),
                "score": float(learning_outcome.get("score", 0.0)),
                "evidence": str(learning_outcome.get("evidence") or ""),
                "needs_follow_up": bool(learning_outcome.get("needs_follow_up", True)),
                "follow_up_suggestion": str(
                    learning_outcome.get("follow_up_suggestion") or ""
                ),
            },
        }
        episode["retrieval"] = self._build_retrieval(episode)
        episode["extraction_metadata"] = {
            "extractor_version": extractor_version,
            "boundary_reason": decision.get("reason", ""),
            "boundary_confidence": decision.get("confidence", 0.0),
            "extraction_confidence": extraction_confidence,
            "created_at": utc_now(),
        }
        return episode

    def _concept_grounding_text(
        self,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
        evidence: str = "",
    ) -> str:
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
            tutor_action.get("strategy_summary", ""),
            *tutor_action.get("teaching_steps", []),
            outcome.get("evidence", ""),
            evidence,
            *(event.get("content", "") for event in events),
        ]
        return "\n".join(str(part) for part in parts if str(part).strip())

    def _normalize_concept_text(self, value: str) -> str:
        return re.sub(r"[\W_]+", "", value.strip().lower())

    def _is_banned_concept_name(self, name: str) -> bool:
        normalized = self._normalize_concept_text(name)
        if not normalized:
            return True
        exact_banned = {
            "workedexample",
            "contrastiveexplanation",
            "stepbystepexplanation",
            "socraticquestioning",
            "minimalnumericexample",
            "formuladecomposition",
            "studentselfexplanation",
            "diagnosticcheck",
            "studentconfidence",
            "learnerconfidence",
            "studentunderstanding",
            "learnerunderstanding",
            "learningmethod",
            "teachingmethod",
            "teachingstrategy",
            "practice",
            "assessment",
            "episode",
            "skill",
            "dataflow",
            "chat",
            "memory",
            "topic",
            "example",
            "explanation",
        }
        if normalized in exact_banned:
            return True
        banned_fragments = [
            "teaching",
            "tutorstrategy",
            "learningstatus",
            "confidence",
            "emotion",
            "dialogue",
            "episode",
            "skill",
            "dataflow",
            "workedexample",
            "diagnostic",
            "socratic",
            "讲解方式",
            "教学方式",
            "教学方法",
            "导师策略",
            "举例方式",
            "学习方式",
            "学习状态",
            "理解程度",
            "学生信心",
            "练习反馈",
            "对话",
            "片段",
            "图谱",
        ]
        return any(fragment in normalized for fragment in banned_fragments)

    def _concept_is_grounded(
        self,
        concept: dict[str, Any],
        *,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
        evidence: str,
    ) -> bool:
        grounding_text = self._concept_grounding_text(episode, events, evidence)
        normalized_text = self._normalize_concept_text(grounding_text)
        names = [
            str(concept.get("name", "")).strip(),
            *[
                str(alias).strip()
                for alias in concept.get("aliases", [])
                if str(alias).strip()
            ],
        ]
        for name in names:
            normalized_name = self._normalize_concept_text(name)
            if len(normalized_name) >= 3 and normalized_name in normalized_text:
                return True
            if any("\u4e00" <= char <= "\u9fff" for char in name):
                compact_name = "".join(name.split())
                if len(compact_name) >= 2 and compact_name in grounding_text:
                    return True
        return False

    def _sanitize_concept_payload(
        self,
        payload: dict[str, list[dict[str, Any]]],
        *,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        concepts = payload.get("concepts", [])
        edges = payload.get("edges", [])
        concept_lookup = {
            str(concept.get("name", "")).strip(): concept
            for concept in concepts
            if str(concept.get("name", "")).strip()
            and not self._is_banned_concept_name(str(concept.get("name", "")).strip())
        }
        concept_by_normalized = {
            self._normalize_concept_text(str(concept.get("name", "")).strip()): concept
            for concept in concepts
            if str(concept.get("name", "")).strip()
            and not self._is_banned_concept_name(str(concept.get("name", "")).strip())
        }
        normalized_edges = []
        for edge in edges:
            target_name = str(
                edge.get("target_name") or edge.get("concept_name") or ""
            ).strip()
            if not target_name:
                continue
            normalized = concept_lookup.get(target_name) or concept_by_normalized.get(
                self._normalize_concept_text(target_name)
            )
            if normalized is None:
                continue
            if self._is_banned_concept_name(str(normalized.get("name", ""))):
                continue
            structural_role = str(edge.get("structural_role", "mentioned")).strip().lower()
            learner_relation = str(edge.get("learner_relation", "neutral")).strip().lower()
            if structural_role not in {"main", "supporting", "mentioned"}:
                structural_role = "mentioned"
            if learner_relation not in {"confused", "clarified", "neutral"}:
                learner_relation = "neutral"
            try:
                weight = float(edge.get("importance_score", edge.get("weight", 0.0)))
            except (TypeError, ValueError):
                weight = 0.0
            try:
                confidence = float(edge.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            evidence = str(edge.get("evidence", "")).strip()
            if not evidence:
                continue
            if not self._concept_is_grounded(
                normalized,
                episode=episode,
                events=events,
                evidence=evidence,
            ):
                continue
            combined_score = weight * max(confidence, 0.01)
            if structural_role == "main":
                if weight < 0.8 or confidence < 0.65 or combined_score < 0.58:
                    continue
            elif structural_role == "supporting":
                if weight < 0.76 or confidence < 0.62 or combined_score < 0.52:
                    continue
            else:
                if weight < 0.86 or confidence < 0.72 or combined_score < 0.65:
                    continue
            normalized_edges.append(
                {
                    "target_name": normalized["name"],
                    "weight": max(0.0, min(1.0, weight)),
                    "evidence": evidence,
                    "metadata": {
                        "structural_role": structural_role,
                        "learner_relation": learner_relation,
                        "confidence": max(0.0, min(1.0, confidence)),
                    },
                }
            )

        normalized_edges.sort(key=lambda item: item["weight"], reverse=True)
        normalized_edges = [edge for edge in normalized_edges if edge["weight"] >= 0.76]
        kept = []
        seen_targets = set()
        main_assigned = False
        for edge in normalized_edges:
            target_name = edge["target_name"]
            if target_name in seen_targets:
                continue
            role = edge["metadata"]["structural_role"]
            if role == "mentioned":
                continue
            if role == "main":
                if main_assigned:
                    edge = {
                        **edge,
                        "metadata": {**edge["metadata"], "structural_role": "supporting"},
                    }
                else:
                    main_assigned = True
            kept.append(edge)
            seen_targets.add(target_name)
            if len(kept) == 3:
                break

        if kept and not any(edge["metadata"]["structural_role"] == "main" for edge in kept):
            kept[0] = {
                **kept[0],
                "metadata": {**kept[0]["metadata"], "structural_role": "main"},
            }

        kept_names = {edge["target_name"] for edge in kept}
        kept_concepts = [
            concept
            for concept in concepts
            if str(concept.get("name", "")).strip() in kept_names
        ]
        return {"concepts": kept_concepts, "edges": kept}

    def _extract_concepts_for_episode(
        self,
        episode: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        segment_id: str,
        session_id: str,
        correlation_id: str,
        causation_id: str | None,
    ) -> dict[str, list[dict[str, Any]]] | None:
        try:
            if self.llm.is_live:
                prompt = self._concept_prompt(episode, events)
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                payload = coerce_concept_payload_from_llm(raw, episode, events)
                extractor_version = "concept_extractor_v1_llm"
            else:
                payload = self.concept_extractor.extract(episode, events)
                extractor_version = "concept_extractor_v1_fallback"
            sanitized = self._sanitize_concept_payload(
                payload,
                episode=episode,
                events=events,
            )
            for concept in sanitized["concepts"]:
                concept["retrieval"] = self._build_concept_retrieval(concept)
            for edge in sanitized["edges"]:
                edge["metadata"]["extractor_version"] = extractor_version
                edge["metadata"]["created_at"] = utc_now()
        except Exception as error:
            failure = self.dataflow.append_event(
                session_id=session_id,
                turn_index=self.dataflow.next_turn_index(session_id),
                actor="memory_agent",
                event_type="concept_extraction_failed",
                content=str(error),
                segment_id=segment_id,
                metadata={"error": str(error), "episode_id": episode["episode_id"]},
                causation_id=causation_id,
                correlation_id=correlation_id,
            )
            return {"failed_event": failure.to_dict()}

        event = self.dataflow.append_event(
            session_id=session_id,
            turn_index=self.dataflow.next_turn_index(session_id),
            actor="memory_agent",
            event_type="concept_extraction_completed",
            content="，".join(concept["name"] for concept in sanitized["concepts"]) or "no concepts",
            segment_id=segment_id,
            metadata={
                "episode_id": episode["episode_id"],
                "concepts": sanitized["concepts"],
                "edges": sanitized["edges"],
            },
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        return {"event": event.to_dict(), **sanitized}

    def _extract_segment(
        self,
        segment: dict[str, Any],
        *,
        correlation_id: str,
        retry: bool = False,
    ) -> dict[str, Any] | None:
        if not retry and "episode_extraction_completed" in segment:
            return segment["episode_extraction_completed"]["metadata"]["episode"]

        events = segment.get("events", [])
        if not events:
            return None

        try:
            extractor_version = "episode_extractor_v1_fallback"
            extraction_confidence = 0.64
            if self.llm.is_live:
                prompt = EPISODE_EXTRACTION_PROMPT.replace(
                    "{buffer_text}",
                    self._render_segment_for_extraction(events),
                )
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                semantic_episode = coerce_episode_from_llm(raw, events)
                extractor_version = "episode_extractor_v1_llm"
                extraction_confidence = 0.82
            else:
                semantic_episode = self.extractor.extract(events)
            episode = self._finalize_episode(
                semantic_episode,
                segment,
                extractor_version=extractor_version,
                extraction_confidence=extraction_confidence,
            )
        except Exception as error:
            failure = self.dataflow.append_event(
                session_id=segment["session_id"],
                turn_index=self.dataflow.next_turn_index(segment["session_id"]),
                actor="memory_agent",
                event_type="episode_extraction_failed",
                content=str(error),
                segment_id=segment["segment_id"],
                metadata={"error": str(error)},
                causation_id=segment.get("closed_event", {}).get("event_id"),
                correlation_id=correlation_id,
            )
            segment["episode_extraction_failed"] = failure.to_dict()
            return None

        extraction_event = self.dataflow.append_event(
            session_id=segment["session_id"],
            turn_index=self.dataflow.next_turn_index(segment["session_id"]),
            actor="memory_agent",
            event_type="episode_extraction_completed",
            content=episode["summary"]["short_summary"],
            segment_id=segment["segment_id"],
            metadata={
                "segment_id": segment["segment_id"],
                "episode_id": episode["episode_id"],
                "episode": episode,
            },
            causation_id=segment.get("closed_event", {}).get("event_id"),
            correlation_id=correlation_id,
        )
        segment["episode_extraction_completed"] = extraction_event.to_dict()
        self.graph.apply_episode(episode)
        concept_result = self._extract_concepts_for_episode(
            episode,
            events,
            segment_id=segment["segment_id"],
            session_id=segment["session_id"],
            correlation_id=correlation_id,
            causation_id=extraction_event.event_id,
        )
        if concept_result:
            if "event" in concept_result:
                segment["concept_extraction_completed"] = concept_result["event"]
                self.graph.apply_concept_extraction(
                    episode["episode_id"],
                    concepts=concept_result["concepts"],
                    edges=concept_result["edges"],
                )
            elif "failed_event" in concept_result:
                segment["concept_extraction_failed"] = concept_result["failed_event"]
        skill_evidence_result = self._record_skill_evidence(
            episode,
            events,
            concept_result=concept_result if concept_result and "concepts" in concept_result else None,
            segment_id=segment["segment_id"],
            session_id=segment["session_id"],
            correlation_id=correlation_id,
            causation_id=extraction_event.event_id,
        )
        if skill_evidence_result:
            if "event" in skill_evidence_result:
                segment["skill_evidence_recorded"] = skill_evidence_result["event"]
                distillation_result = self._attempt_skill_distillation(
                    segment,
                    evidence=skill_evidence_result["evidence"],
                    correlation_id=correlation_id,
                    causation_id=skill_evidence_result["event"]["event_id"],
                )
                if distillation_result:
                    if "event" in distillation_result:
                        segment["skill_distillation_completed"] = distillation_result["event"]
                    elif "failed_event" in distillation_result:
                        segment["skill_distillation_failed"] = distillation_result["failed_event"]
                validation_result = self._attempt_skill_validation(
                    segment,
                    evidence=skill_evidence_result["evidence"],
                    correlation_id=correlation_id,
                    causation_id=skill_evidence_result["event"]["event_id"],
                )
                if validation_result and "event" in validation_result:
                    segment["skill_validation_recorded"] = validation_result["event"]
            elif "failed_event" in skill_evidence_result:
                segment["skill_distillation_failed"] = skill_evidence_result["failed_event"]
        return episode

    def _start_tutor_turn(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> dict[str, Any]:
        self.refresh_from_storage()
        correlation_id = make_id("corr")
        turn_index = self.dataflow.next_turn_index(session_id)
        user_event = self.dataflow.append_event(
            session_id=session_id,
            turn_index=turn_index,
            actor="student",
            event_type="user_message",
            content=message,
            correlation_id=correlation_id,
        )
        user_event_dict = user_event.to_dict()
        self.buffer.add(user_event_dict)

        context = self.retriever.retrieve(message)
        memory_context = self.retriever.render_context(context)
        messages = self._build_tutor_messages(
            session_id=session_id,
            user_query=message,
            memory_context=memory_context,
            current_user_event_id=user_event.event_id,
            memory_mode=memory_mode,
        )
        return {
            "session_id": session_id,
            "message": message,
            "correlation_id": correlation_id,
            "turn_index": turn_index,
            "user_event": user_event,
            "user_event_dict": user_event_dict,
            "context": context,
            "messages": messages,
            "memory_mode": memory_mode,
        }

    def _complete_tutor_turn(
        self,
        *,
        turn: dict[str, Any],
        answer: str,
        usage: dict[str, Any] | None = None,
        reasoning: str = "",
    ) -> dict[str, Any]:
        session_id = turn["session_id"]
        correlation_id = turn["correlation_id"]
        turn_index = turn["turn_index"]
        user_event = turn["user_event"]
        user_event_dict = turn["user_event_dict"]
        context = turn["context"]
        assistant_metadata: dict[str, Any] = {}
        if usage:
            assistant_metadata["usage"] = usage
        if reasoning.strip():
            assistant_metadata["reasoning"] = reasoning.strip()
        if context:
            assistant_metadata["retrieval_context"] = context
        assistant_event = self.dataflow.append_event(
            session_id=session_id,
            turn_index=turn_index,
            actor="assistant",
            event_type="assistant_message",
            content=answer,
            metadata=assistant_metadata,
            causation_id=user_event.event_id,
            correlation_id=correlation_id,
        )
        assistant_event_dict = assistant_event.to_dict()
        self.buffer.add(assistant_event_dict)

        session_events = self.buffer.events_by_session.get(session_id, [])
        history = session_events[: max(0, len(session_events) - 2)]
        decision = self.boundary_detector.evaluate(
            history=history,
            new_messages=[user_event_dict, assistant_event_dict],
        )
        boundary_event = self.dataflow.append_event(
            session_id=session_id,
            turn_index=turn_index,
            actor="boundary_agent",
            event_type="boundary_evaluated",
            content=decision.get("topic_summary", ""),
            metadata={"decision": decision},
            causation_id=assistant_event.event_id,
            correlation_id=correlation_id,
        )

        boundary = {"decision": decision, "events": []}
        episode = None
        should_close = (
            bool(decision.get("force_end") or decision.get("should_end"))
            and not bool(decision.get("should_wait"))
        )
        if should_close:
            closed_event_policy = str(decision.get("closed_event_policy") or "include_new_messages")
            open_events = self.buffer.events_by_session.get(session_id, [])
            segment_count = len(open_events)
            if closed_event_policy == "exclude_new_messages":
                segment_count = max(0, len(open_events) - len([user_event_dict, assistant_event_dict]))
            candidate_events = open_events[:segment_count]
            if self._segment_has_learning_content(candidate_events):
                segment_id = make_id("segment")
                if closed_event_policy == "exclude_new_messages":
                    segment_events = self.buffer.consume_prefix(session_id, segment_count)
                else:
                    segment_events = self.buffer.consume(session_id)
                closed_event = self.dataflow.append_event(
                    session_id=session_id,
                    turn_index=turn_index,
                    actor="system",
                    event_type="segment_closed",
                    content=decision.get("topic_summary", "") or "segment closed",
                    segment_id=segment_id,
                    metadata={
                        "decision": decision,
                        "event_refs": [event["event_id"] for event in segment_events],
                    },
                    causation_id=boundary_event.event_id,
                    correlation_id=correlation_id,
                )
                boundary = {
                    "segment_id": segment_id,
                    "session_id": session_id,
                    "decision": decision,
                    "events": segment_events,
                    "closed_event": closed_event.to_dict(),
                }
                self.buffer.closed_segments.append(boundary)
                episode = self._extract_segment(
                    boundary,
                    correlation_id=correlation_id,
                )
            else:
                boundary = {
                    "decision": {
                        **decision,
                        "should_end": False,
                        "should_wait": True,
                        "force_end": False,
                        "reason": "continue_current_episode",
                        "boundary_position": "none",
                        "closed_event_policy": "none",
                    },
                    "events": [],
                }

        return {
            "answer": answer,
            "context": context,
            "user_event": user_event_dict,
            "assistant_event": assistant_event_dict,
            "episode": episode,
            "boundary": boundary,
            "usage": usage or {},
            "reasoning": reasoning.strip(),
        }

    def handle_user_message(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> dict[str, Any]:
        turn = self._start_tutor_turn(session_id, message, memory_mode=memory_mode)
        answer = self.llm.chat(turn["messages"], temperature=0.3)
        return self._complete_tutor_turn(turn=turn, answer=answer)

    def stream_user_message(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> Any:
        turn = self._start_tutor_turn(session_id, message, memory_mode=memory_mode)
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: dict[str, Any] = {}
        yield {
            "type": "context",
            "context": turn["context"],
            "user_event": turn["user_event_dict"],
        }
        for chunk in self.llm.stream_chat(turn["messages"], temperature=0.3):
            if chunk.get("type") == "usage":
                usage = dict(chunk.get("usage", {}))
                yield {"type": "usage", "usage": usage}
                continue
            if chunk.get("type") == "reasoning":
                delta = str(chunk.get("delta", ""))
                if delta:
                    reasoning_parts.append(delta)
                    yield {"type": "reasoning", "delta": delta}
                continue
            delta = str(chunk.get("delta", ""))
            if not delta:
                continue
            answer_parts.append(delta)
            yield {"type": "delta", "delta": delta}
        result = self._complete_tutor_turn(
            turn=turn,
            answer="".join(answer_parts),
            usage=usage or None,
            reasoning="".join(reasoning_parts),
        )
        yield {**result, "type": "final"}

    def force_extract(self, session_id: str) -> dict[str, Any] | None:
        self.refresh_from_storage()
        segment = self.buffer.pending_segment(session_id)
        if segment is None:
            return None
        return self._extract_segment(
            segment,
            correlation_id=make_id("corr"),
            retry=True,
        )

    def delete_event(self, event_id: str) -> dict[str, Any]:
        removed = self.dataflow.delete_event(event_id)
        self.refresh_from_storage()
        return {"deleted_events": removed}

    def reset_memory(self) -> dict[str, Any]:
        self.dataflow.clear()
        self.buffer.events_by_session = {}
        self.buffer.closed_segments = []
        self.graph.reset()
        self.graph.save()
        return {"deleted_events": "all"}

    def rebuild_retrieval_embeddings(self) -> dict[str, Any]:
        rebuilt_nodes = 0
        for node in self.graph.nodes_by_type("episode").values():
            node["retrieval"] = self._build_retrieval(node)
            rebuilt_nodes += 1
        for node in self.graph.nodes_by_type("concept").values():
            node["retrieval"] = self._build_concept_retrieval(node)
            rebuilt_nodes += 1
        for node in self.graph.nodes_by_type("skill").values():
            node["retrieval"] = self._build_skill_retrieval(node)
            rebuilt_nodes += 1
        self.graph.save()
        return {
            "rebuilt_nodes": rebuilt_nodes,
            "retrieval_health": self.graph.retrieval_health(self._embedding_signature()),
        }

    def dashboard(self) -> dict[str, Any]:
        self.refresh_from_storage()
        return {
            "events": self.dataflow.list_events(),
            "concepts": list(self.graph.nodes_by_type("concept").values()),
            "episodes": list(self.graph.nodes_by_type("episode").values()),
            "skills": list(self.graph.nodes_by_type("skill").values()),
            "edges": self.graph.edges,
            "boundary_segments": self.buffer.closed_segments,
            "retrieval_health": self.graph.retrieval_health(self._embedding_signature()),
        }
