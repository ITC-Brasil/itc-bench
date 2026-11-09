"""GET /v1/bench/cadastros (ADR-014) against a fake NocoDB: no real NocoDB or network."""

import logging
import socket
import sqlite3
import threading
import time
from datetime import timedelta

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import auth, db
from app.config import Settings
from app.main import create_app
from app.routes import cadastros as rota
from app.services import nocodb_cadastros
from app.tokens import hash_token

# Fictitious markers, nothing like real values: they must never reach a log or the database.
MARCADOR_NOCODB = "marcador-nocodb-fixo"
MARCADOR_WIFI = "marcador-wifi-um"
MARCADOR_SERVIDOR = "marcador-servidor-um"
MARCADOR_OBS = "marcador-obs-um"
SESSAO = auth.SESSAO_PREFIX + "s" * 43

TABELAS = {"servidores": "mSrv", "instaladores": "mIns", "wifi": "mWif", "unidades": "mUni"}


def linhas():
    return {
        "mSrv": [
            {"Id": 1, "Servico": "RustDesk", "Papel": "servidor de ID", "Valor": "id.exemplo.invalid", "Ativo": True, "Publico": True, "Observacao": "publica"},
            {"Id": 2, "Servico": "RustDesk", "Papel": "chave pública", "Valor": MARCADOR_SERVIDOR, "Ativo": True, "Observacao": MARCADOR_OBS},
            {"Id": 3, "Servico": "AnyDesk", "Papel": "senha", "Valor": "inativo", "Ativo": False},
            {"Id": 4, "Servico": "", "Papel": "relay", "Valor": "x", "Ativo": True},
        ],
        "mIns": [
            {"Id": 1, "Programa": "Exemplo", "Versao": "1.0", "Arquivo": "exemplo.msi", "SHA256": "AB" * 32, "Link": "https://exemplo.invalid/a.msi", "Ativo": True},
        ],
        "mWif": [
            {"Id": 10, "SSID": "Rede-Ficticia-A", "Senha": MARCADOR_WIFI, "Unidade": "UM-01", "Categoria": "Carreta", "Ativo": True},
            {"Id": 11, "SSID": "Rede-Ficticia-B", "Senha": MARCADOR_WIFI, "Unidade": "UM-02", "Categoria": "Carreta", "Ativo": True},
            {"Id": 12, "SSID": "Rede-Ficticia-C", "Senha": MARCADOR_WIFI, "Unidade": "UM-99", "Categoria": "Carreta", "Ativo": True},
            {"Id": 13, "SSID": "Rede-Ficticia-D", "Senha": MARCADOR_WIFI, "Unidade": "UM-03", "Categoria": "Carreta", "Ativo": True},
        ],
        "mUni": [
            {"Id": 1, "Codigo": "UM-01", "Nome": "Unidade Um", "Ativo": True},
            {"Id": 2, "Codigo": "UM-02", "Nome": "Unidade Dois", "Ativo": True},
            {"Id": 3, "Codigo": "UM-03", "Nome": "Unidade Tres", "Ativo": False},
        ],
    }


class FakeNocodb:
    def __init__(self, falha=None, atraso=0.0):
        self.dados, self.falha, self.atraso = linhas(), falha, atraso
        self.chamadas = 0
        self.liberar = threading.Event()
        self.liberar.set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.chamadas += 1
        self.liberar.wait(5)
        if self.atraso:
            time.sleep(self.atraso)
        if self.falha == "rede":
            raise httpx.ConnectError("recusado", request=request)
        if self.falha == "timeout":
            raise httpx.ReadTimeout("lento", request=request)
        if self.falha == "401":
            # A NocoDB that echoes the token must not get it into a log or an error.
            return httpx.Response(401, json={"msg": f"token {request.headers['xc-token']} invalido"})
        if self.falha == "html":
            return httpx.Response(200, text="<html>proxy</html>")
        assert request.headers["xc-token"] == MARCADOR_NOCODB
        tabela = request.url.path.split("/")[-2]
        campos = request.url.params["fields"].split(",")
        offset, limite = int(request.url.params["offset"]), int(request.url.params["limit"])
        todas = [{k: v for k, v in linha.items() if k in campos} for linha in self.dados[tabela]]
        pagina = todas[offset : offset + limite]
        return httpx.Response(200, json={"list": pagina, "pageInfo": {"isLastPage": offset + limite >= len(todas)}})


