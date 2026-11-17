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
    "wifi": ("nocodb_tabela_wifi", ("Id", "SSID", "Senha", "Unidade", "Categoria", "Ativo", "AtualizadoEm"), "SSID"),
    "unidades": (
        "nocodb_tabela_unidades",
        # TA-ADR-039: Cidade and TagGLPI are no longer read (the columns may be deleted).
        ("Id", "Codigo", "Nome", "UF", "PerfilPadrao", "Ativo"),
        "Codigo",
    ),
    # TA-ADR-036: optional. Only read when nocodb_tabela_projetos is set; then Unidades and
    # Instaladores also read their Projeto column (the sigla of a Projetos row, TA-ADR-035).
    "projetos": ("nocodb_tabela_projetos", ("Id", "Sigla", "Nome", "Ativo"), "Sigla"),
    # TA-ADR-037: optional. Configuração profiles: which of the 12 numbered steps run.
    "perfis": (
        "nocodb_tabela_perfis",
        ("Id", "Codigo", "Nome", "Etapas", "Descricao", "Ativo"),
        "Codigo",
    ),
}
OPCIONAIS = ("projetos", "perfis")
# Steps of the Bench Configuração, numbered 1..12 (ADR-062; was 1..14, ADR-056). The API only
# checks the range; the Bench maps numbers to steps.
TOTAL_ETAPAS = 12
CODIGO_PERFIL = re.compile(r"[a-z0-9_]{1,32}")


