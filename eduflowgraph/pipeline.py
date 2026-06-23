"""Thin orchestrator connecting all EduFlowGraph modules.

Responsibilities:
- Turn reception and conversation logging
- Memory retrieval and profile fusion
- LLM-based tutoring response (sync + streaming)
- Boundary detection → segment closing → extraction pipeline
- Dashboard aggregation
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import nullcontext
from typing import Any, Callable

from .config import Settings
from .llm import LLMClient, messages_for_prompt
from .memory.buffer import BufferManager, EpisodeBoundaryDetector
from .memory.concept_extractor import (
    HeuristicConceptExtractor,
    build_grounding_text,
    coerce_concept_payload_from_llm,
    sanitize_concept_payload,
)
from .memory.episode_extractor import (
    HeuristicEpisodeExtractor,
    coerce_episode_from_llm,
    finalize_episode,
)
from .memory.retriever import MemoryRetriever
from .memory.skill_pipeline import (
    HeuristicSkillDistiller,
    HeuristicSkillEvidenceExtractor,
    action_overlap,
    apply_skill_validation_result,
    coerce_skill_distillation_payload_from_llm,
    coerce_skill_evidence_payload_from_llm,
    make_validation_edge,
    positive_outcome,
    same_concept_family,
    skill_evidence_concept_scope,
    skill_matches_candidate,
    skill_matches_evidence,
)
from .profile.consolidator import ProfileConsolidator
from .profile.retriever import render_profile_context
from .prompts import (
    CONCEPT_EXTRACTION_PROMPT,
    EPISODE_EXTRACTION_PROMPT,
    SKILL_DISTILLATION_PROMPT,
    SKILL_EVIDENCE_EXTRACTION_PROMPT,
    TUTOR_MEMORY_AUGMENTED_USER_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    TUTOR_USER_PROMPT,
)
from .schemas import make_id, utc_now
from .store.conversation_log import ConversationLog
from .store.graph_store import GraphStore
from .store.memory_flow import MemoryFlow
from .store.profile_store import LearnerProfileStore
from .store.sqlite_conversation_log import SQLiteConversationLog
from .store.sqlite_graph_store import SQLiteGraphStore
from .store.sqlite_memory_flow import SQLiteMemoryFlow
from .store.sqlite_profile_store import SQLiteLearnerProfileStore
from .store.sqlite_storage import SQLiteStorage, StorageError


class TutorPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

        self.storage: SQLiteStorage | None = None
        if settings.storage_backend == "sqlite":
            self.storage = SQLiteStorage(settings.resolved_database_path)
            self.conv_log = SQLiteConversationLog(self.storage)
            self.memory_flow = SQLiteMemoryFlow(self.storage)
            self.graph = SQLiteGraphStore(self.storage)
            self.profile_store = SQLiteLearnerProfileStore(self.storage)
        else:
            self.conv_log = ConversationLog(settings.conversations_dir)
            self.memory_flow = MemoryFlow(settings.memory_flow_path)
            self.graph = GraphStore(settings.nodes_path, settings.edges_path)
            self.profile_store = LearnerProfileStore(settings.data_dir)

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
            rerank_fn=lambda query, candidates, kind: self.llm.rerank(
                query, candidates, kind=kind
            ),
            embedding_signature=self._embedding_signature(),
        )
        self.profile_consolidator = ProfileConsolidator(self.llm)
        self.profile_store.migrate_legacy_if_needed()
        # Serializes stateful turn handling so a follow-up request (sent as soon
        # as the answer settles) cannot race with the previous turn's still-running
        # memory processing on the shared graph/buffer.
        self._turn_lock = threading.Lock()

        self.buffer = BufferManager()
        self.boundary_detector = EpisodeBoundaryDetector(
            self.llm, settings.extraction_turns
        )

        self._closed_segments: list[dict[str, Any]] = []
        self.refresh_from_storage()

    def _storage_transaction(self):
        if self.storage is None:
            return nullcontext()
        return self.storage.transaction()

    # ── Storage replay ─────────────────────────────────────────────

    def refresh_from_storage(self) -> None:
        if self.storage is not None:
            self.graph.reload()
            consumed_ranges: dict[str, list[tuple[int, int]]] = {}
            for episode in self.graph.nodes_by_type("episode").values():
                provenance = episode.get("provenance", {})
                session_id = str(provenance.get("session_id", ""))
                turn_range = provenance.get("turn_range", [0, 0])
                if session_id and isinstance(turn_range, list) and len(turn_range) >= 2:
                    consumed_ranges.setdefault(session_id, []).append(
                        (int(turn_range[0]), int(turn_range[1]))
                    )
            self._rebuild_buffer(consumed_ranges)
            return

        self.graph.reset()
        consumed_ranges: dict[str, list[tuple[int, int]]] = {}
        for event in self.memory_flow.iter_events():
            etype = event.get("event_type", "")
            payload = event.get("payload", {})
            if etype == "episode_created":
                episode = payload.get("episode")
                if isinstance(episode, dict):
                    self.graph.apply_episode(episode, save=False)
                    prov = episode.get("provenance", {})
                    sid = prov.get("session_id", "")
                    tr = prov.get("turn_range", [0, 0])
                    if sid and isinstance(tr, list) and len(tr) >= 2:
                        consumed_ranges.setdefault(sid, []).append(
                            (int(tr[0]), int(tr[1]))
                        )
            elif etype == "concept_extracted":
                episode_id = str(payload.get("episode_id", ""))
                if episode_id:
                    self.graph.apply_concept_extraction(
                        episode_id,
                        concepts=list(payload.get("concepts", [])),
                        edges=list(payload.get("edges", [])),
                        save=False,
                    )
            elif etype == "skill_distilled":
                skill = payload.get("skill")
                if isinstance(skill, dict):
                    self.graph.apply_skill_distillation(
                        skill=skill,
                        edges=list(payload.get("edges", [])),
                        save=False,
                    )
            elif etype == "skill_validated":
                skill = payload.get("skill")
                if isinstance(skill, dict):
                    self.graph.apply_skill_validation(
                        skill=skill,
                        edge=payload.get("edge")
                        if isinstance(payload.get("edge"), dict)
                        else None,
                        save=False,
                    )
        self.graph.save()
        self._rebuild_buffer(consumed_ranges)

    def _rebuild_buffer(
        self, consumed_ranges: dict[str, list[tuple[int, int]]]
    ) -> None:
        """Rebuild in-memory buffer from conversation logs, excluding turns
        already consumed into episodes (identified by turn_range in provenance).
        """
        self.buffer = BufferManager()
        for session_id in self.conv_log.list_sessions():
            turns = self.conv_log.list_turns(session_id)
            ranges = consumed_ranges.get(session_id, [])
            for turn in turns:
                idx = int(turn.get("turn_index", 0))
                if any(lo <= idx <= hi for lo, hi in ranges):
                    continue
                self.buffer.add_turn(session_id, turn)

    # ── Embedding helpers ──────────────────────────────────────────

    def _embedding_signature(self) -> dict[str, Any]:
        return {
            "provider": self.settings.embedding.provider,
            "model_id": self.settings.embedding.model_id,
            "dimensions": self.settings.embedding.dimensions or 0,
        }

    def _make_retrieval_asset(
        self, embedding_text: str, keywords: list[str]
    ) -> dict[str, Any]:
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

    def _build_retrieval(self, episode: dict[str, Any]) -> dict[str, Any]:
        learner = episode.get("learner", {})
        tutor = episode.get("tutor", {})
        outcome = episode.get("outcome", {})
        keywords = []
        for value in [
            episode.get("title", ""),
            learner.get("obstacle", ""),
            *learner.get("evidence", []),
            tutor.get("strategy", ""),
            episode.get("episode_type", ""),
            outcome.get("status", ""),
        ]:
            text = str(value).strip()
            if text and text not in keywords:
                keywords.append(text)
        embedding_text = (
            f"Episode类型：{episode.get('episode_type', 'other')}。"
            f"标题：{episode.get('title', '')}。"
            f"障碍：{learner.get('obstacle', '')}。"
            f"导师策略：{tutor.get('strategy', '')}。"
            f"结果：{outcome.get('evidence', '')}"
        )
        return self._make_retrieval_asset(embedding_text, keywords)

    def _build_concept_retrieval(self, concept: dict[str, Any]) -> dict[str, Any]:
        name = str(concept.get("name", "")).strip()
        aliases = [
            str(a).strip() for a in concept.get("aliases", []) if str(a).strip()
        ]
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
        procedure = [
            str(item) for item in skill.get("procedure", []) if str(item).strip()
        ]
        success_criteria = [
            str(item) for item in skill.get("success_criteria", []) if str(item).strip()
        ]
        embedding_text = str(skill.get("embedding_text") or "").strip() or "\n".join(
            [
                f"Skill: {skill.get('name', '')}",
                f"Trigger: {skill.get('trigger', '')}",
                f"Difficulty pattern: {skill.get('difficulty_pattern', '')}",
                "Procedure: " + " ".join(procedure[:3]) if procedure else "",
                "Success criteria: " + " ".join(success_criteria[:2])
                if success_criteria
                else "",
            ]
        ).strip()
        keywords = [
            str(skill.get("name", "")).strip(),
            str(skill.get("difficulty_pattern", "")).strip(),
            *[
                str(item)
                for item in skill.get("teaching_actions", [])
                if str(item).strip()
            ],
            *evidence_scope,
        ]
        return self._make_retrieval_asset(
            embedding_text, [item for item in keywords if item]
        )

    # ── Prompt builders ────────────────────────────────────────────

    def _render_turns_for_extraction(self, turns: list[dict[str, Any]]) -> str:
        lines = []
        for turn in turns:
            ts = turn.get("timestamp", "")
            user = str(turn.get("user_message", "")).strip()
            assistant = str(turn.get("assistant_message", "")).strip()
            if user:
                lines.append(f"[{ts}] student: {user}")
            if assistant:
                lines.append(f"[{ts}] assistant: {assistant}")
        return "\n".join(lines)

    def _build_tutor_messages(
        self,
        *,
        session_id: str,
        user_query: str,
        memory_context: str,
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
        history = self.conv_log.session_messages(session_id, limit=16)
        return [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": prompt},
        ]

    def _concept_prompt(
        self, episode: dict[str, Any], turns: list[dict[str, Any]]
    ) -> str:
        return CONCEPT_EXTRACTION_PROMPT.replace(
            "{episode_json}",
            json.dumps(episode, ensure_ascii=False, indent=2),
        ).replace(
            "{buffer_text}",
            self._render_turns_for_extraction(turns),
        )

    def _skill_evidence_prompt(
        self,
        episode: dict[str, Any],
        turns: list[dict[str, Any]],
        concept_names: list[str],
    ) -> str:
        return (
            SKILL_EVIDENCE_EXTRACTION_PROMPT.replace(
                "{episode_json}",
                json.dumps(episode, ensure_ascii=False, indent=2),
            )
            .replace(
                "{concept_names}",
                json.dumps(concept_names, ensure_ascii=False),
            )
            .replace(
                "{buffer_text}",
                self._render_turns_for_extraction(turns),
            )
        )

    def _skill_distillation_prompt(
        self,
        episodes: list[dict[str, Any]],
        evidences: list[dict[str, Any]],
        raw_turns_by_episode: dict[str, list[dict[str, Any]]],
    ) -> str:
        raw_tracks = {
            eid: self._render_turns_for_extraction(turns)
            for eid, turns in raw_turns_by_episode.items()
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

    # ── Segment content check ──────────────────────────────────────

    def _segment_has_learning_content(self, turns: list[dict[str, Any]]) -> bool:
        user_messages = [
            str(t.get("user_message", "")).strip()
            for t in turns
            if str(t.get("user_message", "")).strip()
        ]
        substantive = []
        for msg in user_messages:
            normalized = msg.lower().strip()
            compact = "".join(normalized.split())
            if not compact:
                continue
            if len(compact) <= 24 and any(
                marker in normalized
                for marker in [
                    "谢谢", "感谢", "好的", "ok", "thanks", "thank you",
                    "明白", "懂了", "理解了",
                ]
            ):
                continue
            substantive.append(msg)
        if not substantive:
            return False
        learning_markers = [
            "解释", "什么是", "为什么", "怎么", "如何", "例子", "题目",
            "做题", "出题", "练习", "检查", "不懂", "不会", "混淆",
            "对比", "区分", "explain", "why", "how",
        ]
        return any(
            any(marker in m.lower() for marker in learning_markers)
            for m in substantive
        ) or len(substantive) >= 2

    # ── Extraction pipeline ────────────────────────────────────────

    def _extract_concepts_for_episode(
        self,
        episode: dict[str, Any],
        turns: list[dict[str, Any]],
        *,
        session_id: str,
    ) -> dict[str, list[dict[str, Any]]] | None:
        try:
            if self.llm.is_live:
                prompt = self._concept_prompt(episode, turns)
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                payload = coerce_concept_payload_from_llm(raw, episode, turns)
                extractor_version = "concept_extractor_v2_llm"
            else:
                payload = self.concept_extractor.extract(episode, turns)
                extractor_version = "concept_extractor_v2_fallback"
            sanitized = sanitize_concept_payload(
                payload, episode=episode, turns=turns
            )
            for concept in sanitized["concepts"]:
                concept["retrieval"] = self._build_concept_retrieval(concept)
            for edge in sanitized["edges"]:
                edge.setdefault("metadata", {})["extractor_version"] = extractor_version
                edge["metadata"]["created_at"] = utc_now()
        except Exception as error:
            self.memory_flow.emit(
                "concept_extraction_failed",
                session_id,
                {"error": str(error), "episode_id": episode["episode_id"]},
            )
            return None

        with self._storage_transaction():
            self.graph.apply_concept_extraction(
                episode["episode_id"],
                concepts=sanitized["concepts"],
                edges=sanitized["edges"],
            )
            self.memory_flow.emit(
                "concept_extracted",
                session_id,
                {
                    "episode_id": episode["episode_id"],
                    "concepts": sanitized["concepts"],
                    "edges": sanitized["edges"],
                },
            )
        return sanitized

    def _record_skill_evidence(
        self,
        episode: dict[str, Any],
        turns: list[dict[str, Any]],
        *,
        concept_result: dict[str, list[dict[str, Any]]] | None,
        session_id: str,
    ) -> dict[str, Any] | None:
        concept_names = [
            str(item.get("name", "")).strip()
            for item in (concept_result or {}).get("concepts", [])
            if str(item.get("name", "")).strip()
        ]
        concept_ids = [
            str(c["node_id"])
            for name in concept_names
            for c in [self.graph.find_existing_concept(name, [])]
            if c is not None
        ]
        try:
            if self.llm.is_live:
                prompt = self._skill_evidence_prompt(episode, turns, concept_names)
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                evidence = coerce_skill_evidence_payload_from_llm(
                    raw, episode, turns,
                    concept_names=concept_names,
                    concept_ids=concept_ids,
                )
            else:
                evidence = self.skill_evidence_extractor.extract(
                    episode, turns,
                    concept_names=concept_names,
                    concept_ids=concept_ids,
                )
        except Exception as error:
            self.memory_flow.emit(
                "skill_evidence_added",
                session_id,
                {"error": str(error), "episode_id": episode["episode_id"]},
            )
            return None

        self.memory_flow.emit(
            "skill_evidence_added",
            session_id,
            {"episode_id": episode["episode_id"], "evidence": evidence},
        )
        return evidence

    def _attempt_skill_distillation(
        self,
        evidence: dict[str, Any],
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        all_evidences = [
            ev.get("payload", {}).get("evidence", {})
            for ev in self.memory_flow.list_events("skill_evidence_added")
            if isinstance(ev.get("payload", {}).get("evidence"), dict)
        ]
        window = self._build_evidence_window(evidence, all_evidences)
        if len(window) < 2:
            return None

        episode_ids = list(
            dict.fromkeys(
                str(e.get("episode_id", ""))
                for e in window
                if str(e.get("episode_id", "")).strip()
            )
        )
        episodes = [
            self.graph.nodes.get(eid)
            for eid in episode_ids
            if self.graph.nodes.get(eid)
        ]
        if len(episodes) < 2:
            return None

        raw_turns_by_episode: dict[str, list[dict[str, Any]]] = {}
        for ep in episodes:
            sid = ep.get("provenance", {}).get("session_id", "")
            if sid:
                raw_turns_by_episode[ep["episode_id"]] = self.conv_log.list_turns(sid)

        try:
            if self.llm.is_live:
                prompt = self._skill_distillation_prompt(
                    episodes, window, raw_turns_by_episode
                )
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                distilled = coerce_skill_distillation_payload_from_llm(
                    raw, episodes, window, raw_turns_by_episode
                )
            else:
                distilled = self.skill_distiller.distill(
                    episodes, window, raw_turns_by_episode
                )
        except Exception:
            return None

        if distilled is None:
            return None

        skill = distilled["skill"]
        edges = distilled["edges"]
        if any(
            skill_matches_candidate(existing, skill)
            for existing in self.graph.nodes_by_type("skill").values()
        ):
            return None

        skill["retrieval"] = self._build_skill_retrieval(skill)
        with self._storage_transaction():
            self.graph.apply_skill_distillation(skill=skill, edges=edges)
            self.memory_flow.emit(
                "skill_distilled",
                session_id,
                {"skill": skill, "edges": edges},
            )
        return {"skill": skill, "edges": edges}

    def _attempt_skill_validation(
        self,
        evidence: dict[str, Any],
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        matches = [
            skill
            for skill in self.graph.nodes_by_type("skill").values()
            if evidence.get("episode_id")
            not in set(skill.get("metadata", {}).get("source_episode_ids", []))
            and skill_matches_evidence(skill, evidence)
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda item: (
                action_overlap(
                    item.get("teaching_actions", []),
                    evidence.get("teaching_actions", []),
                ),
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
        with self._storage_transaction():
            self.graph.apply_skill_validation(skill=updated_skill, edge=edge)
            self.memory_flow.emit(
                "skill_validated",
                session_id,
                {"skill": updated_skill, "edge": edge, "success": success},
            )
        return {"skill": updated_skill, "edge": edge}

    def _build_evidence_window(
        self,
        current: dict[str, Any],
        all_evidences: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        pattern = str(current.get("difficulty_pattern", "unknown"))
        actions = list(current.get("teaching_actions", []))
        concepts = list(current.get("concept_names", []))
        window: list[dict[str, Any]] = []
        for ev in reversed(all_evidences):
            if ev.get("difficulty_pattern") != pattern:
                continue
            if not same_concept_family(concepts, list(ev.get("concept_names", []))):
                continue
            if actions and action_overlap(actions, list(ev.get("teaching_actions", []))) <= 0:
                continue
            window.append(ev)
            if len(window) == 4:
                break
        return list(reversed(window))

    def _extract_segment(
        self,
        segment_turns: list[dict[str, Any]],
        *,
        session_id: str,
        segment_id: str,
        on_memory_update: Callable[[str], None] | None = None,
    ) -> dict[str, Any] | None:
        if not segment_turns:
            return None
        try:
            if self.llm.is_live:
                prompt = EPISODE_EXTRACTION_PROMPT.replace(
                    "{buffer_text}",
                    self._render_turns_for_extraction(segment_turns),
                )
                raw = self.llm.chat(messages_for_prompt(prompt), temperature=0)
                semantic_episode = coerce_episode_from_llm(raw, segment_turns)
                extractor_version = "episode_extractor_v2_llm"
                extraction_confidence = 0.82
            else:
                semantic_episode = self.extractor.extract(segment_turns)
                extractor_version = "episode_extractor_v2_fallback"
                extraction_confidence = 0.64
            episode = finalize_episode(
                semantic_episode,
                segment_turns=segment_turns,
                session_id=session_id,
                segment_id=segment_id,
                extractor_version=extractor_version,
                extraction_confidence=extraction_confidence,
                retrieval=self._build_retrieval(semantic_episode),
            )
        except Exception as error:
            self.memory_flow.emit(
                "episode_extraction_failed",
                session_id,
                {"error": str(error), "segment_id": segment_id},
            )
            return None

        with self._storage_transaction():
            self.graph.apply_episode(episode)
            self.memory_flow.emit(
                "episode_created",
                session_id,
                {"episode": episode, "segment_id": segment_id},
            )
        if on_memory_update:
            on_memory_update("episode_created")

        concept_result = self._extract_concepts_for_episode(
            episode, segment_turns, session_id=session_id
        )
        if concept_result and on_memory_update:
            on_memory_update("concept_extracted")
        skill_evidence = self._record_skill_evidence(
            episode,
            segment_turns,
            concept_result=concept_result,
            session_id=session_id,
        )
        if skill_evidence:
            self._attempt_skill_distillation(
                skill_evidence, session_id=session_id
            )
            self._attempt_skill_validation(
                skill_evidence, session_id=session_id
            )
        self._consolidate_episode_profile(
            episode=episode,
            concept_result=concept_result,
            skill_evidence=skill_evidence,
        )
        return episode

    # ── Profile consolidation ──────────────────────────────────────

    def _update_context_profile(
        self,
        *,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Lightly rewrite the time-sensitive context_model paragraph each turn."""
        try:
            current = self.profile_store.summary("context_model")
            updates = self.profile_consolidator.update_context(
                current=current,
                user_message=user_message,
                assistant_message=assistant_message,
            )
            if updates:
                self.profile_store.update_models(updates)
        except Exception:
            return

    def _consolidate_episode_profile(
        self,
        *,
        episode: dict[str, Any],
        concept_result: dict[str, Any] | None,
        skill_evidence: dict[str, Any] | None,
    ) -> None:
        """Rewrite learner_model + strategy_model paragraphs at episode boundaries."""
        try:
            current = self.profile_store.summaries()
            updates = self.profile_consolidator.consolidate_episode(
                current=current,
                episode=episode,
                concept_result=concept_result,
                skill_evidence=skill_evidence,
            )
            if updates:
                with self._storage_transaction():
                    self.profile_store.update_models(updates)
                    self.memory_flow.emit(
                        "profile_updated",
                        episode.get("provenance", {}).get("session_id", ""),
                        {
                            "episode_id": episode.get("episode_id", ""),
                            "updated_models": sorted(updates.keys()),
                        },
                    )
        except Exception:
            return

    # ── Profile-aware retrieval ────────────────────────────────────

    def _apply_profile_retrieval(
        self, query: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Attach the lightweight profile paragraphs to the tutor context.

        The profile is already tiny and consolidated, so it is injected directly —
        no scoring or graph-rank fusion. The memory-graph retrieval stays untouched.
        """
        fused = dict(context)
        profile_snapshot = self.profile_store.load()
        fused["profile"] = profile_snapshot
        fused["profile_context"] = render_profile_context(profile_snapshot)
        fused["memory_context_pack"] = self.retriever.render_context(fused)
        return fused

    # ── Turn handling ──────────────────────────────────────────────

    def _start_tutor_turn(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> dict[str, Any]:
        self.refresh_from_storage()
        turn_index = self.conv_log.next_turn_index(session_id)

        context = self.retriever.retrieve(message)
        context = self._apply_profile_retrieval(message, context)
        memory_context = context.get("memory_context_pack") or self.retriever.render_context(context)
        messages = self._build_tutor_messages(
            session_id=session_id,
            user_query=message,
            memory_context=memory_context,
            memory_mode=memory_mode,
        )
        return {
            "session_id": session_id,
            "message": message,
            "turn_index": turn_index,
            "context": context,
            "messages": messages,
            "memory_mode": memory_mode,
        }

    def _persist_tutor_turn(
        self,
        *,
        turn: dict[str, Any],
        answer: str,
        usage: dict[str, Any] | None = None,
        reasoning: str = "",
    ) -> dict[str, Any]:
        """Durably record the turn (conversation log + buffer).

        Fast, local IO only — runs before the answer is reported to the client so
        the turn is never lost, even though heavier memory processing happens after.
        """
        session_id = turn["session_id"]
        turn_index = turn["turn_index"]

        turn_record = self.conv_log.append_turn(
            session_id=session_id,
            turn_index=turn_index,
            user_message=turn["message"],
            assistant_message=answer,
            metadata={
                k: v
                for k, v in [("usage", usage), ("reasoning", reasoning.strip())]
                if v
            },
        )
        self.buffer.add_turn(session_id, turn_record.to_dict())
        return turn_record.to_dict()

    def _process_tutor_turn(
        self,
        *,
        turn: dict[str, Any],
        answer: str,
        on_memory_update: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Heavier post-answer memory work: context profile + boundary + extraction.

        Runs after the answer has been delivered to the client, so it never blocks
        the perceived response time.
        """
        session_id = turn["session_id"]

        self._update_context_profile(
            user_message=turn["message"],
            assistant_message=answer,
        )

        buffer_turns = self.buffer.get_buffer(session_id)
        history_turns = buffer_turns[: max(0, len(buffer_turns) - 1)]
        new_turn = buffer_turns[-1:] if buffer_turns else []

        history_events = self._turns_to_events(history_turns)
        new_events = self._turns_to_events(new_turn)

        decision = self.boundary_detector.evaluate(
            history=history_events,
            new_messages=new_events,
        )

        boundary: dict[str, Any] = {"decision": decision}
        episode = None
        should_close = (
            bool(decision.get("force_end") or decision.get("should_end"))
            and not bool(decision.get("should_wait"))
        )
        if should_close:
            closed_event_policy = str(
                decision.get("closed_event_policy") or "include_new_messages"
            )
            all_buffer = self.buffer.get_buffer(session_id)
            segment_count = len(all_buffer)
            if closed_event_policy == "exclude_new_messages":
                segment_count = max(0, len(all_buffer) - 1)
            candidate_turns = all_buffer[:segment_count]
            if self._segment_has_learning_content(candidate_turns):
                segment_id = make_id("segment")
                if closed_event_policy == "exclude_new_messages":
                    segment_turns = self.buffer.consume_prefix(
                        session_id, segment_count
                    )
                else:
                    segment_turns = self.buffer.consume(session_id)
                boundary["segment_id"] = segment_id
                episode = self._extract_segment(
                    segment_turns,
                    session_id=session_id,
                    segment_id=segment_id,
                    on_memory_update=on_memory_update,
                )
            else:
                decision["should_end"] = False
                decision["should_wait"] = True

        return {"episode": episode, "boundary": boundary}

    def _complete_tutor_turn(
        self,
        *,
        turn: dict[str, Any],
        answer: str,
        usage: dict[str, Any] | None = None,
        reasoning: str = "",
    ) -> dict[str, Any]:
        turn_record = self._persist_tutor_turn(
            turn=turn, answer=answer, usage=usage, reasoning=reasoning
        )
        memory = self._process_tutor_turn(turn=turn, answer=answer)
        return {
            "answer": answer,
            "context": turn["context"],
            "turn": turn_record,
            "episode": memory["episode"],
            "boundary": memory["boundary"],
            "usage": usage or {},
            "reasoning": reasoning.strip(),
        }

    def _turns_to_events(self, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events = []
        for t in turns:
            ts = t.get("timestamp", "")
            user = str(t.get("user_message", "")).strip()
            assistant = str(t.get("assistant_message", "")).strip()
            if user:
                events.append(
                    {"actor": "student", "event_type": "user_message",
                     "content": user, "timestamp": ts}
                )
            if assistant:
                events.append(
                    {"actor": "assistant", "event_type": "assistant_message",
                     "content": assistant, "timestamp": ts}
                )
        return events

    # ── Public API ─────────────────────────────────────────────────

    def handle_user_message(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> dict[str, Any]:
        with self._turn_lock:
            turn = self._start_tutor_turn(
                session_id, message, memory_mode=memory_mode
            )
            answer = self.llm.chat(turn["messages"], temperature=0.3)
            return self._complete_tutor_turn(turn=turn, answer=answer)

    def stream_user_message(
        self,
        session_id: str,
        message: str,
        *,
        memory_mode: str = "ordinary",
    ) -> Any:
        self._turn_lock.acquire()
        try:
            turn = self._start_tutor_turn(
                session_id, message, memory_mode=memory_mode
            )
            answer_parts: list[str] = []
            reasoning_parts: list[str] = []
            usage: dict[str, Any] = {}
            yield {
                "type": "context",
                "context": turn["context"],
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

            answer = "".join(answer_parts)
            reasoning = "".join(reasoning_parts)

            # Persist + report the settled answer immediately so the client can
            # stop its "thinking"/send spinner and let the user continue, before
            # the heavier memory processing runs.
            turn_record = self._persist_tutor_turn(
                turn=turn,
                answer=answer,
                usage=usage or None,
                reasoning=reasoning,
            )
            yield {
                "type": "answer",
                "answer": answer,
                "context": turn["context"],
                "turn": turn_record,
                "usage": usage or {},
                "reasoning": reasoning.strip(),
            }

            memory_stages: list[str] = []

            def _notify_memory(stage: str) -> None:
                memory_stages.append(stage)

            memory = self._process_tutor_turn(
                turn=turn,
                answer=answer,
                on_memory_update=_notify_memory,
            )
            for stage in memory_stages:
                yield {
                    "type": "memory",
                    "stage": stage,
                }
            yield {
                "type": "final",
                "answer": answer,
                "context": turn["context"],
                "turn": turn_record,
                "episode": memory["episode"],
                "boundary": memory["boundary"],
                "usage": usage or {},
                "reasoning": reasoning.strip(),
            }
        finally:
            self._turn_lock.release()

    def force_extract(self, session_id: str) -> dict[str, Any] | None:
        self.refresh_from_storage()
        buffer_turns = self.buffer.get_buffer(session_id)
        if not buffer_turns or not self._segment_has_learning_content(buffer_turns):
            return None
        segment_id = make_id("segment")
        segment_turns = self.buffer.consume(session_id)
        return self._extract_segment(
            segment_turns, session_id=session_id, segment_id=segment_id
        )

    def reset_memory(self) -> dict[str, Any]:
        with self._storage_transaction():
            self.memory_flow.clear()
            self.conv_log.clear_all()
            self.graph.reset()
            self.graph.save()
            self.profile_store.clear()
        self.buffer = BufferManager()
        self._closed_segments = []
        return {"deleted": "all"}

    def rebuild_retrieval_embeddings(self) -> dict[str, Any]:
        rebuilt = 0
        for node in self.graph.nodes_by_type("episode").values():
            node["retrieval"] = self._build_retrieval(node)
            rebuilt += 1
        for node in self.graph.nodes_by_type("concept").values():
            node["retrieval"] = self._build_concept_retrieval(node)
            rebuilt += 1
        for node in self.graph.nodes_by_type("skill").values():
            node["retrieval"] = self._build_skill_retrieval(node)
            rebuilt += 1
        self.graph.save()
        return {
            "rebuilt_nodes": rebuilt,
            "retrieval_health": self.graph.retrieval_health(
                self._embedding_signature()
            ),
        }

    @staticmethod
    def _strip_heavy_fields(node: dict[str, Any]) -> dict[str, Any]:
        """Remove embedding vectors and other heavy fields not needed by the UI."""
        result = dict(node)
        retrieval = result.get("retrieval")
        if isinstance(retrieval, dict) and "embedding_vector" in retrieval:
            result["retrieval"] = {
                k: v for k, v in retrieval.items() if k != "embedding_vector"
            }
        return result

    def dashboard(self) -> dict[str, Any]:
        # Profile is loaded from disk each call; reload graph so dashboard reads
        # reflect writes from other cached pipeline instances (e.g. live chat vs mock poll).
        try:
            self.graph.reload()
            events = self.memory_flow.list_events()
            event_summaries = [
                {
                    "event_type": ev.get("event_type", ""),
                    "timestamp": ev.get("timestamp", ""),
                }
                for ev in events
            ]
            strip = self._strip_heavy_fields
            snapshot = {
                "concepts": [strip(n) for n in self.graph.nodes_by_type("concept").values()],
                "episodes": [strip(n) for n in self.graph.nodes_by_type("episode").values()],
                "skills": [strip(n) for n in self.graph.nodes_by_type("skill").values()],
                "edges": self.graph.edges,
                "profile": self.profile_store.load(),
                "memory_events": event_summaries,
                "memory_flow_count": len(events),
            }
            if self.storage is not None:
                snapshot["storage_health"] = self.storage.health()
            else:
                snapshot["storage_health"] = {"backend": "json"}
            return snapshot
        except (StorageError, sqlite3.DatabaseError) as error:
            profile = self.profile_store.empty_snapshot()
            profile["health"] = {
                "status": "error",
                "message": f"存储读取失败：{error}",
            }
            return {
                "concepts": [],
                "episodes": [],
                "skills": [],
                "edges": [],
                "profile": profile,
                "memory_events": [],
                "memory_flow_count": 0,
                "storage_health": {
                    "backend": self.settings.storage_backend,
                    "status": "error",
                    "message": str(error),
                },
            }
