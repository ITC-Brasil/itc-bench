# ruff: noqa: S314 — XML montado pelo próprio teste
"""Wi-Fi (ADR-018): validação, XML, situação, instalação, teste, log sem SSID nem senha.

Só redes fictícias. A `wlanapi` real roda só na leitura (Windows) e, para gravar, só com
`ITC_TESTE_WIFI=1` numa máquina de teste elevada (grava e apaga uma rede de teste).
"""

import ast
import logging
import os
import sys
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from itc_bench.nucleo import wlan
from itc_bench.nucleo.elevacao import eh_admin
from itc_bench.servicos import wifi
from itc_bench.servicos.cadastros import Cadastros, Rede
from itc_bench.servicos.executor import Sensivel

SENHA = "Marcador-Wifi-9c2e!"
NS = {"w": wifi.NS}


def rede(
    id_: int = 1, ssid: str = "Rede-Teste", senha: str = SENHA, unidade: str = "ABC01"
) -> Rede:
    return Rede(id_, ssid, Sensivel(senha), unidade, "Carreta", "")


class Falso:
    """Cliente WLAN em memória: perfil = XML gravado."""

    def __init__(self, *, interfaces: int = 1, falhar: set[str] | None = None) -> None:
        self.lista = [wlan.Interface(bytes([i]) * 16, f"if{i}") for i in range(interfaces)]
        self.gravados: dict[tuple[bytes, str], str] = {}
        self.falhar = falhar or set()

    def interfaces(self) -> list[wlan.Interface]:
        return self.lista

    def perfis(self, interface: wlan.Interface) -> list[str]:
        return [n for (g, n) in self.gravados if g == interface.guid]

    def perfil(self, interface: wlan.Interface, nome: str, *, com_chave: bool) -> str:
        return self.gravados[(interface.guid, nome)]

    def gravar(self, interface: wlan.Interface, xml: str) -> None:
        nome = ET.fromstring(xml).findtext("w:name", namespaces=NS) or ""
        if nome in self.falhar:
            raise wlan.ErroWlan("WlanSetProfile", 0x80070057, 523)
        self.gravados[(interface.guid, nome)] = xml


# ---------------------------------------------------------------- validação e XML


@pytest.mark.parametrize(
    ("ssid", "senha", "ok"),
    [
        ("Rede-Teste", "12345678", True),
        ("Rede-Teste", "a" * 63, True),
        ("Rede-Teste", "A1" * 32, True),  # 64 hex
        ("Rede-Teste", "", False),  # todas as redes têm senha: vazia é erro
        ("Rede-Teste", "1234567", False),
        ("Rede-Teste", "g" * 64, False),  # 64 sem ser hex
        ("Rede-Teste", "senhaçãoacentuada", False),
        ("", SENHA, False),
        ("é" * 17, SENHA, False),  # 34 bytes
        ("Ação & <Teste>", SENHA, True),
    ],
)
def test_validar(ssid: str, senha: str, ok: bool) -> None:
    assert (wifi.validar(rede(ssid=ssid, senha=senha)) is None) is ok


def test_xml_escapa_ssid_e_senha_e_usa_hex() -> None:
    ssid, senha = 'Café & <"Teste">', "a]]>b<c&d'e\""
    xml = wifi.xml_perfil(rede(ssid=ssid, senha=senha))
    raiz = ET.fromstring(xml)  # XML válido apesar dos caracteres
    assert raiz.findtext("w:name", namespaces=NS) == ssid
    assert raiz.findtext(".//w:SSID/w:hex", namespaces=NS) == ssid.encode().hex().upper()
    assert raiz.findtext(".//w:keyMaterial", namespaces=NS) == senha
    assert raiz.findtext(".//w:authentication", namespaces=NS) == "WPA2PSK"
    assert raiz.findtext(".//w:keyType", namespaces=NS) == "passPhrase"
    assert raiz.findtext(".//w:protected", namespaces=NS) == "false"


def test_xml_chave_hex() -> None:
    xml = wifi.xml_perfil(rede(senha="0F" * 32))
    assert ET.fromstring(xml).findtext(".//w:keyType", namespaces=NS) == "networkKey"


# ---------------------------------------------------------------- situação


def test_situacao() -> None:
    cliente = Falso()
    igual, velha = rede(1, "Rede-A"), rede(2, "Rede-B")
    cliente.gravar(INTERFACE_0 := cliente.lista[0], wifi.xml_perfil(igual))
    cliente.gravar(INTERFACE_0, wifi.xml_perfil(rede(2, "Rede-B", senha="senha-antiga-1")))
    redes = [igual, velha, rede(3, "Rede-C"), rede(4, "Rede-D", senha="")]
    linhas = wifi.situacao(redes, cliente, admin=True)
    assert [x.situacao for x in linhas] == ["igual", "diferente", "ausente", "invalida"]
    sem_admin = wifi.situacao(redes, cliente, admin=False)
    assert [x.situacao for x in sem_admin][:2] == ["nao_conferida", "nao_conferida"]


