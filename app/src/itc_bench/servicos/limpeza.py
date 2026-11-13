"""Limpeza de manutenção (ADR-023), sem Qt.

Lista fechada de itens; o trecho tem as raízes fixas, nunca segue reparse point e devolve só
números por id (nenhum caminho chega ao Python nem ao log). Prévia antes, confirmação na tela.
"""

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

from itc_bench.nucleo.log import log
from itc_bench.servicos import contas, executor

Rodar = Callable[..., executor.Resultado]
RECURSOS = resources.files("itc_bench.recursos") / "limpeza"
TIMEOUT_PREVIA = 300
TIMEOUT_LIMPAR = 900

ITENS: tuple[tuple[str, str], ...] = (
    ("temp_sistema", "Temporários do sistema"),
    ("temp_usuarios", "Temporários das contas"),
    ("lixeira", "Lixeira de todas as contas"),
    ("windows_update", "Cache do Windows Update"),
    ("relatorios_erro", "Relatórios de erro do Windows"),
)
NOMES = dict(ITENS)
CODIGOS = {
    "reinicio_pendente": "atualização esperando reinício; reinicie e limpe de novo",
    "servico_nao_parou": "o serviço do Windows Update não parou a tempo",
    "servico_nao_voltou": "o serviço do Windows Update não voltou; reinicie o computador",
    "reparse": "a pasta é um link; nada foi apagado",
    "fora": "item fora da pasta conhecida ignorado",
}


@dataclass(frozen=True)
class Item:
    id: str
    arquivos: int
    bytes: int
    em_uso: int
    limpo: bool
    codigo: str = ""

    @property
    def ok(self) -> bool:
        return self.limpo and self.codigo not in ("reparse", "fora")

    @property
    def motivo(self) -> str:
        return CODIGOS.get(self.codigo, self.codigo)


def tamanho(n: int) -> str:
    for unidade, fator in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= fator:
            return f"{n / fator:.1f} {unidade}".replace(".", ",")
    return f"{n} B"


def _validar(ids: Iterable[str]) -> list[str]:
    lista = list(dict.fromkeys(ids))
    for i in lista:
        if i not in NOMES:
            raise ValueError(f"Item de limpeza desconhecido: {i!r}")
    return lista


def _rodar(acao: str, ids: Iterable[str], rodar: Rodar) -> list[Item]:
    lista = _validar(ids)
    if not lista:
        return []
    r = rodar(
        (RECURSOS / "limpeza.ps1").read_text("utf-8"),
        timeout=TIMEOUT_LIMPAR if acao == "limpar" else TIMEOUT_PREVIA,
        acao=acao,
        itens=",".join(lista),
    )
    if not r.ok:
        log.error(
            "Limpeza: %s falhou (código %s)", acao, "tempo_esgotado" if r.esgotado else r.codigo
        )
        raise RuntimeError("tempo esgotado" if r.esgotado else f"código {r.codigo}")
    try:
        cru = json.loads(r.saida)
        itens = [
            Item(
                str(d["id"]),
                int(d["arquivos"]),
                int(d["bytes"]),
                int(d["em_uso"]),
                bool(d["limpo"]),
                str(d.get("codigo") or ""),
            )
            for d in cru
            if isinstance(d, dict) and d.get("id") in NOMES
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as erro:
        raise RuntimeError(f"Saída inválida ({type(erro).__name__}).") from None
    for i in itens:
        log.info(
            "Limpeza: %s item=%s arquivos=%s bytes=%s em_uso=%s codigo=%s",
            acao,
            i.id,
            i.arquivos,
            i.bytes,
            i.em_uso,
            i.codigo or "0",
        )
    return itens


def previa(ids: Iterable[str], *, rodar: Rodar = executor.powershell) -> list[Item]:
    return _rodar("previa", ids, rodar)


def limpar(ids: Iterable[str], *, rodar: Rodar = executor.powershell) -> list[Item]:
    return _rodar("limpar", ids, rodar)


# ---------------------------------------------------------------- limpeza de contas (ADR-042)

CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("pessoais", "Pastas pessoais"),
    ("temporarios", "Temporários e caches do Windows"),
    ("navegadores", "Cache dos navegadores e do Teams"),
    ("programas", "Programas só da conta"),
)
NOMES_CATEGORIA = dict(CATEGORIAS)
DETALHE_CATEGORIA = {
    "pessoais": "Área de Trabalho, Documentos, Downloads, Imagens, Vídeos, Músicas e Jogos salvos",
    "temporarios": "Temp, despejos de falha, cache de sombreadores, cache da internet, "
    "relatórios de erro e miniaturas",
    "navegadores": "cache do Edge, do Chrome, do Firefox e do Teams clássico; favoritos, senhas "
    "e configurações ficam",
    "programas": r"programas instalados só para a conta (AppData\Local\Programs)",
}
RECUSAS_CONTA = {
    "nativo": "Administrador nativo: nunca é limpo",
    "suporte": "conta Suporte: nunca é limpa",
    "restrita": "conta Gestão: o Bench não altera (ADR-036)",
    "dono": "é a conta que está rodando o Bench",
    "sessao": "sessão aberta: saia da conta ou use Contas › Encerrar sessões…",
    "sem_perfil": "a conta ainda não tem perfil (nunca entrou)",
    "sid_invalido": "conta inválida",
    "reparse": "a pasta do perfil é um link; nada foi apagado",
    "fora": "item fora da pasta conhecida ignorado",
    "erro_UnauthorizedAccessException": "sem acesso ao perfil: precisa de administrador",
}
TIMEOUT_CONTAS = 3600


