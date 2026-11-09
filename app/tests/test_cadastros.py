"""Cache dos cadastros (ADR-014) com DPAPI real e a API simulada por monkeypatch."""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from itc_bench.nucleo import dpapi
from itc_bench.servicos import api, cadastros
from itc_bench.servicos.cadastros import Armazem, sincronizar
from itc_bench.servicos.executor import Sensivel

# Marcadores fictícios, sem parecer valores reais: nunca podem aparecer no log ou na tela.
SENHA_WIFI = "Marcador-SenhaWifi-4Hq"
CHAVE = "Marcador-ChaveServidor-2Lp"
OBS = "Marcador-Observacao-8Tv"
TOKEN = Sensivel("itcbs_" + "a" * 43)
AGORA = datetime(2026, 11, 4, 14, 10, tzinfo=UTC)


def corpo(versao="v" * 64, unidade=None, defasado=False):
    wifi = [
        {
            "id": 10,
            "ssid": "Rede-Ficticia-A",
            "senha": SENHA_WIFI,
            "unidade": "UM-01",
            "categoria": "Carreta",
            "atualizado_em": "",
        },
        {
            "id": 11,
            "ssid": "Rede-Ficticia-B",
            "senha": SENHA_WIFI,
            "unidade": "UM-02",
            "categoria": "Carreta",
            "atualizado_em": "",
        },
    ]
    return {
        "versao": versao,
        "lido_em": "2026-11-04T14:00:00Z",
        "defasado": defasado,
        "unidade": unidade,
        "servidores": [
            {
                "id": 1,
                "servico": "RustDesk",
                "papel": "servidor de ID",
                "valor": "id.exemplo.invalid",
                "versao": "",
                "observacao": "publica",
                "publico": True,
            },
            {
                "id": 2,
                "servico": "RustDesk",
                "papel": "chave pública",
                "valor": CHAVE,
                "versao": "",
                "observacao": OBS,
                "publico": False,
            },
        ],
        "instaladores": [
            {
                "id": 1,
                "programa": "Exemplo",
                "versao": "1",
                "arquivo": "a.msi",
                "sha256": "ab" * 32,
                "link": "https://exemplo.invalid/a.msi",
                "observacao": "",
            }
        ],
        "wifi": [w for w in wifi if unidade is None or w["unidade"] == unidade],
        "unidades": [
            {
                "id": 1,
                "codigo": "UM-01",
                "nome": "Unidade Um",
                "cidade": "",
                "uf": "",
                "tag_glpi": "",
                "perfil_padrao": "",
            },
            {
                "id": 2,
                "codigo": "UM-02",
                "nome": "Unidade Dois",
                "cidade": "",
                "uf": "",
                "tag_glpi": "",
                "perfil_padrao": "",
            },
        ],
        "descartados": {"wifi": [12]},
    }


class Relogio:
    def __init__(self):
        self.agora = AGORA

    def __call__(self):
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def armazem(tmp_path, relogio):
    return Armazem(tmp_path / "cadastros.dpapi", relogio)


@pytest.fixture
def chamadas(monkeypatch):
    """api.cadastros simulado: cada item da fila é um corpo, None (304) ou uma exceção."""
    fila: list = []
    feitas: list = []

    def falso(base, token, versao, unidade):
        feitas.append((versao, unidade))
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(api, "cadastros", falso)
    return fila, feitas


def test_sincronizacao_online_grava_cifrado(armazem, chamadas):
    fila, feitas = chamadas
    fila.append(corpo())
    r = sincronizar("https://api.exemplo.invalid", TOKEN, armazem, "ana", None)
    assert r.estado == "ok" and feitas == [(None, None)]
    c = r.cadastros
    assert len(c.redes) == 2 and c.por == "ana" and c.descartados == {"wifi": [12]}
    assert isinstance(c.redes[0].senha, Sensivel) and c.redes[0].senha.revelar() == SENHA_WIFI
    publico, secreto = c.servidores
    assert publico.valor == "id.exemplo.invalid" and publico.observacao == "publica"
    assert isinstance(secreto.valor, Sensivel) and isinstance(secreto.observacao, Sensivel)
    assert c.servidor("RustDesk", "chave pública") is secreto
    bruto = armazem.arquivo.read_bytes()
    assert SENHA_WIFI.encode() not in bruto and b"Rede-Ficticia" not in bruto  # cifrado
    registro = json.loads(dpapi.decifrar(bruto))
    assert registro["formato"] == 1 and registro["por"] == "ana"
    assert not armazem.arquivo.with_suffix(".tmp").exists()


