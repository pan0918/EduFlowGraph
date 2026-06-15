import type { RetrievedContext } from "@/lib/types";
import { formatSkillDisplay } from "@/lib/skill-display";

export function ContextRail({ context }: { context: RetrievedContext | null }) {
  return (
    <aside className="w-full shrink-0 space-y-4 border-t border-[var(--border)] pt-6 xl:max-w-[360px] xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
      <div>
        <h3 className="text-lg font-semibold tracking-tight">个性化上下文</h3>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          回答前检索到的学习状态、关键 Episode 和可复用教学技能。
        </p>
      </div>
      {!context ? (
        <div className="surface-card p-4 text-sm text-[var(--muted-foreground)]">
          先和导师聊一句，这里就会出现对应的记忆检索结果。
        </div>
      ) : null}
      {context?.concepts.map((concept) => (
        <div key={concept.node_id} className="rounded-3xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-sm">
          <div className="text-base font-semibold">{concept.name}</div>
          {concept.aliases?.length ? (
            <div className="mt-1 text-xs text-[var(--muted-foreground)]">
              {concept.aliases.slice(0, 3).join(" · ")}
            </div>
          ) : null}
          <p className="mt-3 text-sm leading-6 text-[var(--foreground)]">
            {concept.description || "该概念当前只记录了概念本体，后续会逐步补充说明。"}
          </p>
        </div>
      ))}
      {context?.episodes.length ? (
        <div className="surface-card p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            相关学习片段
          </div>
          <div className="mt-3 space-y-3">
            {context.episodes.map((episode) => (
              <div key={episode.node_id} className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
                <div className="font-medium">{episode.summary.title}</div>
                <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                  {episode.episode_type} | {episode.node_id}
                </div>
                <div className="mt-2 text-sm leading-6 text-[var(--foreground)]">
                  {episode.summary.short_summary}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {context?.skills.length ? (
        <div className="surface-card p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            教学技能建议
          </div>
          <div className="mt-3 space-y-3">
            {context.skills.map((skill) => {
              const display = formatSkillDisplay(skill);
              return (
              <div key={skill.node_id} className="rounded-2xl border border-[var(--border)] bg-[var(--secondary)]/50 p-3">
                <div className="font-medium">{display.name}</div>
                <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                  {display.status} | {display.difficulty}
                </div>
                <div className="mt-2 text-sm leading-6 text-[var(--foreground)]">
                  {display.trigger}
                </div>
                {display.procedure.length ? (
                  <div className="mt-2 text-xs leading-6 text-[var(--muted-foreground)]">
                    {display.procedure.slice(0, 2).join(" / ")}
                  </div>
                ) : null}
              </div>
              );
            })}
          </div>
        </div>
      ) : null}
      {context?.memory_context_pack ? (
        <div className="surface-card p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            Context Pack
          </div>
          <pre className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--foreground)]">
            {context.memory_context_pack}
          </pre>
        </div>
      ) : null}
    </aside>
  );
}
