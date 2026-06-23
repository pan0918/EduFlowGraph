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

## Storage

The default runtime store is one embedded SQLite database:

```text
data/eduflowgraph.db
```

It uses:

- JSON payload columns for flexible Concept / Episode / Skill schemas
- a dedicated Float32 BLOB table for embeddings
- WAL mode for frontend reads alongside short background writes
- foreign keys and transactions for graph consistency

No database server, ORM, or vector database is required. The legacy JSON/JSONL
backend remains available during the migration window:

```bash
export EDUFLOW_STORAGE_BACKEND=json
```

### Migrating legacy data

Stop the web stack before applying a migration, then run:

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --dry-run
.venv/bin/python scripts/migrate_storage.py --data-dir data --apply
.venv/bin/python scripts/migrate_storage.py --data-dir data --verify
```

If an initialized but completely unused SQLite database already exists, migration
still refuses to replace it unless its business tables are verified empty:

```bash
.venv/bin/python scripts/migrate_storage.py \
  --data-dir data \
  --apply \
  --replace-empty
```

Migration never edits the legacy JSON/JSONL files. To roll back during the
observation window, export any new SQLite data first:

```bash
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-export-$(date +%Y%m%d-%H%M%S)
```

After validating the export, stop the app and point the JSON backend at the
chosen exported directory with `EDUFLOW_STORAGE_BACKEND=json` and
`EDUFLOW_DATA_DIR=<export-directory>`.

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
.venv/bin/python -m unittest discover -s tests
node --test $(rg --files web -g '*.test.mjs')
(cd web && npm run build)
.venv/bin/python scripts/smoke_run.py
```
