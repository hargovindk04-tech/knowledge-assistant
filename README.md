# Company Knowledge Assistant

A RAG (Retrieval-Augmented Generation) app that answers questions from company documents. Documents are ingested into Postgres with **pgvector**, embedded with **OpenAI**, indexed with **HNSW**, and queried through a FastAPI backend with a simple web UI. Similar questions are accelerated with a **Redis semantic LLM cache**.

## Features

- Ingest `.txt`, `.md`, `.pdf`, and `.docx` files from a `data/` folder
- Store embeddings in PostgreSQL + pgvector (`vector(1536)`)
- Build an **HNSW** vector index after ingest for fast similarity search
- Ask grounded questions via ChatGPT (`gpt-4o-mini`) with source citations
- **Redis semantic cache** so similar questions can reuse prior LLM answers
- LangSmith tracing for debugging LLM / retrieval chains
- Docker Compose deployment: **app, Postgres, and Redis** all run as containers

## Architecture

```
Browser (UI)  →  http://localhost:8000
    │
    ▼
┌──────────────────────────────────────────────┐
│  Docker Compose                              │
│                                              │
│  cka-app (FastAPI / Uvicorn)                 │
│    ├── POST /ingest → embed + HNSW           │
│    └── POST /ask    → cache? retrieve + LLM  │
│           │                    │             │
│           ▼                    ▼             │
│  cka-db (Postgres+pgvector)  cka-redis       │
│     hostname: postgres         Redis Stack   │
│                              hostname:       │
│                              cka-redis       │
└──────────────────────────────────────────────┘
```

| Component | Technology |
|-----------|------------|
| API / UI | FastAPI, Uvicorn, static HTML (`cka-app`) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| LLM | OpenAI `gpt-4o-mini` |
| Vector DB | Postgres 17 + pgvector (`cka-db`) |
| Vector index | HNSW (cosine distance) via `langchain_postgres` |
| LLM cache | Redis Stack + `RedisSemanticCache` (`cka-redis`) |
| Orchestration | LangChain retrieval + stuff-documents chain |
| Deployment | Docker Compose — **app, Postgres, and Redis** in containers |

## Project structure

```
knowledge-assistant/
├── app/
│   ├── api.py          # FastAPI routes: /, /ingest, /ingest/status, /ask
│   ├── ingest.py       # Document load, chunk, embed, HNSW index
│   ├── rag.py          # RAG chain + Redis semantic LLM cache
│   ├── utils.py        # PGEngine, embeddings, vector store factory
│   └── static/         # Web UI (index.html, CSS)
├── data/               # Source documents to ingest (by category folders)
├── init-db/
│   └── init.sql        # Creates extension + embedding table
├── seed/               # Optional seed assets
├── docker-compose.yml  # app + postgres + redis
├── Dockerfile
├── requirements.txt
├── .env                # Secrets (not committed)
└── .gitignore
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- OpenAI API key
- (Optional) LangSmith API key for tracing

The **application**, **Postgres**, and **Redis** are all started with Docker Compose. You do not need a local Python venv, Postgres, or Redis install for the standard deployment.

## Environment variables

Create a `.env` file in the project root (already gitignored):

```env
# Database — use hostname "postgres" (Compose service name)
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

# Redis semantic LLM cache (Compose service / container hostname)
REDIS_URL=redis://cka-redis:6379/0
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async Postgres URL. Host **must** be `postgres`, not `localhost`. |
| `DATA_DIR` | No | Document root (default: `data`) |
| `OPENAI_API_KEY` | Yes | OpenAI key for embeddings and chat |
| `RETRIEVAL_K` | No | Top-k chunks for RAG (default: `5`) |
| `REDIS_URL` | Yes (for cache) | Redis URL. Host **must** be `cka-redis` (container name) inside Compose. |
| `LANGCHAIN_TRACING_V2` | No | Enable LangSmith tracing |
| `LANGSMITH_API_KEY` | No | LangSmith auth |
| `LANGSMITH_PROJECT` | No | LangSmith project name (e.g. `cka`) |

**Important:** Never commit `.env`. GitHub push protection will block pushes that contain secrets.

## Docker deployment

This project is deployed with **Docker Compose**. All three services run as containers:

| Service | Container | Role | Ports |
|---------|-----------|------|-------|
| `app` | `cka-app` | FastAPI + UI (Uvicorn) | `8000` |
| `postgres` | `cka-db` | Postgres + pgvector | `5432` |
| `redis` | `cka-redis` | Redis Stack (semantic LLM cache) | `6379`, `8001` (RedisInsight UI) |

- App → Postgres over the Compose network using hostname **`postgres`**
- App → Redis using hostname **`cka-redis`** (see `REDIS_URL`)
- Host code is bind-mounted into `cka-app` (`.:/app`) so app file changes apply without rebuild, unless `requirements.txt` / `Dockerfile` change

### 1. Configure `.env`

