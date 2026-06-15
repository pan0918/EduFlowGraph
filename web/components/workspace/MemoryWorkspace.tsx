"use client";

import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { MemoryGraphView } from "@/components/workspace/MemoryGraphView";
import { MetricCards } from "@/components/workspace/MetricCards";

export function MemoryWorkspace() {
  const { snapshot } = useWorkspace();
  const hasMemory =
    snapshot.concepts.length > 0 ||
    snapshot.episodes.length > 0 ||
    snapshot.skills.length > 0 ||
    snapshot.events.length > 0;
  return (
    <div className="min-h-screen bg-[var(--background)] px-8 py-7">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
          空间 / 记忆
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          记忆工作台
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          这里把当前 append-only DataFlow 和自动抽取出的 episode node 摊开看，方便你检查每段教学片段是否被正确结构化。
        </p>
      </div>

      <MetricCards snapshot={snapshot} />

      {snapshot.retrieval_health ? (
        <section className="mt-5 surface-card p-5">
          <div className="text-lg font-semibold tracking-tight">Retrieval 健康状态</div>
          <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
            这里显示当前图中可用于向量检索的节点数量，以及因为 embedding 配置切换而被标记为 stale 的向量数。
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
              这里不会再预放测试节点、测试边或示例轨迹。等你完成模型配置并开始真实对话之后，
              episode 节点和事件流会逐步出现在这个工作台里。
            </p>
          </div>
        </section>
      ) : null}

      <MemoryGraphView snapshot={snapshot} />

      <section className="mt-5 surface-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold tracking-tight">抽取状态摘要</div>
            <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
              这里展示当前 episode 抽取链路的核心计数，方便快速判断自动抽取是否稳定运行。
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Closed Segments
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "segment_closed").length}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Extraction Completed
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "episode_extraction_completed").length}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Extraction Failed
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "episode_extraction_failed").length}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Skill Evidence
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "skill_evidence_recorded").length}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Skill Distilled
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "skill_distillation_completed").length}
            </div>
          </div>
          <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Skill Validation
            </div>
            <div className="mt-2 text-2xl font-semibold">
              {snapshot.events.filter((event) => event.event_type === "skill_validation_recorded").length}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
