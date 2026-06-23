"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  BrainCircuit,
  ChevronDown,
  Database,
  Gauge,
  Loader2,
  SendHorizonal,
  Trash2,
} from "lucide-react";
import {
  useActiveWorkspaceModels,
  useWorkspace,
} from "@/components/providers/WorkspaceProvider";
import { AssistantMarkdown } from "@/components/common/AssistantMarkdown";
import {
  formatReasoningForPanel,
  summarizeRetrieval,
  summarizeUsage,
} from "@/components/workspace/chat-trace-utils";
import { formatSkillDisplay } from "@/lib/skill-display";
import type { RetrievedContext } from "@/lib/types";

type RuntimePicker = "llm" | "embedding" | null;

const ConversationTracePanel = memo(function ConversationTracePanel({
  reasoning,
  retrieval,
  usage,
  streaming,
}: {
  reasoning?: string;
  retrieval?: RetrievedContext | null;
  usage?: Record<string, unknown>;
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const usageSummary = summarizeUsage(usage);
  const retrievalSummary = summarizeRetrieval(retrieval);
  const reasoningPanel = open ? formatReasoningForPanel(reasoning) : null;
  const conceptCount = retrievalSummary?.conceptCount ?? 0;
  const episodeCount = retrievalSummary?.episodeCount ?? 0;
  const skillCount = retrievalSummary?.skillCount ?? 0;
  const hasReasoning = Boolean(reasoning);
  const hasRetrieval = Boolean(retrievalSummary?.hasContext);
  const hasRetrievalHits = Boolean(retrievalSummary?.totalCount);
  const hasUsage = Boolean(usageSummary);
  const hasTrace = hasReasoning || hasRetrieval || hasUsage || streaming;

  if (!hasTrace) return null;

  const cacheLabel =
    usageSummary && usageSummary.promptTokens > 0
      ? `${usageSummary.cachedTokens}/${usageSummary.promptTokens} cached`
      : "等待 usage";
  const cacheRate =
    usageSummary && usageSummary.promptTokens > 0
      ? `${Math.round(usageSummary.cacheHitRate * 100)}%`
      : "0%";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)]/70 text-sm text-[var(--muted-foreground)]">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--secondary)] px-2.5 py-1 text-xs font-medium text-[var(--foreground)]">
            {streaming ? <Loader2 className="h-3 w-3 animate-spin" /> : <BrainCircuit className="h-3 w-3" />}
            {hasReasoning ? "思考已记录" : streaming ? "正在思考" : "思考"}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--secondary)]/70 px-2.5 py-1 text-xs">
            <Database className="h-3 w-3" />
            {conceptCount} 概念 · {episodeCount} 片段 · {skillCount} 技能
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--secondary)]/70 px-2.5 py-1 text-xs">
            <Gauge className="h-3 w-3" />
            缓存 {cacheRate}
          </span>
        </div>
        <ChevronDown
          className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <div className="space-y-4 border-t border-[var(--border)] px-4 py-4">
          <section>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--foreground)]">
              思考过程
            </div>
            {hasReasoning ? (
              <>
                <div className="mt-2 max-h-[260px] overflow-y-auto rounded-lg bg-[var(--background)] px-3 py-2">
                  <AssistantMarkdown content={reasoningPanel?.content ?? ""} />
                </div>
                {reasoningPanel?.truncated ? (
                  <p className="mt-2 text-[11px] leading-5">
                    原始思考约 {reasoningPanel.originalLength.toLocaleString()} 字符，已截断展示以保持展开流畅。
                  </p>
                ) : null}
              </>
            ) : (
              <p className="mt-2 text-xs">当前模型没有返回 reasoning 字段。</p>
            )}
          </section>

          <section>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--foreground)]">
              记忆检索
            </div>
            {hasRetrievalHits ? (
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                <TraceList
                  title="Concepts"
                  items={retrieval?.concepts.map((item) => item.name) ?? []}
                />
                <TraceList
                  title="Episodes"
                  items={retrieval?.episodes.map((item) => item.title) ?? []}
                />
                <TraceList
                  title="Skills"
                  items={retrieval?.skills.map((item) => formatSkillDisplay(item).name) ?? []}
                />
              </div>
            ) : (
              <p className="mt-2 text-xs">
                这轮已执行记忆检索，但没有命中可展示的记忆节点。
              </p>
            )}
            {retrievalSummary ? (
              <div className="mt-2 grid gap-2 text-xs md:grid-cols-4">
                <TraceMetric label="Concept hits" value={retrievalSummary.conceptHits} />
                <TraceMetric label="Episode hits" value={retrievalSummary.episodeHits} />
                <TraceMetric label="Skill hits" value={retrievalSummary.skillHits} />
                <TraceMetric label="Stale vectors" value={retrievalSummary.staleVectors} />
              </div>
            ) : null}
          </section>

          <section>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--foreground)]">
              缓存与 Token
            </div>
            {usageSummary ? (
              <div className="mt-2 grid gap-2 text-xs md:grid-cols-4">
                <TraceMetric label="Prompt" value={usageSummary.promptTokens} />
                <TraceMetric label="Completion" value={usageSummary.completionTokens} />
                <TraceMetric label="Total" value={usageSummary.totalTokens} />
                <TraceMetric label={cacheLabel} value={usageSummary.cachedTokens} />
              </div>
            ) : (
              <p className="mt-2 text-xs">
                当前 provider 没有返回 usage，或接口不支持流式 usage。
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
});

