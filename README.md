# Company Knowledge Assistant

A RAG (Retrieval-Augmented Generation) app that answers questions from company documents. Documents are ingested into Postgres with **pgvector**, embedded with **OpenAI**, and queried through a FastAPI backend with a simple web UI.

## Features

- Ingest `.txt`, `.md`, `.pdf`, and `.docx` files from a `data/` folder
- Store embeddings in PostgreSQL + pgvector (`vector(1536)`)
- Build an **HNSW** vector index after ingest for fast similarity search
- Ask grounded questions via ChatGPT (`gpt-4o-mini`) with source citations
- Optional LangSmith tracing for debugging LLM / retrieval chains
- Docker Compose setup (app + Postgres)

## Architecture

```
Browser (UI)
    │
    ▼
FastAPI (app/api.py)
    ├── POST /ingest  → load → chunk → embed → pgvector → HNSW index
    └── POST /ask     → embed question → HNSW retrieve → LLM answer
                │
                ▼
     Postgres + pgvector + HNSW (cka-db)
```

| Component | Technology |
|-----------|------------|
| API / UI | FastAPI, Uvicorn, static HTML |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| LLM | OpenAI `gpt-4o-mini` |
| Vector DB | Postgres 17 + pgvector |
| Vector index | HNSW (cosine distance) via `langchain_postgres` |
| Orchestration | LangChain (retrieval + stuff documents chain) |
| Containers | Docker Compose (`cka-app`, `cka-db`) |

## Project structure

```
knowledge-assistant/
├── app/
│   ├── api.py          # FastAPI routes: /, /ingest, /ingest/status, /ask
│   ├── ingest.py       # Document load, chunk, embed, HNSW index
│   ├── rag.py          # Retrieval + LLM answer chain
│   ├── utils.py        # PGEngine, embeddings, vector store factory
│   └── static/         # Web UI (index.html, CSS)
├── data/               # Source documents to ingest (by category folders)
├── init-db/
│   └── init.sql        # Creates extension + embedding table
├── seed/               # Optional seed assets
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                # Secrets (not committed)
└── .gitignore
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- OpenAI API key
- (Optional) LangSmith API key for tracing

## Environment variables

Create a `.env` file in the project root (already gitignored):

```env
# Database — use hostname "postgres" inside Docker Compose
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@postgres:5432/rag_db

# Folder of documents to ingest
DATA_DIR=data

# OpenAI (required for embeddings + ask)
OPENAI_API_KEY=sk-your-openai-key

# How many chunks to retrieve per question
RETRIEVAL_K=5

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGSMITH_API_KEY=lsv2_your-langsmith-key
LANGSMITH_PROJECT=cka
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async Postgres URL. Inside Docker use host `postgres`; locally use `localhost`. |
| `DATA_DIR` | No | Document root (default: `data`) |
| `OPENAI_API_KEY` | Yes | OpenAI key for embeddings and chat |
| `RETRIEVAL_K` | No | Top-k chunks for RAG (default: `5`) |
| `LANGCHAIN_TRACING_V2` | No | Enable LangSmith tracing |
| `LANGSMITH_API_KEY` | No | LangSmith auth |
| `LANGSMITH_PROJECT` | No | LangSmith project name (e.g. `cka`) |

**Important:** Never commit `.env`. GitHub push protection will block pushes that contain secrets.

## Quick start (Docker)

### 1. Configure `.env`

Copy the template above and set your `OPENAI_API_KEY`.

### 2. Start services

```powershell
cd D:\github\knowledge-assistant
docker compose up --build -d
```

- App: http://localhost:8000  
- Postgres: `localhost:5432` (user `postgres`, password `postgres123`, db `rag_db`)

### 3. Add documents

Place files under `data/` (subfolders become `category` metadata), for example:

```
data/
├── faqs/
│   ├── vpn-faq.md
│   └── travel-faq.txt
├── guides/
│   └── vpn-setup.md
├── policies/
│   └── PTO Policy.pdf
└── handbooks/
    └── employee_handbook_2025.docx
```

Supported extensions: `.txt`, `.md`, `.pdf`, `.docx`

### 4. Ingest

Open http://localhost:8000 → click **Ingest Data**, or:

```powershell
curl -X POST http://localhost:8000/ingest
```

Check status:

```powershell
curl http://localhost:8000/ingest/status
```

### 5. Ask questions

Use the UI **Ask** button, or:

```powershell
curl -X POST http://localhost:8000/ask `
  -H "Content-Type: application/json" `
  -d "{\"question\": \"What is the PTO policy?\"}"
```

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `POST` | `/ingest` | Start background ingestion (409 if already running) |
| `GET` | `/ingest/status` | Status: `idle` \| `running` \| `succeeded` \| `failed` + stats/error |
| `POST` | `/ask` | Body: `{ "question": "..." }` → `{ "answer", "sources" }` |

## How ingestion works

