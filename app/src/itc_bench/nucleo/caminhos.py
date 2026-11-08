"""Pastas do app. Nada é criado no import: só `inicializar()` mexe no disco."""

import ctypes
import os
import winreg
from pathlib import Path, PureWindowsPath

from itc_bench.nucleo import acl

CHAVE_PERFIS = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"


def _base(variavel: str) -> Path:
    valor = os.environ.get(variavel)
    if not valor:
        raise RuntimeError(f"Variável de ambiente {variavel} ausente.")
    return Path(valor) / "ITC" / "Bench"


def _unidade_do_sistema() -> str:
    """Unidade do Windows pela API: `SystemDrive` do ambiente o usuário troca em HKCU."""
    buffer = ctypes.create_unicode_buffer(260)
    if not ctypes.WinDLL("kernel32").GetSystemWindowsDirectoryW(buffer, len(buffer)):
        raise ctypes.WinError()
    return PureWindowsPath(buffer.value).drive


def pasta_do_sistema(valor: str) -> Path:
    r"""Pasta de `ProfileList` (HKLM) sem expandir pelo ambiente (Módulo 14).

    `PROGRAMDATA`, `SystemDrive` e o próprio `SHGetKnownFolderPath` seguem variáveis de usuário
    (`HKCU\Environment`), que valem no processo elevado da mesma conta.
    """
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_PERFIS) as chave:
        cru, _ = winreg.QueryValueEx(chave, valor)
    texto = str(cru)
    marca = "%systemdrive%"
    if texto.lower().startswith(marca):
        texto = _unidade_do_sistema() + texto[len(marca) :]
    if "%" in texto or not PureWindowsPath(texto).is_absolute():
        raise RuntimeError(f"Pasta {valor} do Windows fora do esperado.")
    return Path(texto)


def programdata() -> Path:
    return pasta_do_sistema("ProgramData")


def dados() -> Path:
    r"""%ProgramData%\ITC\Bench: dados da máquina, comuns a todos os usuários."""
    return programdata() / "ITC" / "Bench"


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
