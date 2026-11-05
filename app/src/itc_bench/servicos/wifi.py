"""Redes Wi-Fi do cadastro (ADR-018), sem Qt: a tela Wi-Fi e a Preparação completa (13) usam.

As redes vêm só do cache dos cadastros (ADR-014). O perfil vai ao Windows pela `wlanapi.dll`
(`nucleo/wlan.py`), com o XML montado aqui em memória. O log identifica a rede só pelo `Id` do
cadastro: nunca SSID, senha ou XML.
"""

import hmac
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from itc_bench.nucleo import wlan
from itc_bench.nucleo.log import log
from itc_bench.servicos.cadastros import Rede

NS = "http://www.microsoft.com/networking/WLAN/profile/v1"
HEX64 = re.compile(r"^[0-9A-Fa-f]{64}$")
ESPERA_CONEXAO = 20.0
PASSO_CONEXAO = 0.5

Situacao = Literal["igual", "diferente", "ausente", "nao_conferida", "invalida"]
ROTULOS: dict[Situacao, str] = {
    "igual": "Instalada (igual)",
    "diferente": "Senha ou segurança diferente",
    "ausente": "Não instalada",
    "nao_conferida": "Instalada (senha não conferida)",
    "invalida": "Cadastro inválido",
}


class Wlan(Protocol):
    """O que `servicos/wifi` usa de `nucleo.wlan.Cliente` (os testes passam um falso)."""

    def interfaces(self) -> list[wlan.Interface]: ...
    def perfis(self, interface: wlan.Interface) -> list[str]: ...
    def perfil(self, interface: wlan.Interface, nome: str, *, com_chave: bool) -> str: ...
    def gravar(self, interface: wlan.Interface, xml: str) -> None: ...
    def conectar(self, interface: wlan.Interface, nome: str) -> None: ...
    def conectado_a(self, interface: wlan.Interface) -> str | None: ...


@dataclass(frozen=True)
class Linha:
    rede: Rede
    situacao: Situacao
    motivo: str = ""  # por que o cadastro é inválido


@dataclass(frozen=True)
class Resumo:
    instaladas: tuple[int, ...] = ()  # Ids
    falhas: tuple[tuple[int, str], ...] = ()  # (Id, motivo para a tela)
    canceladas: tuple[int, ...] = ()
    puladas: tuple[int, ...] = ()  # cadastro inválido


class SemWifi(RuntimeError):
    """Sem adaptador Wi-Fi ou com o serviço WLAN parado."""


def validar(rede: Rede) -> str | None:
    """Motivo do cadastro inválido, ou None. Todas as redes do Grupo têm senha (WPA2-Personal)."""
    ssid = rede.ssid
    if not ssid or len(ssid.encode("utf-8")) > 32:
        return "Nome da rede vazio ou maior que 32 bytes."
    senha = rede.senha.revelar()
    if not senha:
        return "Senha vazia no cadastro."
    if HEX64.match(senha):
        return None
    if not 8 <= len(senha) <= 63 or not all(" " <= c <= "~" for c in senha):
        return "Senha com tamanho ou caractere fora do WPA2 (8 a 63 caracteres comuns)."
    return None


def xml_perfil(rede: Rede) -> str:
    """Perfil WPA2PSK/AES de conexão automática. Escape pelo ElementTree, SSID também em hex."""
    raiz = ET.Element("WLANProfile", xmlns=NS)
    ET.SubElement(raiz, "name").text = rede.ssid
    ssid = ET.SubElement(ET.SubElement(raiz, "SSIDConfig"), "SSID")
    ET.SubElement(ssid, "hex").text = rede.ssid.encode("utf-8").hex().upper()
    ET.SubElement(ssid, "name").text = rede.ssid
    ET.SubElement(raiz, "connectionType").text = "ESS"
    ET.SubElement(raiz, "connectionMode").text = "auto"
    seguranca = ET.SubElement(ET.SubElement(raiz, "MSM"), "security")
    autenticacao = ET.SubElement(seguranca, "authEncryption")
    ET.SubElement(autenticacao, "authentication").text = "WPA2PSK"
    ET.SubElement(autenticacao, "encryption").text = "AES"
    ET.SubElement(autenticacao, "useOneX").text = "false"
    chave = ET.SubElement(seguranca, "sharedKey")
    senha = rede.senha.revelar()
    ET.SubElement(chave, "keyType").text = "networkKey" if HEX64.match(senha) else "passPhrase"
    ET.SubElement(chave, "protected").text = "false"
    ET.SubElement(chave, "keyMaterial").text = senha
    return ET.tostring(raiz, encoding="unicode")


def _iguais(xml_instalado: str, rede: Rede) -> bool:
    """Compara segurança e senha do perfil instalado com o cadastro; a chave lida morre aqui."""
    try:
        raiz = ET.fromstring(xml_instalado)  # noqa: S314 — XML do próprio serviço WLAN
    except ET.ParseError:
        return False
    auth, prot, chave = (
        raiz.find(f".//{{{NS}}}{tag}") for tag in ("authentication", "protected", "keyMaterial")
    )
    if auth is None or auth.text != "WPA2PSK" or chave is None or chave.text is None:
        return False
    if prot is not None and prot.text == "true":
        return False  # sem administrador a chave vem cifrada: quem chama já trata
    return hmac.compare_digest(chave.text.encode("utf-8"), rede.senha.revelar().encode("utf-8"))


