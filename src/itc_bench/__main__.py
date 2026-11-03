"""Ponto de entrada.

itc-bench            pede elevação de administrador (UAC)
itc-bench --dev      sem administrador, para desenvolver
itc-bench --teste    abre, escreve no log e fecha sozinho
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from itc_bench import __version__
from itc_bench.nucleo import caminhos, elevacao
from itc_bench.nucleo.log import configurar as configurar_log
from itc_bench.nucleo.log import log
from itc_bench.ui import tema
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela


def main() -> int:
    argv = sys.argv
    if elevacao.precisa_elevar(argv, elevacao.eh_admin()):
        if elevacao.pedir_elevacao(argv):
            return 0
        app = QApplication(argv)
        QMessageBox.critical(
            None,
            "ITC Bench",
            "O ITC Bench precisa de privilégios de administrador.\n\n"
            "A elevação foi recusada. Abra o programa de novo e aceite o aviso do Windows.",
        )
        return 1

    caminhos.inicializar()
    tela = HandlerTela()
    log.addHandler(tela)
    arquivo = configurar_log()
    log.info(
        "ITC Bench %s iniciado (admin=%s, args=%s). Log: %s",
        __version__,
        elevacao.eh_admin(),
        argv[1:],
        arquivo,
    )

    app = QApplication(argv)
    tema.aplicar(app)
    janela = Janela(tela)
    janela.show()
    if "--teste" in argv:
        log.info("Modo teste: janela aberta; fechando.")
        QTimer.singleShot(800, app.quit)
    codigo = app.exec()
    log.info("Encerrado com código %s.", codigo)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
