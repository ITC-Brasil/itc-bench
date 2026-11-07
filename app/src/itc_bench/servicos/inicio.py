"""Tela Início (ADR-023, item 6), sem Qt: estado da máquina e alertas com a tela que resolve.

Leituras baratas, feitas em tarefa ao abrir e guardadas 60 s. As etapas da preparação vêm do
último andamento lido nesta sessão (ler todas custa minutos: winget, hives fechados).
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any, Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import contas, executor, hive, identificacao, perfis, politicas, protecao
from itc_bench.servicos.cadastros import Cadastros

RECURSOS = resources.files("itc_bench.recursos") / "inicio"
TIMEOUT = 60
CACHE = 60.0
CADASTROS_VELHOS = timedelta(days=1)
Rodar = Callable[..., executor.Resultado]
Nivel = Literal["critico", "atencao"]


@dataclass(frozen=True)
class Maquina:
    fabricante: str = ""
    modelo: str = ""
    serie: str = ""
    edicao: str = ""
    versao: str = ""
    build: str = ""
    disco_total: int | None = None
    disco_livre: int | None = None
    bateria: int | None = None
    na_tomada: bool | None = None

    @property
    def windows(self) -> str:
        edicao = {"Core": "Home", "Professional": "Pro"}.get(self.edicao, self.edicao)
        partes = (
            f"Windows {edicao}".strip(),
            self.versao,
            f"build {self.build}" * bool(self.build),
        )
        return " ".join(x for x in partes if x)


@dataclass(frozen=True)
class Alerta:
    nivel: Nivel
    texto: str
    tela: str  # chave do menu que resolve


@dataclass(frozen=True)
class Painel:
    maquina: Maquina | None
    alertas: tuple[Alerta, ...]
    erros: tuple[str, ...] = ()
    lido_em: float = field(default_factory=time.monotonic)

    @property
    def criticos(self) -> int:
        return sum(1 for a in self.alertas if a.nivel == "critico")


def _texto(v: Any) -> str:
    return str(v).strip()[:100] if v is not None else ""


def _int(v: Any) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def maquina(*, rodar: Rodar = executor.powershell) -> Maquina:
    r = rodar((RECURSOS / "ler.ps1").read_text("utf-8"), timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError("tempo esgotado" if r.esgotado else f"código {r.codigo}")
    try:
        d = json.loads(r.saida)
    except json.JSONDecodeError:
        raise RuntimeError("saída inválida") from None
    return Maquina(
        _texto(d.get("fabricante")),
        _texto(d.get("modelo")),
        _texto(d.get("serie")),
        _texto(d.get("edicao")),
        _texto(d.get("versao")),
        _texto(d.get("build")),
        _int(d.get("disco_total")),
        _int(d.get("disco_livre")),
        _int(d.get("bateria")),
        None if d.get("na_tomada") is None else bool(d.get("na_tomada")),
    )


def alertas(
    *,
    protecao_: protecao.Situacao | None,
    politicas_faltando: int | None,
    nome_pendente: bool,
    suporte: bool | None,
    cadastros: Cadastros | None,
    fila: int,
    disco_livre: float | None = None,
    agora: datetime | None = None,
) -> list[Alerta]:
    """Pura: monta a lista a partir das leituras (None = não lida)."""
    saida: list[Alerta] = []
    if protecao_ is not None:
        saida += [
            Alerta("critico", f"Proteção do login: {t}", "protecao") for t in protecao_.alertas()
        ]
    if politicas_faltando:
        saida.append(
            Alerta(
                "critico", f"{politicas_faltando} política(s) da máquina do perfil faltando", "gpo"
            )
        )
    if suporte is False:
        saida.append(Alerta("critico", "Conta Suporte ausente ou sem administrador", "contas"))
    if nome_pendente:
        saida.append(Alerta("atencao", "Nome do computador muda no próximo reinício", "id"))
    if cadastros is None:
        saida.append(Alerta("atencao", "Sem cadastros: entre online para sincronizar", "config"))
    elif (agora or datetime.now(UTC)) - cadastros.sincronizado_em > CADASTROS_VELHOS:
        saida.append(Alerta("atencao", "Cadastros com mais de 1 dia; sincronize", "config"))
    if fila:
        saida.append(Alerta("atencao", f"{fila} diagnóstico(s) na fila de envio", "diag"))
    if disco_livre is not None and disco_livre < 0.10:
        saida.append(Alerta("atencao", "Menos de 10% de disco livre: use a Limpeza", "limpeza"))
    return saida


def _tentar(nome: str, f: Callable[[], Any], erros: list[str]) -> Any:
    try:
        return f()
    except Exception as erro:  # noqa: BLE001 — uma leitura do Início nunca derruba as outras
        log.warning("Início: leitura %s falhou: %s", nome, type(erro).__name__)
        erros.append(nome)
        return None


def ler(*, admin: bool, cadastros: Cadastros | None, fila: int, perfil: perfis.Perfil) -> Painel:
    erros: list[str] = []
    m = _tentar("maquina", maquina, erros)
    prot = _tentar("protecao", protecao.situacao, erros) if admin else None
    pol: int | None = None
    if admin and "politicas" in perfil.etapas:

        def faltando() -> int:
            leitura = politicas.ler([hive.MAQUINA])
            return sum(
                1
                for pid in perfis.POLITICAS_MAQUINA
                if leitura.situacao.get((pid, "maquina")) != "aplicada"
            )

        pol = _tentar("politicas", faltando, erros)
    estado = _tentar("identificacao", identificacao.estado, erros)
    sup = None
    if admin and cadastros is not None:
        lista = _tentar("contas", contas.listar, erros)
        if lista is not None:
            sup = contas.suporte_ok(lista, contas.protegidas(cadastros))
    livre = None
    if m is not None and m.disco_total:
        livre = (m.disco_livre or 0) / m.disco_total
    lista_alertas = alertas(
        protecao_=prot,
        politicas_faltando=pol,
        nome_pendente=bool(estado and estado.reinicio_pendente),
        suporte=sup,
        cadastros=cadastros,
        fila=fila,
        disco_livre=livre,
    )
    return Painel(m, tuple(lista_alertas), tuple(erros))
