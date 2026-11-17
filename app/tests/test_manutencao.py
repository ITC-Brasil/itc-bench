"""Configuração e Manutenção (ADR-062): ordem das etapas, energia, Wi-Fi da manutenção e tela."""

import threading
from datetime import UTC, datetime
from pathlib import PureWindowsPath

from test_wifi import Falso, rede

from itc_bench.servicos import energia, etapas, limpeza, perfis, steam, wifi
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
    )
    assert [n for n, _, _ in perfis.MANUTENCAO.etapas] == [1, 2, 3, 4]
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
    assert textos == ["1. Limpeza de usuários", "2. Wi-Fi: atualizar senhas", "3. Diagnóstico"]
    assert "steam" in p.desmarcadas()  # escondida não roda
    assert p.perfil.isHidden() and not p.painel_alunos.isHidden()
    assert p.b_ler.isEnabled()
    assert ajuda.TEXTOS["manut"] == ui_prep.AJUDA_MANUTENCAO

    monkeypatch.setattr(steam, "instalada", lambda ler=None: True)
    p2 = ui_prep.PainelPreparacao(True, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p2)
    p2.show()
    ultimo = p2.lista.topLevelItem(p2.lista.topLevelItemCount() - 1).text(0)
    assert ultimo == "4. Remover Steam"


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
