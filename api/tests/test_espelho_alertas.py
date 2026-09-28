import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main, tokens
from app.config import Settings
from app.main import create_app
from app.services import nocodb, ntfy

FIXTURES = Path(__file__).parent / "fixtures"
CONTENT = {"relatorio_md": "## Resumo\nok", "chamado_titulo": "Título", "chamado_descricao": "d", "maior_confianca": "BAIXA"}


def session(sessao_id="2026-09-28_1510_TESTE-NB-11"):
    body = json.loads((FIXTURES / "sessao-1.1.json").read_text("utf-8"))
    body["sessao"]["id"] = sessao_id
    return body


class Fake:
    """httpx transport that records requests and answers with self.reply."""

    def __init__(self, reply):
        self.requests, self.reply = [], reply

    def handler(self, request):
        self.requests.append(request)
        return self.reply(request)

    def bodies(self):
        return [json.loads(r.content) for r in self.requests]


def go_ok(request):
    return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": json.dumps(CONTENT)}}]})


def down(request):
    raise httpx.ConnectError("down", request=request)


def slow(request):
    raise httpx.ReadTimeout("slow", request=request)


@pytest.fixture
def services():
    return {
        "ia": Fake(go_ok),
        "nocodb": Fake(lambda r: httpx.Response(200, json=[{"Id": 1}])),
        "ntfy": Fake(lambda r: httpx.Response(200, json={"id": "x"})),
    }


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "tecnico.db"),
        opencode_go_api_key="sk-test",
        nocodb_enabled=True,
        nocodb_url="https://nocodb.test/",
        nocodb_token="nc-test",
        nocodb_table_id="mtabela",
        ntfy_enabled=True,
        ntfy_url="https://ntfy.test",
        ntfy_topic="itc-infra",
        ntfy_token="tk-test",
        ntfy_failure_threshold_per_hour=3,
    )


