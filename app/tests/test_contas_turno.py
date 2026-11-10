"""Contas por turno (ADR-029): regra de nomes, prévia, criação conta a conta e tela.

Só nomes fictícios; nenhuma conta real é criada (o PowerShell é falso).
"""

import pytest
from test_contas import ALUNO, TECNICO, Falso, conta, lista

from itc_bench.servicos import contas, contas_turno, identificacao
from itc_bench.servicos.executor import Resultado
from itc_bench.servicos.identificacao import Estado
from itc_bench.ui import identificacao as tela
from itc_bench.ui.identificacao import PainelIdentificacao

BASE = "BSBIA02-EST32"
PROT = frozenset({"suporte"})


# ---------------------------------------------------------------- regra de nomes


@pytest.mark.parametrize(
    ("turnos", "sufixo", "esperado"),
    [
        (("Manha", "Tarde", "Noite"), "", ["Manha", "Tarde", "Noite"]),
        (("Manha",), "", ["Manha"]),
        (("Tarde",), "", ["Tarde"]),
        (("Noite",), "", ["Noite"]),
        (("Manha", "Tarde"), "", ["Manha", "Tarde"]),
        (("Manha", "Noite"), "", ["Manha", "Noite"]),
        (("Tarde", "Noite"), "", ["Tarde", "Noite"]),
        ((), "", [None]),
        ((), "Recepcao", ["Recepcao"]),
        ((), "  Guiche  ", ["Guiche"]),
        # Com turno marcado, o sufixo é ignorado (item 7 do pedido).
        (("Manha", "Tarde"), "Recepcao", ["Manha", "Tarde"]),
        # A ordem é sempre Manhã, Tarde, Noite, seja qual for a ordem marcada.
        (("Noite", "Manha"), "", ["Manha", "Noite"]),
    ],
)
def test_nomes(turnos, sufixo, esperado):
    nomes = contas_turno.nomes(BASE, turnos, sufixo)
    assert list(nomes) == [BASE if s is None else f"{BASE}-{s}" for s in esperado]


@pytest.mark.parametrize(
    ("turnos", "sufixo", "esperado"),
    [
        (("Manha", "Tarde"), "Recepcao", ["Manha", "Tarde", "Recepcao"]),
        (("Manha", "Tarde", "Noite"), "Guiche", ["Manha", "Tarde", "Noite", "Guiche"]),
        (("Noite",), "", ["Noite"]),  # opção marcada, sufixo vazio: só os turnos
        ((), "Recepcao", ["Recepcao"]),  # sem turno, igual ao de sempre
        ((), "", [None]),
    ],
)
def test_nomes_com_sufixo_junto_dos_turnos(turnos, sufixo, esperado):
    nomes = contas_turno.nomes(BASE, turnos, sufixo, com_sufixo=True)
    assert list(nomes) == [BASE if s is None else f"{BASE}-{s}" for s in esperado]


def test_previa_com_sufixo_recusa_so_a_conta_do_sufixo():
    previa = contas_turno.previa(BASE, ("Manha",), "Sala 2", None, PROT, com_sufixo=True)
    assert [(p.nome, p.problema is None) for p in previa] == [
        (f"{BASE}-Manha", True),
        (f"{BASE}-Sala 2", False),
    ]


def test_criar_com_sufixo_junto_dos_turnos():
    falso = Falso(TECNICO)
    resumo = contas_turno.criar(BASE, ("Tarde",), "Guiche", com_sufixo=True, rodar=falso)
    assert [(i.nome, i.situacao) for i in resumo.itens] == [
        (f"{BASE}-Tarde", "criado"),
        (f"{BASE}-Guiche", "criado"),
    ]


def test_sem_base_nenhuma_conta():
    assert contas_turno.nomes("", ("Manha",), "x") == ()
    assert contas_turno.nomes("   ", (), "") == ()


VALIDOS = ("", "Recepcao", "Sala_2", "Guiche-1")
INVALIDOS = ("Recepção", "Sala 2", "-x", "x-", "a/b")


