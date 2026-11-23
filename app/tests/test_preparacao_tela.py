"""Telas Configuração e Manutenção (ADR-071): Rodar com as marcações atuais, Rodar sem ler,
contas locais com o motivo das bloqueadas, marcar e desmarcar todas, Atualizar e Encerrar
sessões. Nada toca o Windows: etapas, contas e sessões são falsas."""

import perfis_teste
import pytest
from PySide6.QtCore import Qt

from itc_bench.servicos import contas, etapas
from itc_bench.servicos import preparacao as prep
from itc_bench.servicos.cadastros import Cadastros, Unidade
from itc_bench.ui import contas as ui_contas
from itc_bench.ui import preparacao as ui_prep
from itc_bench.ui import tarefa

BASE = "S-1-5-21-1-2-3-"
PERFIL = perfis_teste.POR_ID["aluno"]  # 1 a 12; sem rede e sem papel, 3 e 4 somem
# O conftest troca _carregar_alunos por um falso nas telas; aqui a leitura (falsa) é o teste.
CARREGAR = ui_prep.PainelPreparacao._carregar_alunos


class Falsa:
    """Etapa que lê `pendente` até aplicar; depois, `feito`."""

    def __init__(self, id_: str) -> None:
        self.id = id_
        self.aplicou = 0

    def ler(self) -> prep.Leitura:
        return prep.Leitura("feito" if self.aplicou else "pendente", "falta")

    def aplicar(self, cancelar) -> prep.Resultado:
        self.aplicou += 1
        return prep.Resultado("ok")


def _c(rid: int, nome: str, **extra) -> contas.Conta:
    valores = dict(
        ativo=True,
        admin=False,
        fonte="Local",
        logada=False,
        ultima=None,
        perfil=f"C:\\Users\\{nome}",
        carregado=False,
    )
    valores.update(extra)
    return contas.Conta(sid=f"{BASE}{rid}", nome=nome, **valores)  # type: ignore[arg-type]


LISTA = contas.Lista(
    (
        _c(500, "Administrador"),
        _c(1001, "Suporte", admin=True),
        _c(1002, "Aluno01"),
        _c(1003, "Aluno02", logada=True, carregado=True),
        _c(1004, "Tecnico", admin=True, logada=True, bench=True),
        _c(1005, "Antiga", ativo=False),
        _c(1006, "Nova", perfil=None),
        _c(1007, "Aluno03"),
        _c(1008, "Online", fonte="MicrosoftAccount"),
        _c(1011, "Gestão", admin=True),
    ),
    (),
    "PC",
)


def _cad() -> Cadastros:
    from datetime import UTC, datetime

    return Cadastros(
        "v" * 64,
        datetime(2026, 11, 19, tzinfo=UTC),
        "t",
        None,
        False,
        (),
        (),
        (),
        (Unidade(1, "UM-01", "Unidade", "", "DF", "", "administrativo", ""),),
        perfis=perfis_teste.PERFIS,
    )


@pytest.fixture
def painel(qtbot, monkeypatch):
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(ui_prep, "confirmar", lambda *a, **k: True)
    monkeypatch.setattr(contas, "listar", lambda **k: LISTA)
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_ver_guardado", lambda self: None)
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_carregar_alunos", CARREGAR)
    cad = _cad()
    p = ui_prep.PainelPreparacao(True, lambda: cad, lambda: "UM-01")
    qtbot.addWidget(p)
    p.perfil.setCurrentIndex(p.perfil.findData("aluno"))
    p._carregar_alunos()
    p.etapas = [Falsa(e) for e in PERFIL.etapas]
    return p


def _item(p, eid):
    for i in range(p.lista.topLevelItemCount()):
        item = p.lista.topLevelItem(i)
        if item.data(0, Qt.ItemDataRole.UserRole) == eid:
            return item
    raise AssertionError(eid)


def _aplicadas(p) -> set[str]:
    return {e.id for e in p.etapas if e.aplicou}


def _visiveis(p) -> list[str]:
    return [
        str(p.lista.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole))
        for i in range(p.lista.topLevelItemCount())
    ]


# ---------------------------------------------------------------- 1. bug do Rodar


def test_desmarcada_depois_de_ler_nao_roda(painel):
    """Bug: o Rodar usava as marcações da leitura; a etapa desmarcada depois rodava."""
    p = painel
    p.ler()
    visiveis = _visiveis(p)
    antes = p.b_rodar.text()
    _item(p, visiveis[0]).setCheckState(0, Qt.CheckState.Unchecked)
    assert p.b_rodar.text() != antes
    p._rodar()
    assert visiveis[0] not in _aplicadas(p)
    assert _aplicadas(p) == set(visiveis[1:])


def test_marcada_depois_de_ler_entra_no_contador_e_roda(painel):
    p = painel
    alvo = _visiveis(p)[-1]
    _item(p, alvo).setCheckState(0, Qt.CheckState.Unchecked)
    p.ler()
    n = len(_visiveis(p)) - 1
    assert p.b_rodar.text() == f"Rodar {n} etapa(s)"
    _item(p, alvo).setCheckState(0, Qt.CheckState.Checked)
    assert p.b_rodar.text() == f"Rodar {n + 1} etapa(s)"
    p._rodar()
    assert alvo in _aplicadas(p)


