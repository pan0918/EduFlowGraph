# EduMindFlow API 文档

## 1. 概述

EduMindFlow 后端由 FastAPI 提供服务。默认本地地址为 `http://127.0.0.1:8000`。所有业务端点都以 `/api/` 开头，聊天接口支持普通 JSON 响应和 SSE 流式响应。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/dashboard` | 获取工作区快照 |
| `POST` | `/api/chat` | 普通聊天 |
| `POST` | `/api/chat/stream` | SSE 流式聊天 |
| `POST` | `/api/extract` | 强制抽取当前 session 的学习片段 |
| `POST` | `/api/diagnostics/model-test` | 模型连接诊断 |
| `POST` | `/api/rebuild-retrieval` | 重建检索向量 |
| `POST` | `/api/reset-memory` | 清空记忆和会话数据 |
| `GET` | `/api/sessions` | 获取会话列表 |
| `GET` | `/api/sessions/{session_id}/turns` | 获取指定会话的 turn |

## 2. 通用约定

### 2.1 请求格式

除 `GET` 端点外，所有端点都使用 JSON 请求体:

```http
Content-Type: application/json
```

### 2.2 响应格式

普通端点返回:

```http
Content-Type: application/json
```

流式聊天端点返回:

```http
Content-Type: text/event-stream
```

### 2.3 缓存

所有 `/api/` 响应都会加上:

```http
Cache-Control: no-store
```

### 2.4 认证

当前版本没有后端认证。生产部署时应在反向代理、网关或应用层增加访问控制。

### 2.5 CORS

后端默认允许以下本地前端来源:

- `http://127.0.0.1:3000`
- `http://localhost:3000`
- `http://127.0.0.1:3001`
- `http://localhost:3001`

## 3. 运行时配置字段

聊天、抽取、诊断、重建和重置接口都可以接收运行时配置。顶层字段用于简单配置，`runtime` 字段用于更精细的 LLM、embedding、reranker 配置。

常用顶层字段:

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | string | `mock` | `mock` 或 `openai-compatible` |
| `api_key` | string | 空 | API key |
| `base_url` | string | `https://api.openai.com/v1` | 模型服务 base URL |
| `chat_model` | string | `gpt-4o-mini` | 聊天模型 |
| `embedding_model` | string | `text-embedding-3-small` | 嵌入模型 |
| `extraction_turns` | int | `4` | 触发片段抽取的轮次数 |

`runtime` 示例:

```json
{
  "runtime": {
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
      "provider": "mock",
      "endpoint_url": "https://api.openai.com/v1/rerank",
      "model_id": ""
    }
  }
}
```

如果同时传入顶层字段和 `runtime`，后端会优先使用 `runtime` 中对应子项。

## 4. 端点

### 4.1 `GET /api/health`

检查后端是否可用。

请求:

```bash
curl http://127.0.0.1:8000/api/health
```

响应:

```json
{
  "status": "ok"
}
```

### 4.2 `GET /api/dashboard`

返回前端工作区需要的完整快照，包括概念、片段、技能、图边、画像和检索状态。

请求:

```bash
curl http://127.0.0.1:8000/api/dashboard
```

响应结构会随记忆数据增长而变化，常见顶层字段包括:

```json
{
  "concepts": [],
  "episodes": [],
  "skills": [],
  "edges": [],
  "profile": {},
  "memory_events": []
}
```

### 4.3 `POST /api/chat`

发送用户消息并返回一次完整导师回复。

请求字段:

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `session_id` | string | `session_demo` | 会话 ID |
| `message` | string | 必填 | 用户消息 |
| `memory_mode` | string | `ordinary` | `ordinary` 或 `augmented` |
| `runtime` | object 或 null | `null` | 运行时配置 |
| `provider` | string | `mock` | 简化模型配置 |
| `api_key` | string | 空 | 简化模型配置 |
| `base_url` | string | `https://api.openai.com/v1` | 简化模型配置 |
| `chat_model` | string | `gpt-4o-mini` | 简化模型配置 |
| `embedding_model` | string | `text-embedding-3-small` | 简化模型配置 |
| `extraction_turns` | int | `4` | 抽取轮次数 |

请求:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"解释一下链式法则","provider":"mock"}'
```

响应:

```json
{
  "answer": "导师回复文本",
  "context": {},
  "turn": {},
  "episode": null,
  "boundary": {},
  "usage": {},
  "snapshot": {}
}
```

### 4.4 `POST /api/chat/stream`

发送用户消息并以 SSE 形式返回导师回复。请求体与 `/api/chat` 相同。

请求:

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"解释一下链式法则","provider":"mock"}'
```

每条 SSE 消息格式:

```text
data: {"type":"delta","delta":"..."}
```

后端会把管线事件序列化到 `data:` 行中。当前 `TutorPipeline.stream_user_message()` 会产生以下事件:

| type | 说明 |
|---|---|
| `context` | 本轮生成前检索到的上下文 |
| `usage` | token 或模型使用信息 |
| `reasoning` | 模型 reasoning 增量 |
| `delta` | 回复文本增量 |
| `answer` | 已落库的完整回复，先于较重的记忆处理返回 |
| `memory` | 记忆抽取或更新阶段 |
| `final` | 本轮完成事件 |

当事件类型为 `final` 或 `memory` 时，后端会附带最新 `snapshot`。

### 4.5 `POST /api/extract`

强制从指定 session 的当前 buffer 中抽取 Episode。适合调试和手动触发记忆写入。

