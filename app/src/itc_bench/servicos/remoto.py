"""Acesso remoto (ADR-019), sem Qt: GLPI Agent, RustDesk e AnyDesk. A tela e o 13 usam.

Dados de Servidores (contrato no ADR-019), instaladores por `servicos/instaladores.py`, processos
só pelo executor. Senhas nunca em argumento: AnyDesk pela entrada padrão; RustDesk pela linha
`password` do `RustDesk.toml` do serviço, que o próprio RustDesk regrava cifrada. O log recebe
programa, versão, passo, resultado e `Id`; nunca senha, chave, URL, host, tag, link ou ID remoto.
"""

import contextlib
import ctypes
import hmac
import ipaddress
import json
import os
import re
import stat
import threading
import time
import tomllib
import urllib.request
import winreg
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from itc_bench.nucleo import versao as _versao
from itc_bench.nucleo.log import log
from itc_bench.servicos import cadastros as cad
from itc_bench.servicos import executor, instaladores
from itc_bench.servicos.cadastros import Cadastros, Instalador
from itc_bench.servicos.executor import Sensivel

RECURSOS = resources.files("itc_bench.recursos") / "remoto"
Rodar = Callable[..., executor.Resultado]
Avisar = Callable[[str], None]

Programa = Literal["GLPI Agent", "RustDesk", "AnyDesk"]
PROGRAMAS: tuple[Programa, ...] = ("GLPI Agent", "RustDesk", "AnyDesk")
EXTENSAO: dict[Programa, str] = {"GLPI Agent": ".msi", "RustDesk": ".msi", "AnyDesk": ".exe"}
SERVICO: dict[Programa, str] = {
    "GLPI Agent": "glpi-agent",
    "RustDesk": "RustDesk",
    "AnyDesk": "AnyDesk",
}
NOME_DESINSTALACAO: dict[Programa, str] = {
    "GLPI Agent": "GLPI Agent",
    "RustDesk": "RustDesk",
    "AnyDesk": "AnyDesk",
}

TIMEOUT_INSTALAR = 600
TIMEOUT_LEITURA = 30
ESPERA_SERVICO = 90  # segundos de polling
ESPERA_CIFRAR = 20
URL_INVENTARIO = "http://127.0.0.1:62354/now"  # endpoint local do GLPI Agent
CHAVE_GLPI = r"SOFTWARE\GLPI-Agent"
DESINSTALACAO = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

HOST = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
CHAVE_RUSTDESK = re.compile(r"^[A-Za-z0-9+/]{43}=$")
SEM_ESPACO_NEM_ASPAS = re.compile(r'^[^\s"\']+$')
ID_REMOTO = re.compile(r"^\d[\d ]{5,15}$")

MSI_OK = {0: "", 3010: "reinício pendente", 1641: "reinício pendente"}
MSI_ERROS = {
    1618: "Outra instalação do Windows está em andamento. Espere terminar e tente de novo.",
    1603: "O instalador falhou (erro fatal 1603).",
    1619: "O Windows não conseguiu abrir o instalador (1619).",
}

Comparacao = _versao.Comparacao


class ErroRemoto(Exception):
    """Mensagem para a tela; o log já recebeu só o código."""


# ---------------------------------------------------------------- dados do cadastro (puros)


@dataclass(frozen=True)
class Dados:
    programa: Programa
    instalador: Instalador
    servidor: str = ""  # GLPI: URL; RustDesk: host. Público.
    tag: str = ""  # GLPI, opcional
    chave: Sensivel | None = None  # RustDesk
    senha: Sensivel | None = None  # RustDesk e AnyDesk
    avisos: tuple[str, ...] = ()
    api: str = ""  # RustDesk, opcional (ADR-030): URL https:// do "Servidor da API". Público.


def _linha(cadastros: Cadastros, servico: str, papel: str, publico: bool) -> cad.Servidor | str:
    linhas = [s for s in cadastros.servidores if s.servico == servico and s.papel == papel]
    tipo = "pública" if publico else "não pública"
    if not linhas:
        return f"Cadastre “{servico}” / {papel} ({tipo}) em Servidores e sincronize."
    if len(linhas) > 1:
        return f"Há mais de uma linha “{servico}” / {papel} em Servidores."
    s = linhas[0]
    if s.publico != publico:
        return f"A linha “{servico}” / {papel} tem que ser {tipo} em Servidores."
    valor = s.valor.revelar() if isinstance(s.valor, Sensivel) else s.valor
    if not valor.strip():
        return f"A linha “{servico}” / {papel} está vazia em Servidores."
    return s


