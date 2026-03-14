# Mindstore

A personal knowledge store that captures thoughts, notes, events, tasks, contacts, and home maintenance items — with semantic search, a web UI, and an MCP server for Claude integration.

Features include:
- **Capture** thoughts, notes, and events via the web UI or API
- **Semantic search** across your knowledge store using vector similarity (pgvector)
- **Tasks** with priorities, due dates, categories, and optional recurrence
- **Contacts** with interaction logging and "reach out" reminders
- **Home maintenance** tracking with interval-based scheduling
- **Dashboard** surfacing overdue items and contacts to reach out to
- **MCP integration** for Claude Desktop and Claude Code

Runs entirely in Docker on any `linux/amd64` or `linux/arm64` host (e.g. a Raspberry Pi 5) and is accessed remotely via Tailscale.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 + pgvector |
| `ingestion` | 8000 | FastAPI REST service (knowledge, tasks, contacts, home) |
| `mcp_server` | 8001 | MCP server (streamable-http transport) |
| `webapp` | 3000 | Web UI with nav, basic auth |

The ingestion service embeds content locally using `all-MiniLM-L6-v2` (384 dimensions) and stores it with pgvector for cosine similarity search. The MCP server delegates all operations to the ingestion API — it does not touch the database directly.

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
- `WEB_USERNAME` / `WEB_PASSWORD` (web UI basic auth)

### 2. Build and start

```bash
docker compose up --build
```

The first build downloads PyTorch and the `all-MiniLM-L6-v2` model (~90MB). Subsequent starts are instant.

### 3. Verify

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Dashboard
curl http://localhost:8000/dashboard -H "X-API-Key: your-api-key"

# Ingest a thought
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"content": "Mindstore is working!", "content_type": "thought"}'
```

---

## Web UI

The web UI is served on port 3000 and requires HTTP basic auth (`WEB_USERNAME` / `WEB_PASSWORD`). A navigation bar links between the four pages.

| Page | URL | Description |
|---|---|---|
| Capture | `/` | Capture thoughts/notes/events, semantic search, recent entries |
| Tasks | `/tasks.html` | Manage tasks with filters, priorities, and inline editing |
| Contacts | `/contacts.html` | Contact list with interaction logging and stale-contact filter |
| Home | `/home.html` | Home maintenance items with interval scheduling |

### Capture page
- Type a thought and press `Ctrl+Enter` (or `⌘+Enter`) to save
- Content with multiple paragraphs or >500 words is auto-detected as a note
- Upload a `.txt` file to ingest as a note
- Semantic search returns results ranked by similarity score
- Click any recent entry or search result to open a detail modal; long notes are reassembled from all chunks so the full content is shown

### Tasks page
- Add tasks with title, priority (high/medium/low), category, due date, and optional recurrence
- Filter by status (open/done/cancelled), category, or tasks due this week
- Overdue tasks are highlighted red; recurring tasks show the interval
- Completing a recurring task automatically creates the next occurrence

### Contacts page
- Add contacts with name, email, phone, company, and notes
- Log interactions inline — each log appends a timestamped entry to the notes and updates "last contacted"
- "Reach out needed" filter shows contacts not reached in 14+ days (or never contacted)
- Client-side name search

### Home page
- Add maintenance items with a name, interval (days), and next due date
- Mark done automatically sets `last_done_at` and advances `next_due_at` by the interval
- Overdue items are highlighted red; items due within 7 days are highlighted yellow

---

## REST API

All endpoints (except `/health`) require `X-API-Key` header.

### Knowledge (thoughts, notes, events)

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest` | Ingest content (auto-chunks notes) |
| `POST` | `/ingest/batch` | Ingest multiple entries |
| `GET` | `/search?q=&limit=&content_type=` | Semantic search |
| `GET` | `/recent?limit=&content_type=` | Most recent entries |
| `GET` | `/thoughts/{id}` | Fetch a thought with all chunks concatenated |
| `PUT` | `/thoughts/{id}` | Update entry (re-embeds if content changes) |
| `DELETE` | `/thoughts/{id}` | Delete entry and all chunks |
| `GET` | `/stats` | Count by type, most recent timestamp |

