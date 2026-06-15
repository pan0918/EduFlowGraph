import test from "node:test";
import assert from "node:assert/strict";

import { composeMessages, snapshotToMessages, snapshotToSessions } from "./workspace-session-utils.ts";

function message(sessionId, streamIndex, actor, content) {
  return {
    event_id: `event_${sessionId}_${streamIndex}`,
    stream_index: streamIndex,
    session_id: sessionId,
    turn_index: Math.ceil(streamIndex / 2),
    timestamp: `2026-06-10T00:00:0${streamIndex}+00:00`,
    actor,
    event_type: actor === "student" ? "user_message" : "assistant_message",
    content,
    metadata: {},
    causation_id: actor === "assistant" ? `event_${sessionId}_${streamIndex - 1}` : null,
  };
}

test("snapshotToSessions collapses sessions with identical message transcripts", () => {
  const snapshot = {
    events: [
      message("session_a", 1, "student", "为什么不能直接把检测准确率当作患病概率？"),
      message("session_a", 2, "assistant", "先区分 P(阳性|患病) 和 P(患病|阳性)。"),
      message("session_b", 3, "student", "为什么不能直接把检测准确率当作患病概率？"),
      message("session_b", 4, "assistant", "先区分 P(阳性|患病) 和 P(患病|阳性)。"),
    ],
  };

  const sessions = snapshotToSessions(snapshot, "session_a");

  assert.equal(sessions.length, 1);
  assert.equal(sessions[0].id, "session_a");
  assert.equal(sessions[0].messageCount, 2);
});

test("snapshotToSessions keeps distinct conversations separate", () => {
  const snapshot = {
    events: [
      message("session_a", 1, "student", "为什么不能直接把检测准确率当作患病概率？"),
      message("session_a", 2, "assistant", "先区分 P(阳性|患病) 和 P(患病|阳性)。"),
      message("session_b", 3, "student", "什么是贝叶斯定理？"),
      message("session_b", 4, "assistant", "贝叶斯定理用于根据证据更新信念。"),
    ],
  };

  const sessions = snapshotToSessions(snapshot, "session_a");

  assert.equal(sessions.length, 2);
  assert.deepEqual(
    sessions.map((session) => session.id).sort(),
    ["session_a", "session_b"],
  );
});

test("composeMessages drops streaming assistant once the persisted assistant event arrives", () => {
  const snapshot = {
    events: [
      message("session_a", 1, "student", "请解释条件概率。"),
      message("session_a", 2, "assistant", "条件概率是给定条件下事件发生的概率。"),
    ],
  };

  const messages = composeMessages(snapshot, "session_a", [
    {
      role: "student",
      content: "请解释条件概率。",
      eventId: "event_session_a_1",
      pending: true,
    },
    {
      role: "assistant",
      content: "条件概率是给定条件下事件发生的概率。",
      streaming: true,
      pending: true,
    },
  ]);

  assert.equal(messages.length, 2);
  assert.deepEqual(
    messages.map((item) => [item.role, item.content, Boolean(item.streaming)]),
    [
      ["student", "请解释条件概率。", false],
      ["assistant", "条件概率是给定条件下事件发生的概率。", false],
    ],
  );
});

test("composeMessages drops pending student once a matching persisted user event arrives", () => {
  const snapshot = {
    events: [
      message("session_a", 1, "student", "请解释条件概率。"),
    ],
  };

  const messages = composeMessages(snapshot, "session_a", [
    {
      role: "student",
      content: "请解释条件概率。",
      pending: true,
    },
    {
      role: "assistant",
      content: "",
      streaming: true,
      pending: true,
    },
  ]);

  assert.deepEqual(
    messages.map((item) => [item.role, item.content]),
    [
      ["student", "请解释条件概率。"],
      ["assistant", ""],
    ],
  );
});

test("composeMessages keeps a repeated pending student after an earlier completed turn", () => {
  const snapshot = {
    events: [
      message("session_a", 1, "student", "请解释条件概率。"),
      message("session_a", 2, "assistant", "条件概率是给定条件下事件发生的概率。"),
    ],
  };

  const messages = composeMessages(snapshot, "session_a", [
    {
      role: "student",
      content: "请解释条件概率。",
      pending: true,
    },
    {
      role: "assistant",
      content: "",
      streaming: true,
      pending: true,
    },
  ]);

  assert.deepEqual(
    messages.map((item) => [item.role, item.content]),
    [
      ["student", "请解释条件概率。"],
      ["assistant", "条件概率是给定条件下事件发生的概率。"],
      ["student", "请解释条件概率。"],
      ["assistant", ""],
    ],
  );
});

test("snapshotToMessages exposes assistant reasoning and usage metadata", () => {
  const assistant = message("session_a", 2, "assistant", "最终回答");
  assistant.metadata = {
    reasoning: "先区分条件和目标事件。",
    usage: {
      prompt_tokens: 120,
      completion_tokens: 30,
      prompt_tokens_details: { cached_tokens: 80 },
    },
    retrieval_context: {
      concepts: [{ node_id: "concept_probability", name: "Conditional probability" }],
      episodes: [],
      skills: [],
    },
  };

  const messages = snapshotToMessages(
    {
      events: [message("session_a", 1, "student", "为什么？"), assistant],
    },
    "session_a",
  );

  assert.equal(messages[1].reasoning, "先区分条件和目标事件。");
  assert.deepEqual(messages[1].usage, assistant.metadata.usage);
  assert.deepEqual(messages[1].retrieval, assistant.metadata.retrieval_context);
});
