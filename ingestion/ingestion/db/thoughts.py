import json

import asyncpg


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
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    row = await pool.fetchrow(
        """
        INSERT INTO thoughts
            (content, embedding, source, content_type, title,
             tags, metadata, chunk_index, parent_id)
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
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]


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