def test_confirmacao_lista_so_as_marcadas_agora(painel, monkeypatch):
    p = painel
    p.ler()
    fora = _visiveis(p)[0]
    _item(p, fora).setCheckState(0, Qt.CheckState.Unchecked)
    textos = []
    monkeypatch.setattr(ui_prep, "confirmar", lambda _p, _t, texto: textos.append(texto) or False)
    p._rodar()
    rotulo = p.fluxo.rotulo(fora)
    assert textos and rotulo not in textos[0]
    assert not _aplicadas(p)  # cancelado na confirmação


# ---------------------------------------------------------------- 2. Rodar sem ler


def test_rodar_sem_ler_fica_disponivel_e_roda_as_marcadas(painel):
    p = painel
    assert p.andamento is None
    n = len(_visiveis(p))
    assert p.b_rodar.isEnabled() and p.b_rodar.text() == f"Rodar {n} etapa(s)"
    p._rodar()
    assert _aplicadas(p) == set(_visiveis(p))


def test_confirmacao_sem_leitura_lista_etapas_e_contas(painel, monkeypatch):
    p = painel
    textos = []
    monkeypatch.setattr(ui_prep, "confirmar", lambda _p, _t, texto: textos.append(texto) or False)
    p._rodar()
    assert p.fluxo.rotulo(_visiveis(p)[0]) in textos[0]
    assert "Contas marcadas: Aluno01, Aluno03" in textos[0]


def test_sem_admin_rodar_continua_desativado(qtbot, monkeypatch):
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_carregar_alunos", lambda self, m=None: None)
    cad = _cad()
    p = ui_prep.PainelPreparacao(False, lambda: cad, lambda: "UM-01")
    qtbot.addWidget(p)
    assert not p.b_rodar.isEnabled()


# ---------------------------------------------------------------- 3. contas locais


def test_contas_locais_com_motivo_e_mesmas_regras():
    prot = frozenset({"suporte"})
    motivos = {c.nome: m for c, m in etapas.contas_locais(LISTA, prot)}
    assert "Online" not in motivos  # só contas locais
    # ADR-072: Suporte, Gestão e Administrador nativo nunca aparecem
    assert motivos == {
        "Aluno01": "",
        "Aluno02": "conta logada",
        "Tecnico": "conta do Bench",
        "Antiga": "desativada",
        "Nova": "sem perfil",
        "Aluno03": "",
    }
    livres = [c.nome for c, m in etapas.contas_locais(LISTA, prot) if not m]
    assert livres == [c.nome for c in etapas.contas_de_aluno(LISTA, prot)]


def test_suporte_gestao_e_nativo_nunca_aparecem():
    """ADR-072: nem com outro nome cadastrado para a Suporte, nem Gestao sem acento."""
    lista = contas.Lista(
        (
            _c(500, "Admin"),
            _c(1020, "SuporteITC", admin=True),
            _c(1021, "Gestao", admin=True),
            _c(1022, "Aluno09"),
        ),
        (),
        "PC",
    )
    nomes = [c.nome for c, _ in etapas.contas_locais(lista, frozenset({"suporte", "suporteitc"}))]
    assert nomes == ["Aluno09"]


def test_administradora_aparece_com_motivo():
    lista = contas.Lista((_c(1010, "Prof", admin=True),), (), "PC")
    assert etapas.contas_locais(lista, frozenset()) == [(lista.contas[0], "administradora")]


def test_painel_mostra_todas_as_locais_e_bloqueadas_sem_marcar(painel):
    p = painel
    itens = {p.alunos.item(i).text(): p.alunos.item(i) for i in range(p.alunos.count())}
    assert set(itens) == {
        "Aluno01",
        "Aluno02 — conta logada",
        "Tecnico — conta do Bench",
        "Antiga — desativada",
        "Nova — sem perfil",
        "Aluno03",
    }
    bloqueada = itens["Aluno02 — conta logada"]
    assert not bloqueada.flags() & Qt.ItemFlag.ItemIsEnabled
    assert bloqueada.checkState() == Qt.CheckState.Unchecked
    assert p.alvos() == [f"{BASE}1002", f"{BASE}1007"]


# ---------------------------------------------------------------- 4. marcar e desmarcar todas


def test_marcar_e_desmarcar_todas_as_etapas(painel):
    p = painel
    p.b_etapas_nenhuma.click()
    assert all(
        p.lista.topLevelItem(i).checkState(0) == Qt.CheckState.Unchecked
        for i in range(p.lista.topLevelItemCount())
    )
    assert not p.b_rodar.isEnabled()
    p.b_etapas_todas.click()
    assert p.b_rodar.text() == f"Rodar {len(_visiveis(p))} etapa(s)"


