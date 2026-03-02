import asyncpg


async def semantic_search(
    pool: asyncpg.Pool,
    embedding: list[float],
    limit: int = 10,
    content_type: str | None = None,
) -> list[dict]:
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    rows = await pool.fetch(
        """
        SELECT
            id::text,
            content,
            title,
            tags,
            content_type,
            source,
            created_at,
            1 - (embedding <=> $1::vector) AS similarity
        FROM thoughts
        WHERE ($2::text IS NULL OR content_type = $2)
          AND parent_id IS NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        vector_str,
        content_type,
        limit,
    )
    return [dict(r) for r in rows]


async def get_recent(
    pool: asyncpg.Pool,
    limit: int = 10,
    content_type: str | None = None,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, source, created_at
        FROM thoughts
        WHERE ($1::text IS NULL OR content_type = $1)
          AND parent_id IS NULL
        ORDER BY created_at DESC
        LIMIT $2
        """,
        content_type,
        limit,
    )
    return [dict(r) for r in rows]


async def get_by_tag(
    pool: asyncpg.Pool,
    tags: list[str],
    limit: int = 20,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, source, created_at
        FROM thoughts
        WHERE tags && $1::text[]
          AND parent_id IS NULL
        ORDER BY created_at DESC
        LIMIT $2
        """,
        tags,
        limit,
    )
    return [dict(r) for r in rows]


async def get_stats(pool: asyncpg.Pool) -> dict:
    type_rows = await pool.fetch(
        "SELECT content_type, COUNT(*) AS cnt FROM thoughts GROUP BY content_type"
    )
    by_type = {r["content_type"]: r["cnt"] for r in type_rows}
    total = sum(by_type.values())

    range_row = await pool.fetchrow(
        "SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM thoughts"
    )
    return {
        "total": total,
        "by_type": by_type,
        "oldest": range_row["oldest"].isoformat() if range_row["oldest"] else None,
        "newest": range_row["newest"].isoformat() if range_row["newest"] else None,
    }