def _texto(s: cad.Servidor) -> str:
    return (s.valor.revelar() if isinstance(s.valor, Sensivel) else s.valor).strip()


def validar_url_glpi(url: str) -> str | None:
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return "A URL do “GLPI Agent” / servidor tem que começar com http:// ou https://."
    if not SEM_ESPACO_NEM_ASPAS.fullmatch(url):
        return "A URL do “GLPI Agent” / servidor não pode ter espaço nem aspas."
    return None


def validar_url_api_rustdesk(url: str) -> str | None:
    """`RustDesk` / `api` (ADR-030): só `https://` com host, sem credencial, query nem fragmento."""
    partes = urlsplit(url)
    if (
        partes.scheme != "https"
        or not partes.hostname
        or partes.username is not None
        or partes.password is not None
        or partes.query
        or partes.fragment
        or not SEM_ESPACO_NEM_ASPAS.fullmatch(url)
    ):
        return (
            "A “RustDesk” / api tem que ser uma URL https:// com o nome do servidor, sem "
            "usuário, senha, espaço, aspas, ? nem #."
        )
    return None


def validar_host(host: str) -> bool:
    with contextlib.suppress(ValueError):
        return ipaddress.ip_address(host).version == 4
    return bool(HOST.fullmatch(host)) and not host.replace(".", "").isdigit()


def dados(
    cadastros: Cadastros | None, programa: Programa, unidade: str | None = None
) -> Dados | str:
    """Tudo o que o programa precisa, ou a mensagem do que falta (ADR-008, ADR-019)."""
    if cadastros is None:
        return "Sem cadastros: conecte, entre e sincronize."
    inst = instaladores.do_cadastro(cadastros, programa)
    if isinstance(inst, str):
        return inst
    motivo = instaladores.validar(inst, EXTENSAO[programa])
    if motivo:
        return motivo

    def pegar(servico: str, papel: str, publico: bool) -> cad.Servidor:
        r = _linha(cadastros, servico, papel, publico)
        if isinstance(r, str):
            raise ErroRemoto(r)
        return r

    try:
        if programa == "GLPI Agent":
            linha = pegar("GLPI Agent", "servidor", True)
            url = _texto(linha)
            if erro := validar_url_glpi(url):
                return erro
            avisos = []
            if url.startswith("http://"):
                avisos.append("O servidor do GLPI está em http:// (sem criptografia), provisório.")
            u = cadastros.unidade_por_codigo(unidade)
            tag = u.tag_glpi.strip() if u is not None else ""
            if tag and not SEM_ESPACO_NEM_ASPAS.fullmatch(tag):
                return "A TagGLPI da unidade não pode ter espaço nem aspas."
            return Dados(programa, inst, servidor=url, tag=tag, avisos=tuple(avisos))
        if programa == "RustDesk":
            host = _texto(pegar("RustDesk", "servidor", True))
            if not validar_host(host):
                return "O “RustDesk” / servidor tem que ser só o nome ou o IPv4, sem porta."
            chave = _texto(pegar("RustDesk", "chave", False))
            if not CHAVE_RUSTDESK.fullmatch(chave):
                return (
                    "A “RustDesk” / chave tem que ser a chave pública do servidor (44 caracteres)."
                )
            senha = _texto(pegar("RustDesk", "senha", False))
            api = ""
            if any(s.servico == "RustDesk" and s.papel == "api" for s in cadastros.servidores):
                api = _texto(pegar("RustDesk", "api", True))  # opcional: só se cadastrada
                if erro := validar_url_api_rustdesk(api):
                    return erro
            return Dados(
                programa,
                inst,
                servidor=host,
                chave=Sensivel(chave),
                senha=Sensivel(senha),
                api=api,
            )
        senha = _texto(pegar("AnyDesk", "senha", False))
        return Dados(programa, inst, senha=Sensivel(senha))
    except ErroRemoto as erro:
        return str(erro)


# ---------------------------------------------------------------- versão (pura)


versao = _versao.versao
comparar = _versao.comparar


# ---------------------------------------------------------------- TOML do RustDesk (puro)


def toml_texto(valor: str) -> str:
    """String básica TOML: o `json.dumps` escapa `"`, `\\` e controles de forma compatível."""
    return json.dumps(valor)


