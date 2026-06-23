# 教学适配画像与 Skill 个性化重排设计

## 1. 目标

本次重构将第三个用户画像模型从“保存下一步如何教学”改为“描述该学生更适合哪些教学 Skill”。完整教学程序只保存在 Skill Node 中，避免画像与 Skill 重复承担教学方法职责。

新的三模型边界为：

- `learner_model`：描述学生当前的知识、理解、推理特点、困难和待验证掌握状态。
- `context_model`：描述当前任务、学习阶段、情绪、意图和压力。
- `teaching_adaptation_model`：用一段自然语言描述该学生适合或不适合的 Skill 类型、认知负荷、讲解节奏和验证偏好。

`learner_model` 与 `context_model` 直接进入 Tutor Prompt；`teaching_adaptation_model` 不作为完整文本直接进入 Tutor Prompt，而是作为 Qwen ReRanker 的个性化重排证据。选中的 Skill 才作为教学程序进入 Tutor Prompt。

## 2. 范围与非目标

### 2.1 本次范围

- 将 `strategy_model` 全面替换为 `teaching_adaptation_model`。
- 清空当前 SQLite 中的测试会话、MemoryFlow、Concept、Episode、Skill、边和用户画像数据。
- 升级 SQLite schema，并保证空数据和异常状态下 API 始终返回可渲染结构。
- 重写画像抽取、精简和 UI 文案，使第三模型只表达 Skill 选择偏好。
- 在 Skill 基础召回后使用现有配置的 `Qwen/Qwen3-Reranker-8B` 做个性化重排。
- 保留 Qwen 返回的 relevance score，参与最终评分、过滤和诊断展示。
- 支持 `seed`、`candidate`、`active` 三种 Skill 状态，低置信度或低匹配分 Skill 不进入 Prompt。
- Skill 缺失、全部被过滤或 ReRanker 异常时，系统仍能正常回答。

### 2.2 非目标

- 不在项目内下载或直接加载 8B ReRanker 权重。
- 不新增独立本地模型服务；继续复用用户已经配置的 ReRanker endpoint。
- 不放宽 Skill 蒸馏标准，也不为填充数量自动制造低质量 Skill。
- 不保留旧 `strategy_model` 的测试摘要。
- 不把教学适配文本拆成固定标签、偏好数组或规则表。

## 3. 画像数据契约

对外画像快照使用以下 canonical keys：

```json
{
  "models": {
    "learner_model": {
      "summary": "...",
      "updated_at": null,
      "revisions": 0
    },
    "teaching_adaptation_model": {
      "summary": "...",
      "updated_at": null,
      "revisions": 0
    },
    "context_model": {
      "summary": "...",
      "updated_at": null,
      "revisions": 0
    }
  },
  "recent_changes": [],
  "updated_at": null,
  "revision_count": 0,
  "health": {"status": "ok", "message": ""}
}
```

`teaching_adaptation_model.summary` 是一段短中文文本，建议不超过 300 字。内容只允许描述：

- 更适合优先选择的 Skill 特征或教学动作类型；
- 应降权或避免的 Skill 特征；
- 适合的认知负荷、抽象程度和讲解节奏；
- 适合的理解验证方式；
- 条件化偏好，例如“新概念先直觉、主动要求推导后再进入形式化 Skill”。

禁止保存具体知识主题的完整教学步骤，例如椭圆面积推导步骤或 PPO 公式推导流程。这些内容属于 Skill Node 或 Tutor 的即时生成。

## 4. SQLite schema 升级与数据清理

SQLite schema 从 v1 升级为 v2。迁移在一个事务中完成：

1. 重建 `profile_models`，将 CHECK 约束中的 `strategy_model` 替换为 `teaching_adaptation_model`。
2. 重建依赖该表的 `profile_changes`。
3. 保留 `learner_model` 与 `context_model` 行结构；旧 `strategy_model` 内容不迁移，插入空的 `teaching_adaptation_model` 行。
4. 更新 `PRAGMA user_version` 为 2。
5. 初始化时确保三个 canonical model 行都存在。

