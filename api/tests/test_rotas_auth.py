"""Every route requires a token or a Bench session, except the closed public list (Module 14)."""

from fastapi.routing import APIRoute

from app.auth import exigir_sessao, exigir_token
from app.main import create_app

# Public on purpose: health, login itself, and logout (always 204, revokes only a valid session).
PUBLICAS = {
    ("GET", "/v1/saude"),
    ("GET", "/v1/bench/saude"),
    ("POST", "/v1/bench/login"),
    ("POST", "/v1/bench/logout"),
}


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


def _rotas(routes):
    """APIRoute at any depth (FastAPI wraps included routers in _IncludedRouter)."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from _rotas(r.original_router.routes)


def test_toda_rota_exige_token_ou_sessao(settings):
    app = create_app(settings)
    rotas = list(_rotas(app.routes))
    assert len(rotas) >= 9
    sem_auth, publicas = [], set()
    for rota in rotas:
        for metodo in rota.methods:
            chave = (metodo, rota.path)
            if chave in PUBLICAS:
                publicas.add(chave)
            elif not {exigir_token, exigir_sessao} & set(_dependencias(rota.dependant)):
                sem_auth.append(chave)
    assert not sem_auth
    assert publicas == PUBLICAS, "rota pública da lista sumiu: revisar a lista"


def test_rotas_de_hostname_validam_o_formato(client):
    for rota in ("/v1/historico/", "/v1/bench/historico/"):
        assert client.get(rota + "nome%20com%20espaco").status_code in (401, 422)