def _toml_valor(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int | float):
        return repr(valor)
    if isinstance(valor, str):
        return toml_texto(valor)
    if isinstance(valor, list):
        return "[" + ", ".join(_toml_valor(v) for v in valor) + "]"
    raise ErroRemoto(f"Valor TOML não suportado ({type(valor).__name__}).")


def _toml(dados_: dict[str, Any]) -> str:
    linhas = [
        f"{json.dumps(k)} = {_toml_valor(v)}" for k, v in dados_.items() if not isinstance(v, dict)
    ]
    for nome, tabela in dados_.items():
        if isinstance(tabela, dict):
            linhas += ["", f"[{json.dumps(nome)}]"]
            for k, v in tabela.items():
                if isinstance(v, dict):
                    raise ErroRemoto("Tabela aninhada no TOML do RustDesk não suportada.")
                linhas.append(f"{json.dumps(k)} = {_toml_valor(v)}")
    return "\n".join(linhas) + "\n"


def rustdesk2(existente: str | None, host: str, chave: str, api: str = "") -> str:
    """`RustDesk2.toml` com o servidor do cadastro, preservando as outras chaves (ADR-019).

    `api` vazia não mexe em `api-server` (fica o que já estava); preenchida, grava (ADR-030).
    """
    try:
        atual = tomllib.loads(existente or "")
    except tomllib.TOMLDecodeError:
        log.warning("Acesso remoto: RustDesk2.toml ilegível; reescrito só com o do Bench")
        atual = {}
    atual.update(
        {
            "rendezvous_server": f"{host}:21116",
            "relay_server": f"{host}:21117",
            "nat_type": 1,
            "serial": 0,
        }
    )
    opcoes = atual.get("options")
    if not isinstance(opcoes, dict):
        opcoes = {}
    opcoes.update(
        {
            "custom-rendezvous-server": host,
            "relay-server": host,
            "key": chave,
            "direct-server": "Y",
            "direct-access-port": "21118",
        }
    )
    if api:
        opcoes["api-server"] = api
    atual["options"] = opcoes
    return _toml(atual)


SENHA_LINHA = re.compile(r"^\s*password\s*=")


def com_senha(existente: str, senha: str | None) -> str:
    """Troca só a linha `password` da seção de topo; `None` tira a linha. O resto fica igual."""
    linhas = existente.splitlines()
    fim = next((i for i, linha in enumerate(linhas) if linha.lstrip().startswith("[")), len(linhas))
    topo = [linha for linha in linhas[:fim] if not SENHA_LINHA.match(linha)]
    if senha is not None:
        topo.insert(0, f"password = {toml_texto(senha)}")
    return "\n".join(topo + linhas[fim:]) + "\n"


SENHA_CIFRADA = re.compile(r"^0[0-9].")  # versão do formato do RustDesk + texto cifrado


def senha_cifrada(texto: str) -> bool:
    """O RustDesk regrava a senha cifrada com a versão do formato na frente: `00` nas versões
    antigas, `01` no 1.5.1 (máquina real, 10/11/2026). Quem chama confere também que a senha em
    texto puro não está mais no arquivo."""
    try:
        valor = tomllib.loads(texto).get("password", "")
    except tomllib.TOMLDecodeError:
        return False
    return isinstance(valor, str) and bool(SENHA_CIFRADA.match(valor))


# ---------------------------------------------------------------- máquina


def pasta_conhecida(csidl: int) -> Path:
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) != 0:
        raise ErroRemoto("Pasta de programas não encontrada.")
    return Path(buffer.value)


def program_files() -> Path:
    return pasta_conhecida(0x26)  # CSIDL_PROGRAM_FILES


def program_files_x86() -> Path:
    return pasta_conhecida(0x2A)  # CSIDL_PROGRAM_FILESX86


def windows() -> Path:
    return Path(executor.sistema32("")).parent


def pasta_config_rustdesk() -> Path:
    return (
        windows()
        / "ServiceProfiles"
        / "LocalService"
        / "AppData"
        / "Roaming"
        / "RustDesk"
        / "config"
    )


def exe(programa: Programa, local: str | None = None) -> Path:
    if programa == "RustDesk":
        return (
            Path(local) / "rustdesk.exe" if local else program_files() / "RustDesk" / "rustdesk.exe"
        )
    if programa == "AnyDesk":
        return (
            Path(local) / "AnyDesk.exe"
            if local
            else program_files_x86() / "AnyDesk" / "AnyDesk.exe"
        )
    raise ValueError(programa)


