"""Modelo de configuração (ADR-076), sem Qt: as marcações das telas num arquivo JSON, para levar
de uma máquina a outras da mesma unidade ou projeto.

Só marcações e escolhas que valem em qualquer máquina: perfil e etapas da Configuração, turnos e
sufixo da Identificação, redes do Wi-Fi (id do cadastro), programas para remover (nome e tipo),
políticas e o que não desligar na Inicialização. Nunca senha, nome do computador, SID ou conta.
Ao ler, tudo é conferido (tipo, tamanho, formato) e o que não casa é descartado.
"""

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from itc_bench import __version__
from itc_bench.nucleo import caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos import contas_turno

VERSAO = 1
EXTENSAO = ".itcbench"
LIMITE_BYTES = 256 * 1024
LIMITE_ITENS = 500
LIMITE_TEXTO = 260
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


@dataclass(frozen=True)
class Modelo:
    perfil: str = ""
    etapas_desmarcadas: tuple[str, ...] = ()
    turnos: tuple[str, ...] = ()
    sufixo: str = ""
    com_sufixo: bool = False
    redes: tuple[str, ...] = ()
    programas: tuple[str, ...] = ()  # ids do cadastro de Instaladores (tela Programas)
    perfil_programas: str = ""  # filtro de perfil da tela Programas; vazio = todos (ADR-077)
    remover: tuple[tuple[str, str], ...] = ()  # (nome, tipo) como aparecem em Remover programas
    politicas: tuple[str, ...] = ()
    manter_inicializacao: tuple[str, ...] = ()  # sem função, mas desmarcados pelo técnico
    criado_em: str = ""
    unidade: str = ""
    versao_bench: str = ""
    secoes: tuple[str, ...] = field(default=())

    def resumo(self) -> list[str]:
        linhas = []
        if self.perfil:
            extra = f", {len(self.etapas_desmarcadas)} etapa(s) desmarcada(s)"
            linhas.append(f"Configuração: perfil {self.perfil}" + extra)
        if self.turnos or self.sufixo:
            partes = [", ".join(self.turnos) or "sem turno"]
            if self.sufixo:
                partes.append(f"sufixo {self.sufixo}" + (" (também)" if self.com_sufixo else ""))
            linhas.append("Identificação: " + "; ".join(partes))
        if self.redes:
            linhas.append(f"Wi-Fi: {len(self.redes)} rede(s)")
        if self.programas or self.perfil_programas:
            filtro = f", perfil {self.perfil_programas}" if self.perfil_programas else ""
            linhas.append(f"Programas: {len(self.programas)} para instalar{filtro}")
        if self.remover:
            linhas.append(f"Remover programas: {len(self.remover)} programa(s)")
        if self.politicas:
            linhas.append(f"Políticas: {len(self.politicas)} marcada(s)")
        if self.manter_inicializacao:
            linhas.append(f"Inicialização: {len(self.manter_inicializacao)} mantido(s) ligado(s)")
        return linhas


def pasta() -> Path:
    r"""Pasta indicada: o arquivo posto aqui é carregado ao abrir o Bench."""
    return caminhos.modelos()


def _textos(valor: Any, *, padrao: re.Pattern[str] | None = None) -> tuple[str, ...]:
    if not isinstance(valor, list):
        return ()
    saida = []
    for v in valor[:LIMITE_ITENS]:
        if not isinstance(v, str) or not v.strip() or len(v) > LIMITE_TEXTO:
            continue
        if padrao is not None and not padrao.match(v):
            continue
        saida.append(v)
    return tuple(dict.fromkeys(saida))


