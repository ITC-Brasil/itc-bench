"""Telas Coleta e laudo e Histórico (ADR-015): coletor e API falsos."""

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from itc_bench.servicos import api, coleta
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.fila import Fila
from itc_bench.ui import diagnostico as tela
from itc_bench.ui import tema
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela

SESSAO = ("https://api.exemplo.invalid", Sensivel("itcbs_marcador"), "tecnico.um")
LAUDO = {
    "diagnostico_id": 3,
    "relatorio_md": "## Resumo\n<img src=x>",
    "chamado_titulo": "<b>T</b>",
    "chamado_descricao": "D",
    "maior_confianca": "ALTA",
    "modelo": "m",
}


def coletar_falso(**kw):
    inicio = datetime(2026, 11, 4, 10).astimezone()
    c = coleta.Coleta("TESTE-NB-01", inicio, True, {})
    c.nomes_pessoais = ["marcador-pessoa"]
    for nome in coleta.ROTULOS:
        if kw.get("cancelar") and kw["cancelar"].is_set() and nome == "disco":
            break
        dados = {
            "processos": {"memoria": {"percentualEmUso": 50}},
            "rede": {"resumo": {"internetOk": True, "dnsOk": True}},
            "eventlog": {"totalGrupos": 2, "gruposCriticos": 1},
            "disco": {"volumes": [{"percentualLivre": 8.5}]},
            "bateria": {"presente": False},
        }[nome]
        m = coleta.Modulo(nome, "ok", None, inicio, 1.0, dados)
        c.modulos[nome] = m
        kw["ao_progresso"](nome, m)
    c.fim = inicio + timedelta(seconds=30)
    c.encerrada_normalmente = True
    return c


@pytest.fixture
def respostas(monkeypatch):
    fila_de_respostas: list = []
    enviados: list = []

    def relatorio(base, token, corpo):
        enviados.append(corpo)
        r = fila_de_respostas.pop(0) if fila_de_respostas else LAUDO
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(api, "relatorio", relatorio)
    return fila_de_respostas, enviados


def painel(qtbot, sessao=SESSAO, fila=None):
    tema.aplicar(QApplication.instance())
    p = tela.PainelColeta(lambda: sessao, fila or Fila(None), True, lambda: "UM-01", coletar_falso)
    qtbot.addWidget(p)
    return p


def test_coleta_online_mostra_areas_e_laudo_como_texto(qtbot, respostas):
    _, enviados = respostas
    p = painel(qtbot)
    p.nova_coleta()
    qtbot.waitUntil(lambda: p.caixa_laudo.isVisibleTo(p), timeout=5000)
    assert p.areas.item(3, 3).text() == "menor espaço livre 8.5%"
    assert p.titulo.text() == "<b>T</b>"  # texto puro
    assert "<img src=x>" in p.visor.toPlainText()
    assert (
        enviados[0]["unidade"] == "UM-01" and enviados[0]["sessao"]["coletadoPor"] == "tecnico.um"
    )
    assert "marcador-pessoa" not in str(enviados[0])


def test_offline_vai_para_a_fila(qtbot, respostas):
    f = Fila(None)
    p = painel(qtbot, sessao=None, fila=f)
    p.nova_coleta()
    qtbot.waitUntil(lambda: len(f.itens()) == 1, timeout=5000)
    assert "fila" in p.mensagem.text() and "aguardando envio" in p.estado.text()


@pytest.mark.parametrize(
    ("erro", "na_fila", "botao"),
    [
        (api.IaFalhou("ia_timeout"), 0, "Tentar laudo de novo"),
        (api.Recusado(429, "limite_excedido", 120), 1, "Tentar laudo de novo"),
        (api.Recusado(409, "em_processamento"), 1, "Tentar laudo de novo"),
        (api.SemConexao("x"), 1, "Tentar laudo de novo"),
        (api.Recusado(422, "requisicao_invalida"), 0, None),
    ],
)
def test_falhas_do_envio(qtbot, respostas, erro, na_fila, botao):
    respostas[0].append(erro)
    f = Fila(None)
    p = painel(qtbot, fila=f)
    p.nova_coleta()
    qtbot.waitUntil(lambda: p.botao_coletar.isEnabled(), timeout=5000)
    assert len(f.itens()) == na_fila
    assert p.botao_enviar.isVisibleTo(p) == (botao is not None)
    assert p.mensagem.text()


