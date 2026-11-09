"""Tela Configurações (ADR-014): só leitura, segredos mascarados, unidade da máquina."""

from PySide6.QtWidgets import QApplication, QLabel, QTableWidget
from test_cadastros import CHAVE, OBS, SENHA_WIFI, corpo

from itc_bench.servicos import api, cadastros
from itc_bench.servicos.cadastros import Armazem
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.login import Entrada
from itc_bench.ui import tema
from itc_bench.ui.configuracoes import AJUDA, MASCARA
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela


def montar(qtbot, monkeypatch, armazem, admin=False):
    monkeypatch.setattr(api, "saude", lambda base: True)
    monkeypatch.setattr(api, "cadastros", lambda *a: corpo())
    cadastros.sincronizar("b", Sensivel("t"), armazem, "ana", None)
    tema.aplicar(QApplication.instance())
    j = Janela(
        HandlerTela(), "https://api.exemplo.invalid", None, "NB", armazem=armazem, admin=admin
    )
    qtbot.addWidget(j)
    return j


def textos_visiveis(j: Janela) -> str:
    """Todo texto da tela Configurações: rótulos, células, dicas e itens da lista."""
    tela = j.telas["config"]
    partes = [lbl.text() for lbl in tela.findChildren(QLabel)]
    for tabela in tela.findChildren(QTableWidget):
        for i in range(tabela.rowCount()):
            for k in range(tabela.columnCount()):
                item = tabela.item(i, k)
                if item is not None:
                    partes += [item.text(), item.toolTip()]
    combo = j.configuracoes.unidade
    partes += [combo.itemText(i) for i in range(combo.count())]
    return "\n".join(partes)


def test_mostra_cadastros_com_segredos_mascarados(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, Armazem(tmp_path / "c.dpapi"))
    p = j.configuracoes
    assert p.servidores.rowCount() == 2 and p.wifi.rowCount() == 2
    assert p.instaladores.rowCount() == 1 and p.unidades.rowCount() == 2
    assert p.servidores.item(0, 2).text() == "id.exemplo.invalid"  # Publico: visível
    assert p.servidores.item(1, 2).text() == MASCARA and p.servidores.item(1, 4).text() == MASCARA
    assert p.wifi.item(0, 0).text() == "Rede-Ficticia-A" and p.wifi.item(0, 3).text() == MASCARA
    assert p.instaladores.item(0, 3).text() == "ab" * 6
    assert p.instaladores.item(0, 3).toolTip() == f"<p>{'ab' * 32}</p>"
    texto = textos_visiveis(j)
    for marcador in (SENHA_WIFI, CHAVE, OBS):
        assert marcador not in texto
    assert "1 linha(s) com problema" in texto
    assert not p.botao_sincronizar.isEnabled()  # sem sessão online


def test_so_leitura_e_ajuda(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, Armazem(tmp_path / "c.dpapi"))
    for tabela in j.configuracoes.findChildren(QTableWidget):
        assert tabela.editTriggers() == tabela.EditTrigger.NoEditTriggers
    assert j.telas["config"].ajuda.texto.text() == AJUDA
    assert j.telas["config"].botao_ajuda.isVisible() or j.telas["config"].botao_ajuda is not None


def test_sem_cadastros_e_sem_admin_avisam(qtbot, monkeypatch):
    monkeypatch.setattr(api, "saude", lambda base: True)
    tema.aplicar(QApplication.instance())
    j = Janela(HandlerTela(), None, None, "NB", armazem=Armazem(None))
    qtbot.addWidget(j)
    texto = textos_visiveis(j)
    assert "Sem cadastros nesta máquina" in texto and "só em memória" in texto


def test_trocar_unidade_offline_filtra_e_grava_no_registro(qtbot, monkeypatch, tmp_path):
    gravadas = []
    monkeypatch.setattr(cadastros, "gravar_unidade", gravadas.append)
    armazem = Armazem(tmp_path / "c.dpapi")
    j = montar(qtbot, monkeypatch, armazem, admin=True)
    j._entrou(Entrada("ana.lima", "Ana Lima", None))  # offline
    j.escolher_unidade("UM-02")
    assert gravadas == ["UM-02"] and j.unidade == "UM-02"
    assert [r.id for r in armazem.carregar().redes] == [11]
    assert "Unidade UM-02" in j.rodape.text()
    assert j.configuracoes.unidade.currentData() == "UM-02"


def test_trocar_unidade_online_ressincroniza_filtrado(qtbot, monkeypatch, tmp_path):
    pedidos = []

    def falso(base, token, versao, unidade):
        pedidos.append((versao, unidade))
        return corpo(versao="u" * 64, unidade=unidade)

    armazem = Armazem(tmp_path / "c.dpapi")
    j = montar(qtbot, monkeypatch, armazem)
    monkeypatch.setattr(api, "cadastros", falso)
    sessao = api.SessaoApi(Sensivel("itcbs_x"), "ana.lima", "Ana Lima", "2099-01-01T00:00:00Z")
    j._entrou(Entrada("ana.lima", "Ana Lima", sessao))
    qtbot.waitUntil(lambda: len(pedidos) == 1)
    j.escolher_unidade("UM-01")
    qtbot.waitUntil(lambda: len(pedidos) == 2 and j.cadastros.unidade == "UM-01")
    assert pedidos[1] == (None, "UM-01")
    assert [r.id for r in j.cadastros.redes] == [10]
    assert j.configuracoes.botao_sincronizar.isEnabled()


def test_dica_do_sha256_nunca_e_rich_text(qtbot, monkeypatch, tmp_path):
    def com_html(*_a):
        c = corpo()
        c["instaladores"][0]["sha256"] = "<img src=x>" + "a" * 60
        return c

    armazem = Armazem(tmp_path / "c.dpapi")
    j = montar(qtbot, monkeypatch, armazem)
    monkeypatch.setattr(api, "cadastros", com_html)
    cadastros.sincronizar("b", Sensivel("t"), armazem, "ana", None)
    j.cadastros = armazem.carregar()
    j._atualizar_rodape()
    assert j.configuracoes.instaladores.item(0, 3).toolTip() == ""


def test_servidor_sem_acesso_aos_cadastros_avisa(qtbot, monkeypatch, tmp_path):
    """503 cadastros_indisponivel: a tela diz que a API está no ar sem o NocoDB, com a data."""
    armazem = Armazem(tmp_path / "c.dpapi")
    j = montar(qtbot, monkeypatch, armazem)

    def fora(*_a):
        raise api.CadastrosIndisponivel("cadastros_indisponivel")

    monkeypatch.setattr(api, "cadastros", fora)
    j._sincronizou(cadastros.sincronizar("b", Sensivel("t"), armazem, "ana", None))
    assert "Servidor sem acesso aos cadastros; usando a cópia de " in textos_visiveis(j)
    j._sincronizou(cadastros.Sincronizacao("igual", armazem.carregar()))
    assert "Servidor sem acesso" not in textos_visiveis(j)
