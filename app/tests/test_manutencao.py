"""Configuração e Manutenção (ADR-062): ordem das etapas, energia, Wi-Fi da manutenção e tela."""

import threading
from datetime import UTC, datetime
from pathlib import PureWindowsPath

import pytest
from test_wifi import Falso, rede

from itc_bench.servicos import contas, energia, etapas, limpeza, perfis, steam, wifi
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.contas import Conta, Lista
from itc_bench.servicos.executor import Resultado
from itc_bench.ui import ajuda
from itc_bench.ui import preparacao as ui_prep


class ClienteFalso(Falso):
    def __enter__(self) -> "ClienteFalso":
        return self

    def __exit__(self, *_: object) -> None:
        return None


SID = "S-1-5-21-1-2-3-1001"


def _cadastros(*redes) -> Cadastros:
    return Cadastros("v" * 64, datetime.now(UTC), "t", "ABC01", False, (), (), redes, ())


# ---------------------------------------------------------------- listas e energia


def test_configuracao_e_manutencao_montam_na_ordem_dos_numeros():
    ctx = etapas.Contexto(admin=False, cadastros=None)
    assert tuple(e.id for e in etapas.montar(ctx)) == perfis.CONFIGURACAO.ordem
    assert tuple(e.id for e in etapas.montar_manutencao(ctx)) == (
        "limpeza_usuarios",
        "wifi_senhas",
        "diagnostico",
        "steam",
        "inicializacao",
    )
    assert [n for n, _, _ in perfis.MANUTENCAO.etapas] == [1, 2, 3, 4, 5]
    assert [n for n, _, _ in perfis.CONFIGURACAO.etapas] == list(range(1, 13))


def test_energia_nunca_no_comeco_e_planos_finais_no_fim():
    lista = {e.id: e for e in etapas.montar(etapas.Contexto(admin=True, cadastros=None))}
    inicio, fim = lista["energia_inicio"], lista["energia"]
    assert set(inicio.valores.values()) == {0}  # type: ignore[attr-defined]
    assert fim.valores == {  # type: ignore[attr-defined]
        ("tela", "ac"): 1800,
        ("tela", "dc"): 1800,
        ("suspensao", "ac"): 3600,
        ("suspensao", "dc"): 3600,
    }
    for valores in (perfis.ENERGIA_INICIO, perfis.ENERGIA):
        assert set(valores.values()) <= set(energia.TEMPOS)


# ---------------------------------------------------------------- Wi-Fi da manutenção


def test_wifi_da_manutencao_so_atualiza_redes_que_ja_existem():
    antiga = rede(1, "Rede-A", senha="SenhaAntiga-123")
    nova = rede(1, "Rede-A", senha="SenhaNova-456")
    ausente = rede(2, "Rede-B")
    cliente = ClienteFalso()
    interface = cliente.interfaces()[0]
    cliente.gravar(interface, wifi.xml_perfil(antiga))
    ctx = etapas.Contexto(admin=True, cadastros=_cadastros(nova, ausente), unidade="ABC01")
    etapa = etapas.WifiSenhas(ctx, cliente=lambda: cliente)

    lida = etapa.ler()
    assert lida.situacao == "pendente" and lida.detalhe.startswith("1 rede")
    assert etapa.aplicar(threading.Event()).estado == "ok"
    assert cliente.perfil(interface, "Rede-A", com_chave=True) == wifi.xml_perfil(nova)
    assert "Rede-B" not in cliente.perfis(interface)  # a manutenção não instala rede nova
    assert etapa.ler().situacao == "feito"


def test_wifi_da_manutencao_sem_rede_no_cadastro_bloqueia():
    ctx = etapas.Contexto(admin=True, cadastros=_cadastros(), unidade="ABC01")
    assert etapas.WifiSenhas(ctx, cliente=ClienteFalso).ler().situacao == "bloqueada"


# ---------------------------------------------------------------- tela


