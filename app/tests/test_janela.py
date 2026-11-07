from PySide6.QtWidgets import QApplication

from itc_bench.nucleo.log import log
from itc_bench.ui import tema
from itc_bench.ui.janela import Janela
from itc_bench.ui.limpeza import AJUDA as AJUDA_LIMPEZA
from itc_bench.ui.log_qt import HandlerTela
from itc_bench.ui.navegacao import GRUPOS


def janela(qtbot):
    tema.aplicar(QApplication.instance())
    handler = HandlerTela()
    j = Janela(handler)
    qtbot.addWidget(j)
    return j, handler


def test_sete_grupos_e_vinte_itens(qtbot):
    j, _ = janela(qtbot)
    assert [g for g, _ in GRUPOS] == [
        "Início",
        "Preparar",
        "Software",
        "Segurança",
        "Aparência e periféricos",
        "Diagnóstico",
        "Sistema",
    ]
    assert len(j.nav) == 20
    assert j.pilha.currentWidget() is j.telas["inicio"]


def test_cada_item_abre_sua_tela_com_modulo(qtbot):
    j, _ = janela(qtbot)
    for _, itens in GRUPOS:
        for item in itens:
            j.nav[item.chave].click()
            tela = j.telas[item.chave]
            assert j.pilha.currentWidget() is tela
            assert tela.titulo.text() == item.titulo
            if item.chave != "config":  # Configurações já tem conteúdo (Módulo 05)
                assert item.modulo in tela.modulo.text()


def test_botao_ajuda_abre_e_fecha_popup(qtbot):
    j, _ = janela(qtbot)
    j.show()
    j.raiz.setCurrentWidget(j.conteudo)  # sem login: o conteúdo fica atrás da Entrar
    tela = j.telas["limpeza"]
    j.abrir("limpeza")
    tela.botao_ajuda.click()
    assert tela.ajuda.isVisible()
    assert tela.ajuda.texto.text() == AJUDA_LIMPEZA
    tela.ajuda.fechar.click()
    assert not tela.ajuda.isVisible()
    assert not tela.botao_ajuda.isChecked()


def test_log_aparece_na_tela_registro(qtbot):
    j, handler = janela(qtbot)
    log.addHandler(handler)
    try:
        log.warning("linha de teste")
    finally:
        log.removeHandler(handler)
    assert "linha de teste" in j.log.toPlainText()