def de_dados(d: Any) -> Modelo:
    if not isinstance(d, dict) or d.get("formato") != "itc-bench-modelo":
        raise ValueError("não é um modelo do ITC Bench")
    if not isinstance(d.get("versao"), int) or d["versao"] > VERSAO:
        raise ValueError("modelo de uma versão mais nova do Bench")
    cfg: dict[str, Any] = d["configuracao"] if isinstance(d.get("configuracao"), dict) else {}
    ide: dict[str, Any] = d["identificacao"] if isinstance(d.get("identificacao"), dict) else {}
    perfil = cfg.get("perfil")
    bruto = ide.get("sufixo")
    sufixo = bruto if isinstance(bruto, str) else ""
    if sufixo and contas_turno.validar_sufixo(sufixo) is not None:
        sufixo = ""
    remover = []
    for par in (
        (d.get("remover") or [])[:LIMITE_ITENS] if isinstance(d.get("remover"), list) else []
    ):
        if (
            isinstance(par, list)
            and len(par) == 2
            and all(isinstance(x, str) and 0 < len(x) <= LIMITE_TEXTO for x in par)
        ):
            remover.append((par[0], par[1]))
    secoes = tuple(
        s
        for s in (
            "configuracao",
            "identificacao",
            "wifi",
            "programas",
            "remover",
            "politicas",
            "inicializacao",
        )
        if s in d
    )
    return Modelo(
        perfil=perfil if isinstance(perfil, str) and _ID.match(perfil) else "",
        etapas_desmarcadas=_textos(cfg.get("etapas_desmarcadas"), padrao=_ID),
        turnos=tuple(t for t in _textos(ide.get("turnos")) if t in contas_turno.TURNOS),
        sufixo=sufixo,
        com_sufixo=ide.get("com_sufixo") is True,
        redes=_textos(d.get("wifi"), padrao=_ID),
        programas=_textos(d.get("programas"), padrao=_ID),
        perfil_programas=pp
        if isinstance(pp := d.get("perfil_programas"), str) and _ID.match(pp)
        else "",
        remover=tuple(dict.fromkeys(remover)),
        politicas=_textos(d.get("politicas"), padrao=_ID),
        manter_inicializacao=_textos(d.get("inicializacao")),
        criado_em=str(d.get("criado_em") or "")[:40],
        unidade=str(d.get("unidade") or "")[:40],
        versao_bench=str(d.get("versao_bench") or "")[:40],
        secoes=secoes,
    )


def para_dados(m: Modelo) -> dict[str, Any]:
    return {
        "formato": "itc-bench-modelo",
        "versao": VERSAO,
        "criado_em": m.criado_em or datetime.now(UTC).isoformat(timespec="seconds"),
        "versao_bench": __version__,
        "unidade": m.unidade,
        "configuracao": {"perfil": m.perfil, "etapas_desmarcadas": list(m.etapas_desmarcadas)},
        "identificacao": {"turnos": list(m.turnos), "sufixo": m.sufixo, "com_sufixo": m.com_sufixo},
        "wifi": list(m.redes),
        "programas": list(m.programas),
        "perfil_programas": m.perfil_programas,
        "remover": [list(p) for p in m.remover],
        "politicas": list(m.politicas),
        "inicializacao": list(m.manter_inicializacao),
    }


def salvar(m: Modelo, destino: Path) -> Path:
    if destino.suffix.lower() != EXTENSAO:
        destino = destino.with_suffix(EXTENSAO)
    texto = json.dumps(para_dados(m), ensure_ascii=False, indent=2)
    destino.write_text(texto, "utf-8")
    log.info("Modelo: salvo (%s seções)", len(m.resumo()))
    return destino


def ler(origem: Path) -> Modelo:
    try:
        if origem.stat().st_size > LIMITE_BYTES:
            raise ValueError("arquivo grande demais para um modelo")
        dados = json.loads(origem.read_text("utf-8-sig"))
    except OSError as erro:
        raise ValueError(f"não deu para abrir ({type(erro).__name__})") from None
    except json.JSONDecodeError:
        raise ValueError("arquivo não é JSON") from None
    m = de_dados(dados)
    log.info("Modelo: lido (%s seções)", len(m.resumo()))
    return m


def na_pasta() -> list[Path]:
    """Modelos da pasta indicada, do mais novo para o mais velho."""
    try:
        return sorted(
            (p for p in pasta().glob(f"*{EXTENSAO}") if p.is_file() and not p.is_symlink()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []


def usar_sempre(origem: Path) -> Path:
    """Copia o modelo para a pasta indicada (ADR-078): passa a abrir sozinho nesta máquina. A
    cópia fica com a data de agora, então vence os que já estavam lá."""
    destino = pasta() / origem.name
    pasta().mkdir(parents=True, exist_ok=True)
    if origem.resolve() != destino.resolve():
        shutil.copyfile(origem, destino)
    os.utime(destino)
    log.info("Modelo: copiado para a pasta indicada")
    return destino


def parar_de_usar() -> int:
    """Tira os modelos da pasta indicada (são cópias). Devolve quantos saíram."""
    saiu = 0
    for p in na_pasta():
        p.unlink()
        saiu += 1
    log.info("Modelo: %s arquivo(s) tirado(s) da pasta indicada", saiu)
    return saiu


def da_pasta() -> tuple[Path, Modelo] | None:
    """O modelo mais novo da pasta indicada, se houver. Arquivo ruim é ignorado (e logado)."""
    for arquivo in na_pasta():
        try:
            return arquivo, ler(arquivo)
        except ValueError as erro:
            log.warning("Modelo: arquivo da pasta ignorado (%s)", erro)
    return None