def desinstalacao(programa: Programa) -> tuple[str | None, str | None]:
    """(DisplayVersion, InstallLocation) pelas chaves Uninstall de 64 e 32 bits."""
    prefixo = NOME_DESINSTALACAO[programa].lower()
    for visao in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            raiz = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, DESINSTALACAO, 0, winreg.KEY_READ | visao
            )
        except OSError:
            continue
        with raiz:
            for i in range(winreg.QueryInfoKey(raiz)[0]):
                try:
                    with winreg.OpenKey(raiz, winreg.EnumKey(raiz, i)) as k:
                        nome = str(winreg.QueryValueEx(k, "DisplayName")[0])
                        if not nome.lower().startswith(prefixo):
                            continue
                        ver = str(winreg.QueryValueEx(k, "DisplayVersion")[0])
                        try:
                            # O AnyDesk grava entre aspas.
                            local = (
                                str(winreg.QueryValueEx(k, "InstallLocation")[0]).strip().strip('"')
                                or None
                            )
                        except OSError:
                            local = None
                        return ver, local
                except OSError:
                    continue
    return None, None


def glpi_registro() -> tuple[str, str]:
    """(server, tag) gravados pelo agente."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, CHAVE_GLPI, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as k:
            valores = {}
            for nome in ("server", "tag"):
                try:
                    valores[nome] = str(winreg.QueryValueEx(k, nome)[0])
                except OSError:
                    valores[nome] = ""
            return valores["server"], valores["tag"]
    except OSError:
        return "", ""


def gravar_glpi_registro(server: str, tag: str) -> None:
    """Reconfigurar: tag vazia não apaga a gravada (ADR-019)."""
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, CHAVE_GLPI, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
    ) as k:
        winreg.SetValueEx(k, "server", 0, winreg.REG_SZ, server)
        if tag:
            winreg.SetValueEx(k, "tag", 0, winreg.REG_SZ, tag)


def sem_reparse(alvo: Path, base: Path) -> None:
    """Recusa se `alvo` ou algum pai até `base` for ponto de reparse (como no ADR-011)."""
    atual = alvo
    while True:
        if (
            atual.exists()
            and os.lstat(atual).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ErroRemoto("Pasta de configuração do RustDesk é um ponto de reparse; recusado.")
        if atual == base or atual.parent == atual:
            return
        atual = atual.parent


def gravar_atomico(caminho: Path, texto: str) -> None:
    """`.tmp` + `replace`; o `.tmp` nunca fica para trás (pode ter a senha)."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    try:
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(caminho)
    finally:
        tmp.unlink(missing_ok=True)


def script(nome: str) -> str:
    return (RECURSOS / f"{nome}.ps1").read_text("utf-8")


# ---------------------------------------------------------------- situação


@dataclass(frozen=True)
class Situacao:
    programa: Programa
    instalada: str | None
    cadastro: str | None
    comparacao: Comparacao | None
    servico: str | None  # Running, Stopped, ... ou None
    config: Literal["conferida", "diferente", "nao_conferida", ""]
    id_remoto: str = ""
    falta: str = ""  # cadastro incompleto
    detalhes: tuple[str, ...] = field(default=())


def _id(caminho: Path, executar: Rodar) -> str:
    if not caminho.is_file():
        return ""
    r = executar(
        [str(caminho), "--get-id"], timeout=TIMEOUT_LEITURA, descricao=f"{caminho.name} --get-id"
    )
    texto = r.saida.strip() if r.ok else ""
    return texto if ID_REMOTO.fullmatch(texto) else ""


def servicos(*, rodar: Rodar = executor.powershell) -> dict[str, str | None]:
    r = rodar(script("estado"), timeout=TIMEOUT_LEITURA)
    if not r.ok:
        return {}
    try:
        lido = json.loads(r.saida)
    except json.JSONDecodeError:
        return {}
    return {k: (str(v) if v else None) for k, v in lido.items()} if isinstance(lido, dict) else {}


