import logging
from unittest import mock

import pytest

from itc_bench.nucleo import log as modulo_log


@pytest.fixture(autouse=True)
def limpa_handlers():
    yield
    for h in list(modulo_log.log.handlers):
        h.close()
        modulo_log.log.removeHandler(h)


def test_rotacao_no_limite(tmp_path):
    arquivo = modulo_log.configurar(tmp_path)
    linha = "x" * 1000
    for _ in range(6 * 1100):  # ~6,6 MiB, mais que os 5 arquivos juntos
        modulo_log.log.info(linha)
    nomes = sorted(p.name for p in tmp_path.iterdir())
    assert nomes == ["bench.log", "bench.log.1", "bench.log.2", "bench.log.3", "bench.log.4"]
    for p in tmp_path.iterdir():
        assert p.stat().st_size <= modulo_log.TAMANHO_MAXIMO
    assert arquivo == tmp_path / "bench.log"


def test_sem_permissao_vai_para_localappdata(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    original = modulo_log._handler

    def falha_no_programdata(pasta):
        if "la" not in pasta.parts:
            raise PermissionError(13, "Acesso negado")
        return original(pasta)

    with (
        mock.patch.object(modulo_log, "_handler", falha_no_programdata),
        caplog.at_level(logging.WARNING),
    ):
        arquivo = modulo_log.configurar(tmp_path / "pd")
    assert arquivo == tmp_path / "la" / "ITC" / "Bench" / "logs" / "bench.log"
    assert "Sem permissão" in caplog.text
