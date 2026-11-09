"""Ponto de entrada.

itc-bench            pede elevação de administrador (UAC)
itc-bench --dev      sem administrador, para desenvolver
itc-bench --teste    abre, escreve no log e fecha sozinho
"""

import os
import sys
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from itc_bench import __version__
from itc_bench.nucleo import acl, caminhos, elevacao, instalacao
from itc_bench.nucleo.log import configurar as configurar_log
from itc_bench.nucleo.log import log
from itc_bench.servicos import api, atualizacao
from itc_bench.servicos.cadastros import Armazem
from itc_bench.servicos.executor import Sensivel
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
    # Antes de qualquer QApplication: plugin, plataforma e DLL nunca vêm do ambiente do usuário.
    retirados = instalacao.limpar_ambiente()
    instalacao.restringir_dlls()
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

    admin = elevacao.modo_admin(argv, elevacao.eh_admin())
    # Pasta de instalação (ADR-025): alterada, o Bench não mexe em nada da máquina.
    erro_pasta: Exception | None = None
    try:
        instalacao.conferir_instalacao()
        if fora := instalacao.caminho_fora_do_pacote():
            raise instalacao.PastaAlterada(f"{len(fora)} entrada(s) de sys.path fora do pacote.")
    except (instalacao.PastaAlterada, OSError) as erro:
        erro_pasta = erro
        admin = False
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
    if retirados:
        log.warning("Variáveis do ambiente ignoradas: %s", ", ".join(retirados))
    estado_mutex = instalacao.criar_mutex(admin)
    if estado_mutex == "alheio":
        log.warning("Outro usuário ocupa o nome do mutex do Bench; ignorado (ADR-026).")
    elif estado_mutex != "criado":
        log.info("Mutex do Bench não criado (%s).", estado_mutex)
    if erro_pasta:
        log.error("Pasta de instalação recusada: %s", erro_pasta)
        if "--dev" not in argv:
            if "--teste" not in argv:  # no CI a caixa modal travaria o runner
                _ = QApplication(argv)
                txt.aviso(
                    None,
                    "ITC Bench",
                    f"A pasta de instalação foi alterada. Reinstale o ITC Bench.\n\n{erro_pasta}",
                    QMessageBox.Icon.Critical,
                )
            return 3
    if "--teste" in argv:
        try:
            log.info("Recursos: %d arquivos lidos.", instalacao.ler_recursos())
        except OSError as erro:
            log.error("Recursos do pacote incompletos: %s", erro)
            return 4
    if "--teste-atualizacao" in argv:
        return _teste_atualizacao(admin and not erro_acl)
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
    atualizar = protegida_ok and not dev and "--teste" not in argv
    janela = Janela(
        tela,
        base,
        cofre,
        armazem=armazem,
        admin=admin,
        fila=fila,
        atualizar=atualizar,
        mutex_alheio=estado_mutex == "alheio",
    )
    janela.show()
    if "--teste" in argv:
        log.info("Modo teste: janela aberta; fechando.")
        QTimer.singleShot(800, app.quit)
    codigo = app.exec()
    log.info("Encerrado com código %s.", codigo)
    return codigo


def _teste_atualizacao(protegida_ok: bool) -> int:
    """CI (ADR-026): consulta, baixa e "fecha" sem janela, com a sessão de teste do job.

    No pacote distribuível recusa sem consultar a API; nada roda sem manifesto assinado pelas
    chaves do pacote. Sai 0 com o instalador disparado (ele espera este processo sair), 5 se
    recusou.
    """
    # Achado 2 da revisão: só na cópia de teste do CI (marcador gravado pelo job ao lado das
    # chaves de teste, na pasta conferida pelo ADR-025) e com a sessão vinda do ambiente do job.
    sessao = os.environ.pop(atualizacao.VARIAVEL_TESTE, "")
    if not atualizacao.copia_de_teste():
        log.error("Teste de atualização recusado: não é a cópia de teste do CI.")
        return 5
    if not sessao:
        log.error("Teste de atualização recusado: sessão de teste ausente no ambiente.")
        return 5
    base = api.endereco(False)
    if not protegida_ok or not base:
        log.error("Teste de atualização: sem administrador, pasta protegida ou endereço.")
        return 5
    try:
        base = api.validar(base, False)
        oferta = atualizacao.consultar(base, Sensivel(sessao))
        atualizacao.limpar(manter=oferta)
        if oferta is None:
            log.error("Teste de atualização: nenhuma versão anunciada.")
            return 5
        atualizacao.baixar(base, Sensivel(sessao), oferta)
        pid = atualizacao.instalar_ao_fechar(
            oferta, os.getpid(), False, soltar_mutex=instalacao.soltar_mutex
        )
    except (
        atualizacao.Recusada,
        api.SemConexao,
        api.ErroApi,
        api.Recusado,
        OSError,
        ValueError,
    ) as erro:
        log.error("Teste de atualização recusado: %s", erro)
        return 5
    if pid is None:
        return 5
    log.info("Teste de atualização: instalador disparado (PID %s).", pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
