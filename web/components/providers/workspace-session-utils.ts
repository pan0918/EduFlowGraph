import type { DashboardSnapshot, RetrievedContext } from "@/lib/types";

export interface ChatMessage {
  role: "student" | "assistant";
  content: string;
  reasoning?: string;
  retrieval?: RetrievedContext;
  usage?: Record<string, unknown>;
  eventId?: string;
  streaming?: boolean;
  pending?: boolean;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
}

type SnapshotEvent = DashboardSnapshot["events"][number];

function isChatEvent(event: SnapshotEvent): boolean {
  return (
    event.event_type === "user_message" ||
    event.event_type === "assistant_message"
  );
}

function sortedChatEvents(events: SnapshotEvent[]): SnapshotEvent[] {
  return [...events].sort((left, right) => {
    const streamDelta =
      Number(left.stream_index || 0) - Number(right.stream_index || 0);
    if (streamDelta !== 0) {
      return streamDelta;
    }
    return String(left.event_id || "").localeCompare(String(right.event_id || ""));
  });
}

function objectRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function normalizeContent(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function transcriptSignature(events: SnapshotEvent[]): string | null {
  const chatEvents = sortedChatEvents(events.filter(isChatEvent));
  if (chatEvents.length === 0) {
    return null;
  }

  return JSON.stringify(
    chatEvents.map((event) => [
      event.actor === "student" ? "student" : "assistant",
      normalizeContent(event.content),
    ]),
  );
}

export function snapshotToMessages(
  snapshot: Pick<DashboardSnapshot, "events">,
  sessionId: string,
): ChatMessage[] {
  return sortedChatEvents(
    snapshot.events
      .filter((event) => event.session_id === sessionId)
      .filter(isChatEvent),
  ).map((event) => ({
    role: event.actor === "student" ? "student" : "assistant",
    content: event.content,
    reasoning:
      typeof event.metadata?.reasoning === "string"
        ? event.metadata.reasoning
        : undefined,
    retrieval: objectRecord(event.metadata?.retrieval_context) as
      | RetrievedContext
      | undefined,
    usage: objectRecord(event.metadata?.usage),
    eventId: event.event_id,
  }));
}

export function composeMessages(
  snapshot: Pick<DashboardSnapshot, "events">,
  sessionId: string,
  pendingMessages: ChatMessage[],
): ChatMessage[] {
  const persistedEvents = sortedChatEvents(
    snapshot.events
      .filter((event) => event.session_id === sessionId)
      .filter(isChatEvent),
  );
  const persistedMessages = snapshotToMessages(snapshot, sessionId);
  const latestPersistedMessage = persistedMessages.at(-1);
  const persistedEventIds = new Set(
    persistedMessages
      .map((message) => message.eventId)
      .filter((eventId): eventId is string => Boolean(eventId)),
  );
  const pendingUserEventIds = new Set(
    pendingMessages
      .filter((message) => message.role === "student")
      .map((message) => message.eventId)
      .filter((eventId): eventId is string => Boolean(eventId)),
  );
  const persistedAssistantCausationIds = new Set(
    persistedEvents
      .filter((event) => event.event_type === "assistant_message")
      .map((event) => event.causation_id)
      .filter((eventId): eventId is string => Boolean(eventId)),
  );
  const hasPersistedAssistantForPendingTurn = [...pendingUserEventIds].some(
    (eventId) => persistedAssistantCausationIds.has(eventId),
  );
  const dedupedPending = pendingMessages.filter((message) => {
    if (message.eventId && persistedEventIds.has(message.eventId)) {
      return false;
    }
    if (
      message.role === "assistant" &&
      message.pending &&
      !message.eventId &&
      hasPersistedAssistantForPendingTurn
    ) {
      return false;
    }
    if (
      message.role === "student" &&
      message.pending &&
      !message.eventId &&
      latestPersistedMessage?.role === "student" &&
      normalizeContent(latestPersistedMessage.content) === normalizeContent(message.content)
    ) {
      return false;
    }
    return true;
  });
  return [...persistedMessages, ...dedupedPending];
}

export function snapshotToSessions(
  snapshot: Pick<DashboardSnapshot, "events">,
  currentSessionId: string,
): ChatSessionSummary[] {
  const eventsBySession = new Map<string, SnapshotEvent[]>();
  for (const event of snapshot.events) {
    if (!isChatEvent(event)) {
      continue;
    }
    const events = eventsBySession.get(event.session_id) ?? [];
    events.push(event);
    eventsBySession.set(event.session_id, events);
  }

  const sessions = new Map<string, ChatSessionSummary>();
  for (const [sessionId, events] of eventsBySession) {
    const chatEvents = sortedChatEvents(events);
    const firstStudent = chatEvents.find(
      (event) => event.actor === "student" && event.content.trim(),
    );
    const lastEvent = chatEvents.at(-1);
    sessions.set(sessionId, {
      id: sessionId,
      title: firstStudent?.content.trim().slice(0, 36) || "未命名对话",
      lastUpdated: lastEvent?.timestamp || "",
      messageCount: chatEvents.length,
    });
  }

  if (!sessions.has(currentSessionId)) {
    sessions.set(currentSessionId, {
      id: currentSessionId,
      title: "新对话",
      lastUpdated: "",
      messageCount: 0,
    });
  }

  const canonicalByTranscript = new Map<string, ChatSessionSummary>();
  for (const session of sessions.values()) {
    const signature = transcriptSignature(eventsBySession.get(session.id) ?? []);
    if (!signature) {
      canonicalByTranscript.set(`empty:${session.id}`, session);
      continue;
    }

    const existing = canonicalByTranscript.get(signature);
    if (!existing) {
      canonicalByTranscript.set(signature, session);
      continue;
    }

    const shouldReplace =
      session.id === currentSessionId ||
      (existing.id !== currentSessionId &&
        session.lastUpdated.localeCompare(existing.lastUpdated) > 0);
    if (shouldReplace) {
      canonicalByTranscript.set(signature, session);
    }
  }

  return Array.from(canonicalByTranscript.values()).sort((left, right) => {
    if (left.id === currentSessionId) return -1;
    if (right.id === currentSessionId) return 1;
    return right.lastUpdated.localeCompare(left.lastUpdated);
  });
}
