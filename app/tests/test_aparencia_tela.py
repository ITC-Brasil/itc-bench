"""Telas Proteção do login e Aparência (ADR-022): só leitura sem admin, situação e confirmação."""

from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import Qt

from itc_bench.servicos import aparencia as ap
from itc_bench.servicos import energia, hive, protecao
from itc_bench.servicos import papel_de_parede as pp
from itc_bench.servicos.cadastros import Cadastros, Instalador
from itc_bench.ui import aparencia as tela
from itc_bench.ui import protecao as tela_protecao

SID = "S-1-5-21-1-2-3-1003"
ALUNO = hive.Alvo(SID, "Aluno-Teste", True)
ALVOS = [hive.PADRAO, ALUNO]


def _sem_tarefa(monkeypatch, modulo) -> None:
    monkeypatch.setattr(modulo.tarefa, "iniciar", lambda *a: None)


def marcar(p, *chaves):
    for i in range(p.lista_alvos.count()):
        item = p.lista_alvos.item(i)
        if item.data(Qt.ItemDataRole.UserRole) in chaves:
            item.setCheckState(Qt.CheckState.Checked)


# ---------------------------------------------------------------- Proteção


def situacao_protecao(**acl) -> protecao.Situacao:
    bins = {
        e: protecao.Binario(e, "original", acl.get(e.split(".")[0], "livre"), "limpo")
        for e in protecao.BINARIOS
    }
    return protecao.Situacao(bins, "padrao")


def test_protecao_sem_admin_so_leitura(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela_protecao)
    p = tela_protecao.PainelProtecao(False)
    qtbot.addWidget(p)
    p._recebeu(situacao_protecao())
    assert not p.b_proteger.isEnabled() and not p.b_depurador.isEnabled()


def test_protecao_mostra_nao_protegido(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela_protecao)
    p = tela_protecao.PainelProtecao(True)
    qtbot.addWidget(p)
    p._recebeu(situacao_protecao(utilman="protegido"))
    assert p.b_proteger.isEnabled()
    assert "Sethc (Shift 5x): não protegido" in p.alertas.text()
    assert "Utilman" not in p.alertas.text()
    assert p.arvore.topLevelItem(0).text(2) == "protegido"
    assert "Win+U" in p.confirmacao(True)


# ---------------------------------------------------------------- Mouse e teclado


def test_mouse_situacao_e_confirmacao(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela)
    p = tela.PainelMouse(True, lambda: None)
    qtbot.addWidget(p)
    sit = {(a.id, SID): ap.Situacao("padrao", a.padrao) for a in ap.CATALOGO}
    sit[("velocidade", SID)] = ap.Situacao("ajustado", "15")
    p._recebeu((ALVOS, sit))
    marcar(p, SID)
    assert "Aluno-Teste: 15" in p.itens["velocidade"].text(2)
    p.itens["velocidade"].setCheckState(0, Qt.CheckState.Checked)
    p.valores["velocidade"].setCurrentIndex(p.valores["velocidade"].findData("5"))
    texto = p.confirmacao("aplicar", [ALUNO])
    assert texto == "Velocidade do ponteiro — Aluno-Teste: 15 → 5"
    assert "→ 10" in str(p.confirmacao("desfazer", [ALUNO]))


def test_mouse_sem_admin(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela)
    p = tela.PainelMouse(False, lambda: None)
    qtbot.addWidget(p)
    p._recebeu((ALVOS, {}))
    assert not p.b_aplicar.isEnabled() and not p.ler_fechados.isEnabled()


# ---------------------------------------------------------------- Papel de parede


def test_papel_lista_cadastro_e_confirma(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela)
    linha = Instalador(
        9, "Papel ITC", "", "p.png", "a" * 64, "https://exemplo.invalid/p.png", "", tipo="papel"
    )
    outra = replace(linha, id=10, tipo="instalador", programa="Editor")
    cad = Cadastros("v" * 64, datetime.now(UTC), "t", None, False, (), (linha, outra), (), ())
    p = tela.PainelPapel(True, lambda: cad)
    qtbot.addWidget(p)
    p._recebeu((ALVOS, {SID: pp.Situacao("nao_aplicado")}))
    assert p.imagem.count() == 1 and p.imagem.currentText() == "Papel ITC"
    assert "Aluno-Teste — não aplicado" in p.lista_alvos.item(1).text()
    texto = p.confirmacao("aplicar", [ALUNO, hive.PADRAO])
    assert texto is not None and "Aluno-Teste: não aplicado → papel de parede do Grupo" in texto
    assert "Contas futuras" in texto


# ---------------------------------------------------------------- Energia


def test_energia_confirmacoes(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela)
    p = tela.PainelEnergia(True)
    qtbot.addWidget(p)
    valores = {(a, f): energia.Valor(600, 900) for a in energia.AJUSTES for f in energia.FONTES}
    p._recebeu(energia.Situacao("x", valores, True))
    p.itens[("tela", "ac")].setCheckState(0, Qt.CheckState.Checked)
    p.valores[("tela", "ac")].setCurrentIndex(0)
    assert p.confirmacao("aplicar") == "Desligar a tela — na tomada: 10 min → Nunca"
    assert "15 min (padrão do plano)" in p.confirmacao("desfazer")
    assert "ligada" in p.confirmacao_hibernacao(
        False
    ) and "Inicialização rápida" in p.confirmacao_hibernacao(False)


def test_energia_sem_admin(qtbot, monkeypatch):
    _sem_tarefa(monkeypatch, tela)
    p = tela.PainelEnergia(False)
    qtbot.addWidget(p)
    p._recebeu(energia.Situacao("x", {}, None))
    assert not p.b_aplicar.isEnabled() and not p.b_hib_off.isEnabled()
