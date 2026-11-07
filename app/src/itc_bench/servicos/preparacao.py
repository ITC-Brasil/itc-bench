"""Motor da Preparação completa (ADR-023), sem Qt.

Cada etapa lê a situação no Windows antes de aplicar; etapa feita é pulada, sem marca guardada.
Falha numa etapa segue para a próxima que não depende dela. "Pausar" para depois da etapa
corrente. O log recebe perfil, etapa, situação, resultado e código; nunca mensagem do Windows,
nome de conta, SID, SSID, nome de programa ou senha.
"""

import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from itc_bench.nucleo.log import log
from itc_bench.servicos import perfis

Situacao = Literal[
    "feito", "pendente", "nao_iniciado", "bloqueada", "falhou", "aguardando_reinicio"
]
ROTULO: dict[Situacao, str] = {
    "feito": "feito",
    "pendente": "pendente",
    "nao_iniciado": "não iniciado",
    "bloqueada": "bloqueada",
    "falhou": "falhou",
    "aguardando_reinicio": "aguardando reinício",
}
MAX_REINICIOS = 2


@dataclass(frozen=True)
class Leitura:
    situacao: Situacao
    detalhe: str = ""  # só para a tela
    codigo: str = ""  # vai para o log


@dataclass(frozen=True)
class Resultado:
    # "parcial": aplicou o que cabe ao Bench; o resto fica pendente sem bloquear dependentes.
    estado: Literal["ok", "parcial", "reinicio", "falha"]
    detalhe: str = ""
    codigo: str = ""


class Etapa(Protocol):
    id: str

    def ler(self) -> Leitura: ...

    def aplicar(self, cancelar: threading.Event) -> Resultado: ...


@dataclass
class Andamento:
    """Situação por etapa, na ordem do perfil. Mutável: a tela lê depois de cada aviso."""

    perfil: str
    etapas: list[str]
    situacao: dict[str, Leitura] = field(default_factory=dict)
    reinicio: bool = False

    def feitas(self) -> int:
        return sum(
            1
            for e in self.etapas
            if self.situacao.get(e, Leitura("nao_iniciado")).situacao == "feito"
        )

    def selo(self) -> str:
        return f"{self.feitas()}/{len(self.etapas)}"


def _log(perfil: str, etapa: str, situacao: str, resultado: str, codigo: str = "") -> None:
    log.info(
        "Preparação: perfil=%s etapa=%s situacao=%s resultado=%s codigo=%s",
        perfil,
        etapa,
        situacao,
        resultado,
        codigo or "0",
    )


def _bloqueio(etapa: str, andamento: Andamento) -> str:
    for dep in perfis.dependencias(etapa):
        if dep not in andamento.etapas:
            continue
        s = andamento.situacao.get(dep)
        if s is not None and s.situacao in ("falhou", "bloqueada"):
            return f"depende de {perfis.NOMES[dep]}"
    return ""


def _ler(etapa: Etapa) -> Leitura:
    try:
        return etapa.ler()
    except Exception as erro:  # noqa: BLE001 — uma leitura nunca derruba a preparação
        log.error("Preparação: leitura de %s falhou: %s", etapa.id, type(erro).__name__)
        return Leitura("falhou", "Não foi possível ler a situação.", type(erro).__name__)


def ler_todas(
    etapas: Sequence[Etapa], andamento: Andamento, avisar: Callable[[str], None] = lambda _: None
) -> Andamento:
    for e in etapas:
        if e.id not in andamento.etapas:
            continue
        bloq = _bloqueio(e.id, andamento)
        andamento.situacao[e.id] = Leitura("bloqueada", bloq) if bloq else _ler(e)
        avisar(e.id)
    return andamento


def rodar(
    etapas: Sequence[Etapa],
    andamento: Andamento,
    *,
    pausar: threading.Event,
    cancelar: threading.Event | None = None,
    avisar: Callable[[str], None] = lambda _: None,
) -> Andamento:
    """Roda as etapas do andamento em ordem. Devolve com `reinicio` se alguma pediu."""
    cancelar = cancelar or threading.Event()
    log.info("Preparação: início perfil=%s etapas=%s", andamento.perfil, ",".join(andamento.etapas))
    for e in etapas:
        if e.id not in andamento.etapas:
            continue
        if pausar.is_set():
            log.info("Preparação: pausada antes de %s", e.id)
            break
        bloq = _bloqueio(e.id, andamento)
        if bloq:
            andamento.situacao[e.id] = Leitura("bloqueada", bloq)
            _log(andamento.perfil, e.id, "bloqueada", "pulada", "dependencia")
            avisar(e.id)
            continue
        lida = _ler(e)
        if lida.situacao in ("feito", "bloqueada", "aguardando_reinicio", "falhou"):
            andamento.situacao[e.id] = lida
            _log(andamento.perfil, e.id, lida.situacao, "pulada", lida.codigo)
            andamento.reinicio = andamento.reinicio or lida.situacao == "aguardando_reinicio"
            avisar(e.id)
            continue
        try:
            r = e.aplicar(cancelar)
        except Exception as erro:  # noqa: BLE001 — falha parcial: segue para a próxima
            log.error("Preparação: etapa %s falhou: %s", e.id, type(erro).__name__)
            r = Resultado("falha", "Falha inesperada; veja o Registro.", type(erro).__name__)
        if r.estado == "parcial":
            final = _ler(e)
            if final.situacao == "pendente":
                final = Leitura("pendente", r.detalhe or final.detalhe, r.codigo)
            andamento.situacao[e.id] = final
        elif r.estado == "ok":
            final = _ler(e)
            if final.situacao == "pendente":
                final = Leitura(
                    "falhou", r.detalhe or "Ainda pendente depois de aplicar.", "pendente_apos"
                )
            andamento.situacao[e.id] = final
        elif r.estado == "reinicio":
            andamento.situacao[e.id] = Leitura("aguardando_reinicio", r.detalhe)
            andamento.reinicio = True
        else:
            andamento.situacao[e.id] = Leitura("falhou", r.detalhe, r.codigo or "falha")
        s = andamento.situacao[e.id]
        _log(andamento.perfil, e.id, lida.situacao, s.situacao, s.codigo)
        avisar(e.id)
    log.info("Preparação: fim perfil=%s feitas=%s", andamento.perfil, andamento.selo())
    return andamento


def novo(perfil: perfis.Perfil, desmarcadas: Iterable[str] = ()) -> Andamento:
    fora = set(desmarcadas)
    etapas = [e for e in perfil.etapas if e not in fora]
    return Andamento(perfil.id, etapas, {e: Leitura("nao_iniciado") for e in etapas})
