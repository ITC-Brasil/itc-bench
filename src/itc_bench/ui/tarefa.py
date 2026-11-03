"""Roda uma função fora da thread da tela e devolve o resultado por sinal (ADR-011).

Exceção dentro da tarefa não passa pelo `sys.excepthook`: vai para o log com traceback e para o
sinal `falhou`.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from itc_bench.nucleo.log import log


class Sinais(QObject):
    concluido = Signal(object)
    falhou = Signal(str)


class Tarefa(QRunnable):
    def __init__(self, funcao: Callable[[], Any]) -> None:
        super().__init__()
        self.funcao = funcao
        self.sinais = Sinais()

    def run(self) -> None:
        try:
            resultado = self.funcao()
        except Exception as erro:  # noqa: BLE001 — vai para o log com traceback e para a tela
            log.exception("Falha na tarefa em segundo plano.")
            self.sinais.falhou.emit(str(erro))
            return
        self.sinais.concluido.emit(resultado)


def iniciar(
    funcao: Callable[[], Any],
    ao_concluir: Callable[[Any], None],
    ao_falhar: Callable[[str], None],
) -> None:
    """Conecta os sinais e só então põe a função no pool global (sinal sem receptor se perde)."""
    tarefa = Tarefa(funcao)
    tarefa.sinais.concluido.connect(ao_concluir)
    tarefa.sinais.falhou.connect(ao_falhar)
    QThreadPool.globalInstance().start(tarefa)
