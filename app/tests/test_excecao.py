import logging
import sys
from unittest import mock

import pytest

from itc_bench import __main__ as entrada


def test_excecao_vai_para_log_e_tela(qapp, caplog):
    try:
        raise ValueError("falha inventada")
    except ValueError:
        tipo, valor, rastro = sys.exc_info()
    with mock.patch.object(entrada.txt, "aviso") as caixa, caplog.at_level(logging.CRITICAL):
        entrada._excecao(tipo, valor, rastro)
    assert "Traceback" in caplog.text
    assert "falha inventada" in caplog.text
    assert "falha inventada" in caixa.call_args.args[2]


def test_falha_no_inicializar_passa_pelo_gancho(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["itc-bench", "--dev"])
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    with (
        mock.patch.object(entrada.caminhos, "inicializar", side_effect=PermissionError("negado")),
        pytest.raises(PermissionError),
    ):
        entrada.main()
    assert sys.excepthook is entrada._excecao
