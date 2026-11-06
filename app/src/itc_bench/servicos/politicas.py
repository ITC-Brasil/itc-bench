"""Políticas e USB (ADR-021), sem Qt: as telas Políticas e USB e a Preparação completa (13) usam.

O catálogo é fechado aqui; o 13 escolhe só por id. Leitura e escrita pelos trechos de
`recursos/politicas/` no executor, sempre na vista de 64 bits. Este módulo nunca abre o registro
(sem `winreg`): o hive temporário `HKU\\ITCBench_*` só é tocado pelo trecho. Log sem nome de conta,
SID, caminho de perfil nem nome do hive temporário.
"""

import os
import struct  # noqa: F401  (os testes trocam struct.calcsize por aqui)
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, hive
from itc_bench.servicos.hive import (
    MAQUINA,
    MENSAGENS,
    PADRAO,
    TENTATIVAS_DESCARREGAR,
    Acao,
    Alvo,
    Escopo,
    Feito,
    Rodar,
    alvos,
    recusa_alvo,
    script,
    sids_protegidos,
)

__all__ = [
    "MAQUINA",
    "MENSAGENS",
    "PADRAO",
    "TENTATIVAS_DESCARREGAR",
    "Acao",
    "Alvo",
    "Escopo",
    "Feito",
    "alvos",
    "recusa_alvo",
    "script",
    "sids_protegidos",
]

Estado = Literal["aplicada", "nao_aplicada", "diferente", "nao_lida", "sem_acesso"]

RAIZES: dict[Escopo, tuple[str, ...]] = {
    "usuario": ("software\\policies\\", "software\\microsoft\\windows\\currentversion\\policies\\"),
    "maquina": ("software\\policies\\",),
}
EXATAS_MAQUINA = frozenset({"system\\currentcontrolset\\services\\sharedaccess"})

# Sobras do Configurador: só estes dois nomes, sem curinga (ADR-021, item 9).
SOBRAS_NOMES = ("itc_security_check.bat", "itc_security_check.ps1")

ESTADO_ROTULO: dict[Estado, str] = {
    "aplicada": "aplicada",
    "nao_aplicada": "não aplicada",
    "diferente": "diferente",
    "nao_lida": "não lida",
    "sem_acesso": "sem acesso",
}
AVISO_EDICAO = "efeito não confirmado nesta edição"


# ---------------------------------------------------------------- catálogo


@dataclass(frozen=True)
class Valor:
    chave: str  # relativa à raiz do hive
    nome: str
    tipo: Literal["dword", "sz"]
    dado: int | str
    desfazer: int | str | None = None  # None = apagar (padrão do Windows)
    legado: bool = False  # só reconhecido e apagado se o dado for igual; nunca gravado
    lista: str | None = None  # apagar só se esta chave ficar sem valores


@dataclass(frozen=True)
class Politica:
    id: str
    nome: str
    descricao: str
    grupo: str
    escopos: frozenset[Escopo]
    valores: tuple[Valor, ...]
    sem_confirmar: frozenset[str] = field(default_factory=frozenset)  # "home", "pro"


_U: frozenset[Escopo] = frozenset({"usuario"})
_M: frozenset[Escopo] = frozenset({"maquina"})
_UM: frozenset[Escopo] = frozenset({"usuario", "maquina"})
_EXP = "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer"
_SIS = "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System"

