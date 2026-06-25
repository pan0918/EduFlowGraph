import type { SkillNode } from "@/lib/types";

const DIFFICULTY_LABELS: Record<string, string> = {
  direction_confusion: "方向混淆",
  abstraction_gap: "抽象概念未落地",
  procedural_gap: "步骤缺口",
  symbol_grounding: "符号含义未落地",
  transfer_failure: "迁移失败",
  conceptual_confusion: "概念理解混淆",
  unknown: "未识别模式",
};

const ACTION_LABELS: Record<string, string> = {
  contrastive_explanation: "对比解释",
  step_by_step_guidance: "分步骤引导",
  worked_example: "完整例题示范",
  socratic_questioning: "苏格拉底式追问",
  concrete_example: "具体例子",
  formula_decomposition: "公式拆解",
  self_explanation_prompt: "学生自我解释",
  student_self_explanation: "学生自我解释",
  diagnostic_check: "诊断检查",
  guided_practice: "引导练习",
  error_correction: "错误纠正",
  minimal_numeric_example: "最小数字例子",
  step_by_step_explanation: "分步骤引导",
};

const STATUS_LABELS: Record<string, string> = {
  seed: "种子技能",
  candidate: "候选技能",
  active: "已验证技能",
  retired: "已停用",
};

const TEXT_TRANSLATIONS: Record<string, string> = {
  "Clarify direction confusion through contrastive explanation": "用对比解释澄清方向混淆",
  "Ground formula meaning through decomposition and learner restatement": "通过公式拆解和复述落地符号含义",
  "Support transfer to similar cases through worked examples": "用例题示范支持迁移到相似题",
  "Build a workable step sequence through guided decomposition": "通过引导拆解建立可执行步骤",
  "Ground abstract ideas through concrete examples": "用具体例子落地抽象概念",
  "Name the two easily confused objects.": "先点名两个容易混淆的对象。",
  "Explain each object in natural language.": "用自然语言分别解释两个对象。",
  "Contrast them under the same scenario.": "放到同一个场景里对比它们。",
  "Decompose the target into smaller steps.": "把目标拆成更小的步骤。",
  "Explain one step at a time.": "一次只解释一个步骤。",
  "Check understanding after each step.": "每一步后都检查理解。",
  "Present a small worked example.": "先给一个小型完整例题。",
  "Highlight key decision points.": "标出关键判断点。",
  "Ask the learner to transfer the pattern.": "请学习者把模式迁移到相似题。",
  "Ask a low-barrier diagnostic question.": "先问一个低门槛诊断问题。",
  "Follow up based on the learner response.": "根据学习者回答继续追问。",
  "Ask the learner to summarize the rule.": "请学习者总结规则。",
  "Set up a small-count scenario.": "设置一个数量很小的场景。",
  "List the relevant quantities.": "列出相关数量。",
  "Map the numbers back to the formula.": "把数字映射回公式。",
  "Break the formula into smaller terms.": "把公式拆成更小的项。",
  "Explain what each term means.": "解释每一项的含义。",
  "Reconnect the terms to the full expression.": "再把各项连回完整表达式。",
  "Ask the learner to restate the idea.": "请学习者用自己的话复述。",
  "Probe for missing links.": "追问缺失的理解环节。",
  "Confirm transfer to a fresh example.": "用一个新例子确认能否迁移。",
  "Ask a focused check question.": "问一个聚焦的小检查问题。",
  "Inspect the learner answer.": "检查学习者的回答。",
  "Decide whether more support is needed.": "判断是否还需要继续支架。",
  "The learner can explain the directional difference without reversing the two meanings.": "学习者能说明两个对象的方向差异，并且不再反着解释。",
  "The learner can correctly distinguish the two targets in a fresh scenario.": "学习者能在新场景中正确区分两个目标。",
  "The learner can explain what each formula term means.": "学习者能解释公式中每一项的含义。",
  "The learner can connect the formula back to the underlying idea in plain language.": "学习者能用日常语言把公式连回背后的思想。",
  "The learner can transfer the method to a similar case without copying the original example.": "学习者能把方法迁移到相似题，而不是照抄原例。",
  "The learner can explain which parts of the example stay the same and which parts change.": "学习者能说明相似例子中哪些不变、哪些改变。",
  "The learner can state the key steps in order without losing the sequence.": "学习者能按顺序说出关键步骤。",
  "The learner can start a similar problem without waiting for the tutor to break it apart.": "学习者能自己开始拆解相似问题。",
  "The learner can map the concrete example back to the abstract concept.": "学习者能把具体例子映射回抽象概念。",
  "The learner can restate the abstract idea after seeing the example.": "学习者能在看过例子后复述抽象思想。",
  "The learner can clearly state the difference between the two targets.": "学习者能清楚说出两个目标的差异。",
  "The learner can explain the key steps in order.": "学习者能按顺序解释关键步骤。",
  "The learner can transfer the example pattern to a similar case.": "学习者能把例题模式迁移到相似情境。",
  "The learner can articulate the rule without the tutor saying it first.": "学习者能先于导师自己说出规则。",
  "The learner can map the numeric example back to the abstract concept.": "学习者能把数字例子映射回抽象概念。",
  "The learner can explain why each formula term appears.": "学习者能解释每个公式项为什么出现。",
  "The learner can restate the core idea in their own words.": "学习者能用自己的话复述核心思想。",
  "The learner can answer a short follow-up check correctly.": "学习者能正确回答一个短检查题。",
};

