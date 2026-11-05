"""Wi-Fi nativo do Windows (`wlanapi.dll`) por ctypes (ADR-018), sem processo nem arquivo.

O XML do perfil, com a senha, vai direto da memória do Bench para o serviço WLAN: não passa por
disco, linha de comando nem ambiente. Nada aqui grava log com SSID ou XML; o erro sai só com o
código Win32.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from types import TracebackType

_VERSAO_CLIENTE = 2
_PERFIL_COM_CHAVE = 0x4  # WLAN_PROFILE_GET_PLAINTEXT_KEY: só com administrador
SERVICO_PARADO = 1062  # ERROR_SERVICE_NOT_ACTIVE
NAO_ENCONTRADO = 1168  # ERROR_NOT_FOUND


class _Guid(ctypes.Structure):
    _fields_ = (("dados", ctypes.c_ubyte * 16),)


class _Interface(ctypes.Structure):
    _fields_ = (
        ("guid", _Guid),
        ("descricao", ctypes.c_wchar * 256),
        ("estado", wintypes.DWORD),
    )


class _ListaInterfaces(ctypes.Structure):
    _fields_ = (
        ("quantos", wintypes.DWORD),
        ("indice", wintypes.DWORD),
        ("itens", _Interface * 1),
    )


class _Perfil(ctypes.Structure):
    _fields_ = (("nome", ctypes.c_wchar * 256), ("flags", wintypes.DWORD))


class _ListaPerfis(ctypes.Structure):
    _fields_ = (
        ("quantos", wintypes.DWORD),
        ("indice", wintypes.DWORD),
        ("itens", _Perfil * 1),
    )


class ErroWlan(OSError):
    """Falha da `wlanapi`; `codigo` é o erro Win32 (e `motivo`, o WLAN_REASON_CODE se houver)."""

    def __init__(self, funcao: str, codigo: int, motivo: int = 0) -> None:
        super().__init__(codigo, f"{funcao}: 0x{codigo:08X}" + (f" ({motivo})" if motivo else ""))
        self.codigo = codigo
        self.motivo = motivo


@dataclass(frozen=True)
class Interface:
    guid: bytes
    descricao: str


def _dll() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("wlanapi")
    p = ctypes.POINTER
    dll.WlanOpenHandle.argtypes = (
        wintypes.DWORD,
        ctypes.c_void_p,
        p(wintypes.DWORD),
        p(wintypes.HANDLE),
    )
    dll.WlanCloseHandle.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    dll.WlanFreeMemory.argtypes = (ctypes.c_void_p,)
    dll.WlanEnumInterfaces.argtypes = (wintypes.HANDLE, ctypes.c_void_p, p(p(_ListaInterfaces)))
    dll.WlanGetProfileList.argtypes = (
        wintypes.HANDLE,
        p(_Guid),
        ctypes.c_void_p,
        p(p(_ListaPerfis)),
    )
    dll.WlanGetProfile.argtypes = (
        wintypes.HANDLE,
        p(_Guid),
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        p(ctypes.c_void_p),
        p(wintypes.DWORD),
        p(wintypes.DWORD),
    )
    dll.WlanSetProfile.argtypes = (
        wintypes.HANDLE,
        p(_Guid),
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.BOOL,
        ctypes.c_void_p,
        p(wintypes.DWORD),
    )
    for nome in (
        "WlanOpenHandle",
        "WlanCloseHandle",
        "WlanEnumInterfaces",
        "WlanGetProfileList",
        "WlanGetProfile",
        "WlanSetProfile",
    ):
        getattr(dll, nome).restype = wintypes.DWORD
    return dll


def _guid(interface: Interface) -> _Guid:
    return _Guid((ctypes.c_ubyte * 16).from_buffer_copy(interface.guid))


class Cliente:
    """Sessão com o serviço WLAN. Use com `with`; sem serviço/adaptador, ErroWlan ao abrir."""

    def __init__(self) -> None:
        self._dll = _dll()
        self._handle = wintypes.HANDLE()

    def __enter__(self) -> "Cliente":
        versao = wintypes.DWORD()
        self._checar(
            "WlanOpenHandle", self._dll.WlanOpenHandle(_VERSAO_CLIENTE, None, versao, self._handle)
        )
        return self

    def __exit__(
        self,
        _tipo: type[BaseException] | None,
        _erro: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        if self._handle:
            self._dll.WlanCloseHandle(self._handle, None)

    @staticmethod
    def _checar(funcao: str, codigo: int, motivo: int = 0) -> None:
        if codigo:
            raise ErroWlan(funcao, codigo, motivo)

    def interfaces(self) -> list[Interface]:
        lista = ctypes.POINTER(_ListaInterfaces)()
        self._checar("WlanEnumInterfaces", self._dll.WlanEnumInterfaces(self._handle, None, lista))
        try:
            quantos = lista.contents.quantos
            itens = ctypes.cast(lista.contents.itens, ctypes.POINTER(_Interface))
            return [
                Interface(bytes(itens[i].guid.dados), itens[i].descricao) for i in range(quantos)
            ]
        finally:
            self._dll.WlanFreeMemory(lista)

    def perfis(self, interface: Interface) -> list[str]:
        lista = ctypes.POINTER(_ListaPerfis)()
        guid = _guid(interface)
        self._checar(
            "WlanGetProfileList", self._dll.WlanGetProfileList(self._handle, guid, None, lista)
        )
        try:
            itens = ctypes.cast(lista.contents.itens, ctypes.POINTER(_Perfil))
            return [itens[i].nome for i in range(lista.contents.quantos)]
        finally:
            self._dll.WlanFreeMemory(lista)

    def perfil(self, interface: Interface, nome: str, *, com_chave: bool) -> str:
        """XML do perfil. Com `com_chave` e administrador, a senha vem em claro: não guardar."""
        xml = ctypes.c_void_p()
        flags = wintypes.DWORD(_PERFIL_COM_CHAVE if com_chave else 0)
        acesso = wintypes.DWORD()
        codigo = self._dll.WlanGetProfile(
            self._handle, _guid(interface), nome, None, xml, flags, acesso
        )
        self._checar("WlanGetProfile", codigo)
        try:
            return ctypes.wstring_at(xml.value) if xml.value else ""
        finally:
            self._dll.WlanFreeMemory(xml)

    def gravar(self, interface: Interface, xml: str) -> None:
        """Perfil de todos os usuários (`dwFlags = 0`), sobrescrevendo o de mesmo nome."""
        motivo = wintypes.DWORD()
        codigo = self._dll.WlanSetProfile(
            self._handle, _guid(interface), 0, xml, None, True, None, motivo
        )
        self._checar("WlanSetProfile", codigo, motivo.value)
