"""Tela Configurações (ADR-014): só leitura, segredos mascarados, unidade da máquina."""

import pytest
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


def test_unidades_sem_cidade_nem_tag(qtbot, monkeypatch, tmp_path):
    """ADR-067: a aba Unidades mostra só a UF; cache sem as chaves cidade/tag_glpi é aceito."""
    j = montar(qtbot, monkeypatch, Armazem(tmp_path / "c.dpapi"))
    p = j.configuracoes
    titulos = [p.unidades.horizontalHeaderItem(k).text() for k in range(p.unidades.columnCount())]
    assert titulos == ["Código", "Nome", "Projeto", "UF", "Perfil padrão"]
    registro = {
        "versao": "v",
        "sincronizado_em": "2026-11-18T10:00:00+00:00",
        "por": "t",
        "unidade": None,
        "dados": {
            "servidores": [],
            "instaladores": [],
            "wifi": [],
            "unidades": [
                {"id": 1, "codigo": "ABC01", "nome": "A", "uf": "DF", "perfil_padrao": ""}
            ],
        },
    }
    u = cadastros._de_dados(registro).unidades[0]
    assert (u.cidade, u.tag_glpi, u.uf) == ("", "", "DF")


def test_aba_projetos_e_projeto_da_unidade(qtbot, monkeypatch, tmp_path):
    """ADR-059: Projetos numa aba, com as unidades de cada; a unidade mostra a sigla."""

    def com_projetos():
        c = corpo()
        c["projetos"] = [{"id": 1, "sigla": "ABC", "nome": "Projeto Abc"}]
        c["unidades"][0]["projeto"] = "ABC"
        return c

    monkeypatch.setattr(api, "saude", lambda base: True)
    monkeypatch.setattr(api, "cadastros", lambda *a: com_projetos())
    armazem = Armazem(tmp_path / "c.dpapi")
    c = cadastros.sincronizar("b", Sensivel("t"), armazem, "ana", None)
    tema.aplicar(QApplication.instance())
    j = Janela(HandlerTela(), "https://api.exemplo.invalid", None, "NB", armazem=armazem)
    qtbot.addWidget(j)
    p = j.configuracoes
    codigo = p.unidades.item(0, 0).text()
    assert p.unidades.item(0, 2).text() == "ABC" and p.unidades.item(1, 2).text() == "—"
    assert [p.projetos.item(0, k).text() for k in range(3)] == ["ABC", "Projeto Abc", codigo]
    cad = armazem.carregar()
    assert cad is not None and cad.projeto_por_sigla("ABC").nome == "Projeto Abc"
    assert cad.projeto_por_sigla("") is None
    del c


def test_so_leitura_e_ajuda(qtbot, monkeypatch, tmp_path):
    j = montar(qtbot, monkeypatch, Armazem(tmp_path / "c.dpapi"))
    for tabela in j.configuracoes.findChildren(QTableWidget):
        assert tabela.editTriggers() == tabela.EditTrigger.NoEditTriggers
    # Configurações também traz a ajuda da faixa de atualização, que não tem tela própria.
    assert j.telas["config"].ajuda.texto.text().startswith(AJUDA)
    assert "Atualização do ITC Bench" in j.telas["config"].ajuda.texto.text()
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


# ---------------------------------------------------------------- unidade pelo nome (ADR-048)


