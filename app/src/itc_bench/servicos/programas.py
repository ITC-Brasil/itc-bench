r"""Programas (ADR-020), sem Qt: instaladores, winget e Web Apps da tabela Instaladores.

Tudo pelo executor, com lista de argumentos. O log recebe programa, tipo, `Id`, versão, passo,
resultado e código; nunca `Link`, URL do Web App, caminho de perfil nem nome de usuário.
Usado pela tela Programas e pela Preparação completa (Módulo 13).
"""

import ctypes
import json
import re
import tempfile
import threading
import winreg
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path, PurePath, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

from itc_bench.nucleo import acl, versao
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, instaladores, remoto
from itc_bench.servicos.cadastros import Cadastros, Instalador

RECURSOS = resources.files("itc_bench.recursos") / "programas"
Rodar = Callable[..., executor.Resultado]
Avisar = Callable[[str], None]

Tipo = Literal["instalador", "winget", "webapp"]
Situacao = Literal[
    "instalado",
    "desatualizado",
    "mais_novo",
    "nao_instalado",
    "ambiguo",
    "desconhecido",
    "bloqueado",
]
Estado = Literal["ok", "reinicio", "falha", "cancelado", "em_execucao", "pulado"]

TIMEOUT_INSTALAR = 900
TIMEOUT_WINGET = 1800
TIMEOUT_LEITURA = 120
DESCRICAO_ATALHO = "ITC Bench"
DESINSTALACAO = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

ARGUMENTO = re.compile(r"^[A-Za-z0-9/_=.:+,{}-]+$")
PROPRIEDADE_MSI = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*=[A-Za-z0-9/_=.:+,{}-]*$")
WINGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{1,127}$")
URL_WEBAPP = re.compile(r"^https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?#][^\s\x00-\x1f\"'<>\\]*)?$")
NOME_PROIBIDO = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {
    f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
}
SID_USUARIO = re.compile(r"^S-1-5-21-[\d-]+$")
ARGUMENTOS_MODO = {
    "quiosque": ("--kiosk", "{url}", "--edge-kiosk-type=fullscreen", "--no-first-run"),
    "app": ("--app={url}", "--no-first-run"),
}

# Tabela fechada (doc oficial do winget, returnCodes.md); outro código vira falha com o hex.
WINGET_OK = {0: "", 0x8A150109: "reinício pendente"}
WINGET_ERROS = {
    0x8A150014: "O pacote não existe no winget (confira o ID no cadastro).",
    0x8A150061: "O pacote já está instalado.",
    0x8A15002B: "Não há atualização para este pacote.",
    0x8A150010: "O pacote não tem instalador para todos os usuários (escopo de máquina).",
    0x8A150008: "O download do winget falhou. Confira a rede.",
    0x8A150045: "O winget não abriu a origem. Confira a rede.",
    0x8A15004B: "O winget não abriu a origem. Confira a rede.",
    0x8A150107: "Sem rede para instalar este pacote.",
    0x8A150011: "O instalador baixado não confere com o manifesto do winget.",
    0x8A150101: "O programa está aberto. Feche e tente de novo.",
    0x8A150102: "Outra instalação em andamento. Espere terminar e tente de novo.",
    0x8A15010A: "Reinicie o computador e tente de novo.",
    0x8A150104: "Falta uma dependência do pacote.",
    0x8A150105: "Disco cheio.",
}
EXE_OK = {0: "", 3010: "reinício pendente"}


class ErroPrograma(Exception):
    """Mensagem para a tela; o log já recebeu só `Id` e motivo."""


# ---------------------------------------------------------------- lista (pura)


@dataclass(frozen=True)
class Item:
    linha: Instalador
    bloqueio: str = ""  # cadastro inválido ou duplicado: não instala

    @property
    def id(self) -> int:
        return self.linha.id

    @property
    def tipo(self) -> str:
        return self.linha.tipo

    @property
    def programa(self) -> str:
        return self.linha.programa

    @property
    def extensao(self) -> str:
        return PurePath(self.linha.arquivo.strip()).suffix.lower()

    @property
    def interativo(self) -> bool:
        return self.tipo == "instalador" and self.extensao == ".exe" and not self.linha.argumentos