**POST /ingest body:**
```json
{
  "content": "string (required, max 50,000 chars)",
  "content_type": "thought | note | event",
  "title": "optional string",
  "tags": ["optional", "list"],
  "metadata": {}
}
```

### Tasks

| Method | Path | Description |
|---|---|---|
| `POST` | `/tasks` | Create a task |
| `GET` | `/tasks?status=&category=&due_soon_days=` | List tasks |
| `GET` | `/tasks/{id}` | Get a task |
| `PUT` | `/tasks/{id}` | Update a task |
| `DELETE` | `/tasks/{id}` | Delete a task |
| `POST` | `/tasks/{id}/complete` | Mark done (creates next recurrence if set) |

**POST /tasks body:**
```json
{
  "title": "string (required)",
  "notes": "optional string",
  "priority": "high | medium | low",
  "status": "open | done | cancelled",
  "category": "general | work | personal | health | finance | home",
  "due_date": "YYYY-MM-DD",
  "recurrence_days": 7,
  "tags": []
}
```

### Contacts

| Method | Path | Description |
|---|---|---|
| `POST` | `/contacts` | Create a contact |
| `GET` | `/contacts?reach_out_days=` | List contacts (filter by days since last contact) |
| `GET` | `/contacts/{id}` | Get a contact |
| `PUT` | `/contacts/{id}` | Update a contact |
| `DELETE` | `/contacts/{id}` | Delete a contact |
| `POST` | `/contacts/{id}/interaction` | Log an interaction (appends timestamped note, sets last_contact_at) |

**POST /contacts body:**
```json
{
  "name": "string (required)",
  "email": "optional",
  "phone": "optional",
  "company": "optional",
  "notes": "optional",
  "tags": []
}
```

### Home Maintenance

| Method | Path | Description |
|---|---|---|
| `POST` | `/home` | Create a home item |
| `GET` | `/home?due_soon_days=` | List items |
| `GET` | `/home/{id}` | Get an item |
| `PUT` | `/home/{id}` | Update an item |
| `DELETE` | `/home/{id}` | Delete an item |
| `POST` | `/home/{id}/complete` | Mark done (advances next_due_at by interval_days) |

**POST /home body:**
```json
{
  "name": "string (required)",
  "notes": "optional",
  "interval_days": 90,
  "next_due_at": "ISO 8601 datetime",
  "tags": []
}
```

### Dashboard

| Method | Path | Description |
|---|---|---|
| `GET` | `/dashboard` | Overdue tasks, due-soon tasks, overdue home items, due-soon home items, contacts not reached in 14+ days |

---

## MCP Tools

The MCP server exposes 24 tools across four domains.

### Knowledge tools

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

### Task tools

| Tool | Description |
|---|---|
| `add_task` | Create a task with priority, category, due date, recurrence |
| `update_task` | Update any task field |
| `complete_task` | Mark done; auto-creates next recurrence if set |
| `list_tasks` | List tasks filtered by status, category, or due date window |

### Contact tools

| Tool | Description |
|---|---|
| `add_contact` | Add a contact |
| `update_contact` | Update contact fields |
| `log_interaction` | Log a timestamped interaction note and set last_contact_at |
| `list_contacts` | List contacts, optionally filtered by days since last contact |

### Home maintenance tools

| Tool | Description |
|---|---|
| `add_home_item` | Add a maintenance item with interval |
| `update_home_item` | Update a home item |
| `complete_home_item` | Mark done and advance next_due_at by interval |
| `list_home_items` | List items, optionally filtered by due date window |

### Dashboard tool

| Tool | Description |
|---|---|
| `get_dashboard` | Summary of overdue/due-soon tasks, home items, and contacts to reach |

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

# Rebuild a single service
docker compose up --build ingestion

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
