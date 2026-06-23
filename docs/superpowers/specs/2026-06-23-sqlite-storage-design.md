# EduFlowGraph 原生 SQLite 存储重构设计与迁移策略

> 日期：2026-06-23
>
> 状态：待用户审阅
>
> 适用范围：单机、单用户、单学生使用场景
>
> 目标技术：Python `sqlite3` + JSON payload + Float32 BLOB + SQLite WAL

## 1. 背景与决策

EduFlowGraph 当前使用多组 JSON/JSONL 文件保存数据：

- `data/conversations/*.jsonl`：按 session 保存完整 Turn。
- `data/memory_flow.jsonl`：保存记忆状态变更事件。
- `data/graph_nodes.json`：保存 Concept、Episode、Skill 节点。
- `data/graph_edges.json`：保存图边。
- `data/learner_profile.json`：保存三段式学习者画像。

这种实现直观，适合早期 Demo，但已经出现以下明确问题：

1. `GraphStore.save()` 每次写入都会序列化和覆盖完整节点、边文件。
2. 4096 维向量以 JSON 数字数组保存，体积大、解析慢。
3. 向量同时出现在图快照和 MemoryFlow 事件里，形成重复存储。
4. ConversationLog、MemoryFlow、GraphStore、ProfileStore 分别写文件，无法形成跨存储原子事务。
5. 多个 pipeline 实例需要反复 `reload()` 和重放 MemoryFlow 才能看到最新状态。
6. 查询 session、event type、node type 和邻接边都依赖全文件扫描。
7. 文件写入中断时可能得到半写入 JSON，且当前代码对部分解析错误采取静默跳过。

当前样本只有 6 个图节点、4 条边和 8 条 MemoryFlow 事件，但：

- `graph_nodes.json` 约 0.76 MB；
- `memory_flow.jsonl` 约 0.57 MB；
- 6 个节点均包含 4096 维向量。

因此本次设计决定使用一个嵌入式 SQLite 文件作为唯一主存储：

```text
data/eduflowgraph.db
```

不引入 SQLAlchemy、SQLModel、Alembic、独立向量数据库或外部数据库服务。

## 2. 目标

### 2.1 必须实现

1. 保持现有 FastAPI 路由、请求体、SSE 事件和响应结构不变。
2. 保持现有 Store 类的公开读取接口和主要写入接口语义不变。
3. 旧 JSON/JSONL 数据必须可完整迁移，迁移失败时不能破坏原文件。
4. 前端所有 Dashboard、Memory、Profile、Knowledge、Skills、Chat 页面继续获得完整、稳定的数据形状。
5. 向量从节点 JSON 和 MemoryFlow 中分离，统一存为 Float32 BLOB。
6. MemoryFlow 保持 append-only 审计语义，但不再携带向量。
7. 节点、边、事件、画像更新支持事务提交和回滚。
8. 支持单进程内前端轮询读取与后台记忆写入并存。
9. 提供明确的 schema version、迁移验证、回滚和数据导出能力。

### 2.2 不在本次范围内

1. 多用户账号、权限和租户隔离。
2. PostgreSQL、云数据库或分布式存储。
3. 专用向量数据库。
4. 全文搜索引擎。
5. 修改 Concept、Episode、Skill 的业务语义。
6. 修改 Tutor、检索、画像和前端交互逻辑。
7. 删除旧数据文件；旧文件至少保留一个迁移观察周期。

## 3. 总体架构

```text
FastAPI / TutorPipeline
          │
          ▼
     Store Facades
     ├── ConversationLog
     ├── MemoryFlow
     ├── GraphStore
     └── LearnerProfileStore
          │
          ▼
      SQLiteStorage
     ├── connection factory
     ├── transaction manager
     ├── schema migrations
     ├── JSON codec
     └── vector codec
          │
          ▼
   data/eduflowgraph.db
```

Store 类继续承担领域接口；`SQLiteStorage` 只负责数据库连接、事务、schema 和编码，不包含教育业务规则。

### 3.1 数据职责

| 数据 | 事实来源 | 用途 |
|---|---|---|
| Turn | `turns` | 对话回放、历史消息、Episode 抽取 |
| MemoryEvent | `memory_events` | 状态变化审计、调试、事件统计 |
| Concept/Episode/Skill | `nodes` | 当前图节点物化状态 |
| Episode-Concept/Episode-Skill | `edges` | 当前图关系物化状态 |
| 三段画像 | `profile_models` | 当前学习者画像 |
| 画像变更 | `profile_changes` | 最近画像修改记录 |
| Embedding | `embeddings` | 检索和相似概念匹配 |

