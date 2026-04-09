import datetime

import asyncpg

from ._helpers import _vec, _build_set_clause


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
    sets, values, idx = _build_set_clause("tasks", kwargs, embedding)
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
            new_due = task["due_date"] + datetime.timedelta(days=task["recurrence_days"])
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
