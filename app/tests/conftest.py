import os

# Widgets sem abrir janela (ADR-010).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest

from itc_bench.nucleo import log as _log


@pytest.fixture(autouse=True)
def _apaga_janelas_do_teste():
    """Cada teste termina sem janela viva e sem tarefa de fundo rodando.

    Sem isto, as janelas fechadas ficavam vivas até o fim da suíte (5.020 widgets depois dos 4
    testes de `test_janela.py`): cada troca de tema repintava todas (30 a 50 s por troca na
    suíte inteira), e destruí-las no encerramento do processo deu código 1 com tudo passando
    no CI.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    QThreadPool.globalInstance().waitForDone(60_000)
    app.processEvents()  # sinais das tarefas que acabaram de terminar
    for janela in QApplication.topLevelWidgets():
        janela.close()
        janela.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


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
    # ADR-048: o nome desta máquina não decide a unidade nos testes.
    monkeypatch.setattr(cadastros, "nome_do_computador", lambda: "PC-DE-TESTE")
    if request.module.__name__ == "test_api_cliente":
        return  # testa o cliente real contra o servidor local roteirizado

    def sem_conexao(*_args: object) -> None:
        raise api.SemConexao("teste")

    monkeypatch.setattr(api, "cadastros", sem_conexao)


@pytest.fixture(autouse=True)
def _sem_mudar_monitor(monkeypatch):
    """Monitores (ADR-041): nenhum teste muda a resolução ou a escala da máquina."""
    from itc_bench.nucleo import video

    def proibido(*_args: object) -> int:
        raise AssertionError("teste tentou mudar o monitor de verdade")

    monkeypatch.setattr(video, "mudar_modo", proibido)
    monkeypatch.setattr(video, "mudar_escala", proibido)


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
