"""Remover Steam (ADR-064), sem Qt: Manutenção, etapa 4.

A Steam é da máquina (Program Files (x86)\\Steam), não da conta. Sai pelo desinstalador dela, em
silêncio (`/S`), que leva os jogos da biblioteca padrão (`steamapps`) e os usuários salvos. Só
aceita o `uninstall.exe` da pasta padrão; o caminho nunca vai para o log.
"""

import threading
import time
import winreg
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, remoto

CHAVE = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam"
PRAZO = 900  # o desinstalador da Steam volta logo e segue trabalhando; espera a chave sumir
INTERVALO = 5


def esperado() -> PureWindowsPath:
    return PureWindowsPath(remoto.program_files_x86()) / "Steam" / "uninstall.exe"


def _ler_desinstalador() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE) as chave:
            valor, _ = winreg.QueryValueEx(chave, "UninstallString")
    except OSError:
        return ""
    return str(valor).strip().strip('"')


def desinstalador(ler: Callable[[], str] = _ler_desinstalador) -> str | None:
    """O `uninstall.exe` da Steam, só se for o da pasta padrão e existir; senão None."""
    valor = ler().strip().strip('"')
    if not valor:
        return None
    if str(PureWindowsPath(valor)).casefold() != str(esperado()).casefold():
        log.warning("Steam: desinstalador fora da pasta padrão; não removida pelo Bench")
        return None
    return valor if Path(valor).is_file() else None


def instalada(ler: Callable[[], str] = _ler_desinstalador) -> bool:
    return desinstalador(ler) is not None


def remover(
    *,
    cancelar: threading.Event | None = None,
    ler: Callable[[], str] = _ler_desinstalador,
    rodar: Callable[..., executor.Resultado] = executor.executar,
    dormir: Callable[[float], None] = time.sleep,
    prazo: float = PRAZO,
) -> tuple[bool, str]:
    """(ok, mensagem). Roda `uninstall.exe /S` e espera a Steam sair do registro."""
    exe = desinstalador(ler)
    if exe is None:
        return True, "A Steam não está instalada."
    r = rodar([exe, "/S"], timeout=120, descricao="Steam: desinstalador /S")
    if not r.ok:
        log.error("Steam: desinstalador terminou com código %s", r.codigo)
        return False, f"O desinstalador da Steam falhou (código {r.codigo})."
    esperado_ = 0.0
    while instalada(ler):
        if cancelar is not None and cancelar.is_set():
            return False, "Cancelado: a Steam ainda está sendo removida."
        if esperado_ >= prazo:
            log.error("Steam: ainda instalada depois de %s s", int(prazo))
            return False, "A Steam não saiu a tempo. Feche a Steam e rode de novo."
        dormir(INTERVALO)
        esperado_ += INTERVALO
    log.info("Steam: removida")
    return True, "Steam e jogos removidos."