`nodes`、`edges`、`profile_models` 是当前状态；`memory_events` 是审计日志。正常启动直接读取物化状态，不再依赖完整事件重放来恢复图。

## 4. SQLite Schema

所有时间继续保存 UTC ISO-8601 字符串，避免改变现有 API 数据格式。

### 4.1 `sessions`

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Session 标题仍由第一条用户消息派生，不在表中重复维护。

### 4.2 `turns`

```sql
CREATE TABLE turns (
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, turn_index),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_turns_session_timestamp
ON turns(session_id, timestamp);
```

`metadata_json` 保留 usage、reasoning 和未来可选字段。

### 4.3 `memory_events`

```sql
CREATE TABLE memory_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_memory_events_type_sequence
ON memory_events(event_type, sequence);

CREATE INDEX idx_memory_events_session_sequence
ON memory_events(session_id, sequence);
```

`sequence` 保证严格插入顺序。读取不能依赖时间戳排序，因为多个事件可能具有相同秒级时间。

### 4.4 `nodes`

```sql
CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL CHECK (node_type IN ('concept', 'episode', 'skill')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_nodes_type_updated
ON nodes(node_type, updated_at);
```

`payload_json` 保存当前节点完整业务字段，但不保存 `retrieval.embedding_vector`。保留 JSON payload 是为了继续兼容不同节点 schema，并避免一次性拆出大量稀疏列。

### 4.5 `edges`

```sql
CREATE TABLE edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX idx_edges_source_type ON edges(source, edge_type);
CREATE INDEX idx_edges_target_type ON edges(target, edge_type);
```

### 4.6 `profile_models`

```sql
CREATE TABLE profile_models (
    model_name TEXT PRIMARY KEY CHECK (
        model_name IN ('learner_model', 'strategy_model', 'context_model')
    ),
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    revisions INTEGER NOT NULL DEFAULT 0
);
```

数据库初始化时始终插入三行空模型，保证前端永远能读取完整画像结构。

### 4.7 `profile_changes`

```sql
CREATE TABLE profile_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,
    model_name TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (model_name) REFERENCES profile_models(model_name)
);

CREATE INDEX idx_profile_changes_recent
ON profile_changes(change_id DESC);
```

读取时只返回最近的固定数量，写入后可删除超出保留上限的旧记录。

### 4.8 `embeddings`

```sql
CREATE TABLE embeddings (
    node_id TEXT PRIMARY KEY,
    vector_blob BLOB NOT NULL,
    dimensions INTEGER NOT NULL,
    dtype TEXT NOT NULL DEFAULT 'float32-le',
    provider TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX idx_embeddings_signature
ON embeddings(provider, model_id, dimensions);
```

向量编码规则固定为 little-endian Float32：

```python
numpy.asarray(vector, dtype="<f4").tobytes(order="C")
```

读取时必须校验：

1. `dimensions > 0`；
2. `len(vector_blob) == dimensions * 4`；
3. 解码结果不包含 NaN 或 Infinity；
4. metadata dimensions 与实际维数一致。

4096 维向量编码后固定为 16384 字节，不再承担 JSON 数字文本和重复事件副本的开销。

### 4.9 Schema 版本

使用 SQLite 原生 `PRAGMA user_version` 管理版本，不引入 Alembic。

每次迁移必须：

1. 在单个事务中运行；
2. 检查当前版本；
3. 只执行相邻版本升级；
4. 成功后更新 `user_version`；
5. 失败时完整回滚。

## 5. JSON 与向量编解码

### 5.1 JSON 规范

统一使用：

```python
json.dumps(value, ensure_ascii=False, separators=(",", ":"))
```

写入前验证顶层类型。读取失败不能静默丢弃，必须抛出带表名和主键的 `StorageDecodeError`。

### 5.2 节点读取兼容

数据库内的 `payload_json` 不含向量，但 Store 内部读取节点时需要恢复现有结构：

```text
nodes.payload_json
       +
embeddings.vector_blob
       ↓
node["retrieval"]["embedding_vector"]
```

