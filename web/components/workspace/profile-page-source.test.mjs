import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const sidebarSource = readFileSync(
  new URL("../sidebar/WorkspaceSidebar.tsx", import.meta.url),
  "utf8",
);
const memoryWorkspaceSource = readFileSync(
  new URL("./MemoryWorkspace.tsx", import.meta.url),
  "utf8",
);
const profilePageSource = readFileSync(
  new URL("../../app/(workspace)/space/profile/page.tsx", import.meta.url),
  "utf8",
);
const profileWorkspaceSource = readFileSync(
  new URL("./LearnerProfileWorkspace.tsx", import.meta.url),
  "utf8",
);

test("workspace sidebar exposes a dedicated learner profile page", () => {
  assert.match(sidebarSource, /href:\s*"\/space\/profile"/);
  assert.match(sidebarSource, /label:\s*"画像"/);
});

test("profile route renders the dedicated learner profile workspace", () => {
  assert.match(profilePageSource, /LearnerProfileWorkspace/);
  assert.match(profilePageSource, /<LearnerProfileWorkspace\s*\/>/);
});

test("memory workspace does not own the learner profile panel", () => {
  assert.doesNotMatch(memoryWorkspaceSource, /学习画像/);
  assert.doesNotMatch(memoryWorkspaceSource, /snapshot\.profile\.items/);
});

test("profile workspace uses two-portrait profile system", () => {
  assert.match(profileWorkspaceSource, /learner_model/);
  assert.match(profileWorkspaceSource, /context_model/);
  assert.match(profileWorkspaceSource, /学习者画像/);
  assert.match(profileWorkspaceSource, /情境画像/);
  assert.doesNotMatch(profileWorkspaceSource, /teaching_adaptation_model/);
  assert.doesNotMatch(profileWorkspaceSource, /教学适配模型/);
  assert.doesNotMatch(profileWorkspaceSource, /strategy_model/);
});

test("profile workspace renders lightweight summary + recent changes", () => {
  // single-paragraph summary per model, not an item list
  assert.match(profileWorkspaceSource, /entry\?\.summary/);
  assert.match(profileWorkspaceSource, /recent_changes/);
  assert.match(profileWorkspaceSource, /revision_count/);
  // old evidence-item fields must be gone
  assert.doesNotMatch(profileWorkspaceSource, /confidence/);
  assert.doesNotMatch(profileWorkspaceSource, /lifecycle/);
});
