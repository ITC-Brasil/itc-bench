r"""Bench empacotado (ADR-025): ambiente endurecido, pasta de instalação conferida e mutex.

Roda antes do Qt. A conferência acontece depois de Python e Qt já terem carregado do pacote:
ela detecta uma pasta alterada, não impede a carga. Quem impede é a ACL de `Program Files`.
"""

import ctypes
import os
import re
import stat
import sys
from collections.abc import Callable
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from itc_bench.nucleo import acl, caminhos

# Só a plataforma de teste do CI passa; caminho de plugin nunca vem do ambiente.
QPA_PERMITIDAS = {"offscreen"}
PREFIXOS_LIMPOS = ("QT_", "QML", "PYTHON")
MUTEX = "ITCBench"  # mesmo nome do AppMutex do instalador (local e Global\)

TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
CONFIAVEIS = {"SY", "BA", TRUSTED_INSTALLER}
# CREATOR OWNER só aparece como modelo herdável: no filho vira o dono, que é um dos confiáveis.
IGNORADOS = {"CO"}
# Direitos SDDL (aliases de arquivo e os genéricos de diretório) em máscara.
_ALIAS = {
    "GA": 0x10000000,
    "GX": 0x20000000,
    "GW": 0x40000000,
    "GR": 0x80000000,
    "SD": 0x10000,
    "RC": 0x20000,
    "WD": 0x40000,
    "WO": 0x80000,
    "CC": 0x1,
    "DC": 0x2,
    "LC": 0x4,
    "SW": 0x8,
    "RP": 0x10,
    "WP": 0x20,
    "DT": 0x40,
    "LO": 0x80,
    "CR": 0x100,
    "FA": 0x1F01FF,
    "FR": 0x120089,
    "FW": 0x120116,
    "FX": 0x1200A0,
}
# Gravar, anexar, EA, apagar filho, atributos, DELETE, WRITE_DAC, WRITE_OWNER, GENERIC_ALL/WRITE.
ESCRITA = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000
_ACE = re.compile(r"\(([^)]*)\)")


class PastaAlterada(Exception):
    """A pasta do Bench instalado não é a esperada ou alguém além dos administradores grava nela."""


def congelado() -> bool:
    return bool(getattr(sys, "frozen", False))


def limpar_ambiente(ambiente: dict[str, str] | None = None) -> list[str]:
    """Tira `QT_*`, `QML*` e `PYTHON*` herdados de `HKCU\\Environment` (ajuste 1 do Módulo 15).

    Vale também no `uv run`. No congelado, o `QT_PLUGIN_PATH` volta apontando para o pacote.
    Devolve os nomes retirados (para o log; os valores nunca).
    """
    amb = os.environ if ambiente is None else ambiente
    retirados = [
        nome
        for nome in list(amb)
        if nome.upper().startswith(PREFIXOS_LIMPOS)
        and not (nome.upper() == "QT_QPA_PLATFORM" and amb[nome] in QPA_PERMITIDAS)
    ]
    for nome in retirados:
        del amb[nome]
    if congelado():
        amb["QT_PLUGIN_PATH"] = str(Path(sys._MEIPASS) / "PySide6" / "plugins")  # type: ignore[attr-defined]
    return sorted(retirados)


def restringir_dlls() -> None:
    """No congelado: DLL só da pasta do EXE, de System32 e do pacote; nunca do `PATH` do usuário.

    O gancho do PyInstaller para PySide6 põe o pacote no início do `PATH`, mas o `PATH` também
    leva as pastas do usuário. `LOAD_LIBRARY_SEARCH_DEFAULT_DIRS` tira o `PATH` da busca.
    """
    if not congelado():
        return
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.AddDllDirectory.argtypes = (ctypes.c_wchar_p,)
    k32.AddDllDirectory.restype = ctypes.c_void_p
    if not k32.SetDefaultDllDirectories(0x1000):  # LOAD_LIBRARY_SEARCH_DEFAULT_DIRS
        raise ctypes.WinError(ctypes.get_last_error())
    pacote = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    for pasta in (pacote, pacote / "PySide6"):
        if not k32.AddDllDirectory(str(pasta)):
            raise ctypes.WinError(ctypes.get_last_error())


