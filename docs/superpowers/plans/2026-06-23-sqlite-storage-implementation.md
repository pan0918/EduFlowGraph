# EduFlowGraph SQLite Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the JSON/JSONL primary store with a backward-compatible SQLite backend using JSON payloads, Float32 vector BLOBs, WAL, safe migration, and unchanged API/rendering contracts.

**Architecture:** Keep the existing JSON stores available during migration, add focused SQLite store implementations behind the same behavioral interfaces, and select the backend from `Settings`. SQLite owns current state and audit data; node payloads remain flexible JSON while embeddings live in a dedicated BLOB table. Migration is performed into a temporary database and accepted only after semantic comparison with the legacy stores.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, NumPy Float32 codecs, FastAPI, `unittest`, Node test runner, Next.js production build.

---

### Task 1: Lock Storage and API Contracts

**Files:**
- Create: `tests/test_sqlite_storage.py`
- Modify: `tests/test_eduflowgraph.py`
- Test: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing tests for the desired SQLite foundation API**

```python
class SQLiteStorageContractTest(unittest.TestCase):
    def test_initialization_creates_schema_and_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(Path(tmp) / "eduflowgraph.db")
            self.assertEqual(storage.schema_version(), 1)
            self.assertEqual(storage.journal_mode(), "wal")
            self.assertEqual(storage.quick_check(), "ok")

    def test_empty_snapshot_contract_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = TutorPipeline(load_settings_from_mapping({
                "provider": "mock",
                "data_dir": tmp,
                "storage_backend": "sqlite",
            }))
            snapshot = pipeline.dashboard()
            self.assertEqual(snapshot["concepts"], [])
            self.assertEqual(snapshot["episodes"], [])
            self.assertEqual(snapshot["skills"], [])
            self.assertEqual(snapshot["edges"], [])
            self.assertEqual(set(snapshot["profile"]["models"]), {
                "learner_model", "strategy_model", "context_model"
            })
```

- [ ] **Step 2: Run tests and verify missing SQLite classes/settings fail**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage -v`

Expected: import or assertion failure because SQLite storage is not implemented.

- [ ] **Step 3: Add canonical contract fixtures for turns, events, nodes, edges, and profile**

Create helpers returning one populated session, one Episode, two Concepts, one Skill, graph edges, three profile models, and 32-dimensional deterministic vectors. The fixture must use the exact current API keys from `DashboardSnapshot` and `Turn`.

- [ ] **Step 4: Re-run the focused tests and retain the expected RED state**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage -v`

Expected: failure remains attributable to missing SQLite implementation, not fixture syntax.

### Task 2: Implement SQLite Core, Schema, JSON Codec, and Vector Codec

**Files:**
- Create: `EduFlowGraph/store/sqlite_storage.py`
- Test: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing codec and rollback tests**

```python
def test_vector_codec_round_trip_and_validation(self):
    encoded = encode_vector([0.25, -0.5, 1.0])
    self.assertEqual(encoded.dimensions, 3)
    decoded = decode_vector(encoded.blob, encoded.dimensions)
    np.testing.assert_allclose(decoded, [0.25, -0.5, 1.0], rtol=1e-6)
    with self.assertRaises(StorageDecodeError):
        decode_vector(encoded.blob[:-1], encoded.dimensions)

def test_transaction_rolls_back_all_writes(self):
    with self.storage.transaction() as tx:
        tx.execute("INSERT INTO sessions VALUES (?, ?, ?)", ("s1", NOW, NOW))
        raise RuntimeError("force rollback")
    self.assertEqual(self.storage.fetch_value(
        "SELECT COUNT(*) FROM sessions"
    ), 0)
```

- [ ] **Step 2: Run codec tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteCodecTest -v`

Expected: missing codec/storage symbols.

- [ ] **Step 3: Implement focused SQLite infrastructure**

Implement:

```python
class StorageError(RuntimeError): ...
class StorageDecodeError(StorageError): ...
class StorageIntegrityError(StorageError): ...