def argumentos(linha: Instalador) -> list[str]:
    """Uma linha de `Argumentos` = um item da lista; nunca linha de comando em texto."""
    itens = [a.strip() for a in linha.argumentos.splitlines() if a.strip()]
    msi = PurePath(linha.arquivo.strip()).suffix.lower() == ".msi"
    for a in itens:
        if not (PROPRIEDADE_MSI if msi else ARGUMENTO).fullmatch(a):
            tipo = "PROPRIEDADE=valor" if msi else "letras, números e / _ = . : + , { } -"
            raise ErroPrograma(f"Argumento inválido em “{linha.programa}” (só {tipo}).")
    return itens


def tem_icone(linha: Instalador) -> bool:
    return any(x.strip() for x in (linha.link, linha.sha256, linha.arquivo))


def validar(linha: Instalador) -> str:
    """Motivo do cadastro inválido, ou vazio."""
    if linha.tipo == "instalador":
        if linha.programa in remoto.PROGRAMAS:
            return "É do Acesso remoto."
        ext = PurePath(linha.arquivo.strip()).suffix.lower()
        motivo = instaladores.validar(linha, ext if ext in (".msi", ".exe") else ".msi/.exe")
        if motivo:
            return motivo
        try:
            argumentos(linha)
        except ErroPrograma as erro:
            return str(erro)
        return ""
    if linha.tipo == "winget":
        ok = WINGET_ID.fullmatch(linha.identificador.strip())
        return "" if ok else f"ID do winget inválido em “{linha.programa}”."
    if linha.tipo == "webapp":
        if not url_valida(linha.identificador):
            return f"O endereço de “{linha.programa}” tem que ser https://."
        if linha.modo not in ARGUMENTOS_MODO:
            return f"Modo desconhecido em “{linha.programa}”."
        if nome_atalho(linha.programa) is None:
            return f"O nome “{linha.programa}” não serve para atalho."
        return (instaladores.validar(linha, ".ico") or "") if tem_icone(linha) else ""
    return "Tipo desconhecido."


def url_valida(url: str) -> bool:
    return bool(URL_WEBAPP.fullmatch(url)) and bool(urlsplit(url).hostname)


def nome_atalho(programa: str) -> str | None:
    """Nome do `.lnk`: sem caracteres proibidos, `..`, reservados nem ponto/espaço no fim."""
    nome = NOME_PROIBIDO.sub("", programa).strip()[:60].rstrip(". ")
    if not nome or ".." in nome or nome.split(".")[0].upper() in RESERVADOS:
        return None
    return nome + ".lnk"


def chave_duplicata(linha: Instalador) -> tuple[str, str]:
    if linha.tipo == "instalador":
        return linha.tipo, linha.programa.casefold()
    return linha.tipo, linha.identificador.strip().casefold()


def listar(cadastros: Cadastros | None) -> list[Item]:
    """Linhas de Programas (sem as do Acesso remoto), com o bloqueio de cada uma."""
    if cadastros is None:
        return []
    linhas = [
        i
        for i in cadastros.instaladores
        if not (i.tipo == "instalador" and i.programa in remoto.PROGRAMAS)
        and i.tipo != "papel"  # papel de parede é da tela Aparência (ADR-022)
    ]
    contagem = Counter(chave_duplicata(i) for i in linhas)
    itens = []
    for linha in linhas:
        if contagem[chave_duplicata(linha)] > 1:
            itens.append(Item(linha, "Cadastro duplicado em Instaladores."))
        else:
            itens.append(Item(linha, validar(linha)))
    return itens


# ---------------------------------------------------------------- registro e detecção


@dataclass(frozen=True)
class Instalado:
    """Entrada de `Uninstall`. `usuario`: veio de HKU (perfil carregado)."""

    chave: str
    nome: str
    versao: str
    usuario: bool
    valores: dict[str, str] = field(default_factory=dict, repr=False)


def _valores(chave: winreg.HKEYType) -> dict[str, str]:
    valores = {}
    for i in range(winreg.QueryInfoKey(chave)[1]):
        nome, dado, tipo = winreg.EnumValue(chave, i)
        if tipo == winreg.REG_EXPAND_SZ:
            dado = winreg.ExpandEnvironmentStrings(dado)
        valores[nome] = str(dado)
    return valores


def _raizes() -> Iterable[tuple[int, str, int, bool]]:
    for visao in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        yield winreg.HKEY_LOCAL_MACHINE, DESINSTALACAO, visao, False
    try:
        with winreg.OpenKey(winreg.HKEY_USERS, "") as usuarios:
            sids = [winreg.EnumKey(usuarios, i) for i in range(winreg.QueryInfoKey(usuarios)[0])]
    except OSError as erro:
        log.warning("Programas: HKU ilegível (%s)", type(erro).__name__)
        return
    for sid in sids:
        if SID_USUARIO.fullmatch(sid):
            yield winreg.HKEY_USERS, rf"{sid}\{DESINSTALACAO}", 0, True


