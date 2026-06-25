"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  composeMessages,
  turnsToMessages,
  type ChatMessage,
  type ChatSessionSummary,
  type TurnRecord,
} from "@/components/providers/workspace-session-utils";
import type {
  DashboardSnapshot,
  DiagnosticResult,
  RetrievedContext,
  RuntimeConfig,
  WorkspaceSettings,
} from "@/lib/types";
import {
  buildRuntimeConfig,
  DEFAULT_SETTINGS,
  getActiveEmbeddingModel,
  getActiveEmbeddingProfile,
  getActiveLlmModel,
  getActiveLlmProfile,
  getActiveRerankerModel,
  getActiveRerankerProfile,
  normalizeSettings,
} from "@/lib/runtime";

interface DiagnosticsState {
  llm: DiagnosticResult | null;
  embedding: DiagnosticResult | null;
  reranker: DiagnosticResult | null;
  loading: "llm" | "embedding" | "reranker" | null;
}

interface WorkspaceContextValue {
  settings: WorkspaceSettings;
  snapshot: DashboardSnapshot;
  messages: ChatMessage[];
  sessions: ChatSessionSummary[];
  context: RetrievedContext | null;
  loading: boolean;
  backendHealthy: boolean;
  runtime: RuntimeConfig | null;
  runtimeError: string | null;
  diagnostics: DiagnosticsState;
  lastError: string | null;
  refreshDashboard: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  deleteMessage: (eventId: string) => Promise<void>;
  resetMemory: () => Promise<void>;
  forceExtract: () => Promise<void>;
  startNewSession: () => void;
  switchSession: (sessionId: string) => void;
  runDiagnostic: (kind: "llm" | "embedding" | "reranker") => Promise<void>;
  rebuildRetrieval: () => Promise<void>;
  updateSettings: (
    updater:
      | WorkspaceSettings
      | ((current: WorkspaceSettings) => WorkspaceSettings),
  ) => void;
  clearLastError: () => void;
}

const EMPTY_SNAPSHOT: DashboardSnapshot = {
  concepts: [],
  episodes: [],
  skills: [],
  edges: [],
  profile: {
    models: {
      learner_model: { summary: "", updated_at: null, revisions: 0 },
      context_model: { summary: "", updated_at: null, revisions: 0 },
    },
    recent_changes: [],
    updated_at: null,
    revision_count: 0,
    health: { status: "ok", message: "" },
  },
  skill_adaptation: {
    summary: "",
    updated_at: null,
    revisions: 0,
    recent_changes: [],
    health: { status: "ok", message: "" },
  },
  memory_flow_count: 0,
};

const EMPTY_DIAGNOSTICS: DiagnosticsState = {
  llm: null,
  embedding: null,
  reranker: null,
  loading: null,
};

const STORAGE_KEY = "eduflowgraph-workspace-settings";
const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
}

function makeSessionId(): string {
  return `session_${Date.now().toString(36)}`;
}

