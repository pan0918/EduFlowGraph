import json
import hashlib
from pathlib import Path
import re
from typing import Any, Callable

from ..schemas import utc_now
from ..skills import DIFFICULTY_PATTERN_TAXONOMY


class GraphStore:
    def __init__(self, nodes_path: Path, edges_path: Path):
        self.nodes_path = nodes_path
        self.edges_path = edges_path
        self.nodes_path.parent.mkdir(parents=True, exist_ok=True)
        self.edges_path.parent.mkdir(parents=True, exist_ok=True)
        self.nodes = self._load_json(self.nodes_path, {})
        self.edges = self._load_json(self.edges_path, [])
        if not isinstance(self.nodes, dict):
            self.nodes = {}
        if not isinstance(self.edges, list):
            self.edges = []

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
            return default
        text = path.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else default

    def save(self) -> None:
        self.nodes_path.write_text(
            json.dumps(self.nodes, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        self.edges_path.write_text(
            json.dumps(self.edges, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    def reload(self) -> None:
        """Reload nodes/edges from disk so readers see writes from other pipeline instances."""
        self.nodes = self._load_json(self.nodes_path, {})
        self.edges = self._load_json(self.edges_path, [])
        if not isinstance(self.nodes, dict):
            self.nodes = {}
        if not isinstance(self.edges, list):
            self.edges = []

    def reset(self) -> None:
        self.nodes = {}
        self.edges = []

    def nodes_by_type(self, node_type: str) -> dict[str, dict[str, Any]]:
        result = {}
        for node_id, node in self.nodes.items():
            if node.get("node_type") != node_type:
                continue
            if node_type == "episode":
                node = self._migrate_episode_if_needed(node)
            result[node_id] = node
        return result

    def _migrate_episode_if_needed(self, node: dict[str, Any]) -> dict[str, Any]:
        """Transparently upgrade v1 episode schema to v2 if required fields are missing."""
        if "title" in node and "learner" in node:
            return node
        node = dict(node)
        summary_raw = node.get("summary", {})
        if isinstance(summary_raw, dict):
            node["title"] = summary_raw.get("title", "")
            node["summary"] = summary_raw.get("short_summary") or summary_raw.get("topic_summary", "")
            node["memory_value"] = summary_raw.get("topic_summary") or summary_raw.get("short_summary", "")
        else:
            node.setdefault("title", "")
            node.setdefault("memory_value", "")
        lp = node.pop("learner_problem", {}) or {}
        if lp:
            node["learner"] = {
                "goal": lp.get("student_question", ""),
                "obstacle": lp.get("detected_problem", ""),
                "initial_state": lp.get("understanding_before", ""),
                "evidence": lp.get("difficulty_signals", []),
            }
        else:
            node.setdefault("learner", {"goal": "", "obstacle": "", "initial_state": "", "evidence": []})
        ta = node.pop("tutor_action", {}) or {}
        if ta:
            node["tutor"] = {
                "strategy": ta.get("main_strategy") or ta.get("strategy_summary", ""),
                "key_moves": ta.get("teaching_steps", []),
            }
        else:
            node.setdefault("tutor", {"strategy": "", "key_moves": []})
        lo = node.pop("learning_outcome", {}) or {}
        if lo:
            node["outcome"] = {
                "status": lo.get("result") or lo.get("understanding_after", ""),
                "evidence": lo.get("evidence", ""),
                "next_step": lo.get("follow_up_suggestion", ""),
            }
        else:
            node.setdefault("outcome", {"status": "", "evidence": "", "next_step": ""})
        prov = node.get("provenance", {})
        if isinstance(prov, dict) and "turn_range" not in prov:
            prov = dict(prov)
            prov["turn_range"] = [0, 0]
            node["provenance"] = prov
        return node

    # ── Episode ────────────────────────────────────────────────────────

    def apply_episode(self, episode: dict[str, Any], *, save: bool = True) -> None:
        node_id = episode.get("node_id") or episode.get("episode_id")
        if not node_id:
            raise ValueError("episode node requires node_id or episode_id")
        normalized = dict(episode)
        normalized["node_id"] = node_id
        normalized.setdefault("episode_id", node_id)
        normalized["node_type"] = "episode"
        self.nodes[node_id] = normalized
        if save:
            self.save()

    # ── Concept ────────────────────────────────────────────────────────

    def upsert_concept(
        self,
        concept: dict[str, Any],
        *,
        save: bool = True,
    ) -> dict[str, Any]:
        raw_name = str(concept.get("name", "")).strip()
        aliases = [
            str(alias).strip()
            for alias in concept.get("aliases", [])
            if str(alias).strip()
        ]
        description = str(concept.get("description", "")).strip()
        now = utc_now()

        existing = self.find_existing_concept(raw_name, aliases)
        if existing is None:
            node_id = self._concept_id_for_name(raw_name or (aliases[0] if aliases else "concept"))
            normalized = {
                "concept_id": node_id,
                "node_id": node_id,
                "node_type": "concept",
                "name": raw_name or (aliases[0] if aliases else "Untitled concept"),
                "aliases": aliases,
                "description": description,
                "retrieval": dict(concept.get("retrieval", {})),
                "metadata": {"created_at": now, "updated_at": now},
            }
            self.nodes[node_id] = normalized
            if save:
                self.save()
            return normalized

        merged_aliases = []
        for alias in [*existing.get("aliases", []), *aliases, raw_name]:
            candidate = str(alias).strip()
            if candidate and candidate != existing["name"] and candidate not in merged_aliases:
                merged_aliases.append(candidate)
        existing["aliases"] = merged_aliases
        if not existing.get("description") and description:
            existing["description"] = description
        if concept.get("retrieval"):
            existing["retrieval"] = dict(concept.get("retrieval", {}))
        metadata = existing.setdefault("metadata", {})
        metadata.setdefault("created_at", now)
        metadata["updated_at"] = now
        if save:
            self.save()
        return existing

    def find_existing_concept(
        self,
        name: str,
        aliases: list[str],
    ) -> dict[str, Any] | None:
        """Dynamic fuzzy matching for concept deduplication."""
        wanted = {
            normalized
            for normalized in [self._normalize_lookup(name), *(self._normalize_lookup(a) for a in aliases)]
            if normalized
        }
        if not wanted:
            return None
        for concept in self.nodes_by_type("concept").values():
            known = {
                normalized
                for normalized in [
                    self._normalize_lookup(str(concept.get("name", ""))),
                    *(self._normalize_lookup(a) for a in concept.get("aliases", [])),
                ]
                if normalized
            }
            if wanted & known:
                return concept
        return None

    def find_similar_concept_by_embedding(
        self,
        embedding: list[float],
        *,
        threshold: float = 0.92,
    ) -> dict[str, Any] | None:
        """Find an existing concept whose embedding vector is very similar."""
        if not embedding:
            return None
        best_score = 0.0
        best_concept = None
        for concept in self.nodes_by_type("concept").values():
            vector = concept.get("retrieval", {}).get("embedding_vector", [])
            if not vector:
                continue
            sim = self._cosine_similarity(embedding, vector)
            if sim > best_score:
                best_score = sim
                best_concept = concept
        if best_concept is not None and best_score >= threshold:
            return best_concept
        return None

    def apply_concept_extraction(
        self,
        episode_id: str,
        *,
        concepts: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        save: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        concept_lookup: dict[str, dict[str, Any]] = {}
        for concept in concepts:
            node = self.upsert_concept(concept, save=False)
            for value in [node.get("name", ""), *(node.get("aliases", []) or [])]:
                normalized = self._normalize_lookup(str(value))
                if normalized:
                    concept_lookup[normalized] = node

        self.edges = [
            edge for edge in self.edges
            if not (edge.get("edge_type") == "episode_concept" and edge.get("source") == episode_id)
        ]

        persisted_edges: list[dict[str, Any]] = []
        for edge in edges:
            target_name = str(
                edge.get("target_name") or edge.get("concept_name") or edge.get("target") or ""
            ).strip()
            if not target_name:
                continue
            normalized_name = self._normalize_lookup(target_name)
            concept = concept_lookup.get(normalized_name)
            if concept is None:
                concept = self.upsert_concept({"name": target_name}, save=False)
                concept_lookup[normalized_name] = concept
            edge_id = f"edge_{episode_id}_{concept['node_id']}"
            persisted = {
                "edge_id": edge_id,
                "edge_type": "episode_concept",
                "source": episode_id,
                "target": concept["node_id"],
                "weight": float(edge.get("weight", edge.get("salience", 0.0))),
                "evidence": str(edge.get("evidence", "")).strip(),
                "metadata": dict(edge.get("metadata", {})),
            }
            self.edges.append(persisted)
            persisted_edges.append(persisted)

        if save:
            self.save()
        return {"concepts": list(self.nodes_by_type("concept").values()), "edges": persisted_edges}

    # ── Skill ──────────────────────────────────────────────────────────

    def upsert_skill(
        self,
        skill: dict[str, Any],
        *,
        save: bool = True,
    ) -> dict[str, Any]:
        node_id = str(skill.get("node_id") or skill.get("skill_id") or "").strip()
        if not node_id:
            raise ValueError("skill node requires node_id or skill_id")
        normalized = self._normalize_skill_node(dict(skill), node_id=node_id)
        normalized["retrieval"] = dict(skill.get("retrieval", normalized.get("retrieval", {})))
        self.nodes[node_id] = normalized
        if save:
            self.save()
        return normalized

    def apply_skill_distillation(
        self,
        *,
        skill: dict[str, Any],
        edges: list[dict[str, Any]],
        save: bool = True,
    ) -> dict[str, Any]:
        node = self.upsert_skill(skill, save=False)
        skill_id = node["node_id"]
        source_episode_ids = {
            str(edge.get("source", "")).strip()
            for edge in edges
            if str(edge.get("source", "")).strip()
        }
        self.edges = [
            edge for edge in self.edges
            if not (
                edge.get("edge_type") == "episode_skill"
                and edge.get("target") == skill_id
                and edge.get("source") in source_episode_ids
                and str(edge.get("metadata", {}).get("role", "")) == "source_evidence"
            )
        ]
        persisted_edges = [self._upsert_edge(edge, save=False) for edge in edges]
        if save:
            self.save()
        return {"skill": node, "edges": persisted_edges}

    def apply_skill_validation(
        self,
        *,
        skill: dict[str, Any],
        edge: dict[str, Any] | None = None,
        save: bool = True,
    ) -> dict[str, Any]:
        node = self.upsert_skill(skill, save=False)
        persisted_edge = self._upsert_edge(edge, save=False) if edge else None
        if save:
            self.save()
        return {"skill": node, "edge": persisted_edge}

    # ── Retrieval health ───────────────────────────────────────────────

    def retrieval_health(self, embedding_signature: dict[str, Any] | None = None) -> dict[str, int]:
        total_nodes = 0
        valid_vectors = 0
        stale_vectors = 0
        signature = embedding_signature or {}
        for node in self.nodes.values():
            if node.get("node_type") not in {"concept", "episode", "skill"}:
                continue
            total_nodes += 1
            retrieval = node.get("retrieval", {})
            vector = retrieval.get("embedding_vector", [])
            metadata = retrieval.get("embedding_metadata", {})
            if not vector:
                continue
            checks = ["provider", "model_id"]
            if signature.get("dimensions"):
                checks.append("dimensions")
            if signature and any(metadata.get(key) != signature.get(key) for key in checks):
                stale_vectors += 1
            else:
                valid_vectors += 1
        return {"total_nodes": total_nodes, "valid_vectors": valid_vectors, "stale_vectors": stale_vectors}

    # ── Internals ──────────────────────────────────────────────────────

    def _normalize_skill_node(self, skill: dict[str, Any], *, node_id: str) -> dict[str, Any]:
        normalized = dict(skill)
        normalized["skill_id"] = str(skill.get("skill_id") or node_id)
        normalized["node_id"] = node_id
        normalized["node_type"] = "skill"
        concept_scope = [
            str(item).strip()
            for item in normalized.pop("concept_scope", []) or []
            if str(item).strip()
        ]
        metadata = dict(normalized.get("metadata", {}))
        if concept_scope and not metadata.get("evidence_concept_scope"):
            metadata["evidence_concept_scope"] = concept_scope
        normalized["metadata"] = metadata
        return normalized

    def _concept_id_for_name(self, name: str) -> str:
        ascii_slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        if ascii_slug:
            return f"concept_{ascii_slug}"
        digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        return f"concept_{digest}"

    def _normalize_lookup(self, value: str) -> str:
        return re.sub(r"[\W_]+", "", value.strip().lower())

    def _upsert_edge(self, edge: dict[str, Any] | None, *, save: bool = True) -> dict[str, Any] | None:
        if edge is None:
            return None
        edge_id = str(edge.get("edge_id") or "").strip()
        if not edge_id:
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            edge_type = str(edge.get("edge_type") or "edge").strip()
            edge_id = f"edge_{edge_type}_{source}_{target}"
        persisted = {
            "edge_id": edge_id,
            "edge_type": str(edge.get("edge_type") or "edge"),
            "source": str(edge.get("source") or ""),
            "target": str(edge.get("target") or ""),
            "weight": float(edge.get("weight", 0.0)),
            "evidence": str(edge.get("evidence", "")).strip(),
            "metadata": dict(edge.get("metadata", {})),
        }
        self.edges = [item for item in self.edges if item.get("edge_id") != edge_id]
        self.edges.append(persisted)
        if save:
            self.save()
        return persisted

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        length = min(len(left), len(right))
        if length == 0:
            return 0.0
        dot = sum(left[i] * right[i] for i in range(length))
        left_norm = sum(v * v for v in left[:length]) ** 0.5
        right_norm = sum(v * v for v in right[:length]) ** 0.5
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
