# EduFlowGraph-Lite：面向 AI4Education 的轻量级图记忆机制设计方案

> 版本：v1.0 Demo Design  
> 目标：基于 DeepTutor 的 AI Tutor 场景，设计一个比 Trace Forest 更适合长期个性化学习建模的轻量级记忆机制。  
> 核心思想：**DataFlow 保存完整交互轨迹，Memory Graph 保存压缩后的结构化学习记忆。**  
> 最小图结构：**Concept ← Episode → Skill**。

---

## 0. 方案摘要

本方案提出一个轻量级教育记忆机制：**EduFlowGraph-Lite**。它不追求一开始构建复杂异构图，而是先保留最核心的三类节点和两类边。

### 0.1 核心结构

```text
DataFlow
  └── append-only 原始事件流，保存完整 tutoring trajectory

Memory Graph
  ├── Concept Node：学生正在学习什么，以及该知识点上的掌握状态
  ├── Episode Node：一次有意义的学习交互片段
  └── Skill Node：从成功教学片段中总结出的可复用教学技能

Edges
  ├── Episode-Concept Edge：某个学习片段涉及哪些知识点
  └── Episode-Skill Edge：某个学习片段使用、验证或生成了哪些教学技能
```

### 0.2 一句话定义

> EduFlowGraph-Lite is an episode-centric educational memory graph that connects what the learner studies with how the tutor teaches through meaningful tutoring episodes extracted from an append-only event stream.

中文表达：

> EduFlowGraph-Lite 是一个以 Episode 为中心的轻量级教育记忆图。它通过从完整交互事件流中抽取有意义的学习片段，将学生学习的知识点和导师使用的教学技能连接起来。

### 0.3 最终图结构

```text
Concept Node  ←→  Episode Node  ←→  Skill Node

学生学什么        发生了什么          怎么教有效
```

更具体地：

```text
Concept A      Concept B      Concept C
    \             |             /
     \            |            /
      Episode 1  Episode 2  Episode 3
          \        |        /
           \       |       /
            Skill X
```

---

## 1. 设计动机

### 1.1 为什么不直接使用复杂图？

一开始不建议设计大量节点和大量边，例如：Misconception Node、Strategy Node、Evidence Node、Mastery Node、Review Node、Assessment Node 等。原因是：

1. **工程实现成本高**：Demo 阶段难以快速落地。
2. **抽取误差会累积**：节点/边越多，LLM 结构化抽取越容易出错。
3. **论文表达容易失焦**：过多结构会让方法看起来复杂，但不一定带来清晰贡献。
4. **调试困难**：当效果不好时，很难判断是检索、抽取、图结构还是更新策略出了问题。

因此，第一版采用“节点类型少、节点内部信息丰富、边关系简单”的设计风格。

### 1.2 为什么保留 DataFlow？

Memory Graph 是从交互中抽取出来的压缩记忆，天然可能有抽取错误或信息损失。因此需要一个不可变的原始事件流作为事实源。

DataFlow 的作用：

1. 保存完整对话和工具调用轨迹。
2. 支持后续重新抽取 Episode。
3. 支持错误分析和实验复现。
4. 支持从成功轨迹中蒸馏 Skill。
5. 支持未来扩展更复杂的记忆结构。

简单来说：

```text
DataFlow = 原始证据层
Memory Graph = 结构化压缩层
Skill Node = 程序性教学经验层
```

---

## 2. 系统总体架构

### 2.1 模块划分

EduFlowGraph-Lite 可以拆成六个模块：

```text
1. Interaction Logger
   记录原始用户问题、导师回答、学生反馈、工具调用等事件。

2. DataFlow Store
   append-only 保存完整事件流。

3. Buffer Manager
   暂存最近若干轮对话，判断是否触发 Episode 抽取。

4. Memory Extractor
   从 buffer 或 session 中抽取 Episode Node，并更新 Concept Node 和 Skill Node。

5. Memory Graph Store
   保存 Concept / Episode / Skill 节点，以及两类边。

6. Memory Retriever
   在回答用户问题前，检索相关 Concept、Episode 和 Skill，形成个性化上下文。
```

### 2.2 运行时流程

```text
用户输入问题
   ↓
记录 UserEvent 到 DataFlow
   ↓
识别当前问题涉及的概念
   ↓
从 Memory Graph 检索相关 Concept / Episode / Skill
   ↓
构造 Personalized Tutor Context
   ↓
Tutor Agent 生成回答
   ↓
记录 AssistantEvent 到 DataFlow
   ↓
更新 Buffer
   ↓
判断是否触发 Episode 抽取
   ↓
如果触发：生成 Episode Node，更新 Concept Node 和 Skill Node
```

### 2.3 离线/会话后流程

```text
Session 结束
   ↓
读取本 session 的 DataFlow
   ↓
总结关键学习片段
   ↓
生成或合并 Episode Node
   ↓
更新 Concept Node 的 learner_state
   ↓
统计 Episode-Skill 效果
   ↓
必要时生成新的 Skill Node
```

---

## 3. DataFlow 设计

DataFlow 是完整事件流。它不要求非常复杂，但要保证足够支持后续抽取和回放。

### 3.1 DataFlow 的基本原则

1. **Append-only**：只追加，不覆盖。
2. **Raw-first**：优先保留原始内容，再保留摘要和标签。
3. **Traceable**：Memory Graph 中的 Episode Node 必须能追溯到原始事件。
4. **Session-aware**：每个事件属于某个 session。
5. **Turn-aware**：每个事件有 turn_index，便于重建对话顺序。

