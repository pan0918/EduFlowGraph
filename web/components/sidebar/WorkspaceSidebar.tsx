"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Brain,
  LayoutGrid,
  MessageSquare,
  Settings2,
  Sparkles,
} from "lucide-react";
import { useWorkspace } from "@/components/providers/WorkspaceProvider";

const navItems = [
  { href: "/chat", label: "聊天", icon: MessageSquare },
  { href: "/knowledge", label: "知识库", icon: BookOpen },
  { href: "/space/memory", label: "记忆", icon: Brain },
  { href: "/space/skills", label: "技能", icon: Sparkles },
  { href: "/settings", label: "设置", icon: Settings2 },
];

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const { settings, sessions, switchSession } = useWorkspace();
  const isChatPage = pathname === "/chat" || pathname.startsWith("/chat/");

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-[var(--border)] bg-[#f3ecdf] px-4 py-4 lg:h-screen lg:w-[252px] lg:border-b-0 lg:border-r">
      <div className="mb-6 flex items-center gap-3 px-2">
        <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-[var(--primary)] text-[var(--primary-foreground)] shadow-surface">
          <LayoutGrid className="h-5 w-5" />
        </div>
        <div>
          <div className="font-semibold tracking-tight text-[var(--foreground)]">
            EduFlowGraph
          </div>
          <div className="text-xs text-[var(--muted-foreground)]">个性化导师</div>
        </div>
      </div>

      <div className="px-1 py-1">
        <nav className="space-y-1.5">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            const isChat = href === "/chat";

            return (
              <div key={href} className="space-y-1.5">
                <Link
                  href={href}
                  className={`flex items-center gap-3 rounded-2xl px-3 py-3 text-sm transition ${
                    active
                      ? "bg-[var(--secondary)] text-[var(--foreground)]"
                      : "text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{label}</span>
                </Link>

                {isChat && isChatPage ? (
                  <div className="space-y-1 pl-3">
                    {sessions.map((session) => {
                      const current = session.id === settings.sessionId;
                      return (
                        <button
                          key={session.id}
                          onClick={() => switchSession(session.id)}
                          className={`w-full rounded-2xl px-3 py-3 text-left transition ${
                            current
                              ? "bg-[#efe6d8] text-[var(--foreground)]"
                              : "text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)]"
                          }`}
                        >
                          <div className="line-clamp-1 text-sm font-medium">
                            {session.title}
                          </div>
                          <div className="mt-1 text-xs text-[var(--muted-foreground)]">
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
    </aside>
  );
}