def test_tela_de_manutencao_sem_perfil_e_steam_so_se_instalada(qtbot, monkeypatch):
    monkeypatch.setattr(
        ui_prep.PainelPreparacao, "_carregar_alunos", lambda self, marcar=None: None
    )
    monkeypatch.setattr(steam, "instalada", lambda ler=None: False)
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p)
    p.show()
    textos = [p.lista.topLevelItem(i).text(0) for i in range(p.lista.topLevelItemCount())]
    assert textos == [
        "1. Limpeza de usuários",
        "2. Wi-Fi: atualizar senhas",
        "3. Diagnóstico",
        "5. Desligar inicialização de apps não necessários",
    ]
    assert "steam" in p.desmarcadas()  # escondida não roda
    assert p.perfil.isHidden() and not p.painel_alunos.isHidden()
    assert p.b_ler.isEnabled()
    assert ajuda.TEXTOS["manut"] == ui_prep.AJUDA_MANUTENCAO

    monkeypatch.setattr(steam, "instalada", lambda ler=None: True)
    p2 = ui_prep.PainelPreparacao(True, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p2)
    p2.show()
    textos2 = [p2.lista.topLevelItem(i).text(0) for i in range(p2.lista.topLevelItemCount())]
    assert textos2[-2:] == ["4. Remover Steam", "5. Desligar inicialização de apps não necessários"]


# ---------------------------------------------------------------- limpeza de usuários (ADR-064)


def test_limpeza_de_usuarios_le_e_limpa_so_as_categorias_da_manutencao(monkeypatch):
    aluno = Conta(SID, "Aluno01", True, False, "Local", False, None, r"C:\Users\Aluno01", False)
    chamadas = []

    def falso(acao):
        def f(contas_, protegidas_, *, categorias=(), rodar=None):
            chamadas.append((acao, [c.sid for c in contas_], tuple(categorias)))
            return [limpeza.ItemConta(SID, c, 3, 2 << 20, 0) for c in categorias]

        return f

    monkeypatch.setattr(limpeza, "previa_contas", falso("previa"))
    monkeypatch.setattr(limpeza, "limpar_contas", falso("limpar"))
    ctx = etapas.Contexto(admin=True, cadastros=None, alvos=(SID,))
    ctx._lista = Lista((aluno,), (), "NB")
    etapa = etapas.LimpezaUsuarios(ctx)
    lida = etapa.ler()
    assert lida.situacao == "pendente" and "6,0 MB em 1 conta" in lida.detalhe
    assert "Aluno01 6,0 MB" in etapa.mudancas() and "para sempre" in etapa.mudancas()
    assert etapa.aplicar(threading.Event()).estado == "ok"
    assert chamadas == [
        ("previa", [SID], ("desktop", "arquivos", "chrome")),
        ("limpar", [SID], ("desktop", "arquivos", "chrome")),
    ]


def test_limpeza_de_usuarios_sem_conta_marcada_bloqueia():
    ctx = etapas.Contexto(admin=True, cadastros=None)
    ctx._lista = Lista((), (), "NB")
    assert etapas.LimpezaUsuarios(ctx).ler().situacao == "bloqueada"


def test_categorias_da_manutencao_no_trecho():
    trecho = (limpeza.RECURSOS / "contas.ps1").read_text("utf-8")
    for cat in ("desktop", "arquivos", "chrome"):
        assert f"    {cat}" in trecho and cat in limpeza.NOMES_CATEGORIA
    assert "'.lnk', '.url'" in trecho and "$manterAtalhos" in trecho
    assert "'Music'" not in trecho.split("arquivos    =")[1].splitlines()[0]
    # a tela Limpeza continua com as quatro categorias dela
    assert [c for c, _ in limpeza.CATEGORIAS] == [
        "pessoais",
        "temporarios",
        "navegadores",
        "programas",
    ]


def test_limpar_contas_manda_as_categorias_pedidas():
    vistos = {}

    def rodar(script, **k):
        vistos.update(k)
        return Resultado(0, "[]", "", 0.0, False)

    aluno = Conta(SID, "Aluno01", True, False, "Local", False, None, r"C:\Users\Aluno01", False)
    limpeza.limpar_contas([aluno], set(), rodar=rodar, categorias=["chrome", "xx", "desktop"])
    assert vistos["categorias"] == "chrome,desktop"
    limpeza.previa_contas([aluno], set(), rodar=rodar)
    assert vistos["categorias"] == "pessoais,temporarios,navegadores,programas"


# ---------------------------------------------------------------- Steam (ADR-064)


def test_steam_so_aceita_o_desinstalador_da_pasta_padrao(monkeypatch, tmp_path):
    exe = tmp_path / "Steam" / "uninstall.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"x")
    monkeypatch.setattr(steam, "esperado", lambda: PureWindowsPath(exe))
    assert steam.desinstalador(lambda: f'"{exe}"') == str(exe)
    assert steam.desinstalador(lambda: r"C:\Outra\uninstall.exe") is None
    assert steam.desinstalador(lambda: "") is None
    assert not steam.instalada(lambda: "")


