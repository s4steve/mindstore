import asyncpg


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
    )


async def insert_thought(
    pool: asyncpg.Pool,
    content: str,
    embedding: list[float],
    source: str,
    content_type: str,
    title: str | None,
    tags: list[str],
    metadata: dict,
    chunk_index: int,
    parent_id: str | None,
) -> str:
    # Format embedding as pgvector literal
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    row = await pool.fetchrow(
        """
        INSERT INTO thoughts
            (content, embedding, source, content_type, title, tags, metadata, chunk_index, parent_id)
        VALUES
            ($1, $2::vector, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id::text
        """,
        content,
        vector_str,
        source,
        content_type,
        title,
        tags,
        metadata,
        chunk_index,
        parent_id,
    )
    return row["id"]


async def get_stats(pool: asyncpg.Pool) -> dict:
    rows = await pool.fetch(
        "SELECT content_type, COUNT(*) AS cnt FROM thoughts GROUP BY content_type"
    )
    by_type = {r["content_type"]: r["cnt"] for r in rows}
    total = sum(by_type.values())

    recent_row = await pool.fetchrow(
        "SELECT created_at FROM thoughts ORDER BY created_at DESC LIMIT 1"
    )
    most_recent = recent_row["created_at"].isoformat() if recent_row else None

    return {"total": total, "by_type": by_type, "most_recent": most_recent}


async def check_connection(pool: asyncpg.Pool) -> bool:
    try:
        await pool.fetchval("SELECT 1")
        return True
    except Exception:
        return False
