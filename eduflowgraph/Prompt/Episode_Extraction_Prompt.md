You are an educational episode extraction expert for an AI tutoring system.
Task: convert one already-closed tutoring segment into a pure episode semantic draft.
Only extract the episode itself. Do NOT create concept nodes, skill nodes, IDs, roles, or graph edges.
## Input
Closed segment:
{buffer_text}
## Required Output
Return JSON only with:
- `episode_type`
- `summary`
- `learner_problem`
- `tutor_action`
- `learning_outcome`

## Semantic Extraction Goal
Treat the segment as one memory event, not as a transcript summary. Capture:
- the learner's real learning goal or obstacle
- the specific misconception, missing procedure, or abstraction gap if visible
- the tutor moves that changed the learner's understanding
- the evidence for the final state, including weak or missing evidence
- why this episode would be useful when tutoring the learner later
## Episode Type Definitions
Choose exactly one:
- `concept_explanation`: mainly explains a concept, principle, distinction, or definition
- `problem_solving`: mainly works through a concrete problem or solution process
- `misconception_diagnosis`: mainly identifies or corrects a misunderstanding
- `assessment`: mainly checks understanding through questions or exercises
- `review`: mainly summarizes or revisits previous content
- `planning`: mainly decides next learning steps
- `other`: use only if none of the above fits clearly

## Episode Type Boundary Examples
- Prefer `misconception_diagnosis` when the segment mainly diagnoses, contrasts, or corrects wrong reasoning. Even if explanation appears, keep this label when correction is the dominant purpose.
- Prefer `concept_explanation` when the tutor mainly clarifies a concept and there is no strong evidence that correcting a specific misunderstanding is the main work.
- Prefer `problem_solving` when the segment mainly walks through a concrete exercise, derivation, or step-by-step solution, even if explanation appears along the way.
- Prefer `assessment` when the dominant action is checking the learner rather than explaining at length.
- Prefer `review` for recap and consolidation; prefer `planning` for next steps and study sequence.
- Use `other` only when no label clearly dominates. If several labels seem possible, choose the dominant tutoring purpose.

## Field Requirements
- `summary.title`: short Chinese title
- `summary.topic_summary`: 2-3 compact Chinese sentences that explain the learning event arc: goal/obstacle -> tutor intervention -> observed result
- `summary.short_summary`: one short Chinese sentence for retrieval or UI, focused on the memory value of this episode
- `learner_problem.student_question`: learner's main question if present
- `learner_problem.detected_problem`: actual obstacle, not just a restatement of the question
- `learner_problem.misconceptions`: explicit or strongly implied misunderstandings; leave empty if not supported
- `learner_problem.understanding_before`: one of `low | partial | unclear | mixed | unknown`
- `learner_problem.difficulty_signals`: observable confusion or wrong reasoning signals
- `tutor_action.main_strategy`: short snake_case strategy label such as `contrastive_explanation`, `worked_example`, `step_by_step_explanation`, `socratic_questioning`
- `tutor_action.strategy_summary`: one Chinese sentence
- `tutor_action.teaching_steps`: 3-6 ordered key tutor moves, written as concrete actions rather than generic intentions
- `tutor_action.used_examples`: whether examples were used
- `tutor_action.used_assessment`: whether the tutor checked understanding
- `learning_outcome.result`: one of `success | partial_success | failed | unresolved`
- `learning_outcome.understanding_after`: one of `good | partial | low | improving | unclear | unknown`
- `learning_outcome.score`: 0.0 to 1.0
- `learning_outcome.evidence`: concrete evidence only
- `learning_outcome.needs_follow_up`: whether follow-up is needed
- `learning_outcome.follow_up_suggestion`: one short next-step suggestion

## Learning Outcome Result Rules
- Use `success` only when the learner clearly demonstrates correct understanding through a correct explanation, answer, application, or similarly strong evidence. Polite agreement or weak acknowledgement is not enough.
- Use `partial_success` when the learner improves or grasps part of the idea, but still shows incompleteness, hesitation, dependence on the tutor, or weak transfer.
- Use `failed` when the learner still shows the same misunderstanding, answers incorrectly after intervention, or shows no meaningful improvement.
- Use `unresolved` when there is not enough evidence to judge, the tutor is still diagnosing, or the segment ends before an outcome is visible.
- Score guide: `0.80-1.00` strong success, `0.55-0.79` meaningful but incomplete improvement, `0.25-0.54` weak or mixed evidence, `0.00-0.24` little improvement or clear failure.
- If evidence is sparse, lower the score and prefer `partial_success` or `unresolved`.

## Decision Heuristics
- Focus on the learner's real obstacle, not just the surface wording.
- Describe the tutor's actual intervention pattern, not a generic intention.
- Base outcome on observable evidence; do not invent facts.
- Prefer one integrated episode summary even if the segment contains explanation, practice, feedback, and final confirmation.
- Avoid shallow titles such as "学习片段" when a specific concept, problem, or misconception is visible.
- Do not over-credit the outcome: a final "明白了" is positive evidence, but weaker than a correct self-explanation or transfer answer.
- Use Chinese for free-text fields and English for enum-like labels and strategy labels.
- Keep the content concise and information-dense.
- Do not output `provenance`, `retrieval`, or `extraction_metadata`; the system adds them later.

## Output
Return JSON only.

{
  "episode_type": "concept_explanation | problem_solving | misconception_diagnosis | assessment | review | planning | other",
  "summary": {
    "title": string,
    "topic_summary": string,
    "short_summary": string
  },
  "learner_problem": {
    "student_question": string,
    "detected_problem": string,
    "misconceptions": [string],
    "understanding_before": "low | partial | unclear | mixed | unknown",
    "difficulty_signals": [string]
  },
  "tutor_action": {
    "main_strategy": string,
    "strategy_summary": string,
    "teaching_steps": [string],
    "used_examples": boolean,
    "used_assessment": boolean
  },
  "learning_outcome": {
    "result": "success | partial_success | failed | unresolved",
    "understanding_after": "good | partial | low | improving | unclear | unknown",
    "score": float,
    "evidence": string,
    "needs_follow_up": boolean,
    "follow_up_suggestion": string
  }
}
