import json

import httpx
import pytest

from app.config import Settings
from app.services import opencode_go
from app.services.opencode_go import IAFalha

KEY = "sk-test-not-real"
MESSAGES = [{"role": "user", "content": "x"}]
CONTENT = {
    "relatorio_md": "## Resumo\nok",
    "chamado_titulo": "Disco quase cheio",
    "chamado_descricao": "C: com 8% livre.",
    "maior_confianca": "ALTA",
}


def completion(content, **extra):
    body = {"model": "mimo-v2.6-flash", "choices": [{"message": {"content": content}}]}
    body.update(extra)
    return body


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_path=str(tmp_path / "t.db"), opencode_go_api_key=KEY)


def call(settings, handler):
    return opencode_go.gerar(settings, MESSAGES, "2026-09-28_1510_TESTE-NB-11", httpx.MockTransport(handler))


def test_success_sends_headers_model_and_timeout(settings):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json=completion(json.dumps(CONTENT), usage={"prompt_tokens": 9800, "completion_tokens": 950}))

    result = call(settings, handler)

    request = seen["request"]
    assert str(request.url) == "https://opencode.ai/zen/go/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["user-agent"] == "itc-tecnico-assistente/1.0"
    assert request.headers["x-opencode-session"] == "2026-09-28_1510_TESTE-NB-11"
    assert request.extensions["timeout"] == {"connect": 60.0, "read": 60.0, "write": 60.0, "pool": 60.0}
    assert json.loads(request.content) == {"model": "mimo-v2.6-flash", "messages": MESSAGES}
    assert (result.chamado_titulo, result.maior_confianca, result.tokens_entrada, result.tokens_saida) == (
        "Disco quase cheio", "ALTA", 9800, 950,
    )


def test_fenced_json_and_confidence_without_accent_are_accepted(settings):
    content = "```json\n" + json.dumps({**CONTENT, "maior_confianca": "media"}) + "\n```"
    result = call(settings, lambda r: httpx.Response(200, json=completion(content)))
    assert result.maior_confianca == "MÉDIA"
    assert result.tokens_entrada is None


def test_unknown_confidence_becomes_null(settings):
    result = call(settings, lambda r: httpx.Response(200, json=completion(json.dumps({**CONTENT, "maior_confianca": "?"}))))
    assert result.maior_confianca is None


def raise_(error):
    def handler(request):
        raise error

    return handler


@pytest.mark.parametrize(
    "handler, status, code",
    [
        (raise_(httpx.ReadTimeout("slow")), 503, "ia_timeout"),
        (raise_(httpx.ConnectTimeout("slow")), 503, "ia_timeout"),
        (raise_(httpx.ConnectError("down")), 503, "ia_indisponivel"),
        (lambda r: httpx.Response(401, json={"error": KEY}), 502, "ia_autenticacao"),
        (lambda r: httpx.Response(403), 502, "ia_autenticacao"),
        (lambda r: httpx.Response(429, json={"error": "quota"}), 503, "ia_cota"),
        (lambda r: httpx.Response(402), 503, "ia_cota"),
        (lambda r: httpx.Response(400, json={"error": "content refused"}), 502, "ia_recusa"),
        (lambda r: httpx.Response(500), 503, "ia_indisponivel"),
        (lambda r: httpx.Response(200, text="not json"), 502, "ia_resposta_invalida"),
        (lambda r: httpx.Response(200, json=completion("texto livre")), 502, "ia_resposta_invalida"),
        (lambda r: httpx.Response(200, json=completion(json.dumps({**CONTENT, "chamado_titulo": " "}))), 502, "ia_resposta_invalida"),
        (lambda r: httpx.Response(200, json={"choices": []}), 502, "ia_resposta_invalida"),
    ],
)
def test_failures_become_clean_codes_without_provider_text(settings, handler, status, code):
    with pytest.raises(IAFalha) as failure:
        call(settings, handler)

    assert (failure.value.status, failure.value.code) == (status, code)
    # No chained httpx error in a traceback: it could carry the request, headers included.
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None or failure.value.__suppress_context__
    assert KEY not in repr(failure.value) + str(failure.value.args)


@pytest.mark.parametrize("key", ["", "changeme", " changeme "])
def test_placeholder_key_is_never_sent(tmp_path, key):
    settings = Settings(_env_file=None, database_path=str(tmp_path / "t.db"), opencode_go_api_key=key)

    def handler(request):
        raise AssertionError("must not be called")

    with pytest.raises(IAFalha) as failure:
        call(settings, handler)
    assert (failure.value.status, failure.value.code) == (503, "ia_nao_configurada")
