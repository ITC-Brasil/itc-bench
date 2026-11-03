"""Leva as linhas do log em arquivo para a tela (thread-safe via sinal Qt)."""

import logging

from PySide6.QtCore import QObject, Signal

from itc_bench.nucleo.log import FORMATO


class _Ponte(QObject):
    linha = Signal(str)


class HandlerTela(logging.Handler):
    """Guarda o histórico e emite cada linha nova; a tela Registro se conecta em `ponte.linha`."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter(FORMATO, "%H:%M:%S"))
        self.ponte = _Ponte()
        self.historico: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        texto = self.format(record)
        self.historico.append(texto)
        self.ponte.linha.emit(texto)
