import os
import subprocess
import sys

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
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "pd"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    caminhos.inicializar()
    assert (tmp_path / "pd" / "ITC" / "Bench" / "logs").is_dir()
    assert (tmp_path / "la" / "ITC" / "Bench").is_dir()
