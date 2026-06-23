"use client";

import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { MemoryGraphView } from "@/components/workspace/MemoryGraphView";
import { MetricCards } from "@/components/workspace/MetricCards";

export function MemoryWorkspace() {
  const { snapshot } = useWorkspace();
  const hasMemory =
    snapshot.concepts.length > 0 ||
    snapshot.episodes.length > 0 ||
    snapshot.skills.length > 0;
  const memoryEvents = ((snapshot as unknown as Record<string, unknown>).memory_events ?? []) as
    Array<Record<string, unknown>>;
  const eventCount = memoryEvents.length || snapshot.memory_flow_count || 0;

  const countByType = (type: string) =>
    memoryEvents.filter((e) => e.event_type === type).length;

  return (
    <div className="page-shell min-h-screen">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
          空间 / 记忆
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          记忆工作台
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          这里展示自动抽取出的概念、学习片段和教学技能节点，方便你检查每段教学片段是否被正确结构化。
        </p>
      </div>

      <MetricCards snapshot={snapshot} />

      {snapshot.retrieval_health ? (
        <section className="mt-5 surface-card p-5">
          <div className="text-lg font-semibold tracking-tight">Retrieval 健康状态</div>
          <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
            当前图中可用于向量检索的节点数量，以及因 embedding 配置切换而标记为 stale 的向量数。
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Retrieval Nodes
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {snapshot.retrieval_health.total_nodes}
              </div>
            </div>
            <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Valid Vectors
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {snapshot.retrieval_health.valid_vectors}
              </div>
            </div>
            <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Stale Vectors
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {snapshot.retrieval_health.stale_vectors}
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {!hasMemory ? (
        <section className="mt-5 surface-card p-8">
          <div className="max-w-3xl">
            <div className="text-lg font-semibold tracking-tight">还没有记忆内容</div>
            <p className="mt-3 text-sm leading-7 text-[var(--muted-foreground)]">
              等你完成模型配置并开始真实对话之后，概念、学习片段和教学技能节点会逐步出现在这个工作台里。
            </p>
          </div>
        </section>
      ) : null}

      <MemoryGraphView snapshot={snapshot} />

      <section className="mt-5 surface-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold tracking-tight">Memory Flow 摘要</div>
            <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
              MemoryFlow 记录所有记忆系统状态变化事件，方便审计和回放。
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              总事件数
            </div>
            <div className="mt-2 text-2xl font-semibold">{eventCount}</div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Episode Created
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {countByType("episode_created")}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Concept Extracted
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {countByType("concept_extracted")}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Skill Evidence
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {countByType("skill_evidence_added")}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Skill Distilled
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {countByType("skill_distilled")}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Profile Updated
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {countByType("profile_updated")}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