### 3.2 Event Schema

Demo 阶段可以使用如下事件结构：

```json
{
  "event_id": "event_20260603_0001",
  "session_id": "session_20260603_01",
  "turn_index": 1,
  "timestamp": "2026-06-03T10:15:00",
  "actor": "student",
  "event_type": "user_message",
  "content": "为什么不能直接用检测准确率当作患病概率？",
  "metadata": {
    "course": "probability",
    "topic_hint": "bayes theorem",
    "source": "chat"
  }
}
```

### 3.3 actor 字段

建议支持以下 actor：

```text
student        学生/用户
assistant      AI tutor
tool           工具，例如搜索、计算器、代码执行器
memory_agent   记忆检索或记忆更新模块
evaluator      评估器，例如判断学生是否掌握
```

### 3.4 event_type 字段

Demo 阶段可以先支持这些类型：

```text
user_message            学生输入
assistant_message       导师回答
retrieval_result        检索结果
tool_call               工具调用
tool_result             工具返回
diagnosis               学生状态诊断
assessment              掌握程度评估
memory_extraction       记忆抽取结果
```

### 3.5 DataFlow 存储建议

Demo 阶段最简单可以使用：

```text
方案 A：JSONL 文件
  每一行一个 event，方便调试。

方案 B：SQLite
  使用 events 表保存所有事件，后续查询更方便。

方案 C：MongoDB
  适合保存半结构化事件，但 Demo 阶段不是必须。
```

推荐 Demo 第一版使用 SQLite 或 JSONL。

SQLite 表结构示例：

```sql
CREATE TABLE dataflow_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT,
    turn_index INTEGER,
    timestamp TEXT,
    actor TEXT,
    event_type TEXT,
    content TEXT,
    metadata_json TEXT
);
```

---

## 4. Memory Graph 总体设计

### 4.1 节点类型

第一版只保留三类节点：

```text
1. Concept Node
2. Episode Node
3. Skill Node
```

### 4.2 边类型

第一版只保留两类边：

```text
1. Episode-Concept Edge
2. Episode-Skill Edge
```

### 4.3 为什么 Episode 是中心？

Episode 是连接 Concept 和 Skill 的桥梁。

```text
Concept 表示学生学什么。
Skill 表示导师怎么教。
Episode 表示一次真实发生的学习过程。
```

没有 Episode，Concept 和 Skill 的关系就会变成静态假设。

有了 Episode，系统可以从真实交互中统计：

```text
某个知识点上，学生经常出现什么问题？
某种教学技能是否真的有效？
某种技能在哪些知识点上效果最好？
某个学生对哪种解释方式反应更好？
```

---

## 5. Concept Node 设计

Concept Node 表示一个知识点，同时也保存学生在该知识点上的个性化学习状态。

### 5.1 Concept Node 的定位

Concept Node 不只是课程知识图谱中的“知识点”，还包含 learner-specific 信息。

例如：

```text
Bayes Theorem 不是单纯的贝叶斯公式节点，
而是“该学生对贝叶斯公式的当前理解状态”。
```

### 5.2 Concept Node Schema

```json
{
  "node_id": "concept_bayes_theorem",
  "node_type": "concept",
  "name": "Bayes Theorem",
  "aliases": ["贝叶斯公式", "Bayesian rule"],

  "description": "根据证据更新概率判断的公式。",
  "domain": "probability",
  "course": "intro_probability",

  "prerequisites": [
    "conditional_probability",
    "joint_probability"
  ],

  "related_concepts": [
    "posterior_probability",
    "prior_probability",
    "likelihood"
  ],

  "learner_state": {
    "mastery": 0.42,
    "status": "weak",
    "confidence": 0.71,
    "last_touched": "2026-06-03T10:30:00",
    "success_count": 2,
    "error_count": 4,
    "trend": "improving"
  },

  "misconceptions": [
    "混淆 P(A|B) 和 P(B|A)",
    "把检测准确率直接当成患病概率",
    "忽略先验概率"
  ],

  "recommended_actions": [
    "use_contrastive_example",
    "ask_student_to_define_event_A_B",
    "use_small_numeric_example"
  ],

  "summary": "学生知道贝叶斯公式的大致形式，但条件方向和先验概率理解不稳定。",

  "created_at": "2026-06-03T10:00:00",
  "updated_at": "2026-06-03T10:30:00"
}
```

### 5.3 learner_state 字段说明

| 字段 | 含义 | 示例 |
|---|---|---|
| mastery | 学生对该概念的掌握程度，范围 0-1 | 0.42 |
| status | 离散掌握状态 | unknown / weak / partial / mastered |
| confidence | 系统对该判断的置信度 | 0.71 |
| last_touched | 最近一次涉及该概念的时间 | 2026-06-03 |
| success_count | 成功表现次数 | 2 |
| error_count | 错误表现次数 | 4 |
| trend | 最近趋势 | improving / stable / declining |

### 5.4 mastery 更新建议

Demo 阶段不需要复杂模型，可以用规则更新。

例如：

```text
如果 Episode outcome = success:
    mastery += 0.10
    success_count += 1

如果 Episode outcome = partial_success:
    mastery += 0.03
    success_count += 1

如果 Episode outcome = fail:
    mastery -= 0.05
    error_count += 1

mastery 限制在 [0, 1]
```

伪代码：

