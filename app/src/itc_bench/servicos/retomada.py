"""Retomada assistida da Preparação completa depois do reinício (ADR-023, item 5), sem Qt.

Nada abre o Bench sozinho: sem Run/RunOnce, tarefa agendada ou serviço. Antes de "Reiniciar
agora" a tela grava `protegido\\preparacao.json` (perfil, etapas desmarcadas, nome pedido, alvos
por SID, horário e contagem de reinícios; sem senha, token, técnico ou nome de conta). Ao abrir,
o técnico entra de novo e escolhe continuar; o motor relê tudo do Windows.

Ao ler: arquivo que é reparse point, com dono ou ACL fora do critério (só SYSTEM e
Administradores), ilegível, de formato desconhecido ou vencido (24 h) é apagado e registrado.
Cada id é validado contra o catálogo e o que não casa é descartado. SIDs nunca vão ao log.
"""

import json
import re
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from itc_bench.nucleo import acl, caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos import identificacao, perfis

FORMATO = 1
NOME = "preparacao.json"
VALIDADE = timedelta(hours=24)
MAX_REINICIOS = 2
SID = re.compile(r"^S-1-5-21-\d+(?:-\d+)+$")
DONOS = ("O:BA", "O:SY")
ACE = re.compile(r"\(([^)]*)\)")


@dataclass(frozen=True)
class Estado:
    perfil: str
    desmarcadas: tuple[str, ...]
    nome: str
    alvos: tuple[str, ...]
    criado_em: str
    reinicios: int

    @property
    def pode_reiniciar(self) -> bool:
        return self.reinicios < MAX_REINICIOS


def arquivo(pasta: Path | None = None) -> Path:
    return (pasta or caminhos.protegida()) / NOME


def acl_ok(caminho: Path) -> bool:
    """Critério do ADR-020: dono Administradores ou SYSTEM; só ACEs de permissão a SY e BA."""
    sddl = acl.sddl_atual(caminho)
    if not sddl.startswith(DONOS):
        return False
    dacl = sddl.split("D:", 1)[1] if "D:" in sddl else ""
    aces = ACE.findall(dacl)
    return bool(aces) and all(a.startswith("A;") and a.split(";")[-1] in ("SY", "BA") for a in aces)


def _apagar(caminho: Path, motivo: str) -> None:
    try:
        caminho.unlink(missing_ok=True)
    except OSError as erro:
        log.error(
            "Retomada: não foi possível apagar o estado (%s): %s", motivo, type(erro).__name__
        )
        return
    log.warning("Retomada: estado apagado: %s", motivo)


def gravar(
    estado: Estado, pasta: Path | None = None, conferir: Callable[[Path], bool] = acl_ok
) -> None:
    destino = arquivo(pasta)
    temp = destino.with_suffix(".tmp")
    temp.write_text(json.dumps({"formato": FORMATO, **asdict(estado)}), "utf-8")
    temp.replace(destino)
    if not conferir(destino):
        _apagar(destino, "acl")
        raise acl.ErroAcl(0, "Estado da preparação com ACL inesperado; nada foi guardado.")
    log.info(
        "Retomada: estado gravado perfil=%s reinicios=%s etapas_fora=%s",
        estado.perfil,
        estado.reinicios,
        ",".join(estado.desmarcadas) or "-",
    )


def novo(
    perfil: str,
    desmarcadas: list[str],
    nome: str,
    alvos: list[str],
    anterior: Estado | None = None,
    agora: datetime | None = None,
) -> Estado:
    agora = agora or datetime.now(UTC)
    return Estado(
        perfil,
        tuple(desmarcadas),
        nome,
        tuple(alvos),
        (anterior.criado_em if anterior else agora.isoformat()),
        (anterior.reinicios if anterior else 0) + 1,
    )


def _validar(cru: object) -> Estado | str:
    if not isinstance(cru, dict) or cru.get("formato") != FORMATO:
        return "formato"
    perfil = cru.get("perfil")
    if perfil not in perfis.POR_ID:
        return "perfil"
    try:
        criado = datetime.fromisoformat(str(cru.get("criado_em")))
        reinicios = int(cru.get("reinicios", 0))
    except (TypeError, ValueError):
        return "formato"
    if criado.tzinfo is None:
        return "formato"
    nome = identificacao.normalizar(str(cru.get("nome") or ""))
    if nome and not identificacao.NOME.fullmatch(nome):
        nome = ""
    desmarcadas = tuple(e for e in cru.get("desmarcadas") or () if e in perfis.ORDEM)
    alvos = tuple(s for s in cru.get("alvos") or () if isinstance(s, str) and SID.fullmatch(s))
    return Estado(str(perfil), desmarcadas, nome, alvos, criado.isoformat(), max(reinicios, 0))


def ler(
    pasta: Path | None = None,
    agora: datetime | None = None,
    conferir: Callable[[Path], bool] = acl_ok,
) -> Estado | None:
    caminho = arquivo(pasta)
    try:
        info = caminho.lstat()
    except FileNotFoundError:
        return None
    except OSError as erro:
        log.error("Retomada: estado ilegível: %s", type(erro).__name__)
        return None
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        _apagar(caminho, "reparse")
        return None
    try:
        if not conferir(caminho):
            _apagar(caminho, "acl")
            return None
        cru = json.loads(caminho.read_text("utf-8"))
    except (OSError, ValueError, acl.ErroAcl) as erro:
        _apagar(caminho, f"ilegivel_{type(erro).__name__}")
        return None
    estado = _validar(cru)
    if isinstance(estado, str):
        _apagar(caminho, estado)
        return None
    agora = agora or datetime.now(UTC)
    if agora - datetime.fromisoformat(estado.criado_em) > VALIDADE:
        _apagar(caminho, "vencido")
        return None
    return estado


def descartar(pasta: Path | None = None) -> None:
    _apagar(arquivo(pasta), "descartado")
