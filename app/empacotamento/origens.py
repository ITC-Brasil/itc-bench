"""Origem dos binários do pacote (ADR-025): lista fechada, sem o `PATH` da máquina de build.

A análise de dependências do PyInstaller procura DLL também no `PATH`; uma DLL de qualquer
programa da máquina de build entraria no pacote e rodaria elevada nos notebooks. O `.spec` chama
`conferir` depois da `Analysis` e o build falha se algum binário vier de fora das raízes.
"""

import ctypes
import os
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import PureWindowsPath


def raizes() -> dict[str, str]:
    """Nome → pasta: Python base (inclui `DLLs`), ambiente do projeto e System32 (pela API)."""
    buffer = ctypes.create_unicode_buffer(260)
    if not ctypes.WinDLL("kernel32").GetSystemDirectoryW(buffer, len(buffer)):
        raise ctypes.WinError()
    return {"python": sys.base_prefix, "projeto": sys.prefix, "system32": buffer.value}


def classificar(origem: str, raizes_: dict[str, str]) -> str | None:
    """Nome da raiz que contém `origem` (a mais longa), ou None."""
    alvo = os.path.normcase(os.path.abspath(origem))  # noqa: PTH100 — sem seguir link
    achadas = [
        (len(pasta), nome)
        for nome, pasta in raizes_.items()
        if alvo.startswith(os.path.normcase(os.path.abspath(pasta)).rstrip("\\/") + os.sep)  # noqa: PTH100
    ]
    return max(achadas)[1] if achadas else None


def do_sistema(destino: str) -> bool:
    """UCRT (`ucrtbase.dll` e os conjuntos `api-ms-win-*`): parte do Windows 10/11, resolvido pelo
    carregador. O PyInstaller só os coleta quando acha cópias no `PATH` (ex.: a pasta de um JDK).
    """
    nome = PureWindowsPath(destino).name.lower()
    return nome == "ucrtbase.dll" or nome.startswith("api-ms-win-")


def separar_do_sistema(
    binarios: list[tuple[str, str, str]],
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """(binários que vão no pacote, nomes do UCRT tirados — para o log do build)."""
    tirados = sorted(b[0] for b in binarios if do_sistema(b[0]))
    return [b for b in binarios if not do_sistema(b[0])], tirados


def conferir(binarios: Iterable[tuple[str, str, str]], raizes_: dict[str, str]) -> Counter[str]:
    """Contagem por raiz; `SystemExit` listando o que veio de fora (o build para)."""
    contagem: Counter[str] = Counter()
    fora = []
    for destino, origem, _tipo in binarios:
        if nome := classificar(origem, raizes_):
            contagem[nome] += 1
        else:
            fora.append(f"{destino} <- {origem}")
    if fora:
        raise SystemExit("Binário de origem não permitida (ADR-025):\n" + "\n".join(fora))
    return contagem
