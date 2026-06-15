import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./ChatWorkspace.tsx", import.meta.url), "utf8");

test("conversation trace reasoning renders through AssistantMarkdown instead of raw pre text", () => {
  const reasoningSectionStart = source.indexOf("思考过程");
  const nextSectionStart = source.indexOf("记忆检索", reasoningSectionStart);
  const reasoningSection = source.slice(reasoningSectionStart, nextSectionStart);

  assert.match(reasoningSection, /<AssistantMarkdown\s+content=\{reasoningPanel\?\.content \?\? ""\}/);
  assert.doesNotMatch(reasoningSection, /<pre\b/);
  assert.doesNotMatch(reasoningSection, /\{reasoningPanel\?\.content\}/);
});
