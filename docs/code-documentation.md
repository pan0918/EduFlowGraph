# EduMindFlow 代码文档

## 1. 系统定位

EduMindFlow 是一个记忆增强型 AI 辅导系统。它把普通对话转换为可检索的学习记忆，包括学习片段、知识概念、教学技能和学习者画像。后续对话会读取这些记忆，用于调整解释方式、补充上下文和选择更合适的教学策略。

系统的核心结构是:

```text
Concept <- Episode -> Skill
```

- `Concept` 表示学习内容，例如贝叶斯定理、链式法则、递归。
- `Episode` 表示一次相对完整的学习片段，记录目标、障碍、导师动作和结果。
- `Skill` 表示从多个片段中抽取出的可复用教学策略。
- `LearnerProfile` 记录学习者当前认知状态、情境信息和教学偏好。

## 2. 技术栈

| 层级 | 实现 |
|---|---|
| 后端 | FastAPI, Uvicorn, Python 3.10+ |
| 前端 | Next.js 16, React 19, TypeScript 5, Tailwind CSS |
| 存储 | SQLite 默认后端, JSON/JSONL 遗留后端 |
| 模型接口 | OpenAI-compatible chat, embedding, reranker |
| 本地开发 | Mock LLM, Mock embedding, Mock reranker |

## 3. 代码结构

```text
.
├── EduFlowGraph/
│   ├── web_app.py
│   ├── pipeline.py
│   ├── config.py
│   ├── llm.py
│   ├── prompts.py
│   ├── schemas.py
│   ├── skills.py
│   ├── memory/
│   ├── profile/
│   ├── store/
│   └── Prompt/
├── web/
│   ├── app/
│   ├── components/
│   └── lib/
├── scripts/
├── tests/
└── docs/
```

### 3.1 后端入口

`EduFlowGraph/web_app.py` 定义 FastAPI 应用和所有 `/api/` 路由。它负责:

- 接收请求并转换为 Pydantic 模型。
- 根据请求中的运行时配置创建或复用 `TutorPipeline`。
- 返回普通 JSON 响应或 SSE 流式响应。
- 为 `/api/` 响应添加 `Cache-Control: no-store`。

### 3.2 中央管线

`EduFlowGraph/pipeline.py` 中的 `TutorPipeline` 是后端主编排器。它连接 LLM 客户端、存储层、检索器、画像合并器和记忆抽取模块。

一次普通聊天请求的路径如下:

```text
用户消息
  -> 读取会话和学习者记忆
  -> 检索相关概念、片段、技能和画像
  -> 构建模型输入
  -> 生成导师回复
  -> 持久化 turn
  -> 更新短期 buffer
  -> 判断是否形成 Episode
  -> 抽取 Concept, Episode, Skill evidence
  -> 更新图记忆和学习者画像
```

主要公开方法:

| 方法 | 用途 |
|---|---|
| `handle_user_message` | 非流式聊天处理 |
| `stream_user_message` | SSE 流式聊天处理 |
| `force_extract` | 手动触发当前 session 的片段抽取 |
| `reset_memory` | 清空会话、图记忆、画像和检索数据 |
| `rebuild_retrieval_embeddings` | 重建图节点的检索向量 |
| `dashboard` | 返回前端工作区使用的完整快照 |

## 4. 记忆子系统

记忆相关代码位于 `EduFlowGraph/memory/`。

| 文件 | 职责 |
|---|---|
| `buffer.py` | 管理 session turn buffer, 判断学习片段边界 |
| `episode_extractor.py` | 从一段对话中抽取 Episode 结构 |
| `concept_extractor.py` | 抽取概念、误解、掌握度线索 |
| `skill_pipeline.py` | 抽取教学技能证据并蒸馏为 Skill 节点 |
| `skill_reranker.py` | 根据学习者画像重排候选教学技能 |
| `retriever.py` | 多信号检索概念、片段、技能和画像上下文 |

### 4.1 Episode 边界

`EpisodeBoundaryDetector` 结合 LLM 判断和启发式规则。判断依据包括:

- 学生是否明确表示理解或仍然困惑。
- 当前主题是否发生明显切换。
- buffer 是否达到提取轮次数上限。
- 新消息和历史消息是否仍属于同一学习问题。

边界判断不会直接写数据库。它只决定当前 buffer 是否可以交给抽取模块处理。

### 4.2 Episode 抽取

Episode 抽取会整理以下信息:

- `episode_type`: 学习片段类型。
- `title` 和 `summary`: 片段标题和摘要。
- `learner`: 学习目标、困难、证据。
- `tutor`: 使用的教学动作和关键解释。
- `outcome`: 学习结果和记忆价值。
- `source`: session、turn 范围、时间戳等来源信息。

LLM 输出不可解析时，系统会回退到启发式抽取，避免管线中断。

### 4.3 Concept 抽取

概念抽取负责识别学习内容并更新概念图。系统会对概念名称做规范化和相似度匹配，减少重复节点。每个概念可以附带:

- 结构角色，例如主概念或前置概念。
- 显著性分数。
- 学习者误解或薄弱点。
- 估计掌握度。

### 4.4 Skill 抽取和重排

技能管线先从 Episode 中抽取教学动作证据，再将多条证据合并为更稳定的 Skill 节点。`SkillPersonalizedReranker` 会根据学习者画像和当前问题，对候选技能重新排序。这样系统可以优先选择更适合当前学习者的解释方式。

