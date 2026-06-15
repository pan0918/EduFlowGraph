import type { DashboardSnapshot } from "@/lib/types";

export function MetricCards({ snapshot }: { snapshot: DashboardSnapshot }) {
  const cards = [
    ["事件流", snapshot.events.length],
    ["概念节点", snapshot.concepts.length],
    ["片段节点", snapshot.episodes.length],
    ["技能节点", snapshot.skills.length],
  ];
  return (
    <div className="grid gap-3 md:grid-cols-4">
      {cards.map(([label, value]) => (
        <div key={label} className="surface-card px-4 py-4">
          <div className="text-3xl font-semibold tracking-tight">{value}</div>
          <div className="mt-1 text-sm text-[var(--muted-foreground)]">{label}</div>
        </div>
      ))}
    </div>
  );
}
