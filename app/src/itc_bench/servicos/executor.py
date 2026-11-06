"""Executor único de programas externos (ADR-011).

Lista de argumentos com o programa por caminho absoluto, nunca shell. Dados do usuário vão por
variável de ambiente `ITC_*` ou pelo stdin; valor `Sensivel` nunca aparece no log, em erro nem em
`repr`. Cada processo roda num Job Object: no timeout ou no fim da chamada, filhos que sobraram
são encerrados.
"""

import base64
import ctypes
import logging
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Literal

log = logging.getLogger("itc_bench.executor")

TIMEOUT_PADRAO = 120.0
FATIA = 0.25  # espera entre conferências do cancelamento
MASCARA = "***"
NOME_VARIAVEL = re.compile(r"ITC_[A-Z0-9_]+")
# Linha de comando do Windows: 32 767 caracteres; base64 de UTF-16LE gasta 8/3 por caractere.
LIMITE_SCRIPT = 12_000
ABERTURA_PS = (
    "$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
    "$ErrorActionPreference = 'Stop'\n"
    "$ProgressPreference = 'SilentlyContinue'\n"
    # Pastas pela API, não por variável de ambiente que o usuário pode trocar.
    "$env:PSModulePath = [Environment]::GetFolderPath('System') + "
    "'\\WindowsPowerShell\\v1.0\\Modules;' + [Environment]::GetFolderPath('ProgramFiles') + "
    "'\\WindowsPowerShell\\Modules'\n"
)

Codificacao = Literal["auto", "utf-8", "oem", "ansi"]


class Sensivel:
    """Senha, chave ou token: aparece como *** em repr, str, f-string e log."""

    __slots__ = ("__valor",)

    def __init__(self, valor: str) -> None:
        self.__valor = valor

    def revelar(self) -> str:
        return self.__valor

    def __repr__(self) -> str:
        return MASCARA

    __str__ = __repr__


@dataclass(frozen=True)
class Resultado:
    codigo: int | None
    saida: str
    erros: str
    duracao: float
    esgotado: bool
    cancelado: bool = False

    @property
    def ok(self) -> bool:
        return self.codigo == 0 and not self.esgotado and not self.cancelado


def sistema32(nome: str) -> str:
    """Caminho absoluto na pasta de sistema, lida pela API (`SYSTEMROOT` do ambiente não conta)."""
    buffer = ctypes.create_unicode_buffer(260)
    if not ctypes.WinDLL("kernel32").GetSystemDirectoryW(buffer, len(buffer)):
        raise ctypes.WinError()
    return str(PureWindowsPath(buffer.value, nome))


