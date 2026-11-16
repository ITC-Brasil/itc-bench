"""Perfil de uma conta local criado sem entrar nela (ADR-050), por ctypes, sem processo.

`CreateProfile` (`userenv.dll`) faz o que o primeiro logon faria com o perfil: copia o perfil
padrão para `C:\\Users\\<nome>`, com o `NTUSER.DAT`, e registra em `ProfileList`. Não precisa da
senha da conta, só de administrador. Com o perfil pronto, Políticas, Aparência e Limpeza já
aceitam a conta (deixam de recusar com "sem perfil"). Nada aqui grava log; o caminho do perfil
nunca sai daqui, só o código.
"""

import ctypes
import re
from ctypes import wintypes

JA_EXISTE = -2147024713  # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS), 0x800700B7
RECUSADO = -2147024809  # E_INVALIDARG, 0x80070057: SID ou nome fora do formato
_SID_LOCAL = re.compile(r"^S-1-5-21-\d+-\d+-\d+-\d+$")
# Regras de nome de conta local do Windows: 1 a 20 caracteres, sem controle nem "/\[]:;|=,+*?<>@,
# e sem terminar em ponto ou espaço. O nome vira o nome da pasta do perfil.
_NOME = re.compile(r'^[^\x00-\x1f\x7f"/\\\[\]:;|=,+*?<>@]{1,20}$')
_TAMANHO = 260  # MAX_PATH


def _userenv() -> ctypes.WinDLL:
    u = ctypes.WinDLL("userenv", use_last_error=True)
    u.CreateProfile.restype = ctypes.c_long  # HRESULT
    u.CreateProfile.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    return u


def criar(sid: str, nome: str) -> int:
    """Cria o perfil da conta; devolve 0, `JA_EXISTE` ou o HRESULT da falha."""
    if not _SID_LOCAL.fullmatch(sid) or not _NOME.fullmatch(nome) or nome.endswith((".", " ")):
        return RECUSADO
    caminho = ctypes.create_unicode_buffer(_TAMANHO)
    return int(_userenv().CreateProfile(sid, nome, caminho, _TAMANHO))