因此现有 Retriever、Concept 相似度匹配和 `GraphStore.retrieval_health()` 不需要感知 BLOB。

Dashboard 继续在 `_strip_heavy_fields()` 中移除 `embedding_vector`，不会把 BLOB 或解码后的大数组发送给前端。

### 5.3 MemoryFlow 去重规则

MemoryFlow 的事件名称和 payload 顶层结构保持兼容，但写入前递归删除：

- `retrieval.embedding_vector`
- 任何名为 `embedding_vector` 的嵌套字段
- 原始 BLOB

保留以下兼容能力：

- `episode_created.payload.episode` 仍存在，但不带向量；
- `concept_extracted.payload.concepts` 和 `edges` 仍存在，但 concepts 不带向量；
- `skill_distilled.payload.skill` 和 `edges` 仍存在，但 skill 不带向量；
- `skill_validated.payload.skill` 和 `edge` 仍存在，但 skill 不带向量；
- `replay_episodes()`、`replay_concept_extractions()`、`replay_skill_distillations()` 和 `replay_skill_validations()` 继续返回相同类别的数据。

这样既消除最大重复项，又不破坏现有调试和回放接口。

## 6. Store 接口兼容设计

### 6.1 `ConversationLog`

以下方法保持签名和返回结构：

| 方法 | SQLite 行为 |
|---|---|
| `append_turn()` | 在事务中 upsert session 并插入 Turn |
| `iter_turns()` | 按 `turn_index ASC` 返回 dict iterator |
| `list_turns()` | 返回完整 Turn dict 列表 |
| `next_turn_index()` | 使用 `COALESCE(MAX(turn_index), 0) + 1` |
| `list_sessions()` | 返回至少有一个 Turn 的 session ID |
| `session_messages()` | 保持 OpenAI message 格式和 limit 语义 |
| `render_for_extraction()` | 保持现有文本格式 |
| `clear_session()` | 删除对应 session，级联删除 Turn |
| `clear_all()` | 删除全部 session 与 Turn |

`iter_turns()` 在连接关闭前先获取稳定行集，再生成 dict，避免 generator 长时间持有数据库连接。

### 6.2 `MemoryFlow`

以下方法保持兼容：

| 方法 | SQLite 行为 |
|---|---|
| `emit()` | 插入事件并返回 `MemoryEvent` |
| `iter_events()` | 按 `sequence ASC` 返回事件 |
| `list_events()` | 返回事件列表 |
| `clear()` | 删除所有事件并保留表结构 |
| `replay_*()` | 从兼容 payload 中提取对应对象 |

未知 event type 保持可写，以支持未来扩展；`MEMORY_EVENT_TYPES` 继续用于文档和校验提示，不在数据库层做封闭 CHECK。

### 6.3 `GraphStore`

当前 Pipeline 和 Retriever 会直接访问 `graph.nodes`、`graph.edges`，并会修改由 `nodes_by_type()` 返回的节点后调用 `save()`。第一阶段必须兼容这种行为。

设计为：

- `reload()`：从 `nodes`、`edges`、`embeddings` 重建内存 cache；
- `.nodes`：保持 `dict[node_id, node]`；
- `.edges`：保持 `list[edge]`；
- `save()`：在一个事务中将 cache 与数据库当前快照对齐；
- `reset()`：清空 cache；随后 `save()` 会清空数据库节点和边；
- `nodes_by_type()`：继续返回 cache 中的节点对象；
- 所有 `apply_*`、`upsert_*` 和 `_upsert_edge()` 方法继续更新 cache，并在 `save=True` 时提交数据库；
- `find_existing_concept()`、`find_similar_concept_by_embedding()` 和 `retrieval_health()` 返回语义不变。

`save()` 不再覆盖文件，但为兼容 mutable cache，需要执行 snapshot reconciliation：

1. upsert cache 中全部节点和向量；
2. upsert cache 中全部边；
3. 删除数据库中已不在 cache 的边；
4. 删除数据库中已不在 cache 的节点及其向量；
5. 单事务提交。

当前节点规模很小，这个兼容策略足够轻量。后续可逐步把 Pipeline 的直接 dict 修改改为显式 repository 方法，再将 `save()` 收紧为仅提交 dirty rows；这不属于本次迁移的必要条件。

### 6.4 `LearnerProfileStore`

保持以下输出结构不变：