def test_marcar_e_desmarcar_todas_as_contas_so_as_livres(painel):
    p = painel
    p.b_contas_nenhuma.click()
    assert p.alvos() == []
    p.b_contas_todas.click()
    assert p.alvos() == [f"{BASE}1002", f"{BASE}1007"]  # as bloqueadas continuam de fora


# ---------------------------------------------------------------- 5. Atualizar


def test_atualizar_mantem_as_marcacoes(painel, monkeypatch):
    p = painel
    p.alunos.item(_linha(p, "Aluno03")).setCheckState(Qt.CheckState.Unchecked)
    nova = contas.Lista((*LISTA.contas, _c(1009, "Aluno04")), (), "PC")
    monkeypatch.setattr(contas, "listar", lambda **k: nova)
    p.b_atualizar.click()
    assert p.alvos() == [f"{BASE}1002", f"{BASE}1009"]  # Aluno03 continua desmarcada


def _linha(p, nome: str) -> int:
    for i in range(p.alunos.count()):
        if p.alunos.item(i).data(Qt.ItemDataRole.UserRole) and p.alunos.item(i).text().startswith(
            nome
        ):
            return i
    raise AssertionError(nome)


def test_atualizar_desativado_enquanto_ocupado(painel):
    painel._ocupar(True)
    assert not painel.b_atualizar.isEnabled() and not painel.b_encerrar.isEnabled()
    painel._ocupar(False)
    assert painel.b_atualizar.isEnabled() and painel.b_encerrar.isEnabled()


# ---------------------------------------------------------------- 6. Encerrar sessões


def test_encerrar_sessoes_usa_o_dialogo_das_contas_e_atualiza(painel, monkeypatch):
    p = painel
    pedidos, encerradas = [], []

    def pedir(pai, lista):
        pedidos.append([c.nome for c in contas.com_sessao(lista)])
        return [f"{BASE}1003"]

    monkeypatch.setattr(ui_contas, "pedir_encerrar", pedir)
    monkeypatch.setattr(
        contas,
        "encerrar_sessao",
        lambda sid: encerradas.append(sid) or contas.Feito(True, "ok"),
    )
    depois = contas.Lista(
        tuple(_c(1003, "Aluno02") if c.sid == f"{BASE}1003" else c for c in LISTA.contas),
        (),
        "PC",
    )
    monkeypatch.setattr(contas, "listar", lambda **k: depois)
    p.b_encerrar.click()
    assert pedidos == [["Aluno02", "Tecnico"]]
    assert encerradas == [f"{BASE}1003"]
    assert f"{BASE}1003" in p.alvos()  # deixou de estar logada: vira alvo, marcada


def test_encerrar_sem_admin_desativado(qtbot, monkeypatch):
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_carregar_alunos", lambda self, m=None: None)
    p = ui_prep.PainelPreparacao(False, _cad, lambda: "UM-01")
    qtbot.addWidget(p)
    assert not p.b_encerrar.isEnabled()


def test_manutencao_tem_os_mesmos_botoes(qtbot, monkeypatch):
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(contas, "listar", lambda **k: LISTA)
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_carregar_alunos", CARREGAR)
    p = ui_prep.PainelPreparacao(True, _cad, lambda: "UM-01", manutencao=True)
    qtbot.addWidget(p)
    p._carregar_alunos()
    for b in (p.b_etapas_todas, p.b_etapas_nenhuma, p.b_contas_todas, p.b_contas_nenhuma):
        assert b.isVisible() or not p.isVisible()
    assert p.b_atualizar.isEnabled() and p.b_encerrar.isEnabled()
    # ADR-081: a conta logada (1003) entra na Manutenção, que encerra a sessão antes de tudo.
    assert p.alvos() == [f"{BASE}1002", f"{BASE}1003", f"{BASE}1007"]


# ---------------------------------------------------------------- leitura automática (ADR-073)


def test_leitura_automatica_le_uma_vez_depois_das_contas(qtbot, monkeypatch):
    """O Início pede: a Configuração monta (perfil da unidade, contas) e lê, sem aplicar nada."""
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(contas, "listar", lambda **k: LISTA)
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_ver_guardado", lambda self: None)
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_carregar_alunos", CARREGAR)
    cad = _cad()
    p = ui_prep.PainelPreparacao(True, lambda: cad, lambda: "UM-01")
    qtbot.addWidget(p)
    p.etapas = [Falsa(e) for e in PERFIL.etapas]
    sinais = []
    p.leitura.connect(lambda: sinais.append(p.lendo))
    assert p.ler_automatico() is True
    assert p.andamento is not None and p.alvos()  # leu depois de carregar as contas
    assert p.perfil.currentData() == "administrativo"  # o perfil padrão da unidade
    assert not _aplicadas(p)  # só leitura
    assert sinais and sinais[-1] is False  # avisou o fim
    assert p.ler_automatico() is False  # já leu: não repete


def test_leitura_automatica_nao_atropela_quem_esta_rodando(painel):
    painel._ocupar(True)
    assert painel.ler_automatico() is False
