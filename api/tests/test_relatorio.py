import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import normalizacao, tokens
from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
CONTENT = {
    "relatorio_md": "## Resumo\nC: com 8% livre.",
    "chamado_titulo": "Disco C: quase cheio",
    "chamado_descricao": "Volume C: com 8% livre.",
    "maior_confianca": "ALTA",
}


def session(version):
    return json.loads((FIXTURES / f"sessao-{version}.json").read_text("utf-8"))


class FakeGo:
    """httpx transport standing in for OpenCode Go; never reaches the network."""

    def __init__(self):
        self.requests = []
        self.reply = lambda request: httpx.Response(
            200,
            json={
                "model": "mimo-v2.6-flash",
                "choices": [{"message": {"content": json.dumps(CONTENT)}}],
                "usage": {"prompt_tokens": 9800, "completion_tokens": 950},
            },
        )

    def handler(self, request):
        self.requests.append(request)
        return self.reply(request)

    def prompt(self, index=-1):
        return json.loads(self.requests[index].content)["messages"][1]["content"]


@pytest.fixture
def go():
    return FakeGo()


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_path=str(tmp_path / "tecnico.db"), opencode_go_api_key="sk-test")


@pytest.fixture
def client(settings, go):
    with TestClient(create_app(settings, {"ia": httpx.MockTransport(go.handler)}, lambda funcao: funcao())) as client:
        yield client


@pytest.fixture
def auth(issue):
    return {"Authorization": f"Bearer {issue()}"}


