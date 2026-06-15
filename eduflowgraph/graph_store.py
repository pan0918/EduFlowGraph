import json
import hashlib
from pathlib import Path
import re
from typing import Any

from .schemas import utc_now
from .skills import DIFFICULTY_PATTERN_TAXONOMY


CANONICAL_CONCEPT_GROUPS = [
    {
        "name": "Bayes theorem",
        "aliases": [
            "Bayes theorem",
            "Bayes' theorem",
            "Bayes rule",
            "Bayes' rule",
            "Bayes formula",
            "Bayesian theorem",
            "贝叶斯定理",
            "贝叶斯公式",
        ],
    },
    {
        "name": "Conditional probability",
        "aliases": [
            "Conditional probability",
            "Conditional Probability",
            "Conditional Probability Directionality",
            "条件概率",
            "条件概率方向",
            "条件概率的方向性",
            "P(A|B) vs P(B|A)",
        ],
    },
    {
        "name": "Base Rate",
        "aliases": [
            "Base Rate",
            "base rate",
            "基率",
            "基准率",
            "基础概率",
        ],
    },
]

LEGACY_SKILL_NAME_TRANSLATIONS = {
    "Clarify direction confusion through contrastive explanation": "用对比解释澄清方向混淆",
    "Ground formula meaning through decomposition and learner restatement": "通过公式拆解和复述落地符号含义",
    "Support transfer to similar cases through worked examples": "用例题示范支持迁移到相似题",
    "Build a workable step sequence through guided decomposition": "通过引导拆解建立可执行步骤",
    "Ground abstract ideas through concrete examples": "用具体例子落地抽象概念",
}

LEGACY_SKILL_TEXT_TRANSLATIONS = {
    "Name the two easily confused objects.": "先点名两个容易混淆的对象。",
    "Explain each object in natural language.": "用自然语言分别解释两个对象。",
    "Contrast them under the same scenario.": "放到同一个场景里对比它们。",
    "Ask the learner to restate the idea.": "请学习者用自己的话复述。",
    "Probe for missing links.": "追问缺失的理解环节。",
    "Confirm transfer to a fresh example.": "用一个新例子确认能否迁移。",
    "The learner can explain the directional difference without reversing the two meanings.": "学习者能说明两个对象的方向差异，并且不再反着解释。",
    "The learner can correctly distinguish the two targets in a fresh scenario.": "学习者能在新场景中正确区分两个目标。",
    "The learner can clearly state the difference between the two targets.": "学习者能清楚说出两个目标的差异。",
}