def test_steam_remove_e_espera_sair_do_registro(monkeypatch, tmp_path):
    exe = tmp_path / "uninstall.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(steam, "esperado", lambda: PureWindowsPath(exe))
    leituras = iter([str(exe), str(exe), str(exe), ""])
    chamadas = []

    def rodar(argv, **k):
        chamadas.append(argv)
        return Resultado(0, "", "", 0.0, False)

    ok, msg = steam.remover(ler=lambda: next(leituras), rodar=rodar, dormir=lambda s: None)
    assert ok and "removidos" in msg
    assert chamadas == [[str(exe), "/S"]]


def test_steam_que_nao_sai_a_tempo_falha(monkeypatch, tmp_path):
    exe = tmp_path / "uninstall.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(steam, "esperado", lambda: PureWindowsPath(exe))
    ok, msg = steam.remover(
        ler=lambda: str(exe),
        rodar=lambda *a, **k: Resultado(0, "", "", 0.0, False),
        dormir=lambda s: None,
        prazo=10,
    )
    assert not ok and "não saiu a tempo" in msg


def test_configuracao_continua_com_perfil(qtbot):
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None)
    qtbot.addWidget(p)
    assert not p.perfil.isHidden() and not p.painel_alunos.isHidden()
    assert p.perfil_atual() is None  # sem cadastro, sem perfil (ADR-060)


# -------------------------------------------------------- Wi-Fi por projeto e perfil (ADR-065)


def _cad_wifi():
    from dataclasses import replace

    from itc_bench.servicos.cadastros import Projeto, Unidade

    unidades = (
        Unidade(1, "ABC01", "ABC01", "", "", "", "", projeto="ABC"),
        Unidade(2, "ABC02", "ABC02", "", "", "", "", projeto="ABC"),
        Unidade(3, "XYZ01", "XYZ01", "", "", "", "", projeto=""),
    )
    redes = (
        replace(rede(1, "ABC02-Notebooks", unidade="ABC02"), projeto="ABC", perfis=("aluno",)),
        replace(rede(2, "ABC-Coordenacao", unidade="ABC01"), projeto="ABC", perfis=("pedagogo",)),
        replace(rede(3, "ABC-Geral", unidade="ABC01"), projeto="ABC"),
        rede(4, "XYZ01-Antiga", unidade="XYZ01"),
    )
    return Cadastros(
        "v" * 64,
        datetime.now(UTC),
        "t",
        None,
        False,
        (),
        (),
        redes,
        unidades,
        projetos=(Projeto(1, "ABC", "Abc"),),
    )


def test_redes_pelo_projeto_e_pelo_perfil():
    cad = _cad_wifi()
    ids = lambda rs: sorted(r.id for r in rs)  # noqa: E731
    assert ids(cad.redes_para("ABC01", "aluno")) == [1, 3]  # rede da ABC02 vale no projeto todo
    assert ids(cad.redes_para("ABC02", "pedagogo")) == [2, 3]
    assert ids(cad.redes_para("ABC01")) == [1, 2, 3]  # sem perfil (Manutenção): todas do projeto
    assert ids(cad.redes_para("XYZ01", "aluno")) == [4]  # rede antiga, sem projeto: pela unidade
    assert cad.redes_para(None, "aluno") == ()  # bancada: nenhuma
    assert "wifi" in etapas.ocultas(cad, None, "aluno")
    assert "wifi" not in etapas.ocultas(cad, "ABC01", "aluno")


def test_etapa_wifi_usa_o_perfil_e_a_manutencao_nao():
    cad = _cad_wifi()
    ctx = etapas.Contexto(admin=True, cadastros=cad, unidade="ABC01", perfil="pedagogo")
    assert sorted(r.id for r in etapas.Wifi(ctx)._redes()) == [2, 3]
    assert sorted(r.id for r in etapas.WifiSenhas(ctx)._redes()) == [1, 2, 3]