@dataclass(frozen=True)
class ItemConta:
    sid: str
    categoria: str  # vazio quando a conta inteira foi recusada
    arquivos: int
    bytes: int
    em_uso: int
    codigo: str = ""

    @property
    def motivo(self) -> str:
        return RECUSAS_CONTA.get(self.codigo, self.codigo)


def _suporte(protegidas_: Iterable[str]) -> set[str]:
    """Nomes da Suporte em minúsculas; `Suporte` sempre entra, com ou sem cadastro (ADR-017)."""
    return {p.lower() for p in protegidas_} | {contas.SUPORTE_PADRAO.lower()}


def recusa_conta(conta: Any, protegidas_: Iterable[str]) -> str:
    """Código da recusa (chave de RECUSAS_CONTA) ou vazio. O trecho confere de novo."""
    if conta.nativo:
        return "nativo"
    if conta.nome.lower() in _suporte(protegidas_):
        return "suporte"
    if conta.nome.lower() in contas.RESTRITAS:
        return "restrita"
    if not conta.perfil:
        return "sem_perfil"
    if conta.logada or conta.carregado:
        return "sessao"
    return ""


def _rodar_contas(
    acao: str, contas_: Sequence[Any], protegidas_: Iterable[str], rodar: Rodar
) -> list[ItemConta]:
    prot = sorted(_suporte(protegidas_))
    validas = [c for c in contas_ if not recusa_conta(c, prot)]
    saida = [
        ItemConta(c.sid, "", 0, 0, 0, recusa_conta(c, prot)) for c in contas_ if c not in validas
    ]
    for c in saida:
        log.warning("Limpeza de contas: %s recusada (%s)", acao, c.codigo)
    if not validas:
        return saida
    sids = [c.sid for c in validas]
    r = rodar(
        (RECURSOS / "contas.ps1").read_text("utf-8"),
        timeout=TIMEOUT_CONTAS if acao == "limpar" else TIMEOUT_PREVIA,
        acao=acao,
        sids=",".join(sids),
        protegidas=",".join(prot),
    )
    if not r.ok:
        log.error(
            "Limpeza de contas: %s falhou (código %s)",
            acao,
            "tempo_esgotado" if r.esgotado else r.codigo,
        )
        raise RuntimeError("tempo esgotado" if r.esgotado else f"código {r.codigo}")
    try:
        cru = json.loads(r.saida)
        if isinstance(cru, dict):
            cru = [cru]
        for d in cru:
            n = int(d["n"])
            cat = str(d.get("categoria") or "")
            if not 1 <= n <= len(sids) or (cat and cat not in NOMES_CATEGORIA):
                continue
            saida.append(
                ItemConta(
                    sids[n - 1],
                    cat,
                    int(d["arquivos"]),
                    int(d["bytes"]),
                    int(d["em_uso"]),
                    str(d.get("codigo") or ""),
                )
            )
            log.info(
                "Limpeza de contas: %s conta=%d categoria=%s arquivos=%s bytes=%s em_uso=%s "
                "codigo=%s",
                acao,
                n,
                cat or "-",
                d["arquivos"],
                d["bytes"],
                d["em_uso"],
                d.get("codigo") or "0",
            )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as erro:
        raise RuntimeError(f"Saída inválida ({type(erro).__name__}).") from None
    return saida


def previa_contas(
    contas_: Sequence[Any], protegidas_: Iterable[str], *, rodar: Rodar = executor.powershell
) -> list[ItemConta]:
    return _rodar_contas("previa", contas_, protegidas_, rodar)


def limpar_contas(
    contas_: Sequence[Any], protegidas_: Iterable[str], *, rodar: Rodar = executor.powershell
) -> list[ItemConta]:
    return _rodar_contas("limpar", contas_, protegidas_, rodar)
