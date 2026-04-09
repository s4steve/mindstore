import asyncpg

from ._helpers import _vec, _build_set_clause


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
    sets, values, idx = _build_set_clause("home_items", kwargs, embedding)
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