@pytest.mark.parametrize(
    ("sufixo", "ok"), [*((s, True) for s in VALIDOS), *((s, False) for s in INVALIDOS)]
)
def test_validar_sufixo(sufixo, ok):
    assert (contas_turno.validar_sufixo(sufixo) is None) is ok


# ---------------------------------------------------------------- prévia


def test_previa_marca_existente_e_longo():
    existente = conta(1010, f"{BASE}-Manha")
    previa = contas_turno.previa(BASE, ("Manha", "Tarde"), "", lista(existente), PROT)
    assert [(p.nome, p.existe, p.problema) for p in previa] == [
        (f"{BASE}-Manha", True, None),
        (f"{BASE}-Tarde", False, None),
    ]
    longo = contas_turno.previa("ABCDEFGHIJKLMNO", ("Manha",), "", None, PROT)
    assert longo[0].problema and "20" in longo[0].problema
    sufixo = contas_turno.previa(BASE, (), "Administrativo", None, PROT)
    assert sufixo[0].problema and "20" in sufixo[0].problema


def test_previa_sufixo_invalido_so_sem_turno():
    assert contas_turno.previa(BASE, (), "Sala 2", None, PROT)[0].problema
    assert contas_turno.previa(BASE, ("Tarde",), "Sala 2", None, PROT)[0].problema is None


def test_previa_aceita_nome_igual_ao_computador():
    lista_pc = contas.Lista((), (), BASE)
    assert contas_turno.previa(BASE, (), "", lista_pc, PROT)[0].problema is None
    # A tela Contas continua recusando.
    assert contas.validar_nome(BASE, lista_pc, PROT) == contas.MENSAGENS["nome_computador"]


# ---------------------------------------------------------------- criação


def test_criar_cria_so_o_que_falta_padrao_e_sem_senha():
    falso = Falso(TECNICO, ALUNO, conta(1010, f"{BASE}-Noite"))
    resumo = contas_turno.criar(BASE, ("Manha", "Tarde", "Noite"), "", rodar=falso)
    assert [(i.nome, i.situacao) for i in resumo.itens] == [
        (f"{BASE}-Manha", "criado"),
        (f"{BASE}-Tarde", "criado"),
        (f"{BASE}-Noite", "existia"),
    ]
    assert (resumo.criados, resumo.existentes, resumo.erros) == (2, 1, 0)
    assert resumo.computador == BASE
    assert len(falso.chamadas) == 2
    for _, kw in falso.chamadas:
        assert kw["tipo"] == "padrao" and "senha" not in kw
        assert kw["permitir_nome_pc"] == "1"


def test_criar_erro_numa_conta_nao_para_as_outras():
    class Metade(Falso):
        def __call__(self, script: str, **kw: object) -> Resultado:
            r = super().__call__(script, **kw)
            if kw.get("nome") == f"{BASE}-Manha":
                return Resultado(1, "ERRO|criar|Acesso negado", "", 0.1, False)
            return r

    resumo = contas_turno.criar(BASE, ("Manha", "Tarde"), "", rodar=Metade(TECNICO))
    assert [i.situacao for i in resumo.itens] == ["erro", "criado"]
    assert "Acesso negado" in resumo.itens[0].mensagem
    assert (resumo.criados, resumo.erros) == (1, 1)


def test_criar_recusa_invalido_sem_chamar_powershell():
    falso = Falso(TECNICO)
    resumo = contas_turno.criar(BASE, (), "Sala 2", rodar=falso)
    assert resumo.erros == 1 and falso.chamadas == []


def test_criar_conta_unica_com_nome_do_computador():
    falso = Falso(TECNICO)
    resumo = contas_turno.criar(BASE, (), "", rodar=falso)
    assert [(i.nome, i.situacao) for i in resumo.itens] == [(BASE, "criado")]


# ---------------------------------------------------------------- tela


def estado(pendente: str = BASE) -> Estado:
    return Estado("PC-ANTIGO", pendente, False, frozenset())


def painel(qtbot, monkeypatch, admin=True, lista_=None):
    monkeypatch.setattr(identificacao, "estado", lambda **_: estado())
    monkeypatch.setattr(contas, "listar", lambda **_: lista_ or lista(TECNICO))
    p = PainelIdentificacao(admin)
    qtbot.addWidget(p)
    p.show()
    qtbot.waitUntil(lambda: p.estado is not None and p.lista is not None and not p.ocupado)
    return p


