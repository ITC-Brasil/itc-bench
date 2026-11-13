"""Aba Monitores (ADR-041): cartões, escolhas, confirmação com prazo e volta automática."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from test_video import EXTERNO, NOTEBOOK, Falso

from itc_bench.servicos import video
from itc_bench.ui import monitores as tela


def _painel(qtbot, admin=True, prazo=video.PRAZO):
    p = tela.PainelMonitores(admin, prazo=prazo)
    qtbot.addWidget(p)
    p.lido = True  # não lê o Windows ao aparecer
    p._recebeu(video.ler(Falso([NOTEBOOK, EXTERNO])))
    return p


def test_um_cartao_por_monitor_com_valores_atuais(qtbot):
    p = _painel(qtbot)
    assert len(p.cartoes) == 2
    assert p.estado.text() == "2 monitores conectados."
    c1, c2 = p.cartoes
    assert c1.resolucao.currentData() == "1920x1080"
    assert "(recomendada)" in c1.resolucao.currentText()
    assert c1.frequencia.currentData() == 60
    assert c1.escala.currentData() == 125
    assert c2.frequencia.currentData() == 75
    assert [c.escolha().dispositivo for c in p.cartoes] == [r"\\.\DISPLAY1", r"\\.\DISPLAY2"]


def test_frequencias_seguem_a_resolucao(qtbot):
    p = _painel(qtbot)
    c1 = p.cartoes[0]
    c1.resolucao.setCurrentIndex(c1.resolucao.findData("1366x768"))
    assert [c1.frequencia.itemData(i) for i in range(c1.frequencia.count())] == [60]
    c1.resolucao.setCurrentIndex(c1.resolucao.findData("1920x1080"))
    assert [c1.frequencia.itemData(i) for i in range(c1.frequencia.count())] == [144, 60]


def test_sem_admin_so_le(qtbot):
    p = _painel(qtbot, admin=False)
    assert not p.b_aplicar.isEnabled()
    assert not p.cartoes[0].resolucao.isEnabled()


def test_nada_mudou_nao_pergunta(qtbot, monkeypatch):
    p = _painel(qtbot)
    monkeypatch.setattr(tela, "confirmar", lambda *_a: (_ for _ in ()).throw(AssertionError))
    p._aplicar()
    assert p.estado.text() == "Nada mudou."


def test_manter_sem_resposta_volta_sozinho(qtbot):
    p = _painel(qtbot, prazo=1)
    assert p.manter() is False


def test_manter_com_clique(qtbot):
    p = _painel(qtbot)

    def clicar() -> None:
        caixa = QApplication.activeModalWidget()
        assert isinstance(caixa, QMessageBox)
        manter = next(b for b in caixa.buttons() if b.text() == "Manter")
        manter.click()

    QTimer.singleShot(200, clicar)
    assert p.manter() is True


def test_sem_confirmar_desfaz(qtbot, monkeypatch):
    p = _painel(qtbot)
    chamados: list[video.Antes] = []
    monkeypatch.setattr(p, "manter", lambda: False)
    monkeypatch.setattr(p, "carregar", lambda: None)
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda f, ok, falhou: ok(f()))
    monkeypatch.setattr(video, "desfazer", lambda antes: chamados.append(antes) or [])
    antes = video.Antes(p.monitores)
    p._aplicado(([video.Feito("1. Tela", True, "aplicado")], antes))
    assert chamados == [antes]
    assert "Voltou" in p.registro.toPlainText()


def test_nada_aplicado_nao_pergunta(qtbot, monkeypatch):
    p = _painel(qtbot)
    monkeypatch.setattr(p, "manter", lambda: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(p, "carregar", lambda: None)
    p._aplicado(([video.Feito("1. Tela", False, "modo não aceito")], video.Antes()))
    assert p.estado.text() == "Nada foi aplicado."


def test_desenho_como_no_windows_lado_a_lado(qtbot):
    p = _painel(qtbot)
    p.mapa.resize(600, 210)
    r1, r2 = p.mapa.retangulos()
    assert r1.right() < r2.left()  # o externo fica à direita, como na área de trabalho
    assert abs(r1.top() - r2.top()) < 1
    assert p.pilha.currentIndex() == 0


def test_clicar_no_monitor_mostra_as_opcoes_dele(qtbot):
    from PySide6.QtCore import QPoint

    p = _painel(qtbot)
    p.mapa.resize(600, 210)
    centro = p.mapa.retangulos()[1].center()
    qtbot.mouseClick(
        p.mapa, Qt.MouseButton.LeftButton, pos=QPoint(int(centro.x()), int(centro.y()))
    )
    assert p.mapa.atual == 1
    assert p.pilha.currentWidget() is p.cartoes[1]


def test_monitor_alterado_aparece_no_desenho(qtbot):
    p = _painel(qtbot)
    c2 = p.cartoes[1]
    c2.orientacao.setCurrentIndex(c2.orientacao.findData(1))
    assert p.mapa.alterados == {1}
    c2.orientacao.setCurrentIndex(c2.orientacao.findData(0))
    assert p.mapa.alterados == set()


def test_desenho_pinta_sem_erro(qtbot):
    p = _painel(qtbot)
    p.mapa.resize(600, 210)
    assert not p.mapa.grab().isNull()
