import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./KnowledgeWorkspace.tsx", import.meta.url), "utf8");

test("knowledge workspace renders the concept mastery dashboard shell", () => {
  assert.match(source, /概念掌握面板/);
  assert.match(source, /待强化概念/);
  assert.match(source, /生成学习计划/);
  assert.match(source, /搜索概念、知识点或学科/);
});

test("knowledge workspace no longer renders the raw snapshot concept list", () => {
  assert.doesNotMatch(source, /snapshot\.concepts\.map\(\(concept\)/);
});
