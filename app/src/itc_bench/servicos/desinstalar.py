r"""Remover programas (ADR-020), sem Qt: desinstalação sem shell, a partir do registro.

MSI por `ProductCode` (`msiexec /x`); EXE pela `QuietUninstallString` (silencioso) ou
`UninstallString` (interativo), separadas em lista de argumentos. Recusa interpretadores,
comandos que não dá para separar de volta ao mesmo texto e executáveis fora de `Program Files` e
`%WINDIR%` (pasta gravável por usuário comum seria executada como admin). Sem limpeza de
resíduos. O log nunca recebe a `UninstallString`, só o nome do executável e o modo.
"""

import ctypes
import json
import os
import re
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, programas, remoto
from itc_bench.servicos.programas import Instalado

Rodar = Callable[..., executor.Resultado]
Modo = Literal["silencioso", "interativo", "recusado", "protegido", "ausente"]
Estado = Literal["ok", "reinicio", "falha", "cancelado", "em_execucao", "pulado"]
Tipo = Literal["programa", "atalho", "terminal"]

TIMEOUT = 900
GUID = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)
PROIBIDOS = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "rundll32.exe",
    "wscript.exe",
    "cscript.exe",
    "mshta.exe",
    "regsvr32.exe",
    "msiexec.exe",  # só pelo caminho MSI, com o ProductCode
}
PROTEGIDOS = (
    ("ITC Bench", "É o próprio Bench."),
    *((nome, "É do Acesso remoto.") for nome in remoto.NOME_DESINSTALACAO.values()),
    ("Microsoft Visual C++", "Runtime usado por outros programas."),
    ("Microsoft .NET", "Runtime usado por outros programas."),
    ("Microsoft Windows Desktop Runtime", "Runtime usado por outros programas."),
    ("Windows Driver Package", "Driver."),
    ("Intel", "Driver ou ferramenta do fabricante."),
    ("Realtek", "Driver."),
    ("AMD", "Driver."),
    ("NVIDIA", "Driver."),
)
MSI_OK = {**remoto.MSI_OK, 1605: ""}  # 1605: já não estava instalado
EXE_OK = {0: "", 3010: "reinício pendente"}


@dataclass(frozen=True)
class Entrada:
    nome: str
    tipo: Tipo
    modo: Modo
    comando: tuple[str, ...] = ()
    motivo: str = ""
    versao: str = ""
    usuario: bool = False

    @property
    def executavel(self) -> str:
        """Só o nome do arquivo (para log e confirmação; nunca o caminho de perfil)."""
        return PureWindowsPath(self.comando[0]).name if self.comando else ""

    @property
    def selecionavel(self) -> bool:
        return self.modo in ("silencioso", "interativo")


# ---------------------------------------------------------------- separação (pura)