@dataclass(frozen=True)
class EncodedVector:
    blob: bytes
    dimensions: int

class SQLiteStorage:
    SCHEMA_VERSION = 1
    def __init__(self, path: Path): ...
    def connect(self) -> sqlite3.Connection: ...
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]: ...
    def schema_version(self) -> int: ...
    def journal_mode(self) -> str: ...
    def quick_check(self) -> str: ...
```

Create all tables and indexes defined in the approved design. Configure every connection with row factory, `foreign_keys=ON`, `busy_timeout=5000`, and `synchronous=NORMAL`; initialize the database with `journal_mode=WAL` and `user_version=1`.

- [ ] **Step 4: Run core tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteStorageContractTest tests.test_sqlite_storage.SQLiteCodecTest -v`

Expected: all selected tests pass.

- [ ] **Step 5: Refactor schema SQL into one versioned migration constant and rerun tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage -v`

Expected: only tests for not-yet-implemented stores remain failing.

### Task 3: Implement SQLite ConversationLog and MemoryFlow

**Files:**
- Create: `EduFlowGraph/store/sqlite_conversation_log.py`
- Create: `EduFlowGraph/store/sqlite_memory_flow.py`
- Modify: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing behavioral parity tests**

Test both classes for all current methods:

```python
turn = log.append_turn(
    session_id="session_a", turn_index=1,
    user_message="为什么？", assistant_message="因为……",
    metadata={"usage": {"total_tokens": 12}},
)
self.assertEqual(log.list_turns("session_a"), [turn.to_dict()])
self.assertEqual(log.next_turn_index("session_a"), 2)
self.assertEqual(log.list_sessions(), ["session_a"])

event = flow.emit("episode_created", "session_a", {
    "episode": episode_with_embedding,
})
stored = flow.list_events()[0]
self.assertNotIn(
    "embedding_vector",
    stored["payload"]["episode"]["retrieval"],
)
self.assertEqual(flow.replay_episodes()[0]["episode_id"], "episode_1")
```

- [ ] **Step 2: Run store tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteConversationLogTest tests.test_sqlite_storage.SQLiteMemoryFlowTest -v`

Expected: missing classes.

- [ ] **Step 3: Implement ConversationLog with deterministic ordering and exact dict shapes**

Implement the existing public methods. Fetch rows inside a closed connection before yielding from `iter_turns()`. Preserve `metadata` as a dict and use `(session_id, turn_index)` as the primary key.

- [ ] **Step 4: Implement MemoryFlow with insertion sequence and recursive vector stripping**

Implement `emit`, `iter_events`, `list_events`, `clear`, and all replay helpers. Unknown event types remain accepted. JSON decode failures raise `StorageDecodeError` containing the event ID.

- [ ] **Step 5: Run focused and legacy store tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteConversationLogTest tests.test_sqlite_storage.SQLiteMemoryFlowTest tests.test_eduflowgraph.ConversationLogTest tests.test_eduflowgraph.MemoryFlowTest -v`

Expected: all selected tests pass.

### Task 4: Implement SQLite GraphStore and Embedding Separation

**Files:**
- Create: `EduFlowGraph/store/sqlite_graph_store.py`
- Modify: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing GraphStore parity tests**

Cover:

```python
store.apply_episode(episode)
store.apply_concept_extraction(
    episode["episode_id"], concepts=[concept], edges=[edge]
)
store.reload()
self.assertIn(episode["node_id"], store.nodes)
self.assertEqual(len(store.edges), 1)
self.assertEqual(
    store.nodes[episode["node_id"]]["retrieval"]["embedding_vector"],
    episode["retrieval"]["embedding_vector"],
)
self.assertNotIn(
    "embedding_vector",
    json.loads(raw_node_payload)["retrieval"],
)
self.assertEqual(raw_embedding_dimensions, 32)
```

Also test direct mutable cache updates followed by `save()`, stale row removal, `reset()+save()`, concept deduplication, skill validation, and retrieval health.

- [ ] **Step 2: Run GraphStore tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteGraphStoreTest -v`

