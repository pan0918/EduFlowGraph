"use client";

import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import type { DashboardSnapshot } from "@/lib/types";
import { formatSkillDisplay } from "@/lib/skill-display";
import {
  buildMemoryGraphModel,
  type MemoryGraphEdge,
  type MemoryGraphNode,
  type MemoryGraphNodeKind,
} from "@/components/workspace/memory-graph-layout";

const TONES: Record<
  MemoryGraphNodeKind,
  {
    fill: string;
    softFill: string;
    stroke: string;
    text: string;
  }
> = {
  concept: {
    fill: "#cf8e5f",
    softFill: "rgba(207, 142, 95, 0.15)",
    stroke: "rgba(207, 142, 95, 0.55)",
    text: "#8e4c20",
  },
  episode: {
    fill: "#a85423",
    softFill: "rgba(168, 84, 35, 0.16)",
    stroke: "rgba(168, 84, 35, 0.58)",
    text: "#7a3610",
  },
  skill: {
    fill: "#6d3a22",
    softFill: "rgba(109, 58, 34, 0.16)",
    stroke: "rgba(109, 58, 34, 0.6)",
    text: "#4f2410",
  },
};

function curvePath(source: MemoryGraphNode, target: MemoryGraphNode) {
  const bias = source.layerIndex < target.layerIndex ? 0.3 : 0.22;
  const controlSourceX = source.x + (490 - source.x) * bias;
  const controlSourceY = source.y + (490 - source.y) * bias;
  const controlTargetX = target.x + (490 - target.x) * bias;
  const controlTargetY = target.y + (490 - target.y) * bias;
  return `M ${source.x} ${source.y} C ${controlSourceX} ${controlSourceY}, ${controlTargetX} ${controlTargetY}, ${target.x} ${target.y}`;
}

