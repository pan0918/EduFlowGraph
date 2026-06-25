# Knowledge Mastery Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current `Knowledge` workspace concept list with a high-fidelity, hardcoded concept mastery dashboard that supports search and subject filtering.

**Architecture:** Keep the `/knowledge` route unchanged and rebuild the `KnowledgeWorkspace` presentation layer around a local hardcoded dashboard data model. Use a small number of focused local subcomponents so the page can later swap from static data to fetched data without redesigning the UI tree.

**Tech Stack:** Next.js App Router, React client component, Tailwind CSS, Node source tests

---

### Task 1: Guard the new dashboard shape with a failing source test

**Files:**
- Create: `web/components/workspace/knowledge-workspace-source.test.mjs`
- Test: `web/components/workspace/knowledge-workspace-source.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs`
Expected: FAIL because the current page does not contain the new dashboard strings.

- [ ] **Step 3: Extend the test with an old-rendering guard**

```js
test("knowledge workspace no longer renders the raw snapshot concept list", () => {
  assert.doesNotMatch(source, /snapshot\.concepts\.map\(\(concept\)/);
});
```

- [ ] **Step 4: Run test again to confirm the failing baseline**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs`
Expected: still FAIL on the missing new dashboard structure.

### Task 2: Rebuild the knowledge page around hardcoded dashboard data

**Files:**
- Modify: `web/components/workspace/KnowledgeWorkspace.tsx`
- Test: `web/components/workspace/knowledge-workspace-source.test.mjs`

- [ ] **Step 1: Introduce a hardcoded dashboard data model**

Add page-local constants for:

- subject filter labels
- summary cards
- subject mastery cards
- weak concept rail rows
- learning suggestion banner

Keep fields future-friendly: `id`, `name`, `mastery`, `topics`, `recommendation`, `status`, `accent`.

- [ ] **Step 2: Add client-side search and filter state**

Use `useState` for:

- active subject filter
- search query

Derive filtered subject cards and filtered weak concept rows from the hardcoded data so both regions respond together.

- [ ] **Step 3: Replace the old concept-list layout with the new dashboard composition**

Implement:

- hero header with title, copy, search, and decorative background
- pill filter row
- four summary metric cards
- left grid of subject mastery cards
- right weak concept rail
- bottom learning suggestion banner with CTA

- [ ] **Step 4: Keep the implementation modular inside the file**

Use focused local subcomponents such as:

- `SummaryCard`
- `SubjectFilterPill`
- `SubjectMasteryCard`
- `WeakConceptRow`
- `LearningSuggestionBanner`

Avoid a monolithic JSX block.

- [ ] **Step 5: Run the new source test to verify it passes**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs`
Expected: PASS

### Task 3: Polish responsive behavior and empty states

**Files:**
- Modify: `web/components/workspace/KnowledgeWorkspace.tsx`
- Optional Modify: `web/app/globals.css`
- Test: `web/components/workspace/knowledge-workspace-source.test.mjs`

- [ ] **Step 1: Ensure the dashboard collapses cleanly on narrower widths**

Make the main area stack from:

- desktop: subject grid + right rail
- smaller screens: full-width subject grid followed by weak concept panel

- [ ] **Step 2: Add empty-result states for filters**

If search plus subject filter yields no results:

- show a soft empty state for subject cards
- show a matching empty state in the weak concept panel

- [ ] **Step 3: Keep styling scoped**

Prefer page-local utility classes and inline token usage. Only touch `web/app/globals.css` if a small reusable helper is clearly worth it.

- [ ] **Step 4: Re-run the source test**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs`
Expected: PASS

### Task 4: Verify the page at app level

**Files:**
- Test: `web/components/workspace/knowledge-workspace-source.test.mjs`
- Verify: `web`

- [ ] **Step 1: Run the focused Knowledge workspace test**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs`
Expected: PASS

- [ ] **Step 2: Run the existing workspace source tests alongside it**

Run: `node --test web/components/workspace/knowledge-workspace-source.test.mjs web/components/workspace/profile-page-source.test.mjs web/components/workspace/skills-workspace-source.test.mjs web/components/workspace/chat-workspace-source.test.mjs`
Expected: PASS

- [ ] **Step 3: Run a production build**

Run: `npm run build`
Workdir: `web`
Expected: Next.js build succeeds with exit code `0`
