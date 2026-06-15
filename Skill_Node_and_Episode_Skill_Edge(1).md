# Skill Node 与 Episode-Skill Edge 构造方案

## 1. 核心定义

在 EduFlowGraph-Lite 中，Skill Node 表示从成功教学轨迹中蒸馏出的可复用教学程序。它不是单次对话摘要，也不是普通教学策略标签，而是记录：

> 在什么学习困难下，Tutor 应该采取什么教学步骤，以及如何判断学生真正理解。

Episode Node 记录“具体发生过什么”，Concept Node 记录“涉及什么概念”，Skill Node 记录“怎样教可能有效”。

整体结构为：

```text
Concept ← Episode → Skill
```

其中：

- `Episode-Concept Edge` 表示某个概念在该 episode 中的重要程度。
- `Episode-Skill Edge` 表示某个 episode 对某个 skill 的证据贡献程度。

---

## 2. Skill Node 的生成原则

Skill Node 不应该从单个普通 Episode 中随意生成，而应该从一组具有学习转变的 Episodes 中蒸馏出来。

推荐采用三阶段流程：

```text
Skill Evidence → Skill Candidate → Active Skill
```

### 2.1 Skill Evidence：在线收集

每个 Episode 结束后，系统只记录其中出现的教学动作和结果，例如：

```json
{
  "episode_id": "episode_014",
  "concepts": ["Policy Gradient", "REINFORCE"],
  "teaching_actions": [
    "step_by_step_derivation",
    "formula_decomposition",
    "worked_example",
    "student_self_explanation"
  ],
  "outcome": "partial_success"
}
```

这一步不直接创建 Skill Node，只作为后续蒸馏证据。

### 2.2 Skill Candidate：Session 后蒸馏

当一个 session 结束，系统检查是否存在如下轨迹：

```text
学生不懂 / failed / unresolved
      ↓
Tutor 多次解释、提示、举例、推导
      ↓
学生 partial_success / success
```

如果存在明显的学习转变，并且 Tutor 的教学动作可以总结为可复用步骤，则生成 Skill Candidate。

### 2.3 Active Skill：长期验证后升级

当某个 Skill Candidate 在后续多个 Episode 中再次被使用并取得正向效果，可以升级为 Active Skill。

简化规则：

```text
source_episode_count >= 2
且 success_count >= 1
且 confidence >= 0.7
```

---

## 3. Skill Node 最小 Schema

第一版 Skill Node 应该保持简洁，只保存可复用教学程序所需的信息。

```json
{
  "skill_id": "skill_policy_gradient_stepwise_derivation",
  "node_id": "skill_policy_gradient_stepwise_derivation",
  "node_type": "skill",

  "name": "Teach policy gradient through stepwise derivation",

  "status": "candidate",

  "trigger": "Use when the learner is confused about policy gradient derivation, expected return, or the log-derivative trick.",

  "procedure": [
    "Start from the expected return objective.",
    "Ask the learner to identify which terms depend on policy parameters.",
    "Introduce the log-derivative trick step by step.",
    "Explain the sampling interpretation of the gradient estimator.",
    "Use a short trajectory example to connect actions, rewards, and gradients.",
    "Ask the learner to restate the final estimator in their own words."
  ],

  "success_criteria": [
    "The learner can explain why ∇θ log πθ(a|s) appears.",
    "The learner can describe policy gradient as increasing probabilities of high-return actions.",
    "The learner can apply the estimator to a simple trajectory example."
  ],

  "source_episode_ids": [
    "episode_011",
    "episode_012",
    "episode_013",
    "episode_014"
  ],

  "confidence": 0.82,

  "embedding_text": "Use this skill when a learner struggles with policy gradient derivation, expected return, log-derivative trick, or REINFORCE. Teach through stepwise derivation, trajectory examples, and learner self-explanation."
}
```

字段解释：

| 字段 | 含义 |
|---|---|
| `name` | Skill 的简短名称 |
| `status` | `candidate` 或 `active` |
| `trigger` | 什么时候应该调用这个 Skill |
| `procedure` | Tutor 应该执行的教学步骤 |
| `success_criteria` | 如何判断学生真正理解 |
| `source_episode_ids` | Skill 来源于哪些成功教学轨迹 |
| `confidence` | 当前对该 Skill 有效性的置信度 |
| `embedding_text` | 用于后续向量检索的文本 |

---

## 4. Episode-Skill Edge 的含义