class NocodbIndisponivel(Exception):
    """code: timeout, indisponivel, http_<status> or resposta_invalida. Never URL or token."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def configurado(settings) -> bool:
    token = settings.nocodb_cadastros_token.get_secret_value().strip()
    ids = all(getattr(settings, TABELAS[nome][0]).strip() for nome in TABELAS if nome not in OPCIONAIS)
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
        com_projetos = bool(settings.nocodb_tabela_projetos.strip())
        for nome, (id_setting, campos, _) in TABELAS.items():
            if nome in OPCIONAIS and not getattr(settings, id_setting).strip():
                brutos[nome] = []
                continue
            if nome in ("unidades", "instaladores", "perfis", "wifi") and com_projetos:
                campos = (*campos, "Projeto")
            # TA-ADR-038: WiFi.Perfis only exists together with the Perfis table.
            if nome == "wifi" and settings.nocodb_tabela_perfis.strip():
                campos = (*campos, "Perfis")
            url = f"{settings.nocodb_url.rstrip('/')}/api/v2/tables/{getattr(settings, id_setting).strip()}/records"
            try:
                brutos[nome] = paginas(client, url, headers, campos, inicio)
            except NocodbIndisponivel as erro:
                # Table name only in the API log (e.g. instaladores:http_400), never to the Bench.
                raise NocodbIndisponivel(f"{nome}:{erro.code}") from None
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
        for linha in brutos.get(nome, []):
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

    projetos = [projeto(linha) for linha in validos["projetos"]]
    siglas = {p["sigla"] for p in projetos}
    unidades = [unidade(linha) for linha in validos["unidades"]]
    for u in unidades:
        # TA-ADR-036: an unknown sigla keeps the unit, without a project, and is logged.
        if u["projeto"] and u["projeto"] not in siglas:
            log.warning("cadastro unidades Id %s: projeto_invalido", u["id"])
            u["projeto"] = ""
    codigos = {u["codigo"] for u in unidades}
    instaladores = []
    for linha in validos["instaladores"]:
        motivo = motivo_instalador(linha)
        # TA-ADR-035: a papel row names its project; an unknown sigla drops the row.
        if not motivo and papel_projeto(linha) not in siglas | {""}:
            motivo = "projeto_invalido"
        if motivo:
            descartados.setdefault("instaladores", []).append(linha.get("Id"))
            log.warning("cadastro instaladores Id %s descartado: %s", linha.get("Id"), motivo)
            continue
        instaladores.append(instalador(linha))

    perfis_ = perfis(validos["perfis"], siglas, descartados)
    codigos_perfil = {p["codigo"] for p in perfis_}
    wifi = []
    for linha in validos["wifi"]:
        motivo = motivo_rede(linha, siglas, codigos, codigos_perfil)
        if motivo:
            descartados.setdefault("wifi", []).append(linha.get("Id"))
            log.warning("cadastro wifi Id %s descartado: %s", linha.get("Id"), motivo)
            continue
        wifi.append(rede(linha))
    return {
        "servidores": [servidor(linha) for linha in validos["servidores"]],
        "instaladores": instaladores,
        "wifi": wifi,
        "unidades": unidades,
        "projetos": projetos,
        "perfis": perfis_,
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
    sha256 = texto(linha.get("SHA256")).lower()
    # TA-ADR-034: SHA256 is optional; a filled-in but invalid one is a typo and drops the row.
    if tipo == "papel" and not (
        ARQUIVO_PAPEL.fullmatch(texto(linha.get("Arquivo")))
        and (not sha256 or SHA256.fullmatch(sha256))
        and URL_WEBAPP.fullmatch(texto(linha.get("Link")))
    ):
        return "papel_invalido"
    return None


def instalador(linha: dict) -> dict:
    sha256 = texto(linha.get("SHA256")).lower()
    if sha256 and not SHA256.fullmatch(sha256):
        # Empty, not free text: without a hash the Bench computes its own (ADR-028, TA-ADR-034).
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
        "projeto": papel_projeto(linha),
    }


def papel_projeto(linha: dict) -> str:
    """Projeto of a papel row (TA-ADR-035): empty = none. Other Tipos ignore the column."""
    tipo = texto(linha.get("Tipo")) or "instalador"
    return texto(linha.get("Projeto")) if tipo == "papel" else ""


def rede(linha: dict) -> dict:
    return {
        "id": linha.get("Id"),
        "ssid": texto(linha.get("SSID")),
        "senha": SecretStr(texto(linha.get("Senha"))),
        "unidade": texto(linha.get("Unidade")),
        "projeto": texto(linha.get("Projeto")),
        "perfis": lista_perfis(linha),
        "categoria": texto(linha.get("Categoria")),
        "atualizado_em": texto(linha.get("AtualizadoEm")),
    }


def lista_perfis(linha: dict) -> list[str]:
    """WiFi.Perfis (TA-ADR-038): Perfis codes split by comma, semicolon or space, lowercase,
    sorted and unique. Empty = every profile."""
    partes = re.split(r"[,;\s]+", texto(linha.get("Perfis")).lower())
    return sorted({p for p in partes if p})


def motivo_rede(linha: dict, siglas: set[str], codigos: set[str], perfis_: set[str]) -> str:
    """TA-ADR-038: with Projeto the project rules (Unidade is just a note); without it, the old
    rule (an active Unidade). An unknown profile drops the network: giving it to everyone would
    be worse."""
    projeto_ = texto(linha.get("Projeto"))
    if projeto_:
        if projeto_ not in siglas:
            return "projeto_invalido"
    elif texto(linha.get("Unidade")) not in codigos:
        return "unidade_invalida"
    if any(p not in perfis_ for p in lista_perfis(linha)):
        return "perfil_invalido"
    return ""


def unidade(linha: dict) -> dict:
    return {
        "id": linha.get("Id"),
        "codigo": texto(linha.get("Codigo")),
        "nome": texto(linha.get("Nome")),
        "cidade": "",  # TA-ADR-039: kept empty for the Bench 0.19.0, which expects the key
        "uf": texto(linha.get("UF")),
        "tag_glpi": "",  # TA-ADR-039: idem; the GLPI Agent goes without TAG
        "perfil_padrao": texto(linha.get("PerfilPadrao")),
        "projeto": texto(linha.get("Projeto")),
    }


def projeto(linha: dict) -> dict:
    return {
        "id": linha.get("Id"),
        "sigla": texto(linha.get("Sigla")),
        "nome": texto(linha.get("Nome")),
    }


def perfis(linhas: list[dict], siglas: set[str], descartados: dict) -> list[dict]:
    """TA-ADR-037: Codigo [a-z0-9_]{1,32} and unique; Etapas = numbers 1..12 (comma, semicolon or
    space); Projeto empty or an active sigla. A bad row is dropped, logged by Id only."""
    saida, vistos = [], {}
    for linha in linhas:
        codigo = texto(linha.get("Codigo")).lower()
        numeros = etapas(texto(linha.get("Etapas")))
        projeto_ = texto(linha.get("Projeto"))
        motivo = (
            "codigo_invalido" if not CODIGO_PERFIL.fullmatch(codigo)
            else "etapas_invalidas" if numeros is None
            else "projeto_invalido" if projeto_ and projeto_ not in siglas
            else None
        )
        if motivo:
            descartados.setdefault("perfis", []).append(linha.get("Id"))
            log.warning("cadastro perfis Id %s descartado: %s", linha.get("Id"), motivo)
            continue
        vistos[codigo] = vistos.get(codigo, 0) + 1
        saida.append(
            {
                "id": linha.get("Id"),
                "codigo": codigo,
                "nome": texto(linha.get("Nome")) or codigo,
                "etapas": numeros,
                "projeto": projeto_,
                "descricao": texto(linha.get("Descricao")),
            }
        )
    # Two rows with the same Codigo: neither is used (which one would Unidades.PerfilPadrao mean?).
    for p in saida:
        if vistos[p["codigo"]] > 1:
            descartados.setdefault("perfis", []).append(p["id"])
            log.warning("cadastro perfis Id %s descartado: codigo_duplicado", p["id"])
    return [p for p in saida if vistos[p["codigo"]] == 1]


def etapas(valor: str) -> list[int] | None:
    """"1, 2,3;12" -> [1, 2, 3, 12] (sorted, unique). None if empty or any part is not 1..12."""
    partes = [p for p in re.split(r"[,;\s]+", valor) if p]
    if not partes or not all(p.isdigit() and 1 <= int(p) <= TOTAL_ETAPAS for p in partes):
        return None
    return sorted({int(p) for p in partes})