def configurar(settings, **extra):
    valores = dict(
        nocodb_url="https://nocodb.exemplo.invalid/",
        nocodb_cadastros_token=MARCADOR_NOCODB,
        nocodb_tabela_servidores=TABELAS["servidores"],
        nocodb_tabela_instaladores=TABELAS["instaladores"],
        nocodb_tabela_wifi=TABELAS["wifi"],
        nocodb_tabela_unidades=TABELAS["unidades"],
        bench_cadastros_etag_key="chave-etag-teste",
    )
    valores.update(extra)
    return Settings(_env_file=None, database_path=settings.database_path, **valores)


def criar_sessao(settings, token=SESSAO, horas=12):
    db.migrate(settings.database_path)
    agora = auth.utcnow()
    conn = db.connect(settings.database_path)
    try:
        with db.immediate(conn):
            conn.execute(
                "INSERT INTO bench_sessoes (token_hash, usuario, nome, glpi_id, maquina, ip, criada_em, expira_em)"
                " VALUES (?, 'tecnico', 'Ana Lima', 7, 'NB-TESTE-01', '127.0.0.1', ?, ?)",
                (hash_token(token), auth.iso(agora), auth.iso(agora + timedelta(hours=horas))),
            )
    finally:
        conn.close()


AUT = {"Authorization": f"Bearer {SESSAO}"}


@pytest.fixture
def fake():
    return FakeNocodb()


@pytest.fixture
def app_(settings, fake):
    s = configurar(settings)
    criar_sessao(s)
    return create_app(s, transports={"nocodb_cadastros": httpx.MockTransport(fake.handler)})


@pytest.fixture
def cliente(app_):
    with TestClient(app_) as c:
        yield c


def test_sem_sessao_401(cliente, fake):
    assert cliente.get("/v1/bench/cadastros").status_code == 401
    r = cliente.get("/v1/bench/cadastros", headers={"Authorization": "Bearer " + auth.SESSAO_PREFIX + "x" * 43})
    assert r.status_code == 401 and r.json() == {"erro": "nao_autorizado"}
    assert fake.chamadas == 0


def test_token_de_carreta_nao_vale(cliente, issue):
    assert cliente.get("/v1/bench/cadastros", headers={"Authorization": f"Bearer {issue()}"}).status_code == 401


def test_200_conteudo_e_filtros(cliente):
    r = cliente.get("/v1/bench/cadastros", headers=AUT)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    corpo = r.json()
    assert r.headers["etag"] == f'"{corpo["versao"]}"'
    assert corpo["defasado"] is False and corpo["unidade"] is None
    srv = {s["id"]: s for s in corpo["servidores"]}
    assert set(srv) == {1, 2}  # 3 inactive, 4 without Servico
    assert srv[1]["publico"] is True and srv[2]["publico"] is False  # missing Publico = secret
    assert srv[2]["valor"] == MARCADOR_SERVIDOR  # the Bench needs it offline
    assert [w["id"] for w in corpo["wifi"]] == [10, 11]  # 12 unknown unit, 13 inactive unit
    assert [u["codigo"] for u in corpo["unidades"]] == ["UM-01", "UM-02"]
    assert corpo["instaladores"][0]["sha256"] == "ab" * 32
    assert corpo["descartados"] == {"servidores": [4], "wifi": [12, 13]}


def test_filtro_por_unidade(cliente):
    todos = cliente.get("/v1/bench/cadastros", headers=AUT).json()
    r = cliente.get("/v1/bench/cadastros?unidade=UM-02", headers=AUT)
    corpo = r.json()
    assert corpo["unidade"] == "UM-02"
    assert [w["id"] for w in corpo["wifi"]] == [11]
    assert len(corpo["servidores"]) == 2 and len(corpo["unidades"]) == 2  # global
    assert corpo["versao"] != todos["versao"]


