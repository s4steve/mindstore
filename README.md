# Mindstore

A personal knowledge store that captures thoughts, notes, events, tasks, contacts, and home maintenance items — with semantic search, a web UI, and an MCP server for Claude integration.

Features include:
- **Capture** thoughts, notes, and events via the web UI or API
- **Semantic search** across your knowledge store using vector similarity (pgvector)
- **Tasks** with priorities, due dates, categories, and optional recurrence
- **Contacts** with interaction logging and "reach out" reminders
- **Home maintenance** tracking with interval-based scheduling
- **Dashboard** surfacing overdue items and contacts to reach out to
- **Wiki** — auto-generated tag-based knowledge pages with related tags and suggested connections
- **MCP integration** for Claude Desktop and Claude Code

Runs entirely in Docker on any `linux/amd64` or `linux/arm64` host (e.g. a Raspberry Pi 5) and is accessed remotely via Tailscale.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 + pgvector |
| `ingestion` | 8000 | FastAPI REST service (knowledge, tasks, contacts, home) |
| `mcp_server` | 8001 | MCP server (streamable-http transport) |
| `webapp` | 3000 | Web UI with nav, cookie-based login |

The ingestion service embeds content locally using `all-MiniLM-L6-v2` (384 dimensions) and stores it with pgvector for cosine similarity search. The MCP server delegates all operations to the ingestion API — it does not touch the database directly.

---

## Authentication

Mindstore uses three distinct authentication methods for different purposes:

| Service | Auth Method | Env Variable | Purpose |
|---|---|---|---|
| **REST API** (ingestion, port 8000) | `X-API-Key` header | `API_KEY` | Authenticate requests to ingest, search, manage tasks/contacts/home |
| **MCP Server** (port 8001) | Bearer token (`Authorization: Bearer <token>`) | `MCP_AUTH_TOKEN` | Authenticate MCP client connections (Claude Desktop, Claude Code) |
| **Web UI** (port 3000) | Cookie-based login | `WEB_USERNAME` / `WEB_PASSWORD` | Authenticate browser access via login page |

- Set `API_KEY` to a strong secret for service-to-service authentication
- Set `SESSION_SECRET` to a strong, independent secret — it signs web UI session cookies. Keeping it separate from `API_KEY` means a leaked REST key cannot be used to forge sessions, and either secret can be rotated without invalidating the other.
- Set `MCP_AUTH_TOKEN` to a strong secret for MCP client access (the server refuses to start if this is unset)
- Set `WEB_USERNAME` / `WEB_PASSWORD` for web UI login
- Web UI sessions are stored as HMAC-signed cookies (30-day expiry, no server-side state). There is no revocation list — rotating `SESSION_SECRET` is the way to force a global logout.

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
- `API_KEY` (service-to-service authentication: MCP server → ingestion service)
- `SESSION_SECRET` (HMAC key for web UI session cookies — must be distinct from `API_KEY`; generate with `openssl rand -hex 32`)
- `MCP_AUTH_TOKEN` (bearer token for MCP client connections — used by Claude Desktop / Claude Code)
- `WEB_USERNAME` / `WEB_PASSWORD` (web UI login)

### 2. Build and start

```bash
docker compose up --build
```

The first build of the **ingestion** service downloads PyTorch and the `all-MiniLM-L6-v2` model (~90MB). The MCP server no longer loads the model itself — it delegates embedding to ingestion via `POST /embed`, so its image stays small. Subsequent starts are instant.

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

The web UI is served on port 3000 with cookie-based authentication. On first visit you'll see a login page — enter your `WEB_USERNAME` / `WEB_PASSWORD` credentials and the session persists for 30 days. A navigation bar links between the five pages, with a logout link on the right.

| Page | URL | Description |
|---|---|---|
| Capture | `/` | Capture thoughts/notes/events, semantic search, recent entries |
| Tasks | `/tasks.html` | Manage tasks with filters, priorities, and inline editing |
| Contacts | `/contacts.html` | Contact list with interaction logging and stale-contact filter |
| Home | `/home.html` | Home maintenance items with interval scheduling |
| Wiki | `/wiki.html` | Auto-generated tag-based knowledge pages with suggested connections |

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

### Wiki page
The wiki is an auto-generated, read-only view over your existing data — it requires no manual curation. Everything is derived from the tags you already add to thoughts, notes, tasks, contacts, and home items.

