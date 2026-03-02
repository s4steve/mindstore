import httpx
from mcp.server.fastmcp import FastMCP

from embedder import SentenceTransformerEmbedder
from . import search as search_module

# These are set by main.py before registering tools
_ingestion_url: str = ""
_api_key: str = ""
_embedder: SentenceTransformerEmbedder | None = None
_pool = None


def register_tools(mcp: FastMCP, ingestion_url: str, api_key: str, embedder, pool) -> None:
    global _ingestion_url, _api_key, _embedder, _pool
    _ingestion_url = ingestion_url
    _api_key = api_key
    _embedder = embedder
    _pool = pool

    @mcp.tool()
    async def add_thought(content: str, tags: list[str] = []) -> dict:
        """Capture a quick thought or idea."""
        return await _call_ingest(
            content=content,
            content_type="thought",
            tags=tags,
        )

    @mcp.tool()
    async def add_note(title: str, content: str, tags: list[str] = []) -> dict:
        """Store a structured note with a title."""
        return await _call_ingest(
            content=content,
            content_type="note",
            title=title,
            tags=tags,
        )

    @mcp.tool()
    async def add_event(description: str, tags: list[str] = [], metadata: dict = {}) -> dict:
        """Log something that happened."""
        return await _call_ingest(
            content=description,
            content_type="event",
            tags=tags,
            metadata=metadata,
        )

    @mcp.tool()
    async def search_thoughts(query: str, limit: int = 10, content_type: str | None = None) -> list[dict]:
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