def test_304_renova_a_validade(armazem, chamadas, relogio):
    fila, feitas = chamadas
    fila += [corpo(), None]
    sincronizar("b", TOKEN, armazem, "ana", None)
    relogio.agora += timedelta(days=6)
    r = sincronizar("b", TOKEN, armazem, "bia", None)
    assert r.estado == "igual" and feitas[1] == ("v" * 64, None)
    assert r.cadastros.sincronizado_em == relogio.agora and r.cadastros.por == "bia"


@pytest.mark.parametrize(
    "erro", [api.SemConexao("x"), api.CadastrosIndisponivel("cadastros_indisponivel")]
)
def test_offline_mantem_o_cache(armazem, chamadas, erro):
    fila, _ = chamadas
    fila += [corpo(), erro]
    sincronizar("b", TOKEN, armazem, "ana", None)
    r = sincronizar("b", TOKEN, armazem, "ana", None)
    estado = "sem_central" if isinstance(erro, api.CadastrosIndisponivel) else "offline"
    assert r.estado == estado and r.cadastros is not None and len(r.cadastros.redes) == 2
    assert armazem.arquivo.exists()


def test_401_pede_login_e_nao_apaga(armazem, chamadas):
    fila, _ = chamadas
    fila += [corpo(), api.Recusado(401, "nao_autorizado")]
    sincronizar("b", TOKEN, armazem, "ana", None)
    r = sincronizar("b", TOKEN, armazem, "ana", None)
    assert r.estado == "sessao" and armazem.carregar() is not None


def test_resposta_fora_do_formato_mantem_o_cache(armazem, chamadas):
    fila, _ = chamadas
    fila += [corpo(), {"versao": "x", "servidores": "nao e lista"}]
    sincronizar("b", TOKEN, armazem, "ana", None)
    r = sincronizar("b", TOKEN, armazem, "ana", None)
    assert r.estado == "erro" and len(armazem.carregar().redes) == 2


def test_cache_vencido_e_apagado(armazem, chamadas, relogio):
    chamadas[0].append(corpo())
    sincronizar("b", TOKEN, armazem, "ana", None)
    relogio.agora += timedelta(days=7, seconds=1)
    assert armazem.carregar() is None and armazem.aviso == "vencido"
    assert not armazem.arquivo.exists()


def test_relogio_voltado_vence(armazem, chamadas, relogio):
    chamadas[0].append(corpo())
    sincronizar("b", TOKEN, armazem, "ana", None)
    relogio.agora -= timedelta(minutes=6)
    assert armazem.carregar() is None and armazem.aviso == "vencido"


@pytest.mark.parametrize(
    "bruto",
    [
        b"lixo que nao e dpapi",
        dpapi.cifrar(b"nao e json"),
        dpapi.cifrar(b"[1, 2]"),
        dpapi.cifrar(json.dumps({"formato": 99}).encode()),
        dpapi.cifrar(json.dumps({"formato": 1, "versao": "x"}).encode()),
    ],
)
def test_cache_corrompido_e_apagado(armazem, bruto, caplog):
    armazem.arquivo.write_bytes(bruto)
    assert armazem.carregar() is None and armazem.aviso == "corrompido"
    assert not armazem.arquivo.exists()
    assert "corrompido" in caplog.text


def test_sem_admin_so_em_memoria(tmp_path, chamadas, relogio):
    armazem = Armazem(None, relogio)
    chamadas[0].append(corpo())
    assert sincronizar("b", TOKEN, armazem, "ana", None).estado == "ok"
    assert armazem.carregar() is not None
    assert list(tmp_path.iterdir()) == []


