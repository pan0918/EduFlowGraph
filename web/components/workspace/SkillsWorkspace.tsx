"use client";

import { useMemo, useState } from "react";
import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { formatBeijingTime } from "@/lib/datetime";
import { formatSkillDisplay } from "@/lib/skill-display";
import type { DashboardSnapshot, SkillNode } from "@/lib/types";
import {
  Activity,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  Clock3,
  History,
  Lightbulb,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

function skillEvidenceCount(skill: SkillNode): number {
  return (
    (skill.quality?.support_episode_count ?? 0) +
    (skill.quality?.validation_success_count ?? 0) +
    (skill.quality?.validation_fail_count ?? 0)
  );
}

function SkillStats({ snapshot }: { snapshot: DashboardSnapshot }) {
  const total = snapshot.skills.length;
  const candidateCount = snapshot.skills.filter(
    (skill) => skill.status === "candidate",
  ).length;
  const verifiedCount = snapshot.skills.filter(
    (skill) => (skill.quality?.validation_success_count ?? 0) > 0,
  ).length;
  const evidenceCount = snapshot.skills.reduce(
    (sum, skill) => sum + skillEvidenceCount(skill),
    0,
  );
  const cards = [
    { label: "技能总数", value: total, icon: Boxes },
    { label: "候选技能", value: candidateCount, icon: Sparkles },
    { label: "已验证技能", value: verifiedCount, icon: ShieldCheck },
    { label: "证据片段", value: evidenceCount, icon: Activity },
  ];

  return (
    <div className="grid gap-3 md:grid-cols-4">
      {cards.map(({ label, value, icon: Icon }) => (
        <section key={label} className="surface-card px-5 py-4">
          <div className="flex items-center gap-2 text-[var(--muted-foreground)]">
            <Icon className="h-4 w-4" />
            <span className="text-xs uppercase tracking-[0.18em]">{label}</span>
          </div>
          <div className="mt-2 text-3xl font-semibold tracking-tight">{value}</div>
        </section>
      ))}
    </div>
  );
}

function AdaptationEvidencePanel({ snapshot }: { snapshot: DashboardSnapshot }) {
  const adaptation = snapshot.skill_adaptation;
  const summary = adaptation?.summary?.trim() ?? "";
  const recentChanges = adaptation?.recent_changes ?? [];

  return (
    <section className="surface-card p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <BadgeCheck className="h-4 w-4 text-amber-600" />
            <h2 className="text-base font-semibold tracking-tight">
              技能适配证据
            </h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
            用于 Skill 重排、过滤与个性化召回，不写入用户画像。
          </p>
        </div>
        {adaptation?.revisions ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
            <History className="h-3 w-3" />
            {adaptation.revisions}
          </span>
        ) : null}
      </div>

      {summary ? (
        <div className="mt-4 rounded-lg border border-amber-100 bg-amber-50/55 p-4 text-sm leading-7 text-[var(--foreground)]">
          {summary}
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-dashed border-[var(--border)] bg-[var(--secondary)]/50 p-4 text-sm leading-7 text-[var(--muted-foreground)]">
          还没有可用于 Skill 召回的稳定适配证据。
        </div>
      )}

      <div className="mt-4 grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-1">
        <div className="rounded-lg bg-[var(--secondary)]/70 p-3">
          <div className="text-[var(--muted-foreground)]">最近更新</div>
          <div className="mt-1 font-medium">
            {formatBeijingTime(adaptation?.updated_at) ?? "尚未更新"}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--secondary)]/70 p-3">
          <div className="text-[var(--muted-foreground)]">健康状态</div>
          <div className="mt-1 font-medium">
            {adaptation?.health?.message || adaptation?.health?.status || "ok"}
          </div>
        </div>
      </div>

      {recentChanges.length ? (
        <div className="mt-5 border-t border-[var(--border)] pt-4">
          <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            <Clock3 className="h-3.5 w-3.5" />
            最近变更
          </div>
          <div className="space-y-3">
            {recentChanges.slice(0, 4).map((change, index) => (
              <div key={`${change.at ?? ""}-${index}`} className="text-sm">
                <div className="leading-6 text-[var(--foreground)]">
                  {change.note}
                </div>
                <div className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                  {formatBeijingTime(change.at) ?? "时间未记录"}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function RecallSuggestionPanel() {
  const suggestions = [
    { tone: "border-amber-200 bg-amber-50 text-amber-900", text: "优先召回：与当前困难模式匹配且验证成功的 Skill" },
    { tone: "border-sky-200 bg-sky-50 text-sky-900", text: "保留：带有反馈验证或迁移检查的 Skill" },
    { tone: "border-rose-200 bg-rose-50 text-rose-900", text: "避免：只有完整讲解步骤、缺少学习状态证据的内容" },
    { tone: "border-emerald-200 bg-emerald-50 text-emerald-900", text: "可提高：跨主题成功复用过的 Skill" },
  ];
  return (
    <section className="surface-card p-6">
      <div className="flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-[var(--muted-foreground)]" />
        <h2 className="text-base font-semibold tracking-tight">召回建议</h2>
      </div>
      <div className="mt-4 space-y-2">
        {suggestions.map((item) => (
          <div
            key={item.text}
            className={`rounded-lg border px-3 py-2 text-sm leading-6 ${item.tone}`}
          >
            {item.text}
          </div>
        ))}
      </div>
    </section>
  );
}

function SkillCard({ skill }: { skill: SkillNode }) {
  const display = formatSkillDisplay(skill);
  const confidence = skill.quality?.confidence ?? 0;
  return (
    <section className="surface-card p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight">
              {display.name}
            </h2>
            <span className="rounded-full bg-[var(--secondary)] px-2.5 py-1 text-xs font-medium uppercase tracking-[0.14em]">
              {display.status}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
            {display.trigger}
          </p>
        </div>
        <div className="shrink-0 rounded-lg bg-sky-50 px-3 py-2 text-sm font-medium text-sky-900">
          置信度 {confidence.toFixed(2)}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900">
          {display.difficulty}
        </span>
        {display.teachingActions.map((action) => (
          <span
            key={`${skill.node_id}-${action}`}
            className="rounded-full border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-medium"
          >
            {action}
          </span>
        ))}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-[var(--secondary)]/60 p-3">
          <div className="text-xs text-[var(--muted-foreground)]">证据</div>
          <div className="mt-1 text-2xl font-semibold">
            {skill.quality?.support_episode_count ?? 0}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--secondary)]/60 p-3">
          <div className="text-xs text-[var(--muted-foreground)]">成功</div>
          <div className="mt-1 text-2xl font-semibold">
            {skill.quality?.validation_success_count ?? 0}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--secondary)]/60 p-3">
          <div className="text-xs text-[var(--muted-foreground)]">失败</div>
          <div className="mt-1 text-2xl font-semibold">
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
            {display.procedure.slice(0, 4).map((step, index) => (
              <div
                key={`${skill.node_id}-${index}`}
                className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm leading-6"
              >
                {index + 1}. {step}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {display.successCriteria.length ? (
        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            <CheckCircle2 className="h-3.5 w-3.5" />
            成功标准
          </div>
          <div className="flex flex-wrap gap-2">
            {display.successCriteria.map((criterion, index) => (
              <span
                key={`${skill.node_id}-criterion-${index}`}
                className="rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-900"
              >
                {criterion}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function SkillsWorkspace() {
  const { snapshot } = useWorkspace();
  const [query, setQuery] = useState("");

  const filteredSkills = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return snapshot.skills;
    return snapshot.skills.filter((skill) => {
      const display = formatSkillDisplay(skill);
      const haystack = [
        display.name,
        display.trigger,
        display.difficulty,
        ...display.teachingActions,
        ...display.procedure,
        ...display.successCriteria,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [query, snapshot.skills]);

  return (
    <div className="page-shell min-h-screen">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
            Space / 技能
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            技能工作台
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
            展示可复用教学技能，并用独立适配证据支持 Skill 的检索、重排与召回。
          </p>
        </div>
        <label className="relative block w-full max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-11 w-full rounded-lg border border-[var(--border)] bg-[var(--card)] pl-10 pr-4 text-sm outline-none transition focus:border-[var(--primary)] focus:ring-2 focus:ring-[var(--primary)]/15"
            placeholder="搜索技能、证据或困难模式"
          />
        </label>
      </div>

      <SkillStats snapshot={snapshot} />

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div>
          {snapshot.skills.length === 0 ? (
            <section className="surface-card p-8">
              <div className="max-w-3xl">
                <div className="text-lg font-semibold tracking-tight">
                  还没有技能沉淀
                </div>
                <p className="mt-3 text-sm leading-7 text-[var(--muted-foreground)]">
                  等系统从真实事件流里抽取出有效教学轨迹后，这里会出现可复用的教学技能与质量统计。
                </p>
              </div>
            </section>
          ) : filteredSkills.length === 0 ? (
            <section className="surface-card p-8 text-sm text-[var(--muted-foreground)]">
              没有匹配当前搜索条件的技能。
            </section>
          ) : (
            <div className="grid gap-5">
              {filteredSkills.map((skill) => (
                <SkillCard key={skill.node_id} skill={skill} />
              ))}
            </div>
          )}
        </div>

        <aside className="space-y-5">
          <AdaptationEvidencePanel snapshot={snapshot} />
          <RecallSuggestionPanel />
        </aside>
      </div>
    </div>
  );
}
