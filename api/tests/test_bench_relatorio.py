"""POST /v1/bench/relatorio and GET /v1/bench/historico (ADR-016, TA-ADR-028): fake AI, temp DB."""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.config import Settings
from app.main import create_app
from app.routes import cadastros as rota_cadastros
from app.tokens import hash_token
from tests.test_relatorio import CONTENT, FakeGo, session

TOKEN = auth.SESSAO_PREFIX + "s" * 43
OUTRO = auth.SESSAO_PREFIX + "o" * 43
AUT = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_path=str(tmp_path / "tecnico.db"), opencode_go_api_key="sk-test")


@pytest.fixture
def go():
    return FakeGo()


def abrir_sessao(settings, token=TOKEN, usuario="tecnico.um", expira="2999-01-01T00:00:00Z"):
    db.migrate(settings.database_path)
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            conn.execute(
                "INSERT INTO bench_sessoes (token_hash, usuario, nome, glpi_id, maquina, ip, criada_em, expira_em)"
                " VALUES (?, ?, 'Tecnico', 1, 'TESTE-NB-01', '192.0.2.1', '2026-11-04T00:00:00Z', ?)",
                (hash_token(token), usuario, expira),
            )
    finally:
        conn.close()


@pytest.fixture
def cliente(settings, go, monkeypatch):
    abrir_sessao(settings)
    unidades = {"unidades": [{"codigo": "UM-01"}]}
    monkeypatch.setattr(rota_cadastros, "obter", lambda request: (unidades, "", False))
    app = create_app(settings, {"ia": httpx.MockTransport(go.handler)}, lambda f: f())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def linhas(settings):
    def consulta(sql, *params):
        conn = sqlite3.connect(settings.database_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    return consulta


def corpo(envio_id=None, unidade="UM-01"):
    entrada = session("1.1")
    entrada["sessao"] |= {"versaoSchema": "1.3", "origem": "bench", "coletadoPor": "marcador.tecnico"}
    entrada["sessao"].pop("usuarioLogado", None)
    entrada["modulos"]["eventlog"]["dados"]["grupos"] = [
        {"provedor": "Microsoft-Windows-Kernel-Power", "id": 41, "nivel": "critico", "ocorrencias": 3},
        {"provedor": "Microsoft-Windows-Perflib", "id": 1000, "nivel": "erro", "ocorrencias": 9, "exemploMensagem": "x"},
    ]
    return entrada | {"envio_id": envio_id or str(uuid.uuid4()), "unidade": unidade}


def test_envio_com_sessao_grava_auditoria_e_classifica(cliente, go, linhas):
    r = cliente.post("/v1/bench/relatorio", json=corpo(), headers=AUT)
    assert r.status_code == 200 and r.json()["relatorio_md"].startswith(CONTENT["relatorio_md"])
    linha = linhas(
        "SELECT carreta, token_id, bench_usuario, bench_sessao_id, unidade, processando_desde, versao_schema, dados"
        " FROM diagnosticos"
    )[0]
    assert linha[:7] == ("BANCADA", None, "tecnico.um", 1, "UM-01", None, "1.3")
    grupos = json.loads(linha[7])["modulos"]["eventlog"]["dados"]["grupos"]
    assert grupos[0]["conhecido"] is True and grupos[1]["conhecido"] is False  # Perflib != Application Error


def test_coletado_por_e_bench_usuario_fora_do_prompt(cliente, go):
    cliente.post("/v1/bench/relatorio", json=corpo(), headers=AUT)
    cliente.post("/v1/bench/relatorio", json=corpo(), headers=AUT)  # o segundo tem histórico no prompt
    for i in (0, 1):
        assert "marcador.tecnico" not in go.prompt(i) and "tecnico.um" not in go.prompt(i)


def test_unidade_fora_da_lista_fica_nula(cliente, linhas, caplog):
    cliente.post("/v1/bench/relatorio", json=corpo(unidade="UM-99"), headers=AUT)
    assert linhas("SELECT unidade FROM diagnosticos") == [(None,)]
    assert "UM-99" not in caplog.text


@pytest.mark.parametrize("envio", ["nao-e-uuid", "", "../x"])
def test_envio_id_invalido_422(cliente, envio):
    r = cliente.post("/v1/bench/relatorio", json=corpo() | {"envio_id": envio}, headers=AUT)
    assert r.status_code == 422 and r.json() == {"erro": "requisicao_invalida"}


def test_sem_sessao_ou_com_token_da_carreta_401(cliente, issue):
    assert cliente.post("/v1/bench/relatorio", json=corpo()).status_code == 401
    r = cliente.post("/v1/bench/relatorio", json=corpo(), headers={"Authorization": f"Bearer {issue()}"})
    assert r.status_code == 401
    assert cliente.get("/v1/bench/historico/TESTE-NB-11").status_code == 401


def test_sessao_expirada_401(settings, cliente):
    abrir_sessao(settings, OUTRO, expira="2000-01-01T00:00:00Z")
    r = cliente.post("/v1/bench/relatorio", json=corpo(), headers={"Authorization": f"Bearer {OUTRO}"})
    assert r.status_code == 401


def test_mesmo_envio_devolve_o_gravado_sem_nova_ia(cliente, go, linhas):
    envio = str(uuid.uuid4())
    primeiro = cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT).json()
    segundo = cliente.post("/v1/bench/relatorio", json=corpo(envio.upper()), headers=AUT).json()
    assert primeiro == segundo and len(go.requests) == 1
    assert linhas("SELECT count(*) FROM diagnosticos") == [(1,)]
    assert linhas("SELECT count(*) FROM relatorios") == [(1,)]


