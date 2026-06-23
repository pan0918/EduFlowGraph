# Teaching Adaptation Skill Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old teaching-strategy profile with a text-only teaching-adaptation profile that personalizes Qwen-based Skill reranking while keeping empty, degraded, and reset states render-safe.

**Architecture:** Keep Concept/Episode/Skill base recall in `MemoryRetriever`, then pass Skill candidates to a focused `SkillPersonalizedReranker` that builds the personalized Qwen query, preserves relevance scores, combines bounded evidence components, filters weak Skills, and emits a trace. The profile store exposes only `learner_model`, `teaching_adaptation_model`, and `context_model`; only learner/context paragraphs and selected Skill procedures enter the Tutor prompt.

**Tech Stack:** Python 3.11, SQLite 3/WAL, FastAPI, unittest/pytest, Next.js/React/TypeScript, existing OpenAI-compatible rerank endpoint.

---

## File map

- Create `EduFlowGraph/memory/skill_reranker.py`: personalized query/document construction, score normalization, weighted fusion, selection gates, fallback instruction, and trace.
- Modify `EduFlowGraph/llm.py`: preserve reranker indexes and relevance scores without breaking order-only consumers.
- Modify `EduFlowGraph/memory/retriever.py`: expose bounded Skill candidate evidence and render multiple selected Skills without owning personalization policy.
- Modify `EduFlowGraph/pipeline.py`: orchestrate base recall, profile lookup, personalized Skill selection, and prompt-safe profile rendering.
- Modify `EduFlowGraph/profile/dimensions.py`, `consolidator.py`, `retriever.py`, and profile prompts: canonical model rename and new semantic boundary.
- Modify `EduFlowGraph/store/profile_store.py`, `sqlite_profile_store.py`, `sqlite_storage.py`, and `migration.py`: canonical snapshot and SQLite v2 migration.
- Modify `web/lib/types.ts`, profile/context components, and Skill display helpers: canonical key, Seed status, and selection trace.
- Extend active Python tests and add focused reranker tests; validate frontend with typecheck/build.

---

### Task 1: Canonical teaching-adaptation profile contract

**Files:**
- Modify: `tests/test_eduflowgraph.py`
- Modify: `EduFlowGraph/profile/dimensions.py`
- Modify: `EduFlowGraph/profile/retriever.py`
- Modify: `EduFlowGraph/profile/aggregator.py`
- Modify: `EduFlowGraph/profile/__init__.py`
- Modify: `EduFlowGraph/store/profile_store.py`

- [ ] **Step 1: Write failing contract and compatibility tests**

Add assertions equivalent to:

```python
def test_three_models_use_teaching_adaptation_name(self):
    self.assertEqual(
        MODEL_NAMES,
        ("learner_model", "teaching_adaptation_model", "context_model"),
    )
    self.assertEqual(
        set(EPISODE_MODELS),
        {"learner_model", "teaching_adaptation_model"},
    )

def test_legacy_strategy_summary_is_not_carried_into_new_profile(self):
    store = LearnerProfileStore(Path(self.tmp.name))
    normalized = store._normalize_snapshot({
        "models": {
            "learner_model": {"summary": "学习者摘要"},
            "strategy_model": {"summary": "旧教学程序"},
            "context_model": {"summary": "当前探索"},
        }
    })
    self.assertEqual(normalized["models"]["teaching_adaptation_model"]["summary"], "")
    self.assertNotIn("strategy_model", normalized["models"])

def test_prompt_profile_context_excludes_teaching_adaptation_paragraph(self):
    rendered = render_profile_context({"models": {
        "learner_model": {"summary": "学习者摘要"},
        "teaching_adaptation_model": {"summary": "偏好先类比"},
        "context_model": {"summary": "当前探索"},
    }})
    self.assertIn("学习者摘要", rendered)
    self.assertIn("当前探索", rendered)
    self.assertNotIn("偏好先类比", rendered)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Profile or profile' -q`

Expected: failures referencing missing `teaching_adaptation_model` and old `strategy_model` rendering.

- [ ] **Step 3: Implement the canonical model definition and legacy normalization**

Use this canonical metadata:

