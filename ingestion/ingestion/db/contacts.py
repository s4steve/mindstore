import datetime

import asyncpg

from ._helpers import _build_set_clause, _vec


async def create_contact(
    pool: asyncpg.Pool, embedding: list[float] | None = None, **kwargs
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO contacts (name, email, phone, company, notes, tags, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
        RETURNING id::text, name, email, phone, company, last_contact_at,
                  notes, tags, created_at, updated_at
        """,
        kwargs["name"],
        kwargs.get("email"),
        kwargs.get("phone"),
        kwargs.get("company"),
        kwargs.get("notes"),
        kwargs.get("tags", []),
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


async def update_contact(
    pool: asyncpg.Pool, id: str, embedding: list[float] | None = None, **kwargs
) -> dict | None:
    sets, values, idx = _build_set_clause("contacts", kwargs, embedding)
    if not sets:
        return await get_contact(pool, id)
    values.append(id)
    row = await pool.fetchrow(
        f"""
        UPDATE contacts SET {", ".join(sets)}
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


async def log_interaction(
    pool: asyncpg.Pool, id: str, note: str, embedding: list[float] | None = None
) -> dict | None:
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
        id,
        timestamp,
        note,
        _vec(embedding),
    )
    return dict(row) if row else None
