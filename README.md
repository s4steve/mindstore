# Mindstore

A personal knowledge store that captures thoughts, ideas, notes, and events, embeds them locally using sentence-transformers, stores them in PostgreSQL with pgvector, and exposes them via an MCP server and a web UI.

Features include:
- **Capture** thoughts, notes, and events via the web UI or API
- **Semantic search** across your knowledge store using vector similarity (pgvector)
- **MCP integration** for Claude Desktop and Claude Code

Runs entirely in Docker on any `linux/amd64` or `linux/arm64` host (e.g. a Raspberry Pi 5) and is accessed remotely via Tailscale.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 + pgvector |
| `ingestion` | 8000 | FastAPI REST ingestion and search service |
| `mcp_server` | 8001 | MCP server (streamable-http transport) |
| `webapp` | 3000 | Web UI (capture + semantic search) |

The ingestion service embeds content locally using `all-MiniLM-L6-v2` (384 dimensions) and stores it with pgvector for cosine similarity search.

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/s4steve/mindstore.git
cd mindstore
cp .env.example .env
```

Edit `.env` and set strong values for:
- `POSTGRES_PASSWORD`
- `API_KEY`

### 2. Build and start

```bash
docker compose up --build
```

The first build downloads PyTorch and the `all-MiniLM-L6-v2` model (~90MB). Subsequent starts are instant.

### 3. Verify

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Ingest a thought
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"content": "Mindstore is working!", "content_type": "thought"}'

# Stats
curl http://localhost:8000/stats -H "X-API-Key: your-api-key"
```

---

## REST API

### `POST /ingest`

Ingest content. Notes are automatically chunked by paragraph, with a sliding window fallback for long unstructured content.

```json
{
  "content": "string (required, max 50,000 chars)",
  "content_type": "thought | note | event",
  "title": "optional string",
  "tags": ["optional", "list"],
  "metadata": {}
}
```

Response:
```json
{"ids": ["uuid"], "chunks_created": 1, "content_type": "thought"}
```

### `GET /health`

Returns service status. No auth required.

### `GET /search?q=...&limit=10&content_type=...`

Semantic vector search. Embeds the query and returns results ranked by cosine similarity.

```json
[
  {
    "id": "uuid",
    "content": "string",
    "title": "string or null",
    "tags": ["list"],
    "content_type": "thought",
    "created_at": "iso8601",
    "similarity": 0.87
  }
]
```

### `GET /stats`

Returns total count, breakdown by type, and most recent entry timestamp.

---

## Web UI

The web UI is served on port 3000 and requires HTTP basic auth (`WEB_USERNAME` / `WEB_PASSWORD`).

- **Capture** — type a thought and press `Ctrl+Enter` (or `⌘+Enter`) to save it instantly
- **Search** — enter any natural language query to find semantically related entries; results show similarity scores
- **Recent** — the 5 most recent entries are always visible below the search section

---

## MCP Tools

The MCP server exposes 10 tools:

| Tool | Description |
|---|---|
| `add_thought` | Capture a quick thought or idea |
| `add_note` | Store a structured note with a title |
| `add_event` | Log something that happened |
| `search_thoughts` | Semantically search your knowledge store |
| `get_recent` | Get the most recently added entries |
| `get_by_tag` | Find entries by tag |
| `get_by_date_range` | Find entries within a date range |
| `weekly_review` | Summarise the last N days with tag frequency |
| `update_thought` | Edit an existing entry (re-embeds if content changes) |
| `delete_thought` | Remove an entry and all its chunks |
| `get_stats` | Get summary statistics |

---

## Connecting via Tailscale

The service endpoints are accessible over your Tailscale network:

- **Web UI:** `http://<tailscale-ip>:3000`
- **Ingestion REST API:** `http://<tailscale-ip>:8000`
- **MCP Server:** `http://<tailscale-ip>:8001/mcp`

Find the host's Tailscale IP with `tailscale ip -4`.

---

## Claude Code — Global MCP Setup

Adding mindstore globally makes the tools available in every project without any per-project config.

### Option 1: CLI (recommended)

```bash
claude mcp add --transport http --scope global \
  --header "X-API-Key: your-api-key" \
  mindstore http://<pi-tailscale-ip>:8001/mcp
```

Verify it was added:

```bash
claude mcp list
```

Remove it if needed:

```bash
claude mcp remove --scope global mindstore
```

### Option 2: Edit config manually

Add the following to `~/.claude.json` under the `"mcpServers"` key (create the key if it doesn't exist):

```json
{
  "mcpServers": {
    "mindstore": {
      "type": "http",
      "url": "http://<pi-tailscale-ip>:8001/mcp",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

After editing the file, restart Claude Code for the tools to appear.

---

## Claude Desktop

Add to `claude_desktop_config.json` (location varies by OS — check Claude Desktop settings):

```json
{
  "mcpServers": {
    "mindstore": {
      "type": "http",
      "url": "http://<pi-tailscale-ip>:8001/mcp",
      "headers": {
        "X-API-Key": "your-api-key"
      }
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Docker Commands

```bash
# Start all services
docker compose up -d

# Rebuild after code changes
docker compose up --build

# View logs
docker compose logs -f ingestion
docker compose logs -f mcp_server

# Stop everything
docker compose down

# Stop and remove data (destructive)
docker compose down -v
```

---

## Running Tests

### Unit tests (no Docker required)

```bash
pip install pytest sentence-transformers
pip install -e embedder/
cd tests
pytest unit/
```

### Integration tests (requires running stack)

```bash
docker compose up -d
pytest tests/integration/
```

---

## Adding a New Embedder (e.g. Voyage AI)

1. Create `embedder/embedder/voyage.py` implementing `EmbedderBase`
2. Set `EMBEDDER_BACKEND=voyage` and `VOYAGE_API_KEY=...` in `.env`
3. Update the embedder factory in `ingestion/ingestion/main.py` and `mcp_server/mcp_server/main.py` to select the backend from the env var

No other code changes are needed.