const TRIGGER_PATTERNS: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [
    /^Use when the learner shows directionally related concepts, conditions, or formulas around (.+)\.$/,
    () => "当学习者混淆有方向性的概念、条件或公式时使用。",
  ],
  [
    /^Use this skill when learners show direction confusion around (.+)\. Teaching actions: (.+)\.$/,
    (match) => `当学习者出现方向混淆时使用。教学动作：${formatActionList(match[2])}。`,
  ],
  [
    /^Use this skill when the learner confuses directionally related concepts, conditions, or formulas\.$/,
    () => "当学习者混淆有方向性的概念、条件或公式时使用。",
  ],
  [
    /^Use this skill when the learner confuses conditional probability directions\.$/,
    () => "当学习者混淆条件方向时使用。",
  ],
  [
    /^Use when the learner shows an abstract idea that has not grounded yet around (.+)\.$/,
    () => "当学习者还没有把抽象概念落地时使用。",
  ],
  [
    /^Use when the learner shows a missing workable step sequence around (.+)\.$/,
    () => "当学习者缺少可执行步骤时使用。",
  ],
  [
    /^Use when the learner shows symbols or formulas that are not grounded in meaning around (.+)\.$/,
    () => "当学习者无法把符号或公式落到含义时使用。",
  ],
  [
    /^Use when the learner shows difficulty transferring from one example to a nearby case around (.+)\.$/,
    () => "当学习者难以迁移到相似题时使用。",
  ],
];

export interface SkillDisplay {
  name: string;
  trigger: string;
  status: string;
  difficulty: string;
  teachingActions: string[];
  procedure: string[];
  successCriteria: string[];
}

function translateText(text: string): string {
  const trimmed = String(text || "").trim();
  if (!trimmed) return "";
  const exact = TEXT_TRANSLATIONS[trimmed];
  if (exact) return exact;
  for (const [pattern, render] of TRIGGER_PATTERNS) {
    const match = trimmed.match(pattern);
    if (match) return render(match);
  }
  return trimmed;
}

function formatActionList(text: string): string {
  return text
    .split(/\s*,\s*/)
    .map((item) => skillTeachingActionLabel(item.trim()))
    .filter(Boolean)
    .join("、");
}

export function skillDifficultyLabel(value?: string): string {
  return DIFFICULTY_LABELS[String(value || "unknown")] || String(value || "未识别模式");
}

export function skillTeachingActionLabel(value?: string): string {
  return ACTION_LABELS[String(value || "")] || String(value || "");
}

export function skillStatusLabel(value?: string): string {
  return STATUS_LABELS[String(value || "candidate")] || String(value || "candidate");
}

export function formatSkillDisplay(skill: SkillNode): SkillDisplay {
  const difficultyPatterns = Array.from(
    new Set(
      (skill.difficulty_patterns?.length
        ? skill.difficulty_patterns
        : [skill.difficulty_pattern]
      ).filter(Boolean),
    ),
  );
  return {
    name: translateText(skill.name),
    trigger: translateText(skill.trigger || ""),
    status: skillStatusLabel(skill.status),
    difficulty: difficultyPatterns.map(skillDifficultyLabel).join("、"),
    teachingActions: (skill.teaching_actions || []).map(skillTeachingActionLabel).slice(0, 3),
    procedure: (skill.procedure || []).map(translateText).slice(0, 3),
    successCriteria: (skill.success_criteria || []).map(translateText).slice(0, 2),
  };
}
