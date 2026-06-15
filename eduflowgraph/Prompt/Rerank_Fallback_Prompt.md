Return JSON only.

You are re-ranking retrieval candidates for a tutoring system.

Candidate kind: {kind}

Query: {query}

Rules:
- Re-rank by pedagogical usefulness for the current learner request, not just lexical overlap.
- Prefer candidates whose `intent`, `matched_difficulty`, and `match_reasons` best fit the current query.
- For `skill` candidates, prefer higher-confidence and better-validated teaching strategies when relevance is close.
- For `episode` candidates, prefer candidates that better support the current teaching intent and avoid repeating weak historical paths.

Output schema:
{{ "ordered_ids": [string] }}

Candidates:
{candidates_json}