def instalados() -> list[Instalado]:
    """`Uninstall` de 64 e 32 bits e dos perfis carregados."""
    saida: list[Instalado] = []
    for hive, caminho, visao, usuario in _raizes():
        try:
            raiz = winreg.OpenKey(hive, caminho, 0, winreg.KEY_READ | visao)
        except OSError:
            continue
        with raiz:
            for i in range(winreg.QueryInfoKey(raiz)[0]):
                nome_chave = winreg.EnumKey(raiz, i)
                try:
                    with winreg.OpenKey(raiz, nome_chave) as k:
                        valores = _valores(k)
                except OSError:
                    continue
                nome = valores.get("DisplayName", "").strip()
                if not nome:
                    continue
                saida.append(
                    Instalado(nome_chave, nome, valores.get("DisplayVersion", ""), usuario, valores)
                )
    return saida


def produto_msi(caminho: Path) -> str | None:
    """`ProductCode` do `.msi` (tabela Property), pela `msi.dll`; None se ilegível."""
    msi = ctypes.WinDLL("msi")
    banco, visao_, registro = (ctypes.c_ulong() for _ in range(3))
    try:
        if msi.MsiOpenDatabaseW(str(caminho), None, ctypes.byref(banco)):
            return None
        consulta = "SELECT `Value` FROM `Property` WHERE `Property`='ProductCode'"
        if msi.MsiDatabaseOpenViewW(banco, consulta, ctypes.byref(visao_)):
            return None
        if msi.MsiViewExecute(visao_, 0) or msi.MsiViewFetch(visao_, ctypes.byref(registro)):
            return None
        buffer = ctypes.create_unicode_buffer(64)
        tamanho = ctypes.c_ulong(len(buffer))
        if msi.MsiRecordGetStringW(registro, 1, buffer, ctypes.byref(tamanho)):
            return None
        return buffer.value or None
    finally:
        for h in (registro, visao_, banco):
            if h.value:
                msi.MsiCloseHandle(h)


@dataclass(frozen=True)
class Deteccao:
    situacao: Situacao
    instalada: str = ""
    motivo: str = ""


def _por_versao(instalada: str, cadastro: str) -> Deteccao:
    comp = versao.comparar(instalada, cadastro) if cadastro else "igual"
    mapa: dict[str, Situacao] = {
        "igual": "instalado",
        "velha": "desatualizado",
        "nova": "mais_novo",
        "ausente": "nao_instalado",
    }
    sit = mapa[comp]
    return Deteccao(sit, instalada)


def detectar_registro(item: Item, lista: list[Instalado], produto: str | None) -> Deteccao:
    """MSI pelo `ProductCode` do arquivo; senão `Deteccao`/`Programa` como prefixo."""
    if produto:
        achados = [i for i in lista if i.chave.upper() == produto.upper()]
    else:
        prefixo = (item.linha.deteccao or item.programa).strip().casefold()
        achados = [i for i in lista if i.nome.casefold().startswith(prefixo)]
    if not achados:
        return Deteccao("nao_instalado")
    if len({(a.nome, a.versao) for a in achados}) > 1:
        return Deteccao("ambiguo", motivo="Mais de um programa instalado casa com este nome.")
    return _por_versao(achados[0].versao, item.linha.versao)


# ---------------------------------------------------------------- winget


def script(nome: str) -> str:
    return (RECURSOS / f"{nome}.ps1").read_text("utf-8")


def winget(*, rodar: Rodar = executor.powershell) -> Path | str:
    """`winget.exe` do pacote, assinado pela Microsoft; ou o motivo de não usar."""
    r = rodar(script("winget"), timeout=TIMEOUT_LEITURA)
    try:
        lido = json.loads(r.saida) if r.ok else {}
    except json.JSONDecodeError:
        lido = {}
    caminho = str(lido.get("caminho") or "") if isinstance(lido, dict) else ""
    if not caminho:
        return "winget indisponível neste Windows (App Installer ausente)."
    pasta = PureWindowsPath(caminho)
    bases = (remoto.program_files() / "WindowsApps", remoto.windows() / "SystemApps")
    if not any(pasta.is_relative_to(PureWindowsPath(b)) for b in bases):
        log.error("Programas: winget fora das pastas de pacotes do Windows")
        return "winget fora da pasta de pacotes do Windows."
    if not (lido.get("valida") is True and lido.get("microsoft") is True):
        log.error("Programas: assinatura do winget não confere")
        return "A assinatura do winget não confere (Microsoft)."
    return Path(caminho)