@pytest.mark.parametrize("codigo", ["UM-99", "UM-03", "um-01"])
def test_unidade_invalida_422(cliente, codigo):
    r = cliente.get(f"/v1/bench/cadastros?unidade={codigo}", headers=AUT)
    assert r.status_code == 422 and r.json() == {"erro": "unidade_invalida"}


def test_unidade_longa_422_generico(cliente):
    r = cliente.get("/v1/bench/cadastros?unidade=" + "U" * 40, headers=AUT)
    assert r.status_code == 422 and r.json() == {"erro": "requisicao_invalida"}


def test_304_com_versao_igual_e_exige_sessao(cliente, settings):
    primeira = cliente.get("/v1/bench/cadastros", headers=AUT)
    etag = primeira.headers["etag"]
    r = cliente.get("/v1/bench/cadastros", headers={**AUT, "If-None-Match": etag})
    assert r.status_code == 304 and r.content == b"" and r.headers["etag"] == etag
    assert cliente.get("/v1/bench/cadastros", headers={**AUT, "If-None-Match": f"W/{etag}, \"outro\""}).status_code == 304
    assert cliente.get("/v1/bench/cadastros", headers={**AUT, "If-None-Match": '"outra"'}).status_code == 200
    assert cliente.get("/v1/bench/cadastros", headers={"If-None-Match": etag}).status_code == 401
    conn = sqlite3.connect(settings.database_path)
    linhas_ = conn.execute("SELECT usuario, unidade, versao FROM bench_cadastros_entregas").fetchall()
    conn.close()
    # one row per 200 (two), none per 304; only 12 characters of the version
    assert linhas_ == [("tecnico", None, primeira.json()["versao"][:12])] * 2


def test_versao_nao_e_sha256_do_conteudo(settings, fake):
    """HMAC with the server key: a fixed key gives the same version across processes, a random
    key does not, and neither equals a plain SHA-256 of the content."""
    import hashlib

    versoes = []
    for chave in ("chave-etag-teste", "chave-etag-teste", ""):
        s = configurar(settings, bench_cadastros_etag_key=chave)
        criar_sessao(s, token=auth.SESSAO_PREFIX + str(len(versoes)) * 43)
        app = create_app(s, transports={"nocodb_cadastros": httpx.MockTransport(fake.handler)})
        with TestClient(app) as c:
            r = c.get("/v1/bench/cadastros", headers={"Authorization": "Bearer " + auth.SESSAO_PREFIX + str(len(versoes)) * 43})
            versoes.append(r.json()["versao"])
            assert hashlib.sha256(r.content).hexdigest() != versoes[-1]
    assert versoes[0] == versoes[1] != versoes[2]


def test_nao_configurado_503(settings):
    criar_sessao(settings)
    with TestClient(create_app(settings)) as c:
        r = c.get("/v1/bench/cadastros", headers=AUT)
    assert r.status_code == 503 and r.json() == {"erro": "cadastros_indisponivel"}


@pytest.mark.parametrize("falha", ["rede", "timeout", "401", "html"])
def test_nocodb_fora_sem_copia_503_e_sessao_intacta(settings, falha, caplog):
    caplog.set_level(logging.DEBUG)
    s = configurar(settings)
    criar_sessao(s)
    fake = FakeNocodb(falha=falha)
    with TestClient(create_app(s, transports={"nocodb_cadastros": httpx.MockTransport(fake.handler)})) as c:
        r = c.get("/v1/bench/cadastros", headers=AUT)
        assert r.status_code == 503 and r.json() == {"erro": "cadastros_indisponivel"}
        # 503 cadastros_indisponivel does not touch the session
        assert c.get("/v1/bench/sessao", headers=AUT).status_code == 200
        # within the TTL a failed read is not repeated
        chamadas = fake.chamadas
        assert c.get("/v1/bench/cadastros", headers=AUT).status_code == 503
        assert fake.chamadas == chamadas
    assert MARCADOR_NOCODB not in caplog.text


