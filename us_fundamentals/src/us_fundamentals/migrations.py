"""Plain-SQL migration runner (ADR-0003).

Migrations are ordered `NNNN_name.up.sql` / `NNNN_name.down.sql` pairs in
`db/migrations/`. Each applies in its own transaction and is recorded in
`schema_migrations`. No ORM, no framework: the schema diff *is* the review
surface.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from us_fundamentals.errors import ConfigurationError

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.(up|down)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up_sql: str
    down_sql: str


def load_migrations(directory: Path = DEFAULT_DIR) -> list[Migration]:
    pairs: dict[tuple[int, str], dict[str, str]] = {}
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            raise ConfigurationError(f"unrecognized migration file name: {path.name}")
        version, name, direction = int(match[1]), match[2], match[3]
        pairs.setdefault((version, name), {})[direction] = path.read_text(
            encoding="utf-8"
        )
    migrations = []
    for (version, name), scripts in sorted(pairs.items()):
        missing = {"up", "down"}.difference(scripts)
        if missing:
            raise ConfigurationError(
                f"migration {version:04d}_{name} is missing: {sorted(missing)}"
            )
        migrations.append(Migration(version, name, scripts["up"], scripts["down"]))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise ConfigurationError("duplicate migration versions")
    return migrations


def _ensure_bookkeeping(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def applied_versions(conn: psycopg.Connection) -> list[int]:
    _ensure_bookkeeping(conn)
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [row[0] for row in rows]


def migrate_up(
    conn: psycopg.Connection,
    directory: Path = DEFAULT_DIR,
    target: int | None = None,
) -> list[int]:
    """Apply pending migrations in order, each in its own transaction."""
    applied = set(applied_versions(conn))
    ran: list[int] = []
    for migration in load_migrations(directory):
        if migration.version in applied:
            continue
        if target is not None and migration.version > target:
            break
        with conn.transaction():
            conn.execute(migration.up_sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (migration.version, migration.name),
            )
        ran.append(migration.version)
    return ran


def migrate_down(
    conn: psycopg.Connection,
    directory: Path = DEFAULT_DIR,
    target: int = 0,
) -> list[int]:
    """Roll back applied migrations above `target`, newest first."""
    applied = set(applied_versions(conn))
    ran: list[int] = []
    for migration in sorted(
        load_migrations(directory), key=lambda m: m.version, reverse=True
    ):
        if migration.version not in applied or migration.version <= target:
            continue
        with conn.transaction():
            conn.execute(migration.down_sql)
            conn.execute(
                "DELETE FROM schema_migrations WHERE version = %s",
                (migration.version,),
            )
        ran.append(migration.version)
    return ran


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["up", "down", "status"])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--to", type=int, default=None)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)

    with psycopg.connect(args.dsn) as conn:
        if args.command == "up":
            ran = migrate_up(conn, args.dir, args.to)
            print(f"applied: {ran or 'nothing'}")
        elif args.command == "down":
            ran = migrate_down(conn, args.dir, args.to if args.to is not None else 0)
            print(f"rolled back: {ran or 'nothing'}")
        else:
            print(f"applied versions: {applied_versions(conn)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
