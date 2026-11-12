r"""Preferências de UI do usuário em %LOCALAPPDATA%\ITC\Bench\preferencias.json.

Só preferência visual (ADR-037). Nunca senha, token ou dado de cadastro.
"""

import json
import logging
from pathlib import Path

from itc_bench.nucleo import caminhos

log = logging.getLogger("itc_bench.preferencias")

ARQUIVO = "preferencias.json"
MODOS = ("claro", "escuro")
PADRAO = "claro"


def _arquivo(pasta: Path | None) -> Path:
    return (pasta or caminhos.preferencias()) / ARQUIVO


def _ler(pasta: Path | None) -> dict[str, object]:
    arq = _arquivo(pasta)
    if not arq.exists():
        return {}
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        # Sem caminho nem mensagem do erro no log: o caminho tem a pasta do perfil (ADR-023).
        log.warning("Preferências ilegíveis; usando o padrão (%s)", type(erro).__name__)
        return {}
    return dados if isinstance(dados, dict) else {}


def modo(pasta: Path | None = None) -> str:
    """Modo claro ou escuro guardado; claro se não houver ou se o valor não for conhecido."""
    valor = _ler(pasta).get("modo")
    return valor if isinstance(valor, str) and valor in MODOS else PADRAO


def gravar_modo(valor: str, pasta: Path | None = None) -> None:
    """Grava o modo. Levanta ValueError para modo desconhecido e OSError se não gravar."""
    if valor not in MODOS:
        raise ValueError(f"Modo desconhecido: {valor!r}")
    dados = _ler(pasta)
    dados["modo"] = valor
    arq = _arquivo(pasta)
    arq.parent.mkdir(parents=True, exist_ok=True)
    temporario = arq.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arq)