```python
def update_mastery(concept, outcome):
    if outcome == "success":
        delta = 0.10
        concept["learner_state"]["success_count"] += 1
    elif outcome == "partial_success":
        delta = 0.03
        concept["learner_state"]["success_count"] += 1
    elif outcome == "fail":
        delta = -0.05
        concept["learner_state"]["error_count"] += 1
    else:
        delta = 0.0

    old = concept["learner_state"]["mastery"]
    new = max(0.0, min(1.0, old + delta))
    concept["learner_state"]["mastery"] = new

    if new < 0.3:
        concept["learner_state"]["status"] = "weak"
    elif new < 0.7:
        concept["learner_state"]["status"] = "partial"
    else:
        concept["learner_state"]["status"] = "mastered"
```

---

## 6. Episode Node 设计

Episode Node 是 EduFlowGraph-Lite 的核心节点。它表示一次有意义的学习交互片段。

### 6.1 什么是 Episode？

Episode 不是每一轮对话，而是一段具有教学意义的交互。

例如：

```text
一次题目讲解
一次误区纠正
一次概念解释
一次练习反馈
一次复习总结
一次学生从不理解到部分理解的过程
```

### 6.2 Episode 抽取触发条件

可以参考 buffer 机制。

当以下任一条件满足时，触发 Episode 抽取：

```text
1. Buffer 中累计超过 N 轮对话，例如 6-10 轮。
2. 当前话题发生明显切换。
3. 一道题讲解完成。
4. 学生表现出明显误区。
5. 学生表现出明显掌握。
6. Session 结束。
```

Demo 阶段推荐使用简单规则：

```text
每 6 轮对话抽取一次 Episode，或 session 结束时强制抽取。
```

后续可以加入 LLM 判断：

```text
请判断当前 buffer 是否已经形成一个完整的学习片段。
如果是，请抽取 Episode；如果不是，请继续等待。
```

### 6.3 Episode Node Schema

```json
{
  "node_id": "episode_20260603_001",
  "node_type": "episode",

  "session_id": "session_20260603_01",
  "raw_event_refs": [
    "event_20260603_0001",
    "event_20260603_0002",
    "event_20260603_0003"
  ],

  "topic": "Bayes theorem explanation",
  "summary": "学生问为什么不能直接用检测准确率作为患病概率。系统发现学生混淆 P(阳性|患病) 和 P(患病|阳性)，随后使用对比解释进行纠正。",

  "concepts": [
    "bayes_theorem",
    "conditional_probability"
  ],

  "student_state": {
    "question": "为什么不能直接用检测准确率当作患病概率？",
    "detected_problem": "inverse conditional probability confusion",
    "understanding_before": "low",
    "understanding_after": "partial",
    "misconceptions": [
      "混淆 P(A|B) 和 P(B|A)",
      "忽略先验概率"
    ]
  },

  "tutor_action": {
    "strategy": "contrastive_explanation",
    "steps": [
      "区分事件 A 和事件 B",
      "解释 P(A|B) 和 P(B|A) 的自然语言含义",
      "用检测准确率例子进行对比",
      "提醒学生考虑先验概率"
    ],
    "used_example": true,
    "used_questioning": true
  },

  "outcome": {
    "result": "partial_success",
    "score": 0.6,
    "evidence": "学生最后能说出两个条件概率不同，但还不能独立完成新题。"
  },

  "quality": {
    "importance": 0.85,
    "confidence": 0.78,
    "should_retrieve_later": true
  },

  "created_at": "2026-06-03T10:35:00"
}
```

### 6.4 Episode outcome 取值

建议先使用四类：

```text
success          学生基本掌握
partial_success  学生部分理解，但还不稳定
fail             学生仍然没有理解
unknown          无法判断
```

### 6.5 Episode quality 字段

quality 用于控制后续检索和 skill 蒸馏。

| 字段 | 含义 |
|---|---|
| importance | 该 Episode 是否重要，例如是否包含明显误区或关键突破 |
| confidence | LLM 对抽取结果的置信度 |
| should_retrieve_later | 是否适合后续作为记忆检索结果 |

---

## 7. Skill Node 设计

Skill Node 表示一种可复用的教学技能或教学策略。

### 7.1 Skill Node 的定位

Skill Node 不是普通知识点，也不是学生状态，而是：

```text
在某种学习情境下，导师可以如何教学，以及这种方法是否有效。
```

它回答的问题是：

```text
当学生出现这种问题时，应该怎么教？
这种教学方法之前有没有成功过？
它适合哪些概念？
它适合什么水平的学生？
```

### 7.2 Skill Node 的来源

Skill 可以有两种来源：

```text
1. 手工初始化
   开发者预设一些常见教学技能。

2. 从 Episode 中自动总结
   当多个 Episode 显示某种教学方式有效时，生成或更新 Skill Node。
```

Demo 阶段建议先混合使用：

```text
先手工初始化 5-10 个通用 Skill，
然后允许系统从成功 Episode 中更新 skill 的 success_count / fail_count。
```

### 7.3 推荐初始化的 Skill

Demo 阶段可以先准备这些：

```text
1. step_by_step_explanation
   分步骤解释。

2. contrastive_explanation
   对比两个容易混淆的概念。

3. worked_example
   给出完整例题。

4. socratic_questioning
   通过提问引导学生自己发现答案。

5. misconception_diagnosis_first
   先判断学生错在哪里，再解释。

6. analogy_explanation
   使用类比解释抽象概念。

7. minimal_numeric_example
   使用极小数值例子帮助理解。

8. transfer_question
   讲解后给一个迁移题检测是否掌握。
```