```python
PROFILE_MODELS = {
    "learner_model": {
        "label": "学习者模型",
        "subtitle": "长期认知画像 — 稳定特征与待验证假设",
        "description": "沉淀跨多轮对话的稳定认知特征、反复困难与待验证掌握状态。",
        "icon": "brain",
        "budget": 300,
    },
    "teaching_adaptation_model": {
        "label": "教学适配模型",
        "subtitle": "Skill 选择 — 个性化重排与过滤依据",
        "description": "描述更适合或应避免的 Skill 类型、认知负荷、教学节奏与验证偏好，不保存具体教学程序。",
        "icon": "compass",
        "budget": 300,
    },
    "context_model": {
        "label": "情境模型",
        "subtitle": "当前场景 — 任务、阶段与情绪",
        "description": "仅描述当前任务、学习阶段、情绪、意图和压力。",
        "icon": "clock",
        "budget": 200,
    },
}
MODEL_NAMES = tuple(PROFILE_MODELS.keys())
EPISODE_MODELS = ("learner_model", "teaching_adaptation_model")
```

Make `render_profile_context()` iterate only `("learner_model", "context_model")`. Make `_normalize_snapshot()` ignore legacy `strategy_model` instead of aliasing its text.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Profile or profile' -q`

Expected: all selected profile tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_eduflowgraph.py EduFlowGraph/profile EduFlowGraph/store/profile_store.py
git commit -m "refactor: define teaching adaptation profile contract"
```

---

### Task 2: SQLite v2 schema migration and render-safe stores

**Files:**
- Modify: `tests/test_sqlite_storage.py`
- Modify: `tests/test_storage_migration.py`
- Modify: `tests/test_web_app_api.py`
- Modify: `EduFlowGraph/store/sqlite_storage.py`
- Modify: `EduFlowGraph/store/sqlite_profile_store.py`
- Modify: `EduFlowGraph/store/migration.py`
- Modify: `EduFlowGraph/pipeline.py`

- [ ] **Step 1: Write failing v1-to-v2 and empty-shape tests**

Create a v1 database fixture with the old CHECK constraint and a non-empty `strategy_model`, then assert:

```python
storage = SQLiteStorage(database_path)
self.assertEqual(storage.schema_version(), 2)
profile = SQLiteLearnerProfileStore(storage).load()
self.assertEqual(
    set(profile["models"]),
    {"learner_model", "teaching_adaptation_model", "context_model"},
)
self.assertEqual(profile["models"]["teaching_adaptation_model"]["summary"], "")
```

Update dashboard error-contract tests to require the same three canonical keys.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_sqlite_storage.py tests/test_storage_migration.py tests/test_web_app_api.py -q`

Expected: schema version and profile-key assertions fail.

- [ ] **Step 3: Implement transactional schema v2 migration**

Set `SCHEMA_VERSION = 2`. When `PRAGMA user_version == 1`, run a transaction equivalent to:

```sql
ALTER TABLE profile_changes RENAME TO profile_changes_v1;
ALTER TABLE profile_models RENAME TO profile_models_v1;
CREATE TABLE profile_models (
    model_name TEXT PRIMARY KEY CHECK (
        model_name IN ('learner_model', 'teaching_adaptation_model', 'context_model')
    ),
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    revisions INTEGER NOT NULL DEFAULT 0
);
INSERT INTO profile_models(model_name, summary, updated_at, revisions)
SELECT model_name, summary, updated_at, revisions
FROM profile_models_v1
WHERE model_name IN ('learner_model', 'context_model');
INSERT INTO profile_models(model_name, summary, updated_at, revisions)
VALUES ('teaching_adaptation_model', '', NULL, 0);
CREATE TABLE profile_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,
    model_name TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (model_name) REFERENCES profile_models(model_name)
);
INSERT INTO profile_changes(changed_at, model_name, note)
SELECT changed_at, model_name, note
FROM profile_changes_v1
WHERE model_name IN ('learner_model', 'context_model');
DROP TABLE profile_changes_v1;
DROP TABLE profile_models_v1;
CREATE INDEX idx_profile_changes_recent ON profile_changes(change_id DESC);
```

