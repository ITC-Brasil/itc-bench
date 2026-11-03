"""Entradas hostis passadas como dado chegam intactas ao filho e não executam nada.

Processos reais: PowerShell lê por `ITC_*`, Python lê pelo argumento e pelo stdin. Cada valor
tenta criar um arquivo-marca; nenhum pode existir no fim.
"""

import base64
import sys

import pytest

from itc_bench.servicos.executor import executar, powershell


def _hostis(marca: str) -> list[str]:
    return [
        f"'; New-Item -ItemType File '{marca}'; '",
        f'"; New-Item -ItemType File "{marca}"; "',
        f"x & type nul > {marca}",
        f"x | Out-File {marca}",
        f"x; New-Item {marca}",
        f"x ^& echo > {marca}",
        f"%COMSPEC% /c type nul > {marca} %PATH%",
        f"$(New-Item {marca})",
        f"`$(New-Item {marca})`",
        f"linha1\nNew-Item {marca}\r\nlinha3",
        "  espaços  no início e no fim  ",
        "ação, coração, pão, Ç, ü, €, 中文",
        "",
        "A" * 30_000,
    ]


@pytest.fixture
def marca(tmp_path):
    caminho = tmp_path / "executou.txt"
    yield str(caminho)
    assert not caminho.exists(), "um valor hostil executou comando"


def _b64(texto: str) -> str:
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


@pytest.mark.parametrize("indice", range(14))
def test_powershell_por_ambiente(marca, indice):
    valor = _hostis(marca)[indice]
    r = powershell(
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$env:ITC_VALOR))",
        valor=valor,
    )
    assert r.ok, r.erros
    assert r.saida.strip() == _b64(valor)


ECO = "import base64,sys; print(base64.b64encode(sys.argv[1].encode('utf-8')).decode())"
ECO_STDIN = "import base64,sys; print(base64.b64encode(sys.stdin.buffer.read()).decode())"


@pytest.mark.parametrize("indice", range(14))
def test_argumento_para_programa_nativo(marca, indice):
    valor = _hostis(marca)[indice]
    r = executar([sys.executable, "-I", "-c", ECO, valor])
    assert r.ok, r.erros
    assert r.saida.strip() == _b64(valor)


@pytest.mark.parametrize("indice", range(14))
def test_entrada_pelo_stdin(marca, indice):
    valor = _hostis(marca)[indice]
    r = executar([sys.executable, "-I", "-c", ECO_STDIN], entrada=valor, codificacao="utf-8")
    assert r.ok, r.erros
    assert r.saida.strip() == _b64(valor)