def executar(
    argumentos: Sequence[str],
    *,
    ambiente: Mapping[str, str | Sensivel] | None = None,
    entrada: str | Sensivel | None = None,
    timeout: float = TIMEOUT_PADRAO,
    codificacao: Codificacao = "auto",
    descricao: str | None = None,
    cancelar: threading.Event | None = None,
    encerrar_no_timeout: bool = True,
) -> Resultado:
    """Roda o programa e espera (ou até `cancelar`, ADR-015).

    Código ≠ 0 volta no `Resultado`; uso errado levanta exceção. `encerrar_no_timeout=False`
    (instaladores, ADR-020): no timeout o processo continua rodando, fora de Job Object, e o
    `Resultado` volta `esgotado`; não combina com `cancelar`.
    """
    if not encerrar_no_timeout and cancelar is not None:
        raise ValueError("Processo que não é encerrado não aceita cancelamento.")
    if isinstance(argumentos, str | bytes):
        raise TypeError("O comando é uma lista de argumentos, nunca texto.")
    argumentos = list(argumentos)
    if not argumentos or not all(isinstance(a, str) for a in argumentos):
        raise TypeError("Argumentos têm que ser texto; dado sensível vai por ambiente ou entrada.")
    if not PureWindowsPath(argumentos[0]).is_absolute():
        raise ValueError(f"Programa sem caminho absoluto: {argumentos[0]!r}.")

    ambiente = dict(ambiente or {})
    for nome in ambiente:
        if not NOME_VARIAVEL.fullmatch(nome):
            raise ValueError(f"Nome de variável inválido: {nome!r} (use ITC_[A-Z0-9_]+).")
    filho = {k: v for k, v in os.environ.items() if not k.upper().startswith("ITC_")}
    filho.update({k: _texto(v) for k, v in ambiente.items()})
    # Pasta do Windows pela API: um SYSTEMROOT trocado no ambiente quebra ou desvia o filho.
    windows = str(PureWindowsPath(sistema32("")).parent)
    filho.update({k: windows for k in list(filho) if k.upper() in ("SYSTEMROOT", "WINDIR")})
    filho.setdefault("SYSTEMROOT", windows)
    segredos = [v.revelar() for v in [*ambiente.values(), entrada] if isinstance(v, Sensivel)]
    dados = None if entrada is None else _texto(entrada).encode(_codec(codificacao))
    rotulo = descricao or subprocess.list2cmdline(argumentos)

    inicio = time.monotonic()
    processo = subprocess.Popen(  # noqa: S603 — lista de argumentos com caminho absoluto
        argumentos,
        shell=False,
        stdin=subprocess.PIPE if dados is not None else subprocess.DEVNULL,
        # Solto no timeout: sem pipe, para o filho não morrer escrevendo num pipe fechado.
        stdout=subprocess.PIPE if encerrar_no_timeout else subprocess.DEVNULL,
        stderr=subprocess.PIPE if encerrar_no_timeout else subprocess.DEVNULL,
        env=filho,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    job = _Job(processo.pid) if encerrar_no_timeout else None
    esgotado = cancelado = solto = False
    limite = inicio + timeout
    try:
        while True:
            fatia = limite - time.monotonic() if cancelar is None else FATIA
            try:
                # Entrada só na primeira chamada: depois de começar, o communicate a recusa.
                saida, erros = processo.communicate(dados, timeout=max(fatia, 0))
                break
            except subprocess.TimeoutExpired:
                dados = None
                cancelado = cancelar is not None and cancelar.is_set()
                esgotado = not cancelado and time.monotonic() >= limite
                if esgotado and job is None:
                    # Instalador segue sozinho, sem saída ligada a nós.
                    if processo.stdin is not None:
                        processo.stdin.close()
                    saida = erros = b""
                    solto = True
                    break
                if cancelado or esgotado:
                    if job is not None:
                        job.encerrar()
                    processo.kill()
                    saida, erros = processo.communicate()
                    break
    finally:
        if job is not None:
            job.fechar()
    duracao = time.monotonic() - inicio
    saida, erros = saida or b"", erros or b""

    resultado = Resultado(
        codigo=None if esgotado or cancelado else processo.returncode,
        saida=_mascarar(_decodificar(saida, codificacao), segredos),
        erros=_mascarar(_clixml(_decodificar(erros, codificacao)), segredos),
        duracao=duracao,
        esgotado=esgotado,
        cancelado=cancelado,
    )
    variaveis = ", ".join(sorted(ambiente)) or "nenhuma"
    if cancelado:
        log.warning("Cancelado pelo técnico: %s [ITC_*: %s]", rotulo, variaveis)
    elif solto:
        log.error(
            "Tempo esgotado (%.0f s), processo ainda em execução: %s [ITC_*: %s]",
            timeout,
            rotulo,
            variaveis,
        )
    elif esgotado:
        log.error("Tempo esgotado (%.0f s): %s [ITC_*: %s]", timeout, rotulo, variaveis)
    else:
        log.info(
            "Executado: %s [ITC_*: %s] código %s em %.2f s",
            rotulo,
            variaveis,
            resultado.codigo,
            duracao,
        )
        if resultado.codigo != 0 and resultado.erros.strip():
            log.warning("Erro do comando: %s", resultado.erros.strip()[:500])
    return resultado


def powershell(
    script: str,
    *,
    timeout: float = TIMEOUT_PADRAO,
    cancelar: threading.Event | None = None,
    **variaveis: str | Sensivel,
) -> Resultado:
    """Script fixo no código; dados só por `ITC_<NOME>` (`nome="x"` vira `$env:ITC_NOME`)."""
    completo = ABERTURA_PS + script
    if len(completo) > LIMITE_SCRIPT:
        raise ValueError(f"Script com {len(completo)} caracteres; limite {LIMITE_SCRIPT}.")
    codificado = base64.b64encode(completo.encode("utf-16-le")).decode("ascii")
    programa = sistema32(r"WindowsPowerShell\v1.0\powershell.exe")
    return executar(
        [programa, "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
        ambiente={f"ITC_{k.upper()}": v for k, v in variaveis.items()},
        timeout=timeout,
        cancelar=cancelar,
        codificacao="utf-8",
        descricao=f"PowerShell ({len(script)} caracteres): {script.strip().splitlines()[0][:80]}",
    )


def _texto(valor: str | Sensivel) -> str:
    return valor.revelar() if isinstance(valor, Sensivel) else valor


def _clixml(texto: str) -> str:
    """O PowerShell com -EncodedCommand manda o stderr em CLIXML, com `<`, `&` e quebras escapados.

    Volta para texto antes de mascarar; senão a senha escapada passaria pela máscara.
    """
    if not texto.startswith("#< CLIXML"):
        return texto
    try:
        raiz = ET.fromstring(texto.split("\n", 1)[1])  # noqa: S314 — saída do próprio filho
    except (ET.ParseError, IndexError):
        return texto
    partes = [no.text or "" for no in raiz.iter() if no.get("S") == "Error"]
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m[1], 16)), "".join(partes))


