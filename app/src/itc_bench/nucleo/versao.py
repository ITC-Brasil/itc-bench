r"""Versão numérica (ADR-019, ADR-020): a primeira sequência `\d+(\.\d+)*` do texto."""

import re
from typing import Literal

VERSAO = re.compile(r"\d+(?:\.\d+)*")

Comparacao = Literal["ausente", "velha", "igual", "nova"]


def versao(texto: str | None) -> tuple[int, ...] | None:
    """Primeira sequência numérica (`ad 8.0.14` → (8, 0, 14)); None se não houver."""
    achado = VERSAO.search(texto or "")
    return tuple(int(p) for p in achado.group().split(".")) if achado else None


def comparar(instalada: str | None, cadastro: str) -> Comparacao:
    if instalada is None:
        return "ausente"
    a, b = versao(instalada), versao(cadastro)
    if a is None or b is None:
        return "velha"  # ilegível: instala por cima
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return "igual" if a == b else "velha" if a < b else "nova"
