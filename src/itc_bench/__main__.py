"""Ponto de entrada.

    itc-bench            pede elevação de administrador (UAC)
    itc-bench --dev      sem administrador, para desenvolver
    itc-bench --teste    abre, escreve no log e fecha sozinho
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from itc_bench.nucleo import elevacao


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

    app = QApplication(argv)
    if "--teste" in argv:
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
