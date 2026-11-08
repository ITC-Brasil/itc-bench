"""Bench login (ADR-013) against a fake GLPI: no real GLPI, ntfy or network."""

import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import Settings
from app.main import create_app
from app.routes import bench
from app.services import glpi

SENHA = "Marcador-Senha-7Q2x!"
PERFIL = 42
MAQUINA = "NB-TESTE-01"


class FakeGlpi:
    """GLPI v2: token by password grant, then GET /session with the bearer token.

    perfis: every profile of the user in any entity ($_SESSION['glpiprofiles']); ativo: the
    active profile, which is not what decides access.
    """

    def __init__(self, perfis=(PERFIL,), ativo=None, falha=None):
        self.perfis, self.falha, self.chamadas = list(perfis), falha, 0
        self.ativo = ativo if ativo is not None else (self.perfis[0] if self.perfis else 0)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.chamadas += 1
        if self.falha == "rede":
            raise httpx.ConnectError("recusado", request=request)
        if self.falha == "timeout":
            raise httpx.ReadTimeout("lento", request=request)
        if self.falha == "500":
            return httpx.Response(500, text="erro interno com detalhes")
        if request.url.path == glpi.TOKEN:
            corpo = dict(httpx.QueryParams(request.content.decode()))
            if self.falha == "cliente":
                return httpx.Response(401, json={"error": "invalid_client"})
            if corpo["username"] != "tecnico" or corpo["password"] != SENHA:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "tk-glpi", "token_type": "Bearer"})
        assert request.headers["authorization"] == "Bearer tk-glpi"
        if request.url.path == glpi.SESSAO:
            if self.falha == "formato":
                return httpx.Response(200, json={"sem": "campos"})
            return httpx.Response(
                200,
                json={
                    "user_id": 7,
                    "name": "Tecnico",
                    "first_name": "Ana",
                    "real_name": "Lima",
                    "profiles": self.perfis,
                    "active_profile": {"id": self.ativo, "name": "Perfil ativo"},
                },
            )
        return httpx.Response(404)


def configurar(settings, **extra):
    valores = dict(
        glpi_url="http://glpi.exemplo.invalid",
        glpi_oauth_client_id="cliente",
        glpi_oauth_client_secret="segredo",
        glpi_perfil_tecnicos_id=PERFIL,
        bench_login_hmac_key="chave-hmac-teste",
    )
    valores.update(extra)
    return Settings(_env_file=None, database_path=settings.database_path, **valores)


@pytest.fixture
def fake():
    return FakeGlpi()


@pytest.fixture
def cliente(settings, fake):
    app = create_app(configurar(settings), {"glpi": httpx.MockTransport(fake.handler)}, lambda f: f())
    with TestClient(app) as client:
        yield client


def entrar(client, usuario="tecnico", senha=SENHA, **cabecalhos):
    return client.post("/v1/bench/login", json={"usuario": usuario, "senha": senha, "maquina": MAQUINA}, headers=cabecalhos)


