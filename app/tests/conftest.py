import os

# Widgets sem abrir janela (ADR-010).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest

from itc_bench.nucleo import log as _log


@pytest.fixture(autouse=True)
def _sem_tecnico():
    """O técnico do log é global (ADR-013): cada teste começa e termina sem ele."""
    _log.definir_tecnico(None)
    yield
    _log.definir_tecnico(None)