CATALOGO: tuple[Politica, ...] = (
    Politica(
        "cmd",
        "Bloquear Prompt de Comando",
        "O cmd.exe não abre; arquivos .bat de outros programas continuam rodando.",
        "Sistema",
        _U,
        (Valor("Software\\Policies\\Microsoft\\Windows\\System", "DisableCMD", "dword", 2),),
    ),
    Politica(
        "regedit",
        "Bloquear Editor do Registro",
        "O regedit não abre para a conta.",
        "Sistema",
        _U,
        (Valor(_SIS, "DisableRegistryTools", "dword", 1),),
    ),
    Politica(
        "painel",
        "Bloquear Painel de Controle e Configurações",
        "Painel de Controle e o app Configurações não abrem.",
        "Sistema",
        _U,
        (Valor(_EXP, "NoControlPanel", "dword", 1),),
    ),
    Politica(
        "programas",
        "Bloquear Programas e Recursos",
        "Esconde o painel antigo de desinstalar; Configurações › Aplicativos não é coberto.",
        "Sistema",
        _U,
        (
            Valor(
                "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Uninstall",
                "NoAddRemovePrograms",
                "dword",
                1,
            ),
        ),
    ),
    Politica(
        "temas",
        "Remover a página de Temas",
        "Some a troca de tema no painel antigo; no Windows 11 o efeito é parcial.",
        "Aparência",
        _U,
        (Valor(_EXP, "NoThemesTab", "dword", 1),),
    ),
    Politica(
        "ponteiros",
        "Bloquear troca de ponteiros do mouse",
        "A conta não muda o esquema de ponteiros.",
        "Aparência",
        _U,
        (
            Valor(
                "Software\\Policies\\Microsoft\\Windows\\Personalization",
                "NoChangingMousePointers",
                "dword",
                1,
            ),
        ),
    ),
    Politica(
        "powershell",
        "Bloquear PowerShell pelo Explorer",
        "Iniciar, Executar e duplo clique não abrem o PowerShell. Não é bloqueio de execução: "
        "uma cópia renomeada abre.",
        "Aplicativos",
        _U,
        (
            Valor(_EXP + "\\DisallowRun", "ITCBench1", "sz", "powershell.exe"),
            Valor(_EXP + "\\DisallowRun", "ITCBench2", "sz", "powershell_ise.exe"),
            Valor(_EXP + "\\DisallowRun", "ITCBench3", "sz", "pwsh.exe"),
            Valor(_EXP + "\\DisallowRun", "1", "sz", "PowerShell.exe", legado=True),
            Valor(_EXP, "DisallowRun", "dword", 1, lista=_EXP + "\\DisallowRun"),
        ),
    ),
    Politica(
        "store",
        "Bloquear Microsoft Store",
        "A loja não abre. A Microsoft documenta efeito só no Enterprise e no Education.",
        "Aplicativos",
        _UM,
        (Valor("Software\\Policies\\Microsoft\\WindowsStore", "RemoveWindowsStore", "dword", 1),),
        frozenset({"home", "pro"}),
    ),
    Politica(
        "compartilhamento",
        "Ocultar compartilhamento de conexão",
        "Some a opção de compartilhar a internet nas propriedades do adaptador.",
        "Rede",
        _M,
        (
            Valor(
                "SOFTWARE\\Policies\\Microsoft\\Windows\\Network Connections",
                "NC_ShowSharedAccessUI",
                "dword",
                0,
            ),
        ),
        frozenset({"home"}),
    ),
    Politica(
        "wifidirect",
        "Bloquear Wi-Fi Direct",
        "Impede conexões Wi-Fi Direct entre aparelhos.",
        "Rede",
        _M,
        (
            Valor(
                "SOFTWARE\\Policies\\Microsoft\\Windows\\WcmSvc\\GroupPolicy",
                "fBlockWiFiDirect",
                "dword",
                1,
            ),
        ),
        frozenset({"home"}),
    ),
    Politica(
        "ics",
        "Desativar Compartilhamento de Conexão (ICS)",
        "Desativa o serviço SharedAccess; vale a partir do próximo reinício. Desfazer volta "
        "para Manual.",
        "Rede",
        _M,
        (
            Valor(
                "SYSTEM\\CurrentControlSet\\Services\\SharedAccess", "Start", "dword", 4, desfazer=3
            ),
        ),
    ),
    Politica(
        "usb",
        "Armazenamento removível",
        "Pendrive, HD externo, cartão, CD/DVD e celular como disco (Deny_All).",
        "USB",
        _UM,
        (
            Valor(
                "Software\\Policies\\Microsoft\\Windows\\RemovableStorageDevices",
                "Deny_All",
                "dword",
                1,
            ),
        ),
        frozenset({"home"}),
    ),
)
POR_ID = {p.id: p for p in CATALOGO}


def raiz_aceita(escopo: Escopo, chave: str) -> bool:
    c = chave.lower()
    if "\\\\" in c or ".." in c or c.startswith("\\") or c.endswith("\\"):
        return False
    if escopo == "maquina" and c in EXATAS_MAQUINA:
        return True
    return c.startswith(RAIZES[escopo])


def edicao_tipo(edicao: str) -> str:
    """`EditionID` → "home", "pro" ou "outra" (Enterprise, Education...)."""
    if edicao.startswith("Core"):
        return "home"
    if edicao.startswith("Professional"):
        return "pro"
    return "outra"


def aviso_edicao(politica: Politica, edicao: str) -> str | None:
    return AVISO_EDICAO if edicao_tipo(edicao) in politica.sem_confirmar else None


# ---------------------------------------------------------------- situação


def estado(politica: Politica, lidos: dict[str, str | None]) -> Estado:
    """`lidos`: "chave|nome" → valor lido (texto) ou None."""

    def lido(v: Valor) -> str | None:
        return lidos.get(f"{v.chave}|{v.nome}")

    proprios = [v for v in politica.valores if not v.legado]
    if all(lido(v) == str(v.dado) for v in proprios):
        return "aplicada"
    legado = any(
        v.legado and (lido(v) or "").lower() == str(v.dado).lower() for v in politica.valores
    )
    padrao = all(
        lido(v) is None or (v.desfazer is not None and lido(v) == str(v.desfazer)) for v in proprios
    )
    return "nao_aplicada" if padrao and not legado else "diferente"


@dataclass(frozen=True)
class Leitura:
    edicao: str
    dono: str
    situacao: dict[tuple[str, str], Estado]  # (politica, alvo.chave)
    alteravel: dict[tuple[str, str], bool]