- **Tag index sidebar** — lists every tag across all tables, sorted by frequency, with item counts; includes a filter input to quickly find tags
- **Tag detail view** — click a tag to see all items carrying that tag, grouped by type (thoughts, notes, events, tasks, contacts, home items)
- **Related tags** — shows tags that frequently co-occur with the selected tag; click to navigate between related topics
- **Suggested connections** — the most valuable feature: finds items that are semantically similar to the tag's content but don't carry that tag. This surfaces relationships you might not have noticed, like a thought from months ago that relates to a task you just created. Uses centroid embedding similarity across your vector store
- **Hash-based routing** — URLs like `/wiki.html#work` are bookmarkable and shareable; the browser back/forward buttons navigate between tags
- **Modal detail view** — click any item to see its full content (long notes are reassembled from all chunks)

The wiki updates automatically as you add, tag, or modify items — there is nothing to maintain.

---

## REST API

All endpoints (except `/health`) require `X-API-Key` header. This header authenticates requests to the **ingestion service** (port 8000).

**Note:** The MCP server (port 8001) uses **Bearer token authentication** via the `Authorization: Bearer <token>` header — this is separate from the REST API key. See the [Claude Code](#claude-code--global-mcp-setup) and [Claude Desktop](#claude-desktop) sections for MCP configuration.

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

### Wiki / Tags

| Method | Path | Description |
|---|---|---|
| `GET` | `/tags` | List all tags across all tables with usage counts |
| `GET` | `/tags/{tag}` | Items with this tag, related tags (co-occurrence), and suggested connections (semantic similarity) |

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
claude mcp add --transport streamable-http --scope global \
  --header "Authorization: Bearer your-mcp-auth-token" \
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
      "type": "streamable-http",
      "url": "http://<pi-tailscale-ip>:8001/mcp",
      "headers": {
        "Authorization": "Bearer your-mcp-auth-token"
      }
    }
  }
}
```

After editing the file, restart Claude Code for the tools to appear.

> **Note:** Use the `MCP_AUTH_TOKEN` value from your `.env` file. If `MCP_AUTH_TOKEN` is not set on the server, the MCP server will warn at startup but still accept unauthenticated connections. For production deployments, always set a strong `MCP_AUTH_TOKEN`.

---

## Claude Desktop

Add to `claude_desktop_config.json` (location varies by OS — check Claude Desktop settings):

```json
{
  "mcpServers": {
    "mindstore": {
      "type": "streamable-http",
      "url": "http://<pi-tailscale-ip>:8001/mcp",
      "headers": {
        "Authorization": "Bearer your-mcp-auth-token"
      }
    }
  }
}
```

Replace `your-mcp-auth-token` with the `MCP_AUTH_TOKEN` value from your `.env` file. Restart Claude Desktop after saving.

---

## Network Connectivity for MCP

### Understanding the Setup

**Important:** Bearer token authentication secures the MCP connection but does **not** make the server reachable over the internet. Network connectivity and authentication are separate concerns.

| Scenario | Network Path | Works without Proxy? | Recommended? |
|---|---|---|---|
| Claude Desktop on same WiFi as server (e.g., home network) | `http://192.168.x.x:8001/mcp` | ✅ Yes | ✓ Simple, no setup |
| Claude Desktop and server both on Tailscale | `http://<tailscale-ip>:8001/mcp` | ✅ Yes | ✓ **Recommended for remote** |
| Claude Desktop on different network, no VPN | Would need reverse proxy | ❌ No | ✗ Use proxy or VPN first |
| Claude Desktop and server both on WireGuard/OpenVPN | `http://<vpn-ip>:8001/mcp` | ✅ Yes | ✓ Alternative to Tailscale |

### Option 1: Same Local Network (Simple)

If your MCP server and Claude Desktop are on the same local network:

1. Find the server's local IP:
   ```bash
   # On the Raspberry Pi or host running the MCP server
   hostname -I
   # or on macOS
   ipconfig getifaddr en0
   ```

2. Configure Claude Desktop with the local IP:
   ```json
   {
     "mcpServers": {
       "mindstore": {
         "type": "streamable-http",
         "url": "http://192.168.1.50:8001/mcp",
         "headers": {
           "Authorization": "Bearer your-mcp-auth-token"
         }
       }
     }
   }
   ```

3. Verify connectivity from Claude Desktop's machine:
   ```bash
   curl -H "Authorization: Bearer your-mcp-auth-token" http://192.168.1.50:8001/mcp
   ```