Episode-Skill Edge 表示：

> 某个具体 Episode 对某个 Skill 的证据贡献。

它可以表达两种情况，但边类型仍然保持一种：

```text
episode_skill
```

### 4.1 Skill 来源证据

如果某个 Skill 是从一组 Episodes 中蒸馏出来的，那么这些 Episodes 与 Skill 之间建立边，表示它们共同支持了该 Skill 的产生。

```text
episode_011
episode_012
episode_013
episode_014
      ↓
skill_policy_gradient_stepwise_derivation
```

### 4.2 Skill 应用验证

如果后续 Tutor 调用了已有 Skill，并在新的 Episode 中取得效果，则新 Episode 也与该 Skill 建边，表示该 Skill 被再次验证。

---

## 5. Episode-Skill Edge 最小 Schema

```json
{
  "edge_id": "edge_episode_014_skill_policy_gradient_stepwise_derivation",
  "edge_type": "episode_skill",

  "episode_id": "episode_014",
  "skill_id": "skill_policy_gradient_stepwise_derivation",

  "contribution_score": 0.91,
  "confidence": 0.86,

  "evidence": "The learner understood policy gradient after the tutor used stepwise derivation and a trajectory example."
}
```

字段解释：

| 字段 | 含义 |
|---|---|
| `episode_id` | 来源 Episode |
| `skill_id` | 关联 Skill |
| `contribution_score` | 该 Episode 对 Skill 的支持/验证程度 |
| `confidence` | 对该边判断的置信度 |
| `evidence` | 为什么这条边成立 |

`contribution_score` 建议解释为：

```text
0.90-1.00：核心成功案例，完整体现该 Skill，且结果很好
0.70-0.89：明显使用该 Skill，并产生正向效果
0.40-0.69：部分体现该 Skill，但过程或结果不完整
<0.40：不建议建边
```

---

## 6. Skill 蒸馏触发时机

推荐采用半离线策略：

```text
Episode 结束：
  只记录 teaching_actions 和 outcome，作为 skill evidence

Session 结束：
  检查是否存在 failed/partial → success 的学习转变
  如果存在，运行 Skill Distiller，生成 Skill Candidate

长期离线：
  合并相似 Skill
  更新 success_count / fail_count / confidence
  将高质量 candidate 升级为 active
```

第一版 Demo 可以只实现：

```text
Session 结束后蒸馏 Skill Candidate
```

---

## 7. Skill Distillation Prompt 的目标

Skill Distiller 的 Prompt 只需要回答：

```text
这组 Episodes 是否包含一个可复用的成功教学程序？
```

如果是，则抽取：

```text
1. 学生最初的困难
2. Tutor 的关键教学动作
3. 导致理解转变的关键步骤
4. 未来何时触发该 Skill
5. 可复用的教学步骤
6. 成功判断标准
7. 支持该 Skill 的 Episode
```

---


---

## 8. DataFlow 在 Skill 蒸馏中的作用

DataFlow 不参与在线 Episode 抽取，但它是后续 Skill 蒸馏的重要证据来源。

三者职责应明确区分：

```text
SessionBuffer：
  在线临时缓存，用于当前 learning episode 的边界判断与 Episode 抽取。

MemoryGraph / Episode Graph：
  结构化学习轨迹索引，用于发现某个 concept 下的相关 episodes 和潜在成功学习转变。

DataFlow：
  原始学习轨迹档案，用于回放、溯源、debug，以及从成功轨迹中蒸馏 Skill。
```

因此，Skill 蒸馏不应该直接从全量 DataFlow 中盲目扫描开始，而应该采用：

```text
先由 Episode Graph 定位候选成功轨迹，
再通过 Episode.source_event_ids 回查 DataFlow 原始对话，
最后基于完整原始轨迹蒸馏 Skill。
```

---

## 9. 为什么 Skill 蒸馏需要 DataFlow

Episode Node 是对一段学习事件的结构化压缩，适合检索、建图和快速判断学习结果。但 Skill Node 需要的是更加细粒度的教学过程，例如：

```text
Tutor 是如何一步步推导的？
先讲直觉还是先讲公式？
使用了什么例子？
学生在哪一步突然理解？
Tutor 如何检查学生是否真正掌握？
```

这些细节往往存在于 DataFlow 的原始 user / assistant 对话中，而不一定完整保存在 Episode Node 里。

因此：

