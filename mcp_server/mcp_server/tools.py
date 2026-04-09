from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

from embedder import SentenceTransformerEmbedder

from . import search as search_module

# These are set by main.py before registering tools
_ingestion_url: str = ""
_api_key: str = ""
_embedder: SentenceTransformerEmbedder | None = None
_pool = None


def register_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    async def add_thought(content: str, tags: list[str] | None = None) -> dict:
        """Capture a quick thought or idea."""
        return await _call_ingest(
            content=content,
            content_type="thought",
            tags=tags or [],
        )

    @mcp.tool()
    async def add_note(title: str, content: str, tags: list[str] | None = None) -> dict:
        """Store a structured note with a title."""
        return await _call_ingest(
            content=content,
            content_type="note",
            title=title,
            tags=tags or [],
        )

    @mcp.tool()
    async def add_event(
        description: str, tags: list[str] | None = None, metadata: dict | None = None
    ) -> dict:
        """Log something that happened."""
        return await _call_ingest(
            content=description,
            content_type="event",
            tags=tags or [],
            metadata=metadata or {},
        )

    @mcp.tool()
    async def search_thoughts(
        query: str, limit: int = 10, content_type: str | None = None
    ) -> list[dict]:
        """Semantically search your knowledge store."""
        embedding = _embedder.embed(query)
        results = await search_module.semantic_search(_pool, embedding, limit, content_type)
        for r in results:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
            r["similarity"] = float(r["similarity"])
        return results

    @mcp.tool()
    async def get_recent(limit: int = 10, content_type: str | None = None) -> list[dict]:
        """Get the most recently added entries."""
        results = await search_module.get_recent(_pool, limit, content_type)
        for r in results:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return results

    @mcp.tool()
    async def get_by_tag(tags: list[str], limit: int = 20) -> list[dict]:
        """Find entries by tag."""
        results = await search_module.get_by_tag(_pool, tags, limit)
        for r in results:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return results

    @mcp.tool()
    async def get_stats() -> dict:
        """Get summary statistics about your knowledge store."""
        return await search_module.get_stats(_pool)

    @mcp.tool()
    async def get_by_date_range(
        start: str,
        end: str,
        content_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get entries created between two ISO timestamps (e.g. '2026-01-01T00:00:00Z')."""
        results = await search_module.get_by_date_range(_pool, start, end, content_type, limit)
        for r in results:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return results

    @mcp.tool()
    async def weekly_review(days: int = 7) -> dict:
        """Synthesize recent entries to surface patterns and forgotten threads.
        Returns all entries from the last N days grouped by type with tag frequency."""
        return await search_module.weekly_review(_pool, days)

    @mcp.tool()
    async def delete_thought(id: str) -> dict:
        """Permanently delete an entry and all its chunks by ID."""
        return await _call_ingestion("DELETE", f"/thoughts/{id}")

    @mcp.tool()
    async def update_thought(
        id: str,
        content: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Update an existing entry. If content changes it will be re-embedded."""
        payload = {}
        if content is not None:
            payload["content"] = content
        if title is not None:
            payload["title"] = title
        if tags is not None:
            payload["tags"] = tags
        if metadata is not None:
            payload["metadata"] = metadata
        return await _call_ingestion("PUT", f"/thoughts/{id}", payload)

    # ── Tasks ──────────────────────────────────────────────────────────────────

    @mcp.tool()
    async def add_task(
        title: str,
        notes: str | None = None,
        priority: str = "medium",
        due_date: str | None = None,
        recurrence_days: int | None = None,
        category: str = "general",
        tags: list[str] | None = None,
    ) -> dict:
        """Add a task. priority: high/medium/low.

        category: general/work/personal/health/finance/home.
        """
        payload = {"title": title, "priority": priority, "category": category, "tags": tags or []}
        if notes:
            payload["notes"] = notes
        if due_date:
            payload["due_date"] = due_date
        if recurrence_days:
            payload["recurrence_days"] = recurrence_days
        return await _call_ingestion("POST", "/tasks", payload)

    @mcp.tool()
    async def update_task(
        id: str,
        title: str | None = None,
        notes: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
        recurrence_days: int | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Update a task."""
        payload = {k: v for k, v in locals().items() if k != "id" and v is not None}
        return await _call_ingestion("PUT", f"/tasks/{id}", payload)

    @mcp.tool()
    async def complete_task(id: str) -> dict:
        """Mark a task done. If it recurs, creates the next occurrence."""
        return await _call_ingestion("POST", f"/tasks/{id}/complete")

    @mcp.tool()
    async def list_tasks(
        status: str | None = None,
        category: str | None = None,
        due_soon_days: int | None = None,
    ) -> list[dict]:
        """List tasks. Filter by status (open/done/cancelled), category, or due within N days."""
        params = {k: v for k, v in locals().items() if v is not None}
        path = f"/tasks?{urlencode(params)}" if params else "/tasks"
        return await _call_ingestion("GET", path)

    # ── Contacts ───────────────────────────────────────────────────────────────

    @mcp.tool()
    async def add_contact(
        name: str,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Add a contact."""
        payload = {"name": name, "tags": tags or []}
        for k, v in [("email", email), ("phone", phone), ("company", company), ("notes", notes)]:
            if v:
                payload[k] = v
        return await _call_ingestion("POST", "/contacts", payload)

    @mcp.tool()
    async def update_contact(
        id: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Update a contact."""
        payload = {k: v for k, v in locals().items() if k != "id" and v is not None}
        return await _call_ingestion("PUT", f"/contacts/{id}", payload)

    @mcp.tool()
    async def log_interaction(id: str, note: str) -> dict:
        """Log an interaction with a contact. Appends a note and sets last_contact_at."""
        return await _call_ingestion("POST", f"/contacts/{id}/interaction", {"note": note})

    @mcp.tool()
    async def list_contacts(reach_out_days: int | None = None) -> list[dict]:
        """List contacts. Pass reach_out_days to filter contacts not reached in that many days."""
        path = (
            f"/contacts?{urlencode({'reach_out_days': reach_out_days})}"
            if reach_out_days
            else "/contacts"
        )
        return await _call_ingestion("GET", path)

    # ── Home items ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def add_home_item(
        name: str,
        notes: str | None = None,
        interval_days: int | None = None,
        next_due_at: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Add a home maintenance item (e.g. 'Change air filter', interval_days=90)."""
        payload = {"name": name, "tags": tags or []}
        if notes:
            payload["notes"] = notes
        if interval_days:
            payload["interval_days"] = interval_days
        if next_due_at:
            payload["next_due_at"] = next_due_at
        return await _call_ingestion("POST", "/home", payload)

    @mcp.tool()
    async def update_home_item(
        id: str,
        name: str | None = None,
        notes: str | None = None,
        interval_days: int | None = None,
        next_due_at: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Update a home maintenance item."""
        payload = {k: v for k, v in locals().items() if k != "id" and v is not None}
        return await _call_ingestion("PUT", f"/home/{id}", payload)

    @mcp.tool()
    async def complete_home_item(id: str) -> dict:
        """Mark a home item done. Sets last_done_at=now, advances next_due_at."""
        return await _call_ingestion("POST", f"/home/{id}/complete")

    @mcp.tool()
    async def list_home_items(due_soon_days: int | None = None) -> list[dict]:
        """List home maintenance items. Pass due_soon_days to filter items due within N days."""
        path = f"/home?{urlencode({'due_soon_days': due_soon_days})}" if due_soon_days else "/home"
        return await _call_ingestion("GET", path)

    # ── Dashboard ──────────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_dashboard() -> dict:
        """Get a dashboard summary: overdue/due-soon tasks and home items, stale contacts."""
        return await _call_ingestion("GET", "/dashboard")


async def _call_ingest(
    content: str,
    content_type: str,
    title: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    payload = {
        "content": content,
        "content_type": content_type,
        "source": "mcp",
        "tags": tags or [],
        "metadata": metadata or {},
    }
    if title:
        payload["title"] = title
    return await _call_ingestion("POST", "/ingest", payload)


async def _call_ingestion(method: str, path: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=f"{_ingestion_url}{path}",
            json=payload,
            headers={"X-API-Key": _api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