async function readJsonOrThrow<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  const text = await response.text();
  throw new Error(text || `请求失败（${response.status}）`);
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<WorkspaceSettings>(DEFAULT_SETTINGS);
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(EMPTY_SNAPSHOT);
  const [context, setContext] = useState<RetrievedContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsState>(EMPTY_DIAGNOSTICS);
  const [lastError, setLastError] = useState<string | null>(null);
  const [pendingMessages, setPendingMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionTurns, setSessionTurns] = useState<TurnRecord[]>([]);
  const sendSeqRef = useRef(0);

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      setSettings(normalizeSettings(JSON.parse(raw)));
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  const runtimeMemo = useMemo(() => {
    try {
      return {
        runtime: buildRuntimeConfig(settings),
        error: null,
      };
    } catch (error) {
      return {
        runtime: null,
        error: error instanceof Error ? error.message : "运行时配置解析失败。",
      };
    }
  }, [settings]);

  const refreshSessions = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase()}/api/sessions`, {
        cache: "no-store",
      });
      if (!response.ok) return;
      const data = await response.json();
      const serverSessions: ChatSessionSummary[] = (data.sessions || []).map(
        (s: { id: string; title: string; message_count: number; last_updated: string }) => ({
          id: s.id,
          title: s.title || "未命名对话",
          lastUpdated: s.last_updated || "",
          messageCount: s.message_count || 0,
        }),
      );
      const hasCurrentSession = serverSessions.some(
        (s) => s.id === settings.sessionId,
      );
      if (!hasCurrentSession) {
        serverSessions.unshift({
          id: settings.sessionId,
          title: "新对话",
          lastUpdated: "",
          messageCount: 0,
        });
      }
      setSessions(serverSessions);
    } catch {
      setSessions([
        {
          id: settings.sessionId,
          title: "新对话",
          lastUpdated: "",
          messageCount: 0,
        },
      ]);
    }
  }, [settings.sessionId]);

  const refreshSessionTurns = useCallback(async () => {
    try {
      const response = await fetch(
        `${apiBase()}/api/sessions/${encodeURIComponent(settings.sessionId)}/turns`,
        { cache: "no-store" },
      );
      if (!response.ok) {
        setSessionTurns([]);
        return;
      }
      const data = await response.json();
      setSessionTurns(data.turns || []);
    } catch {
      setSessionTurns([]);
    }
  }, [settings.sessionId]);

  const refreshDashboard = useCallback(async () => {
    const response = await fetch(`${apiBase()}/api/dashboard`, {
      cache: "no-store",
    });
    const data = await readJsonOrThrow<DashboardSnapshot>(response);
    setSnapshot(data);
  }, []);

  useEffect(() => {
    let active = true;
    async function boot() {
      try {
        const health = await fetch(`${apiBase()}/api/health`, {
          cache: "no-store",
        });
        if (active) {
          setBackendHealthy(health.ok);
        }
      } catch {
        if (active) setBackendHealthy(false);
      }
      await Promise.allSettled([
        refreshDashboard().catch(() => {}),
        refreshSessions(),
        refreshSessionTurns(),
      ]);
    }
    void boot();
    const timer = window.setInterval(() => {
      void refreshDashboard().catch(() => {
        setBackendHealthy(false);
      });
    }, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    void refreshSessionTurns();
    void refreshSessions();
  }, [settings.sessionId, refreshSessionTurns, refreshSessions]);

  const persistedMessages = useMemo(
    () => turnsToMessages(sessionTurns),
    [sessionTurns],
  );

  const sendMessage = async (message: string) => {
    // Each send gets a monotonically increasing generation id. Only the most
    // recent send is allowed to mutate shared `loading`/pending state, so a
    // follow-up message (sent as soon as the previous answer settled) never has
    // its optimistic bubbles clobbered by the previous stream's tail work.
    const myGen = ++sendSeqRef.current;
    const clientRequestId = `request_${myGen}`;
    const isCurrent = () => sendSeqRef.current === myGen;
    let answerSettled = false;
    setLoading(true);
    setLastError(null);
    try {
      if (!runtimeMemo.runtime) {
        setLastError(runtimeMemo.error);
        throw new Error(runtimeMemo.error || "运行时配置不可用。");
      }
      setPendingMessages([
        { role: "student", content: message, pending: true, clientRequestId },
        {
          role: "assistant",
          content: "",
          streaming: true,
          pending: true,
          clientRequestId,
        },
      ]);
      const response = await fetch(`${apiBase()}/api/chat/stream`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: settings.sessionId,
          message,
          memory_mode: settings.memoryMode,
          extraction_turns: settings.extractionTurns,
          runtime: runtimeMemo.runtime,
        }),
      });
      if (!response.ok || !response.body) {
        await readJsonOrThrow(response);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalReceived = false;

      // Settle the answer: pull the now-persisted turn into the message list,
      // drop the optimistic bubbles, and release the composer. Runs once, as
      // soon as the answer text is complete — before slower memory processing.
      const settleAnswer = async (
        context?: RetrievedContext,
        usage?: Record<string, unknown>,
      ) => {
        if (answerSettled) return;
        answerSettled = true;
        setPendingMessages((current) =>
          current.map((item, index) =>
            index === 1
              ? {
                  ...item,
                  retrieval: context || item.retrieval,
                  usage: usage || item.usage,
                  streaming: false,
                  pending: false,
                }
              : item,
          ),
        );
        await Promise.allSettled([refreshSessionTurns(), refreshSessions()]);
        if (isCurrent()) {
          setPendingMessages([]);
          setLoading(false);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const line = part
            .split("\n")
            .find((item) => item.startsWith("data: "));
          if (!line) continue;
          const event = JSON.parse(line.slice(6)) as {
            type?: string;
            delta?: string;
            context?: RetrievedContext;
            snapshot?: DashboardSnapshot;
            usage?: Record<string, unknown>;
            stage?: string;
          };
          if (event.type === "context" && event.context) {
            setContext(event.context);
            setPendingMessages((current) =>
              current.map((item, index) =>
                index === 1 ? { ...item, retrieval: event.context } : item,
              ),
            );
            continue;
          }
          if (event.type === "usage") {
            setPendingMessages((current) =>
              current.map((item, index) =>
                index === 1 ? { ...item, usage: event.usage } : item,
              ),
            );
            continue;
          }
          if (event.type === "reasoning") {
            const delta = event.delta || "";
            setPendingMessages((current) =>
              current.map((item, index) =>
                index === 1
                  ? { ...item, reasoning: `${item.reasoning || ""}${delta}`, streaming: true }
                  : item,
              ),
            );
            continue;
          }
          if (event.type === "delta") {
            const delta = event.delta || "";
            setPendingMessages((current) =>
              current.map((item, index) =>
                index === 1
                  ? { ...item, content: `${item.content}${delta}`, streaming: true }
                  : item,
              ),
            );
            continue;
          }
          if (event.type === "answer") {
            if (event.context) setContext(event.context);
            await settleAnswer(event.context, event.usage);
            continue;
          }
          if (event.type === "memory" && event.snapshot) {
            setSnapshot(event.snapshot);
            continue;
          }
          if (event.type === "final") {
            finalReceived = true;
            if (event.context) setContext(event.context);
            if (event.snapshot) setSnapshot(event.snapshot);
            void refreshDashboard().catch(() => {});
            // Fallback: if the backend didn't emit a separate "answer" event,
            // settle here so the composer is still released.
            await settleAnswer(event.context, event.usage);
          }
        }
      }

      if (!finalReceived && !answerSettled) {
        throw new Error("流式响应未返回最终状态。");
      }
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "导师请求失败。";
      if (isCurrent()) {
        setLastError(messageText);
        setPendingMessages([]);
      }
      throw error;
    } finally {
      if (isCurrent()) {
        setLoading(false);
      }
    }
  };

  const deleteMessage = async (_eventId: string) => {
    setLastError("消息删除功能正在开发中。");
  };

  const resetMemory = async () => {
    if (!runtimeMemo.runtime) {
      setLastError(runtimeMemo.error);
      throw new Error(runtimeMemo.error || "运行时配置不可用。");
    }
    setLoading(true);
    setLastError(null);
    try {
      const response = await fetch(`${apiBase()}/api/reset-memory`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ runtime: runtimeMemo.runtime }),
      });
      const data = await readJsonOrThrow<{ snapshot: DashboardSnapshot }>(response);
      setSnapshot(data.snapshot);
      setContext(null);
      setPendingMessages([]);
      setSessionTurns([]);
      await refreshSessions();
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "清空记忆失败。";
      setLastError(messageText);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const forceExtract = async () => {
    if (!runtimeMemo.runtime) {
      setLastError(runtimeMemo.error);
      throw new Error(runtimeMemo.error || "运行时配置不可用。");
    }
    setLoading(true);
    setLastError(null);
    try {
      const response = await fetch(`${apiBase()}/api/extract`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: settings.sessionId,
          extraction_turns: settings.extractionTurns,
          runtime: runtimeMemo.runtime,
        }),
      });
      const data = await readJsonOrThrow<{ snapshot: DashboardSnapshot }>(response);
      setSnapshot(data.snapshot);
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "记忆抽取失败。";
      setLastError(messageText);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const startNewSession = () => {
    setContext(null);
    setSettings((current) => ({
      ...current,
      sessionId: makeSessionId(),
    }));
  };

  const switchSession = (sessionId: string) => {
    setContext(null);
    setSettings((current) => ({
      ...current,
      sessionId,
    }));
  };

  const runDiagnostic = async (kind: "llm" | "embedding" | "reranker") => {
    if (!runtimeMemo.runtime) {
      setLastError(runtimeMemo.error);
      throw new Error(runtimeMemo.error || "运行时配置不可用。");
    }
    setLastError(null);
    setDiagnostics((current) => ({ ...current, loading: kind }));
    try {
      const response = await fetch(`${apiBase()}/api/diagnostics/model-test`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          runtime: runtimeMemo.runtime,
        }),
      });
      const result = await readJsonOrThrow<DiagnosticResult>(response);
      setDiagnostics((current) => ({
        ...current,
        loading: null,
        [kind]: result,
      }));
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "模型测试失败。";
      setLastError(messageText);
      setDiagnostics((current) => ({
        ...current,
        loading: null,
        [kind]: {
          status: "error",
          kind,
          provider:
            kind === "llm"
              ? (getActiveLlmProfile(settings)?.provider || "unknown")
              : kind === "embedding"
                ? (getActiveEmbeddingProfile(settings)?.provider || "unknown")
                : (getActiveRerankerProfile(settings)?.provider || "unknown"),
          profile_name:
            kind === "llm"
              ? (getActiveLlmProfile(settings)?.name || "未配置")
              : kind === "embedding"
                ? (getActiveEmbeddingProfile(settings)?.name || "未配置")
                : (getActiveRerankerProfile(settings)?.name || "未配置"),
          model_id:
            kind === "llm"
              ? (getActiveLlmModel(settings)?.modelId || "unconfigured")
              : kind === "embedding"
                ? (getActiveEmbeddingModel(settings)?.modelId || "unconfigured")
                : (getActiveRerankerModel(settings)?.modelId || "unconfigured"),
          error: messageText,
        },
      }));
      throw error;
    }
  };

  const rebuildRetrieval = async () => {
    if (!runtimeMemo.runtime) {
      setLastError(runtimeMemo.error);
      throw new Error(runtimeMemo.error || "运行时配置不可用。");
    }
    setLoading(true);
    setLastError(null);
    try {
      const response = await fetch(`${apiBase()}/api/rebuild-retrieval`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runtime: runtimeMemo.runtime,
        }),
      });
      const data = await readJsonOrThrow<{ snapshot: DashboardSnapshot }>(response);
      setSnapshot(data.snapshot);
    } catch (error) {
      const messageText =
        error instanceof Error ? error.message : "重建 retrieval embeddings 失败。";
      setLastError(messageText);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const updateSettings = (
    updater:
      | WorkspaceSettings
      | ((current: WorkspaceSettings) => WorkspaceSettings),
  ) => {
    setSettings((current) =>
      normalizeSettings(
        typeof updater === "function" ? updater(current) : updater,
      ),
    );
  };

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      settings,
      snapshot,
      messages: composeMessages(persistedMessages, pendingMessages),
      sessions,
      context,
      loading,
      backendHealthy,
      runtime: runtimeMemo.runtime,
      runtimeError: runtimeMemo.error,
      diagnostics,
      lastError,
      refreshDashboard,
      sendMessage,
      deleteMessage,
      resetMemory,
      forceExtract,
      startNewSession,
      switchSession,
      runDiagnostic,
      rebuildRetrieval,
      updateSettings,
      clearLastError: () => setLastError(null),
    }),
    [
      settings,
      snapshot,
      persistedMessages,
      pendingMessages,
      sessions,
      context,
      loading,
      backendHealthy,
      runtimeMemo,
      diagnostics,
      lastError,
    ],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within WorkspaceProvider");
  }
  return context;
}

export function useActiveWorkspaceModels() {
  const { settings } = useWorkspace();
  const llmProfile = getActiveLlmProfile(settings);
  const llmModel = getActiveLlmModel(settings);
  const embeddingProfile = getActiveEmbeddingProfile(settings);
  const embeddingModel = getActiveEmbeddingModel(settings);
  const rerankerProfile = getActiveRerankerProfile(settings);
  const rerankerModel = getActiveRerankerModel(settings);
  return {
    llmProfile,
    llmModel,
    embeddingProfile,
    embeddingModel,
    rerankerProfile,
    rerankerModel,
  };
}
