import asyncpg


def _vec(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(v) for v in embedding) + "]"


# Allowed columns per table for dynamic UPDATE SET clauses.
# Column names are validated against these sets before being
# interpolated into SQL to prevent injection if the code is refactored.
_ALLOWED_COLUMNS: dict[str, frozenset[str]] = {
    "tasks": frozenset(
        {"title", "notes", "status", "priority", "due_date", "recurrence_days", "category", "tags"}
    ),
    "contacts": frozenset({"name", "email", "phone", "company", "notes", "tags"}),
    "home_items": frozenset({"name", "notes", "interval_days", "next_due_at", "tags"}),
}


def _build_set_clause(
    table: str, kwargs: dict, embedding: list[float] | None = None
) -> tuple[list[str], list, int]:
    """Build parameterised SET clause fragments for an UPDATE statement.

    Returns (set_fragments, values, next_param_index).
    Raises ValueError if a column name is not in the allowlist for the table.
    """
    allowed = _ALLOWED_COLUMNS[table]
    sets: list[str] = []
    values: list = []
    idx = 1
    for col, val in kwargs.items():
        if val is None:
            continue
        if col not in allowed:
            raise ValueError(f"Column {col!r} is not allowed for table {table!r}")
        sets.append(f"{col} = ${idx}")
        values.append(val)
        idx += 1
    if embedding is not None:
        sets.append(f"embedding = ${idx}::vector")
        values.append(_vec(embedding))
        idx += 1
    return sets, values, idx


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
    )


async def check_connection(pool: asyncpg.Pool) -> bool:
    try:
        await pool.fetchval("SELECT 1")
        return True
    except Exception:
        return False