def linhas(settings, sql):
    import sqlite3

    conn = sqlite3.connect(settings.database_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_login_certo_devolve_sessao_que_vale_em_sessao(cliente, settings):
    r = entrar(cliente, usuario="  Tecnico ")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["sessao"].startswith("itcbs_") and auth.SESSAO_FORMAT.fullmatch(corpo["sessao"])
    assert corpo["tecnico"] == {"login": "tecnico", "nome": "Ana Lima"}
    s = cliente.get("/v1/bench/sessao", headers={"Authorization": f"Bearer {corpo['sessao']}"})
    assert s.status_code == 200 and s.json()["tecnico"]["login"] == "tecnico"
    # Only the SHA-256 is stored.
    assert corpo["sessao"] not in str(linhas(settings, "SELECT * FROM bench_sessoes"))
    assert linhas(settings, "SELECT usuario, resultado FROM bench_login_auditoria") == [("tecnico", "ok")]


def test_senha_errada_401_e_audita_hmac(cliente, settings):
    r = entrar(cliente, senha="errada")
    assert r.status_code == 401 and r.json() == {"erro": "credenciais_invalidas"}
    usuario, resultado = linhas(settings, "SELECT usuario, resultado FROM bench_login_auditoria")[0]
    assert resultado == "credenciais_invalidas" and usuario.startswith("h:") and "tecnico" not in usuario


@pytest.mark.parametrize(
    ("perfis", "ativo", "esperado"),
    [
        ([PERFIL], PERFIL, 200),  # com o perfil
        ([1, 2], 1, 403),  # sem o perfil
        ([1, PERFIL], 1, 200),  # perfil só numa entidade secundária, não o ativo
    ],
)
def test_acesso_pelo_perfil_em_qualquer_entidade(settings, perfis, ativo, esperado):
    fake = FakeGlpi(perfis=perfis, ativo=ativo)
    with TestClient(create_app(configurar(settings), {"glpi": httpx.MockTransport(fake.handler)}, lambda f: f())) as c:
        r = entrar(c)
    assert r.status_code == esperado
    if esperado == 403:
        assert r.json() == {"erro": "fora_do_perfil"}
        assert linhas(settings, "SELECT usuario, resultado FROM bench_login_auditoria") == [("tecnico", "fora_do_perfil")]


@pytest.mark.parametrize("falha", ["rede", "timeout", "500", "formato", "cliente"])
def test_glpi_fora_lento_ou_estranho_503(settings, falha, caplog):
    fake = FakeGlpi(falha=falha)
    with TestClient(create_app(configurar(settings), {"glpi": httpx.MockTransport(fake.handler)}, lambda f: f())) as c:
        r = entrar(c)
    assert r.status_code == 503 and r.json() == {"erro": "glpi_indisponivel"}
    assert "detalhes" not in caplog.text
    # 503 does not count as a failed attempt.
    assert linhas(settings, "SELECT * FROM bench_login_tentativas") == []


def test_timeout_usa_glpi_timeout_seconds(settings, monkeypatch):
    vistos = []
    original = httpx.Client.__init__

    def init(self, *a, **k):
        vistos.append(k.get("timeout"))
        original(self, *a, **k)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    fake = FakeGlpi()
    with TestClient(create_app(configurar(settings, glpi_timeout_seconds=3), {"glpi": httpx.MockTransport(fake.handler)})) as c:
        entrar(c)
    assert 3 in vistos


@pytest.mark.parametrize(
    "extra",
    [
        dict(glpi_url=""),
        dict(glpi_oauth_client_secret=""),
        dict(glpi_perfil_tecnicos_id=0),
        dict(bench_login_hmac_key=""),
        dict(glpi_url="http://glpi.example.com"),
        dict(glpi_url="http://8.8.8.8"),
    ],
)
def test_sem_configuracao_ou_url_publica_sobe_e_responde_503(settings, fake, extra):
    with TestClient(create_app(configurar(settings, **extra), {"glpi": httpx.MockTransport(fake.handler)})) as c:
        assert c.get("/v1/saude").status_code == 200
        r = entrar(c)
    assert r.status_code == 503 and r.json() == {"erro": "glpi_indisponivel"}
    assert fake.chamadas == 0


def test_defaults_sobem_sem_variaveis_novas(settings):
    with TestClient(create_app(settings)) as c:
        assert entrar(c).status_code == 503


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://localhost:8080", True),
        ("http://127.0.0.1", True),
        ("http://172.17.0.1", True),
        ("http://glpi", True),
        ("http://glpi.internal", True),
        ("https://glpi.example.com", True),
        ("http://glpi.example.com", False),
        ("http://8.8.8.8", False),
        ("ftp://glpi", False),
        ("", False),
    ],
)
def test_url_interna(url, ok):
    assert glpi.url_interna(url) is ok


