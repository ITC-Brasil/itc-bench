"""Tela Início (ADR-023, item 6), sem Qt: estado da máquina e alertas com a tela que resolve.

Leituras baratas, feitas em tarefa ao abrir e guardadas 60 s. As etapas da preparação vêm do
último andamento lido nesta sessão (ler todas custa minutos: winget, hives fechados).
"""

import json
import re
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
    # ADR-073: nome do computador, processador e memória (None ou "" = não lido).
    nome: str = ""
    cpu_nome: str = ""
    cpu_nucleos: int | None = None
    cpu_threads: int | None = None
    cpu_uso: int | None = None  # % agora, da leitura
    mem_total: int | None = None  # bytes instalados
    mem_uso: int | None = None  # % em uso agora
    mem_tipo: str = ""  # DDR4, LPDDR5...
    mem_slots: int | None = None
    mem_modulos: int | None = None
    bateria_projeto: int | None = None  # mWh de fábrica (só com administrador)
    bateria_cheia: int | None = None  # mWh de carga máxima hoje
    bateria_ciclos: int | None = None  # ciclos de carga (relatório do powercfg)

    @property
    def bateria_saude(self) -> int | None:
        """Carga máxima de hoje sobre a de fábrica, em % (até 100), ou None sem as duas."""
        if not self.bateria_projeto or not self.bateria_cheia:
            return None
        return min(100, round(100 * self.bateria_cheia / self.bateria_projeto))

    @property
    def disco_usado(self) -> float | None:
        """Fração usada do disco do sistema, ou None sem leitura."""
        if not self.disco_total or self.disco_livre is None:
            return None
        return min(1.0, max(0.0, 1 - self.disco_livre / self.disco_total))

    @property
    def processador(self) -> str:
        """Modelo curto: `12th Gen Intel(R) Core(TM) i5-1235U` → `Core i5-1235U`."""
        return cpu_curto(self.cpu_nome)

    @property
    def windows(self) -> str:
        """`Windows 11 Pro 26H2 build 26300`. 10 ou 11 vem do build (22000 ou mais = 11): o
        ProductName do registro diz "Windows 10" mesmo no 11."""
        edicao = {"Core": "Home", "Professional": "Pro"}.get(self.edicao, self.edicao)
        build = _int(self.build)
        geracao = "" if build is None else ("11" if build >= WINDOWS_11 else "10")
        partes = (
            " ".join(x for x in ("Windows", geracao, edicao) if x),
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
        return None if v is None or isinstance(v, bool) else int(v)
    except (TypeError, ValueError):
        return None


def _faixa(v: Any, minimo: int, maximo: int) -> int | None:
    """Inteiro dentro da faixa; fora dela (saída estranha), None."""
    n = _int(v)
    return n if n is not None and minimo <= n <= maximo else None


# ---------------------------------------------------------------- regras dos indicadores (ADR-073)

LIMITE_DISCO = 0.10  # livre abaixo disso: alerta de disco e cartão "Quase cheio"
DISCO_ATENCAO = 0.85  # usado a partir disso: anel em atenção
BATERIA_CRITICA = 15  # % abaixo disso, fora da tomada: crítico
BATERIA_ATENCAO = 30
SAUDE_ATENCAO = 80  # % da capacidade de fábrica: abaixo disso, bateria gasta
SAUDE_CRITICA = 50  # abaixo disso, pede troca
WINDOWS_11 = 22000  # primeiro build do Windows 11
# SMBIOS 3.x, tipo de memória (Win32_PhysicalMemory.SMBIOSMemoryType).
TIPOS_MEMORIA = {
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
    27: "LPDDR",
    28: "LPDDR2",
    29: "LPDDR3",
    30: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}
Nivel3 = Literal["normal", "atencao", "critico"]


def nivel_disco(usado: float | None) -> Nivel3:
    """Normal, atenção (85% usado) ou crítico (o mesmo limite do alerta: menos de 10% livre)."""
    if usado is None:
        return "normal"
    if round(1 - usado, 9) < LIMITE_DISCO:  # 1 - 0.9 = 0.0999…: arredonda antes de comparar
        return "critico"
    return "atencao" if usado >= DISCO_ATENCAO else "normal"


def nivel_bateria(carga: int | None, na_tomada: bool | None) -> Nivel3:
    """Carga baixa só preocupa fora da tomada."""
    if carga is None or na_tomada:
        return "normal"
    if carga < BATERIA_CRITICA:
        return "critico"
    return "atencao" if carga < BATERIA_ATENCAO else "normal"


def nivel_saude(saude: int | None) -> Nivel3:
    """Saúde da bateria: atenção abaixo de 80% da capacidade de fábrica, crítica abaixo de 50%."""
    if saude is None:
        return "normal"
    if saude < SAUDE_CRITICA:
        return "critico"
    return "atencao" if saude < SAUDE_ATENCAO else "normal"


def tipo_memoria(codigo: int | None) -> str:
    return TIPOS_MEMORIA.get(codigo or 0, "")


_MARCAS = re.compile(r"\((?:R|TM|C)\)|[®™]", re.IGNORECASE)
_RUIDO = re.compile(
    r"\b\d+(?:st|nd|rd|th) Gen\b|\bIntel\b|\bAMD\b|\bCPU\b|\bProcessor\b|"
    r"\bwith Radeon(?: \w+)* Graphics\b|@.*$",
    re.IGNORECASE,
)


def cpu_curto(nome: str) -> str:
    """Tira marcas, fabricante, geração, "CPU", gráficos e frequência do nome do processador."""
    curto = _RUIDO.sub(" ", _MARCAS.sub("", nome))
    return " ".join(curto.split())[:60]


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
        _faixa(d.get("bateria"), 0, 100),
        None if d.get("na_tomada") is None else bool(d.get("na_tomada")),
        nome=_texto(d.get("nome"))[:15],  # NetBIOS
        cpu_nome=_texto(d.get("cpu_nome")),
        cpu_nucleos=_faixa(d.get("cpu_nucleos"), 1, 1024),
        cpu_threads=_faixa(d.get("cpu_threads"), 1, 4096),
        cpu_uso=_faixa(d.get("cpu_uso"), 0, 100),
        mem_total=_faixa(d.get("mem_total"), 1, 1 << 50),
        mem_uso=_faixa(d.get("mem_uso"), 0, 100),
        mem_tipo=tipo_memoria(_int(d.get("mem_tipo"))),
        mem_slots=_faixa(d.get("mem_slots"), 1, 64),
        mem_modulos=_faixa(d.get("mem_modulos"), 1, 64),
        bateria_projeto=_faixa(d.get("bateria_projeto"), 1, 10_000_000),
        bateria_cheia=_faixa(d.get("bateria_cheia"), 1, 10_000_000),
        bateria_ciclos=_faixa(d.get("bateria_ciclos"), 0, 100_000),
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
    if disco_livre is not None and disco_livre < LIMITE_DISCO:
        saida.append(Alerta("atencao", "Menos de 10% de disco livre: use a Limpeza", "limpeza"))
    return saida


def _tentar(nome: str, f: Callable[[], Any], erros: list[str]) -> Any:
    try:
        return f()
    except Exception as erro:  # noqa: BLE001 — uma leitura do Início nunca derruba as outras
        log.warning("Início: leitura %s falhou: %s", nome, type(erro).__name__)
        erros.append(nome)
        return None


def ler(
    *, admin: bool, cadastros: Cadastros | None, fila: int, perfil: perfis.Perfil | None
) -> Painel:
    erros: list[str] = []
    m = _tentar("maquina", maquina, erros)
    prot = _tentar("protecao", protecao.situacao, erros) if admin else None
    pol: int | None = None
    if admin and perfil is not None and "politicas" in perfil.etapas:

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
