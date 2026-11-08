"""Trava de origem dos binários do pacote (ADR-025): o `PATH` da máquina de build não entra."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "empacotamento"))
import origens

RAIZES = {
    "python": r"C:\py",
    "projeto": r"C:\repo\app\.venv",
    "system32": r"C:\Windows\System32",
}


def test_origens_permitidas_contadas_pela_raiz_mais_longa():
    binarios = [
        ("python313.dll", r"C:\py\python313.dll", "BINARY"),
        ("libcrypto-3-x64.dll", r"C:\py\DLLs\libcrypto-3-x64.dll", "BINARY"),
        ("Qt6Core.dll", r"C:\repo\app\.venv\Lib\site-packages\PySide6\Qt6Core.dll", "BINARY"),
        ("x.dll", r"c:\windows\system32\x.dll", "BINARY"),
    ]
    assert origens.conferir(binarios, RAIZES) == {"python": 2, "projeto": 1, "system32": 1}


@pytest.mark.parametrize(
    "origem",
    [
        r"C:\Program Files\Algum JDK\bin\libcrypto-3-x64.dll",  # pasta do PATH
        r"C:\py-falso\python313.dll",  # prefixo parecido, outra pasta
        r"C:\Windows\System32-x\a.dll",
        r"C:\repo\app\.venv\..\..\fora\a.dll",  # sai da raiz por ..
        r"C:\Users\qualquer\AppData\Local\Temp\a.dll",
    ],
)
def test_origem_fora_para_o_build(origem):
    with pytest.raises(SystemExit, match="origem não permitida"):
        origens.conferir([("a.dll", origem, "BINARY")], RAIZES)


def test_ucrt_fica_fora_do_pacote():
    binarios = [
        ("ucrtbase.dll", r"C:\jdk\bin\ucrtbase.dll", "BINARY"),
        ("api-ms-win-crt-math-l1-1-0.dll", r"C:\jdk\bin\api-ms-win-crt-math-l1-1-0.dll", "BINARY"),
        ("Qt6Core.dll", r"C:\repo\app\.venv\Qt6Core.dll", "BINARY"),
    ]
    ficam, tirados = origens.separar_do_sistema(binarios)
    assert [b[0] for b in ficam] == ["Qt6Core.dll"]
    assert tirados == ["api-ms-win-crt-math-l1-1-0.dll", "ucrtbase.dll"]


def test_raizes_reais_sem_ambiente():
    r = origens.raizes()
    assert r["system32"].lower().endswith("system32")
    assert r["python"] == sys.base_prefix
