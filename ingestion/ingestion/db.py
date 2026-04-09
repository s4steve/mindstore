import json
import asyncpg


def _vec(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(v) for v in embedding) + "]"


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
        json.dumps(metadata),
        chunk_index,
        parent_id,
    )
    return row["id"]


async def delete_thought(pool: asyncpg.Pool, id: str) -> bool:
    """Delete a thought and all its chunks (CASCADE handles children)."""
    result = await pool.execute(
        "DELETE FROM thoughts WHERE id = $1::uuid AND parent_id IS NULL",
        id,
    )
    return result == "DELETE 1"


async def update_thought(
    pool: asyncpg.Pool,
    id: str,
    content: str | None = None,
    embedding: list[float] | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> bool:
    sets: list[str] = []
    values: list = []
    idx = 1

    if content is not None:
        sets.append(f"content = ${idx}")
        values.append(content)
        idx += 1
    if embedding is not None:
        vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
        sets.append(f"embedding = ${idx}::vector")
        values.append(vector_str)
        idx += 1
    if title is not None:
        sets.append(f"title = ${idx}")
        values.append(title)
        idx += 1
    if tags is not None:
        sets.append(f"tags = ${idx}")
        values.append(tags)
        idx += 1
    if metadata is not None:
        sets.append(f"metadata = ${idx}")
        values.append(json.dumps(metadata))
        idx += 1

    if not sets:
        return False

    values.append(id)
    result = await pool.execute(
        f"UPDATE thoughts SET {', '.join(sets)} WHERE id = ${idx}::uuid",
        *values,
    )
    return result == "UPDATE 1"


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
    return [
        {**dict(r), "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


async def get_thought_full(pool: asyncpg.Pool, id: str) -> dict | None:
    """Return a thought with all its chunks' content concatenated in order."""
    rows = await pool.fetch(
        """
        SELECT id::text, content, title, tags, content_type, created_at, chunk_index
        FROM thoughts
        WHERE id = $1::uuid OR parent_id = $1::uuid
        ORDER BY chunk_index ASC
        """,
        id,
    )
    if not rows:
        return None
    first = dict(rows[0])
    return {
        "id": first["id"],
        "content": "\n\n".join(r["content"] for r in rows),
        "title": first["title"],
        "tags": first["tags"],
        "content_type": first["content_type"],
        "created_at": first["created_at"].isoformat(),
        "total_chunks": len(rows),
    }


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
    return [
        {**dict(r), "created_at": r["created_at"].isoformat(), "similarity": float(r["similarity"])}
        for r in rows
    ]


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


# ── Task helpers ──────────────────────────────────────────────────────────────

def _row_to_task(r) -> dict:
    d = dict(r)
    d["id"] = str(d["id"])
    return d


async def create_task(pool: asyncpg.Pool, embedding: list[float] | None = None, **kwargs) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO tasks (title, notes, status, priority, due_date, recurrence_days, category, tags, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector)
        RETURNING id::text, title, notes, status, priority, due_date,
                  recurrence_days, category, tags, created_at, updated_at
        """,
        kwargs["title"], kwargs.get("notes"), kwargs.get("status", "open"),
        kwargs.get("priority", "medium"), kwargs.get("due_date"),
        kwargs.get("recurrence_days"), kwargs.get("category", "general"),
        kwargs.get("tags", []), _vec(embedding),
    )
    return dict(row)


async def list_tasks(
    pool: asyncpg.Pool,
    status: str | None = None,
    category: str | None = None,
    due_soon_days: int | None = None,
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id::text, title, notes, status, priority, due_date,
               recurrence_days, category, tags, created_at, updated_at
        FROM tasks
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR category = $2)
          AND ($3::int IS NULL OR (due_date IS NOT NULL AND due_date <= CURRENT_DATE + $3))
        ORDER BY
            CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            due_date ASC NULLS LAST,
            created_at DESC
        """,
        status, category, due_soon_days,
    )
    return [dict(r) for r in rows]


async def get_task(pool: asyncpg.Pool, id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id::text, title, notes, status, priority, due_date,
               recurrence_days, category, tags, created_at, updated_at
        FROM tasks WHERE id = $1::uuid
        """,
        id,
    )
    return dict(row) if row else None


async def update_task(pool: asyncpg.Pool, id: str, embedding: list[float] | None = None, **kwargs) -> dict | None:
    sets, values, idx = [], [], 1
    for col in ("title", "notes", "status", "priority", "due_date", "recurrence_days", "category", "tags"):
        if col in kwargs and kwargs[col] is not None:
            sets.append(f"{col} = ${idx}")
            values.append(kwargs[col])
            idx += 1
    if embedding is not None:
        sets.append(f"embedding = ${idx}::vector")
        values.append(_vec(embedding))
        idx += 1
    if not sets:
        return await get_task(pool, id)
    values.append(id)
    row = await pool.fetchrow(
        f"""
        UPDATE tasks SET {', '.join(sets)}
        WHERE id = ${idx}::uuid
        RETURNING id::text, title, notes, status, priority, due_date,
                  recurrence_days, category, tags, created_at, updated_at
        """,
        *values,
    )
    return dict(row) if row else None


async def delete_task(pool: asyncpg.Pool, id: str) -> bool:
    result = await pool.execute("DELETE FROM tasks WHERE id = $1::uuid", id)
    return result == "DELETE 1"


async def complete_task(pool: asyncpg.Pool, id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tasks SET status = 'done'
            WHERE id = $1::uuid
            RETURNING id::text, title, notes, status, priority, due_date,
                      recurrence_days, category, tags, created_at, updated_at
            """,
            id,
        )
        if not row:
            return None
        task = dict(row)
        if task.get("recurrence_days") and task.get("due_date"):
            import datetime
            new_due = task["due_date"] + datetime.timedelta(days=task["recurrence_days"])
            # Fetch the embedding to carry it forward
            emb_row = await conn.fetchrow("SELECT embedding::text FROM tasks WHERE id = $1::uuid", id)
            await conn.execute(
                """
                INSERT INTO tasks (title, notes, status, priority, due_date, recurrence_days, category, tags, embedding)
                VALUES ($1, $2, 'open', $3, $4, $5, $6, $7, $8::vector)
                """,
                task["title"], task["notes"], task["priority"],
                new_due, task["recurrence_days"], task["category"], task["tags"],
                emb_row["embedding"] if emb_row else None,
            )
        return task


# ── Contact helpers ───────────────────────────────────────────────────────────

async def create_contact(pool: asyncpg.Pool, embedding: list[float] | None = None, **kwargs) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO contacts (name, email, phone, company, notes, tags, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
        RETURNING id::text, name, email, phone, company, last_contact_at,
                  notes, tags, created_at, updated_at
        """,
        kwargs["name"], kwargs.get("email"), kwargs.get("phone"),
        kwargs.get("company"), kwargs.get("notes"), kwargs.get("tags", []),
        _vec(embedding),
    )
    return dict(row)


async def list_contacts(pool: asyncpg.Pool, reach_out_days: int | None = None) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id::text, name, email, phone, company, last_contact_at,
               notes, tags, created_at, updated_at
        FROM contacts
        WHERE ($1::int IS NULL
               OR last_contact_at IS NULL
               OR last_contact_at < NOW() - ($1 || ' days')::interval)
        ORDER BY last_contact_at ASC NULLS FIRST, name ASC
        """,
        reach_out_days,
    )
    return [dict(r) for r in rows]


async def get_contact(pool: asyncpg.Pool, id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id::text, name, email, phone, company, last_contact_at,
               notes, tags, created_at, updated_at
        FROM contacts WHERE id = $1::uuid
        """,
        id,
    )
    return dict(row) if row else None


async def update_contact(pool: asyncpg.Pool, id: str, embedding: list[float] | None = None, **kwargs) -> dict | None:
    sets, values, idx = [], [], 1
    for col in ("name", "email", "phone", "company", "notes", "tags"):
        if col in kwargs and kwargs[col] is not None:
            sets.append(f"{col} = ${idx}")
            values.append(kwargs[col])
            idx += 1
    if embedding is not None:
        sets.append(f"embedding = ${idx}::vector")
        values.append(_vec(embedding))
        idx += 1
    if not sets:
        return await get_contact(pool, id)
    values.append(id)
    row = await pool.fetchrow(
        f"""
        UPDATE contacts SET {', '.join(sets)}
        WHERE id = ${idx}::uuid
        RETURNING id::text, name, email, phone, company, last_contact_at,
                  notes, tags, created_at, updated_at
        """,
        *values,
    )
    return dict(row) if row else None


async def delete_contact(pool: asyncpg.Pool, id: str) -> bool:
    result = await pool.execute("DELETE FROM contacts WHERE id = $1::uuid", id)
    return result == "DELETE 1"


async def log_interaction(pool: asyncpg.Pool, id: str, note: str, embedding: list[float] | None = None) -> dict | None:
    import datetime
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    row = await pool.fetchrow(
        """
        UPDATE contacts
        SET last_contact_at = NOW(),
            notes = CASE
                WHEN notes IS NULL OR notes = '' THEN $2 || ': ' || $3
                ELSE notes || E'\n\n' || $2 || ': ' || $3
            END,
            embedding = COALESCE($4::vector, embedding)
        WHERE id = $1::uuid
        RETURNING id::text, name, email, phone, company, last_contact_at,
                  notes, tags, created_at, updated_at
        """,
        id, timestamp, note, _vec(embedding),
    )
    return dict(row) if row else None


# ── Home item helpers ─────────────────────────────────────────────────────────

async def create_home_item(pool: asyncpg.Pool, embedding: list[float] | None = None, **kwargs) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO home_items (name, notes, interval_days, next_due_at, tags, embedding)
        VALUES ($1, $2, $3, $4, $5, $6::vector)
        RETURNING id::text, name, notes, last_done_at, next_due_at,
                  interval_days, tags, created_at, updated_at
        """,
        kwargs["name"], kwargs.get("notes"), kwargs.get("interval_days"),
        kwargs.get("next_due_at"), kwargs.get("tags", []), _vec(embedding),
    )
    return dict(row)


async def list_home_items(pool: asyncpg.Pool, due_soon_days: int | None = None) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id::text, name, notes, last_done_at, next_due_at,
               interval_days, tags, created_at, updated_at
        FROM home_items
        WHERE ($1::int IS NULL OR (next_due_at IS NOT NULL AND next_due_at <= NOW() + ($1 || ' days')::interval))
        ORDER BY next_due_at ASC NULLS LAST, name ASC
        """,
        due_soon_days,
    )
    return [dict(r) for r in rows]


async def get_home_item(pool: asyncpg.Pool, id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id::text, name, notes, last_done_at, next_due_at,
               interval_days, tags, created_at, updated_at
        FROM home_items WHERE id = $1::uuid
        """,
        id,
    )
    return dict(row) if row else None


async def update_home_item(pool: asyncpg.Pool, id: str, embedding: list[float] | None = None, **kwargs) -> dict | None:
    sets, values, idx = [], [], 1
    for col in ("name", "notes", "interval_days", "next_due_at", "tags"):
        if col in kwargs and kwargs[col] is not None:
            sets.append(f"{col} = ${idx}")
            values.append(kwargs[col])
            idx += 1
    if embedding is not None:
        sets.append(f"embedding = ${idx}::vector")
        values.append(_vec(embedding))
        idx += 1
    if not sets:
        return await get_home_item(pool, id)
    values.append(id)
    row = await pool.fetchrow(
        f"""
        UPDATE home_items SET {', '.join(sets)}
        WHERE id = ${idx}::uuid
        RETURNING id::text, name, notes, last_done_at, next_due_at,
                  interval_days, tags, created_at, updated_at
        """,
        *values,
    )
    return dict(row) if row else None


async def delete_home_item(pool: asyncpg.Pool, id: str) -> bool:
    result = await pool.execute("DELETE FROM home_items WHERE id = $1::uuid", id)
    return result == "DELETE 1"


async def complete_home_item(pool: asyncpg.Pool, id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE home_items
        SET last_done_at = NOW(),
            next_due_at  = CASE
                WHEN interval_days IS NOT NULL THEN NOW() + (interval_days || ' days')::interval
                ELSE next_due_at
            END
        WHERE id = $1::uuid
        RETURNING id::text, name, notes, last_done_at, next_due_at,
                  interval_days, tags, created_at, updated_at
        """,
        id,
    )
    return dict(row) if row else None


# ── Cross-table semantic search ───────────────────────────────────────────────

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


# ── Dashboard ─────────────────────────────────────────────────────────────────

# ── Wiki / tag helpers ────────────────────────────────────────────────────────

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
