"""Proteção do login (ADR-022): passos fixos, dono sempre devolvido, detecção e atalho.

Executores falsos; o PowerShell real só lê a máquina.
"""

import json
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from itc_bench.servicos import protecao
from itc_bench.servicos.executor import Resultado

SYS = "C:\\W\\System32\\"


def ok(saida: str = "") -> Resultado:
    return Resultado(0, saida, "", 0.1, False)


def falha(codigo: int = 5) -> Resultado:
    return Resultado(codigo, "", "", 0.1, False)


def leitura(**por_exe: dict[str, str]) -> str:
    bins = []
    for exe in protecao.BINARIOS:
        b = {"exe": exe, "arquivo": "original", "acl": "livre", "ifeo": "limpo"}
        b.update(por_exe.get(exe.split(".")[0].lower(), {}))
        bins.append(b)
    flags = {"StickyKeys": "510", "Keyboard Response": "126", "ToggleKeys": "62"}
    return json.dumps({"binarios": bins, "flags": flags})


def ps(saida: str) -> Any:
    return lambda script, **kw: ok(saida)


class Nativo:
    def __init__(self, falhar: str | None = None) -> None:
        self.chamadas: list[list[str]] = []
        self.falhar = falhar

    def __call__(self, argumentos: list[str], **kw: Any) -> Resultado:
        self.chamadas.append(argumentos)
        if self.falhar and self.falhar in argumentos:
            return falha()
        return ok()


def s32(nome: str) -> str:
    return SYS + nome


def test_proteger_tres_passos_fixos() -> None:
    n = Nativo()
    feitos = protecao.alterar(True, rodar_ps=ps(leitura()), rodar=n, sistema32=s32)
    assert all(f.ok for f in feitos) and len(feitos) == 2
    assert n.chamadas[:3] == [
        [SYS + "takeown.exe", "/f", SYS + "utilman.exe", "/a"],
        [SYS + "icacls.exe", SYS + "utilman.exe", "/deny", "*S-1-5-18:(X)"],
        [SYS + "icacls.exe", SYS + "utilman.exe", "/setowner", "*" + protecao.SID_TRUSTEDINSTALLER],
    ]


def test_desproteger_remove_so_a_negacao() -> None:
    n = Nativo()
    protecao.alterar(False, ["sethc.exe"], rodar_ps=ps(leitura()), rodar=n, sistema32=s32)
    assert n.chamadas[1] == [SYS + "icacls.exe", SYS + "sethc.exe", "/remove:d", "*S-1-5-18"]


def test_dono_volta_mesmo_com_falha_no_meio() -> None:
    n = Nativo(falhar="/deny")
    feitos = protecao.alterar(True, ["utilman.exe"], rodar_ps=ps(leitura()), rodar=n, sistema32=s32)
    assert not feitos[0].ok
    assert n.chamadas[-1][2:] == ["/setowner", "*" + protecao.SID_TRUSTEDINSTALLER]


def test_dono_volta_mesmo_com_falha_no_takeown() -> None:
    n = Nativo(falhar="/a")
    protecao.alterar(True, ["utilman.exe"], rodar_ps=ps(leitura()), rodar=n, sistema32=s32)
    assert len(n.chamadas) == 2 and "/setowner" in n.chamadas[1]


def test_proteger_recusa_arquivo_trocado_ou_nao_lido() -> None:
    n = Nativo()
    feitos = protecao.alterar(
        True,
        rodar_ps=ps(leitura(utilman={"arquivo": "trocado"}, sethc={"arquivo": "nao_lido"})),
        rodar=n,
        sistema32=s32,
    )
    assert not any(f.ok for f in feitos) and not n.chamadas
    assert "Restaurar original" in feitos[0].mensagem


def test_cancelar_entre_arquivos() -> None:
    n = Nativo()
    cancelar = threading.Event()

    def rodar(argumentos: list[str], **kw: Any) -> Resultado:
        if "/setowner" in argumentos:
            cancelar.set()
        return n(argumentos, **kw)

    feitos = protecao.alterar(
        True, rodar_ps=ps(leitura()), rodar=rodar, sistema32=s32, cancelar=cancelar
    )
    assert feitos[0].ok and not feitos[1].ok and len(n.chamadas) == 3


def test_so_utilman_e_sethc() -> None:
    with pytest.raises(ValueError):
        protecao.alterar(True, ["cmd.exe"], rodar_ps=ps(leitura()), rodar=Nativo(), sistema32=s32)


def test_situacao_e_alertas() -> None:
    s = protecao.situacao(
        rodar=ps(
            leitura(utilman={"acl": "protegido"}, osk={"ifeo": "depurador"}, sethc={"acl": "dono"})
        )
    )
    assert s.atalho == "padrao"
    alertas = s.alertas()
    assert any("Teclado virtual" in a and "IFEO" in a for a in alertas)
    assert any("Sethc" in a and "dono" in a for a in alertas)
    assert not any("Utilman" in a for a in alertas)


@pytest.mark.parametrize(
    ("flags", "esperado"),
    [
        ({"StickyKeys": "506", "Keyboard Response": "122", "ToggleKeys": "58"}, "desligado"),
        ({"StickyKeys": None, "Keyboard Response": "126", "ToggleKeys": None}, "padrao"),
        ({"StickyKeys": "506", "Keyboard Response": "126", "ToggleKeys": "62"}, "diferente"),
        (None, "nao_lido"),
    ],
)
def test_atalho(flags: Any, esperado: str) -> None:
    assert protecao._atalho(flags) == esperado


def test_leitura_invalida() -> None:
    with pytest.raises(RuntimeError):
        protecao.situacao(rodar=ps('{"binarios": []}'))


def test_restaurar_decide_pela_deteccao() -> None:
    n = Nativo()
    ok_, msg = protecao.restaurar(
        "osk.exe", rodar=n, rodar_ps=ps(leitura(osk={"arquivo": "trocado"})), sistema32=s32
    )
    assert n.chamadas == [[SYS + "sfc.exe", "/scanfile=" + SYS + "osk.exe"]]
    assert not ok_ and "chamado" in msg


def test_trechos_fixos() -> None:
    pasta = Path(protecao.__file__).parent.parent / "recursos" / "protecao"
    ler = (pasta / "ler.ps1").read_text("utf-8")
    escrever = (pasta / "escrever.ps1").read_text("utf-8")
    for proibido in ("SetValue", "DeleteValue", "CreateSubKey", "Set-Acl"):
        assert proibido not in ler
    assert "Registry64" in ler and "Registry64" in escrever
    assert "WOW6432Node" not in ler + escrever
    # Só Debugger e MonitorProcess são apagados.
    assert {
        linha.split("DeleteValue('")[1].split("'")[0]
        for linha in escrever.splitlines()
        if "DeleteValue('" in linha
    } == {
        "Debugger",
        "MonitorProcess",
    }


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_situacao_real() -> None:
    s = protecao.situacao()
    assert set(s.binarios) == set(protecao.BINARIOS)
    assert s.binarios["utilman.exe"].arquivo in ("original", "nao_lido")
