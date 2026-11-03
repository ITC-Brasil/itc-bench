"""Build the report prompt on the server (ADR-006): swapping prompt or model needs no pendrive update."""

import json
from pathlib import Path

SISTEMA = (Path(__file__).parent / "prompts" / "relatorio.md").read_text("utf-8")
# Not needed to diagnose and not sent to the provider: the account that ran the tool
# (ADR-016 data minimization), serial number and MAC addresses.
FORA_DO_PROMPT = frozenset({"usuarioExecucao", "numeroSerie", "macAddress"})
SEM_HISTORICO = "Sem diagnósticos anteriores deste hostname."


def sem_identificadores(valor):
    if isinstance(valor, dict):
        return {k: sem_identificadores(v) for k, v in valor.items() if k not in FORA_DO_PROMPT}
    if isinstance(valor, list):
        return [sem_identificadores(v) for v in valor]
    return valor


def compacto(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def montar(normalizada: dict, avisos: list[str], historico: list[dict]) -> list[dict]:
    usuario = "\n\n".join(
        [
            "## Dados da sessão",
            compacto(sem_identificadores(normalizada)),
            "## Avisos de normalização",
            "\n".join(f"- {aviso}" for aviso in avisos) or "Nenhum.",
            "## Histórico do hostname",
            compacto(historico) if historico else SEM_HISTORICO,
        ]
    )
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]
