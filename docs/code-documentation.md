# EduFlowGraph 代码文档

> **版本**: 1.0 · **最后更新**: 2026-06-29 · **维护者**: EduFlowGraph Contributors

---

## 目录

1. [系统概述](#1-系统概述)
2. [设计哲学](#2-设计哲学)
3. [分层架构](#3-分层架构)
4. [核心模块参考](#4-核心模块参考)
5. [数据模型规范](#5-数据模型规范)
6. [算法描述](#6-算法描述)
7. [数据库 Schema](#7-数据库-schema)
8. [配置系统](#8-配置系统)
9. [前端架构](#9-前端架构)

---

## 1. 系统概述

EduFlowGraph 是一个**记忆增强型 AI 辅导引擎**（Memory-Augmented AI Tutoring Engine），其核心数据模型为 **Concept ← Episode → Skill** 三元组图结构。系统从对话轨迹中自动提取学习片段（Episode），识别知识概念（Concept）与常见误解（Misconception），蒸馏可复用的教学策略（Skill），并构建多维度学习者画像（Learner Profile），从而实现个性化的辅导响应生成。

### 1.1 核心能力矩阵

| 能力域 | 描述 | 关键模块 |
|--------|------|----------|
| 片段边界检测 | 基于 LLM 与启发式规则的混合决策器，判断对话何时完成一个学习片段 | `memory/buffer.py` |
| 片段提取 | 从闭合的对话片段中提取结构化 Episode 节点 | `memory/episode_extractor.py` |
| 概念识别 | 自动识别知识概念，支持模糊去重与嵌入相似度匹配 | `memory/concept_extractor.py` |
| 技能蒸馏 | 从多轮 Episode 证据中提炼可复用的教学策略 | `memory/skill_pipeline.py` |
| 个性化重排序 | 基于学习者画像的技能选择与排序 | `memory/skill_reranker.py` |
| 多信号检索 | 关键词匹配 + 余弦相似度 + 图扩展 + 结果重排 | `memory/retriever.py` |
| 画像管理 | 三个预算文本段落的覆写式画像维护 | `profile/` |
| 双后端存储 | 嵌入式 SQLite（WAL 模式）+ JSON/JSONL 遗留后端 | `store/` |

### 1.2 技术栈

| 层次 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI + Uvicorn |
| 前端框架 | Next.js 16 + React 19 + TypeScript 5 + Tailwind CSS 3.4 |
| 数据库 | SQLite 3（WAL 模式，无外部依赖） |
| LLM 接口 | OpenAI-compatible API（支持任意兼容端点） |
| 编程语言 | Python 3.10+ / TypeScript 5+ |

---

## 2. 设计哲学

### 2.1 覆写式画像（Rewrite-over-Accumulate）

学习者画像采用**覆写**而非**累积**策略。每个画像段落（`learner_model`、`context_model`、`skill_adaptation`）在每次更新时被整体重写，而非追加新证据。这一设计基于以下考量：

- **Token 预算约束**：画像段落注入 LLM prompt 时占用上下文窗口，累积式增长不可接受
- **信息时效性**：过时的学习状态描述对当前辅导决策无正向贡献
- **LLM 压缩优势**：让 LLM 在每次更新时综合所有已知信息重新生成摘要，比机械追加更准确

### 2.2 双后端兼容（Dual-Backend Compatibility）

每个存储层（graph、conversation、memory_flow、profile、skill_adaptation）均提供 JSON/JSONL 和 SQLite 两种实现，通过 `EDUFLOW_STORAGE_BACKEND` 环境变量切换。这一设计支持：

- 零配置开发体验（JSON 后端无需数据库服务器）
- 生产环境的事务一致性（SQLite WAL 模式）
- 无缝迁移路径（`scripts/migrate_storage.py`）

### 2.3 Mock-First 开发（Mock-First Development）

系统在无 API Key 时自动降级为 Mock 模式：

- **LLM Mock**：基于关键词的确定性中文回复
- **Embedding Mock**：32 维哈希向量（字符级哈希）
- **Reranker Mock**：关键词重叠评分

所有模块均可在 Mock 模式下完整运行，支持端到端测试与开发调试。

---

## 3. 分层架构

系统采用四层架构，自顶向下依次为：

```
┌─────────────────────────────────────────────────────────────┐
│                    表示层 (Presentation Layer)                │
│  Next.js Frontend ─ REST/SSE API ─ Workspace Components     │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    应用层 (Application Layer)                 │
│  FastAPI Endpoints ─ Request Models ─ Pipeline Factory      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    领域层 (Domain Layer)                      │
│  TutorPipeline ─ Memory Subsystem ─ Profile Subsystem       │
│  LLMClient ─ MemoryRetriever ─ SkillPersonalizedReranker   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    基础设施层 (Infrastructure Layer)           │
│  SQLiteStorage ─ GraphStore ─ ConversationLog ─ MemoryFlow  │
│  LearnerProfileStore ─ SkillAdaptationStore                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 依赖方向

```
表示层 → 应用层 → 领域层 → 基础设施层
```

- 表示层仅通过 REST API 与应用层通信
- 应用层负责请求验证、管线缓存和响应序列化
- 领域层包含所有业务逻辑，不依赖任何 Web 框架
- 基础设施层仅实现数据持久化，不包含业务逻辑

---

## 4. 核心模块参考

### 4.1 `pipeline.py` — 中央编排器

`TutorPipeline` 类是整个系统的核心编排器，连接所有子模块。

#### 构造函数

```python
TutorPipeline(settings: Settings)
```

初始化所有存储后端、启发式提取器、LLM 客户端、检索器、重排序器、画像合并器、缓冲区管理器和边界检测器。内部使用 `threading.Lock`（`_turn_lock`）保证轮次处理的线程安全性。

#### 公共方法

| 方法 | 签名 | 描述 |
|------|------|------|
| `handle_user_message` | `(session_id, message, *, memory_mode="ordinary") -> dict` | 同步轮次处理：检索 → 生成 → 持久化 |
| `stream_user_message` | `(session_id, message, *, memory_mode="ordinary") -> Generator` | 流式轮次处理，yield SSE 事件 |
| `force_extract` | `(session_id) -> dict \| None` | 强制从当前缓冲区提取 Episode |
| `reset_memory` | `() -> dict` | 清除所有存储数据 |
| `rebuild_retrieval_embeddings` | `() -> dict` | 重建所有节点的检索向量 |
| `dashboard` | `() -> dict` | 返回完整仪表盘快照 |

#### 记忆管线流程

```
用户消息
  │
  ▼
_start_tutor_turn()          ← 刷新存储 + 检索记忆 + 构建消息
  │
  ▼
LLM.chat() / LLM.stream_chat()  ← 生成辅导回复
  │
  ▼
_persist_tutor_turn()        ← 持久化到 conversation_log + buffer
  │
  ▼
_process_tutor_turn()        ← 后处理：
  │                             1. _update_context_profile()  ← 每轮更新情境画像
  │                             2. boundary_detector.evaluate() ← 边界检测
  │                             3. _extract_segment()          ← 若检测到边界：
  │                                ├─ episode_extractor        ← Episode 提取
  │                                ├─ concept_extractor        ← 概念识别
  │                                ├─ skill_evidence_extractor ← 技能证据提取
  │                                ├─ skill_distiller          ← 技能蒸馏/验证
  │                                └─ profile_consolidator     ← 画像合并
  ▼
返回结果
```

### 4.2 `memory/` — 记忆子系统

#### 4.2.1 `buffer.py` — 缓冲区管理与边界检测

**`BufferManager`**：管理每个 session 的轮次缓冲区。

```python
add_turn(session_id, turn) -> None
get_buffer(session_id) -> list[dict]
consume(session_id) -> list[dict]          # 返回并清空缓冲区
consume_prefix(session_id, count) -> list[dict]  # 返回并移除前 N 条
buffer_size(session_id) -> int
```

**`EpisodeBoundaryDetector`**：LLM 辅助（含启发式降级）的边界检测器。

```python
evaluate(*, history, new_messages, time_gap="unknown") -> dict
```

返回格式：`{"should_end": bool, "reason": str, "confidence": float}`

**检测策略**（优先级递减）：

1. **学生反馈门控**（`_apply_student_feedback_gate`）：学生确认理解 → 强制结束；学生仍在困惑 → 阻止提前结束
2. **LLM 判断**：将历史和新消息渲染为 prompt，调用 LLM 进行边界判断
3. **启发式降级**：主题偏移检测（Jaccard 重叠 < 0.15）、学习者确认标记、缓冲区长度上限

#### 4.2.2 `episode_extractor.py` — Episode 提取

**`HeuristicEpisodeExtractor`**：基于规则的 Episode 提取器。

```python
extract(turns: list[dict]) -> dict
```

提取字段：`episode_type`、`title`、`summary`、`learner`（goal/obstacle/evidence）、`tutor`（strategy/key_moves）、`outcome`（status/memory_value）

**`coerce_episode_from_llm(raw, fallback_turns) -> dict`**：解析 LLM JSON 输出，失败时回退到启发式提取器。

**`finalize_episode(semantic_episode, *, segment_turns, session_id, ...) -> dict`**：附加来源元数据（session_id、segment_id、时间戳、轮次范围）和提取元数据。

#### 4.2.3 `concept_extractor.py` — 概念识别

**`HeuristicConceptExtractor`**：基于规则的概念提取器。

```python
extract(episode, turns=None) -> {"concepts": [...], "relations": [...]}
```

**`sanitize_concept_payload(payload, *, episode, turns) -> dict`**：过滤逻辑：

- 移除禁用概念名（`BANNED_CONCEPT_NAMES`：27 个元概念名称）
- 验证概念在 episode 文本中有依据（grounding check）
- 强制显著性阈值：main ≥ 0.80，supporting ≥ 0.55
- 限制最多 3 条边，确保恰好 1 个 "main" 角色

#### 4.2.4 `skill_pipeline.py` — 技能证据提取与蒸馏

**`HeuristicSkillEvidenceExtractor`**：从 Episode 中提取教学行为和困难模式证据。

```python
extract(episode, turns, *, concept_names, concept_ids) -> dict
```

返回：`teaching_actions`（最多 4 个）、`difficulty_pattern`、`concept_scope`、`outcome_signal`、`learning_delta`、`evidence_summary`

**`HeuristicSkillDistiller`**：从多轮 Episode 证据中创建泛化 Skill 节点。

```python
distill(episodes, evidences, raw_events_by_episode) -> {"skill": {...}, "edges": [...]} | None
```

蒸馏条件：≥ 2 个 Episode，兼容的困难模式，正向学习结果。

**置信度计算**（`_confidence_from_window`）：

```
confidence = avg(outcome_score) + episode_count_bonus + improvement_bonus
clamp(confidence, 0.45, 0.95)
```

#### 4.2.5 `skill_reranker.py` — 个性化技能选择

**`SkillPersonalizedReranker`**：基于画像的技能选择与排序。

```python
select(*, query, context_summary, adaptation_summary, candidates) -> dict
```

**评分公式**（完整重排序路径）：

```
final_score = 0.35 × base_score + 0.20 × episode_link + 0.15 × confidence + 0.30 × personal_fit
```

**过滤阈值**：`confidence ≥ 0.60`、`personal_fit ≥ 0.35`、`final_score ≥ 0.50`

**三种状态**：
- `"ok"`：完整重排序（含 personal_fit）
- `"rank_only"`：重排序但无评分
- `"degraded"`：无重排序，基于阈值选择

#### 4.2.6 `retriever.py` — 多信号检索

**`MemoryRetriever`**：从知识图谱中检索相关概念、Episode 和技能。

```python
retrieve(query, top_k_episodes=3, top_k_concepts=3, top_k_skills=12) -> dict
render_context(context) -> str  # 渲染为 prompt 注入格式
```

**检索流程**：

1. **查询理解**（`_understand_query`）：意图分类（7 种）、学习者信号检测、困难模式提示
2. **概念召回**（`_recall_concepts`）：`score = 0.40×keyword + 0.40×vector + 0.10×prior + 0.10×precision`
3. **Episode 扩展**（`_expand_episodes`）：通过 `episode_concept` 边扩展，`score = 0.40×semantic + 0.30×concept_weight + 0.20×outcome + 0.10×recency + intent_bonus`
4. **技能召回**（`_recall_skills`）：两条路径——(a) 通过 `episode_skill` 边，(b) 直接关键词+语义匹配
5. **概念回补**（`_recover_concepts_from_episodes`）：当无直接概念匹配时，从 Episode 边回补

### 4.3 `profile/` — 画像子系统

#### 4.3.1 `dimensions.py` — 画像模型定义

| 模型 | 标签 | 预算 | 更新时机 | 用途 |
|------|------|------|----------|------|
| `learner_model` | 学习者画像 | 300 字符 | Episode 边界 | 长期认知诊断 |
| `context_model` | 情境画像 | 200 字符 | 每轮 | 当前学习情境 |
| `skill_adaptation` | 技能适配证据 | 300 字符 | Episode 边界 | 技能重排序依据 |

#### 4.3.2 `consolidator.py` — 画像合并器

**`ProfileConsolidator`**：覆写式画像维护。

```python
consolidate_episode(*, current, episode, concept_result=None, skill_evidence=None) -> dict
update_context(*, current, user_message, assistant_message) -> dict
```

**过拟合防护**（`_OVERCONFIDENT_PATTERNS`）：正则匹配"已掌握"、"完全理解"、"彻底搞懂"等过度自信表述，替换为"理解尚待验证"。

**预算执行**（`_sanitize_summary`）：通过 LLM 压缩（最多 3 次迭代）确保段落不超出预算。

#### 4.3.3 `retriever.py` — 画像渲染

```python
render_profile_context(profile: dict) -> str
```

仅渲染 `learner_model` 和 `context_model`（不含 `skill_adaptation`，后者仅用于技能重排序）。

### 4.4 `store/` — 存储层

#### 4.4.1 `sqlite_storage.py` — SQLite 存储引擎

**`SQLiteStorage`**：嵌入式 SQLite 存储层，支持 WAL 模式、事务和 Schema 迁移。

```python
__init__(path: Path)
transaction() -> Iterator[sqlite3.Connection]  # 嵌套事务支持
health() -> dict                                # 健康检查
```

**连接配置**：
- `journal_mode=WAL`
- `foreign_keys=ON`
- `busy_timeout=5000`
- `synchronous=NORMAL`

**向量编解码**：
- `encode_vector(vector) -> EncodedVector`：float list → float32 little-endian BLOB
- `decode_vector(blob, dimensions) -> list[float]`：反向解码

#### 4.4.2 `graph_store.py` — 图存储

**`GraphStore`**：基于 JSON 文件的内存图存储。

**概念去重算法**：名称归一化（去除非字母数字字符 + 小写）→ 集合交集判断。

**嵌入相似度匹配**：

```
cosine_sim(a, b) = dot(a, b) / (norm(a) × norm(b))
threshold ≥ 0.92 时判定为同一概念
```

#### 4.4.3 其他存储模块

| 模块 | 类 | 后端 | 描述 |
|------|----|------|------|
| `conversation_log.py` | `ConversationLog` | JSONL | 按 session 的对话日志 |
| `memory_flow.py` | `MemoryFlow` | JSONL | 追加式记忆事件日志（10 种事件类型） |
| `profile_store.py` | `LearnerProfileStore` | JSON | 学习者画像存储 |
| `skill_adaptation_store.py` | `SkillAdaptationStore` | JSON | 技能适配证据存储 |

### 4.5 `llm.py` — LLM 客户端

**`LLMClient`**：统一的 LLM 调用客户端，支持聊天补全、嵌入和重排序。

```python
chat(messages, temperature=0.2) -> str
stream_chat(messages, temperature=0.2) -> Generator    # SSE 流式
embedding(text) -> list[float]
rerank(query, documents, *, kind, allow_llm_fallback) -> list[dict]
```

**重试策略**：指数退避（`1.0 × 2^attempt`），最多 3 次，可重试 HTTP 状态码：`{408, 429, 500, 502, 503, 504}`

**流式实现**：解析 SSE `data:` 行，yield `delta`、`reasoning`、`usage` 事件。当 `stream_options` 不兼容时自动重试。

### 4.6 `schemas.py` — 数据类型定义

```python
@dataclass
class Turn:
    turn_index: int
    timestamp: str          # ISO 8601
    session_id: str
    user_message: str
    assistant_message: str
    metadata: dict[str, Any]

@dataclass
class MemoryEvent:
    event_id: str           # prefix_YYYYMMDD_HHMMSS_hex6
    timestamp: str
    event_type: str
    session_id: str
    payload: dict[str, Any]
```

**枚举常量**：

| 常量 | 值 |
|------|-----|
| `EPISODE_TYPES` | `concept_explanation`, `problem_solving`, `misconception_diagnosis`, `assessment`, `review`, `planning`, `other` |
| `OUTCOME_STATUSES` | `success`, `partial_success`, `failed`, `unresolved` |
| `INITIAL_STATES` | `low`, `partial`, `mixed`, `unclear`, `unknown` |
| `STRUCTURAL_ROLES` | `main`, `supporting`, `context` |
| `LEARNER_STATES` | `confused`, `clarified`, `neutral` |

### 4.7 `skills.py` — 教学行为分类体系

**教学行为**（10 种）：

| 键 | 标签 | 描述 |
|----|------|------|
| `contrastive_explanation` | 对比解释 | 通过对比易混淆概念澄清差异 |
| `step_by_step_guidance` | 分步引导 | 将复杂问题拆解为可执行步骤 |
| `worked_example` | 例题演示 | 提供完整解题过程 |
| `socratic_questioning` | 苏格拉底式提问 | 通过引导性问题促进主动思考 |
| `concrete_example` | 具体举例 | 用具体场景说明抽象概念 |
| `formula_decomposition` | 公式分解 | 逐项解释公式的含义和来源 |
| `self_explanation_prompt` | 自我解释提示 | 要求学习者用自己的话复述 |
| `diagnostic_check` | 诊断性检查 | 设计检验题评估理解程度 |
| `guided_practice` | 引导练习 | 提供脚手架支持的练习 |
| `error_correction` | 纠错反馈 | 针对具体错误进行纠正 |

**困难模式**（7 种）：

| 键 | 标签 | 描述 |
|----|------|------|
| `direction_confusion` | 方向混淆 | P(A\|B) 与 P(B\|A) 混淆 |
| `abstraction_gap` | 抽象鸿沟 | 无法将抽象概念与具体情境关联 |
| `procedural_gap` | 程序缺失 | 缺少解题步骤或方法 |
| `symbol_grounding` | 符号接地 | 无法理解数学符号的含义 |
| `transfer_failure` | 迁移失败 | 无法将已学知识应用到新场景 |
| `conceptual_confusion` | 概念混淆 | 对相似概念产生错误理解 |
| `unknown` | 未知 | 无法归类的困难 |

### 4.8 `prompts.py` — Prompt 模板管理

从 `EduFlowGraph/Prompt/` 目录加载 12 个 Markdown prompt 模板：

| 模板 | 用途 |
|------|------|
| `Episode_Detection_Prompt` | 边界检测 |
| `Episode_Extraction_Prompt` | Episode 提取 |
| `Concept_Extraction_Prompt` | 概念识别 |
| `Skill_Evidence_Extraction_Prompt` | 技能证据提取 |
| `Skill_Distillation_Prompt` | 技能蒸馏 |
| `Rerank_Fallback_Prompt` | LLM 重排序降级 |
| `Tutor_System_Prompt` | 辅导系统 prompt |
| `Tutor_User_Prompt` | 辅导用户 prompt |
| `Tutor_Memory_Augmented_User_Prompt` | 记忆增强用户 prompt |
| `Profile_Update_Prompt` | 画像更新 |
| `Context_Update_Prompt` | 情境更新 |
| `Profile_Condense_Prompt` | 画像压缩 |

---

## 5. 数据模型规范

### 5.1 图节点类型

#### Episode 节点

```json
{
  "node_id": "episode_20260629_143052_a1b2c3",
  "node_type": "episode",
  "episode_type": "concept_explanation",
  "title": "贝叶斯定理中条件概率方向的澄清",
  "summary": "学生混淆 P(A|B) 与 P(B|A)，通过检测准确率的具体案例进行对比解释",
  "learner": {
    "goal": "理解条件概率的方向性",
    "obstacle": "将检测准确率误用为患病概率",
    "evidence": "学生表示'还是不懂 P(A|B) 和 P(B|A) 的区别'"
  },
  "tutor": {
    "strategy": "对比解释 + 具体举例",
    "key_moves": ["用检测准确率 vs 患病概率的实例", "画出条件概率的方向箭头"]
  },
  "outcome": {
    "status": "partial_success",
    "memory_value": "medium"
  },
  "session_id": "session_demo",
  "segment_id": 3,
  "turn_range": [7, 10],
  "created_at": "2026-06-29T14:30:52Z"
}
```

#### Concept 节点

```json
{
  "node_id": "concept_20260629_143105_d4e5f6",
  "node_type": "concept",
  "name": "贝叶斯定理",
  "aliases": ["Bayes' theorem", "贝叶斯公式"],
  "description": "描述在已知先验概率和似然度的情况下如何计算后验概率",
  "structural_role": "main",
  "salience": 0.95,
  "extraction_episode_id": "episode_20260629_143052_a1b2c3"
}
```

#### Skill 节点

```json
{
  "node_id": "skill_direction_confusion_contrastive_explanation",
  "node_type": "skill",
  "difficulty_patterns": ["direction_confusion"],
  "teaching_actions": ["contrastive_explanation", "concrete_example"],
  "procedures": ["识别学生混淆的方向", "构建对比案例", "用箭头标注条件概率方向"],
  "success_criteria": "学生能正确区分 P(A|B) 和 P(B|A)",
  "status": "active",
  "confidence": 0.78,
  "quality": {
    "support_episode_count": 3,
    "validation_success_count": 2,
    "validation_failure_count": 0
  }
}
```

### 5.2 图边类型

| 边类型 | 源 | 目标 | 描述 |
|--------|----|------|------|
| `episode_concept` | Episode | Concept | Episode 涉及的知识概念 |
| `episode_skill` | Episode | Skill | Episode 作为技能的证据来源 |
| `concept_prerequisite` | Concept | Concept | 概念间的前置依赖关系 |

### 5.3 记忆事件类型

| 事件类型 | 描述 |
|----------|------|
| `episode_created` | 新 Episode 创建 |
| `episode_extraction_failed` | Episode 提取失败 |
| `concept_extracted` | 概念提取成功 |
| `concept_merged` | 概念去重合并 |
| `concept_extraction_failed` | 概念提取失败 |
| `skill_evidence_added` | 技能证据添加 |
| `skill_distilled` | 新技能蒸馏成功 |
| `skill_distillation_failed` | 技能蒸馏失败 |
| `skill_validated` | 技能验证完成 |
| `profile_updated` | 画像更新 |

---

## 6. 算法描述

### 6.1 多信号检索评分

#### 概念召回

```
score_concept(c, q) = 0.40 × keyword_match(c, q)
                    + 0.40 × cosine_sim(embedding(c), embedding(q))
                    + 0.10 × prior(c)
                    + 0.10 × precision_bonus(c)

prior(c) = min(1, |episode_concept_edges(c)| / 3)
```

#### Episode 扩展

```
score_episode(e, q) = 0.40 × semantic_sim(e, q)
                    + 0.30 × concept_weight(e)
                    + 0.20 × outcome_relevance(e)
                    + 0.10 × recency(e)
                    + intent_bonus(e, q)
```

#### 技能召回

```
score_skill(s, q) = semantic_sim(s, q)
                  + Σ(episode_score(e) × edge_weight(e, s))
                  + confidence(s) × 0.15
                  + quality_bonus(s)
                  + difficulty_match(s, q)
                  + intent_bonus(s, q)
                  + concept_scope_bonus(s, q)
```

### 6.2 个性化重排序

```
final_score(s) = 0.35 × base_score(s)
               + 0.20 × episode_link(s)
               + 0.15 × confidence(s)
               + 0.30 × personal_fit(s)

personal_fit(s) = reranker(query + context + adaptation, s)
```

### 6.3 边界检测启发式规则

```
topic_shift(t₁, t₂):
  terms₁ = extract_topic_terms(t₁)
  terms₂ = extract_topic_terms(t₂)
  jaccard = |terms₁ ∩ terms₂| / |terms₁ ∪ terms₂|
  return jaccard < 0.15

learner_confirmed(msg):
  return any(marker in msg for marker in LEARNER_CONFIRMATION_MARKERS)

should_end = topic_shift(history, new_msgs)
           ∨ learner_confirmed(new_msgs)
           ∣ buffer_size ≥ hard_max_events
```

### 6.4 置信度计算

```
confidence = clamp(
  avg(outcome_scores) + episode_count_bonus + improvement_bonus,
  0.45,
  0.95
)

episode_count_bonus = min(0.15, |episodes| × 0.05)
improvement_bonus = 0.10 if has_improvement else 0.0
```

---

## 7. 数据库 Schema

### 7.1 SQLite Schema（v3）

```sql
-- 会话表
CREATE TABLE sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 对话轮次表
CREATE TABLE turns (
    session_id       TEXT NOT NULL REFERENCES sessions(session_id),
    turn_index       INTEGER NOT NULL,
    timestamp        TEXT NOT NULL,
    user_message     TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    metadata_json    TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, turn_index)
);
CREATE INDEX idx_turns_session_ts ON turns(session_id, timestamp);

-- 记忆事件表
CREATE TABLE memory_events (
    sequence   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT UNIQUE NOT NULL,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_memory_events_type_seq ON memory_events(event_type, sequence);
CREATE INDEX idx_memory_events_session_seq ON memory_events(session_id, sequence);

-- 图节点表
CREATE TABLE nodes (
    node_id     TEXT PRIMARY KEY,
    node_type   TEXT NOT NULL CHECK(node_type IN ('concept', 'episode', 'skill')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX idx_nodes_type_updated ON nodes(node_type, updated_at);

-- 图边表
CREATE TABLE edges (
    edge_id       TEXT PRIMARY KEY,
    edge_type     TEXT NOT NULL,
    source        TEXT NOT NULL REFERENCES nodes(node_id),
    target        TEXT NOT NULL REFERENCES nodes(node_id),
    weight        REAL NOT NULL DEFAULT 1.0,
    evidence      TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX idx_edges_source_type ON edges(source, edge_type);
CREATE INDEX idx_edges_target_type ON edges(target, edge_type);

-- 画像模型表
CREATE TABLE profile_models (
    model_name TEXT PRIMARY KEY CHECK(model_name IN ('learner_model', 'context_model')),
    summary    TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    revisions  INTEGER NOT NULL DEFAULT 0
);

-- 画像变更日志
CREATE TABLE profile_changes (
    change_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at  TEXT NOT NULL,
    model_name  TEXT NOT NULL REFERENCES profile_models(model_name),
    note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_profile_changes_id ON profile_changes(change_id DESC);

-- 技能适配表
CREATE TABLE skill_adaptation (
    key        TEXT PRIMARY KEY CHECK(key = 'default'),
    summary    TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    revisions  INTEGER NOT NULL DEFAULT 0
);

-- 技能适配变更日志
CREATE TABLE skill_adaptation_changes (
    change_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_skill_adaptation_changes_id ON skill_adaptation_changes(change_id DESC);

-- 嵌入向量表
CREATE TABLE embeddings (
    node_id      TEXT PRIMARY KEY REFERENCES nodes(node_id),
    vector_blob  BLOB NOT NULL,
    dimensions   INTEGER NOT NULL,
    dtype        TEXT NOT NULL DEFAULT 'float32',
    provider     TEXT NOT NULL DEFAULT '',
    model_id     TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_embeddings_meta ON embeddings(provider, model_id, dimensions);
```

### 7.2 Schema 迁移历史

| 版本 | 变更 |
|------|------|
| v1 → v2 | 移除遗留 strategy profile，新增 `teaching_adaptation_model` 条目 |
| v2 → v3 | 将 `teaching_adaptation_model` 从 `profile_models` 迁移到独立的 `skill_adaptation` 表 |

---

## 8. 配置系统

### 8.1 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `EDUFLOW_PROVIDER` | `mock` | 提供者模式：`mock` 或 `openai-compatible` |
| `OPENAI_API_KEY` | — | LLM/嵌入 API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容 API 基础 URL |
| `EDUFLOW_CHAT_MODEL` | `gpt-4o-mini` | 聊天模型 ID |
| `EDUFLOW_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 ID |
| `EDUFLOW_RERANKER_MODEL` | — | 重排序模型 ID |
| `EDUFLOW_DATA_DIR` | `data` | 数据目录路径 |
| `EDUFLOW_STORAGE_BACKEND` | `sqlite` | 存储后端：`sqlite` 或 `json` |
| `EDUFLOW_DATABASE_PATH` | `{data_dir}/eduflowgraph.db` | SQLite 数据库文件路径 |
| `EDUFLOW_EXTRACTION_TURNS` | `4` | Episode 提取触发的缓冲轮次数 |

### 8.2 配置数据类

```python
@dataclass
class Settings:
    data_dir: Path
    storage_backend: str           # "sqlite" | "json"
    database_path: Path | None
    extraction_turns: int
    llm: LLMRuntimeConfig
    embedding: EmbeddingRuntimeConfig
    reranker: RerankerRuntimeConfig
```

`Settings` 通过 `load_settings_from_mapping(values: dict)` 从扁平字典构建，支持前端请求中的运行时覆盖。

---

## 9. 前端架构

### 9.1 路由结构

| 路由 | 页面 | 描述 |
|------|------|------|
| `/` | — | 重定向到 `/chat` |
| `/chat` | `ChatWorkspace` | 辅导聊天界面（SSE 流式） |
| `/knowledge` | `KnowledgeWorkspace` | 概念掌握度仪表盘 |
| `/space/memory` | `MemoryWorkspace` | 记忆图谱可视化 |
| `/space/profile` | `LearnerProfileWorkspace` | 学习者画像查看器 |
| `/space/skills` | `SkillsWorkspace` | 教学技能工作台 |
| `/settings` | `SettingsWorkspace` | 运行时配置 |

### 9.2 状态管理

`WorkspaceProvider`（React Context）集中管理所有状态：

- `settings: WorkspaceSettings` — 运行时配置
- `messages: Message[]` — 当前会话消息
- `sessions: SessionMeta[]` — 会话列表
- `snapshot: DashboardSnapshot` — 仪表盘快照
- `loading: boolean` — 加载状态
- `diagnostics: DiagnosticResult[]` — 诊断结果

### 9.3 运行时配置

前端支持多 Provider 配置（OpenAI、DeepSeek、SiliconFlow、Mock），每个 Provider 可配置独立的 LLM、嵌入和重排序模型。