def test_limite_por_usuario_atinge_e_libera(cliente, settings, fake, monkeypatch):
    agora = datetime(2026, 11, 4, 10, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(bench, "utcnow", lambda: agora)
    for _ in range(settings.bench_login_falhas_usuario):
        assert entrar(cliente, senha="errada").status_code == 401
    chamadas = fake.chamadas
    r = entrar(cliente)
    assert r.status_code == 429 and r.json() == {"erro": "limite_excedido"}
    assert int(r.headers["Retry-After"]) == 14 * 60
    assert fake.chamadas == chamadas, "bloqueado não chega ao GLPI"
    agora = datetime(2026, 11, 4, 10, 15, tzinfo=timezone.utc)
    assert entrar(cliente).status_code == 200


def test_tentativas_em_paralelo_nao_passam_do_limite(settings, fake):
    """Module 14: check and count in one transaction; before, all parallel attempts reached GLPI."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    limite, n = 3, 8
    barreira = threading.Barrier(n, timeout=2)
    original = fake.handler

    def lento(request):
        if request.url.path == glpi.TOKEN:
            try:
                barreira.wait()  # every attempt that got past the check waits for the others
            except threading.BrokenBarrierError:
                pass
        return original(request)

    s = configurar(settings, bench_login_falhas_usuario=limite)
    with TestClient(create_app(s, {"glpi": httpx.MockTransport(lento)}, lambda f: f())) as c:
        with ThreadPoolExecutor(n) as pool:
            codigos = list(pool.map(lambda _: entrar(c, senha="errada").status_code, range(n)))
    assert codigos.count(401) == limite
    assert codigos.count(429) == n - limite


def test_glpi_fora_do_ar_nao_conta_tentativa(cliente, settings, fake):
    fake.falha = "rede"
    for _ in range(settings.bench_login_falhas_usuario + 1):
        assert entrar(cliente).status_code == 503
    fake.falha = None
    assert entrar(cliente).status_code == 200


def test_limite_por_ip_com_usuarios_diferentes(settings, fake, monkeypatch):
    s = configurar(settings, bench_login_falhas_ip=3)
    with TestClient(create_app(s, {"glpi": httpx.MockTransport(fake.handler)}, lambda f: f())) as c:
        for i in range(3):
            assert entrar(c, usuario=f"outro{i}", **{"CF-Connecting-IP": "203.0.113.9"}).status_code == 401
        assert entrar(c, **{"CF-Connecting-IP": "203.0.113.9"}).status_code == 429
        # Another IP is not locked.
        assert entrar(c, **{"CF-Connecting-IP": "203.0.113.10"}).status_code == 200


def test_cf_connecting_ip_invalido_usa_ip_da_conexao(cliente, settings):
    entrar(cliente, senha="errada", **{"CF-Connecting-IP": "nao-e-ip"})
    assert linhas(settings, "SELECT ip FROM bench_login_auditoria") == [("testclient",)]


def test_sucesso_zera_falhas_do_usuario(cliente, settings):
    for _ in range(settings.bench_login_falhas_usuario - 1):
        entrar(cliente, senha="errada")
    assert entrar(cliente).status_code == 200
    for _ in range(settings.bench_login_falhas_usuario - 1):
        assert entrar(cliente, senha="errada").status_code == 401


def test_sessao_expirada_401(cliente, monkeypatch):
    sessao = entrar(cliente).json()["sessao"]
    depois = datetime.now(timezone.utc) + timedelta(hours=12, minutes=1)
    monkeypatch.setattr(auth, "utcnow", lambda: depois)
    r = cliente.get("/v1/bench/sessao", headers={"Authorization": f"Bearer {sessao}"})
    assert r.status_code == 401 and r.json() == {"erro": "nao_autorizado"}


def test_logout_revoga(cliente, settings):
    sessao = entrar(cliente).json()["sessao"]
    h = {"Authorization": f"Bearer {sessao}"}
    assert cliente.post("/v1/bench/logout", headers=h).status_code == 204
    assert cliente.get("/v1/bench/sessao", headers=h).status_code == 401
    assert cliente.post("/v1/bench/logout", headers=h).status_code == 204
    assert cliente.post("/v1/bench/logout").status_code == 204
    assert ("tecnico", "logout") in linhas(settings, "SELECT usuario, resultado FROM bench_login_auditoria")


def test_token_da_carreta_nao_vale_como_sessao_e_vice_versa(cliente, issue):
    carreta = issue()
    assert cliente.get("/v1/bench/sessao", headers={"Authorization": f"Bearer {carreta}"}).status_code == 401
    sessao = entrar(cliente).json()["sessao"]
    r = cliente.post("/v1/relatorio", headers={"Authorization": f"Bearer {sessao}"}, json={})
    assert r.status_code == 401


@pytest.mark.parametrize("caminho", ["/v1/benchx", "/v1/bench/../relatorio", "/v1/bench/%2e%2e/relatorio", "//v1/relatorio"])
def test_caminhos_vizinhos_nao_abrem_rota_da_carreta(cliente, caminho):
    r = cliente.get(caminho)
    assert r.status_code in (401, 404, 405)


def test_saude_do_bench(cliente):
    assert cliente.get("/v1/bench/saude").json() == {"status": "ok"}


def test_corpo_invalido_nao_ecoa_senha(cliente):
    r = cliente.post("/v1/bench/login", json={"usuario": "tecnico", "senha": SENHA, "maquina": "inválida com espaço"})
    assert r.status_code == 422 and SENHA not in r.text


def test_senha_ausente_de_log_e_sqlite(cliente, settings, caplog):
    caplog.set_level(logging.DEBUG)
    entrar(cliente)
    entrar(cliente, senha="errada")
    # A password typed in the user field: GLPI does not recognize it, only its HMAC is stored.
    entrar(cliente, usuario=SENHA, senha=SENHA)
    with open(settings.database_path, "rb") as arquivo:
        bruto = arquivo.read()
    assert SENHA.encode() not in bruto and SENHA.lower().encode() not in bruto
    for tabela in ("bench_sessoes", "bench_login_tentativas", "bench_login_auditoria"):
        assert SENHA.lower() not in str(linhas(settings, f"SELECT * FROM {tabela}")).lower()
    assert SENHA.lower() not in caplog.text.lower()


def test_alerta_no_limite_sem_usuario_por_extenso(settings, fake, monkeypatch):
    enviados = []
    monkeypatch.setattr(bench.ntfy, "alertar", lambda s, chave, titulo, msg, t=None: enviados.append(chave + msg))
    s = configurar(settings, bench_login_falhas_usuario=1)
    with TestClient(create_app(s, {"glpi": httpx.MockTransport(fake.handler)}, lambda f: f())) as c:
        entrar(c, usuario=SENHA, senha="x")
        assert entrar(c, usuario=SENHA, senha="x").status_code == 429
    assert enviados and SENHA.lower() not in enviados[0].lower()