### 7.4 Skill Node Schema

```json
{
  "node_id": "skill_contrastive_conditional_probability",
  "node_type": "skill",

  "name": "Contrastive explanation for conditional probability",
  "description": "通过对比 P(A|B) 和 P(B|A) 的自然语言含义来纠正条件概率方向混淆。",

  "trigger": [
    "学生混淆 P(A|B) 和 P(B|A)",
    "学生把条件概率和后验概率当成同一个东西",
    "学生直接把检测准确率当成患病概率"
  ],

  "procedure": [
    "让学生明确两个事件 A 和 B",
    "分别写出 P(A|B) 和 P(B|A) 的自然语言含义",
    "用同一个情境构造两个对比例子",
    "让学生判断两个概率是否可以互换",
    "最后回到原题，让学生重新解释"
  ],

  "success_condition": [
    "学生能正确指出条件事件",
    "学生能解释 P(A|B) 和 P(B|A) 的区别",
    "学生能在新题中区分两个条件概率"
  ],

  "failure_condition": [
    "学生仍然把两个条件概率视为相同",
    "学生只能复述公式但不能解释含义"
  ],

  "quality": {
    "success_count": 3,
    "fail_count": 1,
    "confidence": 0.75,
    "last_used": "2026-06-03T10:30:00"
  },

  "summary": "当学生混淆条件概率方向时，对比解释通常有帮助。"
}
```

### 7.5 Skill 更新规则

当一个 Episode 使用了某个 Skill 后，根据 outcome 更新该 Skill 的质量统计。

```text
如果 Episode outcome = success:
    skill.success_count += 1
    skill.confidence += 小幅提升

如果 Episode outcome = partial_success:
    skill.success_count += 0.5
    skill.confidence += 极小提升

如果 Episode outcome = fail:
    skill.fail_count += 1
    skill.confidence -= 小幅下降
```

伪代码：

```python
def update_skill_quality(skill, episode_outcome):
    if episode_outcome == "success":
        skill["quality"]["success_count"] += 1
        skill["quality"]["confidence"] += 0.05
    elif episode_outcome == "partial_success":
        skill["quality"]["success_count"] += 0.5
        skill["quality"]["confidence"] += 0.02
    elif episode_outcome == "fail":
        skill["quality"]["fail_count"] += 1
        skill["quality"]["confidence"] -= 0.04

    skill["quality"]["confidence"] = max(
        0.0,
        min(1.0, skill["quality"]["confidence"])
    )
```

---

## 8. Edge 设计

第一版只保留两种边。

```text
1. Episode-Concept Edge
2. Episode-Skill Edge
```

不单独设计 Concept-Concept、Concept-Skill、Skill-Skill 边。

### 8.1 为什么不需要 Concept-Skill 边？

Concept 和 Skill 的关系可以通过 Episode 间接推断。

例如：

```text
Skill X ← Episode 1 → Concept A
Skill X ← Episode 2 → Concept A
Skill X ← Episode 3 → Concept B
```

如果 Skill X 经常出现在 Concept A 的成功 Episode 中，那么可以统计出：

```text
Skill X 对 Concept A 可能有效。
```

这不需要显式建立 `Skill --applies_to--> Concept` 边。

### 8.2 为什么不需要 Concept-Concept 边？

先修关系和相关概念可以暂时放在 Concept Node 的字段中。

```json
{
  "name": "Bayes Theorem",
  "prerequisites": ["conditional_probability"],
  "related_concepts": ["prior_probability", "posterior_probability"]
}
```

后续如果发现概念结构非常重要，再把这些字段升级为显式边。

### 8.3 Episode-Concept Edge Schema

```json
{
  "edge_id": "edge_ep001_concept_bayes",
  "edge_type": "episode_concept",

  "source": "episode_20260603_001",
  "target": "concept_bayes_theorem",

  "weight": 0.91,

  "evidence": "本轮对话主要围绕贝叶斯公式和条件概率方向展开。",

  "metadata": {
    "concept_role": "main_concept",
    "student_performance": "partial_success",
    "detected_misconception": "混淆 P(A|B) 和 P(B|A)"
  },

  "created_at": "2026-06-03T10:35:00"
}
```

### 8.4 Episode-Concept Edge 的 metadata

`concept_role` 可以有这些取值：

```text
main_concept          主要知识点
prerequisite_concept  先修知识点
confused_concept      学生混淆的知识点
review_concept        后续需要复习的知识点
```

### 8.5 Episode-Skill Edge Schema

```json
{
  "edge_id": "edge_ep001_skill_contrastive",
  "edge_type": "episode_skill",

  "source": "episode_20260603_001",
  "target": "skill_contrastive_conditional_probability",

  "weight": 0.84,

  "evidence": "该 episode 中系统使用了对比解释，学生理解从 low 提升到 partial。",

  "metadata": {
    "skill_role": "used",
    "outcome": "partial_success",
    "contribution": "medium"
  },

  "created_at": "2026-06-03T10:35:00"
}
```

### 8.6 Episode-Skill Edge 的 metadata

`skill_role` 可以有这些取值：

```text
used          本 Episode 使用了该 Skill
validated     本 Episode 证明该 Skill 有效
derived_from  该 Skill 是从本 Episode 中总结出来的
failed        本 Episode 中该 Skill 效果不好
```

注意：这些都只是 edge metadata，不是新的边类型。

---

## 9. 记忆抽取流程

### 9.1 整体流程

