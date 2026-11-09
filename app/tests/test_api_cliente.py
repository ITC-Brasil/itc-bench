"""Cliente da API contra um servidor HTTP local com respostas roteirizadas (sem rede real)."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from itc_bench.servicos import api
from itc_bench.servicos.executor import Sensivel

SENHA = "Marcador-Senha-7Q2x!"
SESSAO = "itcbs_" + "a" * 43


class Roteiro:
    status = 200
    corpo: bytes = b""
    tipo = "application/json"
    extras: dict[str, str] = {}  # noqa: RUF012
    recebido: bytes = b""
    caminho = ""
    cabecalhos: dict[str, str] = {}  # noqa: RUF012


def resposta(
    status: int, corpo: object = None, tipo: str = "application/json", **extras: str
) -> None:
    Roteiro.status = status
    Roteiro.corpo = (
        json.dumps(corpo).encode() if tipo == "application/json" else str(corpo).encode()
    )
    Roteiro.tipo = tipo
    Roteiro.extras = extras


class Handler(BaseHTTPRequestHandler):
    def _responder(self) -> None:
        tamanho = int(self.headers.get("Content-Length") or 0)
        Roteiro.recebido = self.rfile.read(tamanho)
        Roteiro.caminho, Roteiro.cabecalhos = self.path, dict(self.headers)
        self.send_response(Roteiro.status)
        self.send_header("Content-Type", Roteiro.tipo)
        for nome, valor in Roteiro.extras.items():
            self.send_header(nome.replace("_", "-"), valor)
        self.send_header("Content-Length", str(len(Roteiro.corpo)))
        self.end_headers()
        self.wfile.write(Roteiro.corpo)

    do_GET = do_POST = _responder

    def log_message(self, *_args: object) -> None:
        pass  # sem ruído no pytest


@pytest.fixture(scope="module")
def base():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()


def entrar(base: str) -> api.SessaoApi:
    return api.entrar(base, "ana.lima", Sensivel(SENHA), "NB-TESTE-01")


def test_login_certo(base):
    resposta(
        200,
        {
            "sessao": SESSAO,
            "expira_em": "2026-11-05T00:00:00Z",
            "tecnico": {"login": "ana.lima", "nome": "Ana"},
        },
    )
    s = entrar(base)
    assert (s.login, s.nome) == ("ana.lima", "Ana") and s.token.revelar() == SESSAO
    assert json.loads(Roteiro.recebido)["senha"] == SENHA  # revelada só no corpo
    assert SESSAO not in repr(s)


@pytest.mark.parametrize(
    ("status", "corpo", "codigo"),
    [
        (401, {"erro": "credenciais_invalidas"}, "credenciais_invalidas"),
        (403, {"erro": "fora_do_perfil"}, "fora_do_perfil"),
    ],
)
def test_recusas_da_api(base, status, corpo, codigo):
    resposta(status, corpo)
    with pytest.raises(api.Recusado) as erro:
        entrar(base)
    assert erro.value.codigo == codigo and SENHA not in str(erro.value)


def test_403_em_html_do_access_nao_e_fora_do_perfil(base):
    resposta(403, "<html>Forbidden</html>", "text/html")
    with pytest.raises(api.ErroApi):
        entrar(base)


def test_403_json_com_outro_erro_e_erro_api(base):
    resposta(403, {"erro": "outra_coisa"})
    with pytest.raises(api.ErroApi):
        entrar(base)


def test_429_com_e_sem_retry_after(base):
    resposta(429, {"erro": "limite_excedido"}, Retry_After="600")
    with pytest.raises(api.Recusado) as erro:
        entrar(base)
    assert erro.value.retry_after == 600
    assert api.mensagem(erro.value) == "Muitas tentativas. Tente de novo em 10 min."
    resposta(429, "<html>rate limited</html>", "text/html")
    with pytest.raises(api.ErroApi):
        entrar(base)
    resposta(429, {"erro": "limite_excedido"})
    with pytest.raises(api.Recusado) as erro:
        entrar(base)
    assert erro.value.retry_after is None
    assert api.mensagem(erro.value) == "Muitas tentativas. Aguarde alguns minutos e tente de novo."


@pytest.mark.parametrize("status", [502, 503, 504, 530])
def test_borda_sem_origem_libera_offline(base, status):
    resposta(status, "<html>Bad gateway</html>", "text/html")
    with pytest.raises(api.SemConexao) as erro:
        entrar(base)
    assert not isinstance(erro.value, api.GlpiIndisponivel)


def test_glpi_indisponivel_libera_offline(base):
    resposta(503, {"erro": "glpi_indisponivel"})
    with pytest.raises(api.GlpiIndisponivel, match="glpi_indisponivel"):
        entrar(base)


def test_redirecionamento_nao_e_seguido(base):
    resposta(302, "", "text/html", Location="https://login.exemplo.invalid/")
    with pytest.raises(api.ErroApi):
        entrar(base)


def test_200_em_html_e_erro_api(base):
    resposta(200, "<html>login do Access</html>", "text/html")
    with pytest.raises(api.ErroApi):
        entrar(base)


def test_servidor_fora_libera_offline():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]  # fechada ao sair do with: conexão recusada
    with pytest.raises(api.SemConexao):
        api.entrar(f"http://127.0.0.1:{porta}", "ana", Sensivel(SENHA), "NB")


def test_sessao_logout_saude(base):
    resposta(200, {"status": "ok"})
    assert api.saude(base)
    resposta(204, "", "text/plain")
    api.sair(base, Sensivel(SESSAO))
    resposta(401, {"erro": "nao_autorizado"})
    assert not api.sessao_valida(base, Sensivel(SESSAO))


@pytest.mark.parametrize(
    ("url", "dev", "ok"),
    [
        ("https://api.exemplo.invalid", False, True),
        ("http://api.exemplo.invalid", False, False),
        ("http://127.0.0.1:8000", False, False),
        ("http://127.0.0.1:8000", True, True),
        ("http://api.exemplo.invalid", True, False),
        ("file:///c:/x", True, False),
        ("https://u:s@api.exemplo.invalid", False, False),
        ("https://u@api.exemplo.invalid", False, False),
        ("https://api.exemplo.invalid/?x=1", False, False),
        ("https://api.exemplo.invalid/#x", False, False),
        ("https://api.exemplo.invalid/a b", False, False),
        ("https://api.exemplo.invalid/base", False, True),
    ],
)
def test_validar_endereco(url, dev, ok):
    if ok:
        assert api.validar(url + "/", dev) == url
    else:
        with pytest.raises(ValueError):
            api.validar(url, dev)


def test_endereco_dev_pela_variavel(monkeypatch):
    monkeypatch.setenv(api.VARIAVEL_DEV, "http://127.0.0.1:9")
    assert api.endereco(dev=True) == "http://127.0.0.1:9"


# Cadastros (ADR-014)


def test_cadastros_200_com_versao_e_unidade(base):
    resposta(200, {"versao": "v1", "wifi": []})
    dados = api.cadastros(base, Sensivel(SESSAO), "v0", "UM-01")
    assert dados == {"versao": "v1", "wifi": []}
    assert Roteiro.caminho == "/v1/bench/cadastros?unidade=UM-01"
    assert Roteiro.cabecalhos["If-None-Match"] == '"v0"'
    assert Roteiro.cabecalhos["Authorization"] == f"Bearer {SESSAO}"


def test_cadastros_sem_versao_nem_unidade(base):
    resposta(200, {"versao": "v1"})
    api.cadastros(base, Sensivel(SESSAO), None, None)
    assert Roteiro.caminho == "/v1/bench/cadastros"
    assert "If-None-Match" not in Roteiro.cabecalhos


def test_cadastros_304(base):
    resposta(304, "", tipo="text/plain")
    assert api.cadastros(base, Sensivel(SESSAO), "v1", None) is None


def test_cadastros_503_do_nocodb_nao_e_sem_conexao(base):
    resposta(503, {"erro": "cadastros_indisponivel"})
    with pytest.raises(api.CadastrosIndisponivel):
        api.cadastros(base, Sensivel(SESSAO), None, None)
    assert not issubclass(api.CadastrosIndisponivel, api.SemConexao)


def test_cadastros_borda_fora_e_sem_conexao(base):
    resposta(530, "<html>tunel</html>", tipo="text/html")
    with pytest.raises(api.SemConexao):
        api.cadastros(base, Sensivel(SESSAO), None, None)


@pytest.mark.parametrize(
    ("status", "corpo", "codigo"),
    [
        (401, {"erro": "nao_autorizado"}, "nao_autorizado"),
        (422, {"erro": "unidade_invalida"}, "unidade_invalida"),
    ],
)
def test_cadastros_recusados(base, status, corpo, codigo):
    resposta(status, corpo)
    with pytest.raises(api.Recusado) as erro:
        api.cadastros(base, Sensivel(SESSAO), None, "UM-09")
    assert erro.value.codigo == codigo


def test_cadastros_403_html_do_access_e_erro_api(base):
    resposta(403, "<html>Access</html>", tipo="text/html")
    with pytest.raises(api.ErroApi):
        api.cadastros(base, Sensivel(SESSAO), None, None)
