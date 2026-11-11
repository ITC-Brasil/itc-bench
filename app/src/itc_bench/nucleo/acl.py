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
# Pasta protegida (ADR-011, ADR-013): sem Usuários, porque DPAPI de máquina qualquer um decifra.
SDDL_PROTEGIDO = "O:BAD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
# Dono Administradores e DACL vazia sem proteção: o item só herda do pai.
_SO_HERDA = "O:BAD:"

_SE_FILE_OBJECT = 1
_OWNER = 0x1
_DACL = 0x4
_PROTECTED_DACL = 0x80000000
_UNPROTECTED_DACL = 0x20000000
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


def proteger(raiz: Path, sddl: str = SDDL, exceto: Path | None = None) -> None:
    """Aplica o SDDL na raiz e em tudo dentro dela, trocando o dono de arquivos de terceiros.

    `exceto`: subpasta que o reset não pode tocar (a protegida). O reset recursivo do Windows
    sobrescreve até DACL protegida (testado com os três modos de `TreeSetNamedSecurityInfoW`),
    o que daria leitura a Usuários na pasta protegida até ela ser refeita.
    """
    verificar_reparse(raiz)
    falhas = _aplicar(raiz, sddl, exceto)
    if any(codigo == _ERROR_ACCESS_DENIED for _, codigo in falhas):
        _habilitar_privilegios()
        try:
            falhas = _aplicar(raiz, sddl, exceto)
        finally:
            _habilitar_privilegios(ligar=False)  # não ficam ligados para o resto da execução
    # Junction criada entre a primeira checagem e o ACL desviaria o log. Agora quem não é admin
    # não cria mais nada ali, então a segunda checagem fecha a corrida.
    verificar_reparse(raiz)
    if falhas:
        lista = "; ".join(f"{nome}: {ctypes.FormatError(codigo)}" for nome, codigo in falhas[:5])
        raise ErroAcl(falhas[0][1], f"ACL não aplicado em {len(falhas)} item(ns): {lista}")


def proteger_segredos(raiz: Path, protegida: Path) -> None:
    """ACL da árvore sem tocar na pasta protegida; depois a protegida, e confere dono e DACL."""
    protegida.mkdir(parents=True, exist_ok=True)
    proteger(raiz, exceto=protegida)
    proteger(protegida, SDDL_PROTEGIDO)
    if (atual := sddl_atual(protegida)) != SDDL_PROTEGIDO:
        raise ErroAcl(0, f"Pasta protegida {protegida} com ACL inesperado: {atual}")