def argv(resto: str) -> list[str]:
    """Regras do Windows (`CommandLineToArgvW`) para os argumentos depois do executável."""
    if not resto.strip():
        return []
    shell32 = ctypes.WinDLL("shell32")
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    shell32.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    n = ctypes.c_int()
    lista = shell32.CommandLineToArgvW("x " + resto, ctypes.byref(n))
    if not lista:
        raise ctypes.WinError()
    try:
        return [lista[i] for i in range(1, n.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(lista)


def separar(texto: str, existe: Callable[[str], bool]) -> tuple[str, list[str]] | None:
    """(executável, argumentos), ou None se não dá para separar com segurança.

    Entre aspas: até a aspa seguinte. Sem aspas: o primeiro prefixo terminado em `.exe` numa
    fronteira de espaço que existe como arquivo (regra do `CreateProcess`). Os argumentos só valem
    se `list2cmdline` devolve exatamente o texto original (o programa recebe a mesma linha).
    """
    texto = texto.strip()
    if texto.startswith('"'):
        fim = texto.find('"', 1)
        if fim < 0:
            return None
        exe, resto = texto[1:fim], texto[fim + 1 :]
        if resto and not resto.startswith(" "):
            return None
    else:
        partes = texto.split(" ")
        for i in range(len(partes)):
            candidato = " ".join(partes[: i + 1])
            if candidato.lower().endswith(".exe") and existe(candidato):
                exe, resto = candidato, " ".join(partes[i + 1 :])
                break
        else:
            return None
    resto = resto.strip()
    args = argv(resto)
    # Sem aspas, espaços repetidos entre argumentos não mudam o que o programa recebe.
    original = resto if '"' in resto else " ".join(resto.split())
    if executor.linha_de_comando(args) != original:
        return None
    return exe, args


# Subpastas de %WINDIR% em que Usuários gravam: executável ali nunca roda (ADR-020).
GRAVAVEIS_WINDOWS = tuple(
    PureWindowsPath(p)
    for base in ("System32", "SysWOW64")
    for p in (
        rf"{base}\Tasks",
        rf"{base}\Tasks_Migrated",
        rf"{base}\spool\drivers\color",
        rf"{base}\spool\PRINTERS",
        rf"{base}\spool\SERVERS",
        rf"{base}\com\dmp",
        rf"{base}\FxsTmp",
        rf"{base}\Microsoft\Crypto\RSA\MachineKeys",
    )
) + tuple(PureWindowsPath(p) for p in ("Temp", "Tasks", "tracing", r"Registration\CRMLog"))


def pastas_aceitas() -> tuple[Path, ...]:
    return remoto.program_files(), remoto.program_files_x86(), remoto.windows()


def recusa(
    exe: str, *, usuario: bool = False, resolver: Callable[[str], str] = os.path.realpath
) -> str:
    """Motivo de não rodar o executável, ou vazio.

    Entrada de HKU (gravável pelo próprio usuário): só Program Files. HKLM: também %WINDIR%, fora
    das subpastas graváveis por Usuários.
    """
    nome = PureWindowsPath(exe).name.lower()
    if not nome.endswith(".exe"):
        return "O desinstalador não é um .exe."
    if nome in PROIBIDOS:
        return f"O registro manda rodar {nome}; remova pelo Painel de Controle."
    if not PureWindowsPath(exe).is_absolute():
        return "O desinstalador não tem caminho absoluto."
    # Caminho final: `..`, junções e links resolvidos.
    final = PureWindowsPath(resolver(exe))
    if PureWindowsPath(final).name.lower() in PROIBIDOS:
        return f"O registro manda rodar {PureWindowsPath(final).name}; remova pelo Painel."
    programas_, programas86, windows = (PureWindowsPath(b) for b in pastas_aceitas())
    if final.is_relative_to(programas_) or final.is_relative_to(programas86):
        return ""
    if usuario:
        return "Remova pelo Painel de Controle, entrando na conta do usuário."
    if not final.is_relative_to(windows):
        return "O desinstalador está fora de Program Files e do Windows; remova pelo Painel."
    relativo = final.relative_to(windows)
    if any(relativo.is_relative_to(g) for g in GRAVAVEIS_WINDOWS):
        return (
            "O desinstalador está numa pasta do Windows gravável por usuários; remova pelo Painel."
        )
    return ""


def protegido(nome: str) -> str:
    dobrado = nome.casefold()
    return next((m for p, m in PROTEGIDOS if dobrado.startswith(p.casefold())), "")


def plano(
    i: Instalado,
    *,
    existe: Callable[[str], bool] = os.path.isfile,
    resolver: Callable[[str], str] = os.path.realpath,
) -> Entrada:
    def entrada(modo: Modo, comando: tuple[str, ...] = (), motivo: str = "") -> Entrada:
        return Entrada(i.nome, "programa", modo, comando, motivo, i.versao, i.usuario)

    motivo = protegido(i.nome)
    if motivo:
        return entrada("protegido", motivo=motivo)
    if GUID.fullmatch(i.chave) and i.valores.get("WindowsInstaller") == "1":
        msiexec = executor.sistema32("msiexec.exe")
        comando = (msiexec, "/x", i.chave.upper(), "/qn", "/norestart")
        return entrada("silencioso", comando)
    ultimo = "Sem comando de desinstalação no registro."
    tentativas: tuple[tuple[str, Modo], ...] = (
        ("QuietUninstallString", "silencioso"),
        ("UninstallString", "interativo"),
    )
    for valor, modo in tentativas:
        texto = i.valores.get(valor, "").strip()
        if not texto:
            continue
        separado = separar(texto, existe)
        if separado is None:
            ultimo = "Comando de desinstalação que não dá para separar com segurança."
            continue
        exe, args = separado
        ultimo = recusa(exe, usuario=i.usuario, resolver=resolver)
        if ultimo:
            continue
        if not existe(exe):
            return entrada("ausente", motivo="Desinstalador ausente.")
        return entrada(modo, (exe, *args))
    return entrada("recusado", motivo=ultimo)


# ---------------------------------------------------------------- lista


def terminal(*, rodar: Rodar = executor.powershell) -> Entrada | None:
    r = rodar(programas.script("terminal"), timeout=programas.TIMEOUT_LEITURA, acao="ver")
    if not (r.ok and '"instalado":true' in r.saida.replace(" ", "")):
        return None
    return Entrada("Windows Terminal (Store)", "terminal", "silencioso")


def listar(
    *,
    rodar: Rodar = executor.powershell,
    ler_registro: Callable[[], list[Instalado]] = programas.instalados,
) -> list[Entrada]:
    """Programas do registro, atalhos do Bench e o Windows Terminal, em ordem de nome."""
    vistos: set[tuple[str, str]] = set()
    entradas = []
    for i in ler_registro():
        if i.valores.get("SystemComponent") == "1" or i.valores.get("ParentKeyName"):
            continue
        if (i.nome, i.versao) in vistos:
            continue  # mesma entrada em 64 e 32 bits
        vistos.add((i.nome, i.versao))
        entradas.append(plano(i))
    atalhos = programas.atalhos(rodar=rodar)
    entradas += [
        Entrada(nome.removesuffix(".lnk"), "atalho", "silencioso")
        for nome, descricao in atalhos.items()
        if descricao == programas.DESCRICAO_ATALHO
    ]
    if (t := terminal(rodar=rodar)) is not None:
        entradas.append(t)
    return sorted(entradas, key=lambda e: e.nome.casefold())


# ---------------------------------------------------------------- execução


@dataclass(frozen=True)
class Feito:
    entrada: Entrada
    estado: Estado
    mensagem: str


def _programa(e: Entrada, *, executar: Rodar) -> Feito:
    msi = e.executavel.lower() == "msiexec.exe"
    r = executar(
        list(e.comando),
        timeout=TIMEOUT,
        encerrar_no_timeout=False,
        descricao=f"desinstalar ({e.modo}): {e.executavel}",
    )
    if r.esgotado:
        log.error("Remover: %s: ainda em execução no fim do tempo", e.nome)
        return Feito(e, "em_execucao", f"{e.nome}: ainda em execução, confira depois.")
    codigo = (r.codigo or 0) & 0xFFFFFFFF
    ok = MSI_OK if msi else EXE_OK
    if codigo in ok:
        estado: Estado = "reinicio" if ok[codigo] else "ok"
        log.info("Remover: %s (%s, %s): %s", e.nome, e.modo, e.executavel, estado)
        sufixo = " Reinicie o computador para concluir." if ok[codigo] else ""
        return Feito(e, estado, f"{e.nome} removido.{sufixo}")
    log.error("Remover: %s (%s, %s): código %s", e.nome, e.modo, e.executavel, codigo)
    texto = remoto.MSI_ERROS.get(codigo) if msi else None
    return Feito(e, "falha", f"{e.nome}: {texto or f'falhou (código {codigo}).'}")


def _atalho(e: Entrada, *, rodar: Rodar) -> Feito:
    r = rodar(
        programas.script("atalho"),
        timeout=programas.TIMEOUT_LEITURA,
        acao="apagar",
        pasta=str(programas.area_publica()),
        nome=f"{e.nome}.lnk",
    )
    if r.ok and "OK" in r.saida.split():
        log.info("Remover: atalho web removido")
        return Feito(e, "ok", f"Atalho {e.nome} removido.")
    log.error("Remover: atalho web não removido (código %s)", r.codigo)
    return Feito(e, "falha", f"O atalho {e.nome} não é do Bench ou não existe mais.")


def _terminal(e: Entrada, *, rodar: Rodar) -> Feito:
    r = rodar(programas.script("terminal"), timeout=TIMEOUT, acao="remover")
    if r.ok and "OK" in r.saida.split():
        log.info("Remover: Windows Terminal removido (usuários e provisionado)")
        return Feito(e, "ok", "Windows Terminal removido para todos os usuários.")
    log.error("Remover: Windows Terminal: código %s", r.codigo)
    return Feito(e, "falha", "Não foi possível remover o Windows Terminal.")


def desinstalar(
    entradas: list[Entrada],
    *,
    avisar: Callable[[str], None] = lambda _t: None,
    cancelar: threading.Event | None = None,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
) -> list[Feito]:
    """Lote em ordem; um falhou, os outros seguem; cancela entre itens.

    Desinstalador ainda em execução no fim do tempo: os programas seguintes não começam (podem
    usar o Windows Installer); atalhos e Terminal seguem (ADR-020).
    """
    travado = ""
    feitos = []
    for n, e in enumerate(entradas, 1):
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(e, "cancelado", "Cancelado antes de começar."))
            continue
        if not e.selecionavel:
            feitos.append(Feito(e, "pulado", e.motivo or "Não pode ser removido."))
            continue
        if travado and e.tipo == "programa":
            feitos.append(Feito(e, "pulado", travado))
            continue
        avisar(f"[{n}/{len(entradas)}] Removendo {e.nome}…")
        if e.tipo == "programa":
            f = _programa(e, executar=executar)
        elif e.tipo == "atalho":
            f = _atalho(e, rodar=rodar)
        else:
            f = _terminal(e, rodar=rodar)
        if f.estado == "em_execucao":
            travado = f"Não iniciado: {e.nome} ainda estava em execução."
        feitos.append(f)
    return feitos


# ---------------------------------------------------------------- pré-instalados Appx (ADR-023)

# Apps de consumidor da própria Microsoft, por nome de família do pacote. Lista fechada: o trecho
# recebe só esta lista e confere de novo cada nome pedido.
APPX_PREINSTALADOS: tuple[str, ...] = (
    "Clipchamp.Clipchamp",
    "Microsoft.BingNews",
    "Microsoft.BingWeather",
    "Microsoft.GamingApp",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.MicrosoftOfficeHub",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.MixedReality.Portal",
    "Microsoft.People",
    "Microsoft.PowerAutomateDesktop",
    "Microsoft.SkypeApp",
    "Microsoft.Todos",
    "Microsoft.WindowsFeedbackHub",
    "Microsoft.WindowsMaps",
    "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay",
    "Microsoft.XboxSpeechToTextOverlay",
    "Microsoft.YourPhone",
    "Microsoft.ZuneMusic",
    "Microsoft.ZuneVideo",
    "microsoft.windowscommunicationsapps",
)
NOME_APPX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.]{2,63}$")
RECUSA_APPX = {
    "fora_da_lista": "fora da lista fechada",
    "sistema": "pacote de sistema",
    "nao_removivel": "marcado como não removível",
    "framework": "framework usado por outros apps",
    "remover": "o Windows recusou a remoção",
}


