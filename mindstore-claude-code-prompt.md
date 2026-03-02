# Mindstore — Claude Code Implementation Prompt

## Project Overview

Build **Mindstore**: a personal knowledge store that captures thoughts, ideas, notes, and events, embeds them locally using sentence-transformers, stores them in PostgreSQL with pgvector, and exposes them via an MCP server. The system runs entirely in Docker on a Raspberry Pi 5 (ARM64) and is accessed remotely via Tailscale.

---

## Constraints & Decisions (Do Not Override)

- **Architecture:** ARM64 (Raspberry Pi 5, 8GB RAM) — all Docker images must have ARM64 variants
- **Embeddings:** Local only using `sentence-transformers` with `all-MiniLM-L6-v2` (384 dimensions). No external embedding APIs. Design the embedding layer as a pluggable abstraction so Voyage AI can be added later without restructuring.
- **Database:** PostgreSQL 15+ with pgvector extension
- **MCP transport:** SSE (HTTP-based) not stdio — the server must be reachable over the network via Tailscale, not just locally via subprocess
- **Capture methods:** REST API (FastAPI) and MCP tools — no CLI tool or file watcher in this phase
- **Language:** Python 3.11+
- **Container orchestration:** Docker Compose
- **No cloud dependencies** — everything runs on the Pi

---

## Repository Structure

Create the following structure:

```
mindstore/
├── docker-compose.yml
├── .env.example
├── .env                          # gitignored
├── README.md
│
├── db/
│   └── init.sql                  # Schema and extensions
│
├── embedder/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── embedder/
│       ├── __init__.py
│       ├── base.py               # Abstract EmbedderBase class
│       └── local.py              # SentenceTransformerEmbedder
│
├── ingestion/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ingestion/
│       ├── __init__.py
│       ├── main.py               # FastAPI app
│       ├── models.py             # Pydantic schemas
│       ├── chunker.py            # Chunking logic
│       ├── pipeline.py           # Orchestrates chunk → embed → store
│       └── db.py                 # asyncpg database connection pool
│
├── mcp_server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── mcp_server/
│       ├── __init__.py
│       ├── main.py               # MCP server entry point (SSE transport)
│       ├── tools.py              # Tool definitions
│       ├── search.py             # Semantic search logic
│       └── db.py                 # asyncpg database connection pool
│
└── shared/
    └── db_utils.py               # Shared connection helpers (optional)
```

---

## Phase 1 — Database Foundation

### Goal
PostgreSQL + pgvector running in Docker with the correct schema.

### `db/init.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS thoughts (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content      TEXT NOT NULL,
    embedding    vector(384),
    source       TEXT NOT NULL DEFAULT 'api',   -- 'api', 'mcp'
    content_type TEXT NOT NULL DEFAULT 'thought', -- 'thought', 'note', 'event', 'article'
    title        TEXT,
    tags         TEXT[] DEFAULT '{}',
    metadata     JSONB DEFAULT '{}',
    chunk_index  INTEGER DEFAULT 0,
    parent_id    UUID REFERENCES thoughts(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS thoughts_embedding_idx
    ON thoughts USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS thoughts_tags_idx ON thoughts USING gin(tags);
CREATE INDEX IF NOT EXISTS thoughts_content_type_idx ON thoughts(content_type);
CREATE INDEX IF NOT EXISTS thoughts_created_at_idx ON thoughts(created_at DESC);
CREATE INDEX IF NOT EXISTS thoughts_parent_id_idx ON thoughts(parent_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER thoughts_updated_at
    BEFORE UPDATE ON thoughts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### `docker-compose.yml` (db service only at this stage)

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    platform: linux/arm64
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-mindstore}
      POSTGRES_USER: ${POSTGRES_USER:-mindstore}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-mindstore}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### Validation
After `docker compose up db`, verify:
- Can connect with `psql`
- `\dx` shows `vector` extension installed
- `\d thoughts` shows correct schema including `vector(384)` column

---

## Phase 2 — Embedder Service

### Goal
A shared embedder module that loads `all-MiniLM-L6-v2` once at startup and exposes an embed function. Must be designed as a pluggable abstraction.

### `embedder/embedder/base.py`

```python
from abc import ABC, abstractmethod

class EmbedderBase(ABC):
    """Abstract base class for embedding providers.
    Implement this to add Voyage AI or OpenAI later."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single string, return list of floats."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple strings, return list of embeddings."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimension count."""
        ...
```

### `embedder/embedder/local.py`

```python
from sentence_transformers import SentenceTransformer
from .base import EmbedderBase

class SentenceTransformerEmbedder(EmbedderBase):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
        self._dims = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()

    @property
    def dimensions(self) -> int:
        return self._dims
```

