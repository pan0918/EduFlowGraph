# EduFlowGraph API 文档

> **版本**: 1.0 · **最后更新**: 2026-06-29 · **Base URL**: `http://127.0.0.1:8000`

---

## 目录

1. [概述](#1-概述)
2. [认证与跨域](#2-认证与跨域)
3. [通用数据结构](#3-通用数据结构)
4. [端点参考](#4-端点参考)
5. [SSE 流式协议](#5-sse-流式协议)
6. [错误处理](#6-错误处理)

---

## 1. 概述

EduFlowGraph 后端通过 FastAPI 提供 RESTful API，所有端点以 `/api/` 为前缀。聊天端点同时支持同步请求和 SSE（Server-Sent Events）流式响应。

### 1.1 端点总览

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/dashboard` | 仪表盘快照 |
| `POST` | `/api/chat` | 同步聊天 |
| `POST` | `/api/chat/stream` | 流式聊天（SSE） |
| `POST` | `/api/extract` | 强制 Episode 提取 |
| `POST` | `/api/diagnostics/model-test` | 模型连接测试 |
| `POST` | `/api/rebuild-retrieval` | 重建检索向量 |
| `POST` | `/api/reset-memory` | 重置所有记忆 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/sessions/{session_id}/turns` | 会话轮次详情 |

### 1.2 请求格式

所有 POST 端点接受 `application/json` 请求体。请求模型通过 Pydantic 定义，所有字段均有默认值。

### 1.3 响应格式

所有响应均为 `application/json`，流式端点为 `text/event-stream`。

---

## 2. 认证与跨域

### 2.1 认证

当前版本**无需认证**。所有端点均可匿名访问。

### 2.2 CORS 配置

允许的来源：

| 来源 | 说明 |
|------|------|
| `http://127.0.0.1:3000` | Next.js 开发服务器 |
| `http://localhost:3000` | Next.js 开发服务器（localhost） |
| `http://127.0.0.1:3001` | 备用前端端口 |
| `http://localhost:3001` | 备用前端端口（localhost） |

### 2.3 缓存策略

所有 `/api/` 路径的响应头包含 `Cache-Control: no-store`，禁用浏览器缓存。

---

## 3. 通用数据结构

### 3.1 请求模型

#### `ChatRequest`

聊天请求模型，用于 `/api/chat` 和 `/api/chat/stream`。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `session_id` | `string` | `"session_demo"` | 会话标识符 |
| `message` | `string` | —（必填） | 用户消息内容 |
| `memory_mode` | `string` | `"ordinary"` | 记忆模式：`"ordinary"` 或 `"augmented"` |
| `runtime` | `object \| null` | `null` | 运行时配置覆盖（见下方） |
| `provider` | `string` | `"mock"` | 提供者模式 |
| `api_key` | `string` | `""` | API Key |
| `base_url` | `string` | `"https://api.openai.com/v1"` | API 基础 URL |
| `chat_model` | `string` | `"gpt-4o-mini"` | 聊天模型 ID |
| `embedding_model` | `string` | `"text-embedding-3-small"` | 嵌入模型 ID |
| `extraction_turns` | `int` | `4` | Episode 提取触发轮次数 |

**`runtime` 对象结构**（可选，覆盖顶层配置）：

```json
{
  "llm": {
    "provider": "openai-compatible",
    "api_key": "sk-...",
    "base_url": "https://api.openai.com/v1",
    "model_id": "gpt-4o-mini"
  },
  "embedding": {
    "provider": "openai-compatible",
    "api_key": "sk-...",
    "endpoint_url": "https://api.openai.com/v1/embeddings",
    "model_id": "text-embedding-3-small"
  },
  "reranker": {
    "provider": "openai-compatible",
    "api_key": "sk-...",
    "endpoint_url": "https://api.openai.com/v1/rerank",
    "model_id": ""
  }
}
```

#### `ExtractRequest`

强制提取请求模型，用于 `/api/extract`。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `session_id` | `string` | `"session_demo"` | 会话标识符 |
| `runtime` | `object \| null` | `null` | 运行时配置覆盖 |
| `provider` | `string` | `"mock"` | 提供者模式 |
| `api_key` | `string` | `""` | API Key |
| `base_url` | `string` | `"https://api.openai.com/v1"` | API 基础 URL |
| `chat_model` | `string` | `"gpt-4o-mini"` | 聊天模型 ID |
| `embedding_model` | `string` | `"text-embedding-3-small"` | 嵌入模型 ID |
| `extraction_turns` | `int` | `4` | Episode 提取触发轮次数 |

#### `DiagnosticsRequest`

诊断请求模型，用于 `/api/diagnostics/model-test`。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `kind` | `string` | —（必填） | 测试类型：`"llm"`、`"embedding"` 或 `"reranker"` |
| `runtime` | `object \| null` | `null` | 运行时配置覆盖 |
| `provider` | `string` | `"mock"` | 提供者模式 |
| `api_key` | `string` | `""` | API Key |
| `base_url` | `string` | `"https://api.openai.com/v1"` | API 基础 URL |
| `chat_model` | `string` | `"gpt-4o-mini"` | 聊天模型 ID |
| `embedding_model` | `string` | `"text-embedding-3-small"` | 嵌入模型 ID |

#### `RebuildRetrievalRequest`

重建检索请求模型，用于 `/api/rebuild-retrieval` 和 `/api/reset-memory`。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `data_dir` | `string` | `"data"` | 数据目录路径 |
| `runtime` | `object \| null` | `null` | 运行时配置覆盖 |
| `provider` | `string` | `"mock"` | 提供者模式 |
| `api_key` | `string` | `""` | API Key |
| `base_url` | `string` | `"https://api.openai.com/v1"` | API 基础 URL |
| `chat_model` | `string` | `"gpt-4o-mini"` | 聊天模型 ID |
| `embedding_model` | `string` | `"text-embedding-3-small"` | 嵌入模型 ID |

### 3.2 响应模型

#### `DashboardSnapshot`

仪表盘快照，由 `/api/dashboard` 和其他端点的 `snapshot` 字段返回。

```json
{
  "concepts": [
    {
      "node_id": "concept_...",
      "name": "贝叶斯定理",
      "structural_role": "main",
      "salience": 0.95,
      "updated_at": "2026-06-29T14:30:52Z"
    }
  ],
  "episodes": [
    {
      "node_id": "episode_...",
      "episode_type": "concept_explanation",
      "title": "...",
      "outcome": {"status": "success"},
      "updated_at": "2026-06-29T14:30:52Z"
    }
  ],
  "skills": [
    {
      "node_id": "skill_...",
      "difficulty_patterns": ["direction_confusion"],
      "teaching_actions": ["contrastive_explanation"],
      "status": "active",
      "confidence": 0.78,
      "updated_at": "2026-06-29T14:30:52Z"
    }
  ],
  "edges": [
    {
      "edge_id": "edge_...",
      "edge_type": "episode_concept",
      "source": "episode_...",
      "target": "concept_...",
      "weight": 1.0
    }
  ],
  "profile": {
    "models": {
      "learner_model": {"summary": "...", "updated_at": "...", "revisions": 3},
      "context_model": {"summary": "...", "updated_at": "...", "revisions": 5}
    },
    "recent_changes": [],
    "updated_at": "...",
    "revision_count": 8
  },
  "skill_adaptation": {
    "summary": "...",
    "updated_at": "...",
    "revisions": 2
  },
  "memory_events": [
    {
      "event_id": "evt_...",
      "event_type": "episode_created",
      "timestamp": "2026-06-29T14:30:52Z",
      "session_id": "session_demo"
    }
  ],
  "storage_health": {
    "backend": "sqlite",
    "schema_version": 3,
    "journal_mode": "wal",
    "database_size_bytes": 65536,
    "integrity": "ok"
  }
}
```

---

## 4. 端点参考

### 4.1 `GET /api/health`

健康检查端点。

**请求**：无参数

**响应**：

```json
{
  "status": "ok"
}
```

**curl 示例**：

```bash
curl http://127.0.0.1:8000/api/health
```

---

### 4.2 `GET /api/dashboard`

返回完整的仪表盘快照，包含所有图节点、边、画像和存储健康状态。

**请求**：无参数

**响应**：`DashboardSnapshot`（见 [3.2 响应模型](#32-响应模型)）

**curl 示例**：

```bash
curl http://127.0.0.1:8000/api/dashboard
```

---

### 4.3 `POST /api/chat`

同步聊天端点。发送用户消息，等待 LLM 生成完整回复后返回。

**请求体**：`ChatRequest`（见 [3.1 请求模型](#31-请求模型)）

**响应**：

```json
{
  "answer": "让我用一个具体的例子来解释...",
  "context": {
    "concepts": [...],
    "episodes": [...],
    "skills": [...],
    "memory_context_pack": "..."
  },
  "turn": {
    "turn_index": 5,
    "timestamp": "2026-06-29T14:30:52Z",
    "session_id": "session_demo",
    "user_message": "...",
    "assistant_message": "..."
  },
  "episode": {
    "node_id": "episode_...",
    "episode_type": "concept_explanation",
    "title": "..."
  },
  "boundary": {
    "should_end": true,
    "reason": "learning_goal_completed",
    "confidence": 0.85
  },
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  },
  "snapshot": { ... }
}
```

**字段说明**：

| 字段 | 类型 | 描述 |
|------|------|------|
| `answer` | `string` | LLM 生成的辅导回复 |
| `context` | `object` | 检索到的记忆上下文 |
| `turn` | `object` | 持久化后的轮次记录 |
| `episode` | `object \| null` | 若检测到边界，返回提取的 Episode |
| `boundary` | `object` | 边界检测结果 |
| `usage` | `object \| null` | Token 使用统计 |
| `snapshot` | `object` | 更新后的仪表盘快照 |

**curl 示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_demo",
    "message": "为什么不能直接用检测准确率当作患病概率？",
    "memory_mode": "ordinary"
  }'
```

---

### 4.4 `POST /api/chat/stream`

流式聊天端点。通过 SSE（Server-Sent Events）逐步返回 LLM 生成的回复。

**请求体**：`ChatRequest`（见 [3.1 请求模型](#31-请求模型)）

**响应**：`text/event-stream`（见 [5. SSE 流式协议](#5-sse-流式协议)）

**curl 示例**：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_demo",
    "message": "解释贝叶斯定理"
  }'
```

---

### 4.5 `POST /api/extract`

强制从当前缓冲区提取 Episode。当累积的轮次数不足自动触发阈值时，可通过此端点手动触发。

**请求体**：`ExtractRequest`（见 [3.1 请求模型](#31-请求模型)）

**响应**：

```json
{
  "episode": {
    "node_id": "episode_...",
    "episode_type": "concept_explanation",
    "title": "...",
    "summary": "...",
    "learner": {...},
    "tutor": {...},
    "outcome": {...}
  },
  "snapshot": { ... }
}
```

若缓冲区为空或无学习内容，`episode` 为 `null`。

**curl 示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session_demo"}'
```

---

### 4.6 `POST /api/diagnostics/model-test`

测试 LLM、嵌入或重排序模型的连接性。

**请求体**：`DiagnosticsRequest`（见 [3.1 请求模型](#31-请求模型)）

**`kind` 取值**：

| 值 | 测试内容 |
|----|----------|
| `"llm"` | 发送 "please reply OK" 测试聊天补全 |
| `"embedding"` | 发送测试文本计算嵌入向量 |
| `"reranker"` | 发送测试查询和文档进行重排序 |

**响应**：

```json
{
  "kind": "llm",
  "status": "ok",
  "latency_ms": 234,
  "model_id": "gpt-4o-mini",
  "detail": "OK"
}
```

**curl 示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/diagnostics/model-test \
  -H "Content-Type: application/json" \
  -d '{"kind": "llm"}'
```

---

### 4.7 `POST /api/rebuild-retrieval`

重建所有图节点的检索嵌入向量。当更换嵌入模型后需要重新计算所有向量时使用。

**请求体**：`RebuildRetrievalRequest`（见 [3.1 请求模型](#31-请求模型)）

**响应**：

```json
{
  "rebuilt_nodes": 42,
  "retrieval_health": {
    "total_nodes": 42,
    "valid_vectors": 42,
    "stale_vectors": 0
  },
  "snapshot": { ... }
}
```

**curl 示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/rebuild-retrieval \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

### 4.8 `POST /api/reset-memory`

重置所有记忆数据，包括：

- 所有对话记录
- 所有记忆事件
- 所有图节点和边
- 学习者画像
- 技能适配证据

**请求体**：`RebuildRetrievalRequest`（见 [3.1 请求模型](#31-请求模型)）

**响应**：

```json
{
  "deleted": true,
  "snapshot": { ... }
}
```

**curl 示例**：

```bash
curl -X POST http://127.0.0.1:8000/api/reset-memory \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

### 4.9 `GET /api/sessions`

返回所有会话的元数据列表。

**请求**：无参数

**响应**：

```json
{
  "sessions": [
    {
      "id": "session_demo",
      "title": "session_demo",
      "message_count": 12,
      "last_updated": "2026-06-29T14:30:52Z"
    }
  ]
}
```

**curl 示例**：

```bash
curl http://127.0.0.1:8000/api/sessions
```

---

### 4.10 `GET /api/sessions/{session_id}/turns`

返回指定会话的所有对话轮次。

**路径参数**：

| 参数 | 类型 | 描述 |
|------|------|------|
| `session_id` | `string` | 会话标识符 |

**响应**：

```json
{
  "turns": [
    {
      "turn_index": 1,
      "timestamp": "2026-06-29T14:25:10Z",
      "session_id": "session_demo",
      "user_message": "...",
      "assistant_message": "...",
      "metadata": {}
    }
  ]
}
```

**curl 示例**：

```bash
curl http://127.0.0.1:8000/api/sessions/session_demo/turns
```

---

## 5. SSE 流式协议

### 5.1 连接方式

客户端通过 `POST /api/chat/stream` 发起请求，响应的 `Content-Type` 为 `text/event-stream`。

### 5.2 事件格式

每个事件遵循标准 SSE 格式：

```
event: <event_type>
data: <json_payload>

```

### 5.3 事件类型

| 事件类型 | 描述 | 数据格式 |
|----------|------|----------|
| `context` | 检索到的记忆上下文 | `{"concepts": [...], "episodes": [...], "skills": [...]}` |
| `delta` | LLM 生成的文本片段 | `{"text": "让我"}` |
| `reasoning` | LLM 推理过程（部分模型支持） | `{"text": "学生混淆了..."}` |
| `usage` | Token 使用统计 | `{"prompt_tokens": 1234, "completion_tokens": 567}` |
| `answer` | 完整的辅导回复 | `{"text": "让我用一个具体的例子来解释..."}` |
| `memory` | 记忆更新事件 | `{"episode": {...}, "boundary": {...}}` |
| `final` | 轮次完成 | `{"turn": {...}, "snapshot": {...}}` |

### 5.4 事件序列

典型的流式响应事件序列：

```
event: context
data: {"concepts": [], "episodes": [], "skills": []}

event: delta
data: {"text": "让"}

event: delta
data: {"text": "我"}

event: delta
data: {"text": "用"}

event: delta
data: {"text": "一个"}

event: delta
data: {"text": "具体的"}

event: delta
data: {"text": "例子"}

event: delta
data: {"text": "来解释..."}

event: usage
data: {"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801}

event: answer
data: {"text": "让我用一个具体的例子来解释..."}

event: memory
data: {"episode": null, "boundary": {"should_end": false, "reason": "..."}}

event: final
data: {"turn": {...}, "snapshot": {...}}
```

### 5.5 客户端实现示例

#### JavaScript (Fetch API)

```javascript
const response = await fetch('http://127.0.0.1:8000/api/chat/stream', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    session_id: 'session_demo',
    message: '解释贝叶斯定理'
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {done, value} = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  const lines = text.split('\n');

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      const eventType = line.slice(7);
      // 处理事件类型
    }
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      // 处理数据
    }
  }
}
```

#### Python (httpx)

```python
import httpx
import json

with httpx.stream("POST", "http://127.0.0.1:8000/api/chat/stream",
                   json={"session_id": "demo", "message": "解释贝叶斯定理"},
                   timeout=60) as response:
    event_type = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
            if event_type == "delta":
                print(data["text"], end="", flush=True)
            elif event_type == "final":
                print("\n--- Turn complete ---")
```

---

## 6. 错误处理

### 6.1 HTTP 状态码

| 状态码 | 含义 | 场景 |
|--------|------|------|
| `200` | 成功 | 正常响应 |
| `422` | 请求验证失败 | Pydantic 模型验证错误 |
| `500` | 服务器内部错误 | 未捕获的异常 |

### 6.2 错误响应格式

```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 6.3 流式端点错误处理

流式端点在 LLM 调用失败时，会通过 SSE 事件返回错误信息：

```
event: error
data: {"error": "LLM connection failed", "detail": "..."}
```

客户端应监听 `error` 事件并适当处理。

### 6.4 诊断端点错误

诊断端点在连接失败时返回非 `ok` 状态：

```json
{
  "kind": "llm",
  "status": "error",
  "latency_ms": 5000,
  "model_id": "gpt-4o-mini",
  "detail": "Connection timeout after 5000ms"
}
```
