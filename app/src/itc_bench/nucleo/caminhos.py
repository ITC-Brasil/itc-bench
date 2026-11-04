"""Pastas do app. Nada é criado no import: só `inicializar()` mexe no disco."""

import os
from pathlib import Path

from itc_bench.nucleo import acl


def _base(variavel: str) -> Path:
    valor = os.environ.get(variavel)
    if not valor:
        raise RuntimeError(f"Variável de ambiente {variavel} ausente.")
    return Path(valor) / "ITC" / "Bench"


def dados() -> Path:
    r"""%ProgramData%\ITC\Bench: dados da máquina, comuns a todos os usuários."""
    return _base("PROGRAMDATA")


def protegida() -> Path:
    r"""%ProgramData%\ITC\Bench\protegido: só SYSTEM e Administradores (ADR-013)."""
    return dados() / "protegido"


def logs() -> Path:
    return dados() / "logs"


def preferencias() -> Path:
    r"""%LOCALAPPDATA%\ITC\Bench: preferências de UI do usuário (nunca senha)."""
    return _base("LOCALAPPDATA")


def inicializar(admin: bool = False) -> None:
    r"""Cria as pastas. Chamado uma vez, no início do app, antes de abrir o log.

    Elevado, aplica o ACL de %ProgramData%\ITC (ADR-011); recusa ponto de reparse antes de criar.
    """
    raiz = dados().parent
    if admin:
        acl.verificar_reparse(raiz)
    for pasta in (dados(), logs(), preferencias()):
        pasta.mkdir(parents=True, exist_ok=True)
    if admin:
        # Também quando a pasta já existe: reaplica o ACL e confere dono e DACL (ADR-013).
        acl.proteger_segredos(raiz, protegida())