```text
DataFlow 中累计事件
   ↓
Buffer Manager 判断是否触发抽取
   ↓
Memory Extractor 读取最近 buffer
   ↓
LLM 抽取 Episode Node
   ↓
识别或创建 Concept Node
   ↓
识别或创建 Skill Node
   ↓
创建 Episode-Concept Edge
   ↓
创建 Episode-Skill Edge
   ↓
更新 Concept learner_state 和 Skill quality
```

### 9.2 Buffer 设计

Buffer 保存最近若干个事件。

```json
{
  "buffer_id": "buffer_session_001",
  "session_id": "session_20260603_01",
  "events": [
    "event_001",
    "event_002",
    "event_003"
  ],
  "status": "active",
  "created_at": "2026-06-03T10:00:00",
  "updated_at": "2026-06-03T10:30:00"
}
```

### 9.3 Episode 抽取 Prompt 模板

可以使用下面的 Prompt：

```text
你是一个 AI 教育系统的记忆抽取器。你的任务是从一段师生对话中抽取一个有意义的学习 Episode。

请根据对话内容完成以下任务：

1. 判断这段对话是否构成一个完整或半完整的学习片段。
2. 如果不构成，请返回 {"should_extract": false}。
3. 如果构成，请抽取：
   - topic：本 Episode 的主题
   - summary：简明摘要
   - concepts：涉及的知识点
   - student_state：学生的问题、错误、理解前后变化
   - tutor_action：导师使用的教学策略和步骤
   - outcome：学习结果，必须是 success / partial_success / fail / unknown 之一
   - quality：重要性、置信度、是否值得后续检索

请严格输出 JSON，不要输出额外解释。

对话内容：
{buffer_text}
```

输出示例：

```json
{
  "should_extract": true,
  "episode": {
    "topic": "Bayes theorem explanation",
    "summary": "学生混淆检测准确率和患病后验概率，导师使用对比解释进行纠正。",
    "concepts": ["bayes_theorem", "conditional_probability"],
    "student_state": {
      "question": "为什么不能直接用检测准确率当作患病概率？",
      "detected_problem": "inverse conditional probability confusion",
      "understanding_before": "low",
      "understanding_after": "partial",
      "misconceptions": ["混淆 P(A|B) 和 P(B|A)"]
    },
    "tutor_action": {
      "strategy": "contrastive_explanation",
      "steps": ["区分事件 A 和 B", "解释两个条件概率的语言含义", "使用检测例子对比"],
      "used_example": true,
      "used_questioning": true
    },
    "outcome": {
      "result": "partial_success",
      "score": 0.6,
      "evidence": "学生能说出两个概率不同，但还不能独立完成新题。"
    },
    "quality": {
      "importance": 0.85,
      "confidence": 0.78,
      "should_retrieve_later": true
    }
  }
}
```

### 9.4 Concept 更新 Prompt 模板

```text
你是一个 AI 教育系统的学习状态更新器。

给定一个新的 Episode 和已有 Concept Node，请更新学生在这些 Concept 上的学习状态。

请完成：
1. 判断 Episode 对每个 Concept 的影响。
2. 更新 mastery、status、success_count、error_count、misconceptions、recommended_actions、summary。
3. 不要大幅修改无依据的信息。
4. 输出更新后的 Concept Node JSON。

Episode:
{episode_json}

Existing Concept Node:
{concept_json}
```

### 9.5 Skill 更新 Prompt 模板

```text
你是一个 AI 教育系统的教学技能更新器。

给定一个新的 Episode 和已有 Skill Nodes，请判断：
1. Episode 是否使用了已有 Skill。
2. Episode 是否验证了某个 Skill 有效或无效。
3. 是否需要创建新的 Skill Node。
4. 如果更新已有 Skill，请更新 success_count、fail_count、confidence、summary。

Episode:
{episode_json}

Candidate Skill Nodes:
{skill_nodes_json}

请严格输出 JSON。
```

---

## 10. 记忆检索流程

### 10.1 检索目标

回答用户问题之前，系统需要检索个性化记忆。

检索不是为了找“最相似文本”，而是为了回答：

```text
这个学生当前可能卡在哪里？
之前是否学过相关知识点？
之前出现过什么误区？
之前哪种解释方式有效？
当前应该调用哪个教学技能？
```

### 10.2 检索步骤

Demo 版本可以使用 5 步：

```text
Step 1：识别当前问题涉及的 Concept
Step 2：检索相关 Concept Node
Step 3：沿 Episode-Concept Edge 找相关 Episode
Step 4：沿 Episode-Skill Edge 找相关 Skill
Step 5：组织 Personalized Tutor Context
```

### 10.3 Step 1：识别 Concept

输入：当前用户问题。

输出：概念列表。

Prompt 示例：

```text
你是一个教育系统的概念识别器。
请从学生问题中识别涉及的知识点。

学生问题：
{user_query}

请输出 JSON：
{
  "concepts": [...],
  "possible_misconceptions": [...],
  "difficulty": "low | medium | high"
}
```

### 10.4 Step 2：检索 Concept Node

检索方式：

```text
1. 精确匹配 concept name / alias
2. embedding 相似度检索
3. 根据 related_concepts / prerequisites 扩展
```

Demo 阶段可以先使用 embedding 检索 + alias 匹配。

### 10.5 Step 3：检索相关 Episode

从命中的 Concept Node 出发，找相关 Episode。

排序建议：

