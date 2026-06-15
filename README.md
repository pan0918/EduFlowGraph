# EduFlowGraph Tutor

EduFlowGraph Tutor is a runnable AI4Education demo inspired by DeepTutor-style workspaces. It implements the memory design in `EduFlowGraph_Lite_Memory_Design.md`:

- `DataFlow`: append-only JSONL event stream for full tutoring trajectories.
- `Memory Graph`: `Concept <- Episode -> Skill`.
- `Buffer`: recent interaction events trigger episode extraction.
- `Retriever`: retrieves learner state, relevant episodes, and teaching skills before the tutor answers.
- `Skill Workbench`: initialized teaching skills are updated by episode outcomes.

## Quick Start

```bash
cd /Users/frud_/Desktop/AITutor
.venv/bin/python scripts/start_web.py
```

The launcher now starts both:

- FastAPI backend on `127.0.0.1:8000` (or next free port nearby)
- Next + Tailwind frontend on `127.0.0.1:3000` (or next free port nearby)

To reuse the existing DeepTutor frontend dependency tree without a new install, make `web/node_modules` point at `/Users/frud_/Desktop/DeepTutor/web/node_modules`.

## Model Configuration

The app runs in `mock` mode without keys. To use a real model, set these in the sidebar or environment:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="gpt-4o-mini"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-3-small"
```

Any OpenAI-compatible chat and embedding endpoint can be used.

## Frontend

`web/` is now a small Next.js workspace styled to align with DeepTutor:

- left workspace sidebar
- central React/Tailwind work surfaces
- right personalized context rail
- separate routes for `Chat`, `Knowledge`, `Memory`, `Skills`, and `Settings`

The frontend calls the FastAPI backend through `NEXT_PUBLIC_API_BASE`.

## Workspaces

- `Chat`: tutor chat plus retrieved personalized context.
- `Memory`: graph visualization, raw DataFlow, nodes, and edges.
- `Knowledge`: concept mastery, misconceptions, and recommended actions.
- `Skills`: reusable teaching skills and quality statistics.
- `Settings`: endpoint and storage notes.

## Tests

```bash
.venv/bin/python -m unittest tests/test_memory_pipeline.py
.venv/bin/python scripts/smoke_run.py
```