正式重构前调用项目现有的原子清空能力，删除：

- `sessions` 与 `turns`；
- `memory_events`；
- `nodes`、`edges` 与 `embeddings`；
- 三个画像摘要与画像变更记录。

清空后执行 SQLite `quick_check`、外键检查和逐表计数验证。数据库文件和 WAL 机制保留，不删除数据库本体。

JSON 后端仅作为兼容路径：读取旧快照时忽略 `strategy_model` 内容并产生空的 `teaching_adaptation_model`；对外始终返回新字段，避免前端出现新旧字段混合。

## 5. 画像更新流程

### 5.1 Episode 边界更新

Episode 完成后，画像聚合器同时改写：

- `learner_model`：继续遵守证据纪律，不因一次“懂了”断言长期掌握。
- `teaching_adaptation_model`：根据 Episode 结果、学生行为证据、使用过的教学动作和后续验证结果，归纳跨主题的 Skill 选择偏好。

教学适配抽取必须把“某方法在某次 Episode 中使用过”与“该学生稳定适合某类 Skill”区分开。一次成功只能形成谨慎假设；重复成功、失败对比或跨主题证据才能形成更明确偏好。

### 5.2 每轮情境更新

`context_model` 继续每轮轻量刷新，只记录当前学习场景。它不保存教学方法建议。

### 5.3 Mock 与异常路径

无在线 LLM 或画像更新失败时，启发式聚合器仍生成边界清晰的简短文本。画像更新错误不得阻断回答、会话持久化或记忆图谱更新。

## 6. Skill 状态与注入资格

Skill Node 支持：

- `seed`：人工或系统预置、尚未获得本学生 Episode 证据的教学 Skill。
- `candidate`：由严格 Skill 蒸馏流程产生，已有重复 Episode 支持但尚未充分验证。
- `active`：满足支持 Episode、成功验证和置信度门槛的已验证 Skill。

现有自动蒸馏仍直接产生 `candidate`，验证成功后晋升 `active`。本次不自动创建 Seed Skill，只建立完整状态支持，以便以后导入高质量预置 Skill。

状态本身不保证注入资格。所有状态都必须经过：

1. 最低 Skill confidence 门槛；
2. 个性化 ReRank relevance 门槛；
3. 最终综合分门槛。

任何门槛未通过即从 Selected Skills 中移除。这样即使候选池非空，也不会为了凑 Top K 强制注入低质量 Skill。

## 7. 两阶段 Skill 检索与个性化重排

### 7.1 第一阶段：基础候选召回

Concept 与 Episode 按现有流程召回。Skill 召回从“直接取 Top 1”改为先收集最多 12 个候选，基础证据包括：

- query 与 Skill 的语义/关键词相关性；
- 当前召回 Episode 到 Skill 的边权与 Episode 相关性；
- Skill 自身 confidence、验证次数和状态；
- concept scope、difficulty pattern 和当前意图匹配。

每个候选保留归一化后的 `base_skill_score`、`episode_link_score` 和 `skill_confidence`，范围均为 `[0, 1]`。

基础召回的原始分数在当前候选池内按 `raw_score / max_raw_score` 归一化；没有有效原始分时记为 0。`episode_link_score` 使用当前 Skill 所有关联命中 Episode 中最大的 `episode_score * edge_weight`，再在候选池内采用同样方式归一化。`skill_confidence` 直接截断到 `[0, 1]`。

### 7.2 第二阶段：Qwen 个性化 ReRank

仅对 Skill 候选构造 personalized rerank query：

```text
任务：根据学生当前问题、当前学习情境和长期教学适配偏好，判断哪个教学 Skill 最适合本轮。若 Skill 与“避免/降权”偏好冲突，应显著降分。

学生当前问题：{user_query}
当前学习情境：{context_model_summary 或“暂无”}
教学适配偏好：{teaching_adaptation_model_summary 或“暂无稳定偏好”}
```

每个 ReRank document 包含：

