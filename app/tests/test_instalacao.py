"""Bench empacotado (ADR-025): ambiente, pasta de instalação e recursos."""

import os
import sys
from pathlib import Path

import pytest

from itc_bench.nucleo import instalacao as i

TI = i.TRUSTED_INSTALLER
# DACL real de uma pasta criada pelo instalador em Program Files (herdada).
HERDADA = (
    f"O:BAD:AI(A;ID;FA;;;{TI})(A;CIIOID;GA;;;{TI})(A;ID;FA;;;SY)(A;OICIIOID;GA;;;SY)"
    "(A;ID;FA;;;BA)(A;OICIIOID;GA;;;BA)(A;ID;0x1200a9;;;BU)(A;OICIIOID;GXGR;;;BU)"
    "(A;OICIIOID;GA;;;CO)(A;ID;0x1200a9;;;AC)(A;OICIIOID;GXGR;;;AC)"
)


def test_ambiente_sem_qt_nem_python_do_usuario():
    amb = {
        "QT_PLUGIN_PATH": r"C:\x",
        "QT_QPA_PLATFORM_PLUGIN_PATH": r"C:\x",
        "qt_debug_plugins": "1",
        "QML2_IMPORT_PATH": r"C:\x",
        "PYTHONPATH": r"C:\x",
        "PYTHONHOME": r"C:\x",
        "QT_QPA_PLATFORM": "windows:fontengine=x",
        "PATH": r"C:\Windows",
        "ITC_X": "1",
    }
    retirados = i.limpar_ambiente(amb)
    assert amb == {"PATH": r"C:\Windows", "ITC_X": "1"}
    assert "PYTHONPATH" in retirados


def test_ambiente_mantem_so_a_plataforma_do_ci():
    amb = {"QT_QPA_PLATFORM": "offscreen"}
    assert i.limpar_ambiente(amb) == []
    assert amb == {"QT_QPA_PLATFORM": "offscreen"}


def test_main_limpa_o_ambiente_antes_do_qt(monkeypatch):
    """Injeta as variáveis no processo e confere que o `main` tira antes do QApplication."""
    from itc_bench import __main__ as entrada

    monkeypatch.setenv("QT_PLUGIN_PATH", r"C:\usuario\plugins")
    monkeypatch.setenv("PYTHONPATH", r"C:\usuario\py")
    visto: dict[str, str | None] = {}

    def parar(*_a, **_k):
        visto["qt"] = os.environ.get("QT_PLUGIN_PATH")
        visto["py"] = os.environ.get("PYTHONPATH")
        raise SystemExit(9)

    monkeypatch.setattr(entrada.elevacao, "precisa_elevar", parar)
    with pytest.raises(SystemExit):
        entrada.main()
    assert visto == {"qt": None, "py": None}


@pytest.mark.parametrize(
    ("sddl", "ok"),
    [
        (HERDADA, True),
        (f"O:{TI}D:PAI(A;;FA;;;{TI})(A;;0x1301bf;;;SY)(A;;0x1301bf;;;BA)(A;;0x1200a9;;;BU)", True),
        ("O:BAD:PAI(A;;FA;;;SY)(A;;FA;;;BA)(D;;FA;;;WD)", True),  # negação não dá acesso
        (HERDADA + "(A;;0x1301bf;;;BU)", False),  # Usuários modificam
        (HERDADA + "(A;OICI;FW;;;AU)", False),
        (HERDADA + "(A;;WD;;;WD)", False),  # WRITE_DAC para Todos
        (HERDADA + "(A;OICIIO;GW;;;BU)", False),  # herdável: o filho novo seria gravável
        (HERDADA + "(A;;0x4;;;IU)", False),  # criar subpasta
        (HERDADA + "(A;;0x10000;;;S-1-5-21-1-2-3-1001)", False),  # DELETE para uma conta
        (HERDADA + "(A;;ZZ;;;BU)", False),  # alias desconhecido conta como escrita
        ("O:BUD:PAI(A;;FA;;;SY)(A;;FA;;;BA)", False),  # dono Usuários
        ("O:BAD:NO_ACCESS_CONTROL", False),
        ("O:BA", False),  # sem DACL
    ],
)
def test_criterio_de_escrita(sddl, ok):
    assert (i.escrita_de_terceiros(sddl) == []) is ok


def _instalada(tmp_path: Path) -> Path:
    pasta = tmp_path / "Program Files" / "ITC" / "Bench"
    (pasta / "_internal").mkdir(parents=True)
    (pasta / "ITC Bench.exe").write_bytes(b"MZ")
    (pasta / "_internal" / "a.dll").write_bytes(b"MZ")
    return pasta


def test_pasta_ok(tmp_path):
    pasta = _instalada(tmp_path)
    vistos: list[str] = []
    i.conferir_pasta(pasta / "ITC Bench.exe", pasta, lambda p: vistos.append(p.name) or HERDADA)
    assert {"ITC", "Bench", "_internal", "a.dll", "ITC Bench.exe"} <= set(vistos)


def test_pasta_diferente_da_fixa(tmp_path):
    pasta = _instalada(tmp_path)
    with pytest.raises(i.PastaAlterada, match="pasta de instalação esperada"):
        i.conferir_pasta(pasta / "ITC Bench.exe", tmp_path / "outra", lambda _p: HERDADA)


def test_arquivo_gravavel_dentro(tmp_path):
    pasta = _instalada(tmp_path)

    def ler(p: Path) -> str:
        return HERDADA + "(A;;FA;;;BU)" if p.name == "a.dll" else HERDADA

    with pytest.raises(i.PastaAlterada, match=r"a.dll"):
        i.conferir_pasta(pasta / "ITC Bench.exe", pasta, ler)


def test_pai_gravavel(tmp_path):
    pasta = _instalada(tmp_path)

    def ler(p: Path) -> str:
        return HERDADA + "(A;OICI;FA;;;BU)" if p.name == "ITC" else HERDADA

    with pytest.raises(i.PastaAlterada, match="ITC"):
        i.conferir_pasta(pasta / "ITC Bench.exe", pasta, ler)


@pytest.mark.skipif(sys.platform != "win32", reason="junction é do Windows")
def test_junction_dentro_e_recusada(tmp_path):
    import _winapi

    pasta = _instalada(tmp_path)
    alvo = tmp_path / "usuario"
    alvo.mkdir()
    _winapi.CreateJunction(str(alvo), str(pasta / "_internal" / "plugins"))
    with pytest.raises(i.PastaAlterada, match="reparse"):
        i.conferir_pasta(pasta / "ITC Bench.exe", pasta, lambda _p: HERDADA)


def test_fora_do_congelado_nada_e_conferido(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    i.conferir_instalacao()
    assert i.caminho_fora_do_pacote() == []
    i.restringir_dlls()  # não mexe na busca de DLL do pytest


def test_recursos_todos_lidos():
    assert i.ler_recursos() > 50


def test_recursos_vazio(tmp_path):
    with pytest.raises(FileNotFoundError):
        i.ler_recursos(tmp_path)


def test_mutex():
    assert "ITCBench" not in i.criar_mutex()