```json
{
  "models": {
    "learner_model": {"summary": "", "updated_at": null, "revisions": 0},
    "strategy_model": {"summary": "", "updated_at": null, "revisions": 0},
    "context_model": {"summary": "", "updated_at": null, "revisions": 0}
  },
  "recent_changes": [],
  "updated_at": null,
  "revision_count": 0,
  "health": {"status": "ok", "message": ""}
}
```

方法兼容要求：

- `load()` 始终返回完整三模型结构；
- `empty_snapshot()` 结构不变；
- `update_model()`、`update_models()` 保持 revision 和 recent_changes 语义；
- `summary()`、`summaries()`、`is_empty()` 语义不变；
- `clear()` 重置三行模型和画像变更；
- `migrate_legacy_if_needed()` 在 SQLite 模式下成为幂等兼容入口。

### 6.5 `TutorPipeline.refresh_from_storage()`

不再通过重放 MemoryFlow 重建 GraphStore。新流程：

```text
graph.reload()
  ↓
读取所有 Episode provenance.turn_range
  ↓
从 turns 重建尚未被 Episode 消费的 Buffer
```

MemoryFlow 仍可用于审计和手工重放测试，但不是正常启动路径的唯一事实来源。

## 7. API 与前端渲染兼容

### 7.1 不允许改变的 API

- `GET /api/dashboard`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}/turns`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/extract`
- `POST /api/diagnostics/model-test`
- `POST /api/rebuild-retrieval`
- `POST /api/reset-memory`

请求字段、返回字段和 SSE `type` 保持不变。

### 7.2 Dashboard 必须保持的字段

```text
concepts          list
episodes          list
skills            list
edges              list
profile            object，且包含完整三个 model
memory_events      list
memory_flow_count  integer
```

所有列表在无数据时必须返回 `[]`，不能返回 `null` 或缺失字段。

### 7.3 Sessions 与 Turns

`/api/sessions` 继续返回：

```text
id
title
message_count
last_updated
```

`/api/sessions/{session_id}/turns` 继续返回 Turn dict，字段和 metadata 结构不变。前端 `turnsToMessages()` 不需要修改。

### 7.4 读取失败的降级规则

数据库错误不能被伪装成空数据。采用以下规则：

1. Store 层抛出明确的 `StorageError` 子类。
2. Chat 写入失败时请求失败，不能返回“成功但未保存”。
3. Dashboard 读取失败时返回结构完整的安全快照，并设置：

```json
"profile": {
  "health": {
    "status": "error",
    "message": "存储读取失败：..."
  }
}
```

4. 前端继续保留最后一次有效 snapshot；首次启动无有效 snapshot 时使用现有 `EMPTY_SNAPSHOT`。
5. 任何错误响应不得包含数据库文件内容、API key 或完整 embedding。

这样页面不会因为字段缺失而渲染崩溃，同时错误也不会被静默吞掉。

## 8. 事务、连接与 WAL

### 8.1 连接策略

不跨线程共享 SQLite connection。每个 Store 操作或事务从 connection factory 获取当前线程连接，完成后关闭。

不通过 `check_same_thread=False` 共享全局连接，以免把并发正确性交给调用方。

### 8.2 每个连接的 PRAGMA

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

数据库初始化时执行：

```sql
PRAGMA journal_mode = WAL;
```

### 8.3 事务边界

`SQLiteStorage.transaction()` 提供一个显式 Unit of Work：

```python
with storage.transaction() as transaction:
    graph_store.apply_episode(..., transaction=transaction)
    graph_store.apply_concept_extraction(..., transaction=transaction)
    memory_flow.emit(..., transaction=transaction)
```

事务对象持有本次操作唯一的 connection。Store 在收到 transaction 时必须复用它且不得自行 commit；未收到 transaction 时，Store 为单个公开操作创建并提交短事务。事务上下文不能使用进程级全局变量传递，也不能跨请求复用。

以下操作必须原子提交：

1. 创建 Episode + Concept 节点 + Episode-Concept 边 + MemoryEvent；
2. Skill distillation + Skill 边 + MemoryEvent；
3. Skill validation + Skill 质量更新 + validation edge + MemoryEvent；
4. Profile models 更新 + profile_changes + profile_updated event；
5. reset memory 清理 turns、events、nodes、edges、embeddings 和 profile；
6. retrieval embedding rebuild 更新全部 embedding 和 metadata。

