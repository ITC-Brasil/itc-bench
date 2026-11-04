"""DPAPI em escopo de máquina (ADR-013), por ctypes, sem pywin32.

Escopo de máquina porque o Bench roda elevado com contas de Windows diferentes na mesma bancada.
Qualquer usuário local decifra DPAPI de máquina: o que protege o arquivo é o ACL da pasta
protegida (`nucleo/acl.py`), não a cifra.
"""

import ctypes
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4
_ENTROPIA = b"ITC Bench logins offline"


class _Blob(ctypes.Structure):
    _fields_ = (("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char)))


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
for _nome in ("CryptProtectData", "CryptUnprotectData"):
    _f = getattr(_crypt32, _nome)
    _f.restype = wintypes.BOOL
    _f.argtypes = (
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    )


def _blob(dados: bytes) -> tuple[_Blob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(dados, len(dados))
    return _Blob(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _chamar(funcao: str, dados: bytes, flags: int) -> bytes:
    entrada, _b1 = _blob(dados)
    entropia, _b2 = _blob(_ENTROPIA)
    saida = _Blob()
    descricao = ctypes.c_void_p() if funcao == "CryptUnprotectData" else None
    ok = getattr(_crypt32, funcao)(
        ctypes.byref(entrada),
        ctypes.byref(descricao) if descricao is not None else None,
        ctypes.byref(entropia),
        None,
        None,
        flags,
        ctypes.byref(saida),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(saida.pbData, ctypes.c_void_p))
        if descricao:
            _kernel32.LocalFree(descricao)


def cifrar(dados: bytes) -> bytes:
    return _chamar(
        "CryptProtectData", dados, _CRYPTPROTECT_UI_FORBIDDEN | _CRYPTPROTECT_LOCAL_MACHINE
    )


def decifrar(dados: bytes) -> bytes:
    return _chamar("CryptUnprotectData", dados, _CRYPTPROTECT_UI_FORBIDDEN)