def caminho_fora_do_pacote() -> list[str]:
    """Entradas de `sys.path` fora do pacote (`PYTHONPATH` lido pelo bootloader apareceria aqui)."""
    if not congelado():
        return []
    pacote = os.path.normcase(sys._MEIPASS)  # type: ignore[attr-defined]
    return [p for p in sys.path if not os.path.normcase(os.path.abspath(p)).startswith(pacote)]  # noqa: PTH100 — sem seguir link


def escrita_de_terceiros(sddl: str) -> list[str]:
    """Problemas de dono e DACL pelo critério do ADR-020 (vazia = ok). Sem texto localizado."""
    problemas = []
    dono = sddl.split("O:", 1)[1].split("G:", 1)[0].split("D:", 1)[0] if "O:" in sddl else ""
    if dono not in CONFIAVEIS:
        problemas.append(f"dono {dono or '?'}")
    dacl = sddl.split("D:", 1)[1] if "D:" in sddl else ""
    if not dacl or dacl.startswith("NO_ACCESS_CONTROL") or "(" not in dacl:
        problemas.append("DACL nula")
    for ace in _ACE.findall(dacl):
        partes = ace.split(";")
        if len(partes) < 6 or partes[0] in ("D", "OD", "XD", "AU", "ML"):
            continue  # negação e auditoria não dão acesso
        sid, direitos = partes[5], partes[2]
        if sid in CONFIAVEIS or sid in IGNORADOS:
            continue
        if _mascara(direitos) & ESCRITA:
            problemas.append(f"escrita para {sid}")
    return problemas


def _mascara(direitos: str) -> int:
    if direitos.lower().startswith("0x"):
        return int(direitos, 16)
    pares = [direitos[i : i + 2] for i in range(0, len(direitos), 2)]
    return sum(_ALIAS.get(p, ESCRITA) for p in pares)  # alias desconhecido conta como escrita


def conferir_pasta(exe: Path, esperada: Path, ler: Callable[[Path], str] = acl.sddl_atual) -> None:
    """Levanta `PastaAlterada` se o EXE não estiver na pasta fixa ou ela não estiver protegida.

    Confere a pasta, o pai (`Program Files\\ITC`) e tudo dentro dela: sem reparse point, dono e
    DACL só com escrita de SYSTEM, Administradores e TrustedInstaller. Não corrige nada: os
    arquivos podem já ter sido trocados.
    """
    pasta = exe.parent
    if os.path.normcase(str(pasta)) != os.path.normcase(str(esperada)):
        raise PastaAlterada("O ITC Bench não está na pasta de instalação esperada.")
    itens = [pasta.parent, *_arvore(pasta)]
    for item in itens:
        atributos = os.lstat(item).st_file_attributes
        if atributos & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise PastaAlterada(f"Ponto de reparse na pasta de instalação: {item.name}")
        if problemas := escrita_de_terceiros(ler(item)):
            raise PastaAlterada(f"Permissão alterada em {item.name}: {', '.join(problemas)}")


def _arvore(raiz: Path) -> list[Path]:
    """Raiz e tudo dentro, sem entrar em ponto de reparse (o chamador recusa ao vê-lo)."""
    itens, pendentes = [], [raiz]
    while pendentes:
        item = pendentes.pop()
        itens.append(item)
        atributos = os.lstat(item).st_file_attributes
        if atributos & stat.FILE_ATTRIBUTE_DIRECTORY and not (
            atributos & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            pendentes.extend(item.iterdir())
    return itens


def conferir_instalacao() -> None:
    """No congelado, `conferir_pasta` com a pasta fixa do HKLM; fora dele, nada."""
    if congelado():
        conferir_pasta(Path(sys.executable), caminhos.instalacao())


_mutexes: list[int] = []
# Só SYSTEM e Administradores abrem o mutex do Bench; o dono vem do token elevado (BA).
SDDL_MUTEX = "D:P(A;;GA;;;SY)(A;;GA;;;BA)"
_ERROR_ALREADY_EXISTS = 183
_SE_KERNEL_OBJECT = 6
_OWNER_SECURITY_INFORMATION = 1
_SYNCHRONIZE_READ_CONTROL = 0x00100000 | 0x00020000
_WIN_LOCAL_SYSTEM = 22
_WIN_BUILTIN_ADMINISTRATORS = 26


class _Atributos(ctypes.Structure):
    _fields_ = (
        ("nLength", ctypes.c_ulong),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", ctypes.c_int),
    )


def _k32() -> ctypes.WinDLL:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.OpenMutexW.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p)
    k32.OpenMutexW.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
    k32.LocalFree.argtypes = (ctypes.c_void_p,)
    return k32