Initialize canonical rows after migration. Update stores, migration/export tests, and dashboard fallback shapes.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_sqlite_storage.py tests/test_storage_migration.py tests/test_web_app_api.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_sqlite_storage.py tests/test_storage_migration.py tests/test_web_app_api.py EduFlowGraph/store EduFlowGraph/pipeline.py
git commit -m "feat: migrate profile storage to schema v2"
```

---

### Task 3: Rewrite profile extraction semantics

**Files:**
- Modify: `tests/test_eduflowgraph.py`
- Modify: `EduFlowGraph/profile/consolidator.py`
- Modify: `EduFlowGraph/Prompt/Profile_Update_Prompt.md`
- Modify: `EduFlowGraph/Prompt/Profile_Condense_Prompt.md`
- Modify: `EduFlowGraph/Prompt/Context_Update_Prompt.md`
- Modify: `EduFlowGraph/profile/__init__.py`

- [ ] **Step 1: Write failing semantic-boundary tests**

Add tests asserting that Episode consolidation returns `teaching_adaptation_model`, omits `strategy_model`, and does not place topic-specific procedures in the adaptation summary:

```python
updates = consolidator.consolidate_episode(
    current={
        "learner_model": "",
        "teaching_adaptation_model": "",
        "context_model": "",
    },
    episode=episode,
    concept_result={"concepts": [{"name": "贝叶斯定理"}]},
    skill_evidence={"teaching_actions": ["worked_example"]},
)
self.assertIn("teaching_adaptation_model", updates)
self.assertNotIn("strategy_model", updates)
adaptation = updates["teaching_adaptation_model"]["summary"]
self.assertIn("例题", adaptation)
self.assertNotIn("贝叶斯公式推导步骤", adaptation)
```

Add prompt-content assertions requiring “Skill 选择偏好” and forbidding “下一步教学程序”.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Consolidator or Prompt' -q`

Expected: old strategy key and semantics fail the assertions.

- [ ] **Step 3: Implement new prompt and heuristic consolidation**

Rename all episode update variables and payload keys. The mock path should produce generalized conditional preferences, for example:

```python
if status in {"success", "partial_success"} and primary_action:
    sentence = (
        f"当学生出现{difficulty_label}时，倾向优先选择{action_label}类 Skill，"
        f"并通过{validation_label}确认是否适配；单次效果仍待跨主题验证"
    )
elif status == "failed" and primary_action:
    sentence = (
        f"当学生出现{difficulty_label}时，应降低{action_label}类 Skill 的优先级，"
        "优先尝试不同认知负荷或不同表达路径"
    )
```

The live prompt must demand one paragraph of generalized Skill preferences, negative preferences, pacing, and validation style, while explicitly banning topic-specific procedures.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Consolidator or Prompt or Profile' -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_eduflowgraph.py EduFlowGraph/profile EduFlowGraph/Prompt
git commit -m "refactor: extract teaching adaptation preferences"
```

---

### Task 4: Preserve Qwen reranker relevance scores

**Files:**
- Modify: `tests/test_model_runtime.py`
- Modify: `EduFlowGraph/llm.py`

- [ ] **Step 1: Write failing score-contract tests**

Add tests covering score responses, order-only responses, and invalid scores:

```python
response = {
    "results": [
        {"index": 1, "relevance_score": 0.91},
        {"index": 0, "relevance_score": 0.42},
    ]
}
ranked = client._extract_rerank_results(response, documents)
self.assertEqual(ranked[0]["id"], "skill_b")
self.assertEqual(ranked[0]["rerank"]["relevance_score"], 0.91)
self.assertEqual(ranked[0]["rerank"]["rank"], 0)
```

Assert that existing SiliconFlow payload remains `documents: string[]` and Qwen instruction is present.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_model_runtime.py -k rerank -q`

Expected: `_extract_rerank_results` is absent or score metadata is missing.

- [ ] **Step 3: Implement score-preserving extraction**

Replace the order-only helper with a helper that copies each candidate and attaches:

```python
candidate["rerank"] = {
    "rank": rank,
    "relevance_score": float(score) if score is not None else None,
    "provider": self.reranker_provider,
    "model_id": self.reranker_model_id,
    "source": "reranker",
}
```

