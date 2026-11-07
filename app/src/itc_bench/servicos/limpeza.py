"""Limpeza de manutenção (ADR-023), sem Qt.

Lista fechada de itens; o trecho tem as raízes fixas, nunca segue reparse point e devolve só
números por id (nenhum caminho chega ao Python nem ao log). Prévia antes, confirmação na tela.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import resources

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

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