- Skill 名称与状态；
- trigger；
- difficulty pattern；
- teaching actions；
- procedure；
- success criteria；
- 关联 Episode 证据摘要。

继续使用已配置的 `Qwen/Qwen3-Reranker-8B` endpoint。Qwen 返回的 relevance score 归一化为 `[0, 1]`，记为 `personal_fit_score`。教学适配与当前情境合并为一次重排，避免同一批候选做两次 8B 推理，也避免两个高度相关分数重复计权。

若 relevance score 已在 `[0, 1]` 内则直接使用；若返回任意实数 logit，则使用 sigmoid 转换；NaN、Infinity 和缺失值视为无效响应并进入降级路径。

### 7.3 最终评分

在方案建议权重基础上，将适配与情境合并为个性化适配分：

```text
final_skill_score =
  0.35 * base_skill_score
+ 0.20 * episode_link_score
+ 0.15 * skill_confidence
+ 0.30 * personal_fit_score
```

文本中的负向偏好由 instruction-aware Qwen ReRanker 纳入 `personal_fit_score`，不再用脆弱的关键词解析额外制造 `negative_penalty`。最终按分数排序并过滤，最多保留 4 个 Selected Skills。

门槛作为命名配置常量集中管理，不散落在检索代码中。初始值固定为：

- `MIN_SKILL_CONFIDENCE = 0.60`；
- `MIN_PERSONAL_FIT_SCORE = 0.35`；
- `MIN_FINAL_SKILL_SCORE = 0.50`；
- `SKILL_CANDIDATE_POOL_SIZE = 12`；
- `MAX_SELECTED_SKILLS = 4`。

每个候选先过 confidence，再过 personal fit，最后过 final score；任一道门槛失败都记录明确的过滤原因。每个候选在 retrieval trace 中保留组件分数、过滤原因和是否入选，便于调试，而不是只显示最终顺序。

## 8. Prompt 注入与冷启动

Memory Context 的注入顺序为：

1. LearnerModel；
2. ContextModel；
3. Concept；
4. Episode；
5. Selected Skills。

完整 `teaching_adaptation_model` 不进入 Tutor Prompt。

当至少一个 Skill 通过门槛时，注入最多 4 个 Skill 的教学程序，并明确它们是可组合的候选路径而非必须机械执行的命令。

当没有 Skill、全部被过滤或 ReRanker 不可用且基础分也不足时：

- 省略 Skill Block；
- 从教学适配摘要的首个完整偏好句提取不超过 120 字的短控制提示；
- 若画像也为空，使用通用短提示：“先建立直观理解，再逐步展开关键步骤，并用一个简短问题检查理解。”

只把这句控制提示注入 Prompt，不注入完整教学适配画像。无 Skill 时 Memory Context 仍包含 LearnerModel、ContextModel、Concept 和 Episode，绝不生成空上下文或抛错。

## 9. ReRanker 返回契约与降级

现有 ReRanker 客户端只保留返回顺序。本次扩展内部结果，使每个候选同时保留：

- `rerank_index`；
- `relevance_score`；
- 使用的 provider 与 model id；
- 是否由真实 ReRanker、基础排序或 mock 路径产生。

降级规则：

1. Qwen 请求成功且返回合法 score：使用个性化综合评分。
2. Qwen 只返回顺序、不返回 score：第 `index` 名（从 0 开始）使用 `1 - index / candidate_count` 作为有限 fallback score，并在 trace 标记 `rank_only`。
3. Qwen 超时、报错或返回无效数据：保留基础召回顺序，仅当 `skill_confidence >= 0.75`、`base_skill_score >= 0.60`，且 Skill 为 `active` 或 `episode_link_score >= 0.50` 时允许降级入选；trace 标记 `degraded`。
4. 没有任何合格 Skill：进入短控制提示 fallback。

ReRanker 故障不得触发额外在线聊天模型重排，以避免隐藏延迟和不可控成本；也不得阻断 Tutor 回答。

## 10. API 与 UI

