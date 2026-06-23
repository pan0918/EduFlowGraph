import type { DashboardSnapshot } from "@/lib/types";
import { formatSkillDisplay } from "../../lib/skill-display.ts";

export type MemoryGraphNodeKind = "concept" | "episode" | "skill";

export interface MemoryGraphLayer {
  kind: MemoryGraphNodeKind;
  label: string;
  count: number;
  layerIndex: number;
  radius: number;
}

export interface MemoryGraphEdge {
  id: string;
  sourceId: string;
  targetId: string;
  edgeType: string;
  weight: number;
  evidence: string;
}

export interface MemoryGraphNode {
  id: string;
  kind: MemoryGraphNodeKind;
  layerIndex: number;
  title: string;
  subtitle: string;
  summary: string;
  radius: number;
  orbitRadius: number;
  orbitAngle: number;
  x: number;
  y: number;
  degree: number;
  connectedNodeIds: string[];
  mergedCount: number;
  sourceNodeIds: string[];
  raw:
    | DashboardSnapshot["concepts"][number]
    | DashboardSnapshot["episodes"][number]
    | DashboardSnapshot["skills"][number];
}

export interface MemoryGraphModel {
  center: {
    x: number;
    y: number;
  };
  layers: MemoryGraphLayer[];
  nodes: MemoryGraphNode[];
  edges: MemoryGraphEdge[];
  summary: {
    totalNodes: number;
    totalEdges: number;
    conceptCount: number;
    episodeCount: number;
    skillCount: number;
  };
}

const GRAPH_CENTER = { x: 490, y: 490 };
const LAYER_RADII: Record<MemoryGraphNodeKind, number> = {
  concept: 170,
  episode: 292,
  skill: 412,
};
const LAYER_ORDER: MemoryGraphNodeKind[] = ["concept", "episode", "skill"];
const LAYER_LABELS: Record<MemoryGraphNodeKind, string> = {
  concept: "L1 Concepts",
  episode: "L2 Episodes",
  skill: "L3 Skills",
};
const LAYER_OFFSETS: Record<MemoryGraphNodeKind, number> = {
  concept: -Math.PI / 2,
  episode: -Math.PI / 2 + Math.PI / 8,
  skill: -Math.PI / 2 - Math.PI / 10,
};

function clampNodeRadius(kind: MemoryGraphNodeKind, degree: number): number {
  const base = kind === "episode" ? 8 : 6;
  return Math.min(base + degree * 1.6, kind === "episode" ? 16 : 13);
}

function normalizedAngle(index: number, count: number, offset: number): number {
  if (count <= 0) {
    return offset;
  }
  if (count === 1) {
    return offset;
  }
  return offset + (Math.PI * 2 * index) / count;
}

function edgeWeight(value: number | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0.5;
  }
  return Math.max(0.15, Math.min(1, value));
}

function nodePosition(orbitRadius: number, orbitAngle: number) {
  return {
    x: GRAPH_CENTER.x + Math.cos(orbitAngle) * orbitRadius,
    y: GRAPH_CENTER.y + Math.sin(orbitAngle) * orbitRadius,
  };
}