class GraphStore:
    def __init__(self, nodes_path: Path, edges_path: Path):
        self.nodes_path = nodes_path
        self.edges_path = edges_path
        self.nodes_path.parent.mkdir(parents=True, exist_ok=True)
        self.edges_path.parent.mkdir(parents=True, exist_ok=True)
        self.nodes = self._load_json(self.nodes_path, {})
        self.edges = self._load_json(self.edges_path, [])
        if self._normalize_loaded_graph():
            self.save()

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
            return default
        text = path.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else default

    def save(self) -> None:
        self.nodes_path.write_text(
            json.dumps(self.nodes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.edges_path.write_text(
            json.dumps(self.edges, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset(self) -> None:
        self.nodes = {}
        self.edges = []

    def rebuild_from_episodes(self, episodes: list[dict[str, Any]]) -> None:
        self.reset()
        for episode in episodes:
            self.apply_episode(episode, save=False)
        self.save()

    def nodes_by_type(self, node_type: str) -> dict[str, dict[str, Any]]:
        return {
            node_id: node
            for node_id, node in self.nodes.items()
            if node.get("node_type") == node_type
        }

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
            edge
            for edge in self.edges
            if not (
                edge.get("edge_type") == "episode_concept"
                and edge.get("source") == episode_id
            )
        ]

        persisted_edges: list[dict[str, Any]] = []
        for edge in edges:
            target_name = str(
                edge.get("target_name")
                or edge.get("concept_name")
                or edge.get("target")
                or ""
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
                "weight": float(edge.get("weight", 0.0)),
                "evidence": str(edge.get("evidence", "")).strip(),
                "metadata": dict(edge.get("metadata", {})),
            }
            self.edges.append(persisted)
            persisted_edges.append(persisted)

        if save:
            self.save()
        return {
            "concepts": list(self.nodes_by_type("concept").values()),
            "edges": persisted_edges,
        }

    def apply_skill_distillation(
        self,
        *,
        skill: dict[str, Any],
        edges: list[dict[str, Any]],
        save: bool = True,
    ) -> dict[str, Any]:
        node = self.upsert_skill(skill, save=False)
        source_roles = {"source_evidence"}
        skill_id = node["node_id"]
        source_episode_ids = {
            str(edge.get("source", "")).strip()
            for edge in edges
            if str(edge.get("source", "")).strip()
        }
        self.edges = [
            edge
            for edge in self.edges
            if not (
                edge.get("edge_type") == "episode_skill"
                and edge.get("target") == skill_id
                and edge.get("source") in source_episode_ids
                and str(edge.get("metadata", {}).get("role", "")) in source_roles
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
        name, aliases = self._canonicalize_concept(raw_name, aliases)
        description = str(concept.get("description", "")).strip()
        now = utc_now()

        existing = self._find_existing_concept(name, aliases)
        if existing is None:
            node_id = self._concept_id_for_name(name or aliases[0] if aliases else "concept")
            normalized = {
                "concept_id": node_id,
                "node_id": node_id,
                "node_type": "concept",
                "name": name or aliases[0] if aliases else "Untitled concept",
                "aliases": aliases,
                "description": description,
                "retrieval": dict(concept.get("retrieval", {})),
                "metadata": {
                    "created_at": now,
                    "updated_at": now,
                },
            }
            self.nodes[node_id] = normalized
            if save:
                self.save()
            return normalized

        merged_aliases = []
        for alias in [*existing.get("aliases", []), *aliases, raw_name, name]:
            candidate = str(alias).strip()
            if (
                candidate
                and candidate != existing["name"]
                and candidate not in merged_aliases
            ):
                merged_aliases.append(candidate)
        existing["aliases"] = merged_aliases
        if self._canonical_name_for(raw_name) == name and existing.get("name") != name:
            old_name = str(existing.get("name", "")).strip()
            if old_name and old_name not in existing["aliases"]:
                existing["aliases"].append(old_name)
            existing["name"] = name
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

    def _normalize_loaded_graph(self) -> bool:
        changed = False
        id_redirects: dict[str, str] = {}

        for node_id, node in list(self.nodes.items()):
            if node.get("node_type") != "concept":
                continue
            name, aliases = self._canonicalize_concept(
                str(node.get("name", "")).strip(),
                [
                    str(alias).strip()
                    for alias in node.get("aliases", [])
                    if str(alias).strip()
                ],
            )
            if not self._canonical_name_for(name):
                continue
            target_id = self._concept_id_for_name(name)
            normalized = dict(node)
            normalized["concept_id"] = target_id
            normalized["node_id"] = target_id
            normalized["node_type"] = "concept"
            normalized["name"] = name
            normalized["aliases"] = aliases
            if target_id in self.nodes and target_id != node_id:
                target = self.nodes[target_id]
                self._merge_concept_node(target, normalized)
                del self.nodes[node_id]
                id_redirects[node_id] = target_id
                changed = True
            elif target_id != node_id:
                del self.nodes[node_id]
                self.nodes[target_id] = normalized
                id_redirects[node_id] = target_id
                changed = True
            elif normalized != node:
                self.nodes[node_id] = normalized
                changed = True

        if id_redirects:
            for edge in self.edges:
                source = str(edge.get("source") or "")
                target = str(edge.get("target") or "")
                if source in id_redirects:
                    edge["source"] = id_redirects[source]
                    changed = True
                if target in id_redirects:
                    edge["target"] = id_redirects[target]
                    changed = True

        for node_id, node in list(self.nodes.items()):
            if node.get("node_type") != "skill":
                continue
            normalized = self._normalize_skill_node(dict(node), node_id=node_id)
            if normalized != node:
                self.nodes[node_id] = normalized
                changed = True

        return changed

    def _merge_concept_node(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
    ) -> None:
        target["concept_id"] = str(target.get("node_id") or source["node_id"])
        target["node_id"] = str(target.get("node_id") or source["node_id"])
        target["node_type"] = "concept"
        target["name"] = source["name"]
        aliases: list[str] = []
        for value in [
            *target.get("aliases", []),
            target.get("name", ""),
            *source.get("aliases", []),
            source.get("name", ""),
        ]:
            text = str(value).strip()
            if text and text != target["name"] and text not in aliases:
                aliases.append(text)
        target["aliases"] = aliases
        if not target.get("description") and source.get("description"):
            target["description"] = source.get("description", "")
        if not target.get("retrieval") and source.get("retrieval"):
            target["retrieval"] = dict(source.get("retrieval", {}))
        metadata = dict(target.get("metadata", {}))
        source_metadata = source.get("metadata", {})
        metadata.setdefault("created_at", source_metadata.get("created_at", utc_now()))
        metadata["updated_at"] = utc_now()
        target["metadata"] = metadata

    def _normalize_skill_node(
        self,
        skill: dict[str, Any],
        *,
        node_id: str,
    ) -> dict[str, Any]:
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
        name = str(normalized.get("name", "")).strip()
        if name in LEGACY_SKILL_NAME_TRANSLATIONS:
            normalized["name"] = LEGACY_SKILL_NAME_TRANSLATIONS[name]
        trigger = str(normalized.get("trigger", "")).strip()
        if self._skill_trigger_is_specific(trigger):
            pattern = str(normalized.get("difficulty_pattern") or "unknown")
            phrase = DIFFICULTY_PATTERN_TAXONOMY.get(
                pattern,
                DIFFICULTY_PATTERN_TAXONOMY["unknown"],
            ).get("trigger_phrase", "尚不明确的学习困难模式")
            normalized["trigger"] = f"当学习者出现{phrase}时使用。"
        if isinstance(normalized.get("procedure"), list):
            normalized["procedure"] = [
                self._translate_legacy_skill_text(str(item))
                for item in normalized.get("procedure", [])
                if str(item).strip()
            ][:3]
        if isinstance(normalized.get("success_criteria"), list):
            normalized["success_criteria"] = [
                self._translate_legacy_skill_text(str(item))
                for item in normalized.get("success_criteria", [])
                if str(item).strip()
            ][:2]
        return normalized

    def _skill_trigger_is_specific(self, trigger: str) -> bool:
        if not trigger:
            return False
        if trigger.startswith("Use "):
            return True
        if " around " in trigger:
            return True
        if "当学习者在" in trigger and "上出现" in trigger:
            return True
        return False

    def _translate_legacy_skill_text(self, value: str) -> str:
        text = str(value).strip()
        return LEGACY_SKILL_TEXT_TRANSLATIONS.get(text, text)

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
        return {
            "total_nodes": total_nodes,
            "valid_vectors": valid_vectors,
            "stale_vectors": stale_vectors,
        }

    def _find_existing_concept(
        self,
        name: str,
        aliases: list[str],
    ) -> dict[str, Any] | None:
        wanted = {
            normalized
            for normalized in [self._normalize_lookup(name), *(self._normalize_lookup(alias) for alias in aliases)]
            if normalized
        }
        if not wanted:
            return None
        for concept in self.nodes_by_type("concept").values():
            known = {
                normalized
                for normalized in [
                    self._normalize_lookup(str(concept.get("name", ""))),
                    self._canonical_lookup_key(str(concept.get("name", ""))),
                    *(self._normalize_lookup(alias) for alias in concept.get("aliases", [])),
                    *(self._canonical_lookup_key(alias) for alias in concept.get("aliases", [])),
                ]
                if normalized
            }
            if wanted & known:
                return concept
        return None

    def _concept_id_for_name(self, name: str) -> str:
        ascii_slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        if ascii_slug:
            return f"concept_{ascii_slug}"
        digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        return f"concept_{digest}"

    def _normalize_lookup(self, value: str) -> str:
        return re.sub(r"[\W_]+", "", value.strip().lower())

    def _canonicalize_concept(
        self,
        name: str,
        aliases: list[str],
    ) -> tuple[str, list[str]]:
        canonical = self._canonical_name_for(name)
        for alias in aliases:
            canonical = self._canonical_name_for(alias) or canonical
        if not canonical:
            return name, aliases
        canonical_aliases = self._canonical_aliases_for(canonical)
        merged_aliases: list[str] = []
        for value in [*canonical_aliases, name, *aliases]:
            text = str(value).strip()
            if text and text != canonical and text not in merged_aliases:
                merged_aliases.append(text)
        return canonical, merged_aliases

    def _canonical_name_for(self, value: str) -> str:
        normalized = self._normalize_lookup(value)
        if not normalized:
            return ""
        for group in CANONICAL_CONCEPT_GROUPS:
            keys = {
                self._normalize_lookup(alias)
                for alias in [group["name"], *group.get("aliases", [])]
            }
            if normalized in keys:
                return str(group["name"])
        return ""

    def _canonical_lookup_key(self, value: str) -> str:
        canonical = self._canonical_name_for(value)
        return self._normalize_lookup(canonical or value)

    def _canonical_aliases_for(self, canonical_name: str) -> list[str]:
        for group in CANONICAL_CONCEPT_GROUPS:
            if group["name"] == canonical_name:
                return [str(alias) for alias in group.get("aliases", [])]
        return []

    def _upsert_edge(
        self,
        edge: dict[str, Any] | None,
        *,
        save: bool = True,
    ) -> dict[str, Any] | None:
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
