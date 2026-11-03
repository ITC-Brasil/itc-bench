"""Pastas do app. Nada é criado no import: só `inicializar()` mexe no disco."""

import os
from pathlib import Path


def _base(variavel: str) -> Path:
    valor = os.environ.get(variavel)
    if not valor:
        raise RuntimeError(f"Variável de ambiente {variavel} ausente.")
    return Path(valor) / "ITC" / "Bench"


def dados() -> Path:
    r"""%ProgramData%\ITC\Bench: dados da máquina, comuns a todos os usuários."""
    return _base("PROGRAMDATA")


def logs() -> Path:
    return dados() / "logs"


def preferencias() -> Path:
    r"""%LOCALAPPDATA%\ITC\Bench: preferências de UI do usuário (nunca senha)."""
    return _base("LOCALAPPDATA")


def inicializar() -> None:
    """Cria as pastas. Chamado uma vez, no início do app."""
    for pasta in (dados(), logs(), preferencias()):
        pasta.mkdir(parents=True, exist_ok=True)
