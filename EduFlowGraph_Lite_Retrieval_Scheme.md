# EduFlowGraph-Lite 检索召回方案

## 1. 核心目标

EduFlowGraph-Lite 的记忆召回不是为了把历史聊天记录全部塞给 Tutor，而是为了在新对话中回答三个问题：

```text
1. 学生现在正在学什么 Concept？
2. 学生过去在这些 Concept 上发生过什么 Episode？
3. 过去有哪些 Skill 可以指导这次 Tutor 应该怎么教？
```

因此，检索召回的核心逻辑是：

```text
Current Query
  → Concept Recall
  → Episode Recall
  → Skill Recall
  → Memory Context Pack
  → Tutor Response
```

对应图结构：

```text
Concept ← Episode → Skill
```

一句话总结：

> Concept 决定召回范围，Episode 提供历史证据，Skill 提供教学动作。

---

## 2. 节点 Embedding 的生成时机

每个节点的 embedding 应该在节点创建或节点语义更新时预先生成并保存，而不是每次用户提问时重新编码所有节点。

```text
建图阶段：
  Node → embedding_text → embedding vector → vector index

检索阶段：
  Query → query embedding → vector search → recalled nodes
```

### 2.1 Concept Node Embedding

Concept Node 创建时生成 embedding。

推荐 embedding_text：

```text
Concept: Policy Gradient
Aliases: 策略梯度, REINFORCE, Policy Gradient Theorem
Description: A reinforcement learning method that directly optimizes policy parameters using gradient estimates.
```

Concept embedding 用于识别当前 query 涉及哪些概念。

### 2.2 Episode Node Embedding

Episode Node 抽取完成时生成 embedding。

推荐 embedding_text：

```text
Student struggled with policy gradient derivation, especially the log-derivative trick.
Tutor used step-by-step derivation and trajectory examples.
Outcome: partial success.
```

Episode embedding 用于召回相似历史学习事件。

### 2.3 Skill Node Embedding

Skill Node 蒸馏完成时生成 embedding。

推荐 embedding_text：

```text
Use this skill when the learner struggles with policy gradient derivation or the log-derivative trick.
Teach from expected return, introduce the log-derivative trick step by step, use trajectory examples, and ask for self-explanation.
```

Skill embedding 用于召回可复用教学程序。

---

## 3. 在线检索总流程

每次新对话生成回答前，执行如下流程：

```text
Step 1：Memory Need Detection
Step 2：Query Understanding
Step 3：Concept Recall
Step 4：Episode Recall
Step 5：Skill Recall
Step 6：Reranking
Step 7：Context Packing
Step 8：Tutor Response Generation
```

第一版 Demo 可以简化为：

```text
User Query
  → 识别 / 召回 Concept
  → 通过 Episode-Concept Edge 找 Top-K Episodes
  → 通过 Episode-Skill Edge 找 Top-K Skills
  → 生成 Memory Context Pack
  → Tutor 基于记忆回答
```

---

## 4. Step 1：Memory Need Detection

不是每个问题都必须召回记忆。系统应先判断当前 query 是否需要个性化记忆。

需要召回记忆的典型情况：

```text
1. 学生说“我还是不懂”“又忘了”“继续讲”
2. 学生追问之前学过的内容
3. 当前问题涉及已有 Concept Node
4. 当前任务是复习、纠错、练习或评估
5. Tutor 需要决定使用什么教学策略
```

输出示例：

```json
{
  "need_memory": true,
  "reason": "The learner says they still do not understand a previously discussed concept."
}
```

第一版也可以默认每次都检索，但后续建议加入该判断以降低噪声和成本。

---

## 5. Step 2：Query Understanding

对当前 query 做轻量分析，得到：

```json
{
  "raw_query": "我还是不理解策略梯度为什么要用 log pi。",
  "detected_concepts": [
    "Policy Gradient",
    "Log-derivative Trick",
    "REINFORCE"
  ],
  "learner_signal": "still_confused",
  "intent": "concept_explanation"
}
```

