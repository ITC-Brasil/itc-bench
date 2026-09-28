import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{4})_\d{8}_[a-z0-9_]+\.sql$")


def migrate(database_path: str, migrations_dir: Path = MIGRATIONS_DIR) -> None:
    """Apply pending migrations in order, each one atomically with its version row."""
    # isolation_level=None: no implicit transactions from the sqlite3 module. BEGIN and
    # COMMIT go inside the script, so executescript has no pending transaction to commit.
    conn = sqlite3.connect(database_path, isolation_level=None)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY,"
            " name TEXT NOT NULL,"
            " applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for file in sorted(migrations_dir.glob("*.sql")):
            match = MIGRATION_NAME.match(file.name)
            if not match:
                raise ValueError(f"invalid migration name: {file.name}")
            version = int(match.group(1))
            if version in applied:
                continue
            # version and name are safe to inline: both are constrained by MIGRATION_NAME.
            script = (
                "BEGIN;\n"
                f"{file.read_text(encoding='utf-8')}\n;\n"
                f"INSERT INTO schema_migrations (version, name) VALUES ({version}, '{file.name}');\n"
                "COMMIT;"
            )
            try:
                conn.executescript(script)
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


def check(database_path: str) -> None:
    """Raise sqlite3.Error unless the database exists and has been migrated."""
    # Read-only URI: a missing file is an error instead of a new empty database.
    uri = Path(database_path).absolute().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchall()
    finally:
        conn.close()
