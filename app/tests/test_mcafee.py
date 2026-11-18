"""Remoção assistida do McAfee (ADR-068): detecção, linha do MCPR, execução e etapa 6."""

import threading
from pathlib import Path

import pytest
from test_programas import cadastros, inst, res, webapp

from itc_bench.servicos import desinstalar, etapas, instaladores, mcafee
from itc_bench.servicos import programas as pg
from itc_bench.ui import programas as tela


def lista(*nomes):
    return lambda: [pg.Instalado(f"K{n}", nome, "1", False) for n, nome in enumerate(nomes)]


def mcpr(id_=7, **kw):
    return inst(id_, "MCPR", "MCPR.exe", **kw)


def test_encontrados_por_nome_sem_repetir():
    nomes = mcafee.encontrados(
        lista("McAfee LiveSafe", "Editor", "mcafee WebAdvisor", "McAfee LiveSafe")
    )
    assert nomes == ["McAfee LiveSafe", "mcafee WebAdvisor"]
    assert mcafee.encontrados(lista("Editor")) == []


def test_linha_mcpr_diz_o_que_falta():
    assert "sincronize" in mcafee.linha_mcpr(None)
    assert "Cadastre o MCPR" in mcafee.linha_mcpr(cadastros(inst(1)))
    # atalho web chamado MCPR não conta (ADR-066)
    assert "Cadastre o MCPR" in mcafee.linha_mcpr(cadastros(webapp(4, programa="MCPR")))
    assert "mais de uma" in mcafee.linha_mcpr(cadastros(mcpr(7), mcpr(8)))
    assert ".exe" in mcafee.linha_mcpr(cadastros(inst(7, "MCPR", "MCPR.msi")))
    assert mcafee.linha_mcpr(cadastros(mcpr())) == mcpr()


def _remover(executar, restantes=(), conferir=True, **kw):
    return mcafee.remover(
        cadastros(mcpr()),
        executar=executar,
        listar=lista(*restantes),
        obter=lambda *_a, **_k: Path("C:/protegido/x.exe"),
        conferir=lambda _p: conferir,
        **kw,
    )


def test_remover_abre_o_mcpr_sem_argumentos_e_confere_depois():
    chamadas = []

    def executar(args, **kw):
        chamadas.append((args, kw))
        return res(0)

    r = _remover(executar)
    assert r.ok and "Reinicie" in r.mensagem
    ((args, kw),) = chamadas
    assert args == [str(Path("C:/protegido/x.exe"))]  # sem argumento: o técnico conduz
    assert kw["encerrar_no_timeout"] is False and kw["timeout"] == mcafee.TIMEOUT


def test_remover_diz_o_que_sobrou_e_o_tempo_esgotado():
    r = _remover(lambda *_a, **_k: res(0), restantes=("McAfee LiveSafe",))
    assert not r.ok and r.restantes == ["McAfee LiveSafe"] and "de novo" in r.mensagem
    r = _remover(lambda *_a, **_k: res(esgotado=True), restantes=("McAfee LiveSafe",))
    assert "1 hora" in r.mensagem


def test_remover_recusa_sem_linha_ou_hash_diferente():
    nunca = lambda *_a, **_k: pytest.fail("não podia abrir o MCPR")  # noqa: E731
    with pytest.raises(instaladores.ErroInstalador, match="Cadastre o MCPR"):
        mcafee.remover(cadastros(inst(1)), executar=nunca)
    with pytest.raises(instaladores.ErroInstalador, match="não confere"):
        _remover(nunca, conferir=False)


def _etapa6(monkeypatch, *, appx=(), mcafee_nomes=()):
    monkeypatch.setattr(desinstalar, "appx_presentes", lambda **_k: list(appx))
    monkeypatch.setattr(desinstalar, "ise_instalado", lambda **_k: False)
    monkeypatch.setattr(desinstalar, "office_presentes", lambda **_k: [])
    monkeypatch.setattr(desinstalar, "remover_appx", lambda *_a, **_k: [])
    monkeypatch.setattr(desinstalar, "remover_office", lambda *_a, **_k: [])
    monkeypatch.setattr(mcafee, "encontrados", lambda: list(mcafee_nomes))
    return etapas.Preinstalados(etapas.Contexto(admin=True, cadastros=None))


def test_etapa6_avisa_mcafee_sem_bloquear(monkeypatch):
    e = _etapa6(monkeypatch, mcafee_nomes=("McAfee LiveSafe",))
    assert e.ler().situacao == "pendente" and "Remover programas" in e.ler().detalhe
    r = e.aplicar(threading.Event())
    assert r.estado == "parcial" and "MCPR" in r.detalhe
    e = _etapa6(monkeypatch)
    assert e.ler().situacao == "feito" and e.aplicar(threading.Event()).estado == "ok"


def test_tela_remover_mostra_mcafee_e_o_que_falta(qtbot, monkeypatch):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    cad = {"atual": cadastros(inst(1))}
    p = tela.PainelRemover(True, lambda: cad["atual"])
    qtbot.addWidget(p)
    exe = r"C:\Program Files\X\unins000.exe"
    p._recebeu([desinstalar.Entrada("Alfa", "programa", "silencioso", (exe,))])
    assert p.mcafee.isHidden() and p.b_mcafee.isHidden()
    p._recebeu([desinstalar.Entrada("McAfee LiveSafe", "programa", "interativo", (exe,))])
    assert not p.b_mcafee.isHidden()
    assert "McAfee encontrado: McAfee LiveSafe." in p.mcafee.text()
    assert "Cadastre o MCPR" in p.mcafee.text() and not p.b_mcafee.isEnabled()
    cad["atual"] = cadastros(mcpr())
    p._recebeu([desinstalar.Entrada("McAfee LiveSafe", "programa", "interativo", (exe,))])
    assert p.mcafee.text() == "McAfee encontrado: McAfee LiveSafe." and p.b_mcafee.isEnabled()
    assert "McAfee" in tela.AJUDA_REMOVER and "código de validação" in tela.AJUDA_REMOVER
