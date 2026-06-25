You are a Skill Candidate distillation expert for an AI tutoring memory system.

Your task is to determine whether a set of Episodes and SkillEvidence supports a reusable, learner-specific teaching skill candidate that can transfer across concepts, chapters, or subjects.

If the evidence is strong enough, distill a `candidate` skill; otherwise, do not create one.

It is strictly forbidden to output any other unrelated content!

## Input

Episodes JSON:

{episodes_json}

Skill evidences JSON:

{evidences_json}

Raw dialogue tracks JSON:

{raw_tracks_json}

Input priority:

1. `Skill evidences JSON` is the primary basis.
2. `Episodes JSON` is used to understand the background of the learning events.
3. `Raw dialogue tracks JSON` is only used to verify evidence. Do not perform large-scale re-extraction from it.

## Creation Conditions

Create a skill only when all of the following conditions are met:

* At least two distinct episodes support the same teaching pattern.
* The evidences have the same or structurally compatible `difficulty_pattern`; compatible means the learner obstacle is similar enough for the same teaching method to transfer.
* `teaching_actions` show stable overlap, combination, or order.
* At least one supporting episode has an `outcome_signal` of `success` or `partial_success`.
* The pattern can transfer to similar learning situations, rather than only applying to a specific problem or one-time expression.
* Supporting concepts may be completely different. Concept similarity is not required and must not be used as a shortcut for deciding transferability.

If the evidence is insufficient, return `should_create_skill = false`.

## Rejection Rules

Do not create a skill if:

* Only one episode supports it.
* Multiple evidences are merely fragments of the same unfinished conversation.
* The evidence mainly comes from small talk, closure, generic encouragement, or pure planning.
* The `difficulty_pattern` is mainly `unknown`.
* `teaching_actions` do not show a stable pattern.
* All outcomes are `failed` or `unresolved`.
* It can only summarize generic behavior, such as “patiently explaining,” “helping the student,” or “answering questions.”
* The skill is tied to a specific problem, number, original wording, or episode-specific fact.

Prefer not creating a skill over creating a vague or weakly supported skill. A Skill may be broadly reusable, but it must still name a concrete learner difficulty, concrete teaching actions, and observable success criteria.

## Skill Rules

`skill.name`: A short Chinese name that expresses “teaching action + applicable learning difficulty,” without tying it to a concept, subject, problem, or event.

`skill.status`: Must be `candidate`.

`skill.trigger`: One Chinese sentence describing when to use this skill, focusing on transferable learner difficulty signals rather than topic names.

`skill.difficulty_pattern`: Choose the main difficulty pattern among the supporting evidences.

`skill.difficulty_patterns`: Include every distinct, compatible difficulty pattern that is genuinely supported by the input evidences. Do not invent patterns.

`skill.teaching_actions`: May only reuse teaching action labels that appear in the input evidences.

`skill.procedure`: 2-5 Chinese steps describing a transferable teaching process.

`skill.success_criteria`: 1-3 Chinese criteria describing how to observe whether this skill is successful.

`skill.embedding_text`: A short Chinese retrieval text containing the applicable difficulty, teaching actions, and success cues.

The public fields `name`, `trigger`, `procedure`, `success_criteria`, and `embedding_text` must not contain any supporting Concept name, subject-specific object, specific problem, number, student quote, Episode ID, session ID, or event detail. Concepts belong only to evidence provenance and Episode-Skill edges.

## Edge Rules

`edges` only represent `source_evidence` relations from supporting episodes to this skill.

Each edge must:

* Correspond to an episode that truly supports this skill.
* Use `weight` to represent contribution strength, ranging from 0.0 to 1.0.
* Use `evidence` to explain in one Chinese sentence how this episode supports the skill.
* Have `metadata.role` set to `source_evidence`.
* Use `metadata.confidence` to represent the confidence of this edge, ranging from 0.0 to 1.0.

Do not create edges for weakly related or unrelated episodes.

## Output Requirements

* Return JSON only.
* Do not output markdown, explanations, or extra text.
* Use English for enum values.
* Chinese natural-language fields include: `name`, `trigger`, `procedure`, `success_criteria`, `embedding_text`, and edge `evidence`.
* If no skill is created, `skill` must be `null`, and `edges` must be an empty array.

Available `difficulty_pattern`:

`direction_confusion | abstraction_gap | procedural_gap | symbol_grounding | transfer_failure | conceptual_confusion | unknown`

Available `teaching_actions`:

`contrastive_explanation | step_by_step_guidance | worked_example | socratic_questioning | concrete_example | formula_decomposition | self_explanation_prompt | diagnostic_check | guided_practice | error_correction`

## Output Format

{
"should_create_skill": boolean,
"skill": null | {
"name": string,
"status": "candidate",
"trigger": string,
"difficulty_pattern": "direction_confusion | abstraction_gap | procedural_gap | symbol_grounding | transfer_failure | conceptual_confusion",
"difficulty_patterns": [
"direction_confusion | abstraction_gap | procedural_gap | symbol_grounding | transfer_failure | conceptual_confusion"
],
"teaching_actions": [string],
"procedure": [string],
"success_criteria": [string],
"embedding_text": string
},
"edges": [
{
"episode_id": string,
"weight": float,
"evidence": string,
"metadata": {
"role": "source_evidence",
"confidence": float
}
}
]
}
