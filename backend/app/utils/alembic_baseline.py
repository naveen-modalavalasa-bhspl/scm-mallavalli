"""
Reconcile alembic's version pointer with the schema that is actually present.

Why this exists
---------------
These databases carry the full application schema, but `alembic_version` can
sit at the wrong place: empty, or stranded mid-chain by a failed deploy.
`alembic upgrade head` then replays history against a schema that is already
current, which cannot succeed. Some revisions move a column to an intermediate
shape a later revision has since replaced -- `m1364a11bc2` rewrites
`items.item_type` to an ENUM, while `r2026_item_types` later makes it a VARCHAR
carrying FK `fk_items_item_type`. Replaying the former fails with MySQL errno
3780. That is a real conflict, not an "already applied" no-op, so the
idempotent-DDL shim in env.py cannot absorb it.

Note also that no revision in this chain creates `users`, `items`, `indents`,
`roles`, `employees` or `positions`. The chain is incremental-only on top of a
pre-existing baseline; building from an empty database was never supported.

The rule
--------
Compare the live schema against the ORM models:

  * pointer already at head       -> nothing to do
  * no application tables         -> fresh database; leave it alone
  * schema has everything the     -> the schema is AHEAD of the pointer. The
    models require, pointer            remaining revisions would replay
    is not at head                     backwards over it. Stamp head.
  * something the models require  -> genuine pending work. Leave the pointer
    is missing                         alone so `alembic upgrade` applies it.

This never blocks a deploy: it either stamps or steps aside. It is called from
alembic/env.py before migrations run, so it needs no entrypoint change.
"""
import logging

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

log = logging.getLogger("alembic.baseline")

# Presence of any of these means the database is already in use.
SENTINEL_TABLES = ("users", "items", "indents")


def _missing_from_db(connection, metadata):
    """Tables/columns the ORM models require that the database lacks."""
    ctx = MigrationContext.configure(connection)
    tables, columns = [], []
    for d in compare_metadata(ctx, metadata):
        if not isinstance(d, tuple):
            continue
        if d[0] == "add_table":
            tables.append(d[1].name)
        elif d[0] == "add_column":
            columns.append(f"{d[2]}.{d[3].name}")
    return sorted(tables), sorted(columns)


def reconcile_version(connection, metadata, head) -> bool:
    """Stamp `head` when the schema is already ahead of the version pointer.

    Returns True if a stamp was written. Never raises for an ordinary
    "there is real work pending" state -- it just steps aside.
    """
    tables = set(inspect(connection).get_table_names())

    current = None
    if "alembic_version" in tables:
        current = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    if current == head:
        log.info("pointer already at head (%s); nothing to do.", head)
        return False

    if not any(t in tables for t in SENTINEL_TABLES):
        log.info("empty database; leaving it for the normal upgrade path.")
        return False

    log.info("pointer at %s, head is %s. Checking whether the schema is "
             "already ahead of it...", current or "<empty>", head)

    missing_tables, missing_columns = _missing_from_db(connection, metadata)
    if missing_tables or missing_columns:
        for t in missing_tables[:20]:
            log.info("    missing table:  %s", t)
        for c in missing_columns[:20]:
            log.info("    missing column: %s", c)
        log.info("genuine pending work - leaving the pointer alone so the "
                 "upgrade can apply it.")
        return False

    log.warning("schema already has every table and column the models require, "
                "so the %s chain would replay backwards over it; stamping %s.",
                "remaining" if current else "whole", head)
    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "version_num VARCHAR(32) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
    connection.execute(text("DELETE FROM alembic_version"))
    connection.execute(text(
        "INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})
    connection.commit()
    log.warning("stamped %s.", head)
    return True
