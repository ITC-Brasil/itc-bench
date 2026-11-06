"""Read the four Bench cadastros from NocoDB (ADR-014, TA-ADR-027). The only file that does it.

NocoDB is the source of truth for Servidores, Instaladores, WiFi and Unidades; the API only
reads, with a Viewer token on the "ITC Bench" base. Rows are validated here: inactive rows, rows
without the display field and WiFi of an unknown unit are dropped, logged by table and Id only.
Secrets (Servidores.Valor/Observacao unless Publico, WiFi.Senha) stay SecretStr until the route
serializes them. No log line carries a value, a SSID, the URL with its query or a header.
"""

import logging
import re
import time

import httpx
from pydantic import SecretStr

log = logging.getLogger("tecnico.cadastros")
SHA256 = re.compile(r"[0-9a-f]{64}")
# Instaladores by Tipo (TA-ADR-029, TA-ADR-030 for papel): value -> default when empty.
TIPOS = ("instalador", "winget", "webapp", "papel")
CATEGORIAS = ("Programas", "Jogos")
MODOS = ("quiosque", "app")
WINGET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{1,127}")
ARQUIVO_PAPEL = re.compile(r"[^\\/]+\.(?:jpg|jpeg|png)", re.IGNORECASE)
URL_WEBAPP = re.compile(r"https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?#][^\s\x00-\x1f\"'<>\\]*)?")

LIMITE_PAGINA = 1000
MAXIMO_PAGINAS = 20
TETO_SEGUNDOS = 30.0  # under the 100 s of the Cloudflare Tunnel (TA-ADR-010)

# table: (setting with the table id, NocoDB fields, display field)
TABELAS = {
    "servidores": (
        "nocodb_tabela_servidores",
        ("Id", "Servico", "Papel", "Valor", "Versao", "Ativo", "Observacao", "Publico"),
        "Servico",
    ),
    "instaladores": (
        "nocodb_tabela_instaladores",
        (
            "Id", "Programa", "Versao", "Arquivo", "SHA256", "Link", "Ativo", "Observacao",
            "Tipo", "Categoria", "Identificador", "Argumentos", "Deteccao", "Modo",
        ),
        "Programa",
    ),
    "wifi": ("nocodb_tabela_wifi", ("Id", "SSID", "Senha", "Unidade", "categoria", "Ativo", "AtualizadoEm"), "SSID"),
    "unidades": (
        "nocodb_tabela_unidades",
        ("Id", "Codigo", "Nome", "Cidade", "UF", "TagGLPI", "PerfilPadrao", "Ativo"),
        "Codigo",
    ),
}