def winget_instalados(exe: Path, *, executar: Rodar = executor.executar) -> dict[str, str]:
    """ID (minúsculo) → versão, pelo `winget export` em JSON (não depende do idioma)."""
    # Lista de pacotes instalados (não é segredo); pasta temporária funciona sem admin (--dev).
    with tempfile.TemporaryDirectory(prefix="itc-winget-") as pasta:
        return _export(exe, Path(pasta) / "winget.json", executar)


def _export(exe: Path, saida: Path, executar: Rodar) -> dict[str, str]:
    try:
        r = executar(
            [
                str(exe),
                "export",
                "-o",
                str(saida),
                "--source",
                "winget",
                "--include-versions",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout=TIMEOUT_LEITURA,
            descricao="winget export",
        )
        if r.esgotado or not saida.is_file():
            log.warning("Programas: winget export sem arquivo (código %s)", r.codigo)
            return {}
        dados = json.loads(saida.read_text("utf-8-sig"))
        pacotes = [p for s in dados.get("Sources", []) for p in s.get("Packages", [])]
        return {str(p["PackageIdentifier"]).casefold(): str(p.get("Version", "")) for p in pacotes}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as erro:
        log.warning("Programas: winget export ilegível (%s)", type(erro).__name__)
        return {}
    finally:
        saida.unlink(missing_ok=True)


def comando_winget(exe: Path, pacote: str) -> list[str]:
    return [
        str(exe),
        "install",
        "--id",
        pacote,
        "-e",
        "--source",
        "winget",
        "--scope",
        "machine",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


# ---------------------------------------------------------------- Web Apps


def area_publica() -> Path:
    return remoto.pasta_conhecida(0x19)  # CSIDL_COMMON_DESKTOPDIRECTORY


def edge() -> Path | None:
    """`msedge.exe` de App Paths, só dentro de Program Files."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        ) as k:
            caminho = Path(str(winreg.QueryValueEx(k, "")[0]).strip().strip('"'))
    except OSError:
        return None
    bases = (remoto.program_files(), remoto.program_files_x86())
    dentro = any(caminho.is_relative_to(b) for b in bases)
    return caminho if dentro and caminho.is_file() else None


def argumentos_webapp(linha: Instalador) -> list[str]:
    url = linha.identificador.strip()
    if not url_valida(url) or linha.modo not in ARGUMENTOS_MODO:
        raise ErroPrograma(f"Cadastro do Web App “{linha.programa}” inválido.")
    return [a.replace("{url}", url) for a in ARGUMENTOS_MODO[linha.modo]]


def atalhos(*, rodar: Rodar = executor.powershell, pasta: Path | None = None) -> dict[str, str]:
    """Nome do `.lnk` → descrição, no Desktop Público."""
    r = rodar(
        script("atalho"), timeout=TIMEOUT_LEITURA, acao="listar", pasta=str(pasta or area_publica())
    )
    try:
        lido = json.loads(r.saida) if r.ok and r.saida.strip() else []
    except json.JSONDecodeError:
        lido = []
    if isinstance(lido, dict):
        lido = [lido]
    return {str(a.get("nome")): str(a.get("descricao") or "") for a in lido if isinstance(a, dict)}


# ---------------------------------------------------------------- situação


@dataclass(frozen=True)
class Linha:
    """Item e situação, para a tela."""

    item: Item
    situacao: Situacao
    instalada: str = ""
    motivo: str = ""


def situacao(
    itens: list[Item],
    *,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    ler_registro: Callable[[], list[Instalado]] = instalados,
    produto: Callable[[Path], str | None] = produto_msi,
) -> tuple[list[Linha], str]:
    """Situação de cada item e o motivo de o winget estar fora (vazio se está ok)."""
    lista = ler_registro()
    precisa_winget = any(i.tipo == "winget" and not i.bloqueio for i in itens)
    exe = winget(rodar=rodar) if precisa_winget else ""
    sem_winget = exe if isinstance(exe, str) else ""
    do_winget = winget_instalados(exe, executar=executar) if isinstance(exe, Path) else {}
    lnk = atalhos(rodar=rodar) if any(i.tipo == "webapp" for i in itens) else {}
    linhas = []
    for item in itens:
        if item.bloqueio:
            linhas.append(Linha(item, "bloqueado", motivo=item.bloqueio))
        elif item.tipo == "instalador":
            codigo = None
            if item.extensao == ".msi":
                guardado = instaladores.guardado(item.linha, ".msi")
                codigo = produto(guardado) if guardado else None
            e = detectar_registro(item, lista, codigo)
            linhas.append(Linha(item, e.situacao, e.instalada, e.motivo))
        elif item.tipo == "winget":
            if sem_winget:
                linhas.append(Linha(item, "bloqueado", motivo=sem_winget))
                continue
            instalada = do_winget.get(item.linha.identificador.strip().casefold())
            if instalada is None:
                linhas.append(Linha(item, "nao_instalado"))
            else:
                w = _por_versao(instalada, item.linha.versao)
                linhas.append(Linha(item, w.situacao, w.instalada))
        else:
            nome = nome_atalho(item.programa) or ""
            if nome not in lnk:
                linhas.append(Linha(item, "nao_instalado"))
            elif lnk[nome] != DESCRICAO_ATALHO:
                motivo = "Já existe um atalho com este nome que não é do Bench."
                linhas.append(Linha(item, "bloqueado", motivo=motivo))
            else:
                linhas.append(Linha(item, "instalado"))
    return linhas, sem_winget


# ---------------------------------------------------------------- instalação


@dataclass(frozen=True)
class Resultado:
    item: Item
    estado: Estado
    mensagem: str


def _codigo(r: executor.Resultado) -> int:
    return (r.codigo or 0) & 0xFFFFFFFF


def _instalador(
    item: Item,
    origem: Path | None,
    *,
    cancelar: threading.Event | None,
    executar: Rodar,
    progresso: instaladores.Progresso | None,
) -> Resultado:
    linha, ext = item.linha, item.extensao
    args = argumentos(linha)
    if origem is not None:
        arquivo = instaladores.copiar(linha, ext, origem, cancelar=cancelar)
    else:
        arquivo = instaladores.obter(linha, ext, cancelar=cancelar, progresso=progresso)
    if not instaladores.conferir(arquivo, linha.sha256):
        log.error("Programas: Id %s com SHA-256 diferente antes de executar", linha.id)
        raise ErroPrograma(f"O arquivo de “{linha.programa}” não confere com o cadastro.")
    if ext == ".msi":
        comando = [executor.sistema32("msiexec.exe"), "/i", str(arquivo), "/qn", "/norestart"]
        ok, erros = remoto.MSI_OK, remoto.MSI_ERROS
    else:
        comando, ok, erros = [str(arquivo)], EXE_OK, {}
    r = executar(
        [*comando, *args],
        timeout=TIMEOUT_INSTALAR,
        encerrar_no_timeout=False,
        descricao=f"instalador Id {linha.id} ({ext}, {len(args)} argumento(s))",
    )
    return _fim(item, r, ok, erros)


def _winget(item: Item, exe: Path, *, executar: Rodar) -> Resultado:
    pacote = item.linha.identificador.strip()
    r = executar(
        comando_winget(exe, pacote),
        timeout=TIMEOUT_WINGET,
        encerrar_no_timeout=False,
        descricao=f"winget install {pacote}",
    )
    return _fim(item, r, WINGET_OK, WINGET_ERROS)


def _fim(item: Item, r: executor.Resultado, ok: dict[int, str], erros: dict[int, str]) -> Resultado:
    nome = item.programa
    if r.esgotado:
        log.error("Programas: Id %s ainda em execução no fim do tempo", item.id)
        return Resultado(item, "em_execucao", f"{nome}: ainda em execução, confira depois.")
    codigo = _codigo(r)
    if codigo in ok:
        estado: Estado = "reinicio" if ok[codigo] else "ok"
        log.info("Programas: Id %s (%s %s): %s", item.id, item.tipo, item.linha.versao, estado)
        sufixo = " Reinicie o computador para concluir." if ok[codigo] else ""
        return Resultado(item, estado, f"{nome} instalado.{sufixo}")
    log.error("Programas: Id %s (%s): código %#x", item.id, item.tipo, codigo)
    texto = erros.get(codigo, f"falhou (código {codigo:#x}).")
    return Resultado(item, "falha", f"{nome}: {texto}")


def _webapp(item: Item, *, rodar: Rodar, cancelar: threading.Event | None) -> Resultado:
    linha = item.linha
    nome = nome_atalho(linha.programa)
    alvo = edge()
    if nome is None or alvo is None:
        raise ErroPrograma("Microsoft Edge não encontrado em Program Files.")
    pasta = area_publica()
    existente = atalhos(rodar=rodar, pasta=pasta).get(nome)
    if existente is not None and existente != DESCRICAO_ATALHO:
        raise ErroPrograma(f"Já existe o atalho “{nome}” e ele não é do Bench.")
    icone = ""
    if tem_icone(linha):
        base = instaladores.icones()
        base.mkdir(parents=True, exist_ok=True)
        acl.proteger(base, acl.SDDL)  # Usuários leem; só Admin/SYSTEM gravam (ADR-020)
        icone = str(instaladores.obter(linha, ".ico", base=base, cancelar=cancelar))
    r = rodar(
        script("atalho"),
        timeout=TIMEOUT_LEITURA,
        acao="criar",
        pasta=str(pasta),
        nome=nome,
        alvo=str(alvo),
        # URL validada sem espaço nem aspas: juntar por espaço não precisa de aspas.
        argumentos=" ".join(argumentos_webapp(linha)),
        icone=icone,
    )
    if not (r.ok and "OK" in r.saida.split()):
        log.error("Programas: Id %s: atalho não criado (código %s)", item.id, r.codigo)
        raise ErroPrograma(f"Não foi possível criar o atalho de “{linha.programa}”.")
    log.info("Programas: Id %s (webapp, %s): ok", item.id, linha.modo)
    return Resultado(item, "ok", f"Atalho de {linha.programa} criado.")


def ordenar(itens: Iterable[Item]) -> list[Item]:
    ordem = {"instalador": 0, "winget": 1, "webapp": 2}
    return sorted(itens, key=lambda i: ordem.get(i.tipo, 3))


def instalar(
    itens: Iterable[Item],
    *,
    origens: dict[int, Path] | None = None,
    avisar: Avisar = lambda _t: None,
    cancelar: threading.Event | None = None,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    progresso: instaladores.Progresso | None = None,
) -> list[Resultado]:
    """Lote: instaladores, winget, Web Apps. Um falhou, os outros seguem; cancela entre itens.

    Item ainda em execução no fim do tempo: pula os instaladores e winget seguintes (podem usar o
    Windows Installer) e segue só com Web Apps (ADR-020).
    """
    origens = origens or {}
    lista = ordenar(itens)
    exe: Path | str | None = None
    travado = ""
    resultados: list[Resultado] = []
    for n, item in enumerate(lista, 1):
        if cancelar is not None and cancelar.is_set():
            resultados.append(Resultado(item, "cancelado", "Cancelado antes de começar."))
            continue
        if item.bloqueio:
            resultados.append(Resultado(item, "pulado", item.bloqueio))
            continue
        if travado and item.tipo != "webapp":
            resultados.append(Resultado(item, "pulado", travado))
            continue
        avisar(f"[{n}/{len(lista)}] {item.programa}…")
        log.info("Programas: Id %s (%s): instalando", item.id, item.tipo)
        try:
            if item.tipo == "instalador":
                res = _instalador(
                    item,
                    origens.get(item.id),
                    cancelar=cancelar,
                    executar=executar,
                    progresso=progresso,
                )
            elif item.tipo == "winget":
                if exe is None:
                    exe = winget(rodar=rodar)
                if isinstance(exe, str):
                    raise ErroPrograma(exe)
                res = _winget(item, exe, executar=executar)
            else:
                res = _webapp(item, rodar=rodar, cancelar=cancelar)
        except instaladores.Cancelado:
            log.warning("Programas: Id %s: cancelado pelo técnico", item.id)
            res = Resultado(item, "cancelado", "Cancelado pelo técnico.")
        except (ErroPrograma, instaladores.ErroInstalador, acl.ErroAcl) as erro:
            log.error("Programas: Id %s (%s): %s", item.id, item.tipo, type(erro).__name__)
            res = Resultado(item, "falha", str(erro))
        if res.estado == "em_execucao":
            travado = f"Não iniciado: {item.programa} ainda estava em execução."
        resultados.append(res)
    return resultados


def resumo(estados: Iterable[str]) -> str:
    """Contagem por estado, para a tela (também usada em Remover programas)."""
    contagem = Counter(estados)
    nomes: dict[Estado, str] = {
        "ok": "ok",
        "reinicio": "com reinício pendente",
        "falha": "com falha",
        "cancelado": "cancelado(s)",
        "em_execucao": "ainda em execução",
        "pulado": "não iniciado(s)",
    }
    return ", ".join(f"{contagem[k]} {v}" for k, v in nomes.items() if contagem[k])