Copy the template above and set your `OPENAI_API_KEY`. Keep:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres123@postgres:5432/rag_db
REDIS_URL=redis://cka-redis:6379/0
```

### 2. Start all containers

```powershell
cd D:\github\knowledge-assistant
docker compose up --build -d
```

This starts **Postgres, Redis, and the app**. Confirm:

```powershell
docker compose ps
```

You should see `cka-db`, `cka-redis`, and `cka-app` running.

- App / UI: http://localhost:8000  
- Postgres (optional host tools): `localhost:5432` — user `postgres`, password `postgres123`, database `rag_db`
- Redis: `localhost:6379`
- RedisInsight UI: http://localhost:8001

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

The `data/` folder is available inside the app container via the volume mount.

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

Ask a similar question again — if the Redis semantic cache hits, `/ask` is typically much faster.

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

## Redis semantic LLM cache

`/ask` uses LangChain’s global LLM cache backed by **Redis Stack** (`RedisSemanticCache` in `app/rag.py`).

```python
from langchain_core.globals import set_llm_cache
from langchain_redis import RedisSemanticCache
from langchain_openai import OpenAIEmbeddings

REDIS_URL = os.getenv("REDIS_URL")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

set_llm_cache(
    RedisSemanticCache(
        redis_url=REDIS_URL,
        embeddings=embeddings,
        distance_threshold=0.98,
    )
)
```

| Setting | Value | Meaning |
|---------|-------|---------|
| `redis_url` | from `REDIS_URL` | Redis connection (`redis://cka-redis:6379/0`) |
| `embeddings` | `text-embedding-3-small` | Embeds prompts to find *similar* cached calls |
| `distance_threshold` | `0.98` | How close a new prompt must be to reuse a cached answer (higher = stricter match) |

### Behavior

- First ask for a question: full RAG + OpenAI call (slower)
- Later asks that are semantically very similar: may hit the Redis cache (faster)
- Exact wording is not required — similarity is embedding-based
- Cache lives in the `redis-data` Docker volume

### Dependencies

From `requirements.txt`:

```text
redis
langchain-redis
```

Rebuild the app image after adding these packages:

```powershell
docker compose build app
docker compose up -d --force-recreate
```

## How ask (RAG) works

1. Check Redis semantic LLM cache for a similar prior prompt
2. Embed the question (OpenAI) if needed
3. Retrieve top-`RETRIEVAL_K` similar chunks from pgvector (HNSW-backed)
4. Stuff context into a grounded system prompt
5. Generate answer with `gpt-4o-mini` (or reuse cached LLM result)
6. Return answer + unique source paths

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

To reset Postgres **and** Redis volumes (destructive):

```powershell
docker compose down -v
docker compose up --build -d
```

## Common Docker commands

```powershell
# Start all containers (app + postgres + redis)
docker compose up -d

# Stop all
docker compose down

# Rebuild app image after requirements.txt / Dockerfile changes, then recreate
docker compose build app
docker compose up -d --force-recreate

# Logs
docker compose logs -f app
docker compose logs -f
docker compose logs app --tail 100
docker compose logs redis --tail 50

# Check env inside the app container
docker compose exec app printenv DATABASE_URL
docker compose exec app printenv REDIS_URL
docker compose exec app printenv OPENAI_API_KEY

# Reset DB + Redis volumes (destructive) and restart everything
docker compose down -v
docker compose up --build -d
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connect call failed ... 127.0.0.1:5432` | App using `localhost` for DB | Set `DATABASE_URL` host to `postgres` |
| Redis connection errors | Wrong host / Redis not up | Set `REDIS_URL=redis://cka-redis:6379/0`; `docker compose up -d redis` |
| `Missing credentials` / OpenAI error | No API key | Set `OPENAI_API_KEY` in `.env`, recreate app |
| `ModuleNotFoundError: langchain_redis` / `redis` | Deps missing in image | Update `requirements.txt`, `docker compose build app` |
| Ingest “succeeds” but files skipped | Per-file errors caught in ingest | Check `docker compose logs app` for `INGEST ERROR` |
| Dimension mismatch | Table dims ≠ embedding model | Align `init.sql` (`1536` for OpenAI), reset volume, re-ingest |
| First `/ask` slow, similar asks faster | Semantic cache miss then hit | Expected with Redis cache |
| Similar ask still slow | Threshold too strict / different prompt | Adjust `distance_threshold` or clear Redis volume |
| Push rejected (GH013 secrets) | `.env` committed with API keys | Remove `.env` from git history, rotate keys, keep `.env` gitignored |
| Container unhealthy | Healthcheck hits `/health` (not implemented) | App can still work at `/`; ignore or add a `/health` route |

## Security notes

- Keep secrets only in `.env` (gitignored).
- If a key was ever pushed or pasted in chat, **rotate it** in OpenAI / LangSmith.
- Do not commit real credentials into README or example files.

## License

Private / internal project unless otherwise specified.
