"""Proteção do login (ADR-022), sem Qt: a tela Proteção do login e o Início do 13 usam.

Proteger = uma ACE que nega só execução ao SYSTEM no `utilman.exe`/`sethc.exe`, com o dono
devolvido ao TrustedInstaller no mesmo passo. Detecção dos 7 binários de acessibilidade da tela de
login (assinatura do Windows, nome original, IFEO), sempre lida do Windows. Tudo pelo executor:
`takeown`/`icacls`/`sfc` por caminho absoluto e argumentos fixos; trechos de `recursos/protecao/`.
"""

import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Literal

from itc_bench.nucleo import acl
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

RECURSOS = resources.files("itc_bench.recursos") / "protecao"
TIMEOUT, TIMEOUT_SFC = 60.0, 600.0
SID_SYSTEM = "S-1-5-18"
SID_TRUSTEDINSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"

PROTEGIVEIS = ("utilman.exe", "sethc.exe")
BINARIOS = (
    "utilman.exe",
    "sethc.exe",
    "osk.exe",
    "Magnify.exe",
    "Narrator.exe",
    "DisplaySwitch.exe",
    "AtBroker.exe",
)
NOMES = {
    "utilman.exe": "Utilman (Acessibilidade)",
    "sethc.exe": "Sethc (Shift 5x)",
    "osk.exe": "Teclado virtual",
    "Magnify.exe": "Lupa",
    "Narrator.exe": "Narrador",
    "DisplaySwitch.exe": "Alternar vídeo",
    "AtBroker.exe": "AtBroker",
}
# (chave em .DEFAULT\Control Panel\Accessibility, desligado, padrão do Windows)
FLAGS = (
    ("StickyKeys", "506", "510"),
    ("Keyboard Response", "122", "126"),
    ("ToggleKeys", "58", "62"),
)

Arquivo = Literal["original", "trocado", "ausente", "nao_lido"]
Acl = Literal["protegido", "livre", "dono", "ausente", "nao_lida"]
Ifeo = Literal["limpo", "depurador", "nao_lido"]
Atalho = Literal["desligado", "padrao", "diferente", "nao_lido"]
Rodar = Callable[..., executor.Resultado]

ROTULO_ARQUIVO = {
    "original": "original do Windows",
    "trocado": "TROCADO",
    "ausente": "ausente",
    "nao_lido": "não lido (serviço de criptografia parado?)",
}
ROTULO_ACL = {
    "protegido": "protegido",
    "livre": "não protegido",
    "dono": "dono alterado",
    "ausente": "—",
    "nao_lida": "não lida",
}
ROTULO_IFEO = {"limpo": "sem depurador", "depurador": "DEPURADOR", "nao_lido": "não lido"}
ROTULO_ATALHO = {
    "desligado": "desligado",
    "padrao": "ligado (padrão do Windows)",
    "diferente": "diferente",
    "nao_lido": "não lido",
}


@dataclass(frozen=True)
class Binario:
    exe: str
    arquivo: Arquivo
    acl: Acl
    ifeo: Ifeo


@dataclass(frozen=True)
class Situacao:
    binarios: dict[str, Binario]
    atalho: Atalho

    def alertas(self) -> list[str]:
        """Para a tela e para o Início (13). Vazio = tudo certo."""
        saida = []
        for b in self.binarios.values():
            nome = NOMES[b.exe]
            if b.arquivo == "trocado":
                saida.append(f"{nome}: arquivo trocado")
            if b.ifeo == "depurador":
                saida.append(f"{nome}: depurador (IFEO) configurado")
        for exe in PROTEGIVEIS:
            p = self.binarios.get(exe)
            if p is not None and p.acl != "protegido":
                saida.append(f"{NOMES[exe]}: {ROTULO_ACL[p.acl]}")
        return saida


def script(nome: str) -> str:
    return (RECURSOS / f"{nome}.ps1").read_text("utf-8")


