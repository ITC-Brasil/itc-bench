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


# ---------------------------------------------------- marcar/desmarcar e desativar todas (ADR-033)


def marcadas(p):
    return {x.id for x in p._politicas_marcadas()}


def test_marcar_e_desmarcar_todas(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    todas = {x.id for x in p.catalogo}
    assert marcadas(p) == set() and p.b_marcar_todas.text() == "Marcar todas"
    p.b_marcar_todas.click()
    assert marcadas(p) == todas and p.b_marcar_todas.text() == "Desmarcar todas"
    p.b_marcar_todas.click()
    assert marcadas(p) == set() and p.b_marcar_todas.text() == "Marcar todas"


def test_marcar_todas_com_algumas_marcadas_marca_o_resto(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.itens["cmd"].setCheckState(0, Qt.CheckState.Checked)
    assert p.b_marcar_todas.text() == "Marcar todas"
    p.b_marcar_todas.click()
    assert marcadas(p) == {x.id for x in p.catalogo}


def test_marcar_todas_acompanha_marcacao_manual(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    for item in p.itens.values():
        item.setCheckState(0, Qt.CheckState.Checked)
    assert p.b_marcar_todas.text() == "Desmarcar todas"
    p.itens["cmd"].setCheckState(0, Qt.CheckState.Unchecked)
    assert p.b_marcar_todas.text() == "Marcar todas"


def test_marcacao_sobrevive_a_releitura(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.b_marcar_todas.click()
    p._recebeu((ALVOS, leitura(), False))
    assert marcadas(p) == {x.id for x in p.catalogo}
    assert p.b_marcar_todas.text() == "Desmarcar todas"


def test_marcar_todas_vale_sem_admin_e_desativar_nao(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    assert p.b_marcar_todas.isEnabled()
    assert not p.b_desativar_todas.isEnabled()


def test_desativar_todas_desfaz_o_catalogo_nos_alvos_marcados(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    marcar(p, SID)
    confirmacoes: list[tuple[str, str]] = []
    chamadas: list[tuple] = []
    monkeypatch.setattr(tela, "confirmar", lambda _p, t, x: confirmacoes.append((t, x)) or True)
    monkeypatch.setattr(
        politicas,
        "aplicar",
        lambda acao, ids, alvos_, **_: chamadas.append((acao, ids, alvos_)) or [],
    )
    executadas: list = []
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda f, *_: executadas.append(f()))
    assert marcadas(p) == set()  # nenhuma caixa marcada: o botão não depende delas
    p.b_desativar_todas.click()
    titulo, texto = confirmacoes[0]
    assert titulo == "Políticas — desfazer" and "Desativar TODAS" in texto
    assert "Bloquear Prompt de Comando — Aluno-Teste: não aplicada → não aplicada" in texto
    acao, ids, alvos_ = chamadas[0]
    assert acao == "desfazer"
    assert set(ids) == {x.id for x in p.catalogo} and "usb" not in ids
    assert alvos_ == [ALUNO]


def test_desativar_todas_sem_alvo_avisa(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    avisos: list[str] = []
    monkeypatch.setattr(p, "_aviso", lambda t, **_: avisos.append(t))
    monkeypatch.setattr(tela, "confirmar", lambda *_: (_ for _ in ()).throw(AssertionError))
    p.b_desativar_todas.click()
    assert avisos and "alvo" in avisos[0]


def test_desativar_todas_cancelado_nao_altera(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    marcar(p, SID)
    monkeypatch.setattr(tela, "confirmar", lambda *_: False)
    monkeypatch.setattr(politicas, "aplicar", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    p.b_desativar_todas.click()


def test_tela_usb_sem_marcar_nem_desativar_todas(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, usb=True)
    p.show()
    assert not p.b_marcar_todas.isVisible() and not p.b_desativar_todas.isVisible()


def test_confirmacao_avisa_quando_a_conta_que_roda_esta_marcada(qtbot, monkeypatch):
    """ADR-034: a conta que roda o Bench é aceita, com aviso na confirmação."""
    p = painel(qtbot, monkeypatch)
    eu = politicas.Alvo("S-1-5-21-1-2-3-1001", "Tecnico-Teste", True, admin=True)
    texto = p.confirmacao("aplicar", [politicas.POR_ID["cmd"]], [eu])
    assert "rodando o Bench (você)" in texto and "próximo logon" in texto
    sem_eu = p.confirmacao("aplicar", [politicas.POR_ID["cmd"]], [ALUNO])
    assert "rodando o Bench" not in sem_eu


def test_ajuda_diz_que_a_conta_que_roda_e_aceita():
    assert "A conta que está rodando o Bench" in tela.AJUDA and "é aceita" in tela.AJUDA
