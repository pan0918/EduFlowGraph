# Memory Graph Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make concept, episode, and skill nodes cleaner by keeping reusable semantics on nodes and concrete evidence on edges.

**Architecture:** Preserve the current JSON graph shape for compatibility, but tighten what each layer means. Concept canonicalization will merge common bilingual/synonym variants into one reusable concept; skill generation will keep concept-specific evidence out of the skill's learner-facing identity; UI will show compact skill summaries by default.

**Tech Stack:** Python memory pipeline, JSON graph store, Node/Next.js frontend, `node --test`, `unittest`.

---

### Task 1: Concept Canonicalization

**Files:**
- Modify: `eduflowgraph/graph_store.py`
- Test: `tests/test_memory_pipeline.py`

- [ ] Add a failing test proving `Bayes theorem`, `Bayes' theorem`, `贝叶斯定理`, and `贝叶斯公式` upsert into one concept node.
- [ ] Implement a small canonical concept registry and use it before concept IDs and lookup keys are generated.
- [ ] Preserve all useful aliases during merges.

### Task 2: Generic Skill Nodes

**Files:**
- Modify: `eduflowgraph/skill_extractor.py`
- Modify: `eduflowgraph/Prompt/Skill_Distillation_Prompt.md`
- Modify: `eduflowgraph/pipeline.py`
- Test: `tests/test_memory_pipeline.py`

- [ ] Add failing tests proving a distilled skill trigger and embedding text do not contain concrete concept names.
- [ ] Keep concept evidence in metadata for matching/retrieval when useful, but do not make it part of the skill's public trigger.
- [ ] Limit generated procedure and success criteria to concise generic steps.

### Task 3: Compact Skill UI

**Files:**
- Modify: `web/lib/skill-display.ts`
- Modify: `web/components/workspace/SkillsWorkspace.tsx`
- Modify: `web/components/workspace/MemoryGraphView.tsx`
- Modify: `web/components/workspace/memory-graph-layout.ts`
- Test: `web/lib/skill-display.test.mjs`
- Test: `web/components/workspace/chat-workspace-source.test.mjs`
- Test: `web/components/workspace/memory-graph-layout.test.mjs`

- [ ] Add failing tests proving skill display exposes compact procedure and success criteria.
- [ ] Hide concept scope chips from the skill card by default.
- [ ] Keep graph node summaries generic and edge evidence specific.

### Task 4: Verification

**Commands:**
- `python3 -m unittest tests.test_memory_pipeline tests.test_model_runtime`
- `node --test web/components/providers/workspace-session-utils.test.mjs web/components/workspace/chat-trace-utils.test.mjs web/components/workspace/chat-workspace-source.test.mjs web/components/workspace/memory-graph-layout.test.mjs web/lib/latex.test.mjs web/lib/skill-display.test.mjs`
- `npm run build` from `web`

- [ ] Run all commands fresh.
- [ ] Report exact pass/fail status.