def test_ia_fora_e_tentar_de_novo_usa_o_mesmo_envio(qtbot, respostas):
    fila_r, enviados = respostas
    fila_r.append(api.IaFalhou("ia_timeout"))
    p = painel(qtbot)
    p.nova_coleta()
    qtbot.waitUntil(lambda: p.botao_enviar.isVisibleTo(p), timeout=5000)
    p.botao_enviar.click()
    qtbot.waitUntil(lambda: p.caixa_laudo.isVisibleTo(p), timeout=5000)
    assert enviados[0]["envio_id"] == enviados[1]["envio_id"]


def test_401_preserva_a_coleta_e_pede_login(qtbot, respostas):
    respostas[0].append(api.Recusado(401, "nao_autorizado"))
    f = Fila(None)
    p = painel(qtbot, fila=f)
    with qtbot.waitSignal(p.sessao_expirada, timeout=5000):
        p.nova_coleta()
    assert len(f.itens()) == 1 and p.corpo is not None


def test_cancelar_coleta_guarda_o_que_ficou_pronto(qtbot, respostas):
    def lenta(**kw):
        kw["cancelar"].wait(5)
        return coletar_falso(**kw)

    p = painel(qtbot)
    p._coletar = lenta
    p.nova_coleta()
    p.cancelar()
    qtbot.waitUntil(lambda: p.areas.item(3, 1).text() == "cancelado", timeout=5000)
    assert p.areas.item(2, 1).text() == "ok"


def test_janela_401_volta_a_entrar_com_coleta_preservada(qtbot, respostas, monkeypatch):
    respostas[0].append(api.Recusado(401, "nao_autorizado"))
    tema.aplicar(QApplication.instance())
    f = Fila(None)
    j = Janela(HandlerTela(), None, None, "NB", fila=f)
    qtbot.addWidget(j)
    monkeypatch.setattr(j, "sessao_online", lambda: SESSAO)
    j.coleta.obter_sessao = lambda: SESSAO
    j.coleta._coletar = coletar_falso
    j.raiz.setCurrentWidget(j.conteudo)
    j.coleta.nova_coleta()
    qtbot.waitUntil(lambda: j.raiz.currentWidget() is j.entrar, timeout=5000)
    assert len(f.itens()) == 1


def test_ajuda_das_duas_telas(qtbot):
    tema.aplicar(QApplication.instance())
    j = Janela(HandlerTela())
    qtbot.addWidget(j)
    assert j.telas["diag"].ajuda.texto.text() == tela.AJUDA_COLETA
    assert j.telas["hist"].ajuda.texto.text() == tela.AJUDA_HISTORICO
    assert "Revise antes de abrir chamado" in tela.AJUDA_COLETA


def test_historico_com_rede_mostra_laudo_e_pendentes(qtbot, monkeypatch):
    f = Fila(None)
    f.guardar(
        {"envio_id": "e1", "unidade": None, "sessao": {"hostname": "TESTE-NB-01"}}, "tecnico.dois"
    )
    vistos = []

    def historico(base, token, nome):
        vistos.append(nome)
        return {
            "diagnosticos": [
                {
                    "recebido_em": "2026-11-03 10:00:00",
                    "bench_usuario": "tecnico.um",
                    "unidade": "UM-01",
                    "falha": None,
                    "relatorio": {
                        "maior_confianca": "ALTA",
                        "chamado_titulo": "<i>T</i>",
                        "relatorio_md": "# Laudo\n[x](javascript:alert(1))",
                    },
                }
            ]
        }

    monkeypatch.setattr(api, "historico", historico)
    h = tela.PainelHistorico(lambda: SESSAO, f)
    qtbot.addWidget(h)
    h.atualizar()
    qtbot.waitUntil(lambda: h.tabela.rowCount() == 2, timeout=5000)
    assert h.tabela.item(0, 4).text() == "não enviada"
    assert h.tabela.item(1, 4).text() == "<i>T</i>"
    assert vistos == [coleta.hostname()]
    h.tabela.selectRow(1)
    assert "[x](javascript:alert(1))" in h.visor.toPlainText()


def test_historico_sem_rede_so_fila(qtbot):
    f = Fila(None)
    f.guardar({"envio_id": "e1", "sessao": {"hostname": "TESTE-NB-01"}}, "t")
    h = tela.PainelHistorico(lambda: None, f)
    qtbot.addWidget(h)
    h.atualizar()
    assert h.tabela.rowCount() == 1 and "indisponível" in h.estado.text()
    assert not h.botao_pendentes.isEnabled()
