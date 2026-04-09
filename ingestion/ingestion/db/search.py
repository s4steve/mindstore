import asyncpg

from ._helpers import _vec


async def cross_table_search(
    pool: asyncpg.Pool,
    embedding: list[float],
    limit: int = 10,
    content_type: str | None = None,
) -> list[dict]:
    """Semantic search across thoughts, tasks, contacts, and home_items."""
    vector_str = _vec(embedding)
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
    return [
        {**dict(r), "created_at": r["created_at"].isoformat(), "similarity": float(r["similarity"])}
        for r in rows
    ]


async def get_all_tags(pool: asyncpg.Pool) -> list[dict]:
    """Return every tag across all tables with usage count."""
    rows = await pool.fetch(
        """
        WITH all_tags AS (
            SELECT unnest(tags) AS tag FROM thoughts WHERE parent_id IS NULL
            UNION ALL
            SELECT unnest(tags) FROM tasks
            UNION ALL
            SELECT unnest(tags) FROM contacts
            UNION ALL
            SELECT unnest(tags) FROM home_items
        )
        SELECT tag, COUNT(*) AS count
        FROM all_tags
        GROUP BY tag
        ORDER BY count DESC, tag ASC
        """
    )
    return [{"tag": r["tag"], "count": r["count"]} for r in rows]


async def get_items_by_tag(pool: asyncpg.Pool, tag: str) -> list[dict]:
    """Return all items across all tables that carry the given tag."""
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, created_at
        FROM thoughts
        WHERE $1 = ANY(tags) AND parent_id IS NULL

        UNION ALL

        SELECT id::text,
               CASE WHEN notes IS NOT NULL THEN title || E'\n' || notes ELSE title END,
               title, tags, 'task'::text, created_at
        FROM tasks
        WHERE $1 = ANY(tags)

        UNION ALL

        SELECT id::text,
               CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
               name, tags, 'contact'::text, created_at
        FROM contacts
        WHERE $1 = ANY(tags)

        UNION ALL

        SELECT id::text,
               CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
               name, tags, 'home_item'::text, created_at
        FROM home_items
        WHERE $1 = ANY(tags)

        ORDER BY created_at DESC
        """,
        tag,
    )
    return [
        {**dict(r), "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


async def get_related_tags(pool: asyncpg.Pool, tag: str, limit: int = 10) -> list[dict]:
    """Return tags that co-occur with the given tag, ranked by frequency."""
    rows = await pool.fetch(
        """
        WITH tagged_items AS (
            SELECT tags FROM thoughts WHERE $1 = ANY(tags) AND parent_id IS NULL
            UNION ALL
            SELECT tags FROM tasks WHERE $1 = ANY(tags)
            UNION ALL
            SELECT tags FROM contacts WHERE $1 = ANY(tags)
            UNION ALL
            SELECT tags FROM home_items WHERE $1 = ANY(tags)
        ),
        co_tags AS (
            SELECT unnest(tags) AS related_tag FROM tagged_items
        )
        SELECT related_tag, COUNT(*) AS co_occurrence
        FROM co_tags
        WHERE related_tag != $1
        GROUP BY related_tag
        ORDER BY co_occurrence DESC, related_tag ASC
        LIMIT $2
        """,
        tag,
        limit,
    )
    return [{"tag": r["related_tag"], "co_occurrence": r["co_occurrence"]} for r in rows]


async def get_suggested_connections(
    pool: asyncpg.Pool, tag: str, limit: int = 8
) -> list[dict]:
    """Find items semantically similar to a tag's centroid but NOT tagged with it."""
    rows = await pool.fetch(
        """
        WITH tag_embeddings AS (
            SELECT embedding FROM thoughts
            WHERE $1 = ANY(tags) AND parent_id IS NULL AND embedding IS NOT NULL
            UNION ALL
            SELECT embedding FROM tasks
            WHERE $1 = ANY(tags) AND embedding IS NOT NULL
            UNION ALL
            SELECT embedding FROM contacts
            WHERE $1 = ANY(tags) AND embedding IS NOT NULL
            UNION ALL
            SELECT embedding FROM home_items
            WHERE $1 = ANY(tags) AND embedding IS NOT NULL
        ),
        centroid AS (
            SELECT AVG(embedding) AS embedding FROM tag_embeddings
        ),
        combined AS (
            SELECT id::text, content, title, tags, content_type, created_at, embedding
            FROM thoughts
            WHERE parent_id IS NULL AND embedding IS NOT NULL AND NOT ($1 = ANY(tags))

            UNION ALL

            SELECT id::text,
                   CASE WHEN notes IS NOT NULL THEN title || E'\n' || notes ELSE title END,
                   title, tags, 'task'::text, created_at, embedding
            FROM tasks
            WHERE embedding IS NOT NULL AND NOT ($1 = ANY(tags))

            UNION ALL

            SELECT id::text,
                   CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
                   name, tags, 'contact'::text, created_at, embedding
            FROM contacts
            WHERE embedding IS NOT NULL AND NOT ($1 = ANY(tags))

            UNION ALL

            SELECT id::text,
                   CASE WHEN notes IS NOT NULL THEN name || E'\n' || notes ELSE name END,
                   name, tags, 'home_item'::text, created_at, embedding
            FROM home_items
            WHERE embedding IS NOT NULL AND NOT ($1 = ANY(tags))
        )
        SELECT c.id, c.content, c.title, c.tags, c.content_type, c.created_at,
               1 - (c.embedding <=> cent.embedding) AS similarity
        FROM combined c, centroid cent
        WHERE cent.embedding IS NOT NULL
        ORDER BY c.embedding <=> cent.embedding
        LIMIT $2
        """,
        tag,
        limit,
    )
    return [
        {**dict(r), "created_at": r["created_at"].isoformat(), "similarity": float(r["similarity"])}
        for r in rows
    ]


