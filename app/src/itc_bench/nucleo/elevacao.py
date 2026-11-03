"""Elevação de administrador (UAC).

A decisão (`precisa_elevar`, `comando_elevado`) é pura e testável; só `pedir_elevacao`
toca o Windows.
"""

import ctypes
import subprocess  # noqa: TID251 — só list2cmdline, para o ShellExecuteW
import sys
from pathlib import Path


def eh_admin() -> bool:
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def precisa_elevar(argv: list[str], admin: bool) -> bool:
    """`--dev` e `--teste` rodam sem administrador; o resto exige."""
    return not (admin or "--dev" in argv or "--teste" in argv)


def comando_elevado(argv: list[str], executavel: str, congelado: bool) -> tuple[str, list[str]]:
    """Executável e argumentos para reabrir o app elevado."""
    if congelado:
        return executavel, argv[1:]
    # Fora do PyInstaller, reabre como módulo; pythonw evita o console extra.
    pythonw = Path(executavel).with_name("pythonw.exe")
    exe = str(pythonw) if pythonw.exists() else executavel
    return exe, ["-m", "itc_bench", *argv[1:]]


def pedir_elevacao(argv: list[str]) -> bool:
    """Abre o UAC. True se o Windows aceitou criar o processo elevado."""
    exe, args = comando_elevado(argv, sys.executable, getattr(sys, "frozen", False))
    resultado: int = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, subprocess.list2cmdline(args), None, 1
    )
    # Maior que 32 = processo criado; 5 = usuário recusou.
    return resultado > 32
