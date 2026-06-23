"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Brain,
  Eraser,
  LayoutGrid,
  MessageSquare,
  Plus,
  Settings2,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useWorkspace } from "@/components/providers/WorkspaceProvider";

const navItems = [
  { href: "/chat", label: "聊天", icon: MessageSquare },
  { href: "/knowledge", label: "知识库", icon: BookOpen },
  { href: "/space/memory", label: "记忆", icon: Brain },
  { href: "/space/profile", label: "画像", icon: UserRound },
  { href: "/space/skills", label: "技能", icon: Sparkles },
  { href: "/settings", label: "设置", icon: Settings2 },
];

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const { settings, sessions, switchSession, startNewSession, resetMemory, loading } =
    useWorkspace();
  const isChatPage = pathname === "/chat" || pathname.startsWith("/chat/");

  const clearAll = async () => {
    if (!window.confirm("清空当前 DataFlow、Memory Graph 和所有对话记录？")) return;
    await resetMemory();
  };

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-[var(--border)] bg-gradient-to-b from-[#f5ede0] to-[#f0e8da] px-4 py-4 lg:h-screen lg:w-[260px] lg:border-b-0 lg:border-r">
      <div className="mb-5 flex items-center gap-3 px-2">
        <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-[0_6px_20px_rgba(176,80,30,0.25)]">
          <LayoutGrid className="h-5 w-5" />
        </div>
        <div>
          <div className="font-semibold tracking-tight text-[var(--foreground)]">
            EduFlowGraph
          </div>
          <div className="text-[11px] tracking-wide text-[var(--muted-foreground)]">个性化导师系统</div>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2 px-1">
        <button
          onClick={startNewSession}
          className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--primary)] px-3 text-xs font-medium text-[var(--primary-foreground)] shadow-[0_4px_14px_rgba(176,80,30,0.22)] transition hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          新对话
        </button>
        <button
          onClick={() => void clearAll()}
          disabled={loading}
          title="清空记忆"
          aria-label="清空记忆"
          className="inline-flex h-9 items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 text-xs font-medium text-[var(--muted-foreground)] transition hover:bg-[var(--accent)] hover:text-[var(--foreground)] disabled:opacity-60"
        >
          <Eraser className="h-4 w-4" />
        </button>
      </div>

      <div className="px-1 py-1">
        <nav className="space-y-1">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            const isChat = href === "/chat";

            return (
              <div key={href} className="space-y-1">
                <Link
                  href={href}
                  className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-all ${
                    active
                      ? "bg-[var(--card)] text-[var(--foreground)] shadow-[0_2px_8px_rgba(54,45,36,0.06)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{label}</span>
                </Link>

                {isChat && isChatPage ? (
                  <div className="space-y-0.5 pl-3">
                    {sessions.map((session) => {
                      const current = session.id === settings.sessionId;
                      return (
                        <button
                          key={session.id}
                          onClick={() => switchSession(session.id)}
                          className={`w-full rounded-xl px-3 py-2 text-left transition-all ${
                            current
                              ? "bg-[var(--accent)] text-[var(--foreground)]"
                              : "text-[var(--muted-foreground)] hover:bg-[var(--accent)]/60 hover:text-[var(--foreground)]"
                          }`}
                        >
                          <div className="line-clamp-1 text-[13px] font-medium">
                            {session.title}
                          </div>
                          <div className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                            {session.messageCount > 0
                              ? `${session.messageCount} 条消息`
                              : "空白会话"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto px-3 pt-4">
        <div className="rounded-2xl bg-[var(--accent)]/60 px-3 py-2.5 text-[11px] leading-4 text-[var(--muted-foreground)]">
          Memory Graph · Profile · Retrieval
        </div>
      </div>
    </aside>
  );
}
