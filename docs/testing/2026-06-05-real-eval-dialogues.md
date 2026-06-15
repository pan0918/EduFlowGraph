# AITutor 真实测试对话手册

这份手册是给你做真实联调和产品测评用的。

目标不是只看“能不能回答”，而是一起观察这几条链是否真的工作：

- `LLM` 是否参与真实回答
- `Embedding` 是否在节点构造和检索时生效
- `Reranker` 是否在检索排序中生效
- `DataFlow` 是否正确记账
- `Episode / Concept / Skill` 是否逐步长出来
- `Memory Context Pack` 是否真的影响 Tutor 的讲法

## 测试前检查

在开始聊天前，建议先在 `Settings` 页面做这 3 个 diagnostics：

1. `LLM`
2. `Embedding`
3. `Reranker`

建议确认：

- `LLM` 返回 `status = ok`
- `Embedding` 返回 `Embedding length=...`
- `Reranker` 返回 `status = ok`
- `Reranker` 的 `request_preview.payload.documents` 是字符串数组，不是对象数组
- `contract_summary` 中：
  - LLM 的 `response_path` 是 `choices[0].message.content`
  - Embedding 的 `response_path` 是 `data[0].embedding`
  - Reranker 的 `response_path` 是 `results[].index`

## 观察面板

真实测试时，建议同时盯这几个地方：

- `Chat`
  - 回答是否像真的受历史记忆影响
- `右侧 Context Rail`
  - 是否出现 concepts / episodes / skills / context pack
- `Knowledge`
  - 是否出现 concept 节点
- `Skills`
  - 是否出现 candidate / active skill
- `Memory`
  - 是否出现 DataFlow 事件
  - 是否出现 episode / concept / skill 边

## 使用方式

下面每一组都可以单独测试。

- 如果你想观察“从零开始建图”，建议新开一个 session
- 如果你想观察“检索是否利用已有记忆”，就在同一个 session 里继续
- 每组下面的“预期观察”不是要求逐字一致，而是你应该大致看到这些行为

---

## 组 1：条件概率方向混淆，从零开始建图

这组最适合先跑，因为它最容易同时触发：

- episode
- concept
- skill evidence
- skill distillation
- retrieval

### 对话

1. `为什么不能直接把检测准确率当作患病概率？`
2. `我还是不懂 P(A|B) 和 P(B|A) 的区别。`
3. `你能再对比一下 P(A|B) 和 P(B|A) 吗？`
4. `懂了，我现在能说出这两个条件概率的方向差异。`
5. `请再对比一次 P(A|B) 和 P(B|A)，我想检查自己。`
6. `懂了，这次我可以自己解释这两个方向了。`

### 预期观察

- `Chat`
  - 回答应该围绕条件方向差异，而不是只给贝叶斯公式
- `Knowledge`
  - 大概率会出现 `Conditional probability`
  - 可能还会出现 `Bayes theorem`
- `Skills`
  - 大概率会出现一个与 `direction_confusion` 类似的 skill
  - 可能先是 `candidate`，后面升到 `active`
- `Memory`
  - 应该能看到：
    - `episode_extraction_completed`
    - `concept_extraction_completed`
    - `skill_evidence_recorded`
    - `skill_distillation_completed`
    - `skill_validation_recorded`

---

## 组 2：检索是否真的利用已有记忆

这组建议接着“组 1”同一个 session 继续跑。

### 对话

1. `我又分不清 P(A|B) 和 P(B|A) 了，能换个方式再讲吗？`

### 预期观察

- `Context Rail`
  - 应该出现和条件概率相关的 concepts
  - 应该出现相关 past episodes
  - 应该出现一个推荐 pedagogical skill
- `Chat`
  - 回答应该明显像“换一种讲法”
  - 不应该只是重复上一轮同样的解释顺序

---

## 组 3：comparison 意图测试

这组专门测试 query understanding 和 retrieval intent。

### 对话

1. `你帮我比较一下 P(A|B) 和 P(B|A) 到底差在哪。`

### 预期观察

- `Chat`
  - 回答应该采用并排对比风格
  - 更像“左边是什么意思，右边是什么意思，同一场景下有什么差异”
- `Context Rail`
  - `memory_context_pack` 里应该能看到 comparison 风格 instruction

---

## 组 4：assessment 意图测试

这组专门看 Tutor 会不会先检查再决定是否重讲。

### 对话

