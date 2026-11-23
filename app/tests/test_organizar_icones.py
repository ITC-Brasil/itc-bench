"""Organizar os ícones da Área de Trabalho na limpeza de contas (ADR-083)."""

import threading

from itc_bench.servicos import etapas, executor, limpeza
from itc_bench.servicos.contas import Conta, Lista

A, B = "S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1002"


def _rodar(saida, chamadas=None):
    def rodar(script, **k):
        if chamadas is not None:
            chamadas.append((script, k))
        return executor.Resultado(0, saida, "", 0.1, False)

    return rodar


def test_organizar_icones_manda_os_sids_e_le_cada_resposta():
    chamadas = []
    r = limpeza.organizar_icones(
        [A, B, A, "invalido"], rodar=_rodar(f"OK|{A}\nERRO|{B}|conta_em_uso\n", chamadas)
    )
    assert r == {A: "", B: "não deu para abrir o registro da conta"}
    script, k = chamadas[0]
    assert k["sids"] == f"{A},{B}"  # sem repetido nem SID estranho
    assert "FFlags" in script and "function Hive-Usuario" in script


def test_organizar_icones_sem_resposta_ou_falha_do_powershell():
    assert limpeza.organizar_icones([A], rodar=_rodar("")) == {A: "o Bench não recebeu resposta"}

    def falha(*_a, **_k):
        return executor.Resultado(None, "", "", 300, True)

    assert limpeza.organizar_icones([A], rodar=falha) == {A: "tempo esgotado"}
    assert limpeza.organizar_icones([]) == {}


def test_trecho_de_verdade_recusa_conta_que_nao_existe():
    assert limpeza.organizar_icones(["S-1-5-21-0-0-0-9999"]) == {
        "S-1-5-21-0-0-0-9999": "a conta não existe mais"
    }


def _ctx(monkeypatch, organizar):
    conta = Conta(A, "Aluno01", True, False, "Local", False, None, "C:/x", False)
    monkeypatch.setattr(etapas.contas, "listar", lambda **_k: Lista((conta,), (), "PC"))
    monkeypatch.setattr(limpeza, "limpar_contas", lambda *a, **k: [])
    chamadas = []
    monkeypatch.setattr(
        limpeza, "organizar_icones", lambda sids: chamadas.append(list(sids)) or {A: ""}
    )
    ctx = etapas.Contexto(admin=True, cadastros=None, alvos=(A,), organizar_icones=organizar)
    return etapas.LimpezaUsuarios(ctx), chamadas


def test_manutencao_organiza_os_icones_das_contas_limpas(monkeypatch):
    e, chamadas = _ctx(monkeypatch, True)
    assert e.aplicar(threading.Event()).estado == "ok" and chamadas == [[A]]
    assert "organizar os ícones" in e.mudancas()


def test_manutencao_desmarcado_nao_organiza(monkeypatch):
    e, chamadas = _ctx(monkeypatch, False)
    assert e.aplicar(threading.Event()).estado == "ok" and chamadas == []
    assert "ícones" not in e.mudancas()


def test_tela_limpeza_tem_a_caixa_marcada_e_avisa_na_confirmacao(qtbot):
    from itc_bench.ui import limpeza as ui_limpeza

    p = ui_limpeza.PainelLimpezaContas(True, lambda: None)
    qtbot.addWidget(p)
    assert p.organizar.isChecked()
    p.por_sid = {A: Conta(A, "Aluno01", True, False, "Local", False, None, "C:/x", False)}
    assert "organiza os ícones" in p.confirmacao([A])[0]
    p.organizar.setChecked(False)
    assert "organiza os ícones" not in p.confirmacao([A])[0]
    p.icones = {A: "", "S-x": "o Windows recusou"}
    assert "Ícones não organizados em S-x: o Windows recusou" in p._texto_icones()
