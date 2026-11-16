"""Encerrar sessões do Windows pela `wtsapi32` (ADR-049), por ctypes, sem processo.

`WTSLogoffSession` existe em todas as edições; o `logoff.exe` não existe no Windows Home. Quem
acha as sessões da conta é o trecho `recursos/contas/encerrar.ps1` (dono do `explorer.exe`);
aqui só se encerra um número de sessão já conferido. Nunca a sessão em que o Bench roda, nem a
sessão 0 (serviços). Nada aqui grava log; erro sai só com o código Win32.
"""

import ctypes
from ctypes import wintypes

WTS_SERVIDOR_LOCAL = None  # WTS_CURRENT_SERVER_HANDLE
ERRO_RECUSADA = 5  # ERROR_ACCESS_DENIED: sessão 0 ou a do próprio Bench


def _kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcessId.restype = wintypes.DWORD
    k.GetCurrentProcessId.argtypes = ()
    k.ProcessIdToSessionId.restype = wintypes.BOOL
    k.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    return k


def _wtsapi32() -> ctypes.WinDLL:
    w = ctypes.WinDLL("wtsapi32", use_last_error=True)
    w.WTSLogoffSession.restype = wintypes.BOOL
    w.WTSLogoffSession.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL)
    return w


def sessao_atual() -> int:
    """Número da sessão em que o Bench está rodando."""
    k = _kernel32()
    sessao = wintypes.DWORD()
    if not k.ProcessIdToSessionId(k.GetCurrentProcessId(), ctypes.byref(sessao)):
        raise OSError(ctypes.get_last_error(), "ProcessIdToSessionId")
    return int(sessao.value)


def encerrar(sessao: int) -> int:
    """Encerra a sessão e espera o logoff terminar; devolve 0 ou o erro Win32."""
    if sessao <= 0 or sessao == sessao_atual():
        return ERRO_RECUSADA
    if not _wtsapi32().WTSLogoffSession(WTS_SERVIDOR_LOCAL, sessao, True):
        return ctypes.get_last_error() or 1
    return 0