@pytest.mark.parametrize(
    ("nome", "codigo"),
    [
        ("BSBIA01-EST94", "BSBIA01"),
        ("bsbia01-est94", "BSBIA01"),
        ("ABC07", "ABC07"),
        ("ABC07-", "ABC07"),
        ("ABC071-EST", None),  # depois do código vem dígito: não é código
        ("QUALIFICA-EST", "QUALIFICA"),  # formato de código; só vale se estiver no cadastro
        ("ITCBRASIL-EST01", "ITCBRASIL"),  # 9 letras (ADR-055 revisado)
        ("ABCDEFGHIJKLMNO", "ABCDEFGHIJKLMNO"),  # 15 letras: o nome inteiro do computador
        ("ABCDEFGHIJKLMNOP", None),  # 16 letras: não cabe num nome de computador
        ("MOBILITY-EST01", "MOBILITY"),  # unidade sem número (ADR-055)
        ("inesq-est03", "INESQ"),
        ("INESQ", "INESQ"),
        ("RESERVA-06", "RESERVA"),  # formato de código; só vale se estiver no cadastro
        ("A-EST", None),  # sigla sem número com menos de 2 letras
        ("INESQ1-EST", None),  # um dígito só não é número de UM
        ("ABCDEFG01-X", None),  # sigla com mais de 6 letras
        ("", None),
    ],
)
def test_codigo_do_nome(nome, codigo):
    assert cadastros.codigo_do_nome(nome) == codigo


def _corpo_com(codigo):
    c = corpo()
    c["unidades"].append(
        {
            "id": 3,
            "codigo": codigo,
            "nome": "Unidade Três",
            "cidade": "",
            "uf": "",
            "tag_glpi": "",
            "perfil_padrao": "",
        }
    )
    return c


def montar_com_nome(qtbot, monkeypatch, tmp_path, nome, codigo="BSBIA01"):
    monkeypatch.setattr(cadastros, "nome_do_computador", lambda: nome)
    monkeypatch.setattr(api, "saude", lambda base: True)
    monkeypatch.setattr(api, "cadastros", lambda *a: _corpo_com(codigo))
    armazem = Armazem(tmp_path / "c.dpapi")
    cadastros.sincronizar("b", Sensivel("t"), armazem, "ana", None)
    tema.aplicar(QApplication.instance())
    j = Janela(HandlerTela(), "https://api.exemplo.invalid", None, "NB", armazem=armazem)
    qtbot.addWidget(j)
    j._atualizar_rodape()
    return j


def test_sem_unidade_usa_a_do_nome(qtbot, monkeypatch, tmp_path):
    j = montar_com_nome(qtbot, monkeypatch, tmp_path, "BSBIA01-EST94")
    assert j.unidade == "BSBIA01"
    assert j.configuracoes.unidade.currentData() == "BSBIA01"
    assert "identificada pelo nome do computador (BSBIA01-EST94)" in j.configuracoes.aviso.text()


def test_nome_sem_codigo_ou_codigo_fora_do_cadastro_nao_escolhe(qtbot, monkeypatch, tmp_path):
    assert montar_com_nome(qtbot, monkeypatch, tmp_path, "QUALIFICA-EST").unidade is None
    j = montar_com_nome(qtbot, monkeypatch, tmp_path, "XYZ09-NB01")
    assert j.unidade is None
    assert montar_com_nome(qtbot, monkeypatch, tmp_path, "DESKTOP-K2FI5PV").unidade is None


@pytest.mark.parametrize(
    ("nome", "codigo"), [("MOBILITY-EST01", "MOBILITY"), ("INESQ-EST03", "INESQ")]
)
def test_unidade_sem_numero_pelo_nome(qtbot, monkeypatch, tmp_path, nome, codigo):
    j = montar_com_nome(qtbot, monkeypatch, tmp_path, nome, codigo)
    assert j.unidade == codigo
    assert f"identificada pelo nome do computador ({nome})" in j.configuracoes.aviso.text()


def test_escolha_manual_vale_mais_que_o_nome(qtbot, monkeypatch, tmp_path):
    j = montar_com_nome(qtbot, monkeypatch, tmp_path, "BSBIA01-EST94")
    j.escolher_unidade(None)  # técnico escolhe bancada
    j._atualizar_rodape()
    assert j.unidade is None
    j.escolher_unidade("UM-01")
    j._atualizar_rodape()
    assert j.unidade == "UM-01"
    assert "indica a unidade BSBIA01, mas esta máquina está em UM-01" in (
        j.configuracoes.aviso.text()
    )