async def get_dashboard(pool: asyncpg.Pool) -> dict:
    overdue_tasks = await pool.fetch(
        """
        SELECT id::text, title, notes, status, priority, due_date,
               recurrence_days, category, tags, created_at, updated_at
        FROM tasks
        WHERE status = 'open' AND due_date < CURRENT_DATE
        ORDER BY due_date ASC
        """
    )
    due_soon_tasks = await pool.fetch(
        """
        SELECT id::text, title, notes, status, priority, due_date,
               recurrence_days, category, tags, created_at, updated_at
        FROM tasks
        WHERE status = 'open' AND due_date >= CURRENT_DATE AND due_date <= CURRENT_DATE + 7
        ORDER BY due_date ASC
        """
    )
    overdue_home = await pool.fetch(
        """
        SELECT id::text, name, notes, last_done_at, next_due_at,
               interval_days, tags, created_at, updated_at
        FROM home_items
        WHERE next_due_at < NOW()
        ORDER BY next_due_at ASC
        """
    )
    due_soon_home = await pool.fetch(
        """
        SELECT id::text, name, notes, last_done_at, next_due_at,
               interval_days, tags, created_at, updated_at
        FROM home_items
        WHERE next_due_at >= NOW() AND next_due_at <= NOW() + interval '7 days'
        ORDER BY next_due_at ASC
        """
    )
    contacts_to_reach = await pool.fetch(
        """
        SELECT id::text, name, email, phone, company, last_contact_at,
               notes, tags, created_at, updated_at
        FROM contacts
        WHERE last_contact_at IS NULL OR last_contact_at < NOW() - interval '14 days'
        ORDER BY last_contact_at ASC NULLS FIRST
        """
    )
    return {
        "overdue_tasks":     [dict(r) for r in overdue_tasks],
        "due_soon_tasks":    [dict(r) for r in due_soon_tasks],
        "overdue_home":      [dict(r) for r in overdue_home],
        "due_soon_home":     [dict(r) for r in due_soon_home],
        "contacts_to_reach": [dict(r) for r in contacts_to_reach],
    }
