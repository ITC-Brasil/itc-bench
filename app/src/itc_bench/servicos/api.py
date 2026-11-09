r"""Cliente da API do Bench (ADR-013), só com a stdlib, sem Qt.

TLS verificado (`ssl.create_default_context`, repositório do Windows), timeout de 15 s, nenhum
redirecionamento seguido. O que não for JSON da API (302, HTML do Cloudflare Access) é `ErroApi`;
um 403 em HTML nunca vira "sem perfil". A senha chega como `Sensivel` e só é revelada ao montar o
corpo; nenhuma exceção leva o corpo da requisição.

Endereço: `HKLM\SOFTWARE\ITC\Bench`, valor `ApiUrl` (instalador, ADR-008); em `--dev`,
`ITC_BENCH_API_URL` antes do registro.
"""

import json
import os
import ssl
import urllib.error
import urllib.request
import winreg
from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from itc_bench.nucleo.log import log
from itc_bench.servicos.executor import Sensivel

TIMEOUT = 15
# Laudo síncrono (ADR-015): a IA leva até ~90 s no servidor e a borda corta em ~100 s.
TIMEOUT_RELATORIO = 105
CHAVE_REGISTRO = r"SOFTWARE\ITC\Bench"
VARIAVEL_DEV = "ITC_BENCH_API_URL"
# Borda da Cloudflare sem a origem (530: túnel caído) e a API sem o GLPI: liberam o offline.
STATUS_SEM_SERVIDOR = {502, 503, 504, 530}
HOSTS_DEV = {"127.0.0.1", "localhost", "::1"}


class SemConexao(Exception):
    """Servidor inalcançável (rede, DNS, timeout, TLS, borda sem origem, GLPI fora).

    Só esta libera o login offline.
    """


class GlpiIndisponivel(SemConexao):
    """A API está no ar mas não valida o login no GLPI (503 `glpi_indisponivel`).

    Continua liberando o offline (ADR-013); só muda a mensagem quando o offline também recusa.
    """


class Recusado(Exception):
    """A API respondeu e recusou: 401, 403 `fora_do_perfil` ou 429. Nunca libera o offline."""

    def __init__(self, status: int, codigo: str, retry_after: int | None = None) -> None:
        super().__init__(codigo)
        self.status, self.codigo, self.retry_after = status, codigo, retry_after


class ErroApi(Exception):
    """Resposta inesperada: outro código, corpo que não é JSON da API, redirecionamento."""


class IaFalhou(Exception):
    """`502/503 ia_*`: a API recebeu a coleta e gravou o diagnóstico, a IA não respondeu.

    Não é `SemConexao`: a coleta não volta para a fila; o laudo sai num novo envio.
    """

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class CadastrosIndisponivel(Exception):
    """`503 cadastros_indisponivel`: a API está no ar, o NocoDB não (ADR-014).

    Não é `SemConexao`: não libera nada do login e não mexe na sessão; o Bench fica com o cache.
    """


@dataclass(frozen=True)
class SessaoApi:
    token: Sensivel
    login: str
    nome: str
    expira_em: str


def endereco(dev: bool) -> str | None:
    if dev and (valor := os.environ.get(VARIAVEL_DEV, "").strip()):
        return valor
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_REGISTRO) as chave:
            valor, _ = winreg.QueryValueEx(chave, "ApiUrl")
    except FileNotFoundError:
        return None
    return str(valor).strip() or None


def validar(url: str, dev: bool) -> str:
    """HTTPS sempre; http:// só para a própria máquina em `--dev`.

    Sem credencial (`usuario:senha@`), query, fragmento nem espaço (Módulo 15): o endereço vai
    para o registro e para o log do instalador, e não carrega segredo.
    """
    partes = urlsplit(url)
    if (
        partes.username is not None
        or partes.query
        or partes.fragment
        or any(c.isspace() for c in url)
    ):
        raise ValueError("Endereço da API inválido: sem usuário, senha, query nem fragmento.")
    if partes.scheme == "https" and partes.hostname:
        return url.rstrip("/")
    if dev and partes.scheme == "http" and partes.hostname in HOSTS_DEV:
        return url.rstrip("/")
    raise ValueError("Endereço da API precisa ser https://.")


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None  # o 3xx volta como HTTPError e vira ErroApi


