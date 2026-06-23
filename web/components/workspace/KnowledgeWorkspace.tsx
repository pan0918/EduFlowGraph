"use client";

import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { MetricCards } from "@/components/workspace/MetricCards";
import { formatBeijingTime } from "@/lib/datetime";

export function KnowledgeWorkspace() {
  const { snapshot } = useWorkspace();
  const episodeById = new Map(snapshot.episodes.map((episode) => [episode.node_id, episode]));
  const conceptStats = new Map<
    string,
    { count: number; latestMainTitle: string | null }
  >();
  for (const edge of snapshot.edges) {
    if (edge.edge_type !== "episode_concept") continue;
    const stats = conceptStats.get(edge.target) || { count: 0, latestMainTitle: null };
    stats.count += 1;
    if (!stats.latestMainTitle && edge.metadata?.structural_role === "main") {
      stats.latestMainTitle = episodeById.get(edge.source)?.title || null;
    }
    conceptStats.set(edge.target, stats);
  }
  return (
    <div className="page-shell min-h-screen">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
          知识状态
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          概念掌握面板
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          这里聚焦学生在各个概念上的掌握状态、典型误区和建议教学动作。
        </p>
      </div>

      <MetricCards snapshot={snapshot} />

      {snapshot.concepts.length === 0 ? (
        <section className="mt-5 surface-card p-8">
          <div className="max-w-3xl">
            <div className="text-lg font-semibold tracking-tight">还没有概念状态</div>
            <p className="mt-3 text-sm leading-7 text-[var(--muted-foreground)]">
              这里不会再默认展示测试概念。等你开始真实教学交互并触发记忆抽取之后，
              概念掌握度、误区和建议动作才会逐步沉淀出来。
            </p>
          </div>
        </section>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        {snapshot.concepts.map((concept) => (
          <section key={concept.node_id} className="surface-card p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">{concept.name}</h2>
                <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
                  {concept.description || "该概念节点当前只保存稳定概念本体，后续可以逐步补充更多说明。"}
                </p>
              </div>
              <div className="rounded-full bg-[var(--secondary)] px-3 py-2 text-sm font-medium text-[var(--foreground)]">
                {(conceptStats.get(concept.node_id)?.count || 0).toString()} 次关联
              </div>
            </div>
            {concept.aliases?.length ? (
              <div className="mt-5">
                <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  别名 / 表达
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {concept.aliases.map((item) => (
                    <span key={item} className="rounded-full bg-amber-100 px-3 py-1.5 text-xs text-amber-900">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            {concept.metadata?.updated_at ? (
              <div className="mt-5">
                <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  更新时间
                </div>
                <div className="mt-3 text-sm leading-6 text-[var(--foreground)]">
                  {formatBeijingTime(concept.metadata.updated_at) ?? "未记录"}
                </div>
              </div>
            ) : null}
            {conceptStats.get(concept.node_id)?.latestMainTitle ? (
              <div className="mt-5 rounded-2xl bg-[var(--secondary)]/60 p-4 text-sm leading-6 text-[var(--foreground)]">
                最近作为主概念出现于：{conceptStats.get(concept.node_id)?.latestMainTitle}
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