LLM 调用不能放在数据库事务中。正确顺序是：

```text
读取输入状态 → 关闭连接 → 调用 LLM → 打开短事务写入结果
```

避免网络调用期间长期持有写锁。

### 8.4 WAL 文件管理

WAL 模式可能产生：

- `eduflowgraph.db-wal`
- `eduflowgraph.db-shm`

它们属于正常运行文件，需要加入 `.gitignore`。正常关闭或适当 checkpoint 后 SQLite 会管理其大小，不应由应用直接删除。

## 9. 检索与向量策略

本次不引入 `sqlite-vec`。原因：

1. 当前只有个位数节点；
2. NumPy 已经是现有依赖；
3. 暴力余弦相似度实现已经存在；
4. 引入扩展会增加安装、平台兼容和故障面。

当前检索过程：

1. 查询需要参与检索的节点及 embedding BLOB；
2. 解码为 Float32；
3. 使用现有 NumPy/余弦逻辑计算；
4. 保持现有 Concept → Episode → Skill 召回与 rerank 流程。

满足以下任一条件时再评估 `sqlite-vec`：

- 节点数量持续超过 10,000；
- 单次向量召回稳定超过 50 ms；
- BLOB 全量读取成为已测量的主要瓶颈。

## 10. 旧数据迁移设计

### 10.1 迁移原则

1. 原文件只读，不原地修改。
2. 在临时数据库中完成全部导入和验证。
3. 未通过验证时不切换 backend。
4. 不做持续双写，避免两个事实来源长期分叉。
5. 切换后保留旧文件，允许即时回滚。

### 10.2 Backend 开关

过渡期增加：

```text
EDUFLOW_STORAGE_BACKEND=json|sqlite
EDUFLOW_DATABASE_PATH=data/eduflowgraph.db
```

阶段性默认值：

1. 开发和迁移验证阶段默认 `json`；
2. SQLite 合同测试和数据对比全部通过后切换默认 `sqlite`；
3. 保留 `json` backend 一个观察周期用于回滚；
4. 稳定后删除 JSON 写入 backend，但保留 JSON 导入/导出工具。

`Settings` 增加 `storage_backend` 和 `database_path`，但不改变现有 LLM、Embedding、Reranker 或前端 runtime 配置。`web_app.get_pipeline()` 的 cache key 必须加入 backend 和数据库绝对路径，避免 JSON pipeline 与 SQLite pipeline 或不同数据目录错误共享实例。

### 10.3 迁移工具

提供独立命令，例如：

```text
python scripts/migrate_storage.py --data-dir data --dry-run
python scripts/migrate_storage.py --data-dir data --verify
python scripts/migrate_storage.py --data-dir data --apply
```

工具必须在应用停止写入时运行。若检测到目标数据库已存在，默认拒绝覆盖。

### 10.4 预检查

迁移前检查：

1. 所有 JSON 文件可完整解析；
2. 所有 JSONL 非空行可解析；
3. node ID 唯一；
4. edge ID 唯一；
5. edge source/target 均指向已存在节点；
6. Episode provenance 的 session 和 turn_range 合法；
7. Turn `(session_id, turn_index)` 唯一；
8. MemoryEvent event_id 唯一；
9. embedding 维度、metadata 和向量长度一致；
10. profile 可以归一化成三模型结构。

当前旧代码会静默跳过损坏 JSONL 行；迁移工具不能沿用此行为。发现损坏行时默认中止，并输出文件、行号和错误，不自动丢弃。

### 10.5 导入顺序

在 `data/eduflowgraph.db.tmp` 中：

1. 创建 schema 并设置 `user_version`；
2. 导入 sessions；
3. 导入 turns；
4. 导入 nodes，提取并移除 `embedding_vector`；
5. 将向量编码后导入 embeddings；
6. 导入 edges；
7. 导入 memory_events，递归移除 embedding；
8. 导入 profile_models 和 profile_changes；
9. 运行验证；
10. 成功后原子重命名为 `data/eduflowgraph.db`。

### 10.6 数据冲突判断

旧系统中 MemoryFlow 可重放图状态，而 `graph_nodes.json` / `graph_edges.json` 是物化快照。迁移前需要用旧逻辑在内存中重放 MemoryFlow，并与图快照比较：

- 节点 ID、类型、业务字段一致；
- 边 ID、source、target、type、weight 一致；
- embedding 单独比较维度和内容 hash。