```text
Episode score =
    0.4 * semantic_similarity(user_query, episode.summary)
  + 0.3 * edge_weight
  + 0.2 * episode.quality.importance
  + 0.1 * recency_score
```

Demo 阶段可以先取 Top-k，例如：

```text
Top 3 most relevant episodes
```

### 10.6 Step 4：检索相关 Skill

从相关 Episode 出发，找 Skill Node。

排序建议：

```text
Skill score =
    0.4 * skill.confidence
  + 0.3 * episode_skill_edge.weight
  + 0.2 * trigger_match
  + 0.1 * recency_score
```

Demo 阶段取 Top-1 或 Top-2 Skill 即可。

### 10.7 Step 5：构造 Personalized Tutor Context

最终给 Tutor Agent 的上下文可以是：

```json
{
  "current_query": "我还是不懂贝叶斯公式。",
  "detected_concepts": ["bayes_theorem", "conditional_probability"],

  "learner_concept_state": [
    {
      "concept": "bayes_theorem",
      "mastery": 0.42,
      "status": "weak",
      "summary": "学生知道公式形式，但经常混淆条件方向。"
    }
  ],

  "relevant_episodes": [
    {
      "topic": "Bayes theorem explanation",
      "summary": "上次学生混淆检测准确率和后验概率，通过对比解释后部分理解。",
      "outcome": "partial_success"
    }
  ],

  "recommended_skills": [
    {
      "name": "Contrastive explanation for conditional probability",
      "procedure": [
        "明确事件 A 和 B",
        "对比 P(A|B) 与 P(B|A)",
        "使用小数值例子"
      ],
      "confidence": 0.75
    }
  ]
}
```

### 10.8 Tutor 回答 Prompt 模板

```text
你是一个个性化 AI Tutor。

请根据学生当前问题和检索到的学习记忆生成回答。
你的目标不是直接给最终答案，而是根据学生已有状态进行有针对性的教学。

学生当前问题：
{user_query}

个性化学习记忆：
{personalized_tutor_context}

回答要求：
1. 根据学生历史误区调整解释。
2. 优先使用 recommended_skills 中的教学方法。
3. 如果学生之前在某个点上出错，要主动避免重复相同解释。
4. 回答后给一个小检查问题，判断学生是否真的理解。
5. 语气自然、鼓励、清晰。
```

---

## 11. Demo 实现路线

### 11.1 Demo 目标

Demo 不需要一开始做完整系统。建议先验证三个能力：

```text
1. 能从对话中抽取 Episode。
2. 能更新 Concept 中的学生掌握状态。
3. 能在后续回答中检索 Episode 和 Skill，实现个性化教学。
```

### 11.2 最小 Demo 功能

最小可运行版本包括：

```text
1. 一个简单聊天界面。
2. DataFlow 日志记录。
3. Buffer 累积最近若干轮对话。
4. Episode 抽取器。
5. Concept / Episode / Skill 图存储。
6. 检索器。
7. 个性化回答生成器。
```

### 11.3 推荐技术栈

#### 简单版

```text
前端：Streamlit
后端：Python
DataFlow：JSONL 或 SQLite
Graph Store：NetworkX + JSON 文件
Embedding Store：FAISS 或 Chroma
LLM：OpenAI API / 本地模型
```

#### 稍微正式一点

```text
前端：Next.js
后端：FastAPI
DataFlow：SQLite / PostgreSQL
Graph Store：Neo4j / NetworkX
Vector Store：Chroma / Milvus / FAISS
LLM Orchestration：LangGraph / 自己写 pipeline
```

Demo 阶段推荐：

```text
Streamlit + SQLite + NetworkX + Chroma
```

原因：实现快、调试方便、足够展示效果。

### 11.4 文件结构建议

```text
eduflowgraph_lite/
  ├── app.py
  ├── config.py
  ├── data/
  │   ├── dataflow.jsonl
  │   ├── graph_nodes.json
  │   ├── graph_edges.json
  │   └── vector_store/
  │
  ├── memory/
  │   ├── dataflow_store.py
  │   ├── buffer_manager.py
  │   ├── graph_store.py
  │   ├── extractor.py
  │   ├── retriever.py
  │   └── updater.py
  │
  ├── tutor/
  │   ├── tutor_agent.py
  │   ├── prompts.py
  │   └── evaluator.py
  │
  └── schemas/
      ├── event_schema.py
      ├── node_schema.py
      └── edge_schema.py
```

---

## 12. Demo 开发步骤

### Step 1：实现 DataFlow Logger

目标：每轮对话都能写入 JSONL。

示例：

```python
def log_event(event):
    with open("data/dataflow.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
```

### Step 2：实现 Buffer Manager

目标：累计最近若干轮对话。

```python
class BufferManager:
    def __init__(self, max_turns=6):
        self.max_turns = max_turns
        self.events = []

    def add_event(self, event):
        self.events.append(event)

    def should_extract(self):
        return len(self.events) >= self.max_turns

    def clear(self):
        self.events = []
```

### Step 3：实现 Episode Extractor

目标：调用 LLM，把 buffer 转成 Episode JSON。

```python
def extract_episode(buffer_events):
    buffer_text = format_events(buffer_events)
    prompt = EPISODE_EXTRACTION_PROMPT.format(buffer_text=buffer_text)
    response = call_llm(prompt)
    return json.loads(response)
```

### Step 4：实现 Graph Store

目标：保存三类节点和两类边。

可以先用两个 JSON 文件：

```text
graph_nodes.json
graph_edges.json
```

节点结构：

