import os
from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from the DATABASE_URL environment variable,
# which is the same env var the ingestion service uses.
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgresql://"):
    # asyncpg-style URLs use postgresql://, but Alembic needs
    # psycopg2 which also accepts postgresql:// — no change needed.
    pass
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    from sqlalchemy import create_engine

    connectable = create_engine(config.get_main_option("sqlalchemy.url"))
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