@pytest.fixture
def client(settings, services):
    transports = {name: httpx.MockTransport(fake.handler) for name, fake in services.items()}
    with TestClient(create_app(settings, transports, lambda funcao: funcao())) as client:
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


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = datetime(2026, 9, 28, 14, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(ntfy, "utcnow", lambda: Clock.now)
    return Clock


def test_report_is_mirrored_with_the_documented_fields(client, services, auth, rows):
    assert client.post("/v1/relatorio", json=session(), headers=auth).status_code == 200

    (request,) = services["nocodb"].requests
    assert str(request.url) == "https://nocodb.test/api/v2/tables/mtabela/records"
    assert request.headers["xc-token"] == "nc-test"
    ((record,),) = services["nocodb"].bodies()
    assert record["DiagnosticoId"] == 1 and record["Carreta"] == "UM-03" and record["Hostname"] == "TESTE-NB-11"
    assert (record["Projeto"], record["SubPerfil"], record["Modelo"], record["MaiorConfianca"]) == ("BSBIA", "aluno", "m", "BAIXA")
    assert record["ChamadoTitulo"] == "Título" and record["Relatorio"] == "## Resumo\nok"
    assert record["Data"].endswith("+00:00")
    assert rows("SELECT espelho_status, espelho_tentativas, espelho_erro FROM relatorios") == [("ok", 1, None)]


@pytest.mark.parametrize("reply, code", [(down, "indisponivel"), (lambda r: httpx.Response(500), "http_500")])
def test_nocodb_down_does_not_affect_the_response_and_is_resent(client, services, auth, rows, settings, reply, code):
    services["nocodb"].reply = reply
    response = client.post("/v1/relatorio", json=session(), headers=auth)

    assert response.status_code == 200 and response.json()["chamado_titulo"] == "Título"
    assert rows("SELECT espelho_status, espelho_tentativas, espelho_erro FROM relatorios") == [("pendente", 1, code)]

    services["nocodb"].reply = lambda r: httpx.Response(200, json=[{"Id": 1}])
    assert nocodb.espelhar_pendentes(settings, httpx.MockTransport(services["nocodb"].handler)) == 1
    assert rows("SELECT espelho_status, espelho_tentativas, espelho_erro FROM relatorios") == [("ok", 2, None)]
    # Once ok, a report is not sent again.
    assert nocodb.espelhar_pendentes(settings, httpx.MockTransport(services["nocodb"].handler)) == 0


def test_nocodb_down_stops_the_batch_at_the_first_failure(client, services, auth, rows, settings):
    services["nocodb"].reply = down
    for n in range(3):
        client.post("/v1/relatorio", json=session(f"s{n}"), headers=auth)
    services["nocodb"].requests.clear()

    nocodb.espelhar_pendentes(settings, httpx.MockTransport(services["nocodb"].handler))

    assert len(services["nocodb"].requests) == 1


def test_mirror_disabled_sends_nothing_and_keeps_pending(tmp_path, services, issue, rows, settings):
    settings.nocodb_enabled = False
    transports = {name: httpx.MockTransport(fake.handler) for name, fake in services.items()}
    with TestClient(create_app(settings, transports, lambda funcao: funcao())) as client:
        assert client.post("/v1/relatorio", json=session(), headers={"Authorization": f"Bearer {issue()}"}).status_code == 200

    assert services["nocodb"].requests == []
    assert rows("SELECT espelho_status FROM relatorios") == [("pendente",)]


def test_quota_storm_sends_one_alert_then_reports_the_suppressed(client, services, auth, rows, clock):
    services["ia"].reply = lambda r: httpx.Response(429)
    for n in range(10):
        assert client.post("/v1/relatorio", json=session(f"s{n}"), headers=auth).status_code == 503

    titles = [b["title"] for b in services["ntfy"].bodies()]
    # One quota alert and one rate alert (threshold 3), not 10 + 8.
    assert titles == ["OpenCode Go recusou por cota", "Falhas da IA acima do limiar"]
    assert rows("SELECT chave, suprimidos FROM alertas ORDER BY chave") == [("ia:ia_cota", 9), ("ia:taxa", 7)]

    clock.now += timedelta(minutes=61)
    client.post("/v1/relatorio", json=session("s10"), headers=auth)
    last = services["ntfy"].bodies()[2]
    assert last["title"] == "OpenCode Go recusou por cota"
    assert last["message"].endswith("(9 alertas iguais suprimidos desde o último envio.)")
    assert last["topic"] == "itc-infra" and last["priority"] == 4
    assert services["ntfy"].requests[0].headers["authorization"] == "Bearer tk-test"


def test_auth_failure_of_the_go_alerts_and_timeout_does_not(client, services, auth):
    services["ia"].reply = lambda r: httpx.Response(401)
    client.post("/v1/relatorio", json=session(), headers=auth)
    services["ia"].reply = slow
    client.post("/v1/relatorio", json=session("s2"), headers=auth)

    assert [b["title"] for b in services["ntfy"].bodies()] == ["OpenCode Go recusou a chave"]


def test_revoked_token_alerts_once_and_unknown_token_does_not(client, services, auth, settings):
    tokens.main(["revoke", "--carreta", "UM-03", "--motivo", "perdido", "--operador", "teste"], settings)
    for _ in range(3):
        assert client.get("/v1/historico/TESTE-NB-11", headers=auth).status_code == 401
    unknown = {"Authorization": "Bearer itcta_" + "A" * 43}
    assert client.get("/v1/historico/TESTE-NB-11", headers=unknown).status_code == 401

    bodies = services["ntfy"].bodies()
    assert [b["title"] for b in bodies] == ["Token revogado em uso (UM-03)"]


def test_ntfy_down_does_not_affect_the_response(client, services, auth):
    services["ia"].reply = lambda r: httpx.Response(429)
    services["ntfy"].reply = down
    response = client.post("/v1/relatorio", json=session(), headers=auth)
    assert (response.status_code, response.json()) == (503, {"erro": "ia_cota"})


@pytest.mark.parametrize("token", ["", "changeme"])
def test_placeholder_tokens_disable_the_services(settings, token):
    settings.nocodb_token = settings.ntfy_token = SecretStr(token)
    assert not nocodb.configurado(settings) and not ntfy.configurado(settings)


def test_retry_loop_resends_pending_without_new_reports(client, services, auth, rows, monkeypatch):
    services["nocodb"].reply = down
    client.post("/v1/relatorio", json=session(), headers=auth)
    services["nocodb"].reply = lambda r: httpx.Response(200, json=[{"Id": 1}])
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
        if len(waits) > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.repetir_espelho(client.app))

    assert waits == [300, 300]
    assert rows("SELECT espelho_status FROM relatorios") == [("ok",)]