def _atalho(lidos: dict[str, str | None] | None) -> Atalho:
    if not isinstance(lidos, dict):
        return "nao_lido"
    valores = [lidos.get(chave) for chave, _, _ in FLAGS]
    if valores == [d for _, d, _ in FLAGS]:
        return "desligado"
    if all(v is None or v == p for v, (_, _, p) in zip(valores, FLAGS, strict=True)):
        return "padrao"
    return "diferente"


def situacao(*, rodar: Rodar = executor.powershell) -> Situacao:
    r = rodar(script("ler"), timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError("Leitura da proteção falhou.")
    try:
        cru = json.loads(r.saida)
        binarios = {
            str(b["exe"]): Binario(str(b["exe"]), b["arquivo"], b["acl"], b["ifeo"])
            for b in cru["binarios"]
        }
    except (json.JSONDecodeError, KeyError, TypeError) as erro:
        raise RuntimeError(f"Saída inválida da leitura ({type(erro).__name__}).") from None
    if set(binarios) != set(BINARIOS):
        raise RuntimeError("Saída inválida da leitura (binários).")
    return Situacao(binarios, _atalho(cru.get("flags")))


# ---------------------------------------------------------------- proteger / desproteger


@dataclass(frozen=True)
class Feito:
    exe: str
    ok: bool
    mensagem: str


def _passo(nome: str, argumentos: list[str], rodar: Rodar) -> str | None:
    r = rodar(argumentos, timeout=TIMEOUT, descricao=nome)
    if r.ok:
        return None
    return "tempo_esgotado" if r.esgotado else f"{nome}_{r.codigo}"


def _mudar(exe: str, proteger: bool, rodar: Rodar, sistema32: Callable[[str], str]) -> str | None:
    """Três passos; o terceiro (dono de volta ao TrustedInstaller) roda sempre."""
    arq = sistema32(exe)
    erro = _passo("takeown", [sistema32("takeown.exe"), "/f", arq, "/a"], rodar)
    try:
        if erro is None:
            meio = ["/deny", f"*{SID_SYSTEM}:(X)"] if proteger else ["/remove:d", f"*{SID_SYSTEM}"]
            erro = _passo("icacls", [sistema32("icacls.exe"), arq, *meio], rodar)
    finally:
        dono = _passo(
            "setowner",
            [sistema32("icacls.exe"), arq, "/setowner", f"*{SID_TRUSTEDINSTALLER}"],
            rodar,
        )
    return erro or dono


def alterar(
    proteger: bool,
    exes: Sequence[str] = PROTEGIVEIS,
    *,
    rodar_ps: Rodar = executor.powershell,
    rodar: Rodar = executor.executar,
    sistema32: Callable[[str], str] = executor.sistema32,
    cancelar: threading.Event | None = None,
    privilegios: Callable[[bool], None] | None = None,
) -> list[Feito]:
    """Proteger (ou desproteger) cada arquivo; cancelamento entre arquivos, nunca no meio."""
    for exe in exes:
        if exe not in PROTEGIVEIS:
            raise ValueError(f"Arquivo fora da proteção: {exe!r}")
    antes = situacao(rodar=rodar_ps)
    ajustar = privilegios or _privilegios
    # O dono de volta ao TrustedInstaller (`icacls /setowner`) exige o SeRestore ligado no token
    # que o icacls herda; sem isso ele sai com 5 (acesso negado). Ligado só durante os passos e
    # desligado no `finally`. Falhar ao ligar não para: o passo do dono diz se deu certo.
    try:
        ajustar(True)
    except OSError as falha:
        log.warning("Proteção: privilégios não ligados (%s)", type(falha).__name__)
    try:
        return _alterar_arquivos(proteger, exes, antes, rodar, sistema32, cancelar)
    finally:
        try:
            ajustar(False)
        except OSError as falha:
            log.warning("Proteção: privilégios não desligados (%s)", type(falha).__name__)


def _privilegios(ligar: bool) -> None:
    if ligar:
        acl.habilitar_privilegios()
    else:
        acl.desabilitar_privilegios()


def _alterar_arquivos(
    proteger: bool,
    exes: Sequence[str],
    antes: Situacao,
    rodar: Rodar,
    sistema32: Callable[[str], str],
    cancelar: threading.Event | None,
) -> list[Feito]:
    acao = "proteger" if proteger else "desproteger"
    feitos = []
    for exe in exes:
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(exe, False, "Cancelado pelo técnico (antes deste arquivo)."))
            continue
        b = antes.binarios[exe]
        if proteger and b.arquivo != "original":
            motivo = (
                "Arquivo não conferido como original: use “Restaurar original” antes."
                if b.arquivo == "trocado"
                else "Não foi possível conferir o arquivo: tente de novo."
            )
            feitos.append(Feito(exe, False, motivo))
            log.warning("Proteção: %s arquivo=%s resultado=recusado (%s)", acao, exe, b.arquivo)
            continue
        erro = _mudar(exe, proteger, rodar, sistema32)
        log.info(
            "Proteção: %s arquivo=%s resultado=%s codigo=%s",
            acao,
            exe,
            "ok" if erro is None else "erro",
            erro or "0",
        )
        feitos.append(Feito(exe, erro is None, "Feito." if erro is None else f"Falhou ({erro})."))
    return feitos