```json
{
  "concept_bayes_theorem": { ... },
  "episode_20260603_001": { ... },
  "skill_contrastive_explanation": { ... }
}
```

边结构：

```json
[
  {
    "edge_type": "episode_concept",
    "source": "episode_20260603_001",
    "target": "concept_bayes_theorem",
    "weight": 0.91
  },
  {
    "edge_type": "episode_skill",
    "source": "episode_20260603_001",
    "target": "skill_contrastive_explanation",
    "weight": 0.84
  }
]
```

### Step 5：实现 Concept Updater

目标：根据 Episode outcome 更新 Concept learner_state。

简单规则即可：

```python
def update_concepts_by_episode(episode, concepts):
    for concept_id in episode["concepts"]:
        concept = concepts.get(concept_id)
        if not concept:
            concept = create_new_concept(concept_id)
        update_mastery(concept, episode["outcome"]["result"])
        update_misconceptions(concept, episode["student_state"].get("misconceptions", []))
        concepts[concept_id] = concept
```

### Step 6：实现 Skill Updater

目标：根据 tutor_action.strategy 找到对应 Skill，并更新质量。

```python
def update_skill_by_episode(episode, skills):
    strategy = episode["tutor_action"].get("strategy")
    skill_id = map_strategy_to_skill(strategy)

    if skill_id not in skills:
        skills[skill_id] = create_skill_from_episode(episode)

    update_skill_quality(skills[skill_id], episode["outcome"]["result"])
    return skill_id
```

### Step 7：实现 Retriever

目标：用户新问题进来时，找相关 Concept、Episode、Skill。

```python
def retrieve_memory(user_query, graph_store, vector_store):
    concepts = retrieve_concepts(user_query, graph_store, vector_store)
    episodes = retrieve_episodes_by_concepts(concepts, graph_store)
    skills = retrieve_skills_by_episodes(episodes, graph_store)

    return build_personalized_context(
        user_query=user_query,
        concepts=concepts,
        episodes=episodes,
        skills=skills
    )
```

### Step 8：实现 Tutor Agent

目标：用检索到的记忆生成个性化回答。

```python
def tutor_reply(user_query):
    memory_context = retrieve_memory(user_query, graph_store, vector_store)
    prompt = TUTOR_PROMPT.format(
        user_query=user_query,
        memory_context=json.dumps(memory_context, ensure_ascii=False, indent=2)
    )
    answer = call_llm(prompt)
    return answer
```

---

## 13. 示例：一次完整运行过程

### 13.1 学生第一轮提问

```text
学生：为什么不能直接用检测准确率当作患病概率？
```

DataFlow 记录：

```json
{
  "event_id": "event_001",
  "session_id": "session_001",
  "turn_index": 1,
  "actor": "student",
  "event_type": "user_message",
  "content": "为什么不能直接用检测准确率当作患病概率？"
}
```

### 13.2 Tutor 回答

Tutor 根据当前问题解释条件概率方向。

DataFlow 记录 assistant_message。

### 13.3 Buffer 触发 Episode 抽取

系统抽取 Episode：

```json
{
  "node_id": "episode_001",
  "node_type": "episode",
  "topic": "Bayes theorem explanation",
  "summary": "学生混淆检测准确率和患病后验概率，导师使用对比解释帮助学生区分。",
  "concepts": ["bayes_theorem", "conditional_probability"],
  "student_state": {
    "detected_problem": "inverse conditional probability confusion",
    "understanding_before": "low",
    "understanding_after": "partial",
    "misconceptions": ["混淆 P(A|B) 和 P(B|A)"]
  },
  "tutor_action": {
    "strategy": "contrastive_explanation"
  },
  "outcome": {
    "result": "partial_success",
    "score": 0.6
  }
}
```

### 13.4 更新图

创建 Concept：

```text
concept_bayes_theorem
concept_conditional_probability
```

创建或更新 Skill：

```text
skill_contrastive_explanation
```

创建边：

```text
episode_001 --episode_concept--> concept_bayes_theorem
episode_001 --episode_concept--> concept_conditional_probability
episode_001 --episode_skill--> skill_contrastive_explanation
```

### 13.5 学生后续再问

```text
学生：我还是不懂贝叶斯公式。
```

系统检索到：

```text
Concept:
  bayes_theorem，mastery = 0.42，status = weak

Episode:
  上次学生混淆 P(A|B) 和 P(B|A)，通过对比解释后部分理解。

Skill:
  contrastive_explanation，confidence = 0.75
```

Tutor 回答时就不会泛泛解释公式，而会说：

```text
你上次主要卡在“条件方向”上。我们这次先不背公式，先把 P(A|B) 和 P(B|A) 的含义分清楚……
```

这就是个性化记忆起作用的地方。

---

## 14. 可视化建议

Demo 展示时可以做三个视图。

### 14.1 DataFlow View

展示原始事件流：

```text
[10:00] student: 为什么不能直接用检测准确率当作患病概率？
[10:01] assistant: 这里要区分 P(阳性|患病) 和 P(患病|阳性)...
[10:02] student: 所以它们不是一个东西？
[10:03] assistant: 对，我们用一个小例子看...
```

### 14.2 Memory Graph View

展示图结构：

```text
Bayes Theorem      Conditional Probability
      \                    /
       \                  /
        Episode 001
             |
             |
   Contrastive Explanation Skill
```

### 14.3 Personalized Context View

展示模型回答前检索到的记忆：

