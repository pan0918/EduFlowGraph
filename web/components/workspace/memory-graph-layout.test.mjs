import test from "node:test";
import assert from "node:assert/strict";

import { buildMemoryGraphModel } from "./memory-graph-layout.ts";

test("buildMemoryGraphModel builds three concentric layers with adjacency", () => {
  const snapshot = {
    events: [],
    concepts: [
      {
        concept_id: "concept_probability",
        node_id: "concept_probability",
        node_type: "concept",
        name: "Conditional Probability",
        aliases: ["条件概率"],
      },
    ],
    episodes: [
      {
        episode_id: "episode_probability",
        node_id: "episode_probability",
        node_type: "episode",
        episode_type: "concept_explanation",
        summary: {
          title: "条件概率方向澄清",
          topic_summary: "帮助学生区分 P(A|B) 与 P(B|A)",
          short_summary: "用对比解释条件方向差异。",
        },
        learner_problem: {
          student_question: "为什么 P(A|B) 不等于 P(B|A)？",
          detected_problem: "条件方向混淆",
          misconceptions: ["把检测准确率当作后验概率"],
          understanding_before: "low",
          difficulty_signals: ["direction_confusion"],
        },
      },
    ],
    skills: [
      {
        skill_id: "skill_direction_confusion",
        node_id: "skill_direction_confusion",
        node_type: "skill",
        name: "方向对比解释",
        status: "active",
        trigger: "学生分不清两个条件概率的方向",
        difficulty_pattern: "direction_confusion",
        quality: {
          confidence: 0.92,
        },
      },
    ],
    edges: [
      {
        edge_id: "edge_episode_concept",
        edge_type: "episode_concept",
        source: "episode_probability",
        target: "concept_probability",
        weight: 0.91,
        evidence: "围绕条件概率方向差异展开。",
      },
      {
        edge_id: "edge_episode_skill",
        edge_type: "episode_skill",
        source: "episode_probability",
        target: "skill_direction_confusion",
        weight: 0.84,
        evidence: "对比解释帮助学生澄清。",
        metadata: {
          role: "validation",
          confidence: 0.88,
        },
      },
    ],
  };

  const model = buildMemoryGraphModel(snapshot);
  const concept = model.nodes.find((node) => node.id === "concept_probability");
  const episode = model.nodes.find((node) => node.id === "episode_probability");
  const skill = model.nodes.find((node) => node.id === "skill_direction_confusion");

  assert.equal(model.summary.totalNodes, 3);
  assert.equal(model.summary.totalEdges, 2);
  assert.deepEqual(
    model.layers.map((layer) => ({
      kind: layer.kind,
      count: layer.count,
    })),
    [
      { kind: "concept", count: 1 },
      { kind: "episode", count: 1 },
      { kind: "skill", count: 1 },
    ],
  );
  assert.equal(concept?.layerIndex, 1);
  assert.equal(episode?.layerIndex, 2);
  assert.equal(skill?.layerIndex, 3);
  assert.equal(episode?.degree, 2);
  assert.deepEqual(episode?.connectedNodeIds.sort(), [
    "concept_probability",
    "skill_direction_confusion",
  ]);
});

test("buildMemoryGraphModel keeps empty snapshots renderable", () => {
  const model = buildMemoryGraphModel({
    events: [],
    concepts: [],
    episodes: [],
    skills: [],
    edges: [],
  });

  assert.equal(model.nodes.length, 0);
  assert.equal(model.edges.length, 0);
  assert.equal(model.summary.totalNodes, 0);
  assert.equal(model.summary.totalEdges, 0);
  assert.deepEqual(
    model.layers.map((layer) => layer.count),
    [0, 0, 0],
  );
});

test("buildMemoryGraphModel aggregates duplicate episode memories", () => {
  const duplicateEpisode = (id, result) => ({
    episode_id: id,
    node_id: id,
    node_type: "episode",
    episode_type: "assessment",
    summary: {
      title: "把检测准确率当作后验概率",
      topic_summary: "围绕检测准确率和后验概率的混淆展开。",
      short_summary: `当前结果为 ${result}。`,
    },
    learner_problem: {
      student_question: "为什么不能直接把检测准确率当作患病概率？",
      detected_problem: "把检测准确率当作后验概率",
      misconceptions: ["把检测准确率当作后验概率"],
      understanding_before: "low",
      difficulty_signals: ["direction_confusion"],
    },
    tutor_action: {
      main_strategy: "contrastive_explanation",
    },
    learning_outcome: {
      result,
      score: result === "success" ? 0.82 : 0.28,
    },
  });

  const model = buildMemoryGraphModel({
    events: [],
    concepts: [
      {
        concept_id: "concept_bayes",
        node_id: "concept_bayes",
        node_type: "concept",
        name: "Bayes theorem",
        aliases: ["贝叶斯定理"],
      },
    ],
    episodes: [
      duplicateEpisode("episode_a", "failed"),
      duplicateEpisode("episode_b", "success"),
    ],
    skills: [
      {
        skill_id: "skill_direction",
        node_id: "skill_direction",
        node_type: "skill",
        name: "方向对比解释",
        status: "active",
        trigger: "学生分不清两个条件概率的方向",
        difficulty_pattern: "direction_confusion",
      },
    ],
    edges: [
      {
        edge_id: "edge_a_concept",
        edge_type: "episode_concept",
        source: "episode_a",
        target: "concept_bayes",
        weight: 0.91,
        evidence: "第一次解释。",
      },
      {
        edge_id: "edge_b_concept",
        edge_type: "episode_concept",
        source: "episode_b",
        target: "concept_bayes",
        weight: 0.93,
        evidence: "第二次解释。",
      },
      {
        edge_id: "edge_b_skill",
        edge_type: "episode_skill",
        source: "episode_b",
        target: "skill_direction",
        weight: 0.84,
        evidence: "学生理解。",
      },
    ],
  });

  const episodes = model.nodes.filter((node) => node.kind === "episode");

  assert.equal(episodes.length, 1);
  assert.equal(model.summary.episodeCount, 1);
  assert.equal(episodes[0].mergedCount, 2);
  assert.deepEqual(episodes[0].sourceNodeIds.sort(), ["episode_a", "episode_b"]);
  assert.deepEqual(episodes[0].connectedNodeIds.sort(), [
    "concept_bayes",
    "skill_direction",
  ]);
  assert.equal(
    model.edges.filter((edge) => edge.edgeType === "episode_concept").length,
    1,
  );
});
