r"""Fila de diagnósticos não enviados (ADR-015). Sem Qt.

`%ProgramData%\ITC\Bench\protegido\fila-diagnostico.dpapi` (DPAPI de máquina, pasta só de SYSTEM
e Administradores), escrita atômica, `{"formato": 1, "itens": [...]}` com o corpo já saneado.
No máximo 10 itens e 14 dias; o mais antigo sai com log. Ilegível: renomeada para
`fila-diagnostico.corrompida` (a prova fica) e a fila recomeça vazia. É da máquina: logout e
troca de técnico não apagam. Sem administrador (`arquivo=None`), só em memória.

O log tem 8 caracteres do `envio_id` e contagens; nunca o corpo.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from itc_bench.nucleo import dpapi
from itc_bench.nucleo.log import log
from itc_bench.servicos import api, diagnostico
from itc_bench.servicos.executor import Sensivel

FORMATO = 1
MAX_ITENS = 10
IDADE_MAXIMA = timedelta(days=14)
NOME = "fila-diagnostico.dpapi"


@dataclass(frozen=True)
class Item:
    envio_id: str
    criado_em: datetime
    coletado_por: str
    hostname: str
    corpo: dict[str, Any]


class Fila:
    def __init__(
        self, arquivo: Path | None, agora: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.arquivo = arquivo
        self.agora = agora
        self._memoria: list[dict[str, Any]] = []
        self.aviso: str | None = None  # "corrompida" ou "descartados N" na última operação

    def itens(self) -> list[Item]:
        return [self._item(r) for r in self._validos(self._ler())]

    def guardar(self, corpo: dict[str, Any], coletado_por: str) -> None:
        registros = [r for r in self._ler() if r["envio_id"] != corpo["envio_id"]]
        registros.append(
            {
                "envio_id": corpo["envio_id"],
                "criado_em": self.agora().isoformat(),
                "coletado_por": coletado_por,
                "hostname": corpo["sessao"]["hostname"],
                "corpo": corpo,
            }
        )
        self._gravar(registros)
        log.info("Diagnóstico %s na fila.", diagnostico.curto(corpo["envio_id"]))

    def remover(self, envio_id: str) -> None:
        self._gravar([r for r in self._ler() if r["envio_id"] != envio_id])

    def _validos(self, registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agora = self.agora()
        validos = []
        for r in registros:
            try:
                idade = agora - datetime.fromisoformat(r["criado_em"])
                if idade <= IDADE_MAXIMA and isinstance(r["corpo"], dict):
                    validos.append(r)
            except (KeyError, TypeError, ValueError):
                continue
        excesso = max(0, len(validos) - MAX_ITENS)
        if excesso or len(validos) != len(registros):
            descartados = len(registros) - len(validos) + excesso
            self.aviso = f"descartados {descartados}"
            log.warning(
                "Fila de diagnósticos: %d item(ns) antigo(s) ou além do limite descartado(s).",
                descartados,
            )
        return validos[excesso:]

    def _item(self, r: dict[str, Any]) -> Item:
        return Item(
            str(r["envio_id"]),
            datetime.fromisoformat(r["criado_em"]),
            str(r.get("coletado_por") or ""),
            str(r.get("hostname") or ""),
            r["corpo"],
        )

    def _ler(self) -> list[dict[str, Any]]:
        if self.arquivo is None:
            return list(self._memoria)
        try:
            bruto = self.arquivo.read_bytes()
        except FileNotFoundError:
            return []
        try:
            registro = json.loads(dpapi.decifrar(bruto))
            if registro.get("formato") != FORMATO or not isinstance(registro.get("itens"), list):
                raise ValueError("formato")
            return [r for r in registro["itens"] if isinstance(r, dict) and "envio_id" in r]
        except (OSError, ValueError, AttributeError) as erro:
            self._corrompida(type(erro).__name__)
            return []

    def _gravar(self, registros: list[dict[str, Any]]) -> None:
        registros = self._validos(registros)
        if self.arquivo is None:
            self._memoria = registros
            return
        temporario = self.arquivo.with_suffix(".tmp")
        conteudo = json.dumps({"formato": FORMATO, "itens": registros}, ensure_ascii=False)
        temporario.write_bytes(dpapi.cifrar(conteudo.encode()))
        temporario.replace(self.arquivo)

    def _corrompida(self, detalhe: str) -> None:
        self.aviso = "corrompida"
        if self.arquivo is None:
            return
        destino = self.arquivo.with_name("fila-diagnostico.corrompida")
        log.error("Fila de diagnósticos ilegível (%s); guardada como %s.", detalhe, destino.name)
        try:
            self.arquivo.replace(destino)
        except OSError as erro:
            log.error("Não foi possível guardar a fila ilegível: %s", erro)


@dataclass(frozen=True)
class Reenvio:
    enviados: int
    pendentes: int
    sessao_expirada: bool


def reenviar(fila: Fila, base: str, token: Sensivel) -> Reenvio:
    """Um por vez. Sai da fila com 200, IA fora (a coleta já está no servidor) ou 422.

    Sem conexão, 429 ou 409: para e fica. 401: para e avisa (tela Entrar).
    """
    enviados = 0
    for item in fila.itens():
        try:
            diagnostico.enviar(base, token, item.corpo)
        except api.IaFalhou:
            pass  # diagnóstico gravado no servidor; o laudo sai pelo Histórico
        except api.Recusado as erro:
            if erro.status == 422:
                log.error(
                    "Diagnóstico %s recusado pelo servidor; saiu da fila.",
                    diagnostico.curto(item.envio_id),
                )
            elif erro.status == 401:
                return Reenvio(enviados, len(fila.itens()), True)
            else:
                break
        except (api.SemConexao, api.ErroApi):
            break
        fila.remover(item.envio_id)
        enviados += 1
    return Reenvio(enviados, len(fila.itens()), False)
