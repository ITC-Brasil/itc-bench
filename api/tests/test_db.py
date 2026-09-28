import sqlite3

import pytest

from app import db


def versions(path):
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    finally:
        conn.close()


def tables(path):
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def test_applies_pending_migrations_in_order_once(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0002_20260928_b.sql").write_text("CREATE TABLE b (id INTEGER REFERENCES a(id));")
    (migrations / "0001_20260928_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);")
    database = str(tmp_path / "t.db")

    db.migrate(database, migrations)
    db.migrate(database, migrations)

    assert versions(database) == [1, 2]
    assert {"a", "b"} <= tables(database)


def test_failed_migration_leaves_nothing_applied(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_20260928_ok.sql").write_text("CREATE TABLE ok (id INTEGER);")
    # The first statement succeeds, the second fails.
    (migrations / "0002_20260928_broken.sql").write_text(
        "CREATE TABLE partial (id INTEGER);\nINSERT INTO missing VALUES (1);"
    )
    database = str(tmp_path / "t.db")

    with pytest.raises(sqlite3.OperationalError):
        db.migrate(database, migrations)

    assert versions(database) == [1]
    assert "partial" not in tables(database)
    assert "ok" in tables(database)


def test_invalid_migration_name_is_refused(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "1_sem_data.sql").write_text("SELECT 1;")

    with pytest.raises(ValueError):
        db.migrate(str(tmp_path / "t.db"), migrations)