这个结果用于后续 Concept Recall 和 Skill Recall。

---

## 6. Step 3：Concept Recall

Concept Recall 的目标是找到当前 query 涉及的核心概念。

推荐采用混合召回：

```text
1. Name / Alias 精确匹配
2. Query embedding 与 Concept embedding 向量检索
3. 合并结果并重排
```

示例：

```text
Query:
  我还是不理解策略梯度为什么要用 log pi。

召回 Concepts:
  - Policy Gradient
  - Log-derivative Trick
  - REINFORCE
```

Concept 排序可以采用简单公式：

```text
concept_score =
  0.6 * embedding_similarity
+ 0.3 * alias_match_score
+ 0.1 * prior_score
```

其中：

```text
alias_match_score:
  命中 name / alias 时给高分

prior_score:
  可以来自该 concept 的历史 episode 数量、近期出现频率等
```

第一版 Demo 中，如果 Concept 数量较少，可以直接用 numpy 暴力计算 cosine similarity；后续再替换为 FAISS、Chroma、Qdrant、Milvus 或 pgvector。

---

## 7. Step 4：Episode Recall

拿到 Top-K Concepts 后，通过 Episode-Concept Edge 召回相关 Episodes。

```text
Concept → Episode-Concept Edge → Episode
```

Episode 排序时考虑：

```text
1. query 与 episode embedding_text 的语义相似度
2. Episode-Concept Edge.importance_score
3. Episode outcome 是否与当前意图匹配
4. 时间新近程度
5. 是否包含相似 learner difficulty
```

推荐评分公式：

```text
episode_score =
  0.40 * semantic_similarity
+ 0.25 * concept_importance_score
+ 0.15 * outcome_relevance
+ 0.10 * recency_score
+ 0.10 * difficulty_match
```

`outcome_relevance` 的直觉：

```text
当前学生 still_confused：
  优先召回 failed / unresolved / partial_success 以及后续转变为 success 的轨迹

当前任务是复习：
  优先召回曾经 partial_success / failed 的 episode

当前任务是重新讲解：
  优先召回成功解释过的 episode
```

第一版建议只保留：

```text
Top 3 Episodes
```

Episode 是历史证据，过多会污染上下文。

---

## 8. Step 5：Skill Recall

Skill Recall 有两条路径。

### 8.1 Direct Skill Recall

直接用当前 query embedding 检索 Skill Node embedding。

```text
Query → Skill Vector Index → Top Skills
```

适合当前 query 明确表达某种学习困难时，例如：

```text
我不懂策略梯度里面 log pi 是怎么来的。
```

可能召回：

```text
Teach policy gradient through stepwise derivation and trajectory examples
```

### 8.2 Graph-expanded Skill Recall

从召回的 Episodes 出发，通过 Episode-Skill Edge 召回 Skills：

```text
Relevant Episode → Episode-Skill Edge → Skill
```

如果某个 Skill 被多个高分 Episode 支持，并且 contribution_score 高，则优先使用。

推荐评分公式：

```text
skill_score =
  0.40 * trigger_similarity
+ 0.25 * linked_episode_score
+ 0.20 * contribution_score
+ 0.15 * skill_confidence
```

第一版建议只召回：

```text
Top 1 Skill，最多 Top 2 Skills
```

Skill 是教学动作建议，太多容易冲突。

---

## 9. Step 6：Reranking

最终召回结果需要统一重排，避免召回无关历史。

调用一个ReRanker模型来进行

---

## 10. Step 7：Memory Context Pack

不要把原始节点 JSON 直接塞给 Tutor。检索结果应该被压缩成一个结构化的 Memory Context Pack。

推荐格式：

