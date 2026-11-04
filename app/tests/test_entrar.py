"""Tela Entrar, bloqueio por inatividade, logout e técnico no log (ADR-013)."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from itc_bench.nucleo import log as modulo_log
from itc_bench.servicos import api
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.offline import Cofre
from itc_bench.ui import tema
from itc_bench.ui.entrar import Ocioso
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela

SENHA = "Marcador-Senha-7Q2x!"


def montar(qtbot, monkeypatch, tmp_path, cofre=True):
    monkeypatch.setattr(api, "saude", lambda base: True)

    def entrar(base, usuario, senha, maquina):
        if senha.revelar() != SENHA:
            raise api.Recusado(401, "credenciais_invalidas")
        return api.SessaoApi(Sensivel("itcbs_x"), usuario, "Ana Lima", "2099-01-01T00:00:00Z")

    monkeypatch.setattr(api, "entrar", entrar)
    monkeypatch.setattr(api, "sair", lambda base, token: None)
    tema.aplicar(QApplication.instance())
    j = Janela(
        HandlerTela(),
        "https://api.exemplo.invalid",
        Cofre(tmp_path / "l.dpapi") if cofre else None,
        "NB",
    )
    qtbot.addWidget(j)
    return j


def logar(qtbot, j, usuario="ana.lima", senha=SENHA):
    j.entrar.usuario.setText(usuario)
    j.entrar.senha.setText(senha)
    j.entrar.botao.click()


def test_comeca_na_entrar_e_entra_online(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    assert j.raiz.currentWidget() is j.entrar
    assert j.entrar.senha.echoMode() == j.entrar.senha.EchoMode.Password
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    assert j.entrar.senha.text() == ""
    assert modulo_log.tecnico() == "ana.lima"
    assert j.ocioso.relogio.isActive()


def test_senha_errada_mostra_mensagem(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    logar(qtbot, j, senha="errada")
    qtbot.waitUntil(lambda: j.entrar.mensagem.text() == "Usuário ou senha incorretos.")
    assert j.raiz.currentWidget() is j.entrar


def test_bloqueio_e_destravar_pelo_mesmo_tecnico_sem_rede(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    j.ocioso.venceu.emit()
    assert j.raiz.currentWidget() is j.entrar and j.entrar.titulo.text() == "Bloqueado"

    def sem_rede(*_a):
        raise AssertionError("destravar não chama a API")

    monkeypatch.setattr(api, "entrar", sem_rede)
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    assert j.entrada is not None and j.entrada.login == "ana.lima"


def test_bloqueio_sem_pasta_protegida_exige_login_completo(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path, cofre=False)
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    j.bloquear()
    chamadas = []
    original = api.entrar
    monkeypatch.setattr(api, "entrar", lambda *a: chamadas.append(1) or original(*a))
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    assert chamadas == [1]


def test_outro_tecnico_no_bloqueio_vira_troca(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    j.bloquear()
    logar(qtbot, j, usuario="bruno.souza")
    qtbot.waitUntil(lambda: j.entrada is not None and j.entrada.login == "bruno.souza")
    assert modulo_log.tecnico() == "bruno.souza"


def test_sair_e_sessao_expirada_voltam_para_entrar(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    j.botao_sair.click()
    assert j.raiz.currentWidget() is j.entrar and j.entrada is None
    assert modulo_log.tecnico() == "-"
    logar(qtbot, j)
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
    j.sessao_expirada()
    assert j.raiz.currentWidget() is j.entrar and "expirada" in j.entrar.mensagem.text()


def test_ocioso_conta_tecla_e_vence(qtbot):
    ocioso = Ocioso(200)
    QApplication.instance().installEventFilter(ocioso)
    try:
        with qtbot.waitSignal(ocioso.venceu, timeout=2000):
            ocioso.relogio.start()
            qtbot.wait(120)
            evento = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(QApplication.instance(), evento)
            assert ocioso.relogio.remainingTime() > 150  # a tecla reiniciou o relógio
    finally:
        QApplication.instance().removeEventFilter(ocioso)


def test_senha_ausente_do_bench_log(qtbot, monkeypatch, tmp_path):
    arquivo = modulo_log.configurar(tmp_path / "logs")
    try:
        j = montar(qtbot, monkeypatch, tmp_path)
        logar(qtbot, j, senha="errada-" + SENHA)
        qtbot.waitUntil(lambda: bool(j.entrar.mensagem.text()) and j.entrar.botao.isEnabled())
        logar(qtbot, j)
        qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
        j.bloquear()
        logar(qtbot, j)
        qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.conteudo)
        for h in modulo_log.log.handlers:
            h.flush()
        texto = arquivo.read_text(encoding="utf-8")
        assert SENHA not in texto
        assert "[ana.lima]" in texto
    finally:
        for h in list(modulo_log.log.handlers):
            h.close()
            modulo_log.log.removeHandler(h)
        modulo_log.definir_tecnico(None)


def test_nome_do_glpi_nunca_vira_html(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, tmp_path)
    from itc_bench.servicos.login import Entrada

    j._entrou(Entrada("<b>x</b>", "<img src=x>Ana", None))
    j.bloquear()
    assert j.entrar.subtitulo.textFormat() == Qt.TextFormat.PlainText
    assert "&lt;b&gt;" in j.rodape.text()
