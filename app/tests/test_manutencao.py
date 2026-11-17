"""Configuração e Manutenção (ADR-062): ordem das etapas, energia, Wi-Fi da manutenção e tela."""

import threading
from datetime import UTC, datetime

from test_wifi import Falso, rede

from itc_bench.servicos import energia, etapas, perfis, wifi
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import ajuda
from itc_bench.ui import preparacao as ui_prep


class ClienteFalso(Falso):
    def __enter__(self) -> "ClienteFalso":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _cadastros(*redes) -> Cadastros:
    return Cadastros("v" * 64, datetime.now(UTC), "t", "ABC01", False, (), (), redes, ())


# ---------------------------------------------------------------- listas e energia


def test_configuracao_e_manutencao_montam_na_ordem_dos_numeros():
    ctx = etapas.Contexto(admin=False, cadastros=None)
    assert tuple(e.id for e in etapas.montar(ctx)) == perfis.CONFIGURACAO.ordem
    assert tuple(e.id for e in etapas.montar_manutencao(ctx)) == ("wifi_senhas", "diagnostico")
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


def test_tela_de_manutencao_sem_perfil_nem_contas_de_aluno(qtbot):
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None, manutencao=True)
    qtbot.addWidget(p)
    p.show()
    textos = [p.lista.topLevelItem(i).text(0) for i in range(p.lista.topLevelItemCount())]
    assert textos == ["2. Wi-Fi: atualizar senhas", "3. Diagnóstico"]
    assert p.perfil.isHidden() and p.painel_alunos.isHidden()
    assert p.perfil_atual() is not None and p.ocultas() == frozenset()
    assert p.b_ler.isEnabled()
    assert ajuda.TEXTOS["manut"] == ui_prep.AJUDA_MANUTENCAO


def test_configuracao_continua_com_perfil(qtbot):
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None)
    qtbot.addWidget(p)
    assert not p.perfil.isHidden() and not p.painel_alunos.isHidden()
    assert p.perfil_atual() is None  # sem cadastro, sem perfil (ADR-060)