def script_appx() -> str:
    for nome in APPX_PREINSTALADOS:
        if not NOME_APPX.fullmatch(nome):
            raise ValueError(f"Nome Appx inválido na lista: {nome!r}")
    lista = ", ".join(f"'{n}'" for n in APPX_PREINSTALADOS)
    return f"$LISTA = @({lista})\n" + programas.script("appx")


def appx_situacao(*, rodar: Rodar = executor.powershell) -> dict[str, str]:
    """Nome → código da recusa ('' = removível) dos pacotes da lista presentes."""
    r = rodar(script_appx(), timeout=programas.TIMEOUT_LEITURA, acao="ver")
    if not r.ok:
        raise RuntimeError(f"Leitura dos pré-instalados falhou (código {r.codigo}).")
    try:
        lido = json.loads(r.saida or "[]")
    except json.JSONDecodeError:
        raise RuntimeError("Saída inválida da leitura dos pré-instalados.") from None
    return {
        str(i["nome"]): str(i.get("recusa") or "")
        for i in lido
        if isinstance(i, dict) and i.get("nome") in APPX_PREINSTALADOS
    }


def appx_presentes(*, rodar: Rodar = executor.powershell) -> list[str]:
    """Pacotes da lista presentes e removíveis, em ordem."""
    return sorted(n for n, recusa in appx_situacao(rodar=rodar).items() if not recusa)