_abridor = urllib.request.build_opener(
    _SemRedirecionar(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
)


def _chamar(
    base: str,
    metodo: str,
    caminho: str,
    corpo: dict[str, Any] | None = None,
    sessao: Sensivel | None = None,
    extras: dict[str, str] | None = None,
    timeout: float = TIMEOUT,
) -> tuple[int, Message, dict[str, Any] | None]:
    cabecalhos = {"Accept": "application/json", "User-Agent": "itc-bench", **(extras or {})}
    dados = None
    if corpo is not None:
        cabecalhos["Content-Type"] = "application/json"
        dados = json.dumps(
            {k: v.revelar() if isinstance(v, Sensivel) else v for k, v in corpo.items()}
        ).encode()
    if sessao is not None:
        cabecalhos["Authorization"] = f"Bearer {sessao.revelar()}"
    # Esquema conferido em validar(): só https:// (ou http:// local em --dev).
    requisicao = urllib.request.Request(  # noqa: S310
        base + caminho, data=dados, headers=cabecalhos, method=metodo
    )
    try:
        with _abridor.open(requisicao, timeout=timeout) as resposta:
            status, headers, bruto = resposta.status, resposta.headers, resposta.read()
    except urllib.error.HTTPError as erro:
        status, headers, bruto = erro.code, erro.headers, erro.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError, OSError) as erro:
        motivo = getattr(erro, "reason", erro)
        log.warning("API inalcançável em %s %s (%s).", metodo, caminho, type(motivo).__name__)
        raise SemConexao(type(motivo).__name__) from None
    if status in (204, 304):
        return status, headers, None
    if "application/json" not in (headers.get("Content-Type") or ""):
        if status in STATUS_SEM_SERVIDOR:
            raise SemConexao(f"http_{status}")
        log.warning("API respondeu %s sem JSON em %s %s.", status, metodo, caminho)
        raise ErroApi(f"Resposta inesperada do servidor ({status}).")
    try:
        conteudo = json.loads(bruto)
    except ValueError:
        raise ErroApi(f"Resposta inesperada do servidor ({status}).") from None
    if not isinstance(conteudo, dict):
        raise ErroApi(f"Resposta inesperada do servidor ({status}).")
    return status, headers, conteudo


def _retry_after(headers: Message) -> int | None:
    try:
        return max(1, int(headers.get("Retry-After", "")))
    except ValueError:
        return None


def entrar(base: str, usuario: str, senha: Sensivel, maquina: str) -> SessaoApi:
    status, headers, dados = _chamar(
        base, "POST", "/v1/bench/login", {"usuario": usuario, "senha": senha, "maquina": maquina}
    )
    erro = (dados or {}).get("erro")
    if status == 200 and dados:
        try:
            tecnico = dados["tecnico"]
            return SessaoApi(
                Sensivel(dados["sessao"]), tecnico["login"], tecnico["nome"], dados["expira_em"]
            )
        except (KeyError, TypeError):
            raise ErroApi("Resposta inesperada do servidor (200).") from None
    if status == 401 and erro == "credenciais_invalidas":
        raise Recusado(401, erro)
    if status == 403 and erro == "fora_do_perfil":
        raise Recusado(403, erro)
    if status == 429:
        raise Recusado(429, "limite_excedido", _retry_after(headers))
    if status == 503 and erro == "glpi_indisponivel":
        raise GlpiIndisponivel(erro)
    if status in STATUS_SEM_SERVIDOR:
        raise SemConexao(erro or f"http_{status}")
    raise ErroApi(f"Resposta inesperada do servidor ({status}).")


