import json
from pathlib import Path

import pytest

from app import normalizacao

FIXTURES = Path(__file__).parent / "fixtures"


def load(version):
    return json.loads((FIXTURES / f"sessao-{version}.json").read_text("utf-8"))


@pytest.fixture
def v10():
    return normalizacao.normalizar(load("1.0"))


@pytest.fixture
def v11():
    return normalizacao.normalizar(load("1.1"))


def disco(result):
    return result[0]["modulos"]["disco"]["dados"]


def test_1_0_cleanup_summary_is_recalculated_from_items(v10):
    assert disco(v10)["resumo"] == {
        "recuperavelSeguroBytes": 400,
        "itensSeguroComConteudo": 2,
        "revisarBytes": 700,
        "itensRevisar": 1,
    }


def test_1_0_lists_are_sorted_by_bytes(v10):
    assert [i["id"] for i in disco(v10)["itensLimpeza"]] == ["e", "b", "c", "a", "d"]
    assert [p["caminho"] for p in disco(v10)["maioresPastasPerfil"]] == ["p2", "p1"]


def test_1_0_smart_fields_are_renamed_and_derived(v10):
    nvme, usb = disco(v10)["discosFisicos"]

    assert nvme["percentualDesgaste"] == 3
    assert "percentualVidaRestante" not in nvme and "smartDisponivel" not in nvme
    assert nvme["estadoSmart"] == "parcial"
    assert nvme["observacao"].startswith("Contadores não expostos pelo driver: errosLeituraNaoCorrigidos")
    # 0 °C from a USB driver is "not reported"; with every counter null, SMART is unavailable.
    assert usb["temperaturaC"] is None and usb["temperaturaMaximaC"] is None
    assert usb["estadoSmart"] == "indisponivel"


def test_1_0_events_are_reclassified_by_exact_provider_and_id(v10):
    eventlog = v10[0]["modulos"]["eventlog"]["dados"]
    grupos = {(g["provedor"], g["id"]): g for g in eventlog["grupos"]}

    perflib = grupos[("Microsoft-Windows-Perflib", 1000)]
    assert perflib["conhecido"] is False and perflib["descricao"] is None and perflib["apelido"] is None
    kernel_power = grupos[("Microsoft-Windows-Kernel-Power", 41)]
    assert kernel_power["conhecido"] is True and kernel_power["peso"] == "alto" and kernel_power["exemploMensagem"] is None
    volmgr = grupos[("volmgr", 162)]
    # The current base replaces the Phase 1 text: neutral, no action, not official.
    assert volmgr["fonteOficial"] is False and volmgr["acaoSugerida"] is None
    assert volmgr["descricao"] != "descricao antiga da Fase 1"
    assert eventlog["gruposDesconhecidos"] == 1
    # Critical first, then by occurrences within the level.
    assert [(g["provedor"], g["ocorrencias"]) for g in eventlog["grupos"]] == [
        ("Microsoft-Windows-Kernel-Power", 3),
        ("Application Error", 70),
        ("Microsoft-Windows-Perflib", 40),
        ("volmgr", 2),
    ]


def test_1_0_apipa_only_on_connected_adapters(v10):
    adaptadores = v10[0]["modulos"]["rede"]["dados"]["adaptadores"]
    assert [a["apipa"] for a in adaptadores] == [False, True, False]


def test_1_0_session_fields_and_notices(v10):
    sessao, avisos = v10[0]["sessao"], v10[1]

    assert sessao["hostname"] == "TESTE-NB-10"
    assert sessao["ultimaAtualizacao"] == "2026-09-05T14:51:00.123456-03:00"
    assert avisos == [normalizacao.AVISO_PENDRIVE_1_0, normalizacao.AVISO_EVENTOS_1_0]


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_usuario_logado_becomes_the_executing_account(version):
    sessao = normalizacao.normalizar(load(version))[0]["sessao"]

    assert "usuarioLogado" not in sessao
    assert sessao["usuarioExecucao"] in ("aluno01", "tecnico.admin")
    assert sessao["usuarioSessao"] is None


def test_1_1_is_kept_except_for_the_documented_rules(v11):
    raw = load("1.1")
    normalized, avisos = v11

    assert avisos == []
    assert normalized["modulos"]["eventlog"] == raw["modulos"]["eventlog"]
    assert "desconhecido" not in normalized["modulos"]
    assert normalized["sessao"]["campoDeVersaoFutura"] == "ignorado"
    assert disco(v11)["resumo"] == raw["modulos"]["disco"]["dados"]["resumo"]


def test_wear_0_without_power_on_hours_is_not_reported(v11):
    (nvme,) = disco(v11)["discosFisicos"]

    assert nvme["percentualDesgaste"] is None
    assert nvme["observacao"].endswith("percentualDesgaste 0 com horasLigado nulo: tratado como não informado.")


def test_input_is_not_modified():
    raw = load("1.0")
    before = json.dumps(raw, sort_keys=True)
    normalizacao.normalizar(raw)
    assert json.dumps(raw, sort_keys=True) == before


def test_module_in_error_has_no_data_and_does_not_break(v10):
    assert v10[0]["modulos"]["bateria"]["dados"] is None
    assert normalizacao.resumir(v10[0])["bateriaDesgastePercentual"] is None


def test_summary_for_history(v11):
    assert normalizacao.resumir(v11[0]) == {
        "volumes": [{"letra": "C", "percentualLivre": 8.0}],
        "discos": [{"modelo": "SSSTC CL4-4D256-Q62", "estadoSmart": "parcial", "percentualDesgaste": None, "temperaturaC": 43}],
        "eventosPesoAlto": [],
        "totalGruposEventos": 3,
        "bateriaDesgastePercentual": None,
        "memoriaPercentualEmUso": None,
        "internetOk": None,
    }


def test_api_base_has_the_pendrive_entries():
    assert ("volmgr", 162) in normalizacao.BASE_EVENTOS
    assert ("microsoft-windows-hal", 21) not in normalizacao.BASE_EVENTOS
    assert len(normalizacao.BASE_EVENTOS) == 17


USUARIO_SESSAO = r"TESTE-NB-11\aluno01"


def v12():
    body = load("1.1")
    sessao = body["sessao"]
    sessao["versaoSchema"] = "1.2"
    sessao["usuarioExecucao"] = sessao.pop("usuarioLogado")
    sessao["usuarioSessao"] = USUARIO_SESSAO
    return body


def test_1_2_keeps_both_user_fields():
    sessao = normalizacao.normalizar(v12())[0]["sessao"]
    assert (sessao["usuarioExecucao"], sessao["usuarioSessao"]) == ("tecnico.admin", USUARIO_SESSAO)
    assert "usuarioLogado" not in sessao
