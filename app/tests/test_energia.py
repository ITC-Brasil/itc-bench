"""Energia (ADR-022): powercfg com aliases e lista fechada, desfazer pelo padrão, leitura real."""

import json
import sys
import threading
from typing import Any

import pytest

from itc_bench.servicos import energia
from itc_bench.servicos.executor import Resultado


def ok(saida: str = "") -> Resultado:
    return Resultado(0, saida, "", 0.1, False)


class Nativo:
    def __init__(self, falhar: str | None = None) -> None:
        self.chamadas: list[list[str]] = []
        self.falhar = falhar

    def __call__(self, argumentos: list[str], **kw: Any) -> Resultado:
        self.chamadas.append(argumentos[1:])
        assert argumentos[0].lower().endswith("\\system32\\powercfg.exe")
        if self.falhar and self.falhar in argumentos:
            return Resultado(1, "", "", 0.1, False)
        return ok()


def leitura(**padrao: int | None) -> Any:
    ajustes = {
        a: {"ac": 600, "dc": 300, "padrao_ac": padrao.get(a, 900), "padrao_dc": padrao.get(a, 300)}
        for a in energia.AJUSTES
    }
    dados = {"esquema": "x", "ajustes": ajustes, "hibernacao": 1}
    return lambda script, **kw: ok(json.dumps(dados))


def test_tempos_com_aliases_e_setactive() -> None:
    n = Nativo()
    feitos = energia.tempos({("tela", "ac"): 0, ("suspensao", "dc"): 900}, rodar=n)
    assert all(f.ok for f in feitos)
    assert n.chamadas == [
        ["/setacvalueindex", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE", "0"],
        ["/setdcvalueindex", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE", "900"],
        ["/setactive", "SCHEME_CURRENT"],
    ]


@pytest.mark.parametrize(
    "escolha", [{("tela", "ac"): 42}, {("tampa", "ac"): 0}, {("tela", "x"): 0}]
)
def test_tempos_fora_da_lista(escolha: Any) -> None:
    with pytest.raises(ValueError):
        energia.tempos(escolha, rodar=Nativo())


def test_falha_parcial_segue() -> None:
    feitos = energia.tempos(
        {("tela", "ac"): 0, ("disco", "ac"): 0}, rodar=Nativo(falhar="VIDEOIDLE")
    )
    assert [f.ok for f in feitos] == [False, True]


def test_cancelar_entre_chamadas() -> None:
    c = threading.Event()
    c.set()
    n = Nativo()
    feitos = energia.tempos({("tela", "ac"): 0}, rodar=n, cancelar=c)
    assert not feitos[0].ok and n.chamadas == []


def test_desfazer_usa_padrao_do_esquema_e_pula_sem_padrao() -> None:
    n = Nativo()
    feitos = energia.desfazer(
        [("tela", "ac"), ("disco", "dc")], rodar_ps=leitura(disco=None), rodar=n
    )
    assert n.chamadas[0] == ["/setacvalueindex", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE", "900"]
    assert not next(f for f in feitos if f.item == "disco_dc").ok
    assert ["/restoredefaultschemes"] not in n.chamadas and [
        "-restoredefaultschemes"
    ] not in n.chamadas


def test_hibernacao() -> None:
    n = Nativo()
    assert energia.hibernacao(False, rodar=n).ok
    assert n.chamadas == [["/hibernate", "off"]]


def test_situacao_e_rotulos() -> None:
    s = energia.situacao(rodar=leitura())
    assert s.valores[("tela", "ac")] == energia.Valor(600, 900) and s.hibernacao is True
    assert energia.rotulo_tempo(0) == "Nunca" and energia.rotulo_tempo(1200) == "20 min"
    assert energia.rotulo_tempo(None) == "não lido"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_situacao_real() -> None:
    s = energia.situacao()
    assert len(s.esquema) == 36
    assert s.valores[("tela", "ac")].atual is not None