Accept `relevance_score` or `score`. Invalid numeric values make the response unusable; order-only items remain usable with `None` scores. Keep the public `rerank()` return type as a list of candidates.
Keep the existing instruction-aware payload contract for the configured `Qwen/Qwen3-Reranker-8B` model.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_model_runtime.py -k rerank -q`

Expected: all reranker tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_model_runtime.py EduFlowGraph/llm.py
git commit -m "feat: preserve reranker relevance scores"
```

---

### Task 5: Implement isolated Skill personalization and filtering

**Files:**
- Create: `tests/test_skill_reranker.py`
- Create: `EduFlowGraph/memory/skill_reranker.py`
- Modify: `EduFlowGraph/memory/__init__.py`

- [ ] **Step 1: Write failing query, scoring, filtering, and fallback tests**

Use a deterministic helper and cover query composition, reordering, all three gates, degraded selection, fallback, and all supported statuses:

```python
def make_candidate(skill_id: str, *, confidence: float, base: float, episode: float, status: str = "candidate") -> dict:
    return {
        "id": skill_id,
        "node": {
            "skill_id": skill_id,
            "node_id": skill_id,
            "node_type": "skill",
            "name": skill_id,
            "status": status,
            "trigger": "学生需要建立直观理解时",
            "difficulty_pattern": "abstraction_gap",
            "teaching_actions": ["concrete_example"],
            "procedure": ["先给具体例子", "再映射回抽象概念"],
            "success_criteria": ["学生能用自己的话复述"],
            "quality": {"confidence": confidence},
        },
        "base_raw_score": base,
        "episode_link_raw_score": episode,
    }

def test_build_query_uses_context_and_adaptation_but_not_learner_model():
    captured: dict[str, str] = {}
    def rerank(query: str, documents: list[dict], kind: str) -> list[dict]:
        captured["query"] = query
        return [
            {**item, "rerank": {"rank": index, "relevance_score": 0.9, "source": "reranker"}}
            for index, item in enumerate(documents)
        ]
    selector = SkillPersonalizedReranker(rerank_fn=rerank)
    selector.select(
        query="解释新概念",
        context_summary="当前处于探索阶段",
        adaptation_summary="优先选择低认知负荷的类比 Skill",
        candidates=[make_candidate("skill_a", confidence=0.8, base=0.8, episode=0.8)],
    )
    assert "探索阶段" in captured["query"]
    assert "低认知负荷" in captured["query"]
    assert "learner_model" not in captured["query"]

def test_low_confidence_skill_is_filtered_even_when_ranked_first():
    def rerank(query: str, documents: list[dict], kind: str) -> list[dict]:
        return [{**documents[0], "rerank": {"rank": 0, "relevance_score": 0.99, "source": "reranker"}}]
    selector = SkillPersonalizedReranker(rerank_fn=rerank)
    result = selector.select(
        query="解释新概念",
        context_summary="探索阶段",
        adaptation_summary="优先类比",
        candidates=[make_candidate("weak", confidence=0.4, base=1.0, episode=1.0)],
    )
    assert result["skills"] == []
    assert result["skill_selection"]["candidates"][0]["filter_reason"] == "low_confidence"

def test_no_candidate_returns_short_fallback_instruction():
    selector = SkillPersonalizedReranker(rerank_fn=None)
    result = selector.select(
        query="解释新概念",
        context_summary="探索阶段",
        adaptation_summary="先用直观类比建立理解。随后逐步进入形式化推导。",
        candidates=[],
    )
    assert result["skills"] == []
    assert result["skill_selection"]["fallback_instruction"] == "先用直观类比建立理解。"
```

Add separate complete tests named `test_qwen_personal_fit_can_reorder_two_skills`, `test_degraded_mode_only_selects_strong_active_or_episode_supported_skill`, and `test_seed_candidate_and_active_are_accepted_statuses`, using the same helper and explicit expected Skill ids.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_skill_reranker.py -q`

Expected: import failure for the new module.

- [ ] **Step 3: Implement `SkillPersonalizedReranker`**

Expose:

```python
@dataclass(frozen=True)
class SkillSelectionConfig:
    min_confidence: float = 0.60
    min_personal_fit: float = 0.35
    min_final_score: float = 0.50
    candidate_pool_size: int = 12
    max_selected: int = 4

