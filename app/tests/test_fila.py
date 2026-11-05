"""Fila de diagnósticos (ADR-015): DPAPI real, arquivo temporário, API falsa."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from itc_bench.nucleo import dpapi
from itc_bench.servicos import api, fila
from itc_bench.servicos.executor import Sensivel

AGORA = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def corpo(n: int) -> dict:
    return {
        "envio_id": f"{n:08d}-0000-4000-8000-000000000000",
        "sessao": {"hostname": "TESTE-NB-01", "x": "marcador-fila"},
    }


@pytest.fixture
def relogio():
    return {"agora": AGORA}


@pytest.fixture
def f(tmp_path, relogio):
    return fila.Fila(tmp_path / fila.NOME, lambda: relogio["agora"])


def test_guarda_cifrado_e_le(f, tmp_path):
    f.guardar(corpo(1), "tecnico.um")
    bruto = (tmp_path / fila.NOME).read_bytes()
    assert b"marcador-fila" not in bruto
    assert json.loads(dpapi.decifrar(bruto))["formato"] == 1
    [item] = f.itens()
    assert (item.coletado_por, item.hostname, item.corpo) == ("tecnico.um", "TESTE-NB-01", corpo(1))
    assert not (tmp_path / "fila-diagnostico.tmp").exists()


def test_mesmo_envio_nao_duplica(f):
    f.guardar(corpo(1), "a")
    f.guardar(corpo(1), "b")
    assert [i.coletado_por for i in f.itens()] == ["b"]


def test_limite_de_itens_tira_o_mais_antigo(f, caplog):
    for n in range(12):
        f.guardar(corpo(n), "t")
    assert [i.envio_id[:8] for i in f.itens()] == [f"{n:08d}" for n in range(2, 12)]
    assert "marcador-fila" not in caplog.text


def test_item_com_mais_de_14_dias_sai(f, relogio):
    f.guardar(corpo(1), "t")
    relogio["agora"] = AGORA + timedelta(days=14, seconds=1)
    assert f.itens() == [] and f.aviso == "descartados 1"


def test_corrompida_vira_prova_e_fila_recomeca(f, tmp_path):
    (tmp_path / fila.NOME).write_bytes(b"lixo")
    assert f.itens() == [] and f.aviso == "corrompida"
    assert (tmp_path / "fila-diagnostico.corrompida").read_bytes() == b"lixo"
    f.guardar(corpo(1), "t")
    assert len(f.itens()) == 1


def test_formato_desconhecido_e_corrompido(f, tmp_path):
    (tmp_path / fila.NOME).write_bytes(
        dpapi.cifrar(json.dumps({"formato": 9, "itens": []}).encode())
    )
    assert f.itens() == [] and f.aviso == "corrompida"


def test_sem_admin_so_em_memoria(tmp_path):
    m = fila.Fila(None)
    m.guardar(corpo(1), "t")
    assert len(m.itens()) == 1 and list(tmp_path.iterdir()) == []


def _api(monkeypatch, respostas):
    vistos = []

    def relatorio(base, token, c):
        vistos.append(c["envio_id"][:8])
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return {
            "diagnostico_id": 1,
            "relatorio_md": "",
            "chamado_titulo": "",
            "chamado_descricao": "",
            "modelo": "",
        }

    monkeypatch.setattr(api, "relatorio", relatorio)
    return vistos


def test_reenvio_um_por_vez_e_para_sem_conexao(f, monkeypatch):
    for n in range(3):
        f.guardar(corpo(n), "t")
    vistos = _api(monkeypatch, [None, api.SemConexao("x")])
    r = fila.reenviar(f, "https://x.exemplo.invalid", Sensivel("t"))
    assert (r.enviados, r.pendentes, r.sessao_expirada) == (1, 2, False)
    assert vistos == ["00000000", "00000001"]


def test_reenvio_ia_fora_e_422_saem_429_fica(f, monkeypatch):
    for n in range(3):
        f.guardar(corpo(n), "t")
    _api(
        monkeypatch,
        [
            api.IaFalhou("ia_timeout"),
            api.Recusado(422, "requisicao_invalida"),
            api.Recusado(429, "limite_excedido"),
        ],
    )
    r = fila.reenviar(f, "https://x.exemplo.invalid", Sensivel("t"))
    assert (r.enviados, r.pendentes) == (2, 1)


def test_reenvio_401_para_e_avisa(f, monkeypatch):
    f.guardar(corpo(1), "t")
    _api(monkeypatch, [api.Recusado(401, "nao_autorizado")])
    r = fila.reenviar(f, "https://x.exemplo.invalid", Sensivel("t"))
    assert r.sessao_expirada and r.pendentes == 1
