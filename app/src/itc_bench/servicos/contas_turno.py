"""Contas por turno a partir do nome do computador (ADR-029), sem Qt: a tela Identificação usa.

`configurar` junta o renomear (ADR-018) e a criação: renomeia se o nome digitado for outro e,
só se der certo, cria as contas com esse nome como base.

O nome base é sempre o nome do computador (o que vale depois de reiniciar, ADR-018). Regra:
com turno marcado, uma conta `BASE-Turno` por turno (o sufixo é ignorado, a não ser que o
operador marque "Criar também o usuário do sufixo": aí entra mais `BASE-Sufixo`); sem turno e com
sufixo, `BASE-Sufixo`; sem nenhum dos dois, só `BASE`. As contas são Local padrão, sem senha,
e são criadas por `contas.criar` (ADR-017), que confere tudo de novo, aqui e no PowerShell.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import contas, identificacao
from itc_bench.servicos.contas import Lista, Rodar
from itc_bench.servicos.executor import powershell

TURNOS = ("Manha", "Tarde", "Noite")  # sem acento: perfil, scripts e acesso remoto
SUFIXO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?$")

Situacao = Literal["criado", "existia", "erro"]


@dataclass(frozen=True)
class Previsto:
    """Uma linha da prévia: o nome, se já existe e o motivo da recusa (None = pode criar)."""

    nome: str
    existe: bool
    problema: str | None


@dataclass(frozen=True)
class Item:
    nome: str
    situacao: Situacao
    mensagem: str


@dataclass(frozen=True)
class Resumo:
    computador: str
    itens: tuple[Item, ...]
    renomeio: identificacao.Feito | None = None  # None = o nome já era esse

    @property
    def falhou_renomear(self) -> bool:
        return self.renomeio is not None and not self.renomeio.ok

    def _contar(self, situacao: Situacao) -> int:
        return sum(1 for i in self.itens if i.situacao == situacao)

    @property
    def criados(self) -> int:
        return self._contar("criado")

    @property
    def existentes(self) -> int:
        return self._contar("existia")

    @property
    def erros(self) -> int:
        return self._contar("erro")


def validar_sufixo(sufixo: str) -> str | None:
    """Motivo da recusa, ou None. Vazio é válido (o sufixo é opcional)."""
    sufixo = sufixo.strip()
    if sufixo and not SUFIXO.fullmatch(sufixo):
        return "Sufixo: use só letras sem acento, números, hífen ou _ (sem espaço)."
    return None


def usa_sufixo(turnos: Iterable[str], sufixo: str, com_sufixo: bool = False) -> bool:
    """O sufixo vira conta sem turno marcado, ou com turno se o operador pediu (`com_sufixo`)."""
    if not sufixo.strip():
        return False
    return com_sufixo or not any(t in TURNOS for t in turnos)


def nomes(
    base: str, turnos: Iterable[str], sufixo: str, com_sufixo: bool = False
) -> tuple[str, ...]:
    """Nomes das contas, na ordem Manhã, Tarde, Noite (e o sufixo por último, se `com_sufixo`).
    Base vazia = nenhuma conta."""
    base = base.strip()
    if not base:
        return ()
    marcados = set(turnos)
    escolhidos = [t for t in TURNOS if t in marcados]
    if escolhidos:
        extra = (f"{base}-{sufixo.strip()}",) if usa_sufixo(marcados, sufixo, com_sufixo) else ()
        return tuple(f"{base}-{t}" for t in escolhidos) + extra
    sufixo = sufixo.strip()
    if sufixo:
        return (f"{base}-{sufixo}",)
    return (base,)


def previa(
    base: str,
    turnos: Iterable[str],
    sufixo: str,
    lista: Lista | None,
    protegidas_: Iterable[str],
    com_sufixo: bool = False,
) -> tuple[Previsto, ...]:
    """Cada conta que seria criada, com o motivo da recusa. Conta que já existe não é recusa."""
    marcados = tuple(turnos)
    problema_sufixo = validar_sufixo(sufixo) if usa_sufixo(marcados, sufixo, com_sufixo) else None
    sufixada = f"{base.strip()}-{sufixo.strip()}"
    prot = frozenset(protegidas_)
    saida = []
    for nome in nomes(base, marcados, sufixo, com_sufixo):
        existe = lista is not None and any(c.nome.lower() == nome.lower() for c in lista.contas)
        recusa_sufixo = problema_sufixo if (nome == sufixada or not marcados) else None
        problema = recusa_sufixo or (
            None
            if existe
            else contas.validar_nome(nome, lista, prot, permitir_nome_computador=True)
        )
        saida.append(Previsto(nome, existe, problema))
    return tuple(saida)


def criar(
    base: str,
    turnos: Iterable[str],
    sufixo: str,
    *,
    com_sufixo: bool = False,
    protegidas_: frozenset[str] = frozenset({contas.SUPORTE_PADRAO.lower()}),
    rodar: Rodar = powershell,
) -> Resumo:
    """Cria o que falta, uma conta por vez; uma falha não interrompe as outras."""
    marcados = tuple(turnos)
    lista = contas.listar(rodar=rodar)
    itens = []
    for p in previa(base, marcados, sufixo, lista, protegidas_, com_sufixo):
        if p.problema:
            itens.append(Item(p.nome, "erro", p.problema))
            continue
        if p.existe:
            itens.append(Item(p.nome, "existia", "já existia"))
            continue
        try:
            feito = contas.criar(
                p.nome,
                None,
                "padrao",
                protegidas_=protegidas_,
                permitir_nome_computador=True,
                rodar=rodar,
            )
        except contas.ErroContas as erro:
            feito = contas.Feito(False, f"Não foi possível ler as contas: {erro}")
        if feito.ok:
            itens.append(Item(p.nome, "criado", "criado"))
        elif feito.mensagem.startswith(contas.MENSAGENS["nome_existe"]):
            itens.append(Item(p.nome, "existia", "já existia"))
        else:
            itens.append(Item(p.nome, "erro", feito.mensagem))
    resumo = Resumo(base.strip(), tuple(itens))
    log.info(
        "Contas por turno: %s criadas, %s já existiam, %s com erro",
        resumo.criados,
        resumo.existentes,
        resumo.erros,
    )
    return resumo


def configurar(
    nome: str,
    turnos: Iterable[str],
    sufixo: str,
    *,
    renomear: bool,
    com_sufixo: bool = False,
    protegidas_: frozenset[str] = frozenset({contas.SUPORTE_PADRAO.lower()}),
    rodar: Rodar = powershell,
) -> Resumo:
    """Renomeia (se `renomear`) e cria as contas. Se o renomear falhar, nenhuma conta é criada:
    elas levariam um nome que o computador não vai ter."""
    nome = identificacao.normalizar(nome)
    marcados = tuple(turnos)
    renomeio = identificacao.renomear(nome, rodar=rodar) if renomear else None
    if renomeio is not None and not renomeio.ok:
        return Resumo(nome, (), renomeio)
    return replace(
        criar(nome, marcados, sufixo, com_sufixo=com_sufixo, protegidas_=protegidas_, rodar=rodar),
        renomeio=renomeio,
    )