def remover_appx(
    nomes: list[str],
    *,
    rodar: Rodar = executor.powershell,
    cancelar: threading.Event | None = None,
) -> list[Feito]:
    """Remove para todas as contas e o provisionado. Nome fora da lista é recusado aqui e no
    trecho. Uma chamada por pacote; cancela entre eles."""
    feitos = []
    for nome in nomes:
        e = Entrada(nome, "programa", "silencioso")
        if nome not in APPX_PREINSTALADOS:
            log.warning("Remover: Appx recusado: fora_da_lista")
            feitos.append(Feito(e, "pulado", f"{nome}: {RECUSA_APPX['fora_da_lista']}."))
            continue
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(e, "cancelado", "Cancelado antes de começar."))
            continue
        r = rodar(script_appx(), timeout=TIMEOUT, acao="remover", nomes=nome)
        linha = next((x for x in r.saida.splitlines() if x.endswith("|" + nome)), "")
        if r.ok and linha.startswith("OK|"):
            log.info("Remover: Appx %s removido (contas e provisionado)", nome)
            feitos.append(Feito(e, "ok", f"{nome} removido."))
            continue
        codigo = linha.split("|")[1] if linha.startswith("ERRO|") else f"powershell_{r.codigo}"
        log.error("Remover: Appx %s: %s", nome, codigo)
        feitos.append(Feito(e, "falha", f"{nome}: {RECUSA_APPX.get(codigo, codigo)}."))
    return feitos