画像页面保留三个卡片，并将第三张更新为：

- 名称：教学适配模型；
- 说明：根据学生历史学习表现，判断哪些教学 Skill 更适合当前学生，并用于 Skill 的重排、过滤和轻量调节。

聊天侧栏不再把第三模型列为“注入的学习者画像”，而是在独立的“Skill 适配依据”区域展示，明确它参与重排但未全文进入 Tutor Prompt。

Retrieved Context 增加可选诊断字段：

```json
{
  "skill_selection": {
    "candidate_count": 0,
    "selected_count": 0,
    "reranker_status": "ok | rank_only | degraded | skipped",
    "fallback_instruction": "",
    "candidates": []
  }
}
```

旧客户端未读取该字段时不受影响。已有 `skills` 字段继续表示最终 Selected Skills，不改变聊天渲染的主接口含义。

## 11. 组件边界

- `ProfileConsolidator`：只负责三模型文本更新与边界清洗。
- `LearnerProfileStore` / `SQLiteLearnerProfileStore`：只负责 canonical 画像快照持久化与兼容读取。
- `MemoryRetriever`：负责 Concept、Episode 和 Skill 基础候选召回。
- 新的 `SkillPersonalizedReranker`：负责 personalized query/document 构造、Qwen score 归一化、综合评分、门槛过滤和诊断 trace。
- `TutorPipeline`：只编排画像读取、基础召回、Skill 个性化重排和 Prompt 构造。
- 前端类型与组件：只渲染 canonical 模型名、最终 Skills 和可选诊断信息。

个性化重排从当前较大的 `MemoryRetriever` 中拆出，避免继续扩大其职责，也让评分和降级逻辑可以独立测试。

## 12. 测试与验收

### 12.1 单元测试

- 三模型常量、字数预算、空快照和摘要更新全部使用 `teaching_adaptation_model`。
- 旧 `strategy_model` 快照读取后不会泄漏旧摘要。
- SQLite v1 到 v2 迁移更新约束、行名和 user_version。
- ReRank 返回 score、仅返回名次、异常和空候选四种契约。
- 个性化 query 包含 Query、ContextModel 与 TeachingAdaptationModel，但不包含无关的完整 LearnerModel。
- 候选 document 包含 Skill 教学程序与 Episode 证据。
- 综合评分、归一化、Top 4、置信度门槛和最终分门槛。
- `seed`、`candidate`、`active` 状态读取、展示与过滤。
- fallback 只注入一句短提示，不泄漏完整教学适配段落。

### 12.2 集成测试

- 同一问题下，Qwen 更偏好的 Skill 能超过基础语义分稍高但不适合学生的 Skill。
- 画像明确“避免公式密集”时，公式密集 Skill 被降权或过滤。
- ContextModel 从探索切换到形式化推导时，选出的 Skill 随情境变化。
- ReRanker 异常时仍返回 200、可渲染 context 和正常 Tutor 答案。
- 无 Concept、Episode、Skill 和画像的全空状态仍能回答。
- SQLite 重启后画像、Skill 状态和 API 结构一致。
- 重置记忆后所有业务表计数为零，画像三行保留为空模型。

### 12.3 前端与构建验证

- 画像页面显示三个新卡片名称与说明。
- 聊天侧栏正确区分“注入画像”和“Skill 适配依据”。
- TypeScript 类型检查和 Next.js build 通过。
- Python 全量测试通过，SQLite quick check 与 foreign key check 通过。

## 13. 完成标准

满足以下条件才视为完成：

- 项目中不存在运行时使用的 `strategy_model` 字段或“教学策略模型”旧文案；
- 教学适配画像为纯文本，并真实参与 Qwen Skill ReRank；
- ReRank relevance score 被保留并可诊断；
- 只有通过质量和适配门槛的 Skill 才进入 Prompt；
- Skill 缺失或 ReRanker 故障不会造成回答失败或前端渲染失败；
- 旧测试数据已清空，数据库完整性检查通过；
- 后端测试、前端类型检查和生产构建全部通过。
