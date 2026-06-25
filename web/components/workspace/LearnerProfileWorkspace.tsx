"use client";

import { useMemo } from "react";
import { useWorkspace } from "@/components/providers/WorkspaceProvider";
import { formatBeijingTime } from "@/lib/datetime";
import type {
  LearnerProfileSnapshot,
  ProfileModelEntry,
  ProfileModelName,
} from "@/lib/types";
import {
  Brain,
  Clock,
  Sparkles,
  Layers,
  HeartPulse,
  History,
  RefreshCw,
} from "lucide-react";

/* ──────────────────────── Model-level config ──────────────────────── */

interface ModelConfig {
  label: string;
  subtitle: string;
  icon: React.ElementType;
  headerBg: string;
  headerBorder: string;
  iconColor: string;
  chipBg: string;
  chipText: string;
  accentColor: string;
  emptyHint: string;
}

const MODEL_CONFIG: Record<ProfileModelName, ModelConfig> = {
  learner_model: {
    label: "学习者画像",
    subtitle: "长期认知画像 — 稳定特征与待验证假设",
    icon: Brain,
    headerBg: "bg-amber-50/80",
    headerBorder: "border-amber-100",
    iconColor: "text-amber-600",
    chipBg: "bg-amber-50",
    chipText: "text-amber-800",
    accentColor: "bg-amber-400",
    emptyHint: "跨多轮学习后，这里会沉淀稳定的认知特征；单次“懂了”不会直接记为已掌握。",
  },
  context_model: {
    label: "情境画像",
    subtitle: "当前场景 — 任务、阶段与情绪",
    icon: Clock,
    headerBg: "bg-violet-50/80",
    headerBorder: "border-violet-100",
    iconColor: "text-violet-500",
    chipBg: "bg-violet-50",
    chipText: "text-violet-800",
    accentColor: "bg-violet-400",
    emptyHint: "每轮对话轻量刷新，仅记录当前任务、学习阶段和情绪——不含认知诊断。",
  },
};

const MODEL_ORDER: ProfileModelName[] = ["learner_model", "context_model"];

/* ──────────────────────── Helpers ──────────────────────── */

function fmtTime(value?: string | null) {
  return formatBeijingTime(value);
}

function populatedCount(profile: LearnerProfileSnapshot): number {
  if (!profile?.models) return 0;
  return MODEL_ORDER.filter((m) => profile.models[m]?.summary?.trim()).length;
}

/* ──────────────────────── Components ──────────────────────── */

function ModelCard({
  modelName,
  entry,
}: {
  modelName: ProfileModelName;
  entry: ProfileModelEntry | undefined;
}) {
  const cfg = MODEL_CONFIG[modelName];
  const Icon = cfg.icon;
  const summary = entry?.summary?.trim() ?? "";
  const ts = fmtTime(entry?.updated_at);
  const revisions = entry?.revisions ?? 0;

  return (
    <section className="surface-card flex flex-col overflow-hidden">
      <div className={`${cfg.headerBg} border-b ${cfg.headerBorder} px-6 py-4`}>
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${cfg.chipBg}`}
          >
            <Icon className={`h-5 w-5 ${cfg.iconColor}`} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">
                {cfg.label}
              </h2>
              {revisions > 0 && (
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-none ${cfg.chipBg} ${cfg.chipText}`}
                >
                  <RefreshCw className="h-2.5 w-2.5" />
                  {revisions}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
              {cfg.subtitle}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col px-6 py-5">
        {summary ? (
          <p className="text-sm leading-7 text-[var(--foreground)]">{summary}</p>
        ) : (
          <div className="flex flex-1 items-center justify-center py-6">
            <p className="text-center text-xs leading-6 text-[var(--muted-foreground)]">
              {cfg.emptyHint}
            </p>
          </div>
        )}

        {summary && (
          <div className="mt-4 flex items-center justify-between border-t border-[var(--border)] pt-3 text-[11px] text-[var(--muted-foreground)]">
            <span>{summary.length} 字</span>
            {ts && <span>更新于 {ts}</span>}
          </div>
        )}
      </div>
    </section>
  );
}

