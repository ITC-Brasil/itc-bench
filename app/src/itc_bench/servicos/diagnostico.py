r"""Corpo do diagnóstico (contrato 1.3), saneamento e envio (ADR-015, ADR-016). Sem Qt.

O saneamento roda antes da fila e do envio: caminho de perfil vira `%PERFIL%`, nome de perfil
ou da conta vira `<usuario>` (palavra inteira, sem diferenciar maiúsculas). Hostname, serial e
MAC continuam (TA-ADR-023). O log tem 8 caracteres do `envio_id`, status e código; nunca o corpo
nem o laudo.
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from itc_bench import __version__
from itc_bench.nucleo.log import log
from itc_bench.servicos import api
from itc_bench.servicos.coleta import PERFIS_IGNORADOS, PERFIS_SISTEMA, ROTULOS, Coleta
from itc_bench.servicos.executor import Sensivel

VERSAO_SCHEMA = "1.3"
LIMITE_CORPO = 480 * 1024  # margem sob os 512 KB da API
HOSTNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}")
CAMINHO_PERFIL = re.compile(r"(?i)\b([A-Z]):\\Users\\([^\\/:*?\"<>|\r\n]+)")
NOME_MINIMO = 3


def novo_envio_id() -> str:
    return str(uuid.uuid4())


def curto(envio_id: str) -> str:
    return envio_id[:8]


def sanear(valor: Any, nomes: list[str]) -> Any:
    """Troca caminho de perfil e nomes pessoais em toda string do valor (chaves ficam)."""
    pessoais = [
        n
        for n in nomes
        if len(n) >= NOME_MINIMO
        and n.lower() not in PERFIS_IGNORADOS
        and not PERFIS_SISTEMA.match(n)
    ]
    padrao = (
        re.compile(
            r"(?<![\w])("
            + "|".join(re.escape(n) for n in sorted(pessoais, key=len, reverse=True))
            + r")(?![\w])",
            re.IGNORECASE,
        )
        if pessoais
        else None
    )

    def perfil(m: re.Match[str]) -> str:
        if m[2].lower() in PERFIS_IGNORADOS:
            return m[0]
        return "%PERFIL%"

    def texto(s: str) -> str:
        s = CAMINHO_PERFIL.sub(perfil, s)
        return padrao.sub("<usuario>", s) if padrao else s

    def andar(v: Any) -> Any:
        if isinstance(v, str):
            return texto(v)
        if isinstance(v, dict):
            return {k: andar(x) for k, x in v.items()}
        if isinstance(v, list):
            return [andar(x) for x in v]
        return v

    return andar(valor)


def montar(coleta: Coleta, coletado_por: str, envio_id: str, unidade: str | None) -> dict[str, Any]:
    """Corpo de `POST /v1/bench/relatorio`, já saneado e dentro do limite de tamanho."""
    fim = coleta.fim or coleta.inicio
    modulos = {
        nome: {
            "versaoSchema": VERSAO_SCHEMA,
            "tipo": "modulo",
            "modulo": nome,
            "rotulo": ROTULOS[nome],
            "hostname": coleta.hostname,
            "sessaoId": coleta.id,
            "coletadoEm": m.coletado_em.isoformat(),
            "duracaoSegundos": m.duracao,
            "executadoElevado": coleta.elevado,
            "status": m.status,
            "erro": m.erro,
            "dados": m.dados,
        }
        for nome, m in coleta.modulos.items()
    }
    sessao = {
        "versaoSchema": VERSAO_SCHEMA,
        "tipo": "sessao",
        "id": coleta.id,
        "hostname": coleta.hostname,
        "origem": "bench",
        "coletadoPor": coletado_por,
        "usuarioSessao": None,
        "projeto": None,
        "subPerfil": None,
        "inicio": coleta.inicio.isoformat(),
        "fim": fim.isoformat() if coleta.encerrada_normalmente else None,
        "ultimaAtualizacao": fim.isoformat(),
        "duracaoSegundos": round((fim - coleta.inicio).total_seconds()),
        "encerradaNormalmente": coleta.encerrada_normalmente,
        "executadoElevado": coleta.elevado,
        "ferramentaVersao": f"ITC Bench {__version__}",
        "maquina": coleta.maquina,
        "modulos": {
            nome: {
                "rotulo": ROTULOS[nome],
                "status": m.status,
                "erro": m.erro,
                "duracaoSegundos": m.duracao,
            }
            for nome, m in coleta.modulos.items()
        },
        "correcoes": [],
        "avisos": list(coleta.avisos),
    }
    # O login do técnico não é nome de perfil local: fica fora da troca e fora do prompt na API.
    corpo = {
        "envio_id": envio_id,
        "unidade": unidade,
        "sessao": sanear(sessao, coleta.nomes_pessoais) | {"coletadoPor": coletado_por},
        "modulos": sanear(modulos, coleta.nomes_pessoais),
    }
    return caber(corpo)


def tamanho(corpo: dict[str, Any]) -> int:
    return len(json.dumps(corpo, ensure_ascii=False).encode())


def caber(corpo: dict[str, Any]) -> dict[str, Any]:
    """Acima do limite: tira mensagens de evento, depois grupos além de 100, depois portas."""
    if tamanho(corpo) <= LIMITE_CORPO:
        return corpo
    eventos = (corpo["modulos"].get("eventlog") or {}).get("dados") or {}
    rede = (corpo["modulos"].get("rede") or {}).get("dados") or {}
    cortes = (
        lambda: [g.update(exemploMensagem=None) for g in eventos.get("grupos", [])],
        lambda: eventos.update(grupos=eventos.get("grupos", [])[:100]),
        lambda: rede.update(portasEmEscuta=[]),
    )
    for corte in cortes:
        corte()
        corpo["sessao"]["avisos"].append("Coleta reduzida para caber no limite de envio.")
        if tamanho(corpo) <= LIMITE_CORPO:
            return corpo
    raise ValueError("Coleta grande demais para enviar mesmo depois de reduzida.")


@dataclass(frozen=True)
class Laudo:
    diagnostico_id: int
    relatorio_md: str
    chamado_titulo: str
    chamado_descricao: str
    maior_confianca: str | None
    modelo: str


def laudo(dados: dict[str, Any]) -> Laudo:
    try:
        return Laudo(
            int(dados["diagnostico_id"]),
            str(dados["relatorio_md"]),
            str(dados["chamado_titulo"]),
            str(dados["chamado_descricao"]),
            None if dados.get("maior_confianca") is None else str(dados["maior_confianca"]),
            str(dados.get("modelo") or ""),
        )
    except (KeyError, TypeError, ValueError):
        raise api.ErroApi("Resposta inesperada do servidor (200).") from None


def enviar(base: str, token: Sensivel, corpo: dict[str, Any]) -> Laudo:
    """Envia; levanta as exceções de `api` (`IaFalhou`, `Recusado`, `SemConexao`, `ErroApi`)."""
    envio = curto(corpo["envio_id"])
    log.info("Enviando diagnóstico %s (%d bytes).", envio, tamanho(corpo))
    try:
        resultado = laudo(api.relatorio(base, token, corpo))
    except (api.IaFalhou, api.Recusado) as erro:
        log.warning("Diagnóstico %s: %s.", envio, getattr(erro, "codigo", type(erro).__name__))
        raise
    except (api.SemConexao, api.ErroApi) as erro:
        log.warning("Diagnóstico %s não enviado: %s.", envio, type(erro).__name__)
        raise
    log.info("Diagnóstico %s com laudo (id %d).", envio, resultado.diagnostico_id)
    return resultado


def hostname_valido(nome: str) -> str:
    if not HOSTNAME.fullmatch(nome):
        raise ValueError("Nome da máquina fora do padrão.")
    return nome.upper()


def historico(base: str, token: Sensivel, hostname: str) -> list[dict[str, Any]]:
    dados = api.historico(base, token, hostname_valido(hostname))
    itens = dados.get("diagnosticos")
    return [i for i in itens if isinstance(i, dict)] if isinstance(itens, list) else []


def mensagem(erro: Exception) -> str:
    """Texto da tela para cada falha do envio."""
    if isinstance(erro, api.IaFalhou):
        return f"Coleta registrada no servidor; a IA não respondeu ({erro.codigo})."
    if isinstance(erro, api.Recusado):
        if erro.status == 409:
            return "O servidor ainda está gerando este laudo. Aguarde e tente de novo."
        if erro.status == 422:
            return "O servidor recusou a coleta (formato inválido)."
        if erro.status == 401:
            return "Sessão expirada. Entre de novo; a coleta foi preservada."
        if erro.retry_after:
            minutos = max(1, round(erro.retry_after / 60))
            return f"Limite de envios por hora. Tente de novo em {minutos} min."
        return "Limite de envios por hora. Tente de novo mais tarde."
    if isinstance(erro, api.SemConexao):
        return "Sem conexão com o servidor. A coleta ficou na fila para envio."
    return api.mensagem(erro)