# ---------------------------------------------------------------- renomear + criar (serviço)


def test_configurar_renomeia_e_cria_com_o_nome_novo(monkeypatch):
    chamadas: list[str] = []

    def renomear(nome, **_):
        chamadas.append(nome)
        return identificacao.Feito(True, f"Nome trocado para {nome}.")

    monkeypatch.setattr(identificacao, "renomear", renomear)
    resumo = contas_turno.configurar(
        " novo-pc01 ", ("Manha",), "", renomear=True, rodar=Falso(TECNICO)
    )
    assert chamadas == ["NOVO-PC01"]
    assert [i.nome for i in resumo.itens] == ["NOVO-PC01-Manha"]
    assert resumo.renomeio is not None and resumo.renomeio.ok


def test_configurar_falha_no_renomear_nao_cria_contas(monkeypatch):
    monkeypatch.setattr(
        identificacao, "renomear", lambda *_a, **_k: identificacao.Feito(False, "Nome inválido.")
    )
    falso = Falso(TECNICO)
    resumo = contas_turno.configurar(BASE, ("Manha",), "", renomear=True, rodar=falso)
    assert resumo.itens == () and resumo.falhou_renomear and falso.chamadas == []


def test_configurar_sem_renomear_nao_chama_rename(monkeypatch):
    monkeypatch.setattr(identificacao, "renomear", lambda *_a, **_k: pytest.fail("renomeou"))
    resumo = contas_turno.configurar(BASE, (), "Recepcao", renomear=False, rodar=Falso(TECNICO))
    assert resumo.renomeio is None and [i.nome for i in resumo.itens] == [f"{BASE}-Recepcao"]


# ---------------------------------------------------------------- tela


