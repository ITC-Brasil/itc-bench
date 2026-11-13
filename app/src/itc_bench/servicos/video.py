"""Monitores (ADR-041), sem Qt: a tela "Tela e papel de parede" usa.

Resolução, frequência, orientação e escala de cada monitor ativo, de 1 a N. Só valores que o
próprio Windows lista para aquele monitor; nada de valor digitado. A tela guarda a situação de
antes e, se o técnico não confirmar em `PRAZO` segundos, volta tudo (`desfazer`).

Resolução, frequência e orientação valem para a máquina. A escala vale para a conta que roda o
Bench (o Windows grava por usuário) e usa uma API não documentada (risco aceito no ADR-041).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from itc_bench.nucleo import video as nucleo
from itc_bench.nucleo.log import log

PRAZO = 15  # segundos para confirmar antes de voltar sozinho
ORIENTACOES = {0: "Paisagem", 1: "Retrato", 2: "Paisagem (invertida)", 3: "Retrato (invertido)"}

Modo = nucleo.Modo


class Driver(Protocol):
    def monitores(self) -> list[nucleo.MonitorBruto]: ...
    def mudar_modo(self, dispositivo: str, modo: Modo, orientacao: int) -> int: ...
    def mudar_escala(self, adaptador: tuple[int, int], origem: int, percentual: int) -> int: ...


@dataclass(frozen=True)
class Monitor:
    numero: int  # 1, 2, ... na ordem do Windows
    nome: str  # para a tela
    bruto: nucleo.MonitorBruto

    @property
    def dispositivo(self) -> str:
        return self.bruto.dispositivo

    def resolucoes(self) -> list[tuple[int, int]]:
        vistas = dict.fromkeys((m.largura, m.altura) for m in self.bruto.modos)
        return sorted(vistas, key=lambda r: (r[0] * r[1], r[0]), reverse=True)

    def frequencias(self, largura: int, altura: int) -> list[int]:
        fs = {m.frequencia for m in self.bruto.modos if (m.largura, m.altura) == (largura, altura)}
        return sorted(fs, reverse=True)

    def recomendada(self) -> tuple[int, int] | None:
        """A maior resolução listada, que no notebook é a nativa do painel."""
        r = self.resolucoes()
        return r[0] if r else None

    def atual_paisagem(self) -> tuple[int, int]:
        a = self.bruto.atual
        return (max(a.largura, a.altura), min(a.largura, a.altura))


@dataclass(frozen=True)
class Escolha:
    """O que o técnico quer para um monitor. `None` = não mexer."""

    dispositivo: str
    resolucao: tuple[int, int] | None = None
    frequencia: int | None = None
    orientacao: int | None = None
    escala: int | None = None


@dataclass(frozen=True)
class Feito:
    item: str
    ok: bool
    mensagem: str


@dataclass
class Antes:
    """Situação guardada antes de aplicar, para `desfazer`."""

    monitores: list[Monitor] = field(default_factory=list)


def _nome(m: nucleo.MonitorBruto, numero: int) -> str:
    if m.interno:
        base = "Tela do notebook"
    elif m.nome:
        base = m.nome
    else:
        base = "Monitor externo"
    return f"{numero}. {base}" + (" (principal)" if m.principal else "")


def ler(driver: Driver = nucleo) -> list[Monitor]:
    return [Monitor(i, _nome(b, i), b) for i, b in enumerate(driver.monitores(), start=1)]


def validar(monitores: Sequence[Monitor], escolha: Escolha) -> str:
    """Motivo da recusa, ou vazio. Tudo tem de estar na lista que o Windows deu."""
    m = next((x for x in monitores if x.dispositivo == escolha.dispositivo), None)
    if m is None:
        return "monitor não está mais conectado; clique em Atualizar"
    if escolha.resolucao is not None:
        if escolha.resolucao not in m.resolucoes():
            return "resolução não listada pelo monitor"
        if escolha.frequencia is not None and escolha.frequencia not in m.frequencias(
            *escolha.resolucao
        ):
            return "frequência não listada para essa resolução"
    elif escolha.frequencia is not None and escolha.frequencia not in m.frequencias(
        *m.atual_paisagem()
    ):
        return "frequência não listada para a resolução atual"
    if escolha.orientacao is not None and escolha.orientacao not in ORIENTACOES:
        return "orientação desconhecida"
    if escolha.escala is not None:
        if m.bruto.escala is None:
            return "o Windows não informou a escala deste monitor"
        if escolha.escala not in m.bruto.escala.opcoes:
            return "escala não aceita por este monitor"
    return ""


def _muda_modo(m: Monitor, e: Escolha) -> bool:
    a = m.bruto
    return (
        (e.resolucao is not None and e.resolucao != m.atual_paisagem())
        or (e.frequencia is not None and e.frequencia != a.atual.frequencia)
        or (e.orientacao is not None and e.orientacao != a.orientacao)
    )


def mudancas(monitores: Sequence[Monitor], escolhas: Sequence[Escolha]) -> list[str]:
    """Linhas da confirmação, só do que muda."""
    linhas: list[str] = []
    por = {m.dispositivo: m for m in monitores}
    for e in escolhas:
        m = por.get(e.dispositivo)
        if m is None:
            continue
        a = m.bruto
        if e.resolucao is not None and e.resolucao != m.atual_paisagem():
            de, para = m.atual_paisagem(), e.resolucao
            linhas.append(f"{m.nome}: resolução {de[0]}x{de[1]} → {para[0]}x{para[1]}")
        if e.frequencia is not None and e.frequencia != a.atual.frequencia:
            linhas.append(f"{m.nome}: frequência {a.atual.frequencia} Hz → {e.frequencia} Hz")
        if e.orientacao is not None and e.orientacao != a.orientacao:
            linhas.append(
                f"{m.nome}: orientação {ORIENTACOES.get(a.orientacao, '?')} → "
                f"{ORIENTACOES[e.orientacao]}"
            )
        if e.escala is not None and a.escala is not None and e.escala != a.escala.atual:
            linhas.append(f"{m.nome}: escala {a.escala.atual}% → {e.escala}%")
    return linhas


def aplicar(
    escolhas: Sequence[Escolha],
    driver: Driver = nucleo,
    avisar: Callable[[str], None] = lambda _t: None,
) -> tuple[list[Feito], Antes]:
    """Aplica monitor por monitor; uma falha não para os outros. Devolve o `Antes`."""
    atuais = ler(driver)
    antes = Antes(atuais)
    feitos: list[Feito] = []
    por = {m.dispositivo: m for m in atuais}
    for e in escolhas:
        m = por.get(e.dispositivo)
        motivo = validar(atuais, e)
        if m is None or motivo:
            feitos.append(Feito(m.nome if m else "Monitor", False, motivo))
            log.warning("Vídeo: recusado (%s).", motivo)
            continue
        a = m.bruto
        if _muda_modo(m, e):
            res = e.resolucao or m.atual_paisagem()
            freq = e.frequencia
            if freq is None:
                # Resolução nova: a frequência atual, se o monitor tiver; senão, a maior.
                opcoes = m.frequencias(*res)
                freq = a.atual.frequencia if a.atual.frequencia in opcoes else opcoes[0]
            ori = a.orientacao if e.orientacao is None else e.orientacao
            r = driver.mudar_modo(m.dispositivo, Modo(res[0], res[1], freq, a.atual.bits), ori)
            texto = nucleo.RESULTADOS.get(r, f"erro {r}")
            feitos.append(Feito(f"{m.nome}: resolução e frequência", r in (0, 1), texto))
            log.info("Vídeo: monitor %d, modo → código %d.", m.numero, r)
            avisar(f"{m.nome}: {texto}")
        if e.escala is not None and a.escala is not None and e.escala != a.escala.atual:
            r = driver.mudar_escala(a.adaptador, a.origem, e.escala)
            texto = "aplicada" if r == 0 else f"o Windows recusou (código {r})"
            feitos.append(Feito(f"{m.nome}: escala", r == 0, texto))
            log.info("Vídeo: monitor %d, escala → código %d.", m.numero, r)
            avisar(f"{m.nome}: escala {texto}")
    return feitos, antes


def desfazer(antes: Antes, driver: Driver = nucleo) -> list[Feito]:
    """Volta cada monitor guardado à resolução, frequência, orientação e escala de antes."""
    escolhas = [
        Escolha(
            m.dispositivo,
            resolucao=m.atual_paisagem(),
            frequencia=m.bruto.atual.frequencia,
            orientacao=m.bruto.orientacao,
            escala=m.bruto.escala.atual if m.bruto.escala else None,
        )
        for m in antes.monitores
    ]
    feitos, _ = aplicar(escolhas, driver)
    log.info("Vídeo: desfeito (%d itens).", len(feitos))
    return feitos
