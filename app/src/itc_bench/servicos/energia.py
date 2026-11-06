"""Energia (ADR-022), sem Qt: a tela Energia e o 13 (por id) usam.

Esquema ativo da máquina, sem trocar de esquema. Escrita por `powercfg.exe` com aliases do
Windows (não dependem do idioma) e valores de uma lista fechada; leitura pelo trecho
`recursos/energia/ler.ps1`, só dos números. Desfazer volta ao padrão do próprio esquema; sem
`-restoredefaultschemes` (apagaria esquemas do fabricante).
"""

import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

RECURSOS = resources.files("itc_bench.recursos") / "energia"
TIMEOUT = 60.0
Rodar = Callable[..., executor.Resultado]
Fonte = Literal["ac", "dc"]
FONTES: tuple[Fonte, ...] = ("ac", "dc")

# id → (nome, alias do grupo, alias do ajuste)
AJUSTES = {
    "tela": ("Desligar a tela", "SUB_VIDEO", "VIDEOIDLE"),
    "suspensao": ("Suspender", "SUB_SLEEP", "STANDBYIDLE"),
    "hibernar_apos": ("Hibernar depois de", "SUB_SLEEP", "HIBERNATEIDLE"),
    "disco": ("Desligar o disco", "SUB_DISK", "DISKIDLE"),
}
# Lista fechada, em segundos (0 = nunca).
TEMPOS = {0: "Nunca", 300: "5 min", 600: "10 min", 900: "15 min", 1800: "30 min", 3600: "60 min"}
ROTULO_FONTE = {"ac": "Na tomada", "dc": "Na bateria"}


def rotulo_tempo(segundos: int | None) -> str:
    if segundos is None:
        return "não lido"
    if segundos in TEMPOS:
        return TEMPOS[segundos]
    return f"{segundos // 60} min" if segundos % 60 == 0 else f"{segundos} s"


@dataclass(frozen=True)
class Valor:
    atual: int | None
    padrao: int | None


@dataclass(frozen=True)
class Situacao:
    esquema: str
    valores: dict[tuple[str, Fonte], Valor]
    hibernacao: bool | None


def situacao(*, rodar: Rodar = executor.powershell) -> Situacao:
    r = rodar((RECURSOS / "ler.ps1").read_text("utf-8"), timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError("Leitura da energia falhou.")
    try:
        cru = json.loads(r.saida)
        valores = {}
        for aid in AJUSTES:
            d = cru["ajustes"][aid]
            for f in FONTES:
                atual, padrao = d.get(f), d.get(f"padrao_{f}")
                valores[(aid, f)] = Valor(
                    None if atual is None else int(atual), None if padrao is None else int(padrao)
                )
        hib = cru.get("hibernacao")
        return Situacao(str(cru.get("esquema") or ""), valores, None if hib is None else bool(hib))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as erro:
        raise RuntimeError(f"Saída inválida da leitura ({type(erro).__name__}).") from None


@dataclass(frozen=True)
class Feito:
    item: str
    ok: bool
    mensagem: str


def _rodar_powercfg(argumentos: list[str], rodar: Rodar) -> str | None:
    r = rodar([executor.sistema32("powercfg.exe"), *argumentos], timeout=TIMEOUT)
    if r.ok:
        return None
    return "tempo_esgotado" if r.esgotado else f"powercfg_{r.codigo}"


def tempos(
    escolhas: Mapping[tuple[str, Fonte], int],
    *,
    rodar: Rodar = executor.executar,
    cancelar: threading.Event | None = None,
) -> list[Feito]:
    """(ajuste, fonte) → segundos da lista fechada. Uma chamada por valor; cancela entre elas."""
    for (aid, f), seg in escolhas.items():
        if aid not in AJUSTES or f not in FONTES or seg not in TEMPOS:
            raise ValueError(f"Ajuste ou tempo fora da lista: {aid}/{f}")
    feitos = []
    mudou = False
    for (aid, f), seg in escolhas.items():
        item = f"{aid}_{f}"
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(item, False, "Cancelado pelo técnico."))
            continue
        _, grupo, ajuste = AJUSTES[aid]
        opcao = "/setacvalueindex" if f == "ac" else "/setdcvalueindex"
        erro = _rodar_powercfg([opcao, "SCHEME_CURRENT", grupo, ajuste, str(seg)], rodar)
        mudou = mudou or erro is None
        log.info(
            "Energia: aplicar ajuste=%s valor=%s resultado=%s codigo=%s",
            item,
            seg,
            "ok" if erro is None else "erro",
            erro or "0",
        )
        feitos.append(Feito(item, erro is None, "Feito." if erro is None else f"Falhou ({erro})."))
    if mudou:
        # Reativar o esquema faz o Windows usar os valores novos já.
        erro = _rodar_powercfg(["/setactive", "SCHEME_CURRENT"], rodar)
        if erro:
            log.warning("Energia: setactive falhou (%s)", erro)
            feitos.append(
                Feito("setactive", False, f"Valores gravados; reative o esquema ({erro}).")
            )
    return feitos


def desfazer(
    itens: list[tuple[str, Fonte]],
    *,
    rodar_ps: Rodar = executor.powershell,
    rodar: Rodar = executor.executar,
    cancelar: threading.Event | None = None,
) -> list[Feito]:
    """Volta ao padrão do esquema ativo, lido do Windows; sem padrão, não mexe."""
    s = situacao(rodar=rodar_ps)
    escolhas: dict[tuple[str, Fonte], int] = {}
    feitos = []
    for k in itens:
        padrao = s.valores[k].padrao if k in s.valores else None
        if padrao is None:
            feitos.append(
                Feito(f"{k[0]}_{k[1]}", False, "Padrão do esquema não encontrado: não mexi.")
            )
            continue
        escolhas[k] = padrao
    # O padrão pode estar fora da lista fechada (vem do Windows, não do técnico).
    for (aid, f), seg in escolhas.items():
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(f"{aid}_{f}", False, "Cancelado pelo técnico."))
            continue
        _, grupo, ajuste = AJUSTES[aid]
        opcao = "/setacvalueindex" if f == "ac" else "/setdcvalueindex"
        erro = _rodar_powercfg([opcao, "SCHEME_CURRENT", grupo, ajuste, str(int(seg))], rodar)
        log.info(
            "Energia: desfazer ajuste=%s_%s resultado=%s codigo=%s",
            aid,
            f,
            "ok" if erro is None else "erro",
            erro or "0",
        )
        feitos.append(
            Feito(f"{aid}_{f}", erro is None, "Feito." if erro is None else f"Falhou ({erro}).")
        )
    if any(x.ok for x in feitos):
        _rodar_powercfg(["/setactive", "SCHEME_CURRENT"], rodar)
    return feitos


def hibernacao(ligar: bool, *, rodar: Rodar = executor.executar) -> Feito:
    """`/hibernate off` também desliga a Inicialização rápida."""
    erro = _rodar_powercfg(["/hibernate", "on" if ligar else "off"], rodar)
    log.info(
        "Energia: hibernacao=%s resultado=%s codigo=%s",
        "on" if ligar else "off",
        "ok" if erro is None else "erro",
        erro or "0",
    )
    return Feito("hibernacao", erro is None, "Feito." if erro is None else f"Falhou ({erro}).")