def test_cache_offline_guarda_as_redes_do_projeto(tmp_path):
    from itc_bench.servicos import api
    from itc_bench.servicos.cadastros import Armazem, sincronizar
    from itc_bench.servicos.executor import Sensivel

    corpo = {
        "versao": "v" * 64,
        "lido_em": "2026-11-17T12:00:00Z",
        "defasado": False,
        "unidade": None,
        "servidores": [],
        "instaladores": [],
        "descartados": {},
        "projetos": [],
        "perfis": [],
        "unidades": [
            {
                "id": 1,
                "codigo": "ABC01",
                "nome": "",
                "cidade": "",
                "uf": "",
                "tag_glpi": "",
                "perfil_padrao": "",
                "projeto": "ABC",
            },
        ],
        "wifi": [
            {
                "id": 1,
                "ssid": "P",
                "senha": "x" * 8,
                "unidade": "ABC02",
                "categoria": "",
                "atualizado_em": "",
                "projeto": "ABC",
                "perfis": [],
            },
            {
                "id": 2,
                "ssid": "Q",
                "senha": "x" * 8,
                "unidade": "XYZ01",
                "categoria": "",
                "atualizado_em": "",
                "projeto": "",
                "perfis": [],
            },
        ],
    }
    original = (api.saude, api.cadastros)
    try:
        api.saude = lambda base: True
        api.cadastros = lambda *a: corpo
        armazem = Armazem(tmp_path / "c.dpapi")
        sincronizar("b", Sensivel("t"), armazem, "t", None)
    finally:
        api.saude, api.cadastros = original
    filtrado = armazem.filtrar("ABC01")
    assert filtrado is not None and [r.id for r in filtrado.redes] == [1]


# ---------------------------------------------------------------- etapa Inicialização (ADR-080)


def _itens_ini():
    from itc_bench.servicos import inicializacao as ini

    one = ini.Item("runuser", "S-1-5-21-1-1", "Tarde", "OneDrive", "OneDrive.exe", True)
    tail = ini.Item("pasta", "MAQUINA", "", "Tailscale.lnk", "Tailscale.lnk", True)
    adobe = ini.Item("tarefa", "MAQUINA", "", r"\Adobe", "AdobeARM.exe", True)
    desl = ini.Item("run", "MAQUINA", "", "Riot Vanguard", "vgtray.exe", False)
    return ini, (one, tail, adobe, desl)


def test_etapa_inicializacao_le_so_sem_funcao_ligados_e_respeita_manter(monkeypatch):
    ini, itens = _itens_ini()
    monkeypatch.setattr(ini, "ler", lambda: ini.Leitura(itens, (), (), ()))
    ctx = etapas.Contexto(admin=True, cadastros=None, manter_inicializacao=frozenset({"Tailscale"}))
    e = etapas.Inicializacao(ctx)
    leitura = e.ler()
    assert leitura.situacao == "pendente" and leitura.detalhe.startswith("1 item(ns)")
    assert "OneDrive" in e.mudancas() and "encerrar as sessões" in e.mudancas()
    assert etapas.Inicializacao(etapas.Contexto(admin=False, cadastros=None)).ler().situacao == (
        "bloqueada"
    )


def test_etapa_inicializacao_encerra_outras_sessoes_antes_de_desligar(monkeypatch):

    ini, itens = _itens_ini()
    monkeypatch.setattr(ini, "ler", lambda: ini.Leitura(itens, (), (), ()))
    ordem = []

    def conta(sid, nome, bench=False):
        return contas.Conta(
            sid, nome, True, False, "Local", True, datetime.now(), "C:/x", True, bench
        )

    lista = contas.Lista((conta("S1", "Tarde"), conta("S2", "Suporte", bench=True)), (), "PC")
    monkeypatch.setattr(contas, "listar", lambda **_k: lista)
    monkeypatch.setattr(
        contas,
        "encerrar_sessoes",
        lambda sids: ordem.append(("encerrar", list(sids))) or contas.Feito(True, ""),
    )
    monkeypatch.setattr(
        ini,
        "desligar",
        lambda alvo: (
            ordem.append(("desligar", [i.titulo for i in alvo]))
            or [ini.Resultado(i, "") for i in alvo]
        ),
    )
    e = etapas.Inicializacao(etapas.Contexto(admin=True, cadastros=None))
    assert e.aplicar(threading.Event()).estado == "ok"
    assert ordem == [
        ("encerrar", ["S1"]),
        ("desligar", ["OneDrive", "Tailscale"]),
    ]  # não a do Bench


# ---------------------------------------------------------------- conta de administrador (ADR-081)