def test_nocodb_lento_respeita_timeout(settings):
    s = configurar(settings, nocodb_cadastros_timeout_seconds=0.2)
    criar_sessao(s)

    def lento(request):
        raise httpx.ReadTimeout("lento", request=request)

    with TestClient(create_app(s, transports={"nocodb_cadastros": httpx.MockTransport(lento)})) as c:
        assert c.get("/v1/bench/cadastros", headers=AUT).status_code == 503


def test_teto_total_da_leitura(settings, monkeypatch):
    monkeypatch.setattr(nocodb_cadastros, "TETO_SEGUNDOS", 0.05)
    s = configurar(settings)
    fake = FakeNocodb(atraso=0.03)
    with pytest.raises(nocodb_cadastros.NocodbIndisponivel) as erro:
        nocodb_cadastros.ler(s, httpx.MockTransport(fake.handler))
    assert erro.value.code.endswith(":timeout")
    assert MARCADOR_NOCODB not in str(erro.value)


def test_erro_do_nocodb_sem_token(settings):
    fake = FakeNocodb(falha="401")
    with pytest.raises(nocodb_cadastros.NocodbIndisponivel) as erro:
        nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    assert erro.value.code == "servidores:http_401" and MARCADOR_NOCODB not in repr(erro.value)


def test_paginacao(settings):
    fake = FakeNocodb()
    fake.dados["mWif"] = [
        {"Id": i, "SSID": f"Rede-{i}", "Senha": "x", "Unidade": "UM-01", "Ativo": True} for i in range(2500)
    ]
    dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    assert len(dados["wifi"]) == 2500


def test_copia_defasada_quando_nocodb_cai(app_, fake):
    with TestClient(app_) as c:
        assert c.get("/v1/bench/cadastros", headers=AUT).json()["defasado"] is False
        fake.falha = "rede"
        app_.state.cadastros.tentado -= 3600  # TTL over
        corpo = c.get("/v1/bench/cadastros", headers=AUT).json()
        assert corpo["defasado"] is True and len(corpo["wifi"]) == 2
        app_.state.cadastros.lido_mono -= rota.DEFASAGEM_MAXIMA + 1
        assert c.get("/v1/bench/cadastros", headers=AUT).status_code == 503
        fake.falha = None
        app_.state.cadastros.tentado -= 3600
        assert c.get("/v1/bench/cadastros", headers=AUT).json()["defasado"] is False


def test_ttl_evita_nova_leitura(cliente, fake):
    cliente.get("/v1/bench/cadastros", headers=AUT)
    chamadas = fake.chamadas
    cliente.get("/v1/bench/cadastros", headers=AUT)
    cliente.get("/v1/bench/cadastros?unidade=UM-01", headers=AUT)
    assert fake.chamadas == chamadas == 4  # one request per table


def _em_paralelo(c, n=2):
    respostas = []

    def pedir():
        respostas.append(c.get("/v1/bench/cadastros", headers=AUT))

    threads = [threading.Thread(target=pedir) for _ in range(n)]
    for t in threads:
        t.start()
    return threads, respostas


def test_uma_leitura_por_vez_sem_copia(app_, fake):
    """No copy yet: both wait, but NocoDB is read once."""
    fake.liberar.clear()
    with TestClient(app_) as c:
        threads, respostas = _em_paralelo(c)
        time.sleep(0.3)
        fake.liberar.set()
        for t in threads:
            t.join(10)
    assert [r.status_code for r in respostas] == [200, 200]
    assert fake.chamadas == 4


