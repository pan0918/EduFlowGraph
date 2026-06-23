"use client";

import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { MetricCards } from "@/components/workspace/MetricCards";
import { formatSkillDisplay } from "@/lib/skill-display";

export function SkillsWorkspace() {
  const { snapshot } = useWorkspace();
  return (
    <div className="page-shell min-h-screen">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
          Space / 技能
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          技能工作台
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          这里展示从 Episode 中沉淀出来的可复用教学套路，以及它们的置信度和结果统计。
        </p>
      </div>

      <MetricCards snapshot={snapshot} />

      {snapshot.skills.length === 0 ? (
        <section className="mt-5 surface-card p-8">
          <div className="max-w-3xl">
            <div className="text-lg font-semibold tracking-tight">还没有技能沉淀</div>
            <p className="mt-3 text-sm leading-7 text-[var(--muted-foreground)]">
              技能节点现在不会再预置示例。等系统从真实事件流里抽取出有效教学轨迹之后，
              这里才会开始出现可复用的教学套路和它们的质量统计。
            </p>
          </div>
        </section>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        {snapshot.skills.map((skill) => {
          const display = formatSkillDisplay(skill);
          return (
            <section key={skill.node_id} className="surface-card p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-xl font-semibold tracking-tight">{display.name}</h2>
                  <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
                    {display.trigger}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <div className="rounded-full bg-sky-100 px-3 py-2 text-sm font-medium text-sky-900">
                    置信度 {(skill.quality?.confidence ?? 0).toFixed(2)}
                  </div>
                  <div className="rounded-full bg-[var(--secondary)] px-3 py-2 text-xs font-medium uppercase tracking-[0.18em] text-[var(--foreground)]">
                    {display.status}
                  </div>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <span className="rounded-full bg-amber-100 px-3 py-2 text-xs font-medium text-amber-900">
                  困难模式 {display.difficulty}
                </span>
                {display.teachingActions.map((action) => (
                  <span
                    key={`${skill.node_id}-${action}`}
                    className="rounded-full border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-medium text-[var(--foreground)]"
                  >
                    {action}
                  </span>
                ))}
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                    证据 Episodes
                  </div>
                  <div className="mt-2 text-2xl font-semibold">
                    {skill.quality?.support_episode_count ?? 0}
                  </div>
                </div>
                <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                    验证成功
                  </div>
                  <div className="mt-2 text-2xl font-semibold">
                    {skill.quality?.validation_success_count ?? 0}
                  </div>
                </div>
                <div className="rounded-2xl bg-[var(--secondary)]/60 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                    验证失败
                  </div>
                  <div className="mt-2 text-2xl font-semibold">
                    {skill.quality?.validation_fail_count ?? 0}
                  </div>
                </div>
              </div>

              {display.procedure.length ? (
                <div className="mt-5">
                  <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                    核心流程
                  </div>
                  <div className="mt-3 space-y-2">
                    {display.procedure.map((step, index) => (
                      <div key={`${skill.node_id}-${index}`} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm leading-6">
                        {step}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {display.successCriteria.length ? (
                <div className="mt-5">
                  <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                    成功标准
                  </div>
                  <div className="mt-3 space-y-2">
                    {display.successCriteria.map((criterion, index) => (
                      <div
                        key={`${skill.node_id}-criterion-${index}`}
                        className="rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm leading-6"
                      >
                        {criterion}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}
