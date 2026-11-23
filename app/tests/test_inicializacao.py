"""Inicialização (ADR-075): leitura, regras de essencial e recomendado, desligar e a tela. Nada
lê nem muda o Windows."""

import json

import pytest

from itc_bench.servicos import executor
from itc_bench.servicos import inicializacao as ini
from itc_bench.ui import inicializacao as ui_ini
from itc_bench.ui import tarefa

B = chr(92)
SID = "S-1-5-21-1-2-3-1001"
LER = ui_ini.PainelInicializacao.ler
SAIDA = {
    "itens": [
        {"tipo": "run", "sid": "MAQUINA", "conta": "", "nome": "SecurityHealth",
         "comando": "SecurityHealthSystray.exe", "ativo": True},
        {"tipo": "pasta", "sid": "MAQUINA", "conta": "", "nome": "AnyDesk.lnk",
         "comando": "AnyDesk.lnk", "ativo": True},
        {"tipo": "runuser", "sid": SID, "conta": "Tarde", "nome": "OneDrive",
         "comando": "OneDrive.exe /background", "ativo": True},
        {"tipo": "run", "sid": "MAQUINA", "conta": "", "nome": "Riot Vanguard",
         "comando": "vgtray.exe", "ativo": False},
        {"tipo": "app", "sid": SID, "conta": "Tarde",
         "nome": "Microsoft.Copilot_8wekyb3d8bbwe" + B + "CopilotStartup",
         "comando": "Microsoft.Copilot", "ativo": True},
        {"tipo": "tarefa", "sid": "MAQUINA", "conta": "", "nome": B + "Adobe Acrobat Update Task",
         "comando": "AdobeARM.exe", "ativo": True},
        {"tipo": "erro", "sid": SID, "conta": "Tarde", "nome": "conta", "ativo": False},
    ],
    "servicos": {"nome": "GLPI Agent", "rodando": True, "comando": "glpi-agent.exe"},
    "boots": [{"data": "2026-11-20T02:28:28", "boot_ms": 125200, "pos_ms": 46200}],
    "atrasos": [
        {"data": "2026-11-19T12:18:35", "nome": "setup.exe", "atraso_ms": 9397},
        {"data": "2026-11-20T00:06:43", "nome": "Windows Modules Installer", "atraso_ms": 104298},
    ],
}  # fmt: skip


def _rodar(saida, chamadas=None):
    def rodar(script, **k):
        if chamadas is not None:
            chamadas.append((script, k))
        return executor.Resultado(0, json.dumps(saida), "", 0.1, False)

    return rodar


def _leitura():
    return ini.ler(rodar=_rodar(SAIDA))


# ---------------------------------------------------------------- serviço


def test_ler_monta_itens_servicos_e_tempos():
    chamadas = []
    lido = ini.ler(rodar=_rodar(SAIDA, chamadas))
    assert "Get-ScheduledTask" in chamadas[0][0] and "function Contas" in chamadas[0][0]
    assert len(lido.itens) == 6  # tipo desconhecido fica de fora
    assert len(lido.servicos) == 1 and lido.servicos[0].rodando  # objeto solto vira lista
    assert lido.boots[0].boot_ms == 125200
    assert [a.atraso_ms for a in lido.atrasos] == [104298, 9397]  # pelo número, não pelo texto


def test_essencial_e_recomendado():
    por = {i.titulo: i for i in _leitura().itens}
    assert por["SecurityHealth"].essencial and por["AnyDesk"].essencial
    assert not por["AnyDesk"].recomendado
    assert por["OneDrive"].recomendado and por["Microsoft.Copilot"].recomendado
    assert por["Riot Vanguard"].recomendado and not por["Riot Vanguard"].ativo
    assert not por["Adobe Acrobat Update Task"].recomendado
    assert por["OneDrive"].onde == "Tarde" and por["SecurityHealth"].onde == "Todas as contas"


def test_desligar_manda_so_os_ligados_e_nao_essenciais():
    itens = _leitura().itens
    chamadas = []
    resposta = [
        {"tipo": "runuser", "sid": SID, "nome": "OneDrive", "codigo": ""},
        {"tipo": "tarefa", "sid": "MAQUINA", "nome": B + "Adobe Acrobat Update Task",
         "codigo": "sumiu"},
    ]  # fmt: skip
    r = ini.desligar(itens, rodar=_rodar(resposta, chamadas))
    enviados = json.loads(chamadas[0][1]["itens"])
    nomes = {e["nome"] for e in enviados}
    assert "SecurityHealth" not in nomes and "AnyDesk.lnk" not in nomes  # essenciais
    assert "Riot Vanguard" not in nomes  # já desligado
    assert {"OneDrive", B + "Adobe Acrobat Update Task"} <= nomes
    assert "ConvertFrom-Json" in chamadas[0][0]
    assert [x.ok for x in r] == [True, False] and r[1].motivo == "não está mais na inicialização"


def test_desligar_sem_nada_nao_roda():
    def rodar(*_a, **_k):
        raise AssertionError("não devia rodar")

    assert ini.desligar([], rodar=rodar) == []


def test_falha_do_powershell_vira_erro():
    def rodar(*_a, **_k):
        return executor.Resultado(None, "", "", 180, True)

    with pytest.raises(RuntimeError, match="tempo esgotado"):
        ini.ler(rodar=rodar)


def test_trechos_cabem_no_limite():
    for nome in ("ler.ps1", "desligar.ps1"):
        assert len(executor.ABERTURA_PS + ini._script(nome)) < executor.LIMITE_SCRIPT


# ---------------------------------------------------------------- tela


def _painel(qtbot, admin=True):
    p = ui_ini.PainelInicializacao(admin)
    qtbot.addWidget(p)
    p._leu(_leitura())
    return p


