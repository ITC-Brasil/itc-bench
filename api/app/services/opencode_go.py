"""OpenCode Go client (ADR-003): the only place that talks to the provider.

Every failure becomes IAFalha with a stable internal code and no provider text: the key,
the prompt and the provider's error body never reach a log, a response or a message.
"""

import json
import time
from dataclasses import dataclass

import httpx

URL = "https://opencode.ai/zen/go/v1/chat/completions"
USER_AGENT = "itc-tecnico-assistente/1.0"
CONFIANCAS = ("ALTA", "MÉDIA", "BAIXA")
# .env.example ships "changeme": treat it as no key instead of sending it.
CHAVES_FICTICIAS = ("", "changeme")


class IAFalha(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


@dataclass
class Resposta:
    relatorio_md: str
    chamado_titulo: str
    chamado_descricao: str
    maior_confianca: str | None
    modelo: str
    tokens_entrada: int | None
    tokens_saida: int | None
    duracao_ms: int


def gerar(settings, mensagens: list[dict], sessao_id: str, transport: httpx.BaseTransport | None = None) -> Resposta:
    chave = settings.opencode_go_api_key.get_secret_value().strip()
    if chave in CHAVES_FICTICIAS:
        raise IAFalha(503, "ia_nao_configurada")

    headers = {
        "Authorization": f"Bearer {chave}",
        "User-Agent": USER_AGENT,
        # The session id groups the request on the provider side (§7); never user data.
        "x-opencode-session": sessao_id,
    }
    corpo = {"model": settings.opencode_go_model, "messages": mensagens}
    # ADR-026: with the provider default, a real session took 126.7 s; "low" took 62.2 s.
    esforco = settings.opencode_go_reasoning_effort.strip()
    if esforco:
        corpo["reasoning_effort"] = esforco
    # ponytail: httpx timeouts are per phase (connect, each read), not total; a provider
    # that trickles bytes could pass 60 s. Add a wall-clock deadline if that shows up.
    inicio = time.monotonic()
    try:
        with httpx.Client(timeout=settings.opencode_go_timeout_seconds, transport=transport) as client:
            resposta = client.post(URL, json=corpo, headers=headers)
    except httpx.TimeoutException:
        raise IAFalha(503, "ia_timeout") from None
    except httpx.HTTPError:
        raise IAFalha(503, "ia_indisponivel") from None
    duracao_ms = int((time.monotonic() - inicio) * 1000)

    if resposta.status_code != 200:
        raise erro_http(resposta.status_code)
    return interpretar(resposta, settings.opencode_go_model, duracao_ms)


def erro_http(status: int) -> IAFalha:
    if status in (401, 403):
        return IAFalha(502, "ia_autenticacao")
    if status in (402, 429):
        return IAFalha(503, "ia_cota")
    if status >= 500:
        return IAFalha(503, "ia_indisponivel")
    return IAFalha(502, "ia_recusa")


def interpretar(resposta: httpx.Response, modelo_pedido: str, duracao_ms: int) -> Resposta:
    try:
        corpo = resposta.json()
        texto = corpo["choices"][0]["message"]["content"]
        conteudo = json.loads(sem_cerca(texto))
        campos = {k: conteudo[k] for k in ("relatorio_md", "chamado_titulo", "chamado_descricao")}
    except (ValueError, KeyError, IndexError, TypeError):
        raise IAFalha(502, "ia_resposta_invalida") from None
    if not all(isinstance(v, str) and v.strip() for v in campos.values()):
        raise IAFalha(502, "ia_resposta_invalida")

    confianca = conteudo.get("maior_confianca")
    confianca = confianca.strip().upper().replace("MEDIA", "MÉDIA") if isinstance(confianca, str) else None
    uso = corpo.get("usage") or {}
    return Resposta(
        **{k: v.strip() for k, v in campos.items()},
        maior_confianca=confianca if confianca in CONFIANCAS else None,
        modelo=str(corpo.get("model") or modelo_pedido),
        tokens_entrada=uso.get("prompt_tokens"),
        tokens_saida=uso.get("completion_tokens"),
        duracao_ms=duracao_ms,
    )


def sem_cerca(texto: str) -> str:
    """Accept the JSON wrapped in a ```json fence, which models add despite the prompt."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return texto