def test_uma_leitura_por_vez_com_copia(app_, fake):
    """Copy expired and NocoDB slow: one request renews, the other gets the copy at once."""
    with TestClient(app_) as c:
        c.get("/v1/bench/cadastros", headers=AUT)
        app_.state.cadastros.tentado -= 3600
        fake.liberar.clear()
        lenta = threading.Thread(target=lambda: c.get("/v1/bench/cadastros", headers=AUT))
        lenta.start()
        time.sleep(0.3)  # the first request holds the lock, waiting on NocoDB
        inicio = time.monotonic()
        r = c.get("/v1/bench/cadastros", headers=AUT)
        assert r.status_code == 200 and time.monotonic() - inicio < 2
        fake.liberar.set()
        lenta.join(10)
    assert fake.chamadas == 8  # first read + one renewal


def test_segredos_fora_do_log_e_do_sqlite(app_, settings, caplog):
    caplog.set_level(logging.DEBUG)
    with TestClient(app_) as c:
        etag = c.get("/v1/bench/cadastros", headers=AUT).headers["etag"].strip('"')
        c.get("/v1/bench/cadastros?unidade=UM-01", headers=AUT)
    texto_log = caplog.text
    for marcador in (MARCADOR_WIFI, MARCADOR_SERVIDOR, MARCADOR_OBS, MARCADOR_NOCODB, "Rede-Ficticia", etag):
        assert marcador not in texto_log
    bruto = b"".join(p.read_bytes() for p in __import__("pathlib").Path(settings.database_path).parent.glob("tecnico.db*"))
    for marcador in (MARCADOR_WIFI, MARCADOR_SERVIDOR, MARCADOR_OBS, MARCADOR_NOCODB, "Rede-Ficticia", etag):
        assert marcador.encode() not in bruto


def test_segredos_sao_secretstr_ate_a_resposta(settings, fake):
    dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    texto = repr(dados)
    assert MARCADOR_WIFI not in texto and MARCADOR_SERVIDOR not in texto and MARCADOR_OBS not in texto
    assert "publica" in texto  # Publico = true: plain


def test_log_de_acesso_do_uvicorn_sem_corpo_nem_etag(app_, caplog):
    """The real uvicorn access log: method, path and status only; no body, no If-None-Match."""
    caplog.set_level(logging.INFO, logger="uvicorn.access")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(app_, host="127.0.0.1", port=porta, log_config=None, access_log=True))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if servidor.started:
                break
            time.sleep(0.05)
        base = f"http://127.0.0.1:{porta}"
        etag = httpx.get(base + "/v1/bench/cadastros", headers=AUT).headers["etag"]
        r = httpx.get(base + "/v1/bench/cadastros", headers={**AUT, "If-None-Match": etag})
        assert r.status_code == 304
    finally:
        servidor.should_exit = True
        thread.join(10)
    acesso = "\n".join(r.getMessage() for r in caplog.records if r.name == "uvicorn.access")
    assert "/v1/bench/cadastros" in acesso and "304" in acesso
    for marcador in (etag.strip('"'), MARCADOR_WIFI, MARCADOR_SERVIDOR, SESSAO):
        assert marcador not in acesso


def test_sha256_invalido_vira_vazio(settings, fake):
    fake.dados["mIns"].append({"Id": 2, "Programa": "Outro", "SHA256": "<b>nao-hex</b>", "Ativo": True})
    dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    assert [i["sha256"] for i in dados["instaladores"]] == ["ab" * 32, ""]