若不一致，迁移默认中止并生成差异报告，不擅自选择一方覆盖另一方。

### 10.7 迁移验证

验证同时比较旧 backend 和 SQLite backend：

| 数据 | 验证方式 |
|---|---|
| sessions | ID 集合、首条消息标题、消息数、最后更新时间 |
| turns | 全字段逐 Turn 比较 |
| memory events | event_id、顺序、type、session、去向量后的 payload |
| nodes | node_id、node_type、去向量后的 payload |
| embeddings | dimensions、provider、model_id、Float32 hash、余弦自相似度 |
| edges | edge_id 和全部业务字段 |
| profile | 完整 snapshot 语义比较 |
| dashboard | 规范化 JSON 比较 |
| retrieval | 固定 query 的 Top-K node ID 和顺序比较 |

允许的差异仅包括：

- JSON 空白和 key 顺序；
- Float64 JSON 数字转 Float32 后的预期精度差异；
- MemoryFlow 中被刻意移除的 embedding 字段。

### 10.8 切换与回滚

切换步骤：

1. 停止应用写入；
2. 运行迁移和验证；
3. 备份当前 legacy 文件清单及 hash；
4. 设置 backend 为 `sqlite`；
5. 启动后运行 health、dashboard、sessions、turns、mock chat 和 retrieval smoke tests；
6. 确认页面可渲染后恢复正常使用。

回滚步骤：

1. 停止应用；
2. 将 backend 改回 `json`；
3. 使用未被修改的旧文件启动；
4. 保留失败 SQLite DB 和日志用于诊断。

切换后的新数据不会自动回写旧 JSON。因此回滚窗口内如果 SQLite 已产生新对话，需要先运行 SQLite → JSON 导出，再决定是否回滚。切换后的首次真实使用前应完成全部 smoke tests，尽量避免产生分叉数据。

## 11. 测试设计

### 11.1 SQLite 基础测试

- schema 首次创建；
- schema 重复初始化幂等；
- `PRAGMA user_version` 升级；
- WAL 和 foreign_keys 生效；
- JSON codec 中文和嵌套对象 round-trip；
- Float32 BLOB round-trip；
- 维度不一致、损坏 BLOB、NaN/Infinity 被拒绝；
- transaction exception 后无部分写入；
- foreign key 和级联删除正确。

### 11.2 Store 合同测试

现有 Store 测试应参数化运行在 legacy JSON 和 SQLite 两个 backend 上，断言相同公开行为：

- ConversationLog 全部方法；
- MemoryFlow 全部方法和事件顺序；
- GraphStore CRUD、mutable cache、reload、save、reset、检索健康度；
- LearnerProfileStore 空结构、更新、revision、recent changes、clear。

### 11.3 Pipeline 集成测试

- mock chat 保存完整 Turn；
- streaming answer 落盘后可立即从 session API 读取；
- Episode 抽取同时写节点、边、事件和画像；
- 故意在写入中途抛错时全部回滚；
- restart 后 Buffer 能正确排除已消费 Turn；
- retrieval embedding rebuild 不在 event payload 中重复向量；
- reset memory 原子清空所有业务表并恢复空画像结构。

### 11.4 API 合同测试

对 SQLite backend 运行当前 API 测试，并增加：

- 空数据库 Dashboard 结构完整；
- populated Dashboard 与 legacy backend 语义一致；
- sessions 和 turns 数据形状不变；
- SSE context、delta、answer、memory、final 事件不变；
- storage error 返回结构可控且不泄露敏感数据；
- dashboard 读取失败不会返回缺字段对象。

### 11.5 前端渲染测试

至少使用以下 fixture 验证：

1. 完全空 snapshot；
2. 只有 Conversation，无图节点；
3. 有 Concept/Episode/Skill/Edge/Profile 的完整 snapshot；
4. embedding 缺失或 stale；
5. profile health 为 error；
6. recent_changes 为空或达到上限；
7. MemoryFlow 无事件或有事件。

必须运行：

```text
node --test <全部前端测试>
npm run build
```

### 11.6 迁移验收测试

- 使用真实 `data/` 的只读副本迁移；
- 迁移前后统计完全一致；
- Dashboard 规范化比较通过；
- 固定检索 query 结果一致；
- 前端生产构建通过；
- 启动栈后 Chat、Memory、Knowledge、Profile、Skills、Settings 均可打开；
- 页面无 hydration、undefined property 或 JSON decode 错误。

