<div align="center">

# EduMindFlow

**Memory-Augmented AI Tutoring System**

EduMindFlow is a local-first AI tutoring prototype that combines conversational tutoring, structured memory extraction, learner profiling, and retrieval-augmented teaching adaptation.

[Quick Start](#quick-start) · [Architecture](#architecture) · [Configuration](#configuration) · [API](#api) · [Project Structure](#project-structure)

</div>

---

## Overview

EduMindFlow turns tutoring conversations into reusable learning memory. During a chat session, the backend records turns, detects learning episodes, extracts concepts, distills teaching skills, and updates a learner profile. Later responses can retrieve this memory to adapt explanations to the learner’s history, misconceptions, mastery level, and preferred teaching style.

The project is designed to run locally with a simple stack:

- FastAPI backend for tutoring, memory extraction, retrieval, and storage.
- Next.js frontend for chat, knowledge graph, memory, skills, profile, and settings views.
- SQLite as the default embedded storage backend.
- OpenAI-compatible model interface, with mock mode available for local development without API keys.

## Core Features

| Area | Capability |
|---|---|
| Tutoring chat | REST and SSE streaming chat endpoints with memory-aware context injection |
| Learning memory | Episode, concept, skill, and learner-profile extraction from conversation turns |
| Retrieval | Keyword, embedding, graph, profile, and reranking signals for personalized context selection |
| Learner profile | Cognitive portrait, situational context, and teaching-preference summaries |
| Storage | SQLite database with WAL mode; legacy JSON storage remains available for migration/rollback |
| Frontend workspace | Chat, knowledge, memory graph, skills, profile, and settings panels |

## Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                      Next.js Frontend                      │
│  Chat · Knowledge · Memory · Skills · Profile · Settings   │
└──────────────────────────────┬─────────────────────────────┘
                               │ REST / SSE
┌──────────────────────────────▼─────────────────────────────┐
│                       FastAPI Backend                       │
│                                                            │
│  TutorPipeline                                             │
│    ├─ MemoryRetriever                                      │
│    ├─ SkillPersonalizedReranker                            │
│    ├─ BufferManager / BoundaryDetector                     │
│    ├─ EpisodeExtractor / ConceptExtractor                  │
│    ├─ SkillEvidenceExtractor / SkillDistiller              │
│    └─ ProfileConsolidator                                  │
│                                                            │
│  LLMClient ─ OpenAI-compatible models or mock runtime       │
│  SQLiteStorage ─ sessions, turns, graph, profile, vectors   │
└────────────────────────────────────────────────────────────┘
```

Typical conversation flow:

```text
User message
  → retrieve learner/profile/memory context
  → generate tutor response
  → persist conversation turn
  → detect episode boundary
  → extract concepts, episode metadata, and skill evidence
  → update graph memory and learner profile
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Optional: an OpenAI-compatible API key for real model calls

### Install

```bash
git clone git@github.com:pan0918/EduFlowGraph.git
cd EduFlowGraph

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web
npm install
cd ..
```

### Run

```bash
.venv/bin/python scripts/start_web.py
```

Default local services:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`

By default, the app can run in mock mode. This is useful for checking the UI and data flow without configuring external model credentials.

## Configuration

Create a local environment file from the template:

```bash
cp .env.example .env
```

Common variables:

| Variable | Default | Purpose |
|---|---:|---|
| `EDUFLOW_PROVIDER` | `openai-compatible` | Runtime provider: `mock` or `openai-compatible` |
| `OPENAI_API_KEY` | empty | API key for the selected OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `EDUFLOW_CHAT_MODEL` | `gpt-4o-mini` | Chat model name |
| `EDUFLOW_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `EDUFLOW_STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite` or `json` |
| `EDUFLOW_DATABASE_PATH` | `data/eduflowgraph.db` | SQLite database path |
| `EDUFLOW_DATA_DIR` | `data` | Runtime data directory |

Example real-model setup:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="gpt-4o-mini"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-3-small"
```

## API

The backend serves these endpoints from `http://127.0.0.1:8000`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Runtime and storage health |
| `GET` | `/api/dashboard` | Concepts, episodes, skills, graph edges, and profile snapshot |
| `POST` | `/api/chat` | Non-streaming tutor response |
| `POST` | `/api/chat/stream` | SSE streaming tutor response |
| `POST` | `/api/extract` | Force extraction from the current turn buffer |
| `POST` | `/api/diagnostics/model-test` | Check model, embedding, and reranker connectivity |
| `POST` | `/api/rebuild-retrieval` | Rebuild retrieval embeddings |
| `POST` | `/api/reset-memory` | Clear conversations, memory graph, and profile |
| `GET` | `/api/sessions` | List conversation sessions |
| `GET` | `/api/sessions/{session_id}/turns` | Read turns for one session |

Streaming chat example:

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain the chain rule in calculus", "session_id": "demo"}'
```

## Project Structure

```text
.
├── EduFlowGraph/                 # Python backend package
│   ├── pipeline.py               # TutorPipeline orchestration
│   ├── web_app.py                # FastAPI app and API routes
│   ├── config.py                 # Runtime configuration
│   ├── llm.py                    # Chat, embedding, and rerank client
│   ├── memory/                   # Episode, concept, skill, and retrieval logic
│   ├── profile/                  # Learner-profile models and consolidation
│   ├── store/                    # SQLite and legacy JSON storage implementations
│   └── Prompt/                   # Prompt templates used by the backend
│
├── web/                          # Next.js frontend
│   ├── app/                      # App Router pages
│   ├── components/               # Workspace UI components and providers
│   └── lib/                      # Frontend types and configuration helpers
│
├── scripts/
│   ├── start_web.py              # Starts backend and frontend together
│   ├── migrate_storage.py        # JSON to SQLite migration utility
│   └── export_storage.py         # SQLite export utility
│
├── docs/                         # Public API, code, and deployment documentation
├── tests/                        # Backend unit tests
├── data/                         # Local runtime data, ignored by Git
├── requirements.txt              # Python dependencies
└── .env.example                  # Environment variable template
```

## Storage

The default storage backend is SQLite at `data/eduflowgraph.db`. Runtime data is ignored by Git.

To use the legacy JSON backend:

```bash
export EDUFLOW_STORAGE_BACKEND=json
```

To migrate existing JSON data into SQLite:

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --dry-run
.venv/bin/python scripts/migrate_storage.py --data-dir data --apply
.venv/bin/python scripts/migrate_storage.py --data-dir data --verify
```

## Development Checks

Useful local checks before committing:

```bash
.venv/bin/python -m unittest discover -s tests
node --test $(rg --files web -g '*.test.mjs')
cd web && npm run build
```

## License

This project is for research and educational use.
