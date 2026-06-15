import test from "node:test";
import assert from "node:assert/strict";

import {
  formatReasoningForPanel,
  summarizeRetrieval,
  summarizeUsage,
} from "./chat-trace-utils.ts";

test("summarizeUsage reads OpenAI chat completion cached token details", () => {
  const summary = summarizeUsage({
    prompt_tokens: 200,
    completion_tokens: 40,
    total_tokens: 240,
    prompt_tokens_details: {
      cached_tokens: 150,
    },
  });

  assert.deepEqual(summary, {
    promptTokens: 200,
    completionTokens: 40,
    totalTokens: 240,
    cachedTokens: 150,
    cacheHitRate: 0.75,
  });
});

test("summarizeUsage reads compatible input token cache fields", () => {
  const summary = summarizeUsage({
    input_tokens: 100,
    output_tokens: 25,
    input_tokens_details: {
      cache_read: 60,
    },
  });

  assert.equal(summary?.promptTokens, 100);
  assert.equal(summary?.completionTokens, 25);
  assert.equal(summary?.totalTokens, 125);
  assert.equal(summary?.cachedTokens, 60);
  assert.equal(summary?.cacheHitRate, 0.6);
});

test("summarizeUsage reads DeepSeek-style prompt cache hit and miss fields", () => {
  const summary = summarizeUsage({
    completion_tokens: 20,
    prompt_cache_hit_tokens: 320,
    prompt_cache_miss_tokens: 80,
  });

  assert.equal(summary?.promptTokens, 400);
  assert.equal(summary?.completionTokens, 20);
  assert.equal(summary?.totalTokens, 420);
  assert.equal(summary?.cachedTokens, 320);
  assert.equal(summary?.cacheHitRate, 0.8);
});

test("summarizeUsage reads Anthropic-style cache read input tokens", () => {
  const summary = summarizeUsage({
    input_tokens: 50,
    output_tokens: 10,
    cache_creation_input_tokens: 100,
    cache_read_input_tokens: 450,
  });

  assert.equal(summary?.promptTokens, 600);
  assert.equal(summary?.completionTokens, 10);
  assert.equal(summary?.totalTokens, 610);
  assert.equal(summary?.cachedTokens, 450);
  assert.equal(summary?.cacheHitRate, 0.75);
});

test("summarizeRetrieval keeps an empty retrieval context visible", () => {
  const summary = summarizeRetrieval({
    concepts: [],
    episodes: [],
    skills: [],
    retrieval_summary: {
      stale_vectors: 0,
      concept_hits: 0,
      episode_hits: 0,
      skill_hits: 0,
    },
    memory_context_pack: "[Memory Context]\\n- None",
  });

  assert.deepEqual(summary, {
    conceptCount: 0,
    episodeCount: 0,
    skillCount: 0,
    totalCount: 0,
    hasContext: true,
    staleVectors: 0,
    conceptHits: 0,
    episodeHits: 0,
    skillHits: 0,
  });
});

test("formatReasoningForPanel clips very long reasoning for responsive rendering", () => {
  const reasoning = `${"A".repeat(80)}${"B".repeat(80)}${"C".repeat(80)}`;

  const panel = formatReasoningForPanel(reasoning, 120);

  assert.equal(panel.truncated, true);
  assert.equal(panel.content.length <= 160, true);
  assert.equal(panel.content.startsWith("A".repeat(60)), true);
  assert.equal(panel.content.endsWith("C".repeat(60)), true);
  assert.match(panel.content, /中间/);
});

test("formatReasoningForPanel keeps normal reasoning untouched", () => {
  const panel = formatReasoningForPanel("先检索，再回答。", 120);

  assert.deepEqual(panel, {
    content: "先检索，再回答。",
    truncated: false,
    originalLength: 8,
  });
});