def test_unidade_filtra_na_api_e_versao_nao_se_mistura(armazem, chamadas):
    fila, feitas = chamadas
    fila += [corpo(), corpo(versao="u" * 64, unidade="UM-01")]
    sincronizar("b", TOKEN, armazem, "ana", None)
    r = sincronizar("b", TOKEN, armazem, "ana", "UM-01")
    # versão do cache era de "todas": não vai no If-None-Match da unidade
    assert feitas[1] == (None, "UM-01")
    assert r.cadastros.unidade == "UM-01" and [w.id for w in r.cadastros.redes] == [10]


def test_troca_de_unidade_offline_filtra_e_regrava(armazem, chamadas):
    chamadas[0].append(corpo())
    sincronizar("b", TOKEN, armazem, "ana", None)
    c = armazem.filtrar("UM-02")
    assert c is not None and [w.id for w in c.redes] == [11] and c.unidade == "UM-02"
    relido = armazem.carregar()
    assert [w.id for w in relido.redes] == [11] and relido.versao == ""
    registro = json.loads(dpapi.decifrar(armazem.arquivo.read_bytes()))
    assert [w["id"] for w in registro["dados"]["wifi"]] == [11]


def test_segredos_fora_do_log_e_do_repr(armazem, chamadas, caplog):
    caplog.set_level(logging.DEBUG)
    chamadas[0].append(corpo())
    r = sincronizar("b", TOKEN, armazem, "ana", None)
    texto = caplog.text + repr(r.cadastros)
    for marcador in (SENHA_WIFI, CHAVE, OBS, "v" * 64):
        assert marcador not in texto
    assert "Rede-Ficticia" not in caplog.text  # SSID: visível na tela, nunca no log
    assert "v" * 12 in caplog.text  # só a versão curta


def test_rotulo(armazem, chamadas, relogio):
    chamadas[0].append(corpo())
    c = sincronizar("b", TOKEN, armazem, "ana", None).cadastros
    hora = c.sincronizado_em.astimezone().strftime("%H:%M")
    assert cadastros.rotulo(None, False) == "sem cadastros"
    assert cadastros.rotulo(c, False, AGORA) == f"sincronizado {hora}"
    assert cadastros.rotulo(c, True, AGORA).startswith("offline · dados de ")
    outro_dia = cadastros.rotulo(c, False, AGORA + timedelta(days=2))
    assert outro_dia == f"sincronizado {c.sincronizado_em.astimezone():%d/%m %H:%M}"


def test_unidade_trocada_e_api_fora_filtra_o_cache(armazem, chamadas):
    fila, _ = chamadas
    fila += [corpo(), api.SemConexao("x")]
    sincronizar("b", TOKEN, armazem, "ana", None)
    r = sincronizar("b", TOKEN, armazem, "ana", "UM-01")
    assert r.estado == "offline" and r.cadastros.unidade == "UM-01"
    assert [w.id for w in armazem.carregar().redes] == [10]


def test_instalador_de_cache_antigo_vira_tipo_instalador() -> None:
    """Cache gravado antes do ADR-020 não tem os campos novos."""
    from itc_bench.servicos.cadastros import _de_dados

    antigo = {"id": 1, "programa": "P", "versao": "1", "arquivo": "p.msi", "sha256": "a" * 64}
    antigo |= {"link": "https://exemplo.invalid/p.msi", "observacao": ""}
    registro = {
        "versao": "v" * 64,
        "sincronizado_em": "2026-11-06T10:00:00+00:00",
        "por": "teste",
        "unidade": None,
        "dados": {"servidores": [], "instaladores": [antigo], "wifi": [], "unidades": []},
    }
    i = _de_dados(registro).instaladores[0]
    assert (i.tipo, i.categoria, i.modo, i.identificador) == (
        "instalador",
        "Programas",
        "quiosque",
        "",
    )