def test_instaladores_por_tipo(settings, fake, caplog):
    """TA-ADR-029: defaults for empty Tipo/Categoria/Modo; invalid rows dropped by Id only."""
    url = "https://exemplo.invalid/jogo?x=1"
    fake.dados["mIns"] += [
        {"Id": 2, "Programa": "Pacote", "Tipo": "winget", "Identificador": "Exemplo.Pacote", "Ativo": True},
        {"Id": 3, "Programa": "Jogo", "Tipo": "webapp", "Categoria": "Jogos", "Modo": "app", "Identificador": url, "Ativo": True},
        {"Id": 4, "Programa": "X", "Tipo": "outro", "Ativo": True},
        {"Id": 5, "Programa": "X", "Categoria": "Outra", "Ativo": True},
        {"Id": 6, "Programa": "X", "Tipo": "webapp", "Modo": "tela", "Identificador": url, "Ativo": True},
        {"Id": 7, "Programa": "X", "Tipo": "winget", "Identificador": "id com espaço", "Ativo": True},
        {"Id": 8, "Programa": "X", "Tipo": "webapp", "Identificador": "http://exemplo.invalid", "Ativo": True},
        {"Id": 9, "Programa": "X", "Tipo": "webapp", "Identificador": 'https://exemplo.invalid/"a', "Ativo": True},
    ]
    with caplog.at_level("WARNING", logger="tecnico.cadastros"):
        dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    por_id = {i["id"]: i for i in dados["instaladores"]}
    assert set(por_id) == {1, 2, 3}
    assert (por_id[1]["tipo"], por_id[1]["categoria"], por_id[1]["modo"]) == ("instalador", "Programas", "quiosque")
    assert por_id[2]["identificador"] == "Exemplo.Pacote"
    assert (por_id[3]["categoria"], por_id[3]["modo"]) == ("Jogos", "app")
    assert dados["descartados"]["instaladores"] == [4, 5, 6, 7, 8, 9]
    texto_log = caplog.text
    assert "tipo_invalido" in texto_log and "modo_invalido" in texto_log
    assert url not in texto_log and "id com espaço" not in texto_log


def test_papel_de_parede(settings, fake, caplog):
    """TA-ADR-030/034: papel needs .jpg/.jpeg/.png and an https Link; SHA256 optional but valid."""
    sha = "a" * 64
    base = {"Programa": "Papel", "Tipo": "papel", "Ativo": True}
    link = "https://exemplo.invalid/papel.jpg"
    fake.dados["mIns"] += [
        {**base, "Id": 2, "Arquivo": "papel.JPG", "SHA256": sha.upper(), "Link": link},
        {**base, "Id": 3, "Arquivo": "papel.png", "SHA256": sha, "Link": link},
        {**base, "Id": 4, "Arquivo": "papel.gif", "SHA256": sha, "Link": link},
        {**base, "Id": 5, "Arquivo": "papel.jpg", "SHA256": "", "Link": link},
        {**base, "Id": 6, "Arquivo": "papel.jpg", "SHA256": sha, "Link": "http://exemplo.invalid/p.jpg"},
        {**base, "Id": 7, "Arquivo": "pasta\\papel.jpg", "SHA256": sha, "Link": link},
        {**base, "Id": 8, "Arquivo": "papel.jpg", "SHA256": "nao-hex", "Link": link},
    ]
    with caplog.at_level("WARNING", logger="tecnico.cadastros"):
        dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    por_id = {i["id"]: i for i in dados["instaladores"]}
    assert set(por_id) == {1, 2, 3, 5}
    assert por_id[2]["tipo"] == "papel" and por_id[2]["sha256"] == sha
    assert por_id[5]["sha256"] == ""
    assert dados["descartados"]["instaladores"] == [4, 6, 7, 8]
    assert "papel_invalido" in caplog.text and link not in caplog.text


def test_wifi_le_categoria_pelo_titulo(settings, fake):
    """NocoDB `fields=` uses the column title (`Categoria`); `categoria` came back absent."""
    dados = nocodb_cadastros.ler(configurar(settings), httpx.MockTransport(fake.handler))
    assert {rede["categoria"] for rede in dados["wifi"]} == {"Carreta"}


def test_tabela_que_falhou_so_no_log(settings, caplog):
    """The API log names the table (instaladores:http_400); the Bench only gets cadastros_indisponivel."""
    s = configurar(settings)
    criar_sessao(s)
    fake = FakeNocodb()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.split("/")[-2] == "mIns":
            return httpx.Response(400, json={"msg": "campo inexistente"})
        return fake.handler(request)

    with caplog.at_level("WARNING"), TestClient(create_app(s, transports={"nocodb_cadastros": httpx.MockTransport(handler)})) as c:
        r = c.get("/v1/bench/cadastros", headers=AUT)
    assert r.status_code == 503 and r.json() == {"erro": "cadastros_indisponivel"}
    assert "instaladores:http_400" in caplog.text
