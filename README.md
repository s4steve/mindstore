# Mindstore

A personal knowledge store that captures thoughts, ideas, notes, and events, embeds them locally using sentence-transformers, stores them in PostgreSQL with pgvector, and exposes them via an MCP server.

Runs entirely in Docker on a Raspberry Pi 5 (ARM64) and is accessed remotely via Tailscale.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 + pgvector |
| `ingestion` | 8000 | FastAPI REST ingestion service |
| `mcp_server` | 8001 | MCP server (SSE transport) |

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

Ingest content. Automatically chunks articles and notes.

```json
{
  "content": "string (required, max 50,000 chars)",
  "content_type": "thought | note | event | article",
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

### `GET /stats`

Returns total count, breakdown by type, and most recent entry timestamp.

---

## MCP Tools

The MCP server exposes 7 tools:

| Tool | Description |
|---|---|
| `add_thought` | Capture a quick thought or idea |
| `add_note` | Store a structured note with a title |
| `add_event` | Log something that happened |
| `search_thoughts` | Semantically search your knowledge store |
| `get_recent` | Get the most recently added entries |
| `get_by_tag` | Find entries by tag |
| `get_stats` | Get summary statistics |

---

## Connecting via Tailscale

The two service endpoints are accessible over your Tailscale network:

- **Ingestion REST API:** `http://<pi-tailscale-ip>:8000`
- **MCP Server (SSE):** `http://<pi-tailscale-ip>:8001/sse`

Find your Pi's Tailscale IP with `tailscale ip -4` on the Pi.

### Claude Desktop (`claude_desktop_config.json`)

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

### Claude Code (`.mcp.json` in project root or `~/.config/claude/mcp.json`)

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

After saving the config, restart Claude Desktop or reload Claude Code for the tools to appear.

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