```text
Episode Node 负责发现“哪里可能存在成功轨迹”；
DataFlow 负责还原“这条成功轨迹具体是怎么发生的”；
Skill Distiller 负责从原始轨迹中抽象出可复用教学程序。
```

---

## 10. 基于 DataFlow 的 Skill 蒸馏流程

推荐流程如下：

```text
Step 1：从 Episode Graph 中选择目标 concept
Step 2：检索该 concept 相关的 episodes，并按时间排序
Step 3：检测是否存在 failed / unresolved / partial_success → success 的学习转变
Step 4：读取这些 episodes 的 source_event_ids
Step 5：从 DataFlow 中取回原始对话内容
Step 6：将原始轨迹输入 Skill Distiller
Step 7：生成 Skill Node 和 Episode-Skill Edges
```

示例：

```text
episode_011: 学生不理解策略梯度为什么是期望形式，outcome = unresolved
episode_012: 学生仍然卡在 log-derivative trick，outcome = failed
episode_013: Tutor 开始逐步推导，outcome = partial_success
episode_014: Tutor 结合轨迹例子讲解，学生能够复述，outcome = success
        ↓
发现同一 concept 上出现学习转变
        ↓
根据 source_event_ids 回查 DataFlow 原始对话
        ↓
蒸馏出 Skill：Teach policy gradient through stepwise derivation and trajectory examples
```

---

## 11. DataFlow 与 Episode 的链接方式

为了支持 Skill 蒸馏，Episode Node 需要保存原始事件引用：

```json
{
  "episode_id": "episode_014",
  "source_event_ids": [
    "evt_041",
    "evt_042",
    "evt_043",
    "evt_044"
  ],
  "outcome": "success"
}
```

DataFlow event 中可以可选保存反向链接：

```json
{
  "event_id": "evt_041",
  "session_id": "session_003",
  "turn_id": "turn_008",
  "role": "user",
  "content": "我还是不明白为什么策略梯度里面会出现 log pi。",
  "linked_episode_id": "episode_014"
}
```

这样可以形成双向追溯：

```text
Episode → source_event_ids → DataFlow 原始对话
DataFlow event → linked_episode_id → 所属 Episode
```

其中，Skill 蒸馏主要依赖第一条路径：

```text
Episode.source_event_ids → DataFlow.event_id → 原始教学轨迹
```

---

## 12. DataFlow 最小字段要求

为了支持 Skill 蒸馏，DataFlow 不需要复杂结构，但至少应保存：

```text
event_id
learner_id
session_id
turn_id
timestamp
role
content
linked_episode_id
metadata
```

其中最关键的是：

```text
event_id：用于被 Episode.source_event_ids 引用
content：保存原始对话内容
linked_episode_id：用于追溯 event 属于哪个 Episode
```

如果条件允许，assistant message 的 metadata 可以额外保存：

```json
{
  "metadata": {
    "tutor_strategy": "step_by_step_derivation",
    "invoked_skill_ids": [],
    "model": "...",
    "prompt_version": "..."
  }
}
```

这些字段不是必须的，但有助于后续分析 Skill 是否被调用、是否有效。

---

## 13. 修正后的 Skill 蒸馏定位

最终，Skill 蒸馏应该被理解为：

```text
MemoryGraph 负责定位候选成功轨迹；
DataFlow 负责提供原始细节证据；
Skill Distiller 负责抽象可复用教学程序；
Episode-Skill Edge 负责记录每个 Episode 对 Skill 的证据贡献。
```

因此，DataFlow 的角色不是在线建图输入，而是：

> Skill distillation 的 evidence replay layer。

也就是说，DataFlow 使系统能够从压缩后的 Episode 回到完整教学轨迹，从而蒸馏出更加可靠、具体、可复用的 Skill Node。

## 14. 最终原则

Skill Node 构造要遵守三条原则：

1. **不要从单个普通 Episode 中轻易生成 Skill。**  
   Skill 应该来自一条或多条成功教学轨迹。

2. **Skill 不是摘要，而是程序。**  
   它必须能指导未来 Tutor 如何一步步教学。

3. **Episode-Skill Edge 是证据边。**  
   它记录某个 Episode 在多大程度上支持、体现或验证了该 Skill。

最终一句话定义：

> Skill Node 是从成功教学轨迹中蒸馏出的可复用教学程序；Episode-Skill Edge 是具体 Episode 对该教学程序的证据贡献。