def test_ia_falha_e_reenvio_tenta_na_mesma_linha(cliente, go, linhas):
    envio = str(uuid.uuid4())
    go.reply = lambda request: httpx.Response(500)
    r = cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT)
    assert (r.status_code, r.json()) == (503, {"erro": "ia_indisponivel"})
    assert linhas("SELECT falha, processando_desde FROM diagnosticos") == [("ia_indisponivel", None)]
    go.reply = FakeGo().reply
    r = cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT)
    assert r.status_code == 200 and r.json()["diagnostico_id"] == 1
    assert linhas("SELECT id, falha FROM diagnosticos") == [(1, None)]
    assert "Sem diagnósticos anteriores" in go.prompt()  # a própria linha não entra no histórico


def test_reenvio_concorrente_409_sem_segunda_ia(cliente, go, linhas):
    envio = str(uuid.uuid4())
    na_ia, liberar = threading.Event(), threading.Event()
    resposta = go.reply

    def lenta(request):
        na_ia.set()
        liberar.wait(10)
        return resposta(request)

    go.reply = lenta
    resultados = {}
    primeiro = threading.Thread(
        target=lambda: resultados.update(a=cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT))
    )
    primeiro.start()
    assert na_ia.wait(10)
    segundo = cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT)
    liberar.set()
    primeiro.join(10)
    assert (segundo.status_code, segundo.json()) == (409, {"erro": "em_processamento"})
    assert resultados["a"].status_code == 200
    assert len(go.requests) == 1
    assert linhas("SELECT count(*) FROM diagnosticos") == [(1,)]


def test_processando_antigo_e_falha_presumida(cliente, go, linhas, settings):
    envio = str(uuid.uuid4())
    go.reply = lambda request: httpx.Response(500)
    cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT)
    antigo = auth.iso(auth.utcnow() - timedelta(seconds=121))
    conn = db.connect(settings.database_path)
    conn.execute("UPDATE diagnosticos SET processando_desde = ?, falha = NULL", (antigo,))
    conn.close()
    go.reply = FakeGo().reply
    assert cliente.post("/v1/bench/relatorio", json=corpo(envio), headers=AUT).status_code == 200


def test_limite_por_tecnico_e_nao_por_sessao(settings, go, monkeypatch, linhas):
    abrir_sessao(settings)
    abrir_sessao(settings, OUTRO)  # mesmo técnico, outra sessão
    monkeypatch.setattr(rota_cadastros, "obter", lambda request: ({"unidades": []}, "", False))
    s = settings.model_copy(update={"bench_relatorio_limite_hora": 2})
    with TestClient(create_app(s, {"ia": httpx.MockTransport(go.handler)}, lambda f: f())) as c:
        assert c.post("/v1/bench/relatorio", json=corpo(), headers=AUT).status_code == 200
        assert c.post("/v1/bench/relatorio", json=corpo(), headers={"Authorization": f"Bearer {OUTRO}"}).status_code == 200
        r = c.post("/v1/bench/relatorio", json=corpo(), headers=AUT)
    assert r.status_code == 429 and r.json() == {"erro": "limite_excedido"} and int(r.headers["Retry-After"]) > 0


def test_historico_bench_traz_laudo_e_quem_enviou(cliente, issue):
    cliente.post("/v1/bench/relatorio", json=corpo(), headers=AUT)
    r = cliente.get("/v1/bench/historico/teste-nb-11", headers=AUT)
    item = r.json()["diagnosticos"][0]
    assert r.json()["hostname"] == "TESTE-NB-11"
    assert item["bench_usuario"] == "tecnico.um" and item["unidade"] == "UM-01" and item["carreta"] == "BANCADA"
    assert item["relatorio"]["relatorio_md"].startswith(CONTENT["relatorio_md"])
    # A rota da carreta continua sem os campos novos.
    carreta = cliente.get("/v1/historico/TESTE-NB-11", headers={"Authorization": f"Bearer {issue()}"}).json()
    assert "bench_usuario" not in carreta["diagnosticos"][0]
    assert "relatorio_md" not in carreta["diagnosticos"][0]["relatorio"]


@pytest.mark.parametrize("caminho", ["/v1/bench/historico/../x", "/v1/bench/historico/a%20b", "/v1/benchx/relatorio"])
def test_caminhos_vizinhos(cliente, caminho):
    assert cliente.get(caminho, headers=AUT).status_code in (404, 405, 422)


def test_corpo_e_sessao_fora_do_log_e_do_sqlite(cliente, settings, caplog):
    caplog.set_level(logging.DEBUG)
    entrada = corpo()
    entrada["modulos"]["disco"]["dados"]["avisos"] = ["marcador-de-corpo"]
    cliente.post("/v1/bench/relatorio", json=entrada, headers=AUT)
    assert "marcador-de-corpo" not in caplog.text and TOKEN not in caplog.text
    bruto = open(settings.database_path, "rb").read()
    assert TOKEN.encode() not in bruto