def _interface(cliente: Wlan) -> list[wlan.Interface]:
    interfaces = cliente.interfaces()
    if not interfaces:
        raise SemWifi("nenhum adaptador Wi-Fi")
    return interfaces


def instaladas(cliente: Wlan) -> list[str]:
    """Nomes dos perfis no Windows (todas as interfaces), sem repetir."""
    nomes: dict[str, None] = {}
    for interface in _interface(cliente):
        nomes.update(dict.fromkeys(cliente.perfis(interface)))
    return list(nomes)


def situacao(redes: Iterable[Rede], cliente: Wlan, *, admin: bool) -> list[Linha]:
    interface = _interface(cliente)[0]
    perfis = set(cliente.perfis(interface))
    linhas = []
    for rede in redes:
        motivo = validar(rede)
        if motivo:
            linhas.append(Linha(rede, "invalida", motivo))
        elif rede.ssid not in perfis:
            linhas.append(Linha(rede, "ausente"))
        elif not admin:
            linhas.append(Linha(rede, "nao_conferida"))
        else:
            xml = cliente.perfil(interface, rede.ssid, com_chave=True)
            linhas.append(Linha(rede, "igual" if _iguais(xml, rede) else "diferente"))
            del xml
    return linhas


def _falha(erro: Exception) -> str:
    if isinstance(erro, wlan.ErroWlan):
        return f"o Windows recusou (0x{erro.codigo:08X}" + (
            f", motivo {erro.motivo})" if erro.motivo else ")"
        )
    return f"falha inesperada ({type(erro).__name__})"


def instalar(
    redes: Iterable[Rede],
    cliente: Wlan,
    *,
    cancelar: threading.Event | None = None,
    progresso: Callable[[int, int], None] | None = None,
) -> Resumo:
    """Instala para todos os usuários, em todas as interfaces; cancela entre uma rede e outra."""
    lista = list(redes)
    interfaces = _interface(cliente)
    instaladas_, falhas, canceladas, puladas = [], [], [], []
    for i, rede in enumerate(lista):
        if cancelar is not None and cancelar.is_set():
            canceladas = [r.id for r in lista[i:]]
            break
        if progresso:
            progresso(i, len(lista))
        if validar(rede):
            log.warning("Wi-Fi: Id %s pulada: cadastro inválido", rede.id)
            puladas.append(rede.id)
            continue
        try:
            xml = xml_perfil(rede)
            for interface in interfaces:
                cliente.gravar(interface, xml)
            del xml
        except OSError as erro:  # ErroWlan; registrado no log e devolvido para a tela
            motivo = _falha(erro)
            log.error("Wi-Fi: Id %s falhou: %s", rede.id, motivo)
            falhas.append((rede.id, motivo))
            continue
        log.info("Wi-Fi: Id %s instalada", rede.id)
        instaladas_.append(rede.id)
    if progresso:
        progresso(len(lista), len(lista))
    resumo = Resumo(tuple(instaladas_), tuple(falhas), tuple(canceladas), tuple(puladas))
    log.info(
        "Wi-Fi: instalar %s redes: %s ok, %s falhas, %s puladas, %s canceladas",
        len(lista),
        len(resumo.instaladas),
        len(resumo.falhas),
        len(resumo.puladas),
        len(resumo.canceladas),
    )
    return resumo


def testar(
    rede: Rede,
    cliente: Wlan,
    saude: Callable[[], bool],
    *,
    cancelar: threading.Event | None = None,
    espera: float = ESPERA_CONEXAO,
    relogio: Callable[[], float] = time.monotonic,
) -> str:
    """Conecta pelo perfil instalado e pergunta à API se responde. Mensagem para a tela."""
    interface = _interface(cliente)[0]
    try:
        cliente.conectar(interface, rede.ssid)
    except wlan.ErroWlan as erro:
        log.warning("Wi-Fi: testar Id %s: %s", rede.id, _falha(erro))
        return "Não conectou: " + _falha(erro) + ". A rede está instalada?"
    evento = cancelar or threading.Event()
    limite = relogio() + espera
    while cliente.conectado_a(interface) != rede.ssid:
        if relogio() >= limite or evento.wait(PASSO_CONEXAO):
            log.warning("Wi-Fi: testar Id %s: não conectou", rede.id)
            return "Cancelado." if evento.is_set() else "Não conectou em 20 segundos."
    ok = saude()  # quem passa `saude` trata a falta de rede (devolve False)
    log.info("Wi-Fi: testar Id %s: conectado, API %s", rede.id, "ok" if ok else "sem resposta")
    return "Conectado, e a API responde." if ok else "Conectado, mas sem acesso à API."
