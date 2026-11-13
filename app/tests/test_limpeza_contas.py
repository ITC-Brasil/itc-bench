"""Limpeza de contas (ADR-042): regras, trecho e tela. Nada apaga arquivo de conta real."""

import json
import re

import pytest

from itc_bench.servicos import executor, limpeza
from itc_bench.servicos.contas import Conta
from itc_bench.ui import limpeza as tela

BASE = "S-1-5-21-111-222-333-"
TRECHO = (limpeza.RECURSOS / "contas.ps1").read_text("utf-8")


def conta(rid: int, nome: str, **kw: object) -> Conta:
    valores: dict[str, object] = {
        "ativo": True,
        "admin": False,
        "fonte": "Local",
        "logada": False,
        "ultima": None,
        "perfil": rf"C:\Users\{nome}",
        "carregado": False,
    }
    valores.update(kw)
    return Conta(sid=f"{BASE}{rid}", nome=nome, **valores)  # type: ignore[arg-type]


ALUNO = conta(1001, "Aluno01")
ADMIN = conta(1002, "Professor", admin=True)


def _resultado(saida: object, codigo: int = 0) -> executor.Resultado:
    return executor.Resultado(codigo, json.dumps(saida), "", 0.1, False)


class Rodar:
    def __init__(self, saida: object) -> None:
        self.saida = saida
        self.chamadas: list[dict[str, object]] = []

    def __call__(self, script: str, **kw: object) -> executor.Resultado:
        self.chamadas.append(kw)
        return _resultado(self.saida)


@pytest.mark.parametrize(
    ("c", "codigo"),
    [
        (conta(500, "Administrador", admin=True), "nativo"),
        (conta(1003, "Suporte", admin=True), "suporte"),
        (conta(1004, "SuporteITC"), "suporte"),
        (conta(1005, "Gestão"), "restrita"),
        (conta(1006, "Gestao"), "restrita"),
        (conta(1007, "Novo", perfil=None), "sem_perfil"),
        (conta(1008, "Logado", logada=True), "sessao"),
        (conta(1009, "Carregado", carregado=True), "sessao"),
        (ALUNO, ""),
        (ADMIN, ""),  # o responsável liberou qualquer conta marcada, administradoras inclusive
    ],
)
def test_recusa_conta(c, codigo):
    assert limpeza.recusa_conta(c, {"suporteitc"}) == codigo


def test_recusada_nao_vai_ao_trecho_e_validas_vao_por_posicao():
    rodar = Rodar(
        [
            {"n": 1, "categoria": "pessoais", "arquivos": 3, "bytes": 2048, "em_uso": 0},
            {"n": 2, "categoria": "programas", "arquivos": 1, "bytes": 10, "em_uso": 1},
        ]
    )
    suporte = conta(1003, "Suporte", admin=True)
    itens = limpeza.previa_contas([ALUNO, suporte, ADMIN], {"Suporte"}, rodar=rodar)
    (kw,) = rodar.chamadas
    assert kw["sids"] == f"{ALUNO.sid},{ADMIN.sid}"
    assert kw["protegidas"] == "suporte"
    assert kw["acao"] == "previa"
    por = {(i.sid, i.categoria): i for i in itens}
    assert por[(suporte.sid, "")].codigo == "suporte"
    assert por[(ALUNO.sid, "pessoais")].bytes == 2048
    assert por[(ADMIN.sid, "programas")].em_uso == 1


def test_saida_fora_do_contrato_e_ignorada():
    rodar = Rodar(
        [
            {"n": 9, "categoria": "pessoais", "arquivos": 1, "bytes": 1, "em_uso": 0},
            {"n": 1, "categoria": "windows", "arquivos": 1, "bytes": 1, "em_uso": 0},
            {"n": 1, "categoria": "", "arquivos": 0, "bytes": 0, "em_uso": 0, "codigo": "dono"},
        ]
    )
    itens = limpeza.limpar_contas([ALUNO], set(), rodar=rodar)
    assert [(i.categoria, i.codigo) for i in itens] == [("", "dono")]
    assert itens[0].motivo == "é a conta que está rodando o Bench"


def test_todas_recusadas_nao_roda_o_trecho():
    rodar = Rodar([])
    itens = limpeza.limpar_contas([conta(500, "Administrador")], set(), rodar=rodar)
    assert rodar.chamadas == [] and itens[0].codigo == "nativo"


def test_falha_do_trecho_vira_erro():
    def falha(script: str, **kw: object) -> executor.Resultado:
        return executor.Resultado(1, "", "x", 0.1, False)

    with pytest.raises(RuntimeError, match="código 1"):
        limpeza.limpar_contas([ALUNO], set(), rodar=falha)


def test_log_sem_sid_nem_nome(caplog):
    rodar = Rodar([{"n": 1, "categoria": "pessoais", "arquivos": 1, "bytes": 1, "em_uso": 0}])
    with caplog.at_level("INFO"):
        limpeza.limpar_contas([ALUNO, conta(1003, "Suporte")], set(), rodar=rodar)
    assert "S-1-5-21" not in caplog.text and "Aluno01" not in caplog.text
    assert "Suporte" not in caplog.text


