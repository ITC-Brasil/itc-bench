"""Tela Contas: botões seguem as regras, sem admin só leitura, exclusão pede o nome."""

from PySide6.QtCore import Qt
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


def filtrar(p, chave):
    p.filtro.setCurrentIndex(p.filtro.findData(chave))


def test_botoes_seguem_as_regras(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    filtrar(p, "nao_modificaveis")
    selecionar(p, "Administrador")
    assert not any(b.isEnabled() for b in (p.b_admin, p.b_padrao, p.b_senha, p.b_excluir))
    assert "nativo" in p.motivo.text()
    filtrar(p, "modificaveis")
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
    assert p.tabela.rowCount() == 2  # modificáveis: Tecnico-Teste e Aluno-Teste
    filtrar(p, "nao_modificaveis")
    assert p.tabela.rowCount() == 2  # Administrador nativo e Suporte


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


def test_filtro_modificaveis_e_nao_modificaveis(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    nomes = lambda: {p.tabela.item(i, 0).text() for i in range(p.tabela.rowCount())}  # noqa: E731
    assert p.filtro.currentData() == "modificaveis"
    assert nomes() == {"Tecnico-Teste", "Aluno-Teste"}
    assert "2 de 4" in p.estado.text()
    filtrar(p, "nao_modificaveis")
    assert nomes() == {"Administrador", "Suporte"}


def test_encerrar_sessoes_marca_e_confirma(qtbot, monkeypatch):
    from itc_bench.ui import contas as tela

    p = painel(qtbot, monkeypatch)
    assert p.b_encerrar.isEnabled()  # Tecnico-Teste está logada
    escolhidos: list[str] = []

    class Falsa:
        def __init__(self, _pai, abertas):
            self.abertas = abertas

        def exec(self):
            return tela.QDialog.DialogCode.Accepted

        def marcadas(self):
            return [c.sid for c in self.abertas]

    monkeypatch.setattr(tela, "EscolherSessoes", Falsa)
    monkeypatch.setattr(tela, "confirmar", lambda _p, _t, texto: escolhidos.append(texto) or True)
    pedidos: list[str] = []
    monkeypatch.setattr(
        contas,
        "encerrar_sessao",
        lambda sid, **_: pedidos.append(sid) or contas.Feito(True, "ok"),
    )
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda f, ok, _f: None)
    executadas: list = []
    monkeypatch.setattr(p, "_rodar", lambda f: executadas.append(f()))
    p.b_encerrar.click()
    assert "Tecnico-Teste" in escolhidos[0] and "sem salvar" in escolhidos[0]
    assert pedidos == [TECNICO.sid] and executadas[0].ok


def test_escolher_sessoes_libera_so_com_marcada(qtbot):
    from itc_bench.ui.contas import EscolherSessoes

    d = EscolherSessoes(None, [ALUNO, TECNICO])  # type: ignore[arg-type]
    qtbot.addWidget(d)
    ok = d.botoes.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and d.marcadas() == []
    d.lista.item(1).setCheckState(Qt.CheckState.Checked)
    assert ok.isEnabled() and d.marcadas() == [TECNICO.sid]
    assert "(em uso)" in d.lista.item(1).text()
