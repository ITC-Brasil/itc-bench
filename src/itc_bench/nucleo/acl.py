r"""ACL explícito em %ProgramData%\ITC (ADR-011), pela API do Windows, sem processo externo.

Dono Administradores; sem herança; SYSTEM e Administradores (S-1-5-32-544) controle total;
Usuários (S-1-5-32-545) leitura e execução. Os aliases SDDL `SY`, `BA` e `BU` são SIDs, não
nomes localizados.
"""

import ctypes
import os
import stat
from ctypes import wintypes
from pathlib import Path

SDDL = "O:BAD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)"

_SE_FILE_OBJECT = 1
_OWNER = 0x1
_DACL = 0x4
_PROTECTED_DACL = 0x80000000
_TREE_SEC_INFO_RESET = 2
_PROGRESS_INVOKE_ON_ERROR = 3
_ERROR_ACCESS_DENIED = 5
_PRIVILEGIOS = ("SeTakeOwnershipPrivilege", "SeRestorePrivilege")


class ErroAcl(OSError):
    """O ACL não pôde ser aplicado."""


class PontoDeReparse(ErroAcl):
    """Junction ou link simbólico dentro da árvore: pode desviar a escrita do processo elevado."""


def verificar_reparse(raiz: Path) -> None:
    """Levanta `PontoDeReparse` se a raiz ou qualquer item dentro dela for ponto de reparse."""
    if not raiz.exists():
        return
    pendentes = [raiz]
    while pendentes:
        item = pendentes.pop()
        atributos = os.lstat(item).st_file_attributes
        if atributos & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise PontoDeReparse(f"Ponto de reparse em {item}; ACL não aplicado.")
        if atributos & stat.FILE_ATTRIBUTE_DIRECTORY:
            pendentes.extend(item.iterdir())


def proteger(raiz: Path) -> None:
    """Aplica o SDDL na raiz e em tudo dentro dela, trocando o dono de arquivos de terceiros."""
    verificar_reparse(raiz)
    falhas = _aplicar(raiz)
    if any(codigo == _ERROR_ACCESS_DENIED for _, codigo in falhas):
        _habilitar_privilegios()
        falhas = _aplicar(raiz)
    if falhas:
        lista = "; ".join(f"{nome}: {ctypes.FormatError(codigo)}" for nome, codigo in falhas[:5])
        raise ErroAcl(falhas[0][1], f"ACL não aplicado em {len(falhas)} item(ns): {lista}")


_advapi = ctypes.WinDLL("advapi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi.TreeSetNamedSecurityInfoW.restype = wintypes.DWORD
_advapi.TreeSetNamedSecurityInfoW.argtypes = (
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_void_p,
)
# Por item, a falha só chega por este callback; o retorno da função pode ser sucesso.
_Progresso = ctypes.WINFUNCTYPE(
    None, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL
)
_kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_advapi.OpenProcessToken.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
)
_advapi.AdjustTokenPrivileges.argtypes = (
    wintypes.HANDLE,
    wintypes.BOOL,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


def _aplicar(raiz: Path) -> list[tuple[str, int]]:
    """Devolve (item, código de erro) de cada item que falhou."""
    falhas: list[tuple[str, int]] = []

    def anotar(nome: str, codigo: int, _ajuste: object, _args: object, _aplicado: bool) -> None:
        if codigo:
            falhas.append((nome, codigo))

    progresso = _Progresso(anotar)
    descritor = ctypes.c_void_p()
    if not _advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        SDDL, 1, ctypes.byref(descritor), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        dono, padrao = ctypes.c_void_p(), wintypes.BOOL()
        dacl, presente = ctypes.c_void_p(), wintypes.BOOL()
        _advapi.GetSecurityDescriptorOwner(descritor, ctypes.byref(dono), ctypes.byref(padrao))
        _advapi.GetSecurityDescriptorDacl(
            descritor, ctypes.byref(presente), ctypes.byref(dacl), ctypes.byref(padrao)
        )
        codigo = int(
            _advapi.TreeSetNamedSecurityInfoW(
                str(raiz),
                _SE_FILE_OBJECT,
                _OWNER | _DACL | _PROTECTED_DACL,
                dono,
                None,
                dacl,
                None,
                _TREE_SEC_INFO_RESET,
                progresso,
                _PROGRESS_INVOKE_ON_ERROR,
                None,
            )
        )
        if codigo:
            falhas.append((str(raiz), codigo))
        return falhas
    finally:
        _kernel32.LocalFree(descritor)


class _Luid(ctypes.Structure):
    _fields_ = (("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG))


class _Privilegios(ctypes.Structure):
    _fields_ = (
        ("PrivilegeCount", wintypes.DWORD),
        ("Luid", _Luid),
        ("Attributes", wintypes.DWORD),
    )


def _habilitar_privilegios() -> None:
    """Liga SeTakeOwnership e SeRestore no token do processo (só valem em execução elevada)."""
    token = wintypes.HANDLE()
    # TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
    if not _advapi.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x20 | 0x8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for nome in _PRIVILEGIOS:
            novo = _Privilegios(PrivilegeCount=1, Attributes=0x2)  # SE_PRIVILEGE_ENABLED
            if not _advapi.LookupPrivilegeValueW(None, nome, ctypes.byref(novo.Luid)):
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.set_last_error(0)
            _advapi.AdjustTokenPrivileges(token, False, ctypes.byref(novo), 0, None, None)
            if erro := ctypes.get_last_error():  # ERROR_NOT_ALL_ASSIGNED também cai aqui
                raise ErroAcl(erro, f"Privilégio {nome} negado: {ctypes.FormatError(erro)}")
    finally:
        _kernel32.CloseHandle(token)
