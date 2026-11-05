"""Tela Contas: botões seguem as regras, sem admin só leitura, exclusão pede o nome."""

from PySide6.QtWidgets import QDialogButtonBox
from test_contas import ALUNO, NATIVO, SUPORTE, TECNICO, lista

from itc_bench.servicos import contas
from itc_bench.ui.contas import ConfirmarExclusao, PainelContas


def painel(qtbot, monkeypatch, admin=True):
    monkeypatch.setattr(contas, "listar", lambda **_: lista(NATIVO, TECNICO, SUPORTE, ALUNO))
    p = PainelContas(admin, lambda: None)
    qtbot.addWidget(p)
    p.show()
    qtbot.waitUntil(lambda: p.lista is not None and not p.ocupado)
    return p


def selecionar(p, nome):
    for i in range(p.tabela.rowCount()):
        if p.tabela.item(i, 0).text() == nome:
            p.tabela.selectRow(i)
            return
    raise AssertionError(nome)


def test_botoes_seguem_as_regras(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    selecionar(p, "Administrador")
    assert not any(b.isEnabled() for b in (p.b_admin, p.b_padrao, p.b_senha, p.b_excluir))
    assert "nativo" in p.motivo.text()
    selecionar(p, "Tecnico-Teste")
    assert p.b_admin.isEnabled() and not p.b_padrao.isEnabled() and not p.b_senha.isEnabled()
    selecionar(p, "Aluno-Teste")
    assert all(b.isEnabled() for b in (p.b_admin, p.b_padrao, p.b_senha, p.b_sem, p.b_excluir))
    assert p.b_todos_padrao.isEnabled()


def test_sem_admin_so_leitura(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    selecionar(p, "Aluno-Teste")
    botoes = (p.b_admin, p.b_padrao, p.b_senha, p.b_sem, p.b_excluir, p.b_criar, p.b_suporte)
    assert not any(b.isEnabled() for b in botoes)
    assert p.tabela.rowCount() == 4


def test_validacao_ao_digitar(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.nome.setText("aluno-teste")
    assert "Já existe" in p.erro_nome.text() and not p.b_criar.isEnabled()
    p.nome.setText("Teste01")
    p.senha1.setText("a")
    assert "conferem" in p.erro_nome.text()
    p.senha2.setText("a")
    assert p.b_criar.isEnabled()


def test_exclusao_exige_nome_exato(qtbot):
    d = ConfirmarExclusao(None, ALUNO, None)  # type: ignore[arg-type]
    qtbot.addWidget(d)
    ok = d.botoes.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and not d.apagar.isEnabled()  # sem pasta
    d.digitado.setText("aluno-teste")
    assert not ok.isEnabled()
    d.digitado.setText("Aluno-Teste")
    assert ok.isEnabled()
