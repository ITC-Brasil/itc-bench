import os
import subprocess
import sys

import pytest

from itc_bench.nucleo import caminhos

# Importa todos os módulos do pacote, inclusive a UI.
IMPORTA_TUDO = """
import importlib, pkgutil, itc_bench
for m in pkgutil.walk_packages(itc_bench.__path__, "itc_bench."):
    importlib.import_module(m.name)
"""


def test_importar_pacote_nao_cria_nada(tmp_path):
    env = {**os.environ, "PROGRAMDATA": str(tmp_path / "pd"), "LOCALAPPDATA": str(tmp_path / "la")}
    subprocess.run([sys.executable, "-c", IMPORTA_TUDO], env=env, check=True)
    assert list(tmp_path.iterdir()) == []


def test_inicializar_cria_pastas(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "programdata", lambda: tmp_path / "pd")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    caminhos.inicializar()
    assert (tmp_path / "pd" / "ITC" / "Bench" / "logs").is_dir()
    assert (tmp_path / "la" / "ITC" / "Bench").is_dir()


def test_programdata_nao_segue_variavel_de_usuario(tmp_path, monkeypatch):
    # Variável de usuário (HKCU\Environment) vale no processo elevado da mesma conta (Módulo 14).
    real = caminhos.programdata()
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))
    monkeypatch.setenv("SystemDrive", "Z:")
    assert caminhos.programdata() == real
    assert caminhos.dados() == real / "ITC" / "Bench"
    assert not str(caminhos.dados()).lower().startswith(("z:", str(tmp_path).lower()))


def test_pasta_do_sistema_recusa_variavel_que_nao_seja_systemdrive(monkeypatch):
    from unittest import mock

    with (
        mock.patch.object(caminhos.winreg, "OpenKey"),
        mock.patch.object(caminhos.winreg, "QueryValueEx", return_value=(r"%TEMP%\x", 2)),
        pytest.raises(RuntimeError),
    ):
        caminhos.pasta_do_sistema("ProgramData")
