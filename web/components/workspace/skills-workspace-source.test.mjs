import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./SkillsWorkspace.tsx", import.meta.url), "utf8");

test("skills workspace keeps concept scope out of the public skill card", () => {
  assert.doesNotMatch(source, /skill\.concept_scope\?\./);
  assert.doesNotMatch(source, /concept_scope/);
});

test("skills workspace owns skill adaptation evidence", () => {
  assert.match(source, /技能适配证据/);
  assert.match(source, /snapshot\.skill_adaptation/);
  assert.match(source, /Skill 重排/);
});