### `embedder/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Install torch CPU-only first (much smaller on ARM64)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers

COPY . .
RUN pip install --no-cache-dir -e .

# Pre-download the model during build so startup is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

**Important:** The model is downloaded and baked into the image at build time. This avoids slow first-run downloads on the Pi.

---

## Phase 3 — Ingestion Service (FastAPI)

### Goal
A FastAPI service that accepts content via REST, chunks it appropriately, embeds it, and stores it in PostgreSQL.

### Chunking Strategy (`ingestion/ingestion/chunker.py`)

Implement a `chunk(content, content_type)` function with these rules:

| content_type | Strategy |
|---|---|
| `thought` | No chunking — always single entry |
| `note` | Split by paragraph, min 50 chars per chunk |
| `event` | No chunking — always single entry |
| `article` | Sliding window: 500 tokens, 50 token overlap |

Return a list of `ChunkResult(text, chunk_index, total_chunks)`.

### API Endpoints (`ingestion/ingestion/main.py`)

Implement the following REST endpoints:

#### `POST /ingest`
```json
{
  "content": "string (required)",
  "content_type": "thought | note | event | article (default: thought)",
  "title": "string (optional)",
  "tags": ["string"] ,
  "source": "api",
  "metadata": {}
}
```
Response:
```json
{
  "ids": ["uuid", "uuid"],
  "chunks_created": 2,
  "content_type": "note"
}
```

#### `GET /health`
Returns service status and DB connectivity.

#### `GET /stats`
Returns total thought count, breakdown by content_type, most recent entry timestamp.

### Pipeline (`ingestion/ingestion/pipeline.py`)

```python
async def ingest(request: IngestRequest, db_pool, embedder) -> IngestResponse:
    chunks = chunker.chunk(request.content, request.content_type)
    parent_id = None

    ids = []
    for chunk in chunks:
        vector = embedder.embed(chunk.text)
        id = await db.insert_thought(
            pool=db_pool,
            content=chunk.text,
            embedding=vector,
            source=request.source,
            content_type=request.content_type,
            title=request.title,
            tags=request.tags,
            metadata=request.metadata,
            chunk_index=chunk.chunk_index,
            parent_id=parent_id
        )
        if parent_id is None and len(chunks) > 1:
            parent_id = id
        ids.append(id)

    return IngestResponse(ids=ids, chunks_created=len(chunks))
```

### Docker service additions to `docker-compose.yml`

```yaml
  ingestion:
    build:
      context: ./ingestion
      dockerfile: Dockerfile
    platform: linux/arm64
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    depends_on:
      db:
        condition: service_healthy
```

---

## Phase 4 — MCP Server

### Goal
An MCP server using SSE transport (HTTP-based, not stdio) so it can be reached over Tailscale from Claude Desktop, Claude Code, or any future custom client.

Use the `mcp` Python SDK from Anthropic. The server must run as a persistent HTTP service.

### Tools to implement (`mcp_server/mcp_server/tools.py`)

#### Write Tools

**`add_thought`**
- Description: "Capture a quick thought or idea"
- Params: `content: str`, `tags: list[str] = []`
- Internally calls the ingestion pipeline with `content_type="thought"`

**`add_note`**
- Description: "Store a structured note with a title"
- Params: `title: str`, `content: str`, `tags: list[str] = []`
- content_type: `note`

**`add_event`**
- Description: "Log something that happened"
- Params: `description: str`, `tags: list[str] = []`, `metadata: dict = {}`
- content_type: `event`

#### Read Tools

**`search_thoughts`**
- Description: "Semantically search your knowledge store"
- Params: `query: str`, `limit: int = 10`, `content_type: str = None`
- Embeds the query, runs cosine similarity search, returns results with similarity scores

**`get_recent`**
- Description: "Get the most recently added entries"
- Params: `limit: int = 10`, `content_type: str = None`

**`get_by_tag`**
- Description: "Find entries by tag"
- Params: `tags: list[str]`, `limit: int = 20`

**`get_stats`**
- Description: "Get summary statistics about your knowledge store"
- Params: none
- Returns counts by type, total entries, date range

### Search query (`mcp_server/mcp_server/search.py`)

```sql
SELECT
    id,
    content,
    title,
    tags,
    content_type,
    source,
    created_at,
    1 - (embedding <=> $1::vector) AS similarity
FROM thoughts
WHERE ($2::text IS NULL OR content_type = $2)
  AND parent_id IS NULL  -- return parent chunks only, not sub-chunks
ORDER BY embedding <=> $1::vector
LIMIT $3;
```

