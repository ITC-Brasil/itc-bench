import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{4})_\d{8}_[a-z0-9_]+\.sql$")
LEADING_COMMENTS = re.compile(r"^\s*(?:(?:--[^\n]*(?:\n|$)|/\*.*?\*/)\s*)*", re.S)
TRANSACTION_CONTROL = re.compile(r"(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", re.I)
# The API and the token CLI write to the same file: a writer waits for the lock this long
# instead of failing at once with "database is locked".
BUSY_TIMEOUT_SECONDS = 5.0


def connect(database_path: str) -> sqlite3.Connection:
    """Autocommit connection with busy timeout; write through immediate()."""
    # timeout= is sqlite3_busy_timeout. isolation_level=None: no implicit transactions.
    return sqlite3.connect(database_path, isolation_level=None, timeout=BUSY_TIMEOUT_SECONDS)


@contextmanager
def immediate(conn: sqlite3.Connection):
    """Write transaction that takes the lock up front, so the busy timeout applies.

    A deferred transaction that upgrades from read to write gets SQLITE_BUSY at once,
    without waiting; BEGIN IMMEDIATE waits on the busy handler instead.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def statements(sql: str):
    """Split a script into statements; complete_statement keeps quoted ';' and triggers whole."""
    buffer = ""
    for piece in sql.split(";"):
        buffer += piece + ";"
        if sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    if buffer.strip(" \t\r\n;"):
        yield buffer


def reject_transaction_control(name: str, sql: str) -> None:
    # The runner owns the transaction: a COMMIT inside the file would make it non-atomic.
    for statement in statements(sql):
        if TRANSACTION_CONTROL.match(LEADING_COMMENTS.sub("", statement, count=1)):
            raise ValueError(f"transaction control is not allowed in migrations: {name}")


def migrate(database_path: str, migrations_dir: Path = MIGRATIONS_DIR) -> None:
    """Apply pending migrations in order, each one atomically with its version row."""
    # No implicit transactions (connect): BEGIN and COMMIT go inside the script, so
    # executescript has no pending transaction to commit.
    conn = connect(database_path)
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
            sql = file.read_text(encoding="utf-8")
            reject_transaction_control(file.name, sql)
            # version and name are safe to inline: both are constrained by MIGRATION_NAME.
            script = (
                "BEGIN;\n"
                f"{sql}\n;\n"
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
