import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app import db, tokens

TOKEN = re.compile(r"itcta_[A-Za-z0-9_-]{43}")


@pytest.fixture
def cli(settings, capsys):
    """Run the CLI and return (exit code, stdout, stderr)."""

    def run(*argv):
        code = tokens.main([*argv, "--operador", "teste"], settings)
        out, err = capsys.readouterr()
        return code, out, err

    return run


@pytest.fixture
def rows(settings):
    def query(sql, *params):
        conn = sqlite3.connect(settings.database_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    return query


def create(cli, carreta="UM-03"):
    code, out, _ = cli("create", "--carreta", carreta, "--descricao", "pendrive da carreta")
    assert code == 0
    return TOKEN.search(out).group()


def test_create_stores_only_the_hash_and_shows_the_token_once(cli, rows):
    token = create(cli)

    assert rows("SELECT carreta, token_hash, ativo FROM carretas_tokens") == [
        ("UM-03", tokens.hash_token(token), 1)
    ]
    code, out, _ = cli("list")
    assert code == 0
    assert "UM-03" in out
    assert token not in out and tokens.hash_token(token) not in out


def test_carreta_is_normalized(cli, rows):
    create(cli, " um-03 ")
    code, _, _ = cli("create", "--carreta", "UM-03", "--descricao", "x")

    assert code == 1
    assert rows("SELECT carreta FROM carretas_tokens") == [("UM-03",)]


@pytest.mark.parametrize(
    "argv",
    [
        ("revoke", "--carreta", "UM-99", "--motivo", "perdido"),
        ("rotate", "--carreta", "UM-99"),
        ("create", "--carreta", "  ", "--descricao", "x"),
    ],
)
def test_refusals_are_audited(cli, rows, argv):
    code, _, err = cli(*argv)

    assert code == 1
    assert "recusado" in err
    assert rows("SELECT operacao, resultado FROM tokens_auditoria") == [(argv[0], "recusado")]


def test_second_create_is_refused_and_audited(cli, rows):
    create(cli)
    code, _, _ = cli("create", "--carreta", "UM-03", "--descricao", "outro")

    assert code == 1
    assert rows("SELECT count(*) FROM carretas_tokens") == [(1,)]
    assert rows("SELECT operacao, resultado FROM tokens_auditoria ORDER BY id") == [
        ("create", "ok"),
        ("create", "recusado"),
    ]


def test_empty_operator_is_refused_and_audited(settings, rows, capsys):
    code = tokens.main(["list", "--operador", "  "], settings)

    assert code == 1
    assert rows("SELECT operacao, operador, resultado FROM tokens_auditoria") == [("list", "", "recusado")]


def test_usage_error_exits_2_before_the_database(settings, capsys):
    with pytest.raises(SystemExit) as exit_:
        tokens.main(["list"], settings)

    assert exit_.value.code == 2
    assert not Path(settings.database_path).exists()


def test_revoke_deactivates_the_token(cli, rows):
    create(cli)
    code, _, _ = cli("revoke", "--carreta", "UM-03", "--motivo", "pendrive perdido")

    assert code == 0
    assert rows("SELECT ativo, revogado_por, motivo FROM carretas_tokens") == [(0, "teste", "pendrive perdido")]
    assert rows("SELECT token_id, resultado, detalhe FROM tokens_auditoria WHERE operacao = 'revoke'") == [
        (1, "ok", "pendrive perdido")
    ]


def test_rotate_leaves_exactly_one_active_token(cli, rows):
    old = create(cli)
    code, out, _ = cli("rotate", "--carreta", "UM-03")
    new = TOKEN.search(out).group()

    assert code == 0
    assert new != old
    assert rows("SELECT token_hash FROM carretas_tokens WHERE carreta = 'UM-03' AND ativo = 1") == [
        (tokens.hash_token(new),)
    ]
    assert rows("SELECT ativo, motivo FROM carretas_tokens WHERE token_hash = ?", tokens.hash_token(old)) == [
        (0, "rotate")
    ]


def test_failure_in_the_middle_of_rotate_keeps_the_old_token(cli, rows, monkeypatch):
    old = create(cli)
    before = rows("SELECT * FROM carretas_tokens")
    # The new token collides with the old one: the INSERT fails on UNIQUE(token_hash),
    # after the UPDATE that revoked the old token.
    monkeypatch.setattr(tokens.secrets, "token_urlsafe", lambda n: old.removeprefix(tokens.PREFIX))

    code, out, err = cli("rotate", "--carreta", "UM-03")

    assert code == 3
    assert old not in out
    assert rows("SELECT * FROM carretas_tokens") == before
    assert rows("SELECT operacao, resultado FROM tokens_auditoria WHERE resultado = 'falha'") == [("rotate", "falha")]


def test_audit_never_holds_a_token_or_its_hash(cli, rows):
    secrets_seen = [create(cli), create(cli, "UM-04")]
    _, out, _ = cli("rotate", "--carreta", "UM-03")
    secrets_seen.append(TOKEN.search(out).group())
    cli("revoke", "--carreta", "UM-04", "--motivo", "desativada")
    cli("create", "--carreta", "UM-03", "--descricao", "recusado")
    cli("list")
    _, audit_out, _ = cli("auditoria")
    secrets_seen += [tokens.hash_token(token) for token in secrets_seen]

    cells = [str(value) for row in rows("SELECT * FROM tokens_auditoria") for value in row]
    assert len(cells) > 0
    for secret in secrets_seen:
        assert not any(secret in cell for cell in cells)
        assert secret not in audit_out


def test_auditoria_filters_by_carreta_and_audits_itself(cli, rows):
    create(cli)
    create(cli, "UM-04")
    code, out, _ = cli("auditoria", "--carreta", "um-04")

    assert code == 0
    assert "UM-04" in out and "UM-03" not in out
    assert rows("SELECT operacao, carreta FROM tokens_auditoria ORDER BY id DESC LIMIT 1") == [("auditoria", "UM-04")]


def test_writer_waits_for_a_busy_database(settings):
    # Another writer (the API, say) holds the lock for 0.5 s.
    db.migrate(settings.database_path)
    locked = threading.Event()

    def hold():
        conn = db.connect(settings.database_path)
        conn.execute("BEGIN IMMEDIATE")
        locked.set()
        time.sleep(0.5)
        conn.execute("COMMIT")
        conn.close()

    holder = threading.Thread(target=hold)
    holder.start()
    locked.wait()

    start = time.monotonic()
    code = tokens.main(["list", "--operador", "teste"], settings)
    holder.join()

    assert code == 0
    assert time.monotonic() - start >= 0.4


def test_uso_counts_diagnosticos_per_carreta_and_day(cli, rows, settings):
    create(cli)
    conn = db.connect(settings.database_path)
    with db.immediate(conn):
        for hostname, falha, em in [("A", None, "2026-09-28 10:00:00"), ("B", "ia_timeout", "2026-09-28 23:10:00"),
                                     ("A", None, "2026-09-29 08:00:00")]:
            conn.execute(
                "INSERT INTO diagnosticos (carreta, token_id, hostname, sessao_id, versao_schema, dados, resumo,"
                " falha, recebido_em) VALUES ('UM-03', 1, ?, 's', '1.1', '{}', '{}', ?, ?)",
                (hostname, falha, em),
            )
    conn.close()

    code, out, _ = cli("uso", "--carreta", "um-03")

    assert code == 0
    assert out.splitlines() == [
        "carreta\ttoken_id\tdia\tdiagnosticos\thostnames\tfalhas_ia\tprimeiro\tultimo",
        "UM-03\t1\t2026-09-28\t2\t2\t1\t10:00:00\t23:10:00",
        "UM-03\t1\t2026-09-29\t1\t1\t0\t08:00:00\t08:00:00",
    ]
    assert rows("SELECT operacao, carreta FROM tokens_auditoria ORDER BY id DESC LIMIT 1") == [("uso", "UM-03")]