class NocodbIndisponivel(Exception):
    """code: timeout, indisponivel, http_<status> or resposta_invalida. Never URL or token."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def configurado(settings) -> bool:
    token = settings.nocodb_cadastros_token.get_secret_value().strip()
    ids = all(getattr(settings, tabela[0]).strip() for tabela in TABELAS.values())
    return bool(settings.nocodb_url and ids and token not in ("", "changeme"))


def marcado(valor) -> bool:
    """NocoDB checkbox: true (or 1 on some backends). Anything else, None included, is false."""
    return valor is True or (type(valor) is int and valor == 1)


def texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def ler(settings, transport: httpx.BaseTransport | None = None) -> dict:
    """The four cadastros, validated, plus descartados {table: [Id, ...]}."""
    brutos = {}
    inicio = time.monotonic()
    headers = {"xc-token": settings.nocodb_cadastros_token.get_secret_value().strip()}
    with httpx.Client(timeout=settings.nocodb_cadastros_timeout_seconds, transport=transport) as client:
        for nome, (id_setting, campos, _) in TABELAS.items():
            url = f"{settings.nocodb_url.rstrip('/')}/api/v2/tables/{getattr(settings, id_setting).strip()}/records"
            brutos[nome] = paginas(client, url, headers, campos, inicio)
    return validar(brutos)


def paginas(client: httpx.Client, url: str, headers: dict, campos: tuple, inicio: float) -> list[dict]:
    linhas: list[dict] = []
    for pagina in range(MAXIMO_PAGINAS):
        if time.monotonic() - inicio > TETO_SEGUNDOS:
            raise NocodbIndisponivel("timeout")
        params = {"fields": ",".join(campos), "limit": LIMITE_PAGINA, "offset": pagina * LIMITE_PAGINA}
        try:
            resposta = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            raise NocodbIndisponivel("timeout") from None
        except httpx.HTTPError:
            raise NocodbIndisponivel("indisponivel") from None
        if resposta.status_code != 200:
            raise NocodbIndisponivel(f"http_{resposta.status_code}")
        try:
            corpo = resposta.json()
            lista, fim = corpo["list"], corpo.get("pageInfo", {}).get("isLastPage", True)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise NocodbIndisponivel("resposta_invalida") from None
        if not isinstance(lista, list) or not all(isinstance(linha, dict) for linha in lista):
            raise NocodbIndisponivel("resposta_invalida")
        linhas += lista
        if fim is not False:
            return linhas
    # ponytail: 20 000 rows is far beyond these tables; a cut list is an error, not a partial copy.
    raise NocodbIndisponivel("resposta_invalida")


def validar(brutos: dict[str, list[dict]]) -> dict:
    descartados: dict[str, list] = {}
    validos: dict[str, list[dict]] = {}
    for nome, (_, _, exibicao) in TABELAS.items():
        validos[nome] = []
        for linha in brutos[nome]:
            motivo = None if marcado(linha.get("Ativo")) else "inativo"
            if motivo is None and not texto(linha.get(exibicao)):
                motivo = "sem_" + exibicao.lower()
            if motivo == "inativo":
                continue  # inactive is normal, not a problem in the cadastro
            if motivo:
                descartados.setdefault(nome, []).append(linha.get("Id"))
                log.warning("cadastro %s Id %s descartado: %s", nome, linha.get("Id"), motivo)
                continue
            validos[nome].append(linha)

    instaladores = []
    for linha in validos["instaladores"]:
        motivo = motivo_instalador(linha)
        if motivo:
            descartados.setdefault("instaladores", []).append(linha.get("Id"))
            log.warning("cadastro instaladores Id %s descartado: %s", linha.get("Id"), motivo)
            continue
        instaladores.append(instalador(linha))

    unidades = [unidade(linha) for linha in validos["unidades"]]
    codigos = {u["codigo"] for u in unidades}
    wifi = []
    for linha in validos["wifi"]:
        if texto(linha.get("Unidade")) not in codigos:
            descartados.setdefault("wifi", []).append(linha.get("Id"))
            log.warning("cadastro wifi Id %s descartado: unidade_invalida", linha.get("Id"))
            continue
        wifi.append(rede(linha))
    return {
        "servidores": [servidor(linha) for linha in validos["servidores"]],
        "instaladores": instaladores,
        "wifi": wifi,
        "unidades": unidades,
        "descartados": descartados,
    }


def servidor(linha: dict) -> dict:
    publico = marcado(linha.get("Publico"))
    valor, observacao = texto(linha.get("Valor")), texto(linha.get("Observacao"))
    return {
        "id": linha.get("Id"),
        "servico": texto(linha.get("Servico")),
        "papel": texto(linha.get("Papel")),
        # Fails closed: only Publico = true is public; free text may hold a password.
        "valor": valor if publico else SecretStr(valor),
        "versao": texto(linha.get("Versao")),
        "observacao": observacao if publico else SecretStr(observacao),
        "publico": publico,
    }


def motivo_instalador(linha: dict) -> str | None:
    tipo = texto(linha.get("Tipo")) or "instalador"
    if tipo not in TIPOS:
        return "tipo_invalido"
    if (texto(linha.get("Categoria")) or "Programas") not in CATEGORIAS:
        return "categoria_invalida"
    if (texto(linha.get("Modo")) or "quiosque") not in MODOS:
        return "modo_invalido"
    ident = texto(linha.get("Identificador"))
    if tipo == "winget" and not WINGET_ID.fullmatch(ident):
        return "identificador_invalido"
    if tipo == "webapp" and not URL_WEBAPP.fullmatch(ident):
        return "identificador_invalido"
    if tipo == "papel" and not (
        ARQUIVO_PAPEL.fullmatch(texto(linha.get("Arquivo")))
        and SHA256.fullmatch(texto(linha.get("SHA256")).lower())
        and URL_WEBAPP.fullmatch(texto(linha.get("Link")))
    ):
        return "papel_invalido"
    return None


def instalador(linha: dict) -> dict:
    sha256 = texto(linha.get("SHA256")).lower()
    if sha256 and not SHA256.fullmatch(sha256):
        # Empty, not free text: the Bench refuses to run an installer without a hash (module 10).
        log.warning("cadastro instaladores Id %s: sha256_invalido", linha.get("Id"))
        sha256 = ""
    return {
        "id": linha.get("Id"),
        "programa": texto(linha.get("Programa")),
        "versao": texto(linha.get("Versao")),
        "arquivo": texto(linha.get("Arquivo")),
        "sha256": sha256,
        "link": texto(linha.get("Link")),
        "observacao": texto(linha.get("Observacao")),
        "tipo": texto(linha.get("Tipo")) or "instalador",
        "categoria": texto(linha.get("Categoria")) or "Programas",
        "identificador": texto(linha.get("Identificador")),
        "argumentos": texto(linha.get("Argumentos")),
        "deteccao": texto(linha.get("Deteccao")),
        "modo": texto(linha.get("Modo")) or "quiosque",
    }


def rede(linha: dict) -> dict:
    return {
        "id": linha.get("Id"),
        "ssid": texto(linha.get("SSID")),
        "senha": SecretStr(texto(linha.get("Senha"))),
        "unidade": texto(linha.get("Unidade")),
        "categoria": texto(linha.get("categoria")),
        "atualizado_em": texto(linha.get("AtualizadoEm")),
    }


def unidade(linha: dict) -> dict:
    return {
        "id": linha.get("Id"),
        "codigo": texto(linha.get("Codigo")),
        "nome": texto(linha.get("Nome")),
        "cidade": texto(linha.get("Cidade")),
        "uf": texto(linha.get("UF")),
        "tag_glpi": texto(linha.get("TagGLPI")),
        "perfil_padrao": texto(linha.get("PerfilPadrao")),
    }