def situacao(
    cadastros: Cadastros | None,
    unidade: str | None,
    *,
    admin: bool,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    ler_desinstalacao: Callable[[Programa], tuple[str | None, str | None]] = desinstalacao,
) -> dict[Programa, Situacao]:
    estados = servicos(rodar=rodar)
    saida: dict[Programa, Situacao] = {}
    for programa in PROGRAMAS:
        instalada, local = ler_desinstalacao(programa)
        d = dados(cadastros, programa, unidade)
        falta = d if isinstance(d, str) else ""
        cadastro = d.instalador.versao if isinstance(d, Dados) else None
        comp = comparar(instalada, cadastro) if cadastro else None
        config: Literal["conferida", "diferente", "nao_conferida", ""] = ""
        detalhes: list[str] = list(d.avisos) if isinstance(d, Dados) else []
        id_remoto = ""
        if instalada is not None and isinstance(d, Dados):
            if programa == "GLPI Agent":
                server, tag = glpi_registro()
                ok = server == d.servidor and (not d.tag or tag == d.tag)
                config = "conferida" if ok else "diferente"
                detalhes.append(f"Tag: {d.tag}" if d.tag else "Sem tag")
            elif programa == "RustDesk":
                config = _conferir_rustdesk(d) if admin else "nao_conferida"
        if instalada is not None and programa != "GLPI Agent":
            with contextlib.suppress(OSError, ValueError, ErroRemoto):
                id_remoto = _id(exe(programa, local), executar)
        saida[programa] = Situacao(
            programa,
            instalada,
            cadastro,
            comp,
            estados.get(SERVICO[programa]),
            config,
            id_remoto,
            falta,
            tuple(detalhes),
        )
    return saida