请求字段:

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `session_id` | string | `session_demo` | 会话 ID |
| `runtime` | object 或 null | `null` | 运行时配置 |
| `provider` | string | `mock` | 简化模型配置 |
| `api_key` | string | 空 | 简化模型配置 |
| `base_url` | string | `https://api.openai.com/v1` | 简化模型配置 |
| `chat_model` | string | `gpt-4o-mini` | 简化模型配置 |
| `embedding_model` | string | `text-embedding-3-small` | 简化模型配置 |
| `extraction_turns` | int | `4` | 抽取轮次数 |

请求:

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo","provider":"mock"}'
```

响应:

```json
{
  "episode": null,
  "snapshot": {}
}
```

如果 buffer 中没有足够内容，`episode` 可能为 `null`。

### 4.6 `POST /api/diagnostics/model-test`

检查 LLM、embedding 或 reranker 配置是否可用。

请求字段:

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `kind` | string | 必填 | `llm`, `embedding` 或 `reranker` |
| `runtime` | object 或 null | `null` | 运行时配置 |
| `provider` | string | `mock` | 简化模型配置 |
| `api_key` | string | 空 | 简化模型配置 |
| `base_url` | string | `https://api.openai.com/v1` | 简化模型配置 |
| `chat_model` | string | `gpt-4o-mini` | 简化模型配置 |
| `embedding_model` | string | `text-embedding-3-small` | 简化模型配置 |

请求:

```bash
curl -X POST http://127.0.0.1:8000/api/diagnostics/model-test \
  -H "Content-Type: application/json" \
  -d '{"kind":"embedding","provider":"mock"}'
```

响应取决于诊断类型，通常包含连接状态和错误信息。

### 4.7 `POST /api/rebuild-retrieval`

重建已有图节点的检索向量。

请求字段:

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `data_dir` | string | `data` | 数据目录 |
| `runtime` | object 或 null | `null` | 运行时配置 |
| `provider` | string | `mock` | 简化模型配置 |
| `api_key` | string | 空 | 简化模型配置 |
| `base_url` | string | `https://api.openai.com/v1` | 简化模型配置 |
| `chat_model` | string | `gpt-4o-mini` | 简化模型配置 |
| `embedding_model` | string | `text-embedding-3-small` | 简化模型配置 |

请求:

```bash
curl -X POST http://127.0.0.1:8000/api/rebuild-retrieval \
  -H "Content-Type: application/json" \
  -d '{"provider":"mock","data_dir":"data"}'
```

响应:

```json
{
  "updated": 0,
  "skipped": 0,
  "errors": [],
  "snapshot": {}
}
```

具体统计字段由 `TutorPipeline.rebuild_retrieval_embeddings()` 返回。

### 4.8 `POST /api/reset-memory`

清空当前数据目录下的会话、记忆图、画像和技能适配数据。

请求体与 `/api/rebuild-retrieval` 相同。

请求:

```bash
curl -X POST http://127.0.0.1:8000/api/reset-memory \
  -H "Content-Type: application/json" \
  -d '{"provider":"mock","data_dir":"data"}'
```

响应:

```json
{
  "cleared": true,
  "snapshot": {}
}
```

这是破坏性操作。生产环境应加认证和确认流程。

### 4.9 `GET /api/sessions`

返回会话列表。

请求:

```bash
curl http://127.0.0.1:8000/api/sessions
```

响应:

```json
{
  "sessions": [
    {
      "id": "demo",
      "title": "解释一下链式法则",
      "message_count": 2,
      "last_updated": "2026-06-30T12:00:00Z"
    }
  ]
}
```

`message_count` 按用户消息和助手消息两类消息估算，所以一个 turn 计为 2 条消息。

### 4.10 `GET /api/sessions/{session_id}/turns`

返回某个会话的原始 turn 列表。

请求:

```bash
curl http://127.0.0.1:8000/api/sessions/demo/turns
```

响应:

```json
{
  "turns": [
    {
      "session_id": "demo",
      "user_message": "解释一下链式法则",
      "assistant_message": "导师回复文本",
      "timestamp": "2026-06-30T12:00:00Z"
    }
  ]
}
```

## 5. 错误处理

FastAPI 会对请求体做 Pydantic 校验。常见状态码:

| 状态码 | 场景 |
|---:|---|
| 200 | 请求成功 |
| 422 | 请求体字段类型错误或缺少必填字段 |
| 500 | 后端处理异常 |

校验错误示例:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "message"],
      "msg": "Field required"
    }
  ]
}
```

流式端点如果在响应开始前失败，会返回普通 HTTP 错误。如果响应已经开始，客户端应捕获连接中断并显示通用失败提示。

## 6. 客户端示例

### 6.1 JavaScript fetch

```js
const response = await fetch("http://127.0.0.1:8000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    session_id: "demo",
    message: "解释一下链式法则",
    provider: "mock"
  })
});

const data = await response.json();
console.log(data.answer);
```

### 6.2 JavaScript SSE

```js
const response = await fetch("http://127.0.0.1:8000/api/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    session_id: "demo",
    message: "解释一下链式法则",
    provider: "mock"
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value, { stream: true }));
}
```

### 6.3 Python httpx

```python
import httpx

payload = {
    "session_id": "demo",
    "message": "解释一下链式法则",
    "provider": "mock",
}

response = httpx.post("http://127.0.0.1:8000/api/chat", json=payload)
response.raise_for_status()
print(response.json()["answer"])
```