```text
[Memory Context]

Current related concepts:
- Policy Gradient
- Log-derivative Trick
- REINFORCE

Learner history:
- The learner previously struggled to understand why policy gradient can be written as an expectation.
- The learner was especially confused about the log-derivative trick.
- Step-by-step derivation plus trajectory examples helped them reach partial understanding.

Relevant past episodes:
1. episode_012: The learner failed to connect expected return with gradient estimation.
2. episode_013: The tutor decomposed the formula and the learner partially understood the log-derivative step.
3. episode_014: A trajectory example helped the learner explain the estimator intuitively.

Recommended pedagogical skill:
Use "Teach policy gradient through stepwise derivation":
1. Start from expected return.
2. Identify policy-dependent terms.
3. Introduce log-derivative trick slowly.
4. Explain sampling interpretation.
5. Use a short trajectory example.
6. Ask learner to restate the estimator.

Teaching instruction:
Do not start directly from the final formula. First rebuild the derivation path and check the learner's understanding after each step.
```

Memory Context Pack 的作用是：

```text
把图谱召回结果转化成 Tutor 可执行的教学上下文。
```

---

## 11. Step 8：Tutor Response Generation

Tutor 不应机械暴露记忆内容，而应将记忆转化为教学行为。

不推荐：

```text
根据你的历史记录，你之前在 episode_014 中……
```

推荐：

```text
我们先不要直接看最终公式。你卡住的关键通常是：
为什么 ∇θπθ(a|s) 可以写成 πθ(a|s)∇θlogπθ(a|s)。

这次我按三步来讲：
第一步从目标函数开始；
第二步只处理和 θ 有关的项；
第三步再引入 log trick。
```

也就是说：

```text
记忆召回结果
  → 改变解释顺序
  → 调整难度
  → 选择例子
  → 决定是否追问
  → 检查学生是否真正理解
```

---

## 12. DataFlow 在在线检索中的位置

默认情况下，在线检索不直接使用 DataFlow。

在线回答主要使用：

```text
MemoryGraph:
  Concept Node
  Episode Node
  Skill Node
  Episode-Concept Edge
  Episode-Skill Edge
```

DataFlow 只在以下情况使用：

```text
1. 需要回看原始对话细节
2. 需要蒸馏或更新 Skill
3. 需要 debug 某个 Episode 为什么被抽取
4. 用户明确问“我之前具体怎么说的”
```

因此，在线检索路径是：

```text
Query → MemoryGraph
```

而不是：

```text
Query → DataFlow
```

DataFlow 是 evidence replay layer，不是常规在线检索层。

---

## 13. 最小 Demo 实现建议

第一版 Demo 可以这样实现：

```text
1. 所有 Concept / Episode / Skill 创建时计算 embedding 并存入向量索引
2. 新 query 到来时只计算 query embedding
3. 召回 Top-K Concept
4. 通过 Episode-Concept Edge 扩展 Top 3 Episode
5. 通过 Episode-Skill Edge 扩展 Top 1 Skill
6. 生成 Memory Context Pack
7. Tutor 根据 Context Pack 生成回答
```

推荐技术路线：

```text
小规模：
  SQLite + numpy cosine similarity

中等规模：
  FAISS / Chroma / LanceDB

正式系统：
  Qdrant / Milvus / pgvector
```

第一版不要做过度复杂的多跳图搜索。先证明：

```text
Concept → Episode → Skill
```

这条召回链路能够让 Tutor 更个性化、更贴合学生历史困难。

---

## 14. 最终原则

EduFlowGraph-Lite 的检索召回遵守三条原则：

1. **节点 embedding 预计算。**  
   节点创建或语义更新时生成 embedding；在线时只编码 query。

2. **Concept 作为召回入口。**  
   先确定当前学习概念，再召回历史 episode。

3. **Skill 作为教学动作建议。**  
   Skill 不只是历史内容，而是指导 Tutor 如何教。

最终一句话定义：

> 检索召回的目标不是找到最相似的历史聊天，而是找到当前学生正在学的概念、过去相关的学习证据，以及最可能有效的教学技能。
