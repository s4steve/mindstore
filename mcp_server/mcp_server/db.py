import asyncpg


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
