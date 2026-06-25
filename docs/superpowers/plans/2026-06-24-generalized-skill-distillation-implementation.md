# Generalized Skill Distillation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make automatically distilled Skill nodes learner-specific but concept-agnostic, so repeated effective teaching patterns transfer across knowledge topics without creating generic low-quality skills.

**Architecture:** Keep Episode-level SkillEvidence concrete and traceable, but replace Concept-family gates with reusable learning-situation compatibility based on difficulty-pattern sets and stable teaching actions. Preserve the singular difficulty field for compatibility, add a plural field for generalized Skills, and keep concrete concepts only in provenance metadata.

**Tech Stack:** Python 3.12, unittest/pytest, SQLite-backed graph storage, Markdown prompts, TypeScript/Next.js.

---

### Task 1: Define generalized matching behavior

**Files:**
- Modify: `tests/test_memory_pipeline.py`
- Modify: `tests/test_eduflowgraph.py`

- [ ] **Step 1: Add failing cross-concept distillation tests**

Add real `HeuristicSkillDistiller` tests using unrelated concepts such as ellipse area and PPO. Assert the result contains both compatible difficulties, stable core actions, no concrete concept in public fields, and concrete concepts only in `metadata.evidence_concept_scope`.

- [ ] **Step 2: Add failing matching and rejection tests**

Assert a Skill can validate on a new concept when difficulty and actions are compatible; assert incompatible difficulties or weakly overlapping actions do not match. Assert old singular-difficulty Skills remain matchable.

- [ ] **Step 3: Run tests and confirm RED**

Run: `.venv/bin/python -m pytest tests/test_memory_pipeline.py tests/test_eduflowgraph.py -q`

Expected: new cross-concept and plural-difficulty assertions fail because current code requires Concept-family equality and only emits one difficulty.

### Task 2: Implement difficulty compatibility and stable actions

**Files:**
- Modify: `EduFlowGraph/memory/skill_pipeline.py`
- Test: `tests/test_memory_pipeline.py`
- Test: `tests/test_eduflowgraph.py`

- [ ] **Step 1: Add normalized pattern helpers**

Implement `skill_difficulty_patterns`, `difficulty_patterns_compatible`, and evidence-pattern normalization. Treat legacy `difficulty_pattern` as a one-element list and exclude `unknown`.

- [ ] **Step 2: Replace Concept-family matching gates**

Update `skill_matches_evidence` and `skill_matches_candidate` to use compatible difficulty sets plus core-action overlap. Keep Concept scope available only through `skill_evidence_concept_scope` for provenance.

- [ ] **Step 3: Distill stable generalized fields**

Aggregate all supported difficulty patterns, choose the most frequent as `difficulty_pattern`, emit `difficulty_patterns`, and select teaching actions occurring in at least half the evidence. Build the Skill id, trigger, procedure, criteria, and embedding text without Concept names.

- [ ] **Step 4: Preserve plural patterns through LLM coercion and merging**

Accept only valid patterns present in evidence/fallback, retain the compatibility field, and union patterns when merging equivalent candidates.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `.venv/bin/python -m pytest tests/test_memory_pipeline.py tests/test_eduflowgraph.py -q`

Expected: all focused tests pass.

### Task 3: Generalize pipeline evidence windows and prompts

**Files:**
- Modify: `EduFlowGraph/pipeline.py`
- Modify: `EduFlowGraph/Prompt/Skill_Distillation_Prompt.md`
- Modify: `tests/test_memory_pipeline.py`

- [ ] **Step 1: Add a failing pipeline window test**

Build two evidence records with different concepts, compatible difficulties, and overlapping actions. Assert `_build_evidence_window` returns both while rejecting an unrelated action/difficulty record.

- [ ] **Step 2: Run the test and confirm RED**

Run: `.venv/bin/python -m pytest tests/test_memory_pipeline.py -q`

Expected: the cross-concept evidence is excluded by `same_concept_family`.

- [ ] **Step 3: Update evidence-window selection**

Use difficulty compatibility and positive action overlap, require distinct non-empty evidence, remove the Concept-family import from the orchestrator, and keep the four-evidence bound.

- [ ] **Step 4: Strengthen the LLM distillation contract**

Describe cross-topic transfer, plural difficulties, stable-action selection, concept-agnostic public text, and rejection of topic summaries. Add `difficulty_patterns` to the JSON output contract.

- [ ] **Step 5: Run the pipeline tests and confirm GREEN**

Run: `.venv/bin/python -m pytest tests/test_memory_pipeline.py -q`

Expected: all pipeline tests pass.

### Task 4: Make recall and UI plural-pattern compatible

**Files:**
- Modify: `EduFlowGraph/memory/retriever.py`
- Modify: `EduFlowGraph/memory/skill_reranker.py`
- Modify: `web/lib/types.ts`
- Modify: `web/lib/skill-display.ts`
- Modify: `web/lib/skill-display.test.mjs`
- Test: `tests/test_memory_pipeline.py`
- Test: `tests/test_skill_reranker.py`

- [ ] **Step 1: Add failing compatibility tests**

Assert retrieval difficulty bonuses match any Skill difficulty pattern and the UI displays multiple difficulty labels. Assert Skill rerank documents include all generalized difficulty patterns and no provenance concept scope is required.

- [ ] **Step 2: Run backend and frontend unit tests and confirm RED**

Run: `.venv/bin/python -m pytest tests/test_memory_pipeline.py tests/test_skill_reranker.py -q`

Run: `node --test web/lib/skill-display.test.mjs`

Expected: plural-pattern assertions fail.

- [ ] **Step 3: Update recall and rerank representations**

Use normalized Skill difficulty sets for bonuses, matched-difficulty traces, retrieval text, and rerank documents. Remove evidence Concept scope from Skill embedding keywords while preserving it in diagnostics.

- [ ] **Step 4: Update TypeScript compatibility and display**

Add optional `difficulty_patterns` to `SkillNode`; render unique labels from the plural list or singular fallback.

- [ ] **Step 5: Re-run focused tests and confirm GREEN**

Run the backend and frontend unit commands from Step 2 and confirm all pass.

### Task 5: Full verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run the full Python suite**

Run: `.venv/bin/python -m pytest -q`

Expected: zero failures.

- [ ] **Step 2: Run all web unit tests**

Run: `node --test web/lib/skill-display.test.mjs web/lib/latex.test.mjs web/components/workspace/chat-workspace-source.test.mjs web/components/workspace/memory-graph-layout.test.mjs web/components/workspace/chat-trace-utils.test.mjs web/components/workspace/skills-workspace-source.test.mjs web/components/workspace/profile-page-source.test.mjs web/components/providers/workspace-session-utils.test.mjs`

Expected: zero failures.

- [ ] **Step 3: Run the production build**

Run: `npm --prefix web run build`

Expected: exit code 0.

- [ ] **Step 4: Validate SQLite state**

Run a read-only SQLite `PRAGMA quick_check`, confirm schema version 2 and WAL mode, and confirm no stored Skill payload is required to migrate for the optional field.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors and only intended project changes remain alongside the pre-existing user changes.
