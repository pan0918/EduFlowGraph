<div align="center">

# EduFlowGraph

**Episode-Centric Memory Graph for Personalized AI Tutoring**

A memory-augmented tutoring engine that extracts structured learning episodes from conversation trajectories, connects them to concepts and teaching skills, and builds evolving learner profiles to personalize future responses.

[Architecture](#architecture) · [Quick Start](#quick-start) · [Configuration](#configuration) · [API Reference](#api-reference) · [Project Structure](#project-structure)

</div>

---

## Overview

EduFlowGraph implements a **Concept ← Episode → Skill** memory graph that turns raw tutoring conversations into structured, retrievable educational memory. The system autonomously detects episode boundaries, extracts learning concepts, distills reusable teaching strategies, and maintains a multi-dimensional learner profile — all without requiring a vector database or external orchestration framework.

### Core Capabilities

| Capability | Description |
|---|---|
| **Episode Extraction** | LLM-based boundary detection segments conversations into coherent learning episodes with type, outcome, and strategy metadata |
| **Concept Graph** | Automatic concept identification with fuzzy deduplication, misconception tracking, and mastery estimation |
| **Skill Distillation** | Teaching actions are extracted from episodes, validated, and distilled into reusable skills mapped to difficulty patterns |
| **Learner Profiling** | Three-budget text profiles (cognitive portrait, situational context, teaching preferences) rewritten at different cadences |
| **Multi-Signal Retrieval** | Keyword matching, cosine similarity, graph expansion, outcome relevance, and reranking compose the retrieval pipeline |
| **Dual Storage** | Embedded SQLite with WAL mode and JSON payload columns; legacy JSON/JSONL backend available |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                            │
│  Chat ─ Knowledge ─ Memory Graph ─ Skills ─ Profile ─ Settings     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  REST / SSE
┌──────────────────────────────▼──────────────────────────────────────┐
│                         FastAPI Backend                              │
│                                                                      │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────────┐ │
│  │  TutorPipeline │──▶│ MemoryRetriever │──▶│ SkillPersonalizedReranker │ │
│  └──────┬──────┘   └──────────────┘   └──────────────────────────┘ │
│         │                                                            │
│  ┌──────▼──────────────────────────────────────────────────────┐   │
│  │                    Memory Subsystem                          │   │
│  │  BufferManager ─▶ BoundaryDetector ─▶ EpisodeExtractor      │   │
│  │       │                │                    │                │   │
│  │       ▼                ▼                    ▼                │   │
│  │  ConceptExtractor ─▶ SkillEvidenceExtractor ─▶ SkillDistiller│  │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────┐  │
│  │ ProfileConsolidator│  │  LLMClient (OpenAI-compat) │  │  SQLiteStorage (WAL)  │  │
│  └──────────────┘   └──────────────────┘   └───────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Memory Pipeline

```
 User Message
      │
      ▼
 ┌────────────┐     ┌─────────────┐     ┌──────────────┐
 │ Retrieve    │────▶│ Generate    │────▶│ Persist Turn │
 │ Context     │     │ Response    │     │ + Buffer     │
 └────────────┘     └─────────────┘     └──────┬───────┘
                                               │
                                        ┌──────▼───────┐
                                        │   Boundary    │
                                        │   Detected?   │
                                        └──┬────────┬──┘
                                           │        │
                                          No       Yes
                                           │        │
                                           ▼        ▼
                                        (idle)  ┌────────────┐
                                                │  Extract    │
                                                │  Episode    │
                                                └──────┬─────┘
                                                       │
                                                ┌──────▼─────┐
                                                │  Extract    │
                                                │  Concepts   │
                                                └──────┬─────┘
                                                       │
                                                ┌──────▼─────┐
                                                │  Distill    │
                                                │  Skills     │
                                                └──────┬─────┘
                                                       │
                                                ┌──────▼─────┐
                                                │  Update     │
                                                │  Profile    │
                                                └────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- (Optional) An OpenAI-compatible API key for real model inference

### Installation

```bash
git clone https://github.com/pan0918/EduFlowGraph.git
cd EduFlowGraph

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend dependencies
cd web
npm install
cd ..
```

### Launch

```bash
# Start both backend and frontend
.venv/bin/python scripts/start_web.py
```

This starts:
- **Backend** — FastAPI on `http://127.0.0.1:8000`
- **Frontend** — Next.js on `http://127.0.0.1:3000`

The system runs in **mock mode** by default — no API keys required. LLM calls return deterministic stubs, embeddings use 32-dimensional hash-based vectors.

## Configuration

### Environment Variables

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | API key for LLM and embedding calls |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `EDUFLOW_PROVIDER` | `openai-compatible` | Provider mode: `mock` or `openai-compatible` |
| `EDUFLOW_CHAT_MODEL` | `gpt-4o-mini` | Chat model identifier |
| `EDUFLOW_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model identifier |
| `EDUFLOW_EXTRACTION_TURNS` | `4` | Buffer size (turns) before episode extraction triggers |
| `EDUFLOW_DATA_DIR` | `data` | Runtime data directory |
| `EDUFLOW_STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite` or `json` |
| `EDUFLOW_DATABASE_PATH` | `data/eduflowgraph.db` | SQLite database file path |

### Using a Real Model

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="gpt-4o-mini"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-3-small"
```

Any OpenAI-compatible endpoint works (DeepSeek, SiliconFlow, local vLLM, etc.).

## API Reference

All endpoints are served from `http://127.0.0.1:8000`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check and storage status |
| `GET` | `/api/dashboard` | Full snapshot: concepts, episodes, skills, edges, profile |
| `POST` | `/api/chat` | Send a message, receive a tutor response |
| `POST` | `/api/chat/stream` | SSE streaming chat with reasoning and memory events |
| `POST` | `/api/extract` | Force episode extraction from the current buffer |
| `POST` | `/api/diagnostics/model-test` | Test LLM / embedding / reranker connectivity |
| `POST` | `/api/rebuild-retrieval` | Rebuild all retrieval embeddings |
| `POST` | `/api/reset-memory` | Wipe all memory, conversations, and profile |
| `GET` | `/api/sessions` | List all conversation sessions |
| `GET` | `/api/sessions/{id}/turns` | Get turns for a specific session |

### Example: Streaming Chat

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain the chain rule in calculus", "session_id": "demo"}'
```

The response is an SSE stream with event types: `reasoning`, `text`, `memory_event`, `usage`, `done`.

## Project Structure

```
EduFlowGraph/
├── EduFlowGraph/                 # Python backend package
│   ├── pipeline.py               # Central orchestrator (TutorPipeline)
│   ├── web_app.py                # FastAPI application and endpoints
│   ├── config.py                 # Settings and runtime config dataclasses
│   ├── schemas.py                # Core data types (Turn, MemoryEvent)
│   ├── llm.py                    # LLM client (chat, embeddings, reranking)
│   ├── prompts.py                # Prompt template loader
│   ├── skills.py                 # Teaching action & difficulty pattern taxonomies
│   ├── memory/                   # Memory subsystem
│   │   ├── buffer.py             # Turn buffer and episode boundary detection
│   │   ├── episode_extractor.py  # Episode extraction from conversation segments
│   │   ├── concept_extractor.py  # Concept identification and deduplication
│   │   ├── skill_pipeline.py     # Skill evidence extraction and distillation
│   │   ├── skill_reranker.py     # Profile-aware skill selection
│   │   └── retriever.py          # Multi-signal memory retrieval
│   ├── profile/                  # Learner profiling subsystem
│   │   ├── dimensions.py         # Profile model definitions and budgets
│   │   ├── consolidator.py       # Profile rewriting at episode boundaries
│   │   ├── retriever.py          # Profile rendering for prompt injection
│   │   └── aggregator.py         # Profile summary helpers
│   ├── store/                    # Storage layer (dual backend)
│   │   ├── sqlite_storage.py     # SQLite connection, schema, migrations
│   │   ├── graph_store.py        # JSON graph store
│   │   ├── conversation_log.py   # JSONL conversation log
│   │   ├── memory_flow.py        # JSONL memory event journal
│   │   ├── profile_store.py      # JSON profile store
│   │   ├── sqlite_*.py           # SQLite implementations per store
│   │   └── migration.py          # Migration support
│   └── Prompt/                   # 12 markdown prompt templates
│
├── web/                          # Next.js frontend
│   ├── app/                      # App Router pages
│   │   ├── (workspace)/chat/     # Tutoring chat interface
│   │   ├── (workspace)/knowledge/# Concept mastery dashboard
│   │   ├── (workspace)/space/    # Memory, Profile, Skills views
│   │   └── (workspace)/settings/ # Runtime configuration
│   ├── components/               # React components
│   │   ├── providers/            # WorkspaceProvider (central state)
│   │   ├── sidebar/              # Navigation sidebar
│   │   ├── workspace/            # Main workspace panels
│   │   └── common/               # Shared components (Markdown renderer)
│   └── lib/                      # Types and runtime config
│
├── scripts/                      # Operational scripts
│   ├── start_web.py              # Unified launcher (backend + frontend)
│   ├── migrate_storage.py        # JSON → SQLite migration
│   └── export_storage.py         # SQLite → JSON export
│
├── data/                         # Runtime data (SQLite DB, gitignored)
├── requirements.txt              # Python dependencies
└── .env.example                  # Environment variable template
```

## Storage

The default backend is a single embedded SQLite database at `data/eduflowgraph.db`. No external database server, ORM, or vector database is required.

**Design choices:**
- JSON payload columns for flexible Concept / Episode / Skill schemas
- Dedicated `Float32 BLOB` table for embedding vectors
- WAL mode for concurrent frontend reads and background writes
- Foreign keys and transactions for graph consistency
- Schema versioning with automatic v1 → v2 → v3 migrations

### Legacy JSON Backend

```bash
export EDUFLOW_STORAGE_BACKEND=json
```

### Migration

```bash
# Preview changes
.venv/bin/python scripts/migrate_storage.py --data-dir data --dry-run

# Apply migration
.venv/bin/python scripts/migrate_storage.py --data-dir data --apply

# Verify integrity
.venv/bin/python scripts/migrate_storage.py --data-dir data --verify

# Export for rollback
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-export-$(date +%Y%m%d-%H%M%S)
```

## License

This project is for research and educational purposes.
