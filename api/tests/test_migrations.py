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


def test_0006_preserva_dados_ids_e_relatorios(tmp_path):
    """Rebuild of diagnosticos (TA-ADR-028) on a database in the 0005 format with sample data."""
    import shutil
    import sqlite3

    from app import db

    antigas = tmp_path / "antigas"
    antigas.mkdir()
    for arquivo in sorted(db.MIGRATIONS_DIR.glob("*.sql")):
        if int(arquivo.name[:4]) <= 5:
            shutil.copy(arquivo, antigas)
    banco = str(tmp_path / "t.db")
    db.migrate(banco, antigas)
    conn = sqlite3.connect(banco)
    conn.execute("INSERT INTO carretas_tokens (id, carreta, token_hash, criado_por, ativo) VALUES (5, 'UM-03', 'h', 'teste', 1)")
    for i, falha in ((3, None), (8, "ia_timeout")):
        conn.execute(
            "INSERT INTO diagnosticos (id, carreta, token_id, hostname, sessao_id, versao_schema, dados, resumo, falha)"
            " VALUES (?, 'UM-03', 5, 'TESTE-NB-11', 's', '1.1', '{}', '{}', ?)",
            (i, falha),
        )
    conn.execute(
        "INSERT INTO relatorios (diagnostico_id, modelo, duracao_ms, relatorio_md, chamado_titulo, chamado_descricao)"
        " VALUES (3, 'm', 1, 'md', 't', 'd')"
    )
    conn.commit()
    antes = conn.execute("SELECT id, carreta, token_id, hostname, falha, recebido_em FROM diagnosticos ORDER BY id").fetchall()
    conn.close()

    db.migrate(banco)

    conn = sqlite3.connect(banco)
    try:
        depois = conn.execute("SELECT id, carreta, token_id, hostname, falha, recebido_em FROM diagnosticos ORDER BY id").fetchall()
        assert depois == antes
        assert conn.execute("SELECT diagnostico_id FROM relatorios").fetchall() == [(3,)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(diagnosticos)")}
        assert {"bench_usuario", "bench_sessao_id", "unidade", "envio_id", "processando_desde"} <= colunas
        with pytest.raises(sqlite3.IntegrityError):  # nem token nem técnico
            conn.execute(
                "INSERT INTO diagnosticos (carreta, hostname, sessao_id, versao_schema, dados, resumo)"
                " VALUES ('BANCADA', 'X', 's', '1.3', '{}', '{}')"
            )
        assert {r[1] for r in conn.execute("PRAGMA index_list(diagnosticos)")} >= {"diagnosticos_hostname", "diagnosticos_carreta"}
    finally:
        conn.close()
