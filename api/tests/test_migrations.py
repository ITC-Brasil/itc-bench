import sqlite3

import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    # The real migrations, as the container applies them.
    path = str(tmp_path / "tecnico.db")
    db.migrate(path)
    conn = sqlite3.connect(path, isolation_level=None)
    yield conn
    conn.close()


def insert_token(conn, carreta, token_hash, ativo=1):
    conn.execute(
        "INSERT INTO carretas_tokens (carreta, token_hash, criado_por, ativo) VALUES (?, ?, 'teste', ?)",
        (carreta, token_hash, ativo),
    )


def test_second_active_token_for_same_carreta_is_rejected(conn):
    insert_token(conn, "UM-03", "a")
    with pytest.raises(sqlite3.IntegrityError):
        insert_token(conn, "UM-03", "b")


def test_revoked_tokens_do_not_count_against_the_active_one(conn):
    insert_token(conn, "UM-03", "a", ativo=0)
    insert_token(conn, "UM-03", "b", ativo=0)
    insert_token(conn, "UM-03", "c")
    insert_token(conn, "UM-04", "d")

    assert conn.execute("SELECT count(*) FROM carretas_tokens WHERE ativo = 1").fetchone()[0] == 2


def test_audit_is_append_only(conn):
    conn.execute(
        "INSERT INTO tokens_auditoria (operacao, operador, carreta, resultado) VALUES ('create', 'teste', 'UM-03', 'ok')"
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE tokens_auditoria SET resultado = 'falha'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM tokens_auditoria")

    assert conn.execute("SELECT resultado FROM tokens_auditoria").fetchall() == [("ok",)]


def insert_report(conn, diagnostico_id, confianca="ALTA"):
    conn.execute(
        "INSERT INTO relatorios (diagnostico_id, modelo, duracao_ms, maior_confianca, relatorio_md,"
        " chamado_titulo, chamado_descricao) VALUES (?, 'm', 1, ?, 'r', 't', 'd')",
        (diagnostico_id, confianca),
    )


def test_one_report_per_diagnostico_with_known_confidence(conn):
    conn.execute(
        "INSERT INTO diagnosticos (carreta, token_id, hostname, sessao_id, versao_schema, dados, resumo)"
        " VALUES ('UM-03', 1, 'H', 'S', '1.1', '{}', '{}')"
    )
    insert_report(conn, 1)

    with pytest.raises(sqlite3.IntegrityError):
        insert_report(conn, 1)
    conn.execute("DELETE FROM relatorios")
    with pytest.raises(sqlite3.IntegrityError):
        insert_report(conn, 1, "alta")
    assert conn.execute("SELECT espelho_status FROM relatorios").fetchall() == []