```json
{
  "learner_state": "学生在 Bayes Theorem 上仍然较弱，主要误区是混淆条件方向。",
  "relevant_episode": "上次通过对比解释后部分理解。",
  "recommended_skill": "contrastive_explanation"
}
```

这个视图对论文和 Demo 都很有用，因为能直观看到记忆机制如何影响回答。

---

## 15. 实验设计建议

### 15.1 Baseline

可以比较以下几类：

```text
1. No Memory
   不使用历史记忆。

2. Vector Memory
   只用向量检索历史对话。

3. Episode-only Memory
   只检索 Episode，不使用 Concept 和 Skill。

4. EduFlowGraph-Lite
   使用 Concept ← Episode → Skill 结构。
```

### 15.2 评估任务

推荐三个任务：

```text
1. Personalized Explanation
   同一个知识点问题，系统是否能根据学生历史误区调整解释？

2. Weakness-aware Question Generation
   系统是否能根据 Concept learner_state 生成合适练习？

3. Skill-aware Tutoring
   系统是否能使用历史上有效的教学 Skill？
```

### 15.3 评估指标

可以使用 LLM-as-a-Judge 或人工评价：

```text
Personalization Score
  回答是否利用了学生历史状态？

Diagnosis Accuracy
  是否正确识别学生误区？

Pedagogical Appropriateness
  教学策略是否适合当前学生？

Concept Alignment
  是否围绕正确知识点展开？

Helpfulness
  学生是否更容易理解？

Memory Usefulness
  检索到的记忆是否真正有用？
```

### 15.4 一个简单评价 Prompt

```text
你是一个 AI 教育系统评估专家。
请评价下面的 Tutor 回答是否充分利用了学生历史记忆。

学生当前问题：
{query}

学生历史记忆：
{memory_context}

Tutor 回答：
{answer}

请从 1-5 分评价：
1. 个性化程度
2. 误区针对性
3. 教学策略合理性
4. 回答清晰度
5. 是否适合学生当前水平

请输出 JSON，并给出简短理由。
```

---

## 16. 后续扩展方向

第一版不要加入复杂结构，但可以为后续扩展预留空间。

### 16.1 Misconception 升级为节点

当前 Misconception 存在 Concept Node 和 Episode Node 的字段里。

如果后续发现误区建模非常重要，可以升级为：

```text
Misconception Node
```

形成：

```text
Concept ← Episode → Skill
              ↓
        Misconception
```

### 16.2 Review Node

如果要做主动复习，可以加入：

```text
ReviewNeed Node
```

用于表示：

```text
哪些概念需要复习？
什么时候复习？
用什么题型复习？
```

### 16.3 Concept-Concept Edge

如果课程知识结构很重要，可以把 Concept 内部字段升级成边：

```text
Concept A --prerequisite_of--> Concept B
Concept A --similar_to--> Concept B
Concept A --contrasts_with--> Concept B
```

### 16.4 Skill-Concept Edge

如果积累了足够 Episode，可以显式建立：

```text
Skill --effective_for--> Concept
```

但第一版不建议直接加，因为可以通过 Episode 间接统计。

### 16.5 更强的 Skill Induction

第一版 Skill 可以手工初始化 + 简单更新。

后续可以做：

```text
成功 Episode 聚类
   ↓
抽取共同 trigger / procedure / outcome
   ↓
生成候选 Skill
   ↓
多次验证后提升为正式 Skill
```

---

## 17. 最终推荐方案固定版

### 17.1 系统名称

推荐名称：

```text
EduFlowGraph-Lite
```

或者论文风格名称：

```text
Episode-Centric Educational Memory Graph
```

### 17.2 核心组成

```text
DataFlow:
  保存完整 tutoring event stream。

Memory Graph:
  Concept Node
  Episode Node
  Skill Node

Edges:
  Episode-Concept Edge
  Episode-Skill Edge
```

### 17.3 核心思想

```text
Concepts are what the learner studies.
Episodes are what actually happened.
Skills are how the tutor teaches.
```

中文：

```text
Concept 表示学生学什么。
Episode 表示学习过程中实际发生了什么。
Skill 表示导师如何教学，以及什么教学方式有效。
```

### 17.4 方法贡献

这个方案的贡献可以总结为三点：

```text
1. 从 session 内 trace forest 转向跨 session 的 episode-centric memory graph。

2. 使用 DataFlow + Memory Graph 双层结构，既保留完整交互轨迹，又支持结构化个性化检索。

3. 引入 Skill Node，把成功教学轨迹压缩成可复用的教学程序性记忆。
```

### 17.5 最小实现目标

Demo 第一版只需要证明：

```text
1. 系统能从对话中抽取 Episode。
2. 系统能通过 Episode 更新 Concept 掌握状态。
3. 系统能通过 Episode 找到相关 Skill。
4. 系统能在后续回答中使用这些记忆进行个性化教学。
```

---

## 18. 一句话总结

EduFlowGraph-Lite 不追求一开始构建复杂教育知识图谱，而是采用一个极简但可扩展的结构：

```text
DataFlow 记录完整交互轨迹；
Episode 从交互轨迹中提取关键学习片段；
Concept 记录学生在知识点上的状态；
Skill 记录有效的教学方式；
Episode 作为桥梁连接 Concept 和 Skill。
```

最核心结构就是：

```text
Concept ← Episode → Skill
```

这个结构足够简单，适合快速实现 Demo；同时也保留了后续扩展空间，可以逐步加入 Misconception、Review、Concept-Concept Edge、Skill-Concept Edge 等更复杂模块。
