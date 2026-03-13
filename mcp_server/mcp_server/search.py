import asyncpg
from datetime import datetime, timezone


async def semantic_search(
    pool: asyncpg.Pool,
    embedding: list[float],
    limit: int = 10,
    content_type: str | None = None,
) -> list[dict]:
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    rows = await pool.fetch(
        """
        WITH combined AS (
            SELECT
                id::text,
                content,
                title,
                tags,
                content_type,
                created_at,
                1 - (embedding <=> $1::vector) AS similarity
            FROM thoughts
            WHERE parent_id IS NULL AND embedding IS NOT NULL

            UNION ALL

            SELECT
                id::text,
                CASE WHEN notes IS NOT NULL THEN title || E'\n' || notes ELSE title END,
                title,
                tags,
                'task'::text,
                created_at,
                1 - (embedding <=> $1::vector)
            FROM tasks
            WHERE embedding IS NOT NULL

            UNION ALL

            SELECT
                id::text,
                CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
                name,
                tags,
                'contact'::text,
                created_at,
                1 - (embedding <=> $1::vector)
            FROM contacts
            WHERE embedding IS NOT NULL

            UNION ALL

            SELECT
                id::text,
                CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
                name,
                tags,
                'home_item'::text,
                created_at,
                1 - (embedding <=> $1::vector)
            FROM home_items
            WHERE embedding IS NOT NULL
        )
        SELECT id, content, title, tags, content_type, created_at, similarity
        FROM combined
        WHERE ($2::text IS NULL OR content_type = $2)
        ORDER BY similarity DESC
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


async def get_by_date_range(
    pool: asyncpg.Pool,
    start: str,
    end: str,
    content_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, source, created_at
        FROM thoughts
        WHERE created_at >= $1
          AND created_at <= $2
          AND ($3::text IS NULL OR content_type = $3)
          AND parent_id IS NULL
        ORDER BY created_at DESC
        LIMIT $4
        """,
        start_dt,
        end_dt,
        content_type,
        limit,
    )
    return [dict(r) for r in rows]


async def weekly_review(pool: asyncpg.Pool, days: int = 7) -> dict:
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, created_at
        FROM thoughts
        WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
          AND parent_id IS NULL
        ORDER BY created_at DESC
        """,
        days,
    )
    entries = [dict(r) for r in rows]

    by_type: dict[str, int] = {}
    tag_freq: dict[str, int] = {}
    for entry in entries:
        by_type[entry["content_type"]] = by_type.get(entry["content_type"], 0) + 1
        for tag in (entry["tags"] or []):
            tag_freq[tag] = tag_freq.get(tag, 0) + 1
        if entry.get("created_at"):
            entry["created_at"] = entry["created_at"].isoformat()

    top_tags = sorted(tag_freq.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "period_days": days,
        "total": len(entries),
        "by_type": by_type,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "entries": entries,
    }


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