def sddl_atual(caminho: Path) -> str:
    """Dono e DACL do item em SDDL."""
    descritor = ctypes.c_void_p()
    codigo = _advapi.GetNamedSecurityInfoW(
        str(caminho),
        _SE_FILE_OBJECT,
        _OWNER | _DACL,
        None,
        None,
        None,
        None,
        ctypes.byref(descritor),
    )
    if codigo:
        raise ctypes.WinError(codigo)
    texto = wintypes.LPWSTR()
    try:
        if not _advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descritor, 1, _OWNER | _DACL, ctypes.byref(texto), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        valor = texto.value or ""
        _kernel32.LocalFree(texto)
        return valor
    finally:
        _kernel32.LocalFree(descritor)


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
_advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
_advapi.SetNamedSecurityInfoW.argtypes = (
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)
_advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
_advapi.GetNamedSecurityInfoW.argtypes = (
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
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


def _aplicar(raiz: Path, sddl: str = SDDL, exceto: Path | None = None) -> list[tuple[str, int]]:
    """Devolve (item, código de erro) de cada item que falhou."""
    if exceto is None or not exceto.exists():
        return _definir(raiz, sddl, _PROTECTED_DACL, arvore=True)
    # Sem recursão na raiz e nas pastas a caminho da exceção (o Windows propaga a herança e
    # pula a DACL protegida); com recursão em cada irmã, que volta a só herdar.
    falhas = _definir(raiz, sddl, _PROTECTED_DACL, arvore=False)
    partes = exceto.relative_to(raiz).parts
    caminho = [raiz.joinpath(*partes[:i]) for i in range(1, len(partes))]
    for pasta in [raiz, *caminho]:
        if pasta != raiz:
            falhas += _definir(pasta, _SO_HERDA, _UNPROTECTED_DACL, arvore=False)
        for item in pasta.iterdir():
            if item != exceto and item not in caminho:
                falhas += _definir(item, _SO_HERDA, _UNPROTECTED_DACL, arvore=True)
    return falhas


def _definir(alvo: Path, sddl: str, protecao: int, *, arvore: bool) -> list[tuple[str, int]]:
    falhas: list[tuple[str, int]] = []

    def anotar(nome: str, codigo: int, _ajuste: object, _args: object, _aplicado: bool) -> None:
        if codigo:
            falhas.append((nome, codigo))

    progresso = _Progresso(anotar)
    descritor = ctypes.c_void_p()
    if not _advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descritor), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        dono, padrao = ctypes.c_void_p(), wintypes.BOOL()
        dacl, presente = ctypes.c_void_p(), wintypes.BOOL()
        _advapi.GetSecurityDescriptorOwner(descritor, ctypes.byref(dono), ctypes.byref(padrao))
        _advapi.GetSecurityDescriptorDacl(
            descritor, ctypes.byref(presente), ctypes.byref(dacl), ctypes.byref(padrao)
        )
        if not dacl:
            raise ErroAcl(0, "SDDL sem DACL")  # DACL nula daria acesso total a todos
        flags = _OWNER | _DACL | protecao
        if arvore:
            codigo = _advapi.TreeSetNamedSecurityInfoW(
                str(alvo),
                _SE_FILE_OBJECT,
                flags,
                dono,
                None,
                dacl,
                None,
                _TREE_SEC_INFO_RESET,
                progresso,
                _PROGRESS_INVOKE_ON_ERROR,
                None,
            )
        else:
            codigo = _advapi.SetNamedSecurityInfoW(
                str(alvo), _SE_FILE_OBJECT, flags, dono, None, dacl, None
            )
        if codigo:
            falhas.append((str(alvo), int(codigo)))
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


def habilitar_privilegios() -> None:
    """Liga SeTakeOwnership e SeRestore no token do Bench. Os processos filhos (takeown,
    icacls) herdam o token com eles ligados: o `icacls /setowner` para outra conta (o
    TrustedInstaller, na Proteção do login) exige o SeRestore ligado (máquina real, 11/11/2026).
    Quem liga desliga com `desabilitar_privilegios` assim que terminar (ADR-022, emenda)."""
    _habilitar_privilegios()


def desabilitar_privilegios() -> None:
    """Desliga SeTakeOwnership e SeRestore de novo: ligados, o Bench e todo processo que ele
    abrir depois passariam por cima das permissões de arquivo."""
    _habilitar_privilegios(ligar=False)


def _habilitar_privilegios(ligar: bool = True) -> None:
    """Liga (ou desliga) SeTakeOwnership e SeRestore no token do processo (só valem em execução
    elevada)."""
    token = wintypes.HANDLE()
    # TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
    if not _advapi.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x20 | 0x8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for nome in _PRIVILEGIOS:
            # SE_PRIVILEGE_ENABLED para ligar; 0 desliga sem remover o privilégio do token.
            novo = _Privilegios(PrivilegeCount=1, Attributes=0x2 if ligar else 0)
            if not _advapi.LookupPrivilegeValueW(None, nome, ctypes.byref(novo.Luid)):
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.set_last_error(0)
            _advapi.AdjustTokenPrivileges(token, False, ctypes.byref(novo), 0, None, None)
            if erro := ctypes.get_last_error():  # ERROR_NOT_ALL_ASSIGNED também cai aqui
                raise ErroAcl(erro, f"Privilégio {nome} negado: {ctypes.FormatError(erro)}")
    finally:
        _kernel32.CloseHandle(token)