class SkillPersonalizedReranker:
    def __init__(
        self,
        rerank_fn: Callable[[str, list[dict[str, Any]], str], list[dict[str, Any]]] | None,
        config: SkillSelectionConfig | None = None,
    ) -> None:
        self.rerank_fn = rerank_fn
        self.config = config or SkillSelectionConfig()

    def select(
        self,
        *,
        query: str,
        context_summary: str,
        adaptation_summary: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return selected Skill nodes plus a render-safe selection trace."""
```

Return a dictionary with `skills` as a list of selected Skill node dictionaries and `skill_selection` containing `candidate_count`, `selected_count`, `reranker_status`, `fallback_instruction`, and `candidates`. Normalize base and episode raw scores by pool maximum, normalize reranker logits with sigmoid, calculate the approved 0.35/0.20/0.15/0.30 formula, record filtering reasons, and extract only the first complete adaptation sentence up to 120 characters for fallback.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_skill_reranker.py -q`

Expected: all new tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_reranker.py EduFlowGraph/memory/skill_reranker.py EduFlowGraph/memory/__init__.py
git commit -m "feat: add personalized skill selection"
```

---

### Task 6: Integrate personalized selection into retrieval and Tutor prompts

**Files:**
- Modify: `tests/test_eduflowgraph.py`
- Modify: `tests/test_web_app_api.py`
- Modify: `EduFlowGraph/memory/retriever.py`
- Modify: `EduFlowGraph/pipeline.py`
- Modify: `EduFlowGraph/Prompt/Tutor_Memory_Augmented_User_Prompt.md`

- [ ] **Step 1: Write failing pipeline integration tests**

Test:

```python
context = pipeline._start_tutor_turn(
    "session_test", "请用直观方式解释这个新概念", memory_mode="memory_augmented"
)["context"]
self.assertIn("skill_selection", context)
self.assertLessEqual(len(context["skills"]), 4)
self.assertNotIn(
    context["profile"]["models"]["teaching_adaptation_model"]["summary"],
    context["profile_context"],
)
```

Add cases for zero Skills, all Skills filtered, reranker failure, and multiple selected Skill blocks. Assert API status 200 and non-empty Tutor messages in every case.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py tests/test_web_app_api.py -k 'skill_selection or adaptation or memory_augmented' -q`

Expected: missing `skill_selection` and old Top-1 behavior failures.

- [ ] **Step 3: Implement orchestration**

Change retrieval to expose up to 12 Skill candidate payloads and their raw evidence components. In `_apply_profile_retrieval()`:

```python
profile = self.profile_store.load()
selection = self.skill_reranker.select(
    query=query,
    context_summary=self.profile_store.summary("context_model"),
    adaptation_summary=self.profile_store.summary("teaching_adaptation_model"),
    candidates=context.get("skill_candidates", []),
)
fused["skills"] = selection["skills"]
fused["skill_selection"] = selection["skill_selection"]
fused["profile"] = profile
fused["profile_context"] = render_profile_context(profile)
```

Render all selected Skill procedures, or a single fallback-control block when none are selected. Never render the full adaptation paragraph in `memory_context_pack`.

- [ ] **Step 4: Run focused and full backend tests**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py tests/test_web_app_api.py tests/test_skill_reranker.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_eduflowgraph.py tests/test_web_app_api.py EduFlowGraph/memory/retriever.py EduFlowGraph/pipeline.py EduFlowGraph/Prompt/Tutor_Memory_Augmented_User_Prompt.md
git commit -m "feat: personalize skill recall with teaching adaptation"
```

---

### Task 7: Update Skill states and frontend contracts

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/skill-display.ts`
- Modify: `web/components/providers/WorkspaceProvider.tsx`
- Modify: `web/components/workspace/LearnerProfileWorkspace.tsx`
- Modify: `web/components/workspace/ContextRail.tsx`
- Modify: `web/components/workspace/chat-trace-utils.ts`
- Modify: `tests/test_eduflowgraph.py`

- [ ] **Step 1: Add failing backend assertions and run frontend typecheck baseline**

Update Skill status assertions to accept exactly `{"seed", "candidate", "active"}` and dashboard profile keys to use `teaching_adaptation_model`.

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Skill or Profile' -q`

Expected: old status/profile assumptions fail where still present.

- [ ] **Step 2: Update TypeScript contracts and UI copy**

Use:

```ts
export type SkillStatus = "seed" | "candidate" | "active";
export type ProfileModelName =
  | "learner_model"
  | "teaching_adaptation_model"
  | "context_model";

export interface SkillSelectionTrace {
  candidate_count: number;
  selected_count: number;
  reranker_status: "ok" | "rank_only" | "degraded" | "skipped";
  fallback_instruction: string;
  candidates: Array<Record<string, unknown>>;
}
```

Profile UI label: `教学适配模型`; subtitle: `Skill 选择 — 个性化重排与过滤依据`. Context rail must render learner/context under “注入的学习者画像” and adaptation separately under “Skill 适配依据”.

- [ ] **Step 3: Run backend tests and TypeScript checks**

Run: `.venv/bin/python -m pytest tests/test_eduflowgraph.py -k 'Skill or Profile' -q`

Run: `npm --prefix web run lint`

Run: `npm --prefix web run build`

Expected: all commands exit 0.

- [ ] **Step 4: Commit**

```bash
git add tests/test_eduflowgraph.py web/lib web/components
git commit -m "feat: show teaching adaptation and skill selection trace"
```

---

### Task 8: Clear test data and perform full verification

**Files:**
- Runtime data: `data/eduflowgraph.db`
- Verify only: entire repository

- [ ] **Step 1: Run the project reset path against the real data directory**

Run:

```bash
.venv/bin/python -c 'from EduFlowGraph.config import load_settings_from_mapping; from EduFlowGraph.pipeline import TutorPipeline; p=TutorPipeline(load_settings_from_mapping({"data_dir":"data","storage_backend":"sqlite","provider":"mock"})); print(p.reset_memory())'
```

Expected: `{'deleted': 'all'}`.

- [ ] **Step 2: Verify database integrity and zero business data**

Run:

```bash
sqlite3 data/eduflowgraph.db "PRAGMA quick_check; PRAGMA foreign_key_check; SELECT 'sessions', COUNT(*) FROM sessions UNION ALL SELECT 'turns', COUNT(*) FROM turns UNION ALL SELECT 'memory_events', COUNT(*) FROM memory_events UNION ALL SELECT 'nodes', COUNT(*) FROM nodes UNION ALL SELECT 'edges', COUNT(*) FROM edges UNION ALL SELECT 'embeddings', COUNT(*) FROM embeddings UNION ALL SELECT 'profile_changes', COUNT(*) FROM profile_changes; SELECT model_name, revisions, length(summary) FROM profile_models ORDER BY model_name;"
```

Expected: `quick_check` returns `ok`, foreign-key check emits no rows, all business counts are 0, and exactly three empty canonical profile rows exist.

- [ ] **Step 3: Run complete backend verification**

Run: `.venv/bin/python -m pytest -q`

Expected: all active tests pass with zero failures.

- [ ] **Step 4: Run frontend verification**

Run: `npm --prefix web run lint`

Run: `npm --prefix web run build`

Expected: both exit 0 with no TypeScript/build errors.

- [ ] **Step 5: Run static legacy-name and diff checks**

Run:

```bash
rg -n "strategy_model|教学策略模型" EduFlowGraph web tests --glob '*.py' --glob '*.md' --glob '*.ts' --glob '*.tsx'
git diff --check
git status --short
```

Expected: legacy names appear only in explicit v1 compatibility/migration tests and code; diff check is clean; unrelated pre-existing files remain untouched.

- [ ] **Step 6: Commit final verification fixes if any**

```bash
git add EduFlowGraph tests web docs/superpowers/plans/2026-06-23-teaching-adaptation-rerank-implementation.md
git commit -m "test: verify teaching adaptation refactor"
```