/* ──────────────────────── Main ──────────────────────── */

export function LearnerProfileWorkspace() {
  const { snapshot } = useWorkspace();
  const { profile } = snapshot;

  const populated = useMemo(() => populatedCount(profile), [profile]);
  const recentChanges = profile.recent_changes ?? [];
  const hasAny = populated > 0;

  return (
    <div className="page-shell min-h-screen">
      {/* Header */}
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted-foreground)]">
          空间 / 画像
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">学习者画像</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          沉淀学习者的长期认知特征与当前学习情境；Skill 适配证据已移至技能工作台，作为检索与重排依据单独维护。
        </p>
      </div>

      {/* Summary Metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <section className="surface-card p-5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-[var(--muted-foreground)]" />
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              已建立画像
            </span>
          </div>
          <div className="mt-2 text-3xl font-semibold">{populated}/2</div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">
            含内容的画像段落
          </div>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-[var(--muted-foreground)]" />
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              累计改写
            </span>
          </div>
          <div className="mt-2 text-3xl font-semibold">
            {profile.revision_count}
          </div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">
            画像更新次数
          </div>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-[var(--muted-foreground)]" />
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              最近更新
            </span>
          </div>
          <div className="mt-2 truncate text-lg font-semibold">
            {fmtTime(profile.updated_at) ?? "尚未更新"}
          </div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">
            最后一次画像改写
          </div>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center gap-2">
            <HeartPulse className="h-4 w-4 text-[var(--muted-foreground)]" />
            <span className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              健康状态
            </span>
          </div>
          <div className="mt-2 text-3xl font-semibold">
            {profile.health.status}
          </div>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">
            {profile.health.message || "运行正常"}
          </div>
        </section>
      </div>

      {/* Content */}
      {!hasAny ? (
        <section className="surface-card mt-6 p-12">
          <div className="mx-auto flex max-w-lg flex-col items-center text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--secondary)]">
              <Sparkles className="h-7 w-7 text-[var(--primary)]" />
            </div>
            <h2 className="mt-5 text-xl font-semibold tracking-tight">
              还没有学习画像
            </h2>
            <p className="mt-3 max-w-md text-sm leading-7 text-[var(--muted-foreground)]">
              系统会从真实教学对话中持续提炼学习者画像和情境画像；教学程序与适配证据保存在技能工作台中。
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {MODEL_ORDER.map((m) => {
                const cfg = MODEL_CONFIG[m];
                const Icon = cfg.icon;
                return (
                  <span
                    key={m}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${cfg.chipBg} ${cfg.chipText}`}
                  >
                    <Icon className="h-3 w-3" />
                    {cfg.label}
                  </span>
                );
              })}
            </div>
          </div>
        </section>
      ) : (
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {MODEL_ORDER.map((m) => (
            <ModelCard key={m} modelName={m} entry={profile.models?.[m]} />
          ))}
        </div>
      )}

      {/* Recent changes */}
      {recentChanges.length > 0 && (
        <section className="surface-card mt-5 p-6">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-[var(--muted-foreground)]" />
            <h2 className="text-base font-semibold tracking-tight">最近变更</h2>
            <span className="text-xs text-[var(--muted-foreground)]">
              （最多保留 {recentChanges.length} 条）
            </span>
          </div>
          <ol className="mt-4 space-y-3">
            {recentChanges.map((change, i) => {
              const cfg = MODEL_CONFIG[change.model];
              return (
                <li
                  key={`${change.at ?? ""}-${i}`}
                  className="flex items-start gap-3"
                >
                  <span
                    className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${cfg?.chipBg ?? "bg-[var(--secondary)]"} ${cfg?.chipText ?? ""}`}
                  >
                    {cfg?.label ?? change.model}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm leading-6 text-[var(--foreground)]">
                      {change.note}
                    </p>
                    {fmtTime(change.at) && (
                      <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                        {fmtTime(change.at)}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}
