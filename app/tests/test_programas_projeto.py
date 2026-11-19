"""Programas por projeto e perfil (ADR-074, TA-ADR-042): regra, lista, etapa 6 e tela."""

from datetime import UTC, datetime

from test_programas import inst, winget

from itc_bench.servicos import cadastros as cad_mod
from itc_bench.servicos import etapas
from itc_bench.servicos import programas as pg
from itc_bench.servicos.cadastros import Cadastros, Unidade
from itc_bench.ui import programas as tela

UNIDADES = (
    Unidade(1, "ABC01", "Unidade Abc", "", "DF", "", "", projeto="ABC"),
    Unidade(2, "DEF01", "Unidade Def", "", "DF", "", "", projeto="DEF"),
    Unidade(3, "SEM01", "Sem projeto", "", "DF", "", ""),
)
GERAL = inst(1, "Geral")
DO_ABC = winget(2, "Ex.Abc", programa="Do ABC", projeto="ABC")
DO_DEF = winget(3, "Ex.Def", programa="Do DEF", projeto="DEF")
ALUNO = winget(4, "Ex.Aluno", programa="Só aluno", perfis=("aluno",))
ABC_PEDAGOGO = winget(5, "Ex.Ped", programa="ABC pedagogo", projeto="ABC", perfis=("pedagogo",))


def _cad(*linhas) -> Cadastros:
    linhas = linhas or (GERAL, DO_ABC, DO_DEF, ALUNO, ABC_PEDAGOGO)
    return Cadastros("v" * 64, datetime.now(UTC), "t", None, False, (), linhas, (), UNIDADES)


def _ids(linhas) -> set[int]:
    return {i.id for i in linhas}


# ---------------------------------------------------------------- regra


def test_programa_sem_projeto_vale_para_todas_as_maquinas():
    c = _cad()
    for unidade in ("ABC01", "DEF01", "SEM01", None):
        assert GERAL.id in _ids(c.instaladores_para(unidade))


def test_programa_do_projeto_so_nas_unidades_dele():
    c = _cad()
    assert _ids(c.instaladores_para("ABC01")) == {1, 2, 4, 5}
    assert _ids(c.instaladores_para("DEF01")) == {1, 3, 4}
    assert _ids(c.instaladores_para("SEM01")) == {1, 4}  # unidade sem projeto: só os gerais


def test_bancada_so_os_gerais():
    assert _ids(_cad().instaladores_para(None)) == {1, 4}


def test_perfil_filtra_e_vazio_vale_para_todos():
    c = _cad()
    assert _ids(c.instaladores_para("ABC01", "aluno")) == {1, 2, 4}
    assert _ids(c.instaladores_para("ABC01", "pedagogo")) == {1, 2, 5}
    assert _ids(c.instaladores_para("ABC01", "outro")) == {1, 2}


def test_cache_le_os_perfis_e_cache_antigo_sem_eles():
    registro = {
        "versao": "v",
        "sincronizado_em": "2026-11-19T10:00:00+00:00",
        "por": "t",
        "unidade": None,
        "dados": {
            "servidores": [],
            "instaladores": [
                {
                    "id": 1,
                    "programa": "A",
                    "versao": "",
                    "arquivo": "",
                    "sha256": "",
                    "link": "",
                    "observacao": "",
                    "tipo": "winget",
                    "projeto": "ABC",
                    "perfis": ["aluno"],
                },
                {
                    "id": 2,
                    "programa": "B",
                    "versao": "",
                    "arquivo": "",
                    "sha256": "",
                    "link": "",
                    "observacao": "",
                },
            ],
            "wifi": [],
            "unidades": [],
        },
    }
    a, b = cad_mod._de_dados(registro).instaladores
    assert (a.projeto, a.perfis) == ("ABC", ("aluno",))
    assert (b.projeto, b.perfis) == ("", ())


# ---------------------------------------------------------------- lista e etapa 6