def _conferir_rustdesk(
    d: Dados, pasta: Path | None = None
) -> Literal["conferida", "diferente", "nao_conferida"]:
    pasta = pasta or pasta_config_rustdesk()
    try:
        opcoes = tomllib.loads((pasta / "RustDesk2.toml").read_text("utf-8")).get("options", {})
        cifrada = senha_cifrada((pasta / "RustDesk.toml").read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return "nao_conferida"
    if d.chave is None:
        return "nao_conferida"
    chave = str(opcoes.get("key", ""))
    ok = (
        opcoes.get("custom-rendezvous-server") == d.servidor
        and hmac.compare_digest(chave.encode(), d.chave.revelar().encode())
        and cifrada
        and (not d.api or opcoes.get("api-server") == d.api)
    )
    return "conferida" if ok else "diferente"


# ---------------------------------------------------------------- execução


@dataclass(frozen=True)
class Feito:
    ok: bool
    mensagem: str
    avisos: tuple[str, ...] = ()
    reinicio: bool = False


def _checar(cancelar: threading.Event | None) -> None:
    if cancelar is not None and cancelar.is_set():
        raise instaladores.Cancelado


def _msiexec(arquivo: Path, *propriedades: str, rodar_exe: Rodar, programa: Programa) -> bool:
    """Roda o MSI; devolve `reinício pendente`. Erro vira `ErroRemoto`."""
    msiexec = executor.sistema32("msiexec.exe")
    # Sem cancelar: matar o cliente não para o Windows Installer (ADR-019).
    r = rodar_exe(
        [msiexec, "/i", str(arquivo), "/qn", "/norestart", *propriedades],
        timeout=TIMEOUT_INSTALAR,
        descricao=f"msiexec /i {programa} (propriedades: {len(propriedades)})",
    )
    if r.esgotado:
        raise ErroRemoto(f"Tempo esgotado instalando {programa}.")
    if r.codigo in MSI_OK:
        return bool(MSI_OK[r.codigo])
    log.error("Acesso remoto: %s: msiexec código %s", programa, r.codigo)
    raise ErroRemoto(
        MSI_ERROS.get(r.codigo or -1, f"O instalador de {programa} falhou (código {r.codigo}).")
    )


def _servico(
    programa: Programa,
    acao: str,
    *,
    rodar: Rodar,
    cancelar: threading.Event | None,
    arquivo: Path | None = None,
    pasta: Path | None = None,
) -> None:
    variaveis = {"servico": SERVICO[programa], "acao": acao, "segundos": str(ESPERA_SERVICO)}
    if arquivo is not None:
        variaveis["arquivo"] = str(arquivo)
    if pasta is not None:
        variaveis["pasta"] = str(pasta)
        variaveis["processo"] = "rustdesk"
    r = rodar(script("servico"), timeout=ESPERA_SERVICO * 2 + 30, cancelar=cancelar, **variaveis)
    if r.cancelado:
        raise instaladores.Cancelado
    if not (r.ok and "OK" in r.saida.split()):
        log.error("Acesso remoto: %s: serviço %s falhou (código %s)", programa, acao, r.codigo)
        raise ErroRemoto(f"O serviço de {programa} não respondeu a tempo ({acao}).")


def preparar_arquivo(
    d: Dados,
    *,
    origem: Path | None,
    cancelar: threading.Event | None,
    progresso: instaladores.Progresso | None = None,
    abrir: instaladores.Abrir | None = None,
) -> Path:
    ext = EXTENSAO[d.programa]
    if origem is not None:
        return instaladores.copiar(d.instalador, ext, origem, cancelar=cancelar)
    if abrir is not None:
        return instaladores.obter(
            d.instalador, ext, cancelar=cancelar, progresso=progresso, abrir=abrir
        )
    return instaladores.obter(d.instalador, ext, cancelar=cancelar, progresso=progresso)


def instalar(
    d: Dados,
    arquivo: Path,
    *,
    avisar: Avisar = lambda _t: None,
    cancelar: threading.Event | None = None,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    pasta_rustdesk: Path | None = None,
) -> Feito:
    """Instala (ou atualiza) com o arquivo já obtido, e configura."""
    programa = d.programa
    try:
        _checar(cancelar)
        if not instaladores.conferir(arquivo):
            log.error(
                "Acesso remoto: %s: SHA-256 diferente antes de executar (Id %s)",
                programa,
                d.instalador.id,
            )
            raise ErroRemoto(f"O arquivo de {programa} não confere com o cadastro (SHA-256).")
        log.info(
            "Acesso remoto: %s %s: instalando (Id %s)",
            programa,
            d.instalador.versao,
            d.instalador.id,
        )
        reinicio = False
        if programa == "GLPI Agent":
            props = [f"SERVER={d.servidor}", "ADD_FIREWALL_EXCEPTION=1", "RUNNOW=1"]
            if d.tag:
                props.insert(1, f"TAG={d.tag}")
            avisar("Instalando o GLPI Agent…")
            reinicio = _msiexec(arquivo, *props, rodar_exe=executar, programa=programa)
            avisar("Esperando o serviço do GLPI Agent…")
            _servico(programa, "esperar", rodar=rodar, cancelar=cancelar)
        elif programa == "RustDesk":
            avisar("Instalando o RustDesk…")
            reinicio = _msiexec(
                arquivo,
                "CREATESTARTMENUSHORTCUTS=N",
                "CREATEDESKTOPSHORTCUTS=N",
                "INSTALLPRINTER=N",
                rodar_exe=executar,
                programa=programa,
            )
            pasta = pasta_rustdesk or pasta_config_rustdesk()
            avisar("Esperando o serviço do RustDesk gerar o ID…")
            _servico(
                programa, "esperar", rodar=rodar, cancelar=cancelar, arquivo=pasta / "RustDesk.toml"
            )
            _configurar_rustdesk(
                d, avisar=avisar, cancelar=cancelar, rodar=rodar, executar=executar, pasta=pasta
            )
        else:
            destino = program_files_x86() / "AnyDesk"
            avisar("Instalando o AnyDesk…")
            r = executar(
                [str(arquivo), "--install", str(destino), "--start-with-win", "--silent"],
                timeout=TIMEOUT_INSTALAR,
                descricao="AnyDesk --install",
            )
            if not r.ok:
                log.error("Acesso remoto: AnyDesk: --install código %s", r.codigo)
                raise ErroRemoto(f"O instalador do AnyDesk falhou (código {r.codigo}).")
            avisar("Esperando o serviço do AnyDesk…")
            _servico(programa, "esperar", rodar=rodar, cancelar=cancelar)
            _senha_anydesk(d, destino / "AnyDesk.exe", executar=executar)
        log.info(
            "Acesso remoto: %s %s: ok%s",
            programa,
            d.instalador.versao,
            " (reinício pendente)" if reinicio else "",
        )
        avisos = (*d.avisos, "Reinicie o computador para concluir.") if reinicio else d.avisos
        return Feito(
            True, f"{programa} {d.instalador.versao} instalado e configurado.", avisos, reinicio
        )
    except instaladores.Cancelado:
        log.warning("Acesso remoto: %s: cancelado pelo técnico", programa)
        return Feito(False, "Cancelado pelo técnico.")
    except (ErroRemoto, instaladores.ErroInstalador) as erro:
        return Feito(False, str(erro))


def reconfigurar(
    d: Dados,
    *,
    avisar: Avisar = lambda _t: None,
    cancelar: threading.Event | None = None,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    pasta_rustdesk: Path | None = None,
    ler_desinstalacao: Callable[[Programa], tuple[str | None, str | None]] = desinstalacao,
) -> Feito:
    programa = d.programa
    try:
        _checar(cancelar)
        log.info("Acesso remoto: %s: reconfigurando (sem reinstalar)", programa)
        if programa == "GLPI Agent":
            gravar_glpi_registro(d.servidor, d.tag)
            _servico(programa, "reiniciar", rodar=rodar, cancelar=cancelar)
        elif programa == "RustDesk":
            _configurar_rustdesk(
                d,
                avisar=avisar,
                cancelar=cancelar,
                rodar=rodar,
                executar=executar,
                pasta=pasta_rustdesk or pasta_config_rustdesk(),
            )
        else:
            _, local = ler_desinstalacao(programa)
            _senha_anydesk(d, exe(programa, local), executar=executar)
        log.info("Acesso remoto: %s: reconfigurado", programa)
        return Feito(True, f"{programa} reconfigurado.", d.avisos)
    except instaladores.Cancelado:
        log.warning("Acesso remoto: %s: cancelado pelo técnico", programa)
        return Feito(False, "Cancelado pelo técnico.")
    except (ErroRemoto, OSError) as erro:
        if isinstance(erro, OSError):
            log.error("Acesso remoto: %s: reconfigurar falhou (%s)", programa, type(erro).__name__)
            return Feito(
                False, f"Não foi possível reconfigurar {programa} ({type(erro).__name__})."
            )
        return Feito(False, str(erro))


def _senha_anydesk(d: Dados, caminho: Path, *, executar: Rodar) -> None:
    if d.senha is None:
        raise ErroRemoto("Senha do AnyDesk ausente.")
    if not caminho.is_file():
        raise ErroRemoto(
            "AnyDesk instalado, mas o executável não foi encontrado para definir a senha."
        )
    # Senha pela entrada padrão (ADR-011/ADR-019): nunca argumento nem `echo`.
    r = executar(
        [str(caminho), "--set-password"],
        entrada=d.senha,
        timeout=TIMEOUT_LEITURA,
        descricao="AnyDesk --set-password",
    )
    if not r.ok:
        log.error("Acesso remoto: AnyDesk: --set-password código %s", r.codigo)
        raise ErroRemoto(f"O AnyDesk não aceitou a senha (código {r.codigo}).")


def _configurar_rustdesk(
    d: Dados,
    *,
    avisar: Avisar,
    cancelar: threading.Event | None,
    rodar: Rodar,
    executar: Rodar,
    pasta: Path,
    esperar: Callable[[float], None] | None = None,
) -> None:
    if d.chave is None or d.senha is None:
        raise ErroRemoto("Chave ou senha do RustDesk ausente.")
    instalado = exe("RustDesk")
    sem_reparse(pasta, windows())
    avisar("Parando o RustDesk para gravar a configuração…")
    _servico("RustDesk", "parar", rodar=rodar, cancelar=cancelar, pasta=instalado.parent)
    pasta.mkdir(parents=True, exist_ok=True)
    sem_reparse(pasta, windows())
    config2, config = pasta / "RustDesk2.toml", pasta / "RustDesk.toml"
    existente2 = config2.read_text("utf-8") if config2.is_file() else None
    gravar_atomico(config2, rustdesk2(existente2, d.servidor, d.chave.revelar(), d.api))
    avisar("Iniciando o RustDesk…")
    _servico("RustDesk", "iniciar", rodar=rodar, cancelar=cancelar)
    _checar(cancelar)
    # ADR-031: o RustDesk 1.5.1 não aceita mais a senha posta no arquivo. A senha vai por
    # `rustdesk.exe --password`, chamado por um trecho fixo com a senha em ITC_SENHA: ela só
    # aparece na linha de comando do rustdesk.exe durante a chamada; nunca no disco nem no log.
    avisar("Definindo a senha permanente do RustDesk…")
    r = rodar(script("senha"), timeout=TIMEOUT_LEITURA, exe=str(instalado), senha=d.senha)
    if not r.ok or "OK" not in r.saida.split():
        log.error("Acesso remoto: RustDesk: --password falhou: %s", _codigo_senha(r))
        raise ErroRemoto(
            f"O RustDesk não aceitou a senha permanente ({_codigo_senha(r)}). "
            "Confira se o serviço do RustDesk está rodando e tente Reconfigurar de novo."
        )
    avisar("Conferindo se o RustDesk guardou a senha cifrada…")
    cifrou = False
    for _ in range(ESPERA_CIFRAR):
        _checar(cancelar)
        texto = config.read_text("utf-8") if config.is_file() else ""
        if d.senha.revelar() in texto:
            # Não deve acontecer com o --password; se acontecer, o texto puro sai do disco.
            _retirar_senha(config, d.senha, rodar=rodar, pasta=instalado.parent)
            raise ErroRemoto(
                "O RustDesk gravou a senha sem cifrar. A senha foi retirada do arquivo; avise o "
                "responsável (ADR-031)."
            )
        if senha_cifrada(texto):
            cifrou = True
            break
        (esperar or time.sleep)(1)
    if not cifrou:
        log.error("Acesso remoto: RustDesk: senha não encontrada cifrada depois do --password")
        raise ErroRemoto(
            "O RustDesk respondeu ao --password, mas a senha cifrada não apareceu na "
            "configuração. Confira a conexão com a senha do cadastro e avise o responsável "
            "(ADR-031)."
        )
    for opcao in ("stop-service-hide-tray", "hide-icon"):
        r = executar(
            [str(instalado), "--option", opcao, "Y"],
            timeout=TIMEOUT_LEITURA,
            descricao=f"rustdesk --option {opcao}",
        )
        if not r.ok:
            log.warning("Acesso remoto: RustDesk: --option %s código %s", opcao, r.codigo)


def _codigo_senha(r: executor.Resultado) -> str:
    """Só o código, para o log e a tela: a saída do rustdesk.exe não é mostrada."""
    if r.esgotado:
        return "tempo esgotado"
    for linha in r.saida.splitlines():
        if linha.startswith("ERRO|"):
            return linha.strip().replace("|", " ", 2)
    return f"código {r.codigo}"


def _retirar_senha(config: Path, senha: Sensivel, *, rodar: Rodar, pasta: Path) -> None:
    """Para o serviço (se der), tira a linha `password` se ainda estiver em texto puro e inicia."""
    with contextlib.suppress(ErroRemoto, instaladores.Cancelado):
        _servico("RustDesk", "parar", rodar=rodar, cancelar=None, pasta=pasta)
    atual = config.read_text("utf-8") if config.is_file() else ""
    if senha.revelar() in atual or not senha_cifrada(atual):
        gravar_atomico(config, com_senha(atual, None))
    log.error("Acesso remoto: RustDesk: a senha não foi cifrada; linha removida")
    with contextlib.suppress(ErroRemoto, instaladores.Cancelado):
        _servico("RustDesk", "iniciar", rodar=rodar, cancelar=None)


def forcar_inventario(*, abrir: Callable[..., Any] = urllib.request.urlopen) -> Feito:
    """Pede ao agente local um inventário agora (`/now`); não fala com o GLPI."""
    try:
        with abrir(URL_INVENTARIO, timeout=10) as resposta:
            status = getattr(resposta, "status", 200)
    except OSError as erro:
        log.warning("Acesso remoto: forçar inventário falhou (%s)", type(erro).__name__)
        return Feito(False, "O GLPI Agent não respondeu. Confira se ele está instalado e rodando.")
    if status != 200:
        log.warning("Acesso remoto: forçar inventário: HTTP %s", status)
        return Feito(False, f"O GLPI Agent recusou o pedido (HTTP {status}).")
    log.info("Acesso remoto: inventário forçado")
    return Feito(True, "Inventário pedido ao GLPI Agent. Ele envia ao servidor em seguida.")


def comando(d: Dados, arquivo: str = "<instalador>") -> str:
    """Comando mostrado na confirmação, sem segredo."""
    if d.programa == "GLPI Agent":
        tag = f" TAG={d.tag}" if d.tag else ""
        return (
            f"msiexec /i {arquivo} /qn /norestart SERVER={d.servidor}{tag} "
            "ADD_FIREWALL_EXCEPTION=1 RUNNOW=1"
        )
    if d.programa == "RustDesk":
        return (
            f"msiexec /i {arquivo} /qn /norestart CREATESTARTMENUSHORTCUTS=N "
            "CREATEDESKTOPSHORTCUTS=N INSTALLPRINTER=N\n"
            "Servidor, chave e servidor da API: RustDesk2.toml do serviço.\n"
            "Senha permanente: rustdesk.exe --password, com o serviço rodando (nunca na tela)."
        )
    return (
        f"{arquivo} --install <Program Files (x86)>\\AnyDesk --start-with-win --silent\n"
        "Senha: pela entrada padrão (nunca na tela)."
    )