### Option 2: Tailscale (Recommended for Remote Access)

Tailscale creates a secure private network across all your devices, allowing Claude Desktop and the MCP server to connect from anywhere without exposing them to the internet.

#### Setup Tailscale

1. **On the MCP server host:**
   ```bash
   # Install Tailscale
   curl -fsSL https://tailscale.com/install.sh | sh

   # Authenticate and join your Tailscale network
   sudo tailscale up

   # Get the Tailscale IP
   tailscale ip -4
   # Example output: 100.123.45.67
   ```

2. **On the machine running Claude Desktop:**
   ```bash
   # Install Tailscale and join the same network
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

3. **Configure Claude Desktop:**
   ```json
   {
     "mcpServers": {
       "mindstore": {
         "type": "streamable-http",
         "url": "http://100.123.45.67:8001/mcp",
         "headers": {
           "Authorization": "Bearer your-mcp-auth-token"
         }
       }
     }
   }
   ```

4. **Verify the connection:**
   ```bash
   curl -H "Authorization: Bearer your-mcp-auth-token" http://100.123.45.67:8001/mcp
   ```

#### Why Tailscale?

- **No port forwarding** — the server never exposes itself to the internet
- **Encrypted end-to-end** — traffic is encrypted by Tailscale in addition to your Bearer token
- **Works across networks** — use the MCP server from anywhere: home, office, mobile
- **Firewall-friendly** — works through most firewalls and NAT
- **Free tier** — supports up to 3 devices for personal use

### Option 3: Reverse Proxy (For Public Deployment)

If you need to expose the MCP server publicly (not recommended), use a reverse proxy with TLS:

```nginx
# Example: nginx reverse proxy
server {
    listen 443 ssl;
    server_name mindstore.example.com;

    ssl_certificate /etc/letsencrypt/live/mindstore.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mindstore.example.com/privkey.pem;

    location /mcp {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then configure Claude Desktop:
```json
{
  "mcpServers": {
    "mindstore": {
      "type": "streamable-http",
      "url": "https://mindstore.example.com/mcp",
      "headers": {
        "Authorization": "Bearer your-mcp-auth-token"
      }
    }
  }
}
```

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

## Troubleshooting MCP Connection Issues

### Claude Desktop can't connect to MCP server

**Problem:** Getting connection timeout or "host unreachable" errors.

**Check 1: Is the MCP server running?**
```bash
# Check if port 8001 is listening
netstat -tuln | grep 8001
# or
ss -tuln | grep 8001
```

**Check 2: Can you reach the server from the same machine?**
```bash
# Without auth (to test network connectivity first)
curl -v http://localhost:8001/mcp

# With auth (when testing from command line)
curl -H "Authorization: Bearer your-mcp-auth-token" http://localhost:8001/mcp
```

**Check 3: If using local IP, is it correct?**
```bash
# Get your server's actual local IP
hostname -I
# or on macOS
ipconfig getifaddr en0
```
Update Claude Desktop config to use the correct IP.

**Check 4: If using Tailscale, verify both devices are connected**
```bash
# On both machines, check Tailscale status
tailscale status

# Ping from Claude Desktop machine to MCP server's Tailscale IP
ping 100.x.x.x
```

**Check 5: Firewall blocking port 8001?**
- Check local firewall rules
- If on a home network, router may need port forwarding (only for local network, not internet)
- Tailscale bypasses firewall issues by creating a private network

### "401 Unauthorized" errors

**Problem:** Connection reaches the server but returns 401.

**Check:** Is `MCP_AUTH_TOKEN` set correctly in both `.env` and Claude Desktop config?

```bash
# On the server, check if token is configured
docker compose logs mcp_server | grep "Bearer token"

# Should see either:
# "Bearer token authentication enabled." (good)
# "MCP_AUTH_TOKEN is not set" (warning, but still accepts connections)
```

**Verify the token matches:**
- Value in `.env` file: `MCP_AUTH_TOKEN=your-actual-token`
- Value in Claude Desktop config: `"Authorization": "Bearer your-actual-token"`

### Claude Code (CLI) connection issues

For Claude Code (the CLI tool), use the same network path and Bearer token:

```bash
claude mcp add --transport streamable-http --scope global \
  --header "Authorization: Bearer your-mcp-auth-token" \
  mindstore http://100.x.x.x:8001/mcp
```

Then verify:
```bash
claude mcp list
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