def test_listar_todas_e_da_maquina():
    c = _cad()
    assert _ids(i.linha for i in pg.listar(c)) == {1, 2, 3, 4, 5}
    assert _ids(i.linha for i in pg.listar(c, "DEF01", "aluno")) == {1, 3, 4}


def test_mesmo_programa_em_projetos_diferentes_nao_e_duplicata():
    a = winget(10, "Ex.Mesmo", programa="Mesmo", projeto="ABC")
    b = winget(11, "Ex.Mesmo", programa="Mesmo", projeto="DEF")
    c = _cad(a, b)
    assert all(not i.bloqueio for i in pg.listar(c))  # Todos os projetos
    assert all(not i.bloqueio for i in pg.listar(c, "ABC01"))
    geral = winget(12, "Ex.Mesmo", programa="Mesmo")
    na_abc = pg.listar(_cad(a, geral), "ABC01")
    assert all(i.bloqueio for i in na_abc)  # os dois iriam para a mesma máquina


def test_etapa_6_instala_so_os_do_projeto_e_perfil():
    c = _cad()
    itens = etapas.itens_programas(c, "ABC01", "pedagogo")
    assert _ids(i.linha for i in itens) == {1, 2, 5}


def test_etapa_6_some_sem_programa_para_o_projeto_e_perfil():
    c = _cad(DO_DEF)
    assert "programas" in etapas.ocultas(c, "ABC01", "aluno")
    assert "programas" not in etapas.ocultas(c, "DEF01", "aluno")
    assert "programas" not in etapas.ocultas(None, "ABC01", "aluno")  # sem cadastro: bloqueada


# ---------------------------------------------------------------- tela


def _painel(qtbot, monkeypatch, unidade="ABC01"):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(
        pg, "situacao", lambda itens: ([pg.Linha(i, "nao_instalado") for i in itens], "")
    )
    c = _cad()
    estado = {"unidade": unidade}
    p = tela.PainelProgramas(True, lambda: c, lambda: estado["unidade"])
    qtbot.addWidget(p)
    p.carregar()
    return p, estado


def _programas(p) -> list[str]:
    return [p.tabela.item(r, 0).text() for r in range(p.tabela.rowCount())]


def test_tela_abre_nos_programas_desta_maquina_com_a_coluna_para(qtbot, monkeypatch):
    p, _ = _painel(qtbot, monkeypatch)
    assert p.escopo.currentText() == "Projeto desta máquina"
    assert sorted(_programas(p)) == sorted(["Geral", "Do ABC", "Só aluno", "ABC pedagogo"])
    para = {
        p.tabela.item(r, 0).text(): p.tabela.item(r, 5).text() for r in range(p.tabela.rowCount())
    }
    assert para["Geral"] == "todos os projetos · todos os perfis"
    assert para["ABC pedagogo"] == "ABC · pedagogo"
    assert "projeto ABC" in p.estado.text()


def test_todos_os_projetos_mostra_tudo(qtbot, monkeypatch):
    p, _ = _painel(qtbot, monkeypatch)
    p.escopo.setCurrentIndex(1)
    assert "Do DEF" in _programas(p) and len(_programas(p)) == 5


def test_bancada_avisa_e_mostra_so_os_gerais(qtbot, monkeypatch):
    p, _ = _painel(qtbot, monkeypatch, unidade=None)
    assert sorted(_programas(p)) == ["Geral", "Só aluno"]
    assert "bancada" in p.estado.text()


def test_ao_voltar_a_tela_reabre_no_projeto_e_rele_se_a_unidade_mudou(qtbot, monkeypatch):
    p, estado = _painel(qtbot, monkeypatch)
    p.escopo.setCurrentIndex(1)
    p.hide()
    estado["unidade"] = "DEF01"
    p.show()
    assert p.escopo.currentIndex() == 0
    assert "Do DEF" in _programas(p) and "Do ABC" not in _programas(p)