1. `你先别重新讲，先检查一下我是不是真的懂了条件概率。`

### 预期观察

- `Chat`
  - 第一反应应该是给一个短检查题或判断题
  - 不应该一上来就长篇重讲
- `Context Rail`
  - `Teaching instruction` 应该更接近：
    - `run a short check before re-teaching`

---

## 组 5：worked-example / formula-grounding 测试

这组专门看 Tutor 会不会先举例子，再解释公式符号含义。

### 对话

1. `不要只讲定义，先给我一个具体例子再解释这个公式每一项是什么意思。`

### 预期观察

- `Chat`
  - 回答应该先给一个小例子
  - 然后再把例子映射到公式每一项
  - 不应该先铺一大段抽象定义
- `Context Rail`
  - `memory_context_pack` 应该有 example-first 风格 instruction

---

## 组 6：concept shift / 新 episode 测试

这组专门看 boundary detection 和 episode 分段是否合理。

建议新开一个 session，也可以接着旧 session 测。

### 对话

1. `请解释一下条件概率。`
2. `再举一个条件概率例子。`
3. `好，那我们先停一下。现在请解释一下导数的几何意义。`
4. `导数和切线斜率为什么会对应起来？`

### 预期观察

- `Memory`
  - 应该不会把“条件概率”和“导数几何意义”强行塞进同一个 episode
- `Knowledge`
  - 后面应该可能出现和导数相关的新 concept

---

## 组 7：symbol grounding 测试

这组更适合测试“公式记住了，但不知道每一项是什么意思”的情况。

### 对话

1. `我记得贝叶斯公式长什么样，但我不知道里面每一项到底代表什么。`
2. `分子为什么是这个？分母又是在干嘛？`
3. `你先别推公式，先告诉我这些符号各自对应现实里的什么东西。`

### 预期观察

- `Chat`
  - 回答应该偏“符号接地”
  - 更像把抽象符号映射到现实含义
- `Skills`
  - 如果后续累积足够，可能出现 `symbol_grounding` 方向的 skill

---

## 组 8：procedural gap 测试

这组专门看系统会不会识别“不会从哪开始做”。

### 对话

1. `我知道条件概率定义，但题目一来我就不知道第一步该做什么。`
2. `这种题我应该先列什么，再看什么？`
3. `你给我一个最小步骤框架，不要一下讲太多。`

### 预期观察

- `Chat`
  - 回答应该更像步骤框架
  - 不应该只重复定义

---

## 组 9：transfer failure 测试

这组专门看“会一道题，不会迁移”。

### 对话

1. `刚才那个例子我看懂了。`
2. `但是如果数字换了，或者题目换个问法，我又不会了。`
3. `你能给我一个相似但不一样的小题让我试试吗？`

### 预期观察

- `Chat`
  - 回答应该给一个轻微变体，而不是重新讲原题
- `Skills`
  - 如果数据足够，后面可能出现 `transfer_failure` 方向的 skill 证据

---

## 组 10：跨主题记忆污染测试

这组专门确认 retrieval 不会把无关主题强行带进来。

建议在已经做过很多条件概率对话之后，新开一个 session 测。

### 对话

1. `我想复习导数的几何意义。`
2. `为什么导数可以理解成函数在某一点的局部变化率？`

### 预期观察

- `Context Rail`
  - 不应该莫名塞很多条件概率 / 贝叶斯相关 concepts
- `Chat`
  - 回答应该聚焦导数几何意义

---

## 推荐测试顺序

如果你想最高效地做一轮完整真实测评，我建议这样跑：

1. 先做 `LLM / Embedding / Reranker diagnostics`
2. 跑 `组 1`
3. 接着跑 `组 2`
4. 跑 `组 3 / 4 / 5`
5. 跑 `组 6`
6. 最后跑 `组 10`

这样你能依次观察：

- 从零建图
- 检索利用记忆
- skill 是否影响 tutor 讲法
- boundary 是否正确
- retrieval 是否污染跨主题回答

---

## 建议你记录的内容

如果你后面要和我一起复盘，建议每组至少记录：

- 你发的用户消息
- Tutor 的回答
- `Context Rail` 截图
- `Memory` 页截图
- `Knowledge / Skills` 页截图
- diagnostics 截图（如果有报错）

这样我能非常快地判断问题是在：

- runtime 配置
- LLM / Embedding / Reranker 契约
- retrieval 排序
- prompt 行为
- graph 构造
- 还是 UI 展示