Expected: missing SQLiteGraphStore.

- [ ] **Step 3: Implement SQLiteGraphStore as a compatible GraphStore subclass**

Override `__init__`, `reload`, and `save`; reuse existing graph normalization and business methods. `reload()` joins nodes with embeddings and injects decoded vectors. `save()` reconciles cache in one transaction: upsert nodes/vectors, upsert edges, delete stale edges, then delete stale nodes.

- [ ] **Step 4: Add corrupt BLOB and stale-signature handling**

Corrupt vectors raise `StorageDecodeError`; absent vectors remain valid nodes; stale provider/model/dimensions are counted by the inherited `retrieval_health()` contract.

- [ ] **Step 5: Run graph tests and all existing graph/pipeline unit tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteGraphStoreTest tests.test_eduflowgraph.GraphStoreTest tests.test_eduflowgraph.PipelineIntegrationTest -v`

Expected: all selected tests pass.

### Task 5: Implement SQLite LearnerProfileStore

**Files:**
- Create: `EduFlowGraph/store/sqlite_profile_store.py`
- Modify: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing profile parity tests**

```python
snapshot = store.load()
self.assertEqual(set(snapshot["models"]), set(MODEL_NAMES))
self.assertEqual(snapshot["revision_count"], 0)
updated = store.update_models({
    "learner_model": {"summary": "学习画像", "note": "新增画像"},
    "context_model": {"summary": "当前复习", "note": "更新情境"},
})
self.assertEqual(updated["revision_count"], 2)
self.assertEqual(len(updated["recent_changes"]), 2)
store.clear()
self.assertFalse(store.is_empty() is False)
```

- [ ] **Step 2: Run profile tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteProfileStoreTest -v`

Expected: missing SQLiteLearnerProfileStore.

- [ ] **Step 3: Implement profile store by preserving existing update semantics**

Subclass `LearnerProfileStore`; override persistence methods while reusing `empty_snapshot`, `update_model`, `update_models`, `summary`, `summaries`, and `is_empty`. Always materialize three profile model rows. Bound changes to the same limit as the current store.

- [ ] **Step 4: Run SQLite and legacy profile tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteProfileStoreTest tests.test_eduflowgraph.ProfileStoreTest tests.test_eduflowgraph.ProfileConsolidatorTest -v`

Expected: all selected tests pass.

### Task 6: Add Backend Settings and Wire SQLite into TutorPipeline

**Files:**
- Modify: `EduFlowGraph/config.py`
- Modify: `EduFlowGraph/pipeline.py`
- Modify: `EduFlowGraph/web_app.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `tests/test_sqlite_storage.py`
- Modify: `tests/test_eduflowgraph.py`

- [ ] **Step 1: Add failing configuration and pipeline tests**

