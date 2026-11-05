"""Identificação (ADR-018): validação, leitura do estado, montagem do ambiente, recusas.

Só nomes fictícios. Nenhum teste renomeia a máquina: o PowerShell real roda só o trecho de
leitura (Windows), e o `renomear.ps1` real só com `ITC_TESTE_IDENTIFICACAO=1` numa máquina de
teste elevada.
"""

import json
import logging
import os
import sys

import pytest

from itc_bench.nucleo.elevacao import eh_admin
from itc_bench.servicos import executor, identificacao
from itc_bench.servicos.executor import Resultado
from itc_bench.servicos.identificacao import Estado, normalizar, validar

ESTADO = Estado("PC-TESTE", "PC-TESTE", False, frozenset({"TESTE01", "ADMINISTRADORES"}))


def res(saida: str = "", codigo: int = 0, esgotado: bool = False) -> Resultado:
    return Resultado(codigo, saida, "", 0.1, esgotado)


def json_estado(**kw: object) -> str:
    base: dict[str, object] = {
        "ativo": "PC-TESTE",
        "pendente": "PC-TESTE",
        "dominio": False,
        "azuread": False,
        "nomes": ["Teste01", "Administradores"],
    }
    base.update(kw)
    return json.dumps(base)


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("ABC01-NB01", None),
        ("X", None),
        ("A" * 15, None),
        ("", "Digite"),
        ("A" * 16, "15"),
        ("-ABC", "hífen"),
        ("ABC-", "hífen"),
        ("ABC_01", "letras"),
        ("AÇÃO01", "letras"),
        ("ABC 01", "letras"),
        ("ABC.01", "letras"),
        ('A"B', "letras"),
        ("12345", "só números"),
        ("SYSTEM", "reservado"),
        ("LOCALHOST", "reservado"),
        ("TESTE01", "conta ou grupo"),
        ("PC-TESTE", "já é o nome"),
    ],
)
def test_validar(nome: str, esperado: str | None) -> None:
    motivo = validar(nome, ESTADO)
    if esperado is None:
        assert motivo is None
    else:
        assert motivo is not None and esperado in motivo


def test_normalizar() -> None:
    assert normalizar("  abc01-nb01 ") == "ABC01-NB01"


def test_pendente_e_dominio() -> None:
    pendente = Estado("PC-VELHO", "PC-NOVO", False, frozenset())
    assert pendente.reinicio_pendente
    assert "depois de reiniciar" in (validar("PC-NOVO", pendente) or "")
    assert validar("PC-VELHO", pendente) is None  # voltar ao nome ativo é uma troca válida
    assert "domínio" in (validar("PC-NOVO", Estado("A", "A", True, frozenset())) or "")


def test_ler() -> None:
    e = identificacao.ler(json_estado(pendente="PC-NOVO", azuread=True))
    assert e.ativo == "PC-TESTE" and e.pendente == "PC-NOVO" and e.dominio
    assert e.nomes_locais == {"TESTE01", "ADMINISTRADORES"}
    with pytest.raises(identificacao.ErroIdentificacao):
        identificacao.ler("isto não é json")
    with pytest.raises(identificacao.ErroIdentificacao):
        identificacao.ler("{}")


class Roteiro:
    def __init__(self, *respostas: Resultado) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[tuple[str, dict[str, object]]] = []

    def __call__(self, script: str, **kw: object) -> Resultado:
        self.chamadas.append((script, kw))
        return self.respostas.pop(0)


def test_renomear_nome_so_pelo_ambiente(caplog: pytest.LogCaptureFixture) -> None:
    rodar = Roteiro(res(json_estado()), res("OK\n"))
    with caplog.at_level(logging.INFO):
        feito = identificacao.renomear(" abc01-nb01 ", rodar=rodar)
    assert feito.ok and "reiniciar" in feito.mensagem
    script, kw = rodar.chamadas[1]
    assert kw["nome"] == "ABC01-NB01"
    assert "ABC01-NB01" not in script and "$env:ITC_NOME" in script
    assert "PC-TESTE -> ABC01-NB01" in caplog.text


def test_renomear_recusa_antes_do_powershell() -> None:
    rodar = Roteiro(res(json_estado(dominio=True)))
    feito = identificacao.renomear("ABC01", rodar=rodar)
    assert not feito.ok and "domínio" in feito.mensagem
    assert len(rodar.chamadas) == 1  # só a leitura


def test_renomear_erro_do_windows_na_tela_codigo_no_log(caplog: pytest.LogCaptureFixture) -> None:
    rodar = Roteiro(res(json_estado()), res("ERRO|renomear|Mensagem do Windows\n", codigo=1))
    with caplog.at_level(logging.INFO):
        feito = identificacao.renomear("ABC01", rodar=rodar)
    assert not feito.ok and "Mensagem do Windows" in feito.mensagem
    assert "falhou: renomear" in caplog.text and "Mensagem do Windows" not in caplog.text


def test_renomear_tempo_esgotado() -> None:
    rodar = Roteiro(res(json_estado()), res(codigo=None, esgotado=True))  # type: ignore[arg-type]
    assert identificacao.renomear("ABC01", rodar=rodar).mensagem == "Tempo esgotado."


def test_reiniciar_argumentos_fixos() -> None:
    chamadas: list[list[str]] = []

    def rodar(args: list[str], **_kw: object) -> Resultado:
        chamadas.append(args)
        return res()

    assert identificacao.reiniciar(rodar=rodar).ok
    assert chamadas[0][0].lower().endswith(r"system32\shutdown.exe")
    assert chamadas[0][1:] == ["/r", "/t", "10"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_estado_real() -> None:
    e = identificacao.estado()
    assert e.ativo and len(e.ativo) <= 15


@pytest.mark.skipif(
    os.environ.get("ITC_TESTE_IDENTIFICACAO") != "1" or not eh_admin(),
    reason="renomeia a máquina: só em máquina de teste elevada",
)
def test_renomear_real_e_voltar() -> None:  # pragma: no cover - roteiro manual
    original = identificacao.estado()
    assert identificacao.renomear("TESTE-08").ok
    assert identificacao.estado().pendente.upper() == "TESTE-08"
    assert executor.powershell(identificacao.script("renomear"), nome=original.ativo).ok
