"""Token CLI for the carretas (PROMPT §6.5, runbook in docs/TOKENS.md).

    python -m app.tokens create --carreta UM-03 --descricao "..." --operador matheus
    python -m app.tokens list --operador matheus
    python -m app.tokens revoke --carreta UM-03 --motivo "..." --operador matheus
    python -m app.tokens rotate --carreta UM-03 --operador matheus
    python -m app.tokens auditoria [--carreta UM-03] --operador matheus

Every run, refused or failed ones included, leaves a row in tokens_auditoria.
Exit codes: 0 ok, 1 refused, 2 failed.
"""

import argparse
import hashlib
import secrets
import sqlite3
import sys

from app import db
from app.config import Settings

PREFIX = "itcta_"


class Refused(Exception):
    """Operation refused by a rule; the message is shown to the operator."""


def generate() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def audit(conn, operacao, operador, carreta, resultado, token_id=None, detalhe=None):
    # Only the row id and the carreta: never the token nor its hash.
    conn.execute(
        "INSERT INTO tokens_auditoria (operacao, operador, carreta, token_id, resultado, detalhe)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (operacao, operador, carreta, token_id, resultado, detalhe),
    )


def active_id(conn, carreta):
    row = conn.execute(
        "SELECT id FROM carretas_tokens WHERE carreta = ? AND ativo = 1", (carreta,)
    ).fetchone()
    return row[0] if row else None


def insert_token(conn, carreta, descricao, operador):
    token = generate()
    cursor = conn.execute(
        "INSERT INTO carretas_tokens (carreta, token_hash, descricao, criado_por) VALUES (?, ?, ?, ?)",
        (carreta, hash_token(token), descricao, operador),
    )
    return token, cursor.lastrowid


def revoke_row(conn, token_id, operador, motivo):
    conn.execute(
        "UPDATE carretas_tokens SET ativo = 0, revogado_em = CURRENT_TIMESTAMP,"
        " revogado_por = ?, motivo = ? WHERE id = ?",
        (operador, motivo, token_id),
    )


def create(conn, args):
    if active_id(conn, args.carreta) is not None:
        raise Refused(f"a carreta {args.carreta} já tem token ativo; use rotate")
    token, token_id = insert_token(conn, args.carreta, args.descricao, args.operador)
    audit(conn, "create", args.operador, args.carreta, "ok", token_id)
    return token_text(args.carreta, token_id, token)


def revoke(conn, args):
    token_id = active_id(conn, args.carreta)
    if token_id is None:
        raise Refused(f"a carreta {args.carreta} não tem token ativo")
    revoke_row(conn, token_id, args.operador, args.motivo)
    audit(conn, "revoke", args.operador, args.carreta, "ok", token_id, args.motivo)
    return f"Token {token_id} da carreta {args.carreta} revogado. Vale a partir da próxima requisição."


def rotate(conn, args):
    old_id = active_id(conn, args.carreta)
    if old_id is None:
        raise Refused(f"a carreta {args.carreta} não tem token ativo; use create")
    descricao = conn.execute("SELECT descricao FROM carretas_tokens WHERE id = ?", (old_id,)).fetchone()[0]
    # Revoke before insert: the partial unique index is checked per statement.
    revoke_row(conn, old_id, args.operador, "rotate")
    token, new_id = insert_token(conn, args.carreta, descricao, args.operador)
    audit(conn, "rotate", args.operador, args.carreta, "ok", new_id, f"substitui o token {old_id}")
    return token_text(args.carreta, new_id, token) + f"\nO token {old_id} foi revogado no mesmo passo."


def list_tokens(conn, args):
    rows = conn.execute(
        "SELECT id, carreta, ativo, descricao, criado_em, criado_por, ultimo_uso, revogado_em, motivo"
        " FROM carretas_tokens ORDER BY carreta, id"
    ).fetchall()
    audit(conn, "list", args.operador, None, "ok")
    return table(["id", "carreta", "ativo", "descricao", "criado_em", "criado_por", "ultimo_uso", "revogado_em", "motivo"], rows)


def show_audit(conn, args):
    rows = conn.execute(
        "SELECT id, em, operacao, operador, carreta, token_id, resultado, detalhe FROM tokens_auditoria"
        " WHERE ? IS NULL OR carreta = ? ORDER BY id",
        (args.carreta, args.carreta),
    ).fetchall()
    audit(conn, "auditoria", args.operador, args.carreta, "ok")
    return table(["id", "em", "operacao", "operador", "carreta", "token_id", "resultado", "detalhe"], rows)


def token_text(carreta, token_id, token):
    return (
        f"Token da carreta {carreta} (id {token_id}):\n\n{token}\n\n"
        "Guarde agora no Vaultwarden. Ele não será mostrado de novo."
    )


def table(headers, rows):
    lines = ["\t".join(headers)]
    lines += ["\t".join("" if value is None else str(value) for value in row) for row in rows]
    return "\n".join(lines)


def carreta(value: str) -> str:
    # Normalized so "um-03" and "UM-03" cannot hold two active tokens.
    return value.strip().upper()


def parser():
    root = argparse.ArgumentParser(prog="python -m app.tokens")
    commands = root.add_subparsers(dest="command", required=True)
    specs = {
        "create": (create, ["carreta", "descricao"]),
        "list": (list_tokens, []),
        "revoke": (revoke, ["carreta", "motivo"]),
        "rotate": (rotate, ["carreta"]),
        "auditoria": (show_audit, []),
    }
    for name, (handler, required) in specs.items():
        sub = commands.add_parser(name)
        sub.set_defaults(handler=handler)
        sub.add_argument("--operador", required=True, help="quem executa, gravado na auditoria")
        if "carreta" in required:
            sub.add_argument("--carreta", required=True, type=carreta)
        if name == "auditoria":
            sub.add_argument("--carreta", type=carreta)
        for field in ("descricao", "motivo"):
            if field in required:
                sub.add_argument(f"--{field}", required=True)
    return root


def main(argv=None, settings: Settings | None = None) -> int:
    args = parser().parse_args(argv)
    args.operador = args.operador.strip()
    carreta_arg = getattr(args, "carreta", None)
    settings = settings or Settings()
    db.migrate(settings.database_path)
    conn = db.connect(settings.database_path)
    try:
        try:
            if not args.operador:
                raise Refused("--operador não pode ser vazio")
            if carreta_arg == "":
                raise Refused("--carreta não pode ser vazia")
            with db.immediate(conn):
                output = args.handler(conn, args)
            # Printed only after COMMIT: a token on screen is always a token in the database.
            print(output)
            return 0
        except Refused as refusal:
            result, detail, code = "recusado", str(refusal), 1
        except sqlite3.Error as error:
            # SQLite messages name tables and constraints, never values.
            result, detail, code = "falha", f"{type(error).__name__}: {error}", 2
        # After the rollback, in autocommit: the operation is undone, its audit row stays.
        audit(conn, args.command, args.operador, carreta_arg, result, detalhe=detail)
        print(f"{result}: {detail}", file=sys.stderr)
        return code
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