def _chaves(escopos: Iterable[Escopo]) -> list[dict[str, Any]]:
    grupos: dict[tuple[str, str], list[str]] = {}
    for p in CATALOGO:
        for escopo in p.escopos & set(escopos):
            for v in p.valores:
                grupos.setdefault((escopo, v.chave), []).append(v.nome)
    return [{"escopo": e, "chave": c, "nomes": n} for (e, c), n in grupos.items()]


def _preencher(alvo: Alvo, dados: dict[str, Any] | None, leitura: Leitura) -> None:
    for p in CATALOGO:
        if alvo.escopo not in p.escopos:
            continue
        k = (p.id, alvo.chave)
        if not dados or not dados.get("ok"):
            leitura.situacao[k] = "sem_acesso"
            continue
        leitura.situacao[k] = estado(p, dados.get("valores") or {})
        alter = dados.get("alteravel") or {}
        if any(alter.get(v.chave) for v in p.valores):
            leitura.alteravel[k] = True


def ler(
    alvos_: Sequence[Alvo],
    *,
    rodar: Rodar = executor.powershell,
    descarregados: bool = False,
) -> Leitura:
    """Situação de todo o catálogo nos alvos. Perfil descarregado (e Contas futuras) só com
    `descarregados=True` (botão "Ler"), que passa pelo carregar/descarregar; senão "não lida"."""
    edicao, dono, dados = hive.ler(
        alvos_, _chaves(["usuario", "maquina"]), rodar=rodar, descarregados=descarregados
    )
    leitura = Leitura(edicao, dono, {}, {})
    for a in alvos_:
        d = dados.get(a.chave)
        if d == hive.NAO_LIDA:
            for p in CATALOGO:
                if "usuario" in p.escopos:
                    leitura.situacao[(p.id, a.chave)] = "nao_lida"
            continue
        _preencher(a, d if isinstance(d, dict) else None, leitura)
    return leitura


# ---------------------------------------------------------------- aplicar / desfazer


def operacoes(acao: Acao, ids: Iterable[str], escopo: Escopo) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for pid in ids:
        p = POR_ID[pid]
        if escopo not in p.escopos:
            continue
        valores = sorted(p.valores, key=lambda v: v.lista is not None)
        for v in valores:
            if not raiz_aceita(escopo, v.chave):
                raise ValueError(f"Raiz recusada no catálogo: {p.id}")
            op = {"p": p.id, "chave": v.chave, "nome": v.nome, "tipo": v.tipo, "dado": v.dado}
            if acao == "aplicar":
                if v.legado:
                    continue
                op["acao"] = "gravar"
            elif v.legado:
                op["acao"] = "apagar_se_igual"
            elif v.lista:
                op.update(acao="apagar_se_vazia", lista=v.lista)
            elif v.desfazer is not None:
                op.update(acao="gravar", dado=v.desfazer)
            else:
                op["acao"] = "apagar"
            ops.append(op)
    return ops


def aplicar(
    acao: Acao,
    ids: Sequence[str],
    alvos_: Sequence[Alvo],
    *,
    protegidas_: Iterable[str],
    rodar: Rodar = executor.powershell,
    cancelar: threading.Event | None = None,
    avisar: Callable[[str], None] = lambda _: None,
) -> list[Feito]:
    """Uma chamada de escrita por alvo, nunca interrompida; cancelar vale entre alvos."""
    hive.bits()
    for pid in ids:
        if pid not in POR_ID:
            raise ValueError(f"Política desconhecida: {pid!r}")
    return hive.aplicar(
        acao,
        alvos_,
        lambda a: operacoes(acao, ids, a.escopo),
        nomes={p.id: p.nome for p in CATALOGO},
        rotulo="Políticas",
        item="politica",
        perfil="politicas",
        protegidas_=protegidas_,
        rodar=rodar,
        cancelar=cancelar,
        avisar=avisar,
    )


# ---------------------------------------------------------------- sobras do Configurador


def pasta_inicializar() -> Path:
    base = os.environ.get("PROGRAMDATA")
    if not base:
        raise RuntimeError("Variável de ambiente PROGRAMDATA ausente.")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "StartUp"


def sobras_configurador(pasta: Path | None = None) -> list[Path]:
    pasta = pasta or pasta_inicializar()
    return [pasta / n for n in SOBRAS_NOMES if (pasta / n).is_file()]


def remover_sobras(pasta: Path | None = None) -> tuple[bool, str]:
    falhas = 0
    for arquivo in sobras_configurador(pasta):
        try:
            arquivo.unlink()
        except OSError as erro:
            falhas += 1
            log.error("Políticas: sobra do Configurador não removida (%s)", type(erro).__name__)
    if falhas:
        return False, "Não foi possível remover todos os arquivos (veja o log)."
    log.info("Políticas: sobras do Configurador removidas")
    return True, "Script de logon do Configurador removido."