def test_tela_um_bloco_sem_reiniciar_agora(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    assert not hasattr(p, "b_reiniciar") and not hasattr(p, "b_renomear")
    assert p.nome.text() == BASE  # já vem com o nome que vale depois de reiniciar
    assert p.b_executar.text() == "Criar usuários"


def test_tela_atualiza_previa(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    assert p.previa.text() == f"✓ {BASE}"
    p.sufixo.setText("Guiche")
    assert p.previa.text() == f"✓ {BASE}-Guiche"
    p.turnos["Manha"].setChecked(True)
    p.turnos["Tarde"].setChecked(True)
    assert p.previa.text() == f"✓ {BASE}-Manha\n✓ {BASE}-Tarde"
    assert not p.sufixo.isEnabled() and "ignorado" in p.dica_sufixo.text()
    assert p.b_executar.isEnabled()
    p.turnos["Manha"].setChecked(False)
    p.turnos["Tarde"].setChecked(False)
    assert p.sufixo.isEnabled() and p.previa.text() == f"✓ {BASE}-Guiche"


def test_tela_opcao_sufixo_junto_dos_turnos(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    assert not p.com_sufixo.isEnabled()  # sem turno, o sufixo já vira conta sozinho
    p.sufixo.setText("Guiche")
    p.turnos["Manha"].setChecked(True)
    assert p.com_sufixo.isEnabled() and not p.sufixo.isEnabled()
    assert p.previa.text() == f"✓ {BASE}-Manha" and "opção abaixo" in p.dica_sufixo.text()
    p.com_sufixo.setChecked(True)
    assert p.sufixo.isEnabled() and p.dica_sufixo.text() == ""
    assert p.previa.text() == f"✓ {BASE}-Manha\n✓ {BASE}-Guiche"
    pedidos: list[bool] = []
    monkeypatch.setattr(tela, "confirmar", lambda *_: True)
    monkeypatch.setattr(tela, "escolher", lambda *_: False)
    monkeypatch.setattr(tela.QMessageBox, "exec", lambda _self: 0)

    def configurar(nome, turnos, sufixo, *, com_sufixo, **_):
        pedidos.append(com_sufixo)
        return contas_turno.Resumo(nome, ())

    monkeypatch.setattr(contas_turno, "configurar", configurar)
    p.b_executar.click()
    qtbot.waitUntil(lambda: bool(pedidos))
    assert pedidos == [True]


def test_tela_nome_novo_entra_na_previa_e_no_botao(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.nome.setText("novo-pc01")
    p.turnos["Noite"].setChecked(True)
    assert p.previa.text() == f"✓ Renomear {BASE} → NOVO-PC01\n✓ NOVO-PC01-Noite"
    assert p.b_executar.text() == "Renomear e criar usuários" and p.b_executar.isEnabled()
    p.nome.setText("-ruim")
    assert not p.b_executar.isEnabled() and p.erro.text()


def test_tela_bloqueia_sem_admin_e_com_erro(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    assert not p.b_executar.isEnabled() and "administrador" in p.motivo.text()
    p = painel(qtbot, monkeypatch)
    p.sufixo.setText("Administrativo")
    assert not p.b_executar.isEnabled() and p.previa.text().startswith("✕")


def test_tela_todas_existentes(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, lista_=lista(TECNICO, conta(1010, BASE)))
    assert "⚠" in p.previa.text() and not p.b_executar.isEnabled()


def falsos_de_tela(monkeypatch, respostas, reinicios):
    monkeypatch.setattr(tela, "confirmar", lambda *_: True)
    monkeypatch.setattr(tela, "escolher", lambda _p, titulo, *_: respostas.append(titulo) or False)
    monkeypatch.setattr(tela.QMessageBox, "exec", lambda _self: 0)
    monkeypatch.setattr(identificacao, "reiniciar", lambda **_: reinicios.append(True))


def test_tela_cria_mostra_resumo_e_so_entao_pergunta_reinicio(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.nome.setText("NOVO-PC01")
    p.turnos["Noite"].setChecked(True)
    respostas: list[str] = []
    reinicios: list[bool] = []
    falsos_de_tela(monkeypatch, respostas, reinicios)
    pedidos: list[tuple[str, bool]] = []

    def configurar(nome, turnos, sufixo, *, renomear, **_):
        pedidos.append((nome, renomear))
        return contas_turno.Resumo(
            nome,
            (contas_turno.Item(f"{nome}-Noite", "criado", "criado"),),
            identificacao.Feito(True, f"Nome trocado para {nome}. Vale depois de reiniciar."),
        )

    monkeypatch.setattr(contas_turno, "configurar", configurar)
    p.b_executar.click()
    qtbot.waitUntil(lambda: "CONFIGURAÇÃO CONCLUÍDA" in p.resultado.text())
    texto = p.resultado.text()
    assert pedidos == [("NOVO-PC01", True)]
    assert "Computador: NOVO-PC01" in texto and "Nome: Nome trocado" in texto
    assert "✓ NOVO-PC01-Noite — criado" in texto
    assert "Total criados: 1" in texto and "Erros: 0" in texto
    assert respostas == ["Configuração concluída"] and reinicios == []


def test_tela_falha_no_renomear_nao_pergunta_reinicio(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p.nome.setText("NOVO-PC01")
    respostas: list[str] = []
    reinicios: list[bool] = []
    falsos_de_tela(monkeypatch, respostas, reinicios)
    monkeypatch.setattr(
        contas_turno,
        "configurar",
        lambda nome, *_a, **_k: contas_turno.Resumo(
            nome, (), identificacao.Feito(False, "O Windows recusou o nome")
        ),
    )
    p.b_executar.click()
    qtbot.waitUntil(lambda: "não foi renomeado" in p.resultado.text())
    assert "Nenhuma conta foi criada" in p.resultado.text()
    assert respostas == [] and reinicios == []


def test_reiniciar_agora_pede_segunda_confirmacao(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    titulos: list[str] = []
    reinicios: list[bool] = []

    def so_a_primeira(_p, titulo, *_):
        titulos.append(titulo)
        return titulo == "Configuração concluída"

    monkeypatch.setattr(tela, "escolher", so_a_primeira)
    monkeypatch.setattr(identificacao, "reiniciar", lambda **_: reinicios.append(True))
    p._perguntar_reinicio()
    assert titulos == ["Configuração concluída", "Reiniciar"] and reinicios == []
