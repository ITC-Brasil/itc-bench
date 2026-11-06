"""Telas Políticas e USB (ADR-021): só leitura sem admin, situação, confirmação, USB."""

from PySide6.QtCore import Qt

from itc_bench.servicos import politicas
from itc_bench.ui import politicas as tela

SID = "S-1-5-21-1-2-3-1003"
ALUNO = politicas.Alvo(SID, "Aluno-Teste", True)
ADMIN = politicas.Alvo("S-1-5-21-1-2-3-1009", "Outro-Admin", True, admin=True)
ALVOS = [politicas.MAQUINA, politicas.PADRAO, ALUNO, ADMIN]


def leitura(edicao="Professional"):
    sit = {}
    for p in politicas.CATALOGO:
        for a in ALVOS:
            if a.escopo in p.escopos:
                sit[(p.id, a.chave)] = "nao_lida" if a.tipo == "padrao" else "nao_aplicada"
    return politicas.Leitura(edicao, "S-1-5-21-1-2-3-1001", sit, {("cmd", SID): True})


def painel(qtbot, monkeypatch, admin=True, usb=False):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    p = tela.PainelPoliticas(admin, lambda: None, usb=usb)
    qtbot.addWidget(p)
    p._recebeu((ALVOS, leitura(), False))
    return p


def marcar(p, *chaves):
    for i in range(p.lista_alvos.count()):
        item = p.lista_alvos.item(i)
        if item.data(Qt.ItemDataRole.UserRole) in chaves:
            item.setCheckState(Qt.CheckState.Checked)


def test_sem_admin_so_leitura(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    assert not p.b_aplicar.isEnabled() and not p.b_desfazer.isEnabled()
    assert not p.ler_fechados.isEnabled()


def test_situacao_e_alteravel(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    marcar(p, SID)
    sistema = p.arvore.topLevelItem(0)
    assert sistema.text(0) == "Sistema"
    cmd = sistema.child(0)
    assert "Aluno-Teste: não aplicada (usuário pode alterar)" in cmd.text(2)
    assert p.b_aplicar.isEnabled()


def test_confirmacao_mostra_mudanca_e_avisos(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    store = politicas.POR_ID["store"]
    texto = p.confirmacao(
        "aplicar", [store, politicas.POR_ID["cmd"]], [ALUNO, ADMIN, politicas.PADRAO]
    )
    assert "Bloquear Prompt de Comando — Aluno-Teste: não aplicada → aplicada" in texto
    assert "Contas futuras: não lida → aplicada" in texto
    assert "administradora" in texto and "Contas futuras: só contas criadas depois" in texto
    assert politicas.AVISO_EDICAO in texto  # Store no Pro


def test_tela_usb_so_tem_usb(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, usb=True)
    assert p.b_aplicar.text() == "Desabilitar USB" and p.b_desfazer.text() == "Habilitar USB"
    assert [p_.id for p_ in p._politicas_marcadas()] == ["usb"]
    assert p.arvore.topLevelItemCount() == 1


def test_politicas_sem_usb_e_sobras(qtbot, monkeypatch):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    p = tela.PainelPoliticas(True, lambda: None)
    qtbot.addWidget(p)
    p.show()
    p._recebeu((ALVOS, leitura(), True))
    assert "usb" not in {x.id for x in p.catalogo}
    assert p.sobras.isVisible()


def test_ajuda_cita_edicao_e_cancelar():
    for ajuda in (tela.AJUDA, tela.AJUDA_USB):
        assert "Efeito não confirmado" in ajuda or "efeito não confirmado" in ajuda.lower()
        assert "Cancelar" in ajuda
