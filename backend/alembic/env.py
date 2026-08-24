"""
Alembic async environment for BHSPL SCM ERP.

Supports:
- Async MySQL (aiomysql)
- Auto-detect model changes via autogenerate
- Reads DB URL from app config / .env
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import app config to get DATABASE_URL
from app.config import settings

# Import Base and ALL models so metadata is populated
from app.database import Base
import app.models  # noqa: F401 — triggers __init__.py which imports all models


config = context.config

# Override sqlalchemy.url from app settings (so .env is the single source of truth)
# Use pymysql for sync migrations (alembic doesn't use async for DDL)
sync_url = settings.DATABASE_URL.replace("aiomysql", "pymysql")
# Escape % for configparser interpolation
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Idempotent DDL replay
#
# Production DBs here were partly built by earlier, partially-applied migration
# runs. Because MySQL auto-commits DDL but alembic_version only commits at the
# end of the run, a crash mid-upgrade leaves the tables in place while the
# version pointer rolls back to empty -- so the next deploy replays from the
# root revision and dies on "table already exists".
#
# This shim makes CREATE/ALTER/DROP statements idempotent: a DDL step whose
# effect is already present is logged and skipped instead of aborting the run.
# Only DDL is filtered -- INSERT/UPDATE/DELETE/SELECT still raise normally, so
# genuine data errors are never masked.
#
# Set ALEMBIC_STRICT_DDL=1 to disable and get stock alembic behaviour.
# ---------------------------------------------------------------------------

# MySQL error codes that mean "the schema is already in the desired state".
_BENIGN_DDL_ERRNOS = {
    1050,  # table already exists
    1051,  # unknown table (DROP TABLE)
    1054,  # unknown column (DROP/MODIFY COLUMN)
    1060,  # duplicate column name (ADD COLUMN)
    1061,  # duplicate key name (CREATE INDEX)
    1068,  # multiple primary key defined
    1022,  # duplicate key
    1091,  # can't DROP; check that column/key exists
    1826,  # duplicate foreign key constraint name
}

_DDL_VERBS = ("CREATE", "ALTER", "DROP", "RENAME")


def _install_idempotent_ddl():
    """Patch alembic's DDL executor to skip already-satisfied statements."""
    import logging as _logging
    from alembic.ddl.impl import DefaultImpl
    from sqlalchemy.exc import DBAPIError

    log = _logging.getLogger("alembic.idempotent")

    if getattr(DefaultImpl, "_idempotent_patched", False):
        return
    original_exec = DefaultImpl._exec

    def _statement_text(impl, construct):
        try:
            return str(construct.compile(dialect=impl.dialect))
        except Exception:
            return str(construct)

    def _errno(err):
        orig = getattr(err, "orig", None)
        args = getattr(orig, "args", None)
        if args and isinstance(args[0], int):
            return args[0]
        return None

    def _exec(self, construct, *args, **kwargs):
        try:
            return original_exec(self, construct, *args, **kwargs)
        except DBAPIError as err:
            code = _errno(err)
            if code not in _BENIGN_DDL_ERRNOS:
                raise
            sql = " ".join(_statement_text(self, construct).split())
            if not sql.upper().lstrip("( ").startswith(_DDL_VERBS):
                # Not DDL (e.g. a data migration) -- never swallow.
                raise
            log.warning(
                "skipping already-applied DDL (MySQL errno %s): %s", code, sql[:200]
            )
            return None

    DefaultImpl._exec = _exec
    DefaultImpl._idempotent_patched = True
    log.info("idempotent DDL replay enabled (set ALEMBIC_STRICT_DDL=1 to disable)")


def do_run_migrations(connection):
    import os as _os

    if _os.getenv("ALEMBIC_STRICT_DDL", "").strip() not in ("1", "true", "True"):
        _install_idempotent_ddl()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,  # safer for MySQL ALTER operations
        # Commit alembic_version after EACH revision. Without this the whole
        # upgrade is one transaction: a late failure discards the version
        # pointer while MySQL keeps the auto-committed DDL, forcing the next
        # deploy to replay from the root revision.
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"init_command": "SET time_zone='+05:30'"},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — uses sync pymysql driver."""
    from sqlalchemy import engine_from_config
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"init_command": "SET time_zone='+05:30'"},
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
