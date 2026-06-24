# 通用教学 Skill 蒸馏设计

## 目标

Skill Node 表达“对该学生反复有效、可迁移到新知识点的教学方法”，而不是某个概念、题目或 Episode 的教学摘要。系统继续要求至少两个独立 Episode 和可观察的正向学习结果，但不再把 Concept 同族作为蒸馏、去重或验证的硬条件。

## 当前问题

当前证据窗口同时要求单一 `difficulty_pattern` 完全相等、教学动作存在交集、Concept 属于同一族。验证与去重也要求 Concept 同族。这会把 Skill 限制成知识点局部规则，例如不同数学公式上反复有效的“公式拆解 + 分步推导”无法合并，违背 Skill 的跨场景复用职责。

## 节点语义

Skill 保留兼容字段 `difficulty_pattern`，并新增 `difficulty_patterns`：

- `difficulty_patterns`：支撑该方法的一个或多个学习困难模式；
- `difficulty_pattern`：主困难模式，供旧接口、旧 UI 和旧数据继续使用；
- `teaching_actions`：只保存跨支持 Episode 稳定出现的核心动作；
- `trigger`、`procedure`、`success_criteria`、`embedding_text`：只描述通用学习情境、教学方法和验证信号，禁止出现具体 Concept、题目、数值、Episode 或会话信息；
- `metadata.evidence_concept_scope`：仅保存有限的证据来源用于审计，不参与硬匹配，也不进入公共 Skill 文案。

旧 Skill 若没有 `difficulty_patterns`，运行时自动视为 `[difficulty_pattern]`。

## 困难兼容性

系统使用开放的困难模式集合，而不是为“数学公式”“晦涩概念”等用户示例写专用分支。困难模式之间按学习障碍结构建立可解释的兼容关系：

- `symbol_grounding` 与 `procedural_gap` 都可支持形式化内容的拆解型方法；
- `abstraction_gap` 与 `conceptual_confusion` 都可支持概念落地型方法；
- 相同困难模式始终兼容；
- `direction_confusion`、`transfer_failure` 保持更专门的边界，除非证据本身具有相同模式；
- `unknown` 永不参与自动蒸馏。

兼容关系只是证据候选窗口，不直接保证创建 Skill。最终仍需稳定教学动作和正向结果。

## 稳定教学动作

证据窗口要求当前证据与历史证据至少共享一个教学动作。蒸馏时只选择在至少一半支持 Episode 中出现的动作，并至少要求一个核心动作。这样既允许一次教学包含诊断或复述等辅助动作，也避免把偶然动作全部写进 Skill。

Skill 去重和验证使用核心动作 Jaccard 相似度；概念名称不再参与判断。相同或兼容困难模式且核心动作高度重叠的候选视为同一教学方法。

## 蒸馏与验证流程

1. Episode 结束后提取 SkillEvidence：具体 Concept、主困难模式、实际教学动作和结果。
2. 从最近证据中选择困难兼容、教学动作有交集的最多四条独立 Episode 证据。
3. 至少两个独立 Episode，且存在学习改善或重复正向结果时才允许蒸馏。
4. 生成 `candidate`，公共字段完全通用化；Concept 只进入审计元数据和 Episode-Skill 证据边。
5. 新 Concept 上出现兼容困难、核心动作匹配且结果为正时，可验证该 Skill；满足既有质量门槛后晋升 `active`。

## 检索

Skill 的直接召回和个性化 ReRank 主要使用：当前困难提示、学习意图、Skill 通用语义、质量与 TeachingAdaptationModel。历史 Concept 只作为来源追踪和很弱的相关性信号，不再进入 Skill 检索关键词，也不阻止跨概念召回。

## LLM 约束

蒸馏提示词明确要求：

- 允许跨知识点、跨章节、跨学科证据共同支撑 Skill；
- 判断共同的学习困难与有效教学动作，而不是寻找相同主题词；
- `difficulty_patterns` 只能来自输入证据；
- 公共字段不得出现具体概念、学科对象、题目、数值、事件或会话；
- 无法形成可迁移方法时返回不创建。

LLM 输出仍经过本地 fallback 结构约束；即使模型输出带入具体概念，本地会优先使用已生成的通用字段边界和合法枚举。

## 测试标准

- 不同数学概念上的公式拆解与分步推导可以蒸馏为同一个通用 Skill；
- 不同学科的抽象概念可由具体例子类动作形成通用 Skill；
- 只有概念相同、但困难或教学动作不稳定时不能创建 Skill；
- 新概念证据可以验证已有 Skill；
- 不兼容困难或低动作重叠不会误验证、误去重；
- Skill 公共字段不包含任何支持证据中的具体概念或 Episode 标识；
- 旧的单 `difficulty_pattern` Skill 继续可读取、匹配、检索和渲染。