# ---------------------------------------------------------------- atalho e incidente


def _escrever(acao: str, rodar: Rodar) -> tuple[bool, str]:
    r = rodar(script("escrever"), timeout=TIMEOUT, acao=acao)
    ok = r.ok and "OK" in r.saida.split()
    cod = "0"
    if not ok:
        cod = (
            "tempo_esgotado"
            if r.esgotado
            else next(
                (ln.split("|")[1] for ln in r.saida.splitlines() if ln.startswith("ERRO|")),
                f"powershell_{r.codigo}",
            )
        )
    log.info("Proteção: %s resultado=%s codigo=%s", acao, "ok" if ok else "erro", cod)
    return ok, ("Feito." if ok else f"Falhou ({cod}).")


def atalho_login(desligar: bool, *, rodar: Rodar = executor.powershell) -> tuple[bool, str]:
    """Shift 5x na tela de login (`HKU\\.DEFAULT`): desligado ou padrão do Windows."""
    return _escrever("atalho_desligar" if desligar else "atalho_padrao", rodar)


def remover_depurador(*, rodar: Rodar = executor.powershell) -> tuple[bool, str]:
    """Apaga só `Debugger`/`MonitorProcess` das chaves IFEO dos 7 binários fixos."""
    return _escrever("remover_depurador", rodar)


def restaurar(
    exe: str,
    *,
    rodar: Rodar = executor.executar,
    rodar_ps: Rodar = executor.powershell,
    sistema32: Callable[[str], str] = executor.sistema32,
) -> tuple[bool, str]:
    """`sfc /scanfile`; quem decide é a nova detecção, não o código do `sfc`."""
    if exe not in BINARIOS:
        raise ValueError(f"Arquivo fora da detecção: {exe!r}")
    r = rodar(
        [sistema32("sfc.exe"), f"/scanfile={sistema32(exe)}"],
        timeout=TIMEOUT_SFC,
        descricao="sfc /scanfile",
    )
    depois = situacao(rodar=rodar_ps).binarios[exe].arquivo
    ok = depois == "original"
    log.info(
        "Proteção: restaurar arquivo=%s resultado=%s codigo=%s",
        exe,
        "ok" if ok else "erro",
        "0" if ok else f"sfc_{r.codigo}/{depois}",
    )
    if ok:
        return True, "Arquivo original restaurado. Proteja de novo."
    return False, f"O arquivo continua {ROTULO_ARQUIVO[depois]}: abra chamado."