function shorten(text: string, maxLength: number) {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}…`;
}

function nodeTypeLabel(kind: MemoryGraphNodeKind) {
  if (kind === "concept") return "概念节点";
  if (kind === "episode") return "学习片段";
  return "技能节点";
}

function connectedNodes(
  selectedNode: MemoryGraphNode | null,
  nodesById: Map<string, MemoryGraphNode>,
) {
  if (!selectedNode) {
    return [];
  }

  return selectedNode.connectedNodeIds
    .map((nodeId) => nodesById.get(nodeId))
    .filter((node): node is MemoryGraphNode => Boolean(node))
    .sort((left, right) => {
      if (left.kind === right.kind) {
        return left.title.localeCompare(right.title);
      }
      return left.layerIndex - right.layerIndex;
    });
}

function detailBody(
  node: MemoryGraphNode | null,
  nodesById: Map<string, MemoryGraphNode>,
  edges: MemoryGraphEdge[],
) {
  if (!node) {
    return {
      eyebrow: "图谱详情",
      title: "点击任意节点",
      description: "选中概念、学习片段或技能节点后，这里会显示提炼后的关键信息和关联关系。",
      metrics: [],
      bullets: [],
      connections: [],
      relationEvidence: [],
    };
  }

  const connections = connectedNodes(node, nodesById);
  const relationEvidence = edges
    .filter((edge) => edge.sourceId === node.id || edge.targetId === node.id)
    .map((edge) => {
      const otherId = edge.sourceId === node.id ? edge.targetId : edge.sourceId;
      const other = nodesById.get(otherId);
      return {
        id: edge.id,
        nodeId: otherId,
        label: other?.title || otherId,
        kind: other ? nodeTypeLabel(other.kind) : "关联节点",
        evidence: edge.evidence || edge.edgeType.replaceAll("_", " "),
      };
    })
    .slice(0, 3);

  if (node.kind === "concept") {
    const raw = node.raw as DashboardSnapshot["concepts"][number];
    return {
      eyebrow: "Concept",
      title: raw.name,
      description: raw.description || "当前概念还没有补充详细描述。",
      metrics: [
        { label: "关联节点", value: String(node.connectedNodeIds.length) },
        { label: "图层", value: "L1" },
        { label: "最近更新", value: raw.metadata?.updated_at?.slice(0, 10) || "未记录" },
      ],
      bullets: raw.aliases?.length
        ? [`别名：${raw.aliases.slice(0, 4).join(" · ")}`]
        : ["这个概念目前还没有登记别名。"],
      connections,
      relationEvidence,
    };
  }

  if (node.kind === "episode") {
    const raw = node.raw as DashboardSnapshot["episodes"][number];
    const score =
      typeof raw.learning_outcome?.score === "number"
        ? raw.learning_outcome.score.toFixed(2)
        : "未记录";
    return {
      eyebrow: "Episode",
      title: raw.summary.title,
      description: raw.summary.short_summary || raw.summary.topic_summary,
      metrics: [
        ...(node.mergedCount > 1
          ? [{ label: "聚合片段", value: String(node.mergedCount) }]
          : []),
        { label: "片段类型", value: raw.episode_type.replaceAll("_", " ") },
        { label: "结果评分", value: score },
        { label: "图层", value: "L2" },
      ],
      bullets: [
        node.mergedCount > 1
          ? `已合并：${node.sourceNodeIds.length} 条同主题记录`
          : "",
        `学生问题：${raw.learner_problem.student_question}`,
        `诊断：${raw.learner_problem.detected_problem}`,
        raw.learning_outcome?.evidence ? `结果证据：${raw.learning_outcome.evidence}` : "",
      ].filter(Boolean),
      connections,
      relationEvidence,
    };
  }

  const raw = node.raw as DashboardSnapshot["skills"][number];
  const display = formatSkillDisplay(raw);
  return {
    eyebrow: "Skill",
    title: display.name,
    description: display.trigger,
    metrics: [
      { label: "状态", value: display.status },
      { label: "置信度", value: (raw.quality?.confidence ?? 0).toFixed(2) },
      { label: "图层", value: "L3" },
    ],
    bullets: [
      `困难模式：${display.difficulty}`,
      display.teachingActions.length
        ? `教学动作：${display.teachingActions.slice(0, 4).join(" · ")}`
        : "",
    ].filter(Boolean),
    connections,
    relationEvidence,
  };
}

function popupPosition(node: MemoryGraphNode) {
  const width = 330;
  const height = 218;
  const xCandidate = node.x > 640 ? node.x - width - 32 : node.x + 32;
  const yCandidate = node.y > 710 ? node.y - height - 24 : node.y - 44;
  return {
    x: Math.max(28, Math.min(980 - width - 28, xCandidate)),
    y: Math.max(28, Math.min(980 - height - 28, yCandidate)),
    width,
    height,
  };
}

export function MemoryGraphView({
  snapshot,
}: {
  snapshot: Pick<DashboardSnapshot, "concepts" | "episodes" | "skills" | "edges">;
}) {
  const model = useMemo(() => buildMemoryGraphModel(snapshot), [snapshot]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedNodeId((current) => {
      if (current && model.nodes.some((node) => node.id === current)) {
        return current;
      }
      return null;
    });
  }, [model.nodes]);

  const nodesById = useMemo(
    () => new Map(model.nodes.map((node) => [node.id, node])),
    [model.nodes],
  );
  const selectedNode = selectedNodeId ? nodesById.get(selectedNodeId) ?? null : null;
  const selectedSet = useMemo(() => {
    if (!selectedNode) {
      return new Set<string>();
    }
    return new Set([selectedNode.id, ...selectedNode.connectedNodeIds]);
  }, [selectedNode]);

  const visibleLabels = useMemo(() => {
    if (model.nodes.length <= 12) {
      return new Set(model.nodes.map((node) => node.id));
    }

    const sorted = [...model.nodes].sort((left, right) => right.degree - left.degree);
    return new Set([
      ...sorted.slice(0, 6).map((node) => node.id),
      ...(selectedNode ? [selectedNode.id, ...selectedNode.connectedNodeIds] : []),
    ]);
  }, [model.nodes, selectedNode]);

  const detail = detailBody(selectedNode, nodesById, model.edges);
  const popup = selectedNode ? popupPosition(selectedNode) : null;

  return (
    <section className="surface-card mt-5 overflow-hidden p-0">
      <div className="min-h-[760px]">
        <div className="relative min-h-[760px] overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.96),rgba(248,241,231,0.88)_45%,rgba(242,231,216,0.95)_100%)]" />
          <div className="absolute left-[-140px] top-[-120px] h-[320px] w-[320px] rounded-full bg-[rgba(213,170,137,0.18)] blur-3xl" />
          <div className="absolute bottom-[-120px] right-[-80px] h-[280px] w-[280px] rounded-full bg-[rgba(162,105,65,0.12)] blur-3xl" />

          <div className="relative z-10 flex h-full flex-col px-5 py-5 lg:px-7 lg:py-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
                  Graph View
                </div>
                <h2 className="mt-2 text-[30px] font-semibold tracking-tight text-[var(--foreground)]">
                  图谱视图
                </h2>
              </div>
            </div>

            <div className="relative mt-6 flex-1 overflow-hidden rounded-[30px] border border-white/70 bg-white/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
              <svg
                viewBox="0 0 980 980"
                className="h-full min-h-[620px] w-full"
                role="img"
                aria-label="分层记忆图谱"
                onClick={() => setSelectedNodeId(null)}
              >
                <defs>
                  <radialGradient id="memoryGraphGlow" cx="50%" cy="50%" r="68%">
                    <stop offset="0%" stopColor="rgba(255,255,255,0.95)" />
                    <stop offset="55%" stopColor="rgba(246,236,225,0.88)" />
                    <stop offset="100%" stopColor="rgba(239,224,207,0.72)" />
                  </radialGradient>
                  <filter id="nodeShadow" x="-50%" y="-50%" width="200%" height="200%">
                    <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="rgba(112, 70, 38, 0.18)" />
                  </filter>
                </defs>

                <rect x="0" y="0" width="980" height="980" fill="url(#memoryGraphGlow)" />

                {[120, 170, 292, 412, 468].map((radius, index) => (
                  <circle
                    key={radius}
                    cx="490"
                    cy="490"
                    r={radius}
                    fill={index === 0 ? "rgba(255,255,255,0.65)" : "none"}
                    stroke="rgba(182, 148, 120, 0.16)"
                    strokeWidth={index === 0 ? 2 : 1.4}
                    strokeDasharray={index >= 3 ? "3 10" : undefined}
                  />
                ))}

                {Array.from({ length: 18 }).map((_, index) => {
                  const angle = (-Math.PI / 2) + (Math.PI * 2 * index) / 18;
                  const x2 = 490 + Math.cos(angle) * 468;
                  const y2 = 490 + Math.sin(angle) * 468;
                  return (
                    <line
                      key={index}
                      x1="490"
                      y1="490"
                      x2={x2}
                      y2={y2}
                      stroke="rgba(180, 151, 127, 0.08)"
                      strokeWidth="1"
                    />
                  );
                })}

                <g>
                  {model.edges.map((edge) => {
                    const source = nodesById.get(edge.sourceId);
                    const target = nodesById.get(edge.targetId);
                    if (!source || !target) {
                      return null;
                    }

                    const isHighlighted =
                      selectedNode &&
                      (edge.sourceId === selectedNode.id ||
                        edge.targetId === selectedNode.id);
                    const shouldDim =
                      selectedNode && !isHighlighted;

                    return (
                      <path
                        key={edge.id}
                        d={curvePath(source, target)}
                        fill="none"
                        stroke={isHighlighted ? "#9a4f25" : "rgba(146, 108, 78, 0.16)"}
                        strokeWidth={isHighlighted ? 2.6 : 1}
                        strokeOpacity={shouldDim ? 0.15 : isHighlighted ? 0.92 : 0.58}
                      />
                    );
                  })}
                </g>

                <g>
                  <circle
                    cx="490"
                    cy="490"
                    r="94"
                    fill="rgba(255,255,255,0.88)"
                    stroke="rgba(185, 142, 110, 0.32)"
                    strokeWidth="2"
                    filter="url(#nodeShadow)"
                  />
                  <circle
                    cx="490"
                    cy="490"
                    r="72"
                    fill="rgba(243,231,218,0.88)"
                    stroke="rgba(185, 142, 110, 0.24)"
                    strokeWidth="1.5"
                  />
                  <text
                    x="490"
                    y="482"
                    textAnchor="middle"
                    className="fill-[#9a562b] text-[18px] font-semibold"
                  >
                    Memory
                  </text>
                  <text
                    x="490"
                    y="510"
                    textAnchor="middle"
                    className="fill-[#8d7d6e] text-[11px] uppercase tracking-[0.22em]"
                  >
                    {model.summary.totalNodes} nodes · {model.summary.totalEdges} links
                  </text>
                </g>

                {model.nodes.map((node) => {
                  const tone = TONES[node.kind];
                  const isSelected = selectedNode?.id === node.id;
                  const isContextual = selectedSet.has(node.id);
                  const shouldDim = selectedNode && !isContextual;
                  const labelOffset = node.kind === "skill" ? 26 : 22;
                  const labelX = node.x + Math.cos(node.orbitAngle) * (node.radius + labelOffset);
                  const labelY = node.y + Math.sin(node.orbitAngle) * (node.radius + labelOffset);
                  const textAnchor =
                    Math.cos(node.orbitAngle) > 0.2
                      ? "start"
                      : Math.cos(node.orbitAngle) < -0.2
                        ? "end"
                        : "middle";

                  return (
                    <g key={node.id} onClick={(event) => event.stopPropagation()}>
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius + (isSelected ? 8 : 4)}
                        fill={isSelected ? tone.softFill : "rgba(255,255,255,0.34)"}
                        opacity={shouldDim ? 0.2 : 1}
                      />
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius}
                        fill={tone.fill}
                        fillOpacity={isSelected ? 1 : 0.88}
                        stroke={isSelected ? "#fff8f3" : tone.stroke}
                        strokeWidth={isSelected ? 3 : 1.4}
                        opacity={shouldDim ? 0.24 : 1}
                        filter={isSelected ? "url(#nodeShadow)" : undefined}
                        className="cursor-pointer transition-transform"
                        onClick={() => setSelectedNodeId(node.id)}
                      />
                      {visibleLabels.has(node.id) ? (
                        <>
                          <text
                            x={labelX}
                            y={labelY}
                            textAnchor={textAnchor}
                            className={clsx(
                              "text-[11px] font-semibold tracking-[0.02em]",
                              shouldDim ? "fill-[rgba(75,50,32,0.24)]" : "fill-[#34261d]",
                            )}
                          >
                            {shorten(node.title, 24)}
                          </text>
                          <text
                            x={labelX}
                            y={labelY + 18}
                            textAnchor={textAnchor}
                            className={clsx(
                              "text-[9px] tracking-[0.16em] uppercase",
                              shouldDim ? "fill-[rgba(112,90,70,0.18)]" : "fill-[#9b8b7f]",
                            )}
                          >
                            {node.kind}
                          </text>
                        </>
                      ) : null}
                    </g>
                  );
                })}

                {selectedNode && popup ? (
                  <foreignObject
                    x={popup.x}
                    y={popup.y}
                    width={popup.width}
                    height={popup.height}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <div className="h-full rounded-[18px] border border-[rgba(198,172,148,0.78)] bg-white/95 px-4 py-3 shadow-[0_18px_40px_rgba(82,55,34,0.18)] backdrop-blur">
                      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-[#8e8175]">
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: TONES[selectedNode.kind].fill }}
                        />
                        {nodeTypeLabel(selectedNode.kind)}
                      </div>
                      <div className="mt-2 text-[17px] font-semibold leading-6 text-[#231b16]">
                        {shorten(detail.title, 34)}
                      </div>
                      <div className="mt-2 text-[13px] leading-5 text-[#5f554b]">
                        {shorten(detail.description, 112)}
                      </div>
                      {detail.relationEvidence.length ? (
                        <div className="mt-3 space-y-1.5">
                          {detail.relationEvidence.slice(0, 2).map((relation) => (
                            <button
                              key={relation.id}
                              onClick={() => {
                                setSelectedNodeId(relation.nodeId);
                              }}
                              className="block w-full rounded-[12px] bg-[#f8efe7] px-3 py-2 text-left text-[12px] leading-4 text-[#6c4730] transition hover:bg-[#f2dfce]"
                            >
                              <span className="font-medium">{shorten(relation.label, 28)}</span>
                              <span className="text-[#9b806d]"> · {shorten(relation.evidence, 42)}</span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-3 rounded-[12px] bg-[#f8efe7] px-3 py-2 text-[12px] leading-4 text-[#7b6b5f]">
                          这个节点暂时没有直接关联边。
                        </div>
                      )}
                    </div>
                  </foreignObject>
                ) : null}
              </svg>

              <div className="pointer-events-none absolute bottom-4 left-4 rounded-[24px] border border-white/70 bg-white/72 px-4 py-3 shadow-[0_18px_42px_rgba(103,72,42,0.08)] backdrop-blur">
                <div className="flex flex-wrap items-center gap-4 text-sm text-[var(--foreground)]">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-[#cf8e5f]" />
                    L1 {model.summary.conceptCount}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-[#a85423]" />
                    L2 {model.summary.episodeCount}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-[#6d3a22]" />
                    L3 {model.summary.skillCount}
                  </span>
                </div>
                <div className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
                  点击节点锁定高亮并查看摘要，关联路径会同时显现出来。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