## 5. 学习者画像

画像相关代码位于 `EduFlowGraph/profile/`。

| 文件 | 职责 |
|---|---|
| `dimensions.py` | 定义画像维度、字段和预算 |
| `consolidator.py` | 根据新证据重写画像 |
| `retriever.py` | 将画像渲染为可注入 prompt 的上下文 |
| `aggregator.py` | 为前端生成画像摘要 |

画像采用重写策略，而不是无限追加文本。这样可以控制 prompt 长度，并避免旧状态长期污染后续教学决策。

当前画像主要包含三类信息:

1. 认知画像: 学习者已掌握内容、误解、困难模式。
2. 情境画像: 当前任务、近期对话状态、临时目标。
3. 教学偏好: 更适合该学习者的解释粒度、节奏和例子类型。

## 6. 存储层

存储代码位于 `EduFlowGraph/store/`。默认后端是 SQLite，遗留 JSON/JSONL 后端仍保留，用于迁移、调试和回滚。

| 存储对象 | SQLite 实现 | 遗留实现 |
|---|---|---|
| 会话 turn | `sqlite_conversation_log.py` | `conversation_log.py` |
| 图节点和边 | `sqlite_graph_store.py` | `graph_store.py` |
| 记忆事件 | `sqlite_memory_flow.py` | `memory_flow.py` |
| 学习者画像 | `sqlite_profile_store.py` | `profile_store.py` |
| 技能适配 | `sqlite_skill_adaptation_store.py` | `skill_adaptation_store.py` |

### 6.1 SQLite 设计

`sqlite_storage.py` 负责连接、初始化、迁移和健康检查。主要设计点:

- 使用 WAL 模式提高读写并发能力。
- 使用事务封装图节点、边、画像和事件写入。
- 复杂业务对象存为 JSON 文本，便于保留灵活 schema。
- 向量以 Float32 BLOB 存储，减少体积并避免引入外部向量数据库。
- `PRAGMA user_version` 记录 schema 版本，启动时自动迁移。

### 6.2 迁移脚本

| 脚本 | 用途 |
|---|---|
| `scripts/migrate_storage.py` | 将遗留 JSON/JSONL 数据迁移到 SQLite |
| `scripts/export_storage.py` | 将 SQLite 数据导出为 JSON/JSONL |

## 7. LLM 和 Prompt

`EduFlowGraph/llm.py` 提供统一模型客户端。它支持:

- Chat completion。
- Streaming chat。
- Embedding。
- Reranker。
- 连接诊断。
- Mock 模式。

Prompt 模板位于 `EduFlowGraph/Prompt/`，由 `EduFlowGraph/prompts.py` 加载。模板以 Markdown 保存，便于直接编辑和审阅。

主要模板包括:

- `Tutor_System_Prompt.md`
- `Tutor_User_Prompt.md`
- `Tutor_Memory_Augmented_User_Prompt.md`
- `Episode_Detection_Prompt.md`
- `Episode_Extraction_Prompt.md`
- `Concept_Extraction_Prompt.md`
- `Skill_Evidence_Extraction_Prompt.md`
- `Skill_Distillation_Prompt.md`
- `Profile_Update_Prompt.md`
- `Profile_Condense_Prompt.md`
- `Context_Update_Prompt.md`
- `Rerank_Fallback_Prompt.md`

## 8. 配置系统

`EduFlowGraph/config.py` 定义运行时配置。配置可以来自环境变量，也可以由前端 Settings 页面通过请求体传入。

常用环境变量:

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EDUFLOW_PROVIDER` | `mock` | 模型提供者模式 |
| `OPENAI_API_KEY` | 空 | API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `EDUFLOW_CHAT_MODEL` | `gpt-4o-mini` | 聊天模型 |
| `EDUFLOW_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 |
| `EDUFLOW_RERANKER_MODEL` | 空 | 重排序模型 |
| `EDUFLOW_EXTRACTION_TURNS` | `4` | 触发 Episode 抽取的轮次数 |
| `EDUFLOW_DATA_DIR` | `data` | 数据目录 |
| `EDUFLOW_STORAGE_BACKEND` | `sqlite` | `sqlite` 或 `json` |
| `EDUFLOW_DATABASE_PATH` | `data/eduflowgraph.db` | SQLite 数据库路径 |

## 9. 前端结构

前端位于 `web/`，使用 Next.js App Router。

| 路径 | 职责 |
|---|---|
| `web/app/` | 页面路由和布局 |
| `web/components/providers/WorkspaceProvider.tsx` | 工作区状态、API 调用、会话和配置管理 |
| `web/components/workspace/` | Chat, Knowledge, Memory, Profile, Skills 等面板 |
| `web/components/sidebar/` | 左侧导航 |
| `web/lib/` | 类型、LaTeX、技能展示等工具函数 |

前端通过 REST 和 SSE 调用后端。核心数据快照来自 `/api/dashboard`，聊天使用 `/api/chat` 或 `/api/chat/stream`。

## 10. 维护建议

- 修改 API 前，先更新 `EduFlowGraph/web_app.py`，再同步 `docs/api-reference.md`。
- 修改配置字段时，同时检查 `EduFlowGraph/config.py`、前端 Settings 页面和部署文档。
- 修改存储 schema 时，补充 SQLite 迁移逻辑和迁移脚本说明。
- 修改 Prompt 文件时，确认对应加载名称仍在 `prompts.py` 中存在。
