"""Ponto de entrada.

itc-bench            pede elevação de administrador (UAC)
itc-bench --dev      sem administrador, para desenvolver
itc-bench --teste    abre, escreve no log e fecha sozinho
"""

import sys
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from itc_bench import __version__
from itc_bench.nucleo import acl, caminhos, elevacao
from itc_bench.nucleo.log import configurar as configurar_log
from itc_bench.nucleo.log import log
from itc_bench.servicos import api
from itc_bench.servicos.cadastros import Armazem
from itc_bench.servicos.fila import NOME as NOME_FILA
from itc_bench.servicos.fila import Fila
from itc_bench.servicos.offline import Cofre
from itc_bench.ui import tema
from itc_bench.ui import texto as txt
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela


def _excecao(tipo: type[BaseException], valor: BaseException, rastro: TracebackType | None) -> None:
    """Exceção não tratada: traceback no log e mensagem na tela."""
    log.critical("Erro não tratado.", exc_info=(tipo, valor, rastro))
    _ = QApplication.instance() or QApplication(sys.argv)
    txt.aviso(
        None,
        "ITC Bench",
        f"Erro inesperado: {valor}\n\nDetalhes em bench.log, na pasta de logs do ITC Bench.",
        QMessageBox.Icon.Critical,
    )


def main() -> int:
    sys.excepthook = _excecao
    argv = sys.argv
    if elevacao.precisa_elevar(argv, elevacao.eh_admin()):
        if elevacao.pedir_elevacao(argv):
            return 0
        app = QApplication(argv)
        txt.aviso(
            None,
            "ITC Bench",
            "O ITC Bench precisa de privilégios de administrador.\n\n"
            "A elevação foi recusada. Abra o programa de novo e aceite o aviso do Windows.",
            QMessageBox.Icon.Critical,
        )
        return 1

    admin = elevacao.eh_admin()
    erro_acl: acl.ErroAcl | None = None
    try:
        caminhos.inicializar(admin)
    except acl.PontoDeReparse:
        raise  # não abre log por um caminho desviado; o excepthook mostra na tela
    except acl.ErroAcl as erro:
        erro_acl = erro
    tela = HandlerTela()
    log.addHandler(tela)
    arquivo = configurar_log()
    log.info(
        "ITC Bench %s iniciado (admin=%s, args=%s). Log: %s",
        __version__,
        admin,
        argv[1:],
        arquivo,
    )
    if not admin:
        log.info("Sem administrador: ACL de %s não aplicado.", caminhos.dados().parent)
    elif erro_acl:
        log.error("%s", erro_acl)

    app = QApplication(argv)
    tema.aplicar(app)
    if erro_acl:
        txt.aviso(None, "ITC Bench", f"{erro_acl}\n\nDetalhes em {arquivo}.")
    dev = "--dev" in argv
    base = api.endereco(dev)
    if base:
        try:
            base = api.validar(base, dev)
        except ValueError as erro:
            log.error("Endereço da API recusado: %s", erro)
            txt.aviso(None, "ITC Bench", f"{erro}\n\nO login só funciona offline.")
            base = None
    else:
        log.warning("Endereço da API não configurado; só o login offline funciona.")
    # Sem administrador não existe pasta protegida: sem login offline (ADR-013).
    cofre = Cofre(caminhos.protegida() / "logins.dpapi") if admin and not erro_acl else None
    if cofre is None:
        log.info("Login offline desligado (sem administrador ou sem pasta protegida).")
    # Cache dos cadastros (ADR-014): na pasta protegida; sem ela, só em memória.
    protegida_ok = admin and not erro_acl
    armazem = Armazem(caminhos.protegida() / "cadastros.dpapi" if protegida_ok else None)
    if not protegida_ok:
        log.info("Cache dos cadastros só em memória (sem administrador ou sem pasta protegida).")
    # Fila dos diagnósticos não enviados (ADR-015): mesma regra do cache.
    fila = Fila(caminhos.protegida() / NOME_FILA if protegida_ok else None)
    janela = Janela(tela, base, cofre, armazem=armazem, admin=admin, fila=fila)
    janela.show()
    if "--teste" in argv:
        log.info("Modo teste: janela aberta; fechando.")
        QTimer.singleShot(800, app.quit)
    codigo = app.exec()
    log.info("Encerrado com código %s.", codigo)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
