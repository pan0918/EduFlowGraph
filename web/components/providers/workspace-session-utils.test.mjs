import test from "node:test";
import assert from "node:assert/strict";

import { composeMessages, turnsToMessages } from "./workspace-session-utils.ts";

function turn(index, user, assistant, metadata = {}) {
  return {
    turn_index: index,
    timestamp: `2026-06-23T00:00:0${index}+00:00`,
    session_id: "session_a",
    user_message: user,
    assistant_message: assistant,
    metadata,
  };
}

test("turnsToMessages preserves chat order and stable event ids", () => {
  const messages = turnsToMessages([
    turn(1, "为什么？", "因为条件方向不同。"),
    turn(2, "再举例。", "来看一个例子。"),
  ]);

  assert.deepEqual(
    messages.map((item) => [item.role, item.content, item.eventId]),
    [
      ["student", "为什么？", "turn_session_a_1_user"],
      ["assistant", "因为条件方向不同。", "turn_session_a_1_assistant"],
      ["student", "再举例。", "turn_session_a_2_user"],
      ["assistant", "来看一个例子。", "turn_session_a_2_assistant"],
    ],
  );
});

test("turnsToMessages exposes assistant reasoning usage and retrieval metadata", () => {
  const retrieval = {
    concepts: [{ node_id: "concept_probability", name: "Conditional probability" }],
    episodes: [],
    skills: [],
  };
  const usage = { prompt_tokens: 120, completion_tokens: 30 };
  const messages = turnsToMessages([
    turn(1, "为什么？", "最终回答", {
      reasoning: "先区分条件和目标事件。",
      usage,
      retrieval_context: retrieval,
    }),
  ]);

  assert.equal(messages[1].reasoning, "先区分条件和目标事件。");
  assert.deepEqual(messages[1].usage, usage);
  assert.deepEqual(messages[1].retrieval, retrieval);
});

test("composeMessages returns persisted messages when there is no pending state", () => {
  const persisted = turnsToMessages([turn(1, "为什么？", "因为条件方向不同。")]);

  assert.equal(composeMessages(persisted, []), persisted);
});

test("composeMessages drops optimistic bubbles after their turn is persisted", () => {
  const persisted = turnsToMessages([turn(1, "请解释条件概率。", "给定条件下的概率。")]);
  const messages = composeMessages(persisted, [
    { role: "student", content: "请解释条件概率。", pending: true },
    { role: "assistant", content: "给定条件下的概率。", pending: true, streaming: true },
  ]);

  assert.deepEqual(messages, persisted);
});

test("composeMessages keeps a deliberately repeated question after an earlier completed turn", () => {
  const persisted = turnsToMessages([turn(1, "请解释条件概率。", "给定条件下的概率。")]);
  const pending = [
    {
      role: "student",
      content: "请解释条件概率。",
      pending: true,
      clientRequestId: "request_2",
    },
    {
      role: "assistant",
      content: "",
      pending: true,
      streaming: true,
      clientRequestId: "request_2",
    },
  ];

  assert.deepEqual(composeMessages(persisted, pending), [...persisted, ...pending]);
});