function TraceList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg bg-[var(--background)] px-3 py-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
        {title}
      </div>
      <div className="mt-2 space-y-1">
        {items.slice(0, 3).map((item) => (
          <div key={item} className="line-clamp-2 text-xs leading-5 text-[var(--foreground)]">
            {item}
          </div>
        ))}
        {items.length === 0 ? <div className="text-xs">无</div> : null}
      </div>
    </div>
  );
}

function TraceMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-[var(--background)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.14em]">{label}</div>
      <div className="mt-1 text-base font-semibold text-[var(--foreground)]">
        {value.toLocaleString()}
      </div>
    </div>
  );
}

export function ChatWorkspace() {
  const {
    settings,
    messages,
    sessions,
    context,
    loading,
    lastError,
    sendMessage,
    deleteMessage,
    updateSettings,
  } = useWorkspace();
  const { llmModel, embeddingModel } = useActiveWorkspaceModels();
  const [draft, setDraft] = useState("");
  const [openPicker, setOpenPicker] = useState<RuntimePicker>(null);
  const currentSession = sessions.find(
    (session) => session.id === settings.sessionId,
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  // Whether to keep the view pinned to the newest message. Turns off when the
  // user scrolls up to read history, so we never yank them back down.
  const autoFollowRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    autoFollowRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  // Follow new content (sent message + streaming reply) only while pinned.
  useEffect(() => {
    if (!autoFollowRef.current) return;
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Jump to the bottom when switching sessions.
  useEffect(() => {
    autoFollowRef.current = true;
    scrollToBottom();
  }, [settings.sessionId, scrollToBottom]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.closest("[data-runtime-picker-root='true']")) return;
      setOpenPicker(null);
    };
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, []);

  const llmChoices = settings.llmProfiles.flatMap((profile) =>
    profile.models.map((model) => ({
      key: `${profile.id}:${model.id}`,
      profileId: profile.id,
      modelId: model.id,
      label: model.label || model.modelId || "未命名模型",
      meta: profile.name,
    })),
  );

  const embeddingChoices = settings.embeddingProfiles.flatMap((profile) =>
    profile.models.map((model) => ({
      key: `${profile.id}:${model.id}`,
      profileId: profile.id,
      modelId: model.id,
      label: model.label || model.modelId || "未命名模型",
      meta: profile.name,
    })),
  );

  const submit = async () => {
    const text = draft.trim();
    if (!text || loading || !llmModel || !embeddingModel) return;
    setDraft("");
    // The user just sent a message: always snap to the newest content.
    autoFollowRef.current = true;
    requestAnimationFrame(scrollToBottom);
    await sendMessage(text);
  };

  const switchLlm = (profileId: string, modelId: string) => {
    updateSettings((current) => ({
      ...current,
      activeLlmProfileId: profileId,
      llmProfiles: current.llmProfiles.map((profile) =>
        profile.id === profileId ? { ...profile, activeModelId: modelId } : profile,
      ),
    }));
    setOpenPicker(null);
  };

  const switchEmbedding = (profileId: string, modelId: string) => {
    updateSettings((current) => ({
      ...current,
      activeEmbeddingProfileId: profileId,
      embeddingProfiles: current.embeddingProfiles.map((profile) =>
        profile.id === profileId ? { ...profile, activeModelId: modelId } : profile,
      ),
    }));
    setOpenPicker(null);
  };

  const switchMemoryMode = (memoryMode: "ordinary" | "memory_augmented") => {
    updateSettings((current) => ({
      ...current,
      memoryMode,
    }));
  };

  return (
    <div className="min-h-screen bg-[#fdfaf4] px-5 py-4 lg:px-7">
      <div className="mx-auto flex min-h-[calc(100vh-32px)] w-full max-w-[1160px] flex-col">
        <div className="mx-auto flex min-h-0 w-full max-w-[920px] flex-1 flex-col">
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-2 pb-7 pt-7"
          >
            {messages.length === 0 ? (
              <div className="flex min-h-full flex-col">
                <div className="text-center text-sm tracking-[0.12em] text-[var(--muted-foreground)]">
                  {currentSession?.title || "新对话"}
                </div>
                {lastError ? (
                  <div className="mt-8 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm leading-7 text-rose-700">
                    {lastError}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="space-y-6">
                {lastError ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm leading-7 text-rose-700">
                    {lastError}
                  </div>
                ) : null}

                {messages.map((message, index) => {
                  if (message.role === "student") {
                    return (
                      <section key={`${message.role}-${index}`} className="group flex justify-end">
                        <div className="flex items-start gap-2">
                          {message.eventId ? (
                            <button
                              onClick={() => void deleteMessage(message.eventId!)}
                              className="mt-3 inline-flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted-foreground)] opacity-0 transition hover:bg-[var(--accent)] hover:text-[var(--foreground)] group-hover:opacity-100"
                              aria-label="删除这条消息"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          ) : null}
                        <div className="max-w-[500px] rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-[13px] leading-6 text-[var(--foreground)] shadow-sm">
                          <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                            你
                          </div>
                          <div className="whitespace-pre-wrap">{message.content}</div>
                        </div>
                        </div>
                      </section>
                    );
                  }

                  return (
                    <section key={`${message.role}-${index}`} className="group space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                          {message.streaming && !message.content ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : null}
                          {message.streaming && !message.content ? "助手正在思考" : "助手回复"}
                        </div>
                        {message.eventId ? (
                          <button
                            onClick={() => void deleteMessage(message.eventId!)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[var(--muted-foreground)] opacity-0 transition hover:bg-[var(--accent)] hover:text-[var(--foreground)] group-hover:opacity-100"
                            aria-label="删除这条回复"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        ) : null}
                      </div>
                      <ConversationTracePanel
                        reasoning={message.reasoning}
                        retrieval={message.retrieval || (message.streaming ? context : null)}
                        usage={message.usage}
                        streaming={message.streaming}
                      />

                      {message.content ? (
                        <div className="relative">
                          <AssistantMarkdown content={message.content} />
                          {message.streaming ? (
                            <span className="ml-1 inline-block h-4 w-1 animate-pulse rounded-full bg-[var(--primary)] align-middle" />
                          ) : null}
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--primary)]" />
                          正在生成回答...
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </div>

          <div className="sticky bottom-0 bg-gradient-to-t from-[#fdfaf4] via-[#fdfaf4] to-transparent pb-4 pt-3">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 shadow-[0_18px_48px_rgba(80,58,35,0.08)]">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit();
                  }
                }}
                placeholder="今天我能帮你什么？"
                className="min-h-[74px] w-full resize-none bg-transparent text-[14px] leading-6 outline-none placeholder:text-[var(--muted-foreground)]"
                disabled={!llmModel || !embeddingModel}
              />
              <div className="mt-3 flex flex-wrap items-end justify-between gap-3 border-t border-[var(--border)]/70 pt-3">
                <div className="relative flex flex-wrap items-center gap-3">
                  <div className="inline-flex h-9 rounded-full border border-[var(--border)] bg-[var(--background)] p-1 text-xs">
                    <button
                      onClick={() => switchMemoryMode("ordinary")}
                      className={`rounded-full px-3 transition ${
                        settings.memoryMode === "ordinary"
                          ? "bg-[var(--secondary)] text-[var(--foreground)]"
                          : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      普通
                    </button>
                    <button
                      onClick={() => switchMemoryMode("memory_augmented")}
                      className={`rounded-full px-3 transition ${
                        settings.memoryMode === "memory_augmented"
                          ? "bg-[var(--secondary)] text-[var(--foreground)]"
                          : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      记忆增强
                    </button>
                  </div>

                  <div className="relative" data-runtime-picker-root="true">
                    <button
                      onClick={() =>
                        setOpenPicker((current) => (current === "llm" ? null : "llm"))
                      }
                      className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--background)] px-3 text-xs text-[var(--foreground)] transition hover:bg-[var(--accent)]"
                    >
                      {llmModel?.label || "选择 LLM"}
                      <ChevronDown className="h-4 w-4" />
                    </button>
                    {openPicker === "llm" ? (
                      <div className="absolute bottom-[calc(100%+10px)] left-0 z-20 min-w-[280px] rounded-[22px] border border-[var(--border)] bg-[var(--card)] p-2 shadow-[0_18px_48px_rgba(80,58,35,0.14)]">
                        {llmChoices.map((choice) => {
                          const active =
                            choice.profileId === settings.activeLlmProfileId &&
                            choice.modelId === llmModel?.id;
                          return (
                            <button
                              key={choice.key}
                              onClick={() => switchLlm(choice.profileId, choice.modelId)}
                              className={`flex w-full items-start justify-between rounded-2xl px-4 py-3 text-left transition ${
                                active
                                  ? "bg-[var(--secondary)] text-[var(--foreground)]"
                                  : "hover:bg-[var(--accent)]"
                              }`}
                            >
                              <div>
                                <div className="text-sm font-medium">{choice.label}</div>
                                <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                                  {choice.meta}
                                </div>
                              </div>
                              {active ? (
                                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-[var(--primary)]" />
                              ) : null}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>

                  <div className="relative" data-runtime-picker-root="true">
                    <button
                      onClick={() =>
                        setOpenPicker((current) =>
                          current === "embedding" ? null : "embedding",
                        )
                      }
                      className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--background)] px-3 text-xs text-[var(--foreground)] transition hover:bg-[var(--accent)]"
                    >
                      {embeddingModel?.label || "选择 Embedding"}
                      <ChevronDown className="h-4 w-4" />
                    </button>
                    {openPicker === "embedding" ? (
                      <div className="absolute bottom-[calc(100%+10px)] left-0 z-20 min-w-[320px] rounded-[22px] border border-[var(--border)] bg-[var(--card)] p-2 shadow-[0_18px_48px_rgba(80,58,35,0.14)]">
                        {embeddingChoices.map((choice) => {
                          const active =
                            choice.profileId === settings.activeEmbeddingProfileId &&
                            choice.modelId === embeddingModel?.id;
                          return (
                            <button
                              key={choice.key}
                              onClick={() =>
                                switchEmbedding(choice.profileId, choice.modelId)
                              }
                              className={`flex w-full items-start justify-between rounded-2xl px-4 py-3 text-left transition ${
                                active
                                  ? "bg-[var(--secondary)] text-[var(--foreground)]"
                                  : "hover:bg-[var(--accent)]"
                              }`}
                            >
                              <div>
                                <div className="text-sm font-medium">{choice.label}</div>
                                <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                                  {choice.meta}
                                </div>
                              </div>
                              {active ? (
                                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-[var(--primary)]" />
                              ) : null}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                </div>

                <button
                  onClick={() => void submit()}
                  disabled={loading || !llmModel || !embeddingModel}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--secondary)] text-[var(--foreground)] transition hover:bg-[var(--accent)] disabled:opacity-60"
                  aria-label={loading ? "思考中" : "发送"}
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