def _dono_administrador(handle: int) -> bool:
    """Dono do objeto é Administradores ou SYSTEM (mesma regra do `[Code]` do instalador)."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.GetSecurityInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    adv.IsWellKnownSid.argtypes = (ctypes.c_void_p, ctypes.c_int)
    dono, descritor = ctypes.c_void_p(), ctypes.c_void_p()
    erro = adv.GetSecurityInfo(
        handle,
        _SE_KERNEL_OBJECT,
        _OWNER_SECURITY_INFORMATION,
        ctypes.byref(dono),
        None,
        None,
        None,
        ctypes.byref(descritor),
    )
    if erro:
        return False
    try:
        return any(
            adv.IsWellKnownSid(dono, tipo)
            for tipo in (_WIN_BUILTIN_ADMINISTRATORS, _WIN_LOCAL_SYSTEM)
        )
    finally:
        _k32().LocalFree(descritor)


def mutex_de_administrador(nome: str = rf"Global\{MUTEX}") -> bool:
    r"""O Bench elevado está aberto? Só conta mutex que abre com `READ_CONTROL` e dono BA/SY.

    Usuário comum consegue criar `Global\ITCBench` (prova no runner, Módulo 16); esse fica
    ignorado aqui e no instalador.
    """
    k32 = _k32()
    handle = k32.OpenMutexW(_SYNCHRONIZE_READ_CONTROL, 0, nome)
    if not handle:
        return False
    try:
        return _dono_administrador(handle)
    finally:
        k32.CloseHandle(handle)


def criar_mutex(admin: bool = True) -> str:
    r"""Mutex `Global\ITCBench` que o instalador confere (ADR-026) enquanto o Bench está aberto.

    Só elevado: sem administrador o mutex não teria dono BA e o instalador o ignoraria. Se o nome
    já estiver ocupado por outro usuário, avisa e segue (a atualização se apoia no `/ESPERAPID`).
    Devolve o estado para o log: "criado", "sem_admin", "alheio" ou "falhou".
    """
    if not admin:
        return "sem_admin"
    k32 = _k32()
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    )
    descritor = ctypes.c_void_p()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        SDDL_MUTEX, 1, ctypes.byref(descritor), None
    ):
        return "falhou"
    atributos = _Atributos(ctypes.sizeof(_Atributos), descritor.value, 0)
    try:
        handle = k32.CreateMutexW(ctypes.byref(atributos), 0, rf"Global\{MUTEX}")
        ultimo = ctypes.get_last_error()
    finally:
        k32.LocalFree(descritor)  # o kernel copiou o descritor
    if not handle:
        return "alheio" if ultimo == 5 else "falhou"
    if ultimo == _ERROR_ALREADY_EXISTS and not _dono_administrador(handle):
        k32.CloseHandle(handle)
        return "alheio"
    _mutexes.append(handle)
    return "criado"


def soltar_mutex() -> None:
    """Antes de disparar a atualização: o instalador não pode ver o Bench que está saindo."""
    k32 = _k32()
    while _mutexes:
        k32.CloseHandle(_mutexes.pop())


def ler_recursos(raiz: Traversable | None = None) -> int:
    """Lê todo arquivo de `recursos/` (`--teste`, ajuste 3): falta no pacote vira exceção."""
    pendentes = [raiz or resources.files("itc_bench.recursos")]
    total = 0
    while pendentes:
        item = pendentes.pop()
        if item.is_dir():
            pendentes.extend(item.iterdir())
        elif not item.name.endswith((".pyc", ".py")):
            item.read_bytes()
            total += 1
    if not total:
        raise FileNotFoundError("recursos/ vazio no pacote")
    return total