def sessao_valida(base: str, token: Sensivel) -> bool:
    status, _, _ = _chamar(base, "GET", "/v1/bench/sessao", sessao=token)
    return status == 200


def sair(base: str, token: Sensivel) -> None:
    _chamar(base, "POST", "/v1/bench/logout", sessao=token)


def cadastros(
    base: str, token: Sensivel, versao: str | None, unidade: str | None
) -> dict[str, Any] | None:
    """Corpo do `200`, ou None no `304` (versão igual). O caminho não leva segredo: a unidade
    é um código de `Unidades`."""
    caminho = "/v1/bench/cadastros" + (f"?{urlencode({'unidade': unidade})}" if unidade else "")
    extras = {"If-None-Match": f'"{versao}"'} if versao else None
    status, _, dados = _chamar(base, "GET", caminho, sessao=token, extras=extras)
    erro = (dados or {}).get("erro")
    if status == 200 and dados:
        return dados
    if status == 304:
        return None
    if status == 401:
        raise Recusado(401, "nao_autorizado")
    if status == 422 and erro == "unidade_invalida":
        raise Recusado(422, erro)
    if status == 503 and erro == "cadastros_indisponivel":
        raise CadastrosIndisponivel(erro)
    if status in STATUS_SEM_SERVIDOR:
        raise SemConexao(erro or f"http_{status}")
    raise ErroApi(f"Resposta inesperada do servidor ({status}).")


def relatorio(base: str, token: Sensivel, corpo: dict[str, Any]) -> dict[str, Any]:
    """`POST /v1/bench/relatorio` (ADR-016). Mesmo `envio_id` repetido é seguro (TA-ADR-028)."""
    status, headers, dados = _chamar(
        base, "POST", "/v1/bench/relatorio", corpo, sessao=token, timeout=TIMEOUT_RELATORIO
    )
    erro = str((dados or {}).get("erro") or "")
    if status == 200 and dados:
        return dados
    if status in (401, 409, 422):
        raise Recusado(status, erro or "nao_autorizado")
    if status == 429:
        raise Recusado(429, "limite_excedido", _retry_after(headers))
    if status in (502, 503) and erro.startswith("ia_"):
        raise IaFalhou(erro)
    if status in STATUS_SEM_SERVIDOR:
        raise SemConexao(erro or f"http_{status}")
    raise ErroApi(f"Resposta inesperada do servidor ({status}).")


def historico(base: str, token: Sensivel, hostname: str) -> dict[str, Any]:
    """`GET /v1/bench/historico/{hostname}`; o hostname vem do Windows, nunca da tela."""
    status, _, dados = _chamar(
        base, "GET", f"/v1/bench/historico/{quote(hostname, safe='')}", sessao=token
    )
    if status == 200 and dados:
        return dados
    if status == 401:
        raise Recusado(401, "nao_autorizado")
    if status in STATUS_SEM_SERVIDOR:
        raise SemConexao(f"http_{status}")
    raise ErroApi(f"Resposta inesperada do servidor ({status}).")


def saude(base: str) -> bool:
    status, _, dados = _chamar(base, "GET", "/v1/bench/saude")
    return status == 200 and (dados or {}).get("status") == "ok"


def mensagem(erro: Exception) -> str:
    """Texto para a tela, sem detalhe interno."""
    if isinstance(erro, Recusado):
        if erro.codigo == "credenciais_invalidas":
            return "Usuário ou senha incorretos."
        if erro.codigo == "fora_do_perfil":
            return "Usuário sem perfil de técnico no GLPI."
        if erro.retry_after:
            minutos = max(1, round(erro.retry_after / 60))
            return f"Muitas tentativas. Tente de novo em {minutos} min."
        return "Muitas tentativas. Aguarde alguns minutos e tente de novo."
    if isinstance(erro, SemConexao):
        return "Sem conexão com o servidor."
    return str(erro) or "Erro inesperado ao falar com o servidor."
