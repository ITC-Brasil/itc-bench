import logging
import threading

from itc_bench.servicos.executor import powershell
from itc_bench.ui import tarefa


def test_resultado_chega_por_sinal_fora_da_thread_da_tela(qtbot):
    threads = []

    def rodar():
        threads.append(threading.current_thread())
        return powershell("Write-Output 'ok'")

    recebidos = []
    tarefa.iniciar(rodar, recebidos.append, recebidos.append)
    qtbot.waitUntil(lambda: bool(recebidos), timeout=30_000)
    assert recebidos[0].saida.strip() == "ok"
    assert threads[0] is not threading.main_thread()


def test_excecao_vai_para_log_e_sinal_falhou(qtbot, caplog):
    def quebra():
        raise RuntimeError("erro inventado")

    with caplog.at_level(logging.ERROR):
        t = tarefa.Tarefa(quebra)
        with qtbot.waitSignal(t.sinais.falhou, timeout=5_000) as espera:
            tarefa.QThreadPool.globalInstance().start(t)
    assert espera.args == ["erro inventado"]
    assert "Traceback" in caplog.text
    assert "erro inventado" in caplog.text