function normalizeKey(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function episodeGroupKey(episode: DashboardSnapshot["episodes"][number]): string {
  const title = episode.title || "";
  const obstacle = episode.learner?.obstacle || "";
  const strategy = episode.tutor?.strategy || "";
  return [
    normalizeKey(title),
    normalizeKey(obstacle),
    normalizeKey(strategy),
  ].join("::");
}

function episodeGroupId(episodes: DashboardSnapshot["episodes"]): string {
  if (episodes.length === 1) {
    return episodes[0].node_id;
  }

  const first = episodes[0];
  const titleStr = typeof first.title === "string" ? first.title : "";
  const slug = normalizeKey(titleStr)
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
  return `episode_group_${slug || first.node_id}`;
}

export function buildMemoryGraphModel(
  snapshot: Pick<DashboardSnapshot, "concepts" | "episodes" | "skills" | "edges">,
): MemoryGraphModel {
  const adjacency = new Map<string, Set<string>>();
  const episodeGroups = new Map<string, DashboardSnapshot["episodes"]>();
  for (const episode of snapshot.episodes) {
    const key = episodeGroupKey(episode);
    const group = episodeGroups.get(key) ?? [];
    group.push(episode);
    episodeGroups.set(key, group);
  }

  const groupedEpisodes = [...episodeGroups.values()].map((group) =>
    [...group].sort((left, right) =>
      String(left.provenance?.start_time || "").localeCompare(
        String(right.provenance?.start_time || ""),
      ),
    ),
  );
  const episodeIdMap = new Map<string, string>();
  const sourceNodeIdsByGroupId = new Map<string, string[]>();
  for (const group of groupedEpisodes) {
    const groupId = episodeGroupId(group);
    sourceNodeIdsByGroupId.set(
      groupId,
      group.map((episode) => episode.node_id),
    );
    for (const episode of group) {
      episodeIdMap.set(episode.node_id, groupId);
    }
  }

  const validIds = new Set<string>([
    ...snapshot.concepts.map((concept) => concept.node_id),
    ...groupedEpisodes.map((group) => episodeGroupId(group)),
    ...snapshot.skills.map((skill) => skill.node_id),
  ]);

  const edgeByKey = new Map<string, MemoryGraphEdge>();
  for (const edge of snapshot.edges) {
    const sourceId = episodeIdMap.get(edge.source) ?? edge.source;
    const targetId = episodeIdMap.get(edge.target) ?? edge.target;
    if (
      sourceId === targetId ||
      !validIds.has(sourceId) ||
      !validIds.has(targetId)
    ) {
      continue;
    }

    const key = `${sourceId}::${targetId}::${edge.edge_type}`;
    const existing = edgeByKey.get(key);
    edgeByKey.set(key, {
      id: existing ? `${existing.id}+${edge.edge_id}` : edge.edge_id,
      sourceId,
      targetId,
      edgeType: edge.edge_type,
      weight: Math.max(existing?.weight ?? 0, edgeWeight(edge.weight)),
      evidence: existing?.evidence || edge.evidence || "",
    });
  }

  const edges = [...edgeByKey.values()].map((edge) => {
    const sourceNeighbors = adjacency.get(edge.sourceId) ?? new Set<string>();
    sourceNeighbors.add(edge.targetId);
    adjacency.set(edge.sourceId, sourceNeighbors);

    const targetNeighbors = adjacency.get(edge.targetId) ?? new Set<string>();
    targetNeighbors.add(edge.sourceId);
    adjacency.set(edge.targetId, targetNeighbors);

    return edge;
  });

  const conceptNodes = [...snapshot.concepts]
    .sort((left, right) => {
      const degreeDelta =
        (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
      if (degreeDelta !== 0) {
        return degreeDelta;
      }
      return left.name.localeCompare(right.name);
    })
    .map((concept, index, items) => {
      const connectedNodeIds = [...(adjacency.get(concept.node_id) ?? new Set<string>())];
      const orbitAngle = normalizedAngle(index, items.length, LAYER_OFFSETS.concept);
      const orbitRadius = LAYER_RADII.concept;
      const position = nodePosition(orbitRadius, orbitAngle);
      return {
        id: concept.node_id,
        kind: "concept" as const,
        layerIndex: 1,
        title: concept.name,
        subtitle: concept.aliases?.slice(0, 2).join(" · ") || "核心概念节点",
        summary: concept.description || "当前概念还没有补充描述。",
        radius: clampNodeRadius("concept", connectedNodeIds.length),
        orbitRadius,
        orbitAngle,
        x: position.x,
        y: position.y,
        degree: connectedNodeIds.length,
        connectedNodeIds,
        mergedCount: 1,
        sourceNodeIds: [concept.node_id],
        raw: concept,
      };
    });

  const episodeNodes = groupedEpisodes
    .sort((left, right) => {
      const leftId = episodeGroupId(left);
      const rightId = episodeGroupId(right);
      const degreeDelta =
        (adjacency.get(rightId)?.size || 0) - (adjacency.get(leftId)?.size || 0);
      if (degreeDelta !== 0) {
        return degreeDelta;
      }
      return (left[0].title || "").localeCompare(right[0].title || "");
    })
    .map((episodes, index, items) => {
      const episode = episodes[0];
      const groupId = episodeGroupId(episodes);
      const connectedNodeIds = [...(adjacency.get(groupId) ?? new Set<string>())];
      const orbitAngle = normalizedAngle(index, items.length, LAYER_OFFSETS.episode);
      const orbitRadius = LAYER_RADII.episode;
      const position = nodePosition(orbitRadius, orbitAngle);
      const mergedCount = episodes.length;
      return {
        id: groupId,
        kind: "episode" as const,
        layerIndex: 2,
        title: episode.title || "",
        subtitle:
          mergedCount > 1
            ? `${mergedCount} traces · ${episode.episode_type.replaceAll("_", " ")}`
            : episode.episode_type.replaceAll("_", " "),
        summary:
          mergedCount > 1
            ? `聚合了 ${mergedCount} 条同主题学习片段：${
                typeof episode.summary === "string" ? episode.summary : ""
              }`
            : typeof episode.summary === "string" ? episode.summary : "",
        radius: clampNodeRadius("episode", connectedNodeIds.length),
        orbitRadius,
        orbitAngle,
        x: position.x,
        y: position.y,
        degree: connectedNodeIds.length,
        connectedNodeIds,
        mergedCount,
        sourceNodeIds: sourceNodeIdsByGroupId.get(groupId) ?? [episode.node_id],
        raw: episode,
      };
    });

  const skillNodes = [...snapshot.skills]
    .sort((left, right) => {
      const degreeDelta =
        (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
      if (degreeDelta !== 0) {
        return degreeDelta;
      }
      return left.name.localeCompare(right.name);
    })
    .map((skill, index, items) => {
      const display = formatSkillDisplay(skill);
      const connectedNodeIds = [...(adjacency.get(skill.node_id) ?? new Set<string>())];
      const orbitAngle = normalizedAngle(index, items.length, LAYER_OFFSETS.skill);
      const orbitRadius = LAYER_RADII.skill;
      const position = nodePosition(orbitRadius, orbitAngle);
      return {
        id: skill.node_id,
        kind: "skill" as const,
        layerIndex: 3,
        title: display.name,
        subtitle: `${display.status} · ${display.difficulty}`,
        summary: display.trigger,
        radius: clampNodeRadius("skill", connectedNodeIds.length),
        orbitRadius,
        orbitAngle,
        x: position.x,
        y: position.y,
        degree: connectedNodeIds.length,
        connectedNodeIds,
        mergedCount: 1,
        sourceNodeIds: [skill.node_id],
        raw: skill,
      };
    });

  const nodes = [...conceptNodes, ...episodeNodes, ...skillNodes];

  return {
    center: GRAPH_CENTER,
    layers: LAYER_ORDER.map((kind, index) => ({
      kind,
      label: LAYER_LABELS[kind],
      count:
        kind === "concept"
          ? snapshot.concepts.length
          : kind === "episode"
            ? episodeNodes.length
            : snapshot.skills.length,
      layerIndex: index + 1,
      radius: LAYER_RADII[kind],
    })),
    nodes,
    edges,
    summary: {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      conceptCount: snapshot.concepts.length,
      episodeCount: episodeNodes.length,
      skillCount: snapshot.skills.length,
    },
  };
}
