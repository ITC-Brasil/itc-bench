import os

# Widgets sem abrir janela (ADR-010).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest

from itc_bench.nucleo import log as _log


@pytest.fixture(autouse=True)
def _sem_tecnico():
    """O técnico do log é global (ADR-013): cada teste começa e termina sem ele."""
    _log.definir_tecnico(None)
    yield
    _log.definir_tecnico(None)


@pytest.fixture(autouse=True)
def _sem_rede_nem_registro(request, monkeypatch):
    """Cadastros (ADR-014): nenhum teste fala com a API real nem mexe na Unidade do registro."""
    from itc_bench.servicos import api, cadastros

    monkeypatch.setattr(cadastros, "unidade_da_maquina", lambda: None)
    monkeypatch.setattr(cadastros, "gravar_unidade", lambda codigo: None)
    if request.module.__name__ == "test_api_cliente":
        return  # testa o cliente real contra o servidor local roteirizado

    def sem_conexao(*_args: object) -> None:
        raise api.SemConexao("teste")

    monkeypatch.setattr(api, "cadastros", sem_conexao)


@pytest.fixture(autouse=True)
def _telas13_sem_leitura_real(request, monkeypatch):
    """Telas do Módulo 13 leem o Windows ao aparecer; nos testes da janela, não leem."""
    if request.module.__name__ == "test_modulo13_tela":
        return
    from itc_bench.ui import inicio, limpeza, preparacao, registro

    monkeypatch.setattr(inicio.PainelInicio, "carregar", lambda self, forcar=False: None)
    monkeypatch.setattr(limpeza.PainelLimpeza, "calcular", lambda self: None)
    monkeypatch.setattr(registro.PainelRegistro, "carregar", lambda self: None)
    monkeypatch.setattr(
        preparacao.PainelPreparacao, "_carregar_alunos", lambda self, marcar=None: None
    )
    monkeypatch.setattr(preparacao.PainelPreparacao, "_ver_guardado", lambda self: None)