def _linha(p, titulo):
    for n in range(p.arvore.topLevelItemCount()):
        linha = p.arvore.topLevelItem(n)
        if linha.text(0) == titulo:
            return linha
    raise AssertionError(titulo)


def test_tela_mostra_so_os_inuteis_ligados(qtbot):
    p = _painel(qtbot)
    titulos = [p.arvore.topLevelItem(n).text(0) for n in range(p.arvore.topLevelItemCount())]
    assert titulos == ["Microsoft.Copilot", "OneDrive"]  # sem essencial, neutro nem desligado
    assert {i.titulo for i in p.marcados()} == {"OneDrive", "Microsoft.Copilot"}
    assert p.estado.text() == "2 item(ns) sem função atrasando a inicialização."
    assert p.b_desligar.isEnabled() and p.b_desligar.text() == "Desligar marcados (2)"
    assert p.servicos.topLevelItemCount() == 1
    assert p.atrasos.topLevelItem(0).text(1) == "104,3 s"
    assert "125,2 s" in p.resumo_boot.text()


def test_desmarcar_tira_do_desligar(qtbot):
    from PySide6.QtCore import Qt

    p = _painel(qtbot)
    _linha(p, "OneDrive").setCheckState(0, Qt.CheckState.Unchecked)
    assert [i.titulo for i in p.marcados()] == ["Microsoft.Copilot"]
    assert p.b_desligar.text() == "Desligar marcados (1)"


def test_nada_inutil(qtbot):
    p = ui_ini.PainelInicializacao(True)
    qtbot.addWidget(p)
    limpo = ini.Leitura(tuple(i for i in _leitura().itens if not i.recomendado), (), (), ())
    p._leu(limpo)
    assert p.arvore.topLevelItemCount() == 0 and not p.b_desligar.isEnabled()
    assert p.estado.text() == "Nada sem função na inicialização."


def test_sem_admin_nao_desliga(qtbot):
    p = _painel(qtbot, admin=False)
    assert p.marcados() and not p.b_desligar.isEnabled()


def test_desligar_confirma_e_le_de_novo(qtbot, monkeypatch):
    p = _painel(qtbot)
    textos = []
    monkeypatch.setattr(ui_ini, "confirmar", lambda _p, _t, texto: textos.append(texto) or True)
    pedidos = []

    def iniciar(f, ok, falha):
        pedidos.append(f)

    monkeypatch.setattr(tarefa, "iniciar", iniciar)
    p._desligar()
    assert "Desligar 2 item(ns)" in textos[0] and "OneDrive (Tarde)" in textos[0]
    assert len(pedidos) == 1 and not p.b_desligar.isEnabled()
    item = p.marcados()[0]
    monkeypatch.setattr(ui_ini.PainelInicializacao, "ler", LER)
    p._desligou([ini.Resultado(item, ""), ini.Resultado(item, "falhou")])
    assert p.estado.text() == "Lendo a inicialização de todas as contas… (pode levar um minuto)"
    assert len(pedidos) == 2  # leu de novo


def test_cancelar_nao_desliga(qtbot, monkeypatch):
    p = _painel(qtbot)
    monkeypatch.setattr(ui_ini, "confirmar", lambda *_a: False)
    monkeypatch.setattr(tarefa, "iniciar", lambda *_a: pytest.fail("não devia rodar"))
    p._desligar()
    assert p.b_desligar.isEnabled()


def test_tailscale_nao_e_essencial():
    item = ini.Item("pasta", "MAQUINA", "", "Tailscale.lnk", "Tailscale.lnk", True)
    assert not item.essencial and item.recomendado


@pytest.mark.parametrize(
    ("nome", "comando"),
    [
        ("RiotClient", "RiotClientServices.exe --launch-background-mode"),
        ("Riot Vanguard", "vgtray.exe"),
        ("Vgtray", "C:/Program Files/Riot Vanguard/vgtray.exe"),
        ("Microsoft.Copilot", "Microsoft.Copilot"),
        ("MicrosoftWindows.CrossDevice", "Dispositivos móveis"),
        ("msedge_cleanup", "msedge.exe --no-startup-window"),
        ("OneDrive", "OneDrive.exe /background"),
        ("Send to OneNote.lnk", "ONENOTEM.EXE /tsr"),
        ("Roblox", "RobloxPlayerBeta.exe"),
    ],
)
def test_lista_do_responsavel_e_sem_funcao(nome, comando):
    assert ini.Item("run", "MAQUINA", "", nome, comando, True).recomendado


TESTE_HIVE = r"""
$script:loads = 0
function Reg-Exe([string[]]$argumentos) {
    if ($argumentos[0] -eq 'load') { $script:loads++ }
    return 0
}
$arq = Join-Path $env:ITC_PASTA 'NTUSER.DAT'
$a = Abrir-Hive 'S-1-5-21-9-9-9-1001' $arq
$b = Abrir-Hive 'S-1-5-21-9-9-9-1001' $arq
Write-Output ("{0}|{1}|{2}" -f ($a -ceq $b), $script:loads, ($a -cmatch '^ITCBench_[0-9a-f]{8}$'))
"""


def test_mesma_conta_na_mesma_execucao_carrega_o_hive_uma_vez(tmp_path):
    # Log de 23/11: o 2º item da mesma conta sem sessão voltava conta_em_uso, porque o trecho
    # tentava carregar de novo o NTUSER.DAT que ele mesmo já tinha carregado.
    (tmp_path / "NTUSER.DAT").write_bytes(b"x")
    script = (ini.RECURSOS / "comum.ps1").read_text("utf-8") + TESTE_HIVE
    r = executor.powershell(script, pasta=str(tmp_path))
    assert r.ok, r.erros
    assert r.saida.strip() == "True|1|True"