## 12. 可观测性与维护

新增存储健康信息，但不破坏现有 Dashboard 字段：

```json
{
  "storage_health": {
    "backend": "sqlite",
    "schema_version": 1,
    "journal_mode": "wal",
    "database_size_bytes": 0,
    "wal_size_bytes": 0,
    "integrity": "ok"
  }
}
```

`storage_health` 为可选新增字段，旧前端可忽略，新前端后续可展示。

维护命令应支持：

- `PRAGMA quick_check` 健康检查；
- JSON 导出；
- SQLite 备份；
- embedding 重建；
- 迁移 dry-run 和差异报告。

## 13. 分阶段迁移计划

### 阶段 A：基础设施与合同锁定

1. 为现有 API、Store 和 Dashboard 增加合同测试。
2. 固化 populated/empty snapshot fixtures。
3. 新增 `SQLiteStorage`、schema migration、JSON codec、vector codec。
4. 不切换现有 backend。

完成标准：SQLite 基础测试通过，现有 JSON 行为无变化。

### 阶段 B：Store SQLite 实现

1. 实现 SQLite ConversationLog。
2. 实现 SQLite MemoryFlow。
3. 实现 SQLite GraphStore cache compatibility。
4. 实现 SQLite LearnerProfileStore。
5. 使用相同合同测试验证两个 backend。

完成标准：两个 backend 的 Store 合同结果一致。

### 阶段 C：Pipeline 原子写入与读取切换

1. Pipeline 初始化共享 SQLiteStorage 配置。
2. `refresh_from_storage()` 改为直接加载物化图。
3. Episode、Skill、Profile 相关写入收敛为短事务。
4. reset 和 embedding rebuild 改为原子操作。
5. API 契约保持不变。

完成标准：全部 Pipeline 和 API 测试在 SQLite backend 通过。

### 阶段 D：迁移工具与真实数据验证

1. 实现 dry-run、apply、verify。
2. 对真实数据副本运行迁移。
3. 生成统计、hash、snapshot 和 retrieval 差异报告。
4. 修复所有非允许差异。

完成标准：迁移报告无未解释差异，旧数据可以完整读取。

### 阶段 E：前端与端到端验收

1. 运行空数据和真实数据页面渲染检查。
2. 运行 SSE Chat、强制抽取、检索重建和 reset 流程。
3. 运行全部 Python、Node 测试和 Next production build。
4. 检查浏览器控制台和后端日志。

完成标准：无字段缺失、读取错误、页面崩溃或数据丢失。

### 阶段 F：默认切换与观察

1. SQLite 成为默认 backend。
2. 旧 JSON backend 和文件保留一个观察周期。
3. 记录数据库体积、WAL 体积和检索延迟。
4. 稳定后移除 JSON 写入实现，保留导入/导出。

完成标准：真实使用稳定，回滚窗口关闭前完成最终备份。

## 14. 验收标准

只有同时满足以下条件，SQLite 迁移才可视为完成：

1. 旧 conversations、events、nodes、edges、profile 全部迁移且验证通过。
2. 所有 embedding 都能解码，维度和模型签名正确。
3. MemoryFlow 不再包含 embedding 数组。
4. Store 公开读取接口保持兼容。
5. Dashboard、sessions、turns、SSE API 契约保持兼容。
6. 空数据和真实数据均能完成前端生产渲染。
7. Chat、Episode 抽取、Skill、Profile、retrieval 和 reset 全链路通过。
8. 任一事务失败都不会留下部分状态。
9. 迁移可 dry-run、可验证、可回滚。
10. 完整 Python 测试、Node 测试和 Next build 全部通过。

## 15. 最终推荐

采用以下最小而完整的方案：

```text
Python sqlite3
+ 单个 eduflowgraph.db
+ JSON payload 保持节点 schema 灵活
+ Float32 little-endian BLOB 独立保存 embedding
+ WAL 支持前台读取与后台短写入
+ Store facade 保持现有接口
+ PRAGMA user_version 管理 schema
+ 临时 DB 迁移、双读验证、单次切换、旧文件回滚
```

这个方案优先保证现有数据、Pipeline、API 和前端渲染兼容，同时解决当前最明显的文件重写、重复向量、查询效率和原子性问题。
