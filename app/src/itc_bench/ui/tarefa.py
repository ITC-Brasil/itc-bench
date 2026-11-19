"""Roda uma função fora da thread da tela e devolve o resultado por sinal (ADR-011).

Exceção dentro da tarefa não passa pelo `sys.excepthook`: vai para o log com traceback e para o
sinal `falhou`.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from itc_bench.nucleo.log import log, tecnico

# Referência até o resultado chegar na thread da tela; sem ela o Python coleta os sinais antes.
_ativas: set["Tarefa"] = set()


class Sinais(QObject):
    concluido = Signal(object)
    falhou = Signal(str)


class Tarefa(QRunnable):
    def __init__(self, funcao: Callable[[], Any]) -> None:
        super().__init__()
        self.funcao = funcao
        self.sinais = Sinais()
        # Quem iniciou: o técnico do log pode trocar antes de a tarefa acabar (ADR-013).
        self.tecnico = tecnico()

    def run(self) -> None:
        try:
            resultado = self.funcao()
        except Exception as erro:  # noqa: BLE001 — vai para o log com traceback e para a tela
            log.exception("Falha na tarefa em segundo plano (iniciada por %s).", self.tecnico)
            self._avisar(self.sinais.falhou, str(erro))
            return
        self._avisar(self.sinais.concluido, resultado)

    def _avisar(self, sinal: Any, valor: Any) -> None:
        """Uma tarefa longa (a leitura da Configuração, ADR-073) pode acabar depois de o Bench
        fechar: os sinais já foram apagados e não há tela para receber."""
        try:
            sinal.emit(valor)
        except RuntimeError:
            log.info(
                "Tarefa em segundo plano terminou depois de a tela fechar; resultado descartado."
            )


def iniciar(
    funcao: Callable[[], Any],
    ao_concluir: Callable[[Any], None],
    ao_falhar: Callable[[str], None],
) -> None:
    """Conecta os sinais e só então põe a função no pool global (sinal sem receptor se perde)."""
    tarefa = Tarefa(funcao)
    tarefa.setAutoDelete(False)
    _ativas.add(tarefa)
    tarefa.sinais.concluido.connect(ao_concluir)
    tarefa.sinais.falhou.connect(ao_falhar)
    tarefa.sinais.concluido.connect(lambda _: _ativas.discard(tarefa))
    tarefa.sinais.falhou.connect(lambda _: _ativas.discard(tarefa))
    QThreadPool.globalInstance().start(tarefa)