def _mascarar(texto: str, segredos: list[str]) -> str:
    for segredo in segredos:
        if segredo:
            texto = texto.replace(segredo, MASCARA)
    return texto.removeprefix("\ufeff")


def _decodificar(dados: bytes, codificacao: Codificacao) -> str:
    """`auto`: UTF-8 se for válido (netsh no Windows 11 já escreve UTF-8), senão OEM (cmd)."""
    if codificacao == "auto":
        try:
            return dados.decode("utf-8")
        except UnicodeDecodeError:
            codificacao = "oem"
    return dados.decode(_codec(codificacao), errors="replace")


def _codec(codificacao: Codificacao) -> str:
    """Página de código para escrever no stdin; `auto` escreve em UTF-8."""
    if codificacao in ("auto", "utf-8"):
        return "utf-8"
    kernel32 = ctypes.WinDLL("kernel32")
    pagina = kernel32.GetOEMCP() if codificacao == "oem" else kernel32.GetACP()
    return f"cp{pagina}"


class _LimiteBasico(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class _LimiteEstendido(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", _LimiteBasico),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


class _Job:
    """Job Object com KILL_ON_JOB_CLOSE: fechar o handle encerra o que sobrou na árvore."""

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _K32.CreateJobObjectW.restype = wintypes.HANDLE
    _K32.OpenProcess.restype = wintypes.HANDLE
    _K32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    _K32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _K32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _K32.CloseHandle.argtypes = (wintypes.HANDLE,)

    def __init__(self, pid: int) -> None:
        k32 = self._K32
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limite = _LimiteEstendido()
        limite.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(self.handle, 9, ctypes.byref(limite), ctypes.sizeof(limite))
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        processo = k32.OpenProcess(0x0100 | 0x0001, False, pid)
        try:
            if not processo or not k32.AssignProcessToJobObject(self.handle, processo):
                log.warning("Processo %s fora do Job Object: %s", pid, ctypes.get_last_error())
        finally:
            if processo:
                k32.CloseHandle(processo)

    def encerrar(self) -> None:
        self._K32.TerminateJobObject(self.handle, 1)

    def fechar(self) -> None:
        if self.handle:
            self._K32.CloseHandle(self.handle)
            self.handle = None