def test_trecho_so_pastas_fixas_e_nunca_o_registro_da_conta():
    codigo = "\n".join(ln.split("#", 1)[0] for ln in TRECHO.splitlines())
    assert "NTUSER" not in codigo.upper()
    assert not re.search(r"(?i)Remove-Item|Set-ItemProperty|New-ItemProperty|reg(\.exe)? ", codigo)
    assert "Registry::HKEY_USERS" in codigo  # só para ver se a sessão está aberta
    for proibida in ("AppData\\Roaming'", "'AppData\\Local'", "Favorites", "Packages"):
        assert proibida not in TRECHO
    for exigida in ("'dono'", "'nativo'", "'suporte'", "'restrita'", "'sessao'", "'reparse'"):
        assert exigida in TRECHO


def test_trecho_real_recusa_sem_tocar_em_nada():
    """PowerShell de verdade, só com SIDs que o trecho recusa antes de abrir qualquer pasta."""
    eu = executor.powershell(
        "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value", timeout=30
    ).saida.strip()
    sids = ["nao-e-sid", f"{BASE}500", eu]
    r = executor.powershell(TRECHO, timeout=60, acao="limpar", sids=",".join(sids), protegidas="")
    assert r.ok, r.erros
    saida = json.loads(r.saida)
    # A conta que roda os testes é recusada antes de abrir pasta. No runner do CI ela é o
    # Administrador nativo (-500), conferido antes de "dono"; numa conta de serviço, nem é SID
    # de usuário local.
    if not eu.startswith("S-1-5-21-"):
        esperado_eu = "sid_invalido"
    elif eu.endswith("-500"):
        esperado_eu = "nativo"
    else:
        esperado_eu = "dono"
    assert [(d["n"], d["codigo"], d["categoria"]) for d in saida] == [
        (1, "sid_invalido", ""),
        (2, "nativo", ""),
        (3, esperado_eu, ""),
    ]


def test_acao_desconhecida_recusada():
    r = executor.powershell(TRECHO, timeout=60, acao="formatar", sids="", protegidas="")
    assert not r.ok


# ---------------------------------------------------------------- tela


def _painel(qtbot, admin=True):
    p = tela.PainelLimpezaContas(admin, lambda: None)
    qtbot.addWidget(p)
    gestao = conta(1005, "Gestão")
    itens = [
        limpeza.ItemConta(ALUNO.sid, "pessoais", 10, 3 << 30, 0),
        limpeza.ItemConta(ALUNO.sid, "temporarios", 5, 1 << 20, 2),
        limpeza.ItemConta(ADMIN.sid, "programas", 1, 1 << 30, 0),
        limpeza.ItemConta(gestao.sid, "", 0, 0, 0, "restrita"),
    ]
    p._calculou(([ALUNO, ADMIN, gestao], itens))
    return p


def test_tela_so_deixa_marcar_quem_pode(qtbot):
    from PySide6.QtCore import Qt

    p = _painel(qtbot)
    linhas = [p.arvore.topLevelItem(i) for i in range(p.arvore.topLevelItemCount())]
    assert [ln.text(0) for ln in linhas] == ["Aluno01", "Professor", "Gestão"]
    assert linhas[0].text(5) == "3,0 GB"
    assert "2 em uso" in linhas[0].text(6)
    assert linhas[2].text(6).startswith("conta Gestão")
    assert linhas[2].data(0, Qt.ItemDataRole.CheckStateRole) is None
    assert not p.b_limpar.isEnabled()
    linhas[0].setCheckState(0, Qt.CheckState.Checked)
    assert p.b_limpar.isEnabled()
    assert p.b_limpar.text() == "Limpar contas (3,0 GB)"


def test_tela_sem_admin_nao_limpa(qtbot):
    from PySide6.QtCore import Qt

    p = _painel(qtbot, admin=False)
    p.arvore.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    assert not p.b_limpar.isEnabled()


@pytest.mark.parametrize("respostas", [[False], [True, False]])
def test_tela_precisa_das_duas_confirmacoes(qtbot, monkeypatch, respostas):
    from PySide6.QtCore import Qt

    p = _painel(qtbot)
    p.arvore.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    fila = list(respostas)
    monkeypatch.setattr(tela, "confirmar", lambda *_a: fila.pop(0))
    chamado = []
    monkeypatch.setattr(tela.limpeza, "limpar_contas", lambda *a, **k: chamado.append(a) or [])
    p._limpar()
    assert chamado == [] and fila == []


def test_tela_limpa_so_as_marcadas_depois_das_duas_confirmacoes(qtbot, monkeypatch):
    from PySide6.QtCore import Qt

    p = _painel(qtbot)
    p.arvore.topLevelItem(1).setCheckState(0, Qt.CheckState.Checked)
    textos: list[str] = []
    monkeypatch.setattr(tela, "confirmar", lambda _p, _t, texto: textos.append(texto) or True)
    alvos: list[list[str]] = []

    def limpar(contas_, prot, **_k):
        alvos.append([c.sid for c in contas_])
        return [limpeza.ItemConta(ADMIN.sid, "programas", 1, 1 << 30, 0)]

    monkeypatch.setattr(tela.limpeza, "limpar_contas", limpar)
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda f, ok, falhou: ok(f()))
    p._limpar()
    assert alvos == [[ADMIN.sid]]
    assert "Professor: 1,0 GB" in textos[0] and "Ficam: papel de parede" in textos[0]
    assert "Não dá para desfazer" in textos[1]
    assert p.arvore.topLevelItem(0).text(6) == "limpa"