def test_situacao_chave_cifrada_ou_outra_seguranca_e_diferente() -> None:
    r = rede()
    cifrada = wifi.xml_perfil(r).replace("<protected>false", "<protected>true")
    wpa3 = wifi.xml_perfil(r).replace("WPA2PSK", "WPA3SAE")
    assert not wifi._iguais(cifrada, r)
    assert not wifi._iguais(wpa3, r)
    assert not wifi._iguais("não é xml", r)
    assert wifi._iguais(wifi.xml_perfil(r), r)


def test_sem_adaptador() -> None:
    cliente = Falso(interfaces=0)
    with pytest.raises(wifi.SemWifi):
        wifi.situacao([rede()], cliente, admin=True)


def test_filtro_por_unidade() -> None:
    from datetime import UTC, datetime

    cad = Cadastros(
        "v", datetime.now(UTC), "t", None, False, (), (),
        (rede(1, unidade="ABC01"), rede(2, unidade="XYZ02")), (),
    )  # fmt: skip
    assert [r.id for r in cad.redes_da_unidade("ABC01")] == [1]
    assert [r.id for r in cad.redes_da_unidade(None)] == [1, 2]


# ---------------------------------------------------------------- instalar


def test_instalar_varias_interfaces_falha_e_invalida(caplog: pytest.LogCaptureFixture) -> None:
    cliente = Falso(interfaces=2, falhar={"Rede-Falha"})
    redes = [rede(1, "Rede-A"), rede(2, "Rede-Falha"), rede(3, "Rede-C", senha="curta")]
    passos: list[tuple[int, int]] = []
    with caplog.at_level(logging.INFO):
        resumo = wifi.instalar(redes, cliente, progresso=lambda i, n: passos.append((i, n)))
    assert resumo.instaladas == (1,) and resumo.puladas == (3,)
    assert resumo.falhas[0][0] == 2 and "0x80070057" in resumo.falhas[0][1]
    assert len(cliente.gravados) == 2  # Rede-A nas duas interfaces
    assert passos[-1] == (3, 3)
    texto = caplog.text
    assert "Id 1 instalada" in texto and "Id 2 falhou" in texto
    for proibido in ("Rede-A", "Rede-Falha", SENHA, "curta", "keyMaterial"):
        assert proibido not in texto


def test_instalar_cancela_entre_redes() -> None:
    cliente = Falso()
    cancelar = threading.Event()

    def progresso(i: int, _n: int) -> None:
        if i == 1:
            cancelar.set()  # pedido durante a segunda rede: ela termina, a terceira não começa

    resumo = wifi.instalar(
        [rede(1, "R1"), rede(2, "R2"), rede(3, "R3")],
        cliente,
        cancelar=cancelar,
        progresso=progresso,
    )
    assert resumo.instaladas == (1, 2) and resumo.canceladas == (3,)


def test_ja_instalada_igual_fica_igual() -> None:
    cliente = Falso()
    r = rede()
    wifi.instalar([r], cliente)
    wifi.instalar([r], cliente)  # sobrescreve sem erro
    assert wifi.situacao([r], cliente, admin=True)[0].situacao == "igual"


# ---------------------------------------------------------------- sem disco nem processo


def test_wifi_nao_abre_processo_nem_grava_arquivo() -> None:
    raiz = Path(wifi.__file__).parent.parent
    for arquivo in (raiz / "servicos" / "wifi.py", raiz / "nucleo" / "wlan.py"):
        arvore = ast.parse(arquivo.read_text("utf-8"))
        nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
        atributos = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
        modulos = {
            a.name
            for n in ast.walk(arvore)
            if isinstance(n, ast.Import | ast.ImportFrom)
            for a in n.names
        } | {n.module for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.module}
        assert "open" not in nomes, arquivo
        assert not {"executor", "tempfile", "subprocess"} & modulos, arquivo
        assert not {"write_text", "write_bytes", "powershell", "executar"} & atributos, arquivo


# ---------------------------------------------------------------- wlanapi real


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_leitura_real() -> None:
    try:
        with wlan.Cliente() as cliente:
            interfaces = cliente.interfaces()
            for interface in interfaces:
                assert isinstance(cliente.perfis(interface), list)
    except wlan.ErroWlan as erro:
        assert erro.codigo == wlan.SERVICO_PARADO  # máquina sem Wi-Fi


@pytest.mark.skipif(
    os.environ.get("ITC_TESTE_WIFI") != "1" or not eh_admin(),
    reason="grava perfil de Wi-Fi: só em máquina de teste elevada",
)
def test_gravar_real() -> None:  # pragma: no cover - roteiro manual
    r = rede(99, "ITC-Teste-Ação &", senha=SENHA)
    with wlan.Cliente() as cliente:
        wifi.instalar([r], cliente)
        assert wifi.situacao([r], cliente, admin=True)[0].situacao == "igual"
