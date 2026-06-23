import type { RetrievedContext } from "@/lib/types";

export interface ChatMessage {
  role: "student" | "assistant";
  content: string;
  reasoning?: string;
  retrieval?: RetrievedContext;
  usage?: Record<string, unknown>;
  eventId?: string;
  streaming?: boolean;
  pending?: boolean;
  clientRequestId?: string;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  lastUpdated: string;
  messageCount: number;
}

export interface TurnRecord {
  turn_index: number;
  timestamp: string;
  session_id: string;
  user_message: string;
  assistant_message: string;
  metadata?: Record<string, unknown>;
}

export function turnsToMessages(turns: TurnRecord[]): ChatMessage[] {
  const messages: ChatMessage[] = [];
  for (const turn of turns) {
    messages.push({
      role: "student",
      content: turn.user_message,
      eventId: `turn_${turn.session_id}_${turn.turn_index}_user`,
    });
    messages.push({
      role: "assistant",
      content: turn.assistant_message,
      reasoning:
        typeof turn.metadata?.reasoning === "string"
          ? turn.metadata.reasoning
          : undefined,
      retrieval: (turn.metadata?.retrieval_context as RetrievedContext) || undefined,
      usage: (turn.metadata?.usage as Record<string, unknown>) || undefined,
      eventId: `turn_${turn.session_id}_${turn.turn_index}_assistant`,
    });
  }
  return messages;
}

export function composeMessages(
  persistedMessages: ChatMessage[],
  pendingMessages: ChatMessage[],
): ChatMessage[] {
  if (pendingMessages.length === 0) return persistedMessages;

  const persistedContents = new Set(
    persistedMessages
      .filter((m) => m.role === "student")
      .map((m) => m.content.trim()),
  );

  const lastPersisted = persistedMessages.at(-1);
  const pendingUser = pendingMessages.find((m) => m.role === "student");

  if (
    pendingUser &&
    !pendingUser.clientRequestId &&
    !pendingUser.eventId &&
    lastPersisted?.role === "assistant" &&
    !lastPersisted.streaming &&
    persistedContents.has(pendingUser.content.trim())
  ) {
    return persistedMessages;
  }

  return [...persistedMessages, ...pendingMessages];
}
