"""Bench version CLI (ADR-026, TA-ADR-033; runbook in docs/BUILD.md).

    python -m app.bench_versao publicar --arquivo setup.exe --manifesto m.json --assinatura m.sig --operador nome
    python -m app.bench_versao listar --operador nome
    python -m app.bench_versao revogar --versao 0.16.0 --operador nome

The manifest is signed by the owner on their own machine; the API never sees the private key
and does not check the signature (the Bench does, with the public keys in its package). The CLI
checks what it can: format, hash and size of the file against the manifest, version above the
last one published. The file is copied to BENCH_VERSOES_DIR as setup-<sha256>.exe.
Exit codes: 0 ok, 1 refused, 2 argparse usage error, 3 database or file failure.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from app import db
from app.config import Settings

PRODUTO = "itc-bench"
APP_ID = "{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}"
SEMVER = re.compile(r"(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})")
SHA256 = re.compile(r"[0-9a-f]{64}")
TETO = 300 * 1024 * 1024
NOTAS_MAX = 500
CAMPOS = {"produto", "app_id", "versao", "minima", "sha256", "tamanho", "notas", "publicado_em"}
# P-256 signature in IEEE P1363 (r || s), what CNG verifies.
ASSINATURA_BYTES = 64


class Refused(Exception):
    """Operation refused by a rule; the message is shown to the operator."""


def ordem(versao: str) -> int:
    m = SEMVER.fullmatch(versao)
    if not m:
        raise Refused(f"versão fora do formato X.Y.Z: {versao!r}")
    major, minor, patch = (int(p) for p in m.groups())
    return major * 1_000_000 + minor * 1_000 + patch


def ler_manifesto(cru: bytes) -> dict:
    """Same rules as the Bench (servicos/atualizacao.py); the Bench checks the signature first."""
    try:
        dados = json.loads(cru.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise Refused("manifesto não é JSON UTF-8") from erro
    if not isinstance(dados, dict) or set(dados) != CAMPOS:
        raise Refused(f"manifesto precisa ter exatamente os campos {sorted(CAMPOS)}")
    if dados["produto"] != PRODUTO or dados["app_id"] != APP_ID:
        raise Refused("manifesto de outro produto")
    for campo in ("versao", "minima", "sha256", "notas", "publicado_em"):
        if not isinstance(dados[campo], str):
            raise Refused(f"campo {campo} precisa ser texto")
    if ordem(dados["minima"]) > ordem(dados["versao"]):
        raise Refused("minima acima da versão")
    if not SHA256.fullmatch(dados["sha256"]):
        raise Refused("sha256 precisa de 64 caracteres hexadecimais minúsculos")
    tamanho = dados["tamanho"]
    if not isinstance(tamanho, int) or isinstance(tamanho, bool) or not 0 < tamanho <= TETO:
        raise Refused("tamanho fora de 1 byte a 300 MB")
    notas = dados["notas"]
    if len(notas) > NOTAS_MAX or any(ord(c) < 32 and c != "\n" for c in notas):
        raise Refused(f"notas: até {NOTAS_MAX} caracteres, texto puro")
    return dados


def hash_arquivo(caminho: Path) -> tuple[str, int]:
    h, total = hashlib.sha256(), 0
    with caminho.open("rb") as f:
        while bloco := f.read(1024 * 1024):
            h.update(bloco)
            total += len(bloco)
    return h.hexdigest(), total


def publicar(conn, args, settings: Settings) -> str:
    manifesto = Path(args.manifesto).read_bytes()
    assinatura = Path(args.assinatura).read_bytes()
    dados = ler_manifesto(manifesto)
    if len(assinatura) != ASSINATURA_BYTES:
        raise Refused(f"assinatura precisa de {ASSINATURA_BYTES} bytes (P-256, IEEE P1363)")
    sha, tamanho = hash_arquivo(Path(args.arquivo))
    if sha != dados["sha256"] or tamanho != dados["tamanho"]:
        raise Refused("o arquivo não confere com o manifesto (sha256 ou tamanho)")
    nova = ordem(dados["versao"])
    ultima = conn.execute("SELECT max(ordem) FROM bench_versoes").fetchone()[0]
    if ultima is not None and nova <= ultima:
        raise Refused("versão menor ou igual à última publicada (revogada inclusive)")
    pasta = Path(settings.bench_versoes_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"setup-{sha}.exe"
    temporario = destino.with_suffix(".parcial")
    with Path(args.arquivo).open("rb") as origem, temporario.open("wb") as saida:
        while bloco := origem.read(1024 * 1024):
            saida.write(bloco)
    os.replace(temporario, destino)
    conn.execute(
        "INSERT INTO bench_versoes (versao, ordem, minima, sha256, tamanho, notas, manifesto, assinatura, publicado_por)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dados["versao"],
            nova,
            dados["minima"],
            sha,
            tamanho,
            dados["notas"],
            base64.b64encode(manifesto).decode(),
            base64.b64encode(assinatura).decode(),
            args.operador,
        ),
    )
    return f"Versão {dados['versao']} publicada (sha256 {sha[:12]}…, mínima {dados['minima']})."


def listar(conn, args, settings: Settings) -> str:
    rows = conn.execute(
        "SELECT versao, minima, substr(sha256, 1, 12), tamanho, publicado_em, publicado_por, revogado_em, revogado_por"
        " FROM bench_versoes ORDER BY ordem"
    ).fetchall()
    linhas = ["\t".join(["versao", "minima", "sha256", "tamanho", "publicado_em", "por", "revogado_em", "por"])]
    linhas += ["\t".join("" if v is None else str(v) for v in row) for row in rows]
    return "\n".join(linhas)


def revogar(conn, args, settings: Settings) -> str:
    feito = conn.execute(
        "UPDATE bench_versoes SET revogado_em = CURRENT_TIMESTAMP, revogado_por = ?"
        " WHERE versao = ? AND revogado_em IS NULL",
        (args.operador, args.versao),
    ).rowcount
    if not feito:
        raise Refused(f"versão {args.versao} não existe ou já foi revogada")
    return f"Versão {args.versao} revogada. A rota passa a servir a anterior não revogada, se houver."


def parser():
    root = argparse.ArgumentParser(prog="python -m app.bench_versao")
    commands = root.add_subparsers(dest="command", required=True)
    for nome, handler in (("publicar", publicar), ("listar", listar), ("revogar", revogar)):
        sub = commands.add_parser(nome)
        sub.set_defaults(handler=handler)
        sub.add_argument("--operador", required=True)
        if nome == "publicar":
            for campo in ("arquivo", "manifesto", "assinatura"):
                sub.add_argument(f"--{campo}", required=True)
        if nome == "revogar":
            sub.add_argument("--versao", required=True)
    return root


def main(argv=None, settings: Settings | None = None) -> int:
    args = parser().parse_args(argv)
    args.operador = args.operador.strip()
    settings = settings or Settings()
    db.migrate(settings.database_path)
    conn = db.connect(settings.database_path)
    try:
        if not args.operador:
            raise Refused("--operador não pode ser vazio")
        with db.immediate(conn):
            saida = args.handler(conn, args, settings)
        print(saida)
        return 0
    except Refused as recusa:
        print(f"Recusado: {recusa}", file=sys.stderr)
        return 1
    except (sqlite3.Error, OSError) as erro:
        print(f"Falha: {type(erro).__name__}", file=sys.stderr)
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