1. Recursively load files from `DATA_DIR`
2. Tag each document with `category` = first path segment under `data/`
3. Split with `RecursiveCharacterTextSplitter` (`chunk_size=900`, `chunk_overlap=120`)
4. Embed with OpenAI `text-embedding-3-small`
5. Store chunks in table `langchain_pg_embedding`
6. Create / apply an **HNSW** vector index (see below)

## HNSW vector index

After documents are embedded and written to Postgres, ingest builds a Hierarchical Navigable Small World (**HNSW**) index so `/ask` can find similar chunks quickly without scanning every row.

Implemented in `app/ingest.py` via `_create_index()`:

```python
from langchain_postgres.v2.indexes import HNSWIndex, DistanceStrategy

async def _create_index(store):
    index = HNSWIndex(
        name="hnsw_idx",
        distance_strategy=DistanceStrategy.COSINE_DISTANCE,
        m=16,
        ef_construction=64,
    )
    await store.aapply_vector_index(index, concurrently=True)
    print("Index Created Succesfully")
```

Called at the end of `run_ingest_async()` after `aadd_documents(...)`.

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `name` | `hnsw_idx` | Index name in Postgres |
| `distance_strategy` | `COSINE_DISTANCE` | Similarity metric (matches typical text-embedding search) |
| `m` | `16` | Max connections per node (graph density; higher = better recall, more memory) |
| `ef_construction` | `64` | Build-time candidate list size (higher = better index quality, slower build) |
| `concurrently` | `True` | Apply index without blocking writes as aggressively |

### Why HNSW?

- **Speed:** Approximate nearest-neighbor search scales better than a full table scan as chunk count grows.
- **Quality:** Cosine distance works well with OpenAI embedding vectors.
- **When it runs:** On each successful ingest (after chunks are inserted). Look for `Index Created Succesfully` in app logs.

### How it fits `/ask`

1. Question is embedded with the same OpenAI model.
2. Retriever queries pgvector using the HNSW index.
3. Top-`RETRIEVAL_K` neighbors become LLM context.

Without an index, search still works for small datasets but gets slower as you add more documents. Re-run **Ingest Data** after large data changes so the index stays useful.

## How ask (RAG) works

1. Embed the question (OpenAI)
2. Retrieve top-`RETRIEVAL_K` similar chunks from pgvector (HNSW-backed)
3. Stuff context into a grounded system prompt
4. Generate answer with `gpt-4o-mini`
5. Return answer + unique source paths

Answers are instructed to stay within retrieved context; if the answer is not present, the model should say **"I don't know."**

## Database schema

Initialized once by `init-db/init.sql` when the Postgres volume is first created:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    langchain_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content text,
    embedding vector(1536),
    langchain_metadata jsonb,
    category text
);
```

`1536` matches OpenAI `text-embedding-3-small`. Changing embedding models requires matching this dimension and re-ingesting.

To reset the database (re-runs `init.sql`):

```powershell
docker compose down -v
docker compose up --build -d
```

## Local development (hybrid)

Run only Postgres in Docker; run the app on the host:

```powershell
docker compose up postgres -d

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Host must use localhost, not "postgres"
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@localhost:5432/rag_db"
$env:DATA_DIR = "data"
$env:OPENAI_API_KEY = "sk-your-key"
$env:RETRIEVAL_K = "5"

uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

## Common commands

```powershell
# Start / stop
docker compose up -d
docker compose down

# Rebuild after requirements.txt changes
docker compose build app
docker compose up -d --force-recreate app

# Logs
docker compose logs -f app
docker compose logs app --tail 100

# Check env inside container
docker compose exec app printenv DATABASE_URL
docker compose exec app printenv OPENAI_API_KEY

# Reset DB volume (destructive)
docker compose down -v
docker compose up --build -d
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connect call failed ... 127.0.0.1:5432` | App in Docker using `localhost` for DB | Set `DATABASE_URL` host to `postgres` |
| `Missing credentials` / OpenAI error | No API key | Set `OPENAI_API_KEY` in `.env`, recreate app |
| `ModuleNotFoundError: pymupdf` / `unstructured` | Deps missing in image | Update `requirements.txt`, `docker compose build app` |
| Ingest “succeeds” but files skipped | Per-file errors caught in ingest | Check `docker compose logs app` for `INGEST ERROR` |
| Dimension mismatch | Table dims ≠ embedding model | Align `init.sql` (`1536` for OpenAI), reset volume, re-ingest |
| `/ask` times vary (1s–10s+) | OpenAI latency; no response cache | Expected; optional LLM cache / chain reuse |
| Push rejected (GH013 secrets) | `.env` committed with API keys | Remove `.env` from git history, rotate keys, keep `.env` gitignored |
| Container unhealthy | Healthcheck hits `/health` (not implemented) | App can still work at `/`; ignore or add a `/health` route |

## Security notes

- Keep secrets only in `.env` (gitignored).
- If a key was ever pushed or pasted in chat, **rotate it** in OpenAI / LangSmith.
- Do not commit real credentials into README or example files.

## License

Private / internal project unless otherwise specified.