@pytest.fixture
def rows(settings):
    def query(sql, *params):
        conn = sqlite3.connect(settings.database_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    return query


def test_report_for_a_1_1_session(client, go, auth, rows):
    response = client.post("/v1/relatorio", json=session("1.1"), headers=auth)

    assert response.status_code == 200
    assert response.json() == {
        **CONTENT,
        "modelo": "mimo-v2.6-flash",
        "tokens_entrada": 9800,
        "tokens_saida": 950,
        "diagnostico_id": 1,
    }
    assert go.requests[0].headers["x-opencode-session"] == "2026-09-28_1510_TESTE-NB-11"
    assert "tecnico.admin" not in go.prompt()
    assert rows("SELECT carreta, token_id, hostname, sessao_id, projeto, sub_perfil, versao_schema, falha FROM diagnosticos") == [
        ("UM-03", 1, "TESTE-NB-11", "2026-09-28_1510_TESTE-NB-11", "BSBIA", "aluno", "1.1", None)
    ]
    assert rows("SELECT diagnostico_id, modelo, tokens_entrada, tokens_saida, maior_confianca, chamado_titulo, espelho_status FROM relatorios") == [
        (1, "mimo-v2.6-flash", 9800, 950, "ALTA", "Disco C: quase cheio", "pendente")
    ]


def test_1_0_session_is_normalized_and_notices_reach_the_report(client, auth, rows):
    response = client.post("/v1/relatorio", json=session("1.0"), headers=auth)

    assert response.status_code == 200
    report = response.json()["relatorio_md"]
    assert report.startswith(CONTENT["relatorio_md"])
    assert report.endswith(f"## Avisos da coleta\n\n- {normalizacao.AVISO_PENDRIVE_1_0}\n- {normalizacao.AVISO_EVENTOS_1_0}")
    ((hostname, dados),) = rows("SELECT hostname, dados FROM diagnosticos")
    stored = json.loads(dados)
    assert hostname == "TESTE-NB-10"
    assert stored["sessao"]["usuarioExecucao"] == "aluno01" and "usuarioLogado" not in stored["sessao"]
    assert stored["modulos"]["disco"]["dados"]["resumo"]["recuperavelSeguroBytes"] == 400
    assert rows("SELECT relatorio_md FROM relatorios") == [(report,)]


def test_history_goes_into_the_prompt_and_the_route(client, go, auth):
    first = session("1.1")
    second = session("1.1")
    second["sessao"]["id"] = "2026-09-29_0900_TESTE-NB-11"
    client.post("/v1/relatorio", json=first, headers=auth)
    client.post("/v1/relatorio", json=second, headers=auth)

    assert "Sem diagnósticos anteriores" in go.prompt(0)
    history = go.prompt(1).split("## Histórico do hostname")[1]
    assert '"sessao_id":"2026-09-28_1510_TESTE-NB-11"' in history
    assert "2026-09-29_0900" not in history

    response = client.get("/v1/historico/teste-nb-11", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["hostname"] == "TESTE-NB-11"
    assert [d["sessao_id"] for d in body["diagnosticos"]] == ["2026-09-29_0900_TESTE-NB-11", "2026-09-28_1510_TESTE-NB-11"]
    assert body["diagnosticos"][0]["relatorio"] == {"maior_confianca": "ALTA", "chamado_titulo": "Disco C: quase cheio", "modelo": "mimo-v2.6-flash"}
    assert body["diagnosticos"][0]["resumo"]["volumes"] == [{"letra": "C", "percentualLivre": 8.0}]
    assert "dados" not in body["diagnosticos"][0]


def timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    "reply, status, code",
    [
        (timeout, 503, "ia_timeout"),
        (lambda r: httpx.Response(429), 503, "ia_cota"),
        (lambda r: httpx.Response(400), 502, "ia_recusa"),
        (lambda r: httpx.Response(401), 502, "ia_autenticacao"),
    ],
)
def test_go_failure_answers_fast_and_keeps_the_diagnostico(client, go, auth, rows, reply, status, code):
    go.reply = reply
    response = client.post("/v1/relatorio", json=session("1.1"), headers=auth)

    assert response.status_code == status
    assert response.json() == {"erro": code}
    assert rows("SELECT falha FROM diagnosticos") == [(code,)]
    assert rows("SELECT count(*) FROM relatorios") == [(0,)]
    history = client.get("/v1/historico/TESTE-NB-11", headers=auth).json()["diagnosticos"]
    assert history[0]["falha"] == code and history[0]["relatorio"] is None


def test_without_a_key_the_go_is_not_called(client, go, auth, settings):
    settings.opencode_go_api_key = SecretStr("changeme")
    response = client.post("/v1/relatorio", json=session("1.1"), headers=auth)

    assert (response.status_code, response.json()) == (503, {"erro": "ia_nao_configurada"})
    assert go.requests == []


def test_without_token_nothing_is_stored_nor_sent(client, go, rows):
    assert client.post("/v1/relatorio", json=session("1.1")).status_code == 401
    assert client.get("/v1/historico/TESTE-NB-11").status_code == 401
    assert go.requests == []
    assert rows("SELECT count(*) FROM diagnosticos") == [(0,)]


def test_revoked_token_is_refused_on_both_routes(client, auth, settings):
    assert client.get("/v1/historico/TESTE-NB-11", headers=auth).status_code == 200
    tokens.main(["revoke", "--carreta", "UM-03", "--motivo", "teste", "--operador", "teste"], settings)

    assert client.get("/v1/historico/TESTE-NB-11", headers=auth).status_code == 401
    assert client.post("/v1/relatorio", json=session("1.1"), headers=auth).status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["sessao"].update(versaoSchema="2.0"),
        lambda s: s["sessao"].pop("hostname"),
        lambda s: s["sessao"].update(hostname="../etc"),
        lambda s: s["sessao"].update(id=""),
        lambda s: s.update(modulos=[]),
        lambda s: s.pop("sessao"),
    ],
)
def test_invalid_body_is_422_without_echo(client, go, auth, rows, change):
    body = session("1.1")
    change(body)
    response = client.post("/v1/relatorio", json=body, headers=auth)

    assert (response.status_code, response.json()) == (422, {"erro": "requisicao_invalida"})
    assert go.requests == []
    assert rows("SELECT count(*) FROM diagnosticos") == [(0,)]


def test_modules_are_optional(client, auth):
    body = session("1.1")
    body.pop("modulos")
    assert client.post("/v1/relatorio", json=body, headers=auth).status_code == 200


def test_invalid_hostname_in_history_is_422(client, auth):
    assert client.get("/v1/historico/" + "A" * 64, headers=auth).status_code == 422
    assert client.get("/v1/historico/-X", headers=auth).status_code == 422


def test_1_2_session_is_accepted(client, auth, rows):
    from test_normalizacao import v12

    assert client.post("/v1/relatorio", json=v12(), headers=auth).status_code == 200
    assert rows("SELECT versao_schema FROM diagnosticos") == [("1.2",)]
