import test from "node:test";
import assert from "node:assert/strict";

import {
  formatSkillDisplay,
  skillDifficultyLabel,
  skillTeachingActionLabel,
} from "./skill-display.ts";

test("formatSkillDisplay localizes existing English distilled skills", () => {
  const skill = {
    node_id: "skill_direction_confusion_contrastive_explanation",
    skill_id: "skill_direction_confusion_contrastive_explanation",
    node_type: "skill",
    name: "Clarify direction confusion through contrastive explanation",
    status: "candidate",
    trigger:
      "Use when the learner shows directionally related concepts, conditions, or formulas around Conditional Probability, Base Rate.",
    concept_scope: ["Conditional Probability", "Base Rate"],
    difficulty_pattern: "direction_confusion",
    teaching_actions: ["contrastive_explanation", "student_self_explanation"],
    procedure: [
      "Name the two easily confused objects.",
      "Contrast them under the same scenario.",
    ],
    success_criteria: [
      "The learner can explain the directional difference without reversing the two meanings.",
    ],
    quality: {
      support_episode_count: 2,
      validation_success_count: 0,
      validation_fail_count: 0,
      confidence: 0.84,
    },
  };

  const display = formatSkillDisplay(skill);

  assert.equal(display.name, "用对比解释澄清方向混淆");
  assert.equal(
    display.trigger,
    "当学习者混淆有方向性的概念、条件或公式时使用。",
  );
  assert.deepEqual(display.teachingActions, ["对比解释", "学生自我解释"]);
  assert.deepEqual(display.procedure, [
    "先点名两个容易混淆的对象。",
    "放到同一个场景里对比它们。",
  ]);
  assert.deepEqual(display.successCriteria, [
    "学习者能说明两个对象的方向差异，并且不再反着解释。",
  ]);
});

test("formatSkillDisplay keeps public skill text compact and generic", () => {
  const skill = {
    node_id: "skill_direction_confusion_contrastive_explanation",
    skill_id: "skill_direction_confusion_contrastive_explanation",
    node_type: "skill",
    name: "Clarify direction confusion through contrastive explanation",
    status: "candidate",
    trigger:
      "Use this skill when learners show direction confusion around Bayes theorem, Conditional probability. Teaching actions: contrastive_explanation, worked_example.",
    concept_scope: ["Bayes theorem", "Conditional probability"],
    difficulty_pattern: "direction_confusion",
    teaching_actions: [
      "contrastive_explanation",
      "student_self_explanation",
      "worked_example",
      "step_by_step_explanation",
    ],
    procedure: [
      "Name the two easily confused objects.",
      "Explain each object in natural language.",
      "Contrast them under the same scenario.",
      "Ask the learner to restate the idea.",
      "Probe for missing links.",
      "Confirm transfer to a fresh example.",
    ],
    success_criteria: [
      "The learner can explain the directional difference without reversing the two meanings.",
      "The learner can correctly distinguish the two targets in a fresh scenario.",
      "The learner can clearly state the difference between the two targets.",
    ],
  };

  const display = formatSkillDisplay(skill);

  assert.equal(
    display.trigger,
    "当学习者出现方向混淆时使用。教学动作：对比解释、完整例题示范。",
  );
  assert.doesNotMatch(display.trigger, /Bayes|Conditional|贝叶斯|条件概率/);
  assert.equal(display.procedure.length, 3);
  assert.equal(display.successCriteria.length, 2);
});

test("skill enum labels are Chinese", () => {
  assert.equal(skillDifficultyLabel("symbol_grounding"), "符号含义未落地");
  assert.equal(skillTeachingActionLabel("minimal_numeric_example"), "最小数字例子");
});