def _lista_sessoes(frente_admin=True):
    def conta(sid, nome, admin=False, logada=True, bench=False):
        return Conta(sid, nome, True, admin, "Local", logada, None, "C:/x", logada, bench)

    return Lista(
        (
            conta("S1", "Tarde"),
            conta("S2", "Manha", logada=False),
            conta("S3", "Suporte" if frente_admin else "Frente", admin=frente_admin),
            conta("S4", "Bench", admin=True, logada=False, bench=True),
        ),
        (),
        "PC",
    )


def test_encerrar_outras_sessoes_poupa_a_da_tela_e_a_do_bench(monkeypatch):
    from itc_bench.nucleo import sessoes

    monkeypatch.setattr(contas, "listar", lambda **_k: _lista_sessoes())
    monkeypatch.setattr(sessoes, "usuario_da_sessao", lambda sessao=None: "suporte")
    pedidos = []
    monkeypatch.setattr(
        contas,
        "encerrar_sessoes",
        lambda sids: pedidos.append(list(sids)) or contas.Feito(True, ""),
    )
    assert contas.encerrar_outras_sessoes() == 1 and pedidos == [["S1"]]
    monkeypatch.setattr(contas, "encerrar_sessoes", lambda sids: contas.Feito(False, "sessão 3"))
    with pytest.raises(RuntimeError, match="não deu para encerrar"):
        contas.encerrar_outras_sessoes()


def _manutencao(qtbot, monkeypatch, admin=True, frente_admin=True):
    from itc_bench.nucleo import sessoes
    from itc_bench.ui import tarefa

    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(contas, "listar", lambda **_k: _lista_sessoes(frente_admin))
    frente = "Suporte" if frente_admin else "Frente"
    monkeypatch.setattr(sessoes, "usuario_da_sessao", lambda sessao=None: frente)
    avisos = []
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_aviso", lambda self, t: avisos.append(t))
    p = ui_prep.PainelPreparacao(admin, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p)
    CARREGAR(p)
    return p, avisos


CARREGAR = ui_prep.PainelPreparacao._carregar_alunos


def test_manutencao_em_conta_comum_pede_administrador(qtbot, monkeypatch):
    p, avisos = _manutencao(qtbot, monkeypatch, frente_admin=False)
    assert p.bloqueio == "a conta Frente não é Suporte, Gestão nem Administrador"
    assert avisos and avisos[0].startswith(ui_prep.MSG_ADMIN)
    assert not p.b_rodar.isEnabled() and not p.b_ler.isEnabled() and not p.b_encerrar.isEnabled()


def test_manutencao_em_conta_administradora_libera(qtbot, monkeypatch):
    p, avisos = _manutencao(qtbot, monkeypatch)
    assert p.bloqueio == "" and not avisos and p.b_encerrar.isEnabled()
    assert "Tarde" in [p.alunos.item(i).text() for i in range(p.alunos.count())]  # logada entra


def test_confirmacao_da_manutencao_avisa_das_sessoes(qtbot, monkeypatch):
    p, _ = _manutencao(qtbot, monkeypatch)
    assert "encerra as sessões abertas das outras contas" in p.confirmacao(p._andamento_atual())


@pytest.mark.parametrize(
    ("nome", "sid", "ok"),
    [
        ("Suporte", "S-1-5-21-1-1001", True),
        ("Gestão", "S-1-5-21-1-1002", True),
        ("Administrador", "S-1-5-21-1-500", True),
        ("Professor", "S-1-5-21-1-1003", False),  # administradora, mas não é conta técnica
    ],
)
def test_so_suporte_gestao_e_administrador_sao_tecnicas(nome, sid, ok):
    c = Conta(sid, nome, True, True, "Local", True, None, "C:/x", True)
    assert contas.tecnica(c, None) is ok


def test_manutencao_em_outra_administradora_tambem_bloqueia(qtbot, monkeypatch):
    from itc_bench.nucleo import sessoes
    from itc_bench.ui import tarefa

    lista = Lista(
        (Conta("S9", "Professor", True, True, "Local", True, None, "C:/x", True),), (), "PC"
    )
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))
    monkeypatch.setattr(contas, "listar", lambda **_k: lista)
    monkeypatch.setattr(sessoes, "usuario_da_sessao", lambda sessao=None: "Professor")
    monkeypatch.setattr(ui_prep.PainelPreparacao, "_aviso", lambda self, t: None)
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p)
    CARREGAR(p)
    assert "Professor" in p.bloqueio and not p.b_rodar.isEnabled()
