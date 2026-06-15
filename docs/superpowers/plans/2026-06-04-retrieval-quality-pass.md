# Retrieval Quality Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve retrieval quality end-to-end so concept, episode, and skill recall align better with learner intent and the final memory context pack drives more effective tutor behavior.

**Architecture:** Keep the existing `concept -> episode -> skill -> rerank -> memory_context_pack` pipeline, but tighten query understanding, candidate scoring, rerank payload quality, and the final teaching instruction generation. Preserve existing schemas and APIs while improving ranking decisions and tutor-facing context fidelity.

**Tech Stack:** Python, unittest, FastAPI, Next.js, in-memory graph retrieval, reranker/LLM fallback runtime

---

### Task 1: Add regression tests for the missing high-order retrieval behaviors

**Files:**
- Modify: `tests/test_memory_pipeline.py`
- Test: `tests/test_memory_pipeline.py`

- [ ] **Step 1: Write failing tests for the new retrieval quality targets**

Add tests that cover:
- comparison intent preferring contrastive skills and comparison-aware instructions
- worked-example intent preferring example-heavy skills and examples-first instructions
- concept recall deduping concept aliases that point to the same node
- rerank payload preserving structured match reasons for downstream ranking/debugging

- [ ] **Step 2: Run the targeted test slice to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_memory_pipeline`
Expected: at least the newly-added retrieval quality tests fail for missing behavior.

- [ ] **Step 3: Keep the failing expectations minimal and behavior-focused**

Use existing graph/test helpers instead of inventing new infrastructure.

- [ ] **Step 4: Re-run the targeted slice until the failures are the expected ones**

Run: `.venv/bin/python -m unittest tests.test_memory_pipeline`
Expected: failures point to retrieval ranking/context behavior, not syntax or fixture mistakes.

### Task 2: Improve retrieval orchestration and ranking logic

**Files:**
- Modify: `eduflowgraph/retriever.py`
- Test: `tests/test_memory_pipeline.py`

- [ ] **Step 1: Refine query understanding**

Add richer intent detection for:
- `comparison`
- `worked_example`
- `formula_grounding`

Preserve existing `assessment`, `review`, `re_explanation`, and `concept_explanation`.

- [ ] **Step 2: Refine concept, episode, and skill scoring**

Implement:
- stronger short-query / alias precision bias for concepts
- episode bonuses aligned to query intent
- skill bonuses aligned to difficulty pattern, intent, teaching actions, and concept scope

- [ ] **Step 3: Improve rerank payload quality without changing public API shape**

Enrich candidate items with compact structured fields such as:
- `match_reasons`
- `matched_concepts`
- `matched_difficulty`
- `intent`

Keep top-level `concepts / episodes / skills / retrieval_summary / memory_context_pack` contract stable.

- [ ] **Step 4: Run targeted tests to verify the retrieval logic passes**

Run: `.venv/bin/python -m unittest tests.test_memory_pipeline`
Expected: new and existing retrieval tests pass.

### Task 3: Improve memory context pack and tutor prompt quality

**Files:**
- Modify: `eduflowgraph/retriever.py`
- Modify: `eduflowgraph/prompts.py`
- Test: `tests/test_memory_pipeline.py`

- [ ] **Step 1: Tighten memory context pack generation**

Make the pack more action-oriented by producing:
- clearer learner trajectory summaries
- a stronger primary teaching move
- explicit fallback guidance when the learner remains confused
- clearer instructions for assessment vs comparison vs worked-example queries

- [ ] **Step 2: Tune the tutor prompt to use the improved pack more faithfully**

Update prompt guidance so the tutor:
- follows the recommended teaching move
- does not repeat failed explanation paths
- adapts to assessment/comparison/worked-example intent
- ends with a compact check question

- [ ] **Step 3: Run targeted tests again to confirm prompt/context expectations**

Run: `.venv/bin/python -m unittest tests.test_memory_pipeline`
Expected: retrieval context tests remain green.

### Task 4: Run full regression verification

**Files:**
- Modify: none
- Test: `tests/test_memory_pipeline.py`
- Test: `tests/test_web_app_api.py`
- Test: `tests/test_model_runtime.py`
- Test: `tests/test_diagnostics_api.py`

- [ ] **Step 1: Run backend regression suite**

Run: `.venv/bin/python -m unittest tests/test_memory_pipeline.py tests/test_web_app_api.py tests/test_model_runtime.py tests/test_diagnostics_api.py`
Expected: all tests pass.

- [ ] **Step 2: Run frontend build verification**

Run: `npm run build`
Working directory: `web`
Expected: production build succeeds.

- [ ] **Step 3: Run smoke verification**

Run: `.venv/bin/python scripts/smoke_run.py`
Expected: smoke run succeeds and still produces a retrieval-enabled snapshot.