### MCP Server Entry Point (`mcp_server/mcp_server/main.py`)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mindstore")

# Register all tools from tools.py
# Run with SSE transport on 0.0.0.0:8001
```

Use `FastMCP` from the `mcp` SDK with SSE transport. Bind to `0.0.0.0` so it's reachable via Tailscale.

### Docker service addition

```yaml
  mcp_server:
    build:
      context: ./mcp_server
      dockerfile: Dockerfile
    platform: linux/arm64
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    depends_on:
      db:
        condition: service_healthy
```

---

## Phase 5 — Configuration, Environment & Hardening

### `.env.example`

```bash
# Database
POSTGRES_DB=mindstore
POSTGRES_USER=mindstore
POSTGRES_PASSWORD=change_me_strong_password

# Ingestion service
INGESTION_HOST=0.0.0.0
INGESTION_PORT=8000

# MCP server
MCP_HOST=0.0.0.0
MCP_PORT=8001

# Embedding model (for future swap to voyage etc.)
EMBEDDER_BACKEND=local
EMBEDDER_MODEL=all-MiniLM-L6-v2

# Optional: API key placeholder for future Voyage integration
# VOYAGE_API_KEY=
```

### Hardening checklist (implement all of these)

- [ ] All services use `restart: unless-stopped`
- [ ] DB credentials only via environment variables, never hardcoded
- [ ] FastAPI ingestion endpoint has basic API key auth via `X-API-Key` header (key set in `.env`)
- [ ] MCP server has the same API key check on the SSE connection
- [ ] Input validation on all endpoints — max content length 50,000 chars
- [ ] Database connection pooling via asyncpg (min 2, max 10 connections)
- [ ] Proper async throughout — no blocking calls in async handlers
- [ ] Graceful shutdown handling in both services
- [ ] All Dockerfiles use non-root user

---

## Phase 6 — Tailscale Integration & Client Config

### README section to generate

Write a `README.md` section titled **"Connecting via Tailscale"** that explains:

1. The two service endpoints:
   - Ingestion REST API: `http://<pi-tailscale-ip>:8000`
   - MCP Server (SSE): `http://<pi-tailscale-ip>:8001/sse`

2. Claude Desktop configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mindstore": {
      "url": "http://<pi-tailscale-ip>:8001/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

3. Claude Code configuration (`.mcp.json` in project root or `~/.config/claude/mcp.json`):
```json
{
  "mcpServers": {
    "mindstore": {
      "url": "http://<pi-tailscale-ip>:8001/sse",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

---

## Phase 7 — Testing

Write the following tests:

### Unit tests
- `test_chunker.py` — test each content_type produces correct chunks
- `test_embedder.py` — test embed returns list of 384 floats
- `test_pipeline.py` — mock db, test ingest calls chunker and embedder correctly

### Integration tests (require running Docker stack)
- `test_api.py` — POST to `/ingest`, GET `/health`, GET `/stats`
- `test_search.py` — ingest 5 entries, search for one, assert it appears in top 3 results
- `test_mcp_tools.py` — call each MCP tool, assert correct response shape

---

## Final Deliverables Checklist

When complete, the following must all work:

- [ ] `docker compose up --build` completes without errors on ARM64
- [ ] `GET http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] `POST http://localhost:8000/ingest` with a thought creates an entry
- [ ] `GET http://localhost:8000/stats` shows 1 entry
- [ ] MCP server is reachable at `http://localhost:8001/sse`
- [ ] All 7 MCP tools are discoverable
- [ ] `search_thoughts` returns semantically relevant results
- [ ] Adding Claude Desktop/Code config and restarting connects successfully
- [ ] All tests pass
- [ ] `.env.example` is complete, `.env` is in `.gitignore`
- [ ] `README.md` covers: setup, docker commands, Tailscale config, MCP client config

---

## Implementation Notes for Claude Code

- Build and validate each phase before moving to the next
- After Phase 1, run `docker compose up db` and verify the schema
- After Phase 3, test the REST API manually before building the MCP layer
- The embedder module is shared code — both ingestion and mcp_server depend on it. Structure it as an installable local package (with `pyproject.toml`) so both services can install it via `pip install ../embedder`
- Use `asyncpg` for all database operations — not SQLAlchemy — to keep it lightweight on the Pi
- When writing Dockerfiles, always specify `platform: linux/arm64` and use slim base images
- PyTorch for ARM64 CPU must use the `--index-url https://download.pytorch.org/whl/cpu` flag — standard PyPI torch is not ARM64 compatible
- Do not use `localhost` in inter-service communication inside Docker Compose — use service names (`db`, `ingestion`, `mcp_server`)
