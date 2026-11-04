"""GLPI client (ADR-005, ADR-013): the only place that knows the GLPI URL and formats.

API v2 (/api.php) with the OAuth2 password grant: get a user token, read GET /session, drop
the token. Access is by GLPI profile, never by group (ADR-013): `profiles` of /session is
$_SESSION['glpiprofiles'], every profile the user has in any entity, not only the active one
(the legacy API equivalent is glpiprofiles of getFullSession). GLPI 12 (or the legacy API as fallback) replaces this file and keeps
autenticar(), Tecnico, CredenciaisInvalidas and GlpiIndisponivel.

Nothing from GLPI (body, headers, token) reaches a log or a response: failures carry a short
code only. The password is read once, into the form body.
"""

import ipaddress
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

log = logging.getLogger("tecnico.glpi")

# GLPI 11 high-level API (CoreController: POST /token, GET /session).
TOKEN = "/api.php/token"
SESSAO = "/api.php/v2/session"
NOMES_INTERNOS = (".internal", ".local", ".lan", ".invalid")


class CredenciaisInvalidas(Exception):
    """Wrong password, unknown or inactive user."""


class GlpiIndisponivel(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Tecnico:
    glpi_id: int
    login: str
    nome: str
    tem_perfil: bool


def url_interna(url: str) -> bool:
    """GLPI 11 has no HTTPS: http:// only to the same server or the Docker network (ADR-013)."""
    partes = urlsplit(url)
    if partes.scheme == "https":
        return bool(partes.hostname)
    if partes.scheme != "http" or not partes.hostname:
        return False
    host = partes.hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith(NOMES_INTERNOS)
    return ip.is_private or ip.is_loopback


def configurado(settings) -> bool:
    return bool(
        settings.glpi_url
        and url_interna(settings.glpi_url)
        and settings.glpi_oauth_client_id
        and settings.glpi_oauth_client_secret.get_secret_value()
        and settings.glpi_perfil_tecnicos_id > 0
        and settings.bench_login_hmac_key.get_secret_value()
    )


def autenticar(settings, usuario: str, senha: SecretStr, transport: httpx.BaseTransport | None = None) -> Tecnico:
    if not configurado(settings):
        raise GlpiIndisponivel("nao_configurado")
    base = settings.glpi_url.rstrip("/")
    try:
        with httpx.Client(timeout=settings.glpi_timeout_seconds, transport=transport, follow_redirects=False) as client:
            resposta = client.post(
                base + TOKEN,
                data={
                    "grant_type": "password",
                    "client_id": settings.glpi_oauth_client_id,
                    "client_secret": settings.glpi_oauth_client_secret.get_secret_value(),
                    "username": usuario,
                    "password": senha.get_secret_value(),
                    "scope": "api",
                },
            )
            if resposta.status_code in (400, 401) and _erro_oauth(resposta) == "invalid_grant":
                raise CredenciaisInvalidas()
            _exigir_200(resposta, "token")
            cabecalhos = {"Authorization": f"Bearer {resposta.json()['access_token']}"}
            sessao = client.get(base + SESSAO, headers=cabecalhos)
            _exigir_200(sessao, "sessao")
            dados = sessao.json()
            perfis = {int(p) for p in dados["profiles"]}
            nome = " ".join(p for p in (dados.get("first_name"), dados.get("real_name")) if p) or str(dados["name"])
            tecnico = Tecnico(
                glpi_id=int(dados["user_id"]),
                login=str(dados["name"]).strip().lower(),
                nome=nome,
                tem_perfil=settings.glpi_perfil_tecnicos_id in perfis,
            )
    except httpx.TimeoutException:
        log.warning("GLPI: timeout")
        raise GlpiIndisponivel("timeout") from None
    except httpx.HTTPError as erro:
        log.warning("GLPI: falha de rede (%s)", type(erro).__name__)
        raise GlpiIndisponivel("rede") from None
    except (ValueError, KeyError, TypeError) as erro:
        log.warning("GLPI: resposta fora do formato (%s)", type(erro).__name__)
        raise GlpiIndisponivel("formato") from None
    return tecnico


def _erro_oauth(resposta: httpx.Response) -> str | None:
    try:
        return resposta.json().get("error")
    except (ValueError, AttributeError):
        return None


def _exigir_200(resposta: httpx.Response, etapa: str) -> None:
    if resposta.status_code != 200:
        log.warning("GLPI: %s respondeu %s", etapa, resposta.status_code)
        raise GlpiIndisponivel(f"{etapa}_{resposta.status_code}")