Test that `storage_backend` defaults to `sqlite` only after explicit test setup, `database_path` defaults under `data_dir`, JSON remains selectable during migration, and `get_pipeline()` cache separates backend/database paths.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLitePipelineTest -v`

Expected: settings or pipeline backend assertions fail.

- [ ] **Step 3: Add Settings fields and backend factory logic**

```python
@dataclass
class Settings:
    storage_backend: str = "sqlite"
    database_path: Path | None = None

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "eduflowgraph.db"
```

Validate backend in `{"json", "sqlite"}`. Include backend and resolved absolute database path in the web pipeline cache key.

- [ ] **Step 4: Initialize matching stores without changing their consumers**

In SQLite mode create one `SQLiteStorage` and the four SQLite stores. In JSON mode retain current constructors. Change `refresh_from_storage()` to use `graph.reload()` as the current-state source and rebuild buffers from Episode provenance.

- [ ] **Step 5: Preserve Dashboard, session, Turn, and SSE shapes**

Add optional `storage_health` while preserving all existing required fields. Ensure heavy vectors remain stripped before API serialization.

- [ ] **Step 6: Update environment examples and ignore database sidecars**

Add:

```text
EDUFLOW_STORAGE_BACKEND=sqlite
EDUFLOW_DATABASE_PATH=data/eduflowgraph.db
```

Ignore `data/*.db`, `data/*.db-wal`, `data/*.db-shm`, and temporary migration databases.

- [ ] **Step 7: Run pipeline and API tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLitePipelineTest tests.test_eduflowgraph.PipelineIntegrationTest tests.test_eduflowgraph.WebAppApiTest -v`

Expected: all selected tests pass on SQLite.

### Task 7: Make Coupled Memory Writes Atomic

**Files:**
- Modify: `EduFlowGraph/store/sqlite_storage.py`
- Modify: `EduFlowGraph/store/sqlite_graph_store.py`
- Modify: `EduFlowGraph/store/sqlite_memory_flow.py`
- Modify: `EduFlowGraph/store/sqlite_profile_store.py`
- Modify: `EduFlowGraph/pipeline.py`
- Modify: `tests/test_sqlite_storage.py`

- [ ] **Step 1: Add failing fault-injection tests**

Inject an exception after a node write but before the paired MemoryEvent and assert the database contains neither. Repeat for Skill validation, Profile update, reset, and embedding rebuild.

- [ ] **Step 2: Run atomicity tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteAtomicityTest -v`

Expected: partial rows remain before transaction wiring.

- [ ] **Step 3: Add an explicit transaction parameter to SQLite store write methods**

Each SQLite write method accepts an optional SQLite connection. When supplied it never commits or closes; when absent it opens a short transaction. Do not change return values.

- [ ] **Step 4: Refactor Pipeline persistence boundaries**

Complete LLM/extraction computation before entering a write transaction. Persist Episode/Concept/edges/events together; persist Skill changes/events together; persist profile changes/event together. Keep LLM network calls outside transactions.

- [ ] **Step 5: Run atomicity and full SQLite tests**

Run: `.venv/bin/python -m unittest tests.test_sqlite_storage -v`

Expected: all SQLite tests pass and fault injection leaves no partial state.

### Task 8: Implement Safe Legacy Migration and Verification

**Files:**
- Create: `EduFlowGraph/store/migration.py`
- Create: `scripts/migrate_storage.py`
- Create: `tests/fixtures/legacy_storage/`
- Create: `tests/test_storage_migration.py`

- [ ] **Step 1: Create a small valid legacy fixture and failing migration tests**

Fixture includes two sessions, turns, Episode/Concept/Skill nodes, both edge types, events containing duplicated vectors, and a populated three-model profile.

Tests assert dry-run performs no writes, apply creates a temp DB then atomically installs it, vectors are removed from payload JSON/events, and semantic verification succeeds.

- [ ] **Step 2: Add failing corruption/conflict tests**

Cover malformed JSONL, duplicate Turn keys, dangling edge endpoints, duplicate event IDs, vector dimension mismatch, existing destination refusal, and graph snapshot versus MemoryFlow replay mismatch.

- [ ] **Step 3: Run migration tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_storage_migration -v`

Expected: missing migration module/CLI.

- [ ] **Step 4: Implement migration reader, validator, importer, and report**

Implement `dry_run`, `apply`, and `verify`. Never modify legacy files. Write to `eduflowgraph.db.tmp`, run `quick_check`, compare canonical records, and use `os.replace()` only after success. Refuse overwrite by default.

- [ ] **Step 5: Implement CLI with clear exit codes**

Exit 0 on successful dry-run/apply/verify; exit 2 on validation failure; print file and line for malformed JSONL; never print API keys or vectors.

- [ ] **Step 6: Run all migration tests twice**

Run twice: `.venv/bin/python -m unittest tests.test_storage_migration -v`

Expected both times: all tests pass, proving idempotent validation and clean fixture handling.

### Task 9: Add Storage Error Degradation and Frontend Contract Coverage

**Files:**
- Modify: `EduFlowGraph/web_app.py`
- Modify: `web/lib/types.ts`
- Modify: `web/components/providers/WorkspaceProvider.tsx`
- Modify: `tests/test_sqlite_storage.py`
- Modify: `web/components/providers/workspace-session-utils.test.mjs`

- [ ] **Step 1: Add failing backend error contract tests**

Simulate `StorageDecodeError` during dashboard read and assert a complete snapshot with empty lists, three profile models, and `profile.health.status == "error"`. Assert chat persistence errors return failure rather than a successful answer.

- [ ] **Step 2: Repair the currently stale workspace session utility test**

Replace removed `snapshotToMessages`/`snapshotToSessions` imports with `turnsToMessages` and current `composeMessages` tests, so the frontend suite tests the active session API architecture.

- [ ] **Step 3: Run backend and Node tests and verify RED for new behavior**

Run:

```text
.venv/bin/python -m unittest tests.test_sqlite_storage.SQLiteErrorContractTest -v
node --test web/components/providers/workspace-session-utils.test.mjs
```

Expected: backend safe snapshot behavior missing; stale frontend test fails until updated.

- [ ] **Step 4: Implement typed storage error handling and optional storage health type**

Preserve last valid frontend snapshot on polling failure. `storage_health` remains optional so existing snapshots stay valid.

- [ ] **Step 5: Run all frontend tests and production build**

Run:

```text
node --test $(rg --files web -g '*.test.mjs')
cd web && npm run build
```

Expected: 0 failed tests and successful static production build.

### Task 10: Migrate a Real Data Copy and Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `项目重构.md`
- Test: full repository

- [ ] **Step 1: Copy real legacy data to a temporary directory**

Use a temporary directory, not the live `data/` directory. Run migration dry-run and record counts without printing vectors.

- [ ] **Step 2: Apply and verify the temporary migration twice**

Run apply once, verify twice. Compare sessions, turns, events, nodes, edges, profiles, embedding dimensions/hashes, dashboard payload, and fixed retrieval queries.

- [ ] **Step 3: Run full backend tests repeatedly**

Run three times:

```text
.venv/bin/python -m unittest discover -s tests
```

Expected each run: 0 failures and 0 errors. Update `tests/test_model_runtime.py`, `tests/test_diagnostics_api.py`, and `tests/test_web_app_api.py` to import the current `EduFlowGraph` modules. Rename the obsolete monolithic `tests/test_memory_pipeline.py` to `tests/legacy_memory_pipeline_tests.py` only after its still-relevant Store, Retriever, Pipeline, and API assertions have been represented in `tests/test_eduflowgraph.py`, `tests/test_sqlite_storage.py`, and `tests/test_storage_migration.py`; the renamed file remains in the repository as migration reference but is no longer collected as an active suite for deleted modules.

- [ ] **Step 4: Run the smoke flow on SQLite twice**

Run the mock tutoring conversation, force/reach Episode extraction, restart the pipeline, verify retrieval, rebuild embeddings, and reset memory. Repeat from a fresh temporary DB.

- [ ] **Step 5: Run complete frontend verification twice**

Run twice:

```text
node --test $(rg --files web -g '*.test.mjs')
cd web && npm run build
```

Expected each run: 0 test failures and successful build.

- [ ] **Step 6: Update documentation with exact migration and rollback commands**

Document default backend, database path, dry-run/apply/verify, JSON export, WAL sidecars, backup, and rollback. Remove obsolete claims that JSON/JSONL is the primary runtime store.

- [ ] **Step 7: Final integrity and diff review**

Run `PRAGMA quick_check`, inspect `git diff --check`, confirm no embedding arrays exist in SQLite node/event JSON, and confirm only intended project files changed.
