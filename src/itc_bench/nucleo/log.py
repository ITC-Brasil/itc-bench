"""Log em arquivo rotativo: 1 MiB por arquivo, 5 arquivos (bench.log + 4 antigos)."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from itc_bench.nucleo import caminhos

TAMANHO_MAXIMO = 1024 * 1024
ARQUIVOS_ANTIGOS = 4
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"

log = logging.getLogger("itc_bench")


def configurar(pasta: Path | None = None) -> Path:
    r"""Liga o log em arquivo e devolve o caminho usado.

    Se o arquivo pertence a uma execução elevada e este processo não pode escrever nele
    (`--dev` sem administrador), o log vai para %LOCALAPPDATA%\ITC\Bench\logs.
    """
    pasta = pasta or caminhos.logs()
    try:
        handler = _handler(pasta)
    except PermissionError:
        reserva = caminhos.preferencias() / "logs"
        handler = _handler(reserva)
        log.warning("Sem permissão em %s; log gravado em %s.", pasta, reserva)
    return Path(handler.baseFilename)


def _handler(pasta: Path) -> RotatingFileHandler:
    pasta.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        pasta / "bench.log",
        maxBytes=TAMANHO_MAXIMO,
        backupCount=ARQUIVOS_ANTIGOS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(FORMATO))
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    return handler
