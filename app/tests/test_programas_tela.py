"""Telas Programas e Remover programas (ADR-020): filtros, só leitura, bloqueio, confirmação."""

from PySide6.QtCore import Qt
from test_programas import cadastros, inst, webapp, winget

from itc_bench.servicos import desinstalar as des
from itc_bench.servicos import programas as pg
from itc_bench.ui import programas as tela


def painel(qtbot, monkeypatch, admin=True):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    cad = cadastros(
        inst(1), winget(2), webapp(3, categoria="Jogos"), inst(4, "Dup"), inst(5, "Dup")
    )
    p = tela.PainelProgramas(admin, lambda: cad)
    qtbot.addWidget(p)
    itens = pg.listar(cad)
    sits = {1: "instalado", 2: "nao_instalado", 3: "nao_instalado"}
    p._recebeu(([pg.Linha(i, sits.get(i.id, "bloqueado"), motivo=i.bloqueio) for i in itens], ""))
    return p


def marcar(p, *linhas):
    for r in linhas:
        p.tabela.item(r, 0).setCheckState(Qt.CheckState.Checked)


def visiveis(p):
    return [
        p.tabela.item(r, 0).text()
        for r in range(p.tabela.rowCount())
        if not p.tabela.isRowHidden(r)
    ]


def test_abas_e_busca(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    assert len(visiveis(p)) == 5
    p.abas.setCurrentIndex(tela.ABAS.index("Jogos"))
    assert visiveis(p) == ["Jogo"]
    p.abas.setCurrentIndex(tela.ABAS.index("Instalados"))
    assert visiveis(p) == ["Editor"]
    p.abas.setCurrentIndex(0)
    p.busca.setText("pac")
    assert visiveis(p) == ["Pacote"]


def test_bloqueado_nao_marca_e_botao_conta(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    dup = [r for r in range(5) if p.linhas[r].item.programa == "Dup"]
    assert all(not (p.tabela.item(r, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable) for r in dup)
    assert not p.acao.isEnabled()
    marcar(p, 0, 1)
    assert p.acao.text() == "Instalar 2 selecionado(s)" and p.acao.isEnabled()


def test_sem_admin_so_le(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    marcar(p, 0)
    assert not p.acao.isEnabled() and not p.escolher.isEnabled()
    assert "só leitura" in p.estado.text()


def test_confirmacao_mostra_modo_e_origem(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    exe = pg.Linha(pg.Item(inst(9, "Setup", "setup.exe")), "nao_instalado")
    texto = p.confirmacao([p.linhas[2], p.linhas[1], exe])
    assert texto.index("Setup") < texto.index("Pacote") < texto.index("Jogo")  # ordem do lote
    assert "interativo (janela do fabricante)" in texto and "baixar" in texto
    assert "winget Exemplo.Pacote" in texto and "atalho web (quiosque)" in texto
    assert "https://" not in texto and "downloads" not in texto


def test_remover_trava_protegido_e_confirma_modo(qtbot, monkeypatch):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    p = tela.PainelRemover(True)
    qtbot.addWidget(p)
    exe = r"C:\Program Files\X\unins000.exe"
    entradas = [
        des.Entrada("Alfa", "programa", "interativo", (exe,)),
        des.Entrada("Driver Y", "programa", "protegido", motivo="Driver."),
        des.Entrada("Windows Terminal (Store)", "terminal", "silencioso"),
    ]
    p._recebeu(entradas)
    assert not (p.tabela.item(1, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable)
    assert "protegido" in p.tabela.item(1, 2).text() and p.tabela.item(1, 2).toolTip() == "Driver."
    marcar(p, 0, 2)
    assert p.acao.isEnabled()
    texto = p.confirmacao([entradas[0], entradas[2]])
    assert "interativo, unins000.exe (abre a janela do fabricante)" in texto
    assert "Program Files" not in texto
    assert "todos os usuários" in texto
