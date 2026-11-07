"""Registro (ADR-023, item 8), sem Qt: leitura do `bench.log` e dos rotacionados, só leitura.

Exportar grava só as linhas filtradas, com o nome do computador, os nomes das contas locais e
`X:\\Users\\<nome>` trocados por marcadores. Nada é acrescentado.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from itc_bench.nucleo import caminhos

NOME = "bench.log"
ROTACIONADOS = 4
LIMITE = 5000
NIVEIS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
CABECA = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:,\d+)? (DEBUG|INFO|WARNING|ERROR|CRITICAL) "
    r"\[([^\]]*)\] (.*)$"
)
PERFIL = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\/:*?\"<>|\r\n\s]+")


@dataclass(frozen=True)
class Linha:
    data: str
    nivel: str
    tecnico: str
    texto: str

    def __str__(self) -> str:
        return f"{self.data} {self.nivel} [{self.tecnico}] {self.texto}"


def arquivos(pasta: Path | None = None) -> list[Path]:
    """Do mais antigo para o mais novo; só os nomes conhecidos, sem seguir link."""
    pasta = pasta or caminhos.logs()
    nomes = [f"{NOME}.{n}" for n in range(ROTACIONADOS, 0, -1)] + [NOME]
    return [p for n in nomes if (p := pasta / n).is_file() and not p.is_symlink()]


def interpretar(texto: str) -> list[Linha]:
    linhas: list[Linha] = []
    for bruta in texto.splitlines():
        m = CABECA.match(bruta)
        if m:
            linhas.append(Linha(m[1], m[2], m[3], m[4]))
        elif linhas and bruta.strip():  # traceback: continua a linha anterior
            ult = linhas[-1]
            linhas[-1] = Linha(ult.data, ult.nivel, ult.tecnico, f"{ult.texto}\n{bruta}")
    return linhas


def ler(pasta: Path | None = None, limite: int = LIMITE) -> list[Linha]:
    linhas: list[Linha] = []
    for p in arquivos(pasta):
        linhas += interpretar(p.read_text("utf-8", errors="replace"))
    return linhas[-limite:]


def filtrar(linhas: Iterable[Linha], nivel: str = "INFO", texto: str = "") -> list[Linha]:
    minimo = NIVEIS.index(nivel) if nivel in NIVEIS else 0
    busca = texto.casefold().strip()
    return [
        ln
        for ln in linhas
        if NIVEIS.index(ln.nivel) >= minimo and (not busca or busca in str(ln).casefold())
    ]


def mascarar(texto: str, computador: str, contas: Sequence[str]) -> str:
    saida = PERFIL.sub("<perfil>", texto)
    if computador:
        saida = re.sub(rf"(?i)(?<![\w-]){re.escape(computador)}(?![\w-])", "<computador>", saida)
    for n, nome in enumerate(sorted({c for c in contas if c.strip()}, key=len, reverse=True), 1):
        saida = re.sub(rf"(?i)(?<![\w.-]){re.escape(nome)}(?![\w.-])", f"<conta-{n}>", saida)
    return saida


def exportar(linhas: Iterable[Linha], destino: Path, computador: str, contas: Sequence[str]) -> int:
    texto = [mascarar(str(ln), computador, contas) for ln in linhas]
    destino.write_text("\n".join(texto) + ("\n" if texto else ""), "utf-8")
    return len(texto)
