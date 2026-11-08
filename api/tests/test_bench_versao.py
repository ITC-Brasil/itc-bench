"""GET /v1/bench/versao, /versao/arquivo and the CLI app.bench_versao (ADR-026, TA-ADR-033)."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import auth, bench_versao, db
from app.config import Settings
from app.main import create_app
from tests.test_bench_relatorio import abrir_sessao

TOKEN = auth.SESSAO_PREFIX + "v" * 43
AUT = {"Authorization": f"Bearer {TOKEN}"}
CONTEUDO = b"MZ" + b"\x00instalador de teste" * 500


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_path=str(tmp_path / "tecnico.db"),
        bench_versoes_dir=str(tmp_path / "bench"),
        bench_versao_downloads_hora=2,
        bench_versao_retomadas_hora=2,
    )


@pytest.fixture
def cliente(settings):
    abrir_sessao(settings, token=TOKEN)
    with TestClient(create_app(settings)) as c:
        yield c


def manifesto(versao="0.16.0", conteudo=CONTEUDO, **troca) -> dict:
    dados = {
        "produto": "itc-bench",
        "app_id": bench_versao.APP_ID,
        "versao": versao,
        "minima": "0.15.0",
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "tamanho": len(conteudo),
        "notas": "Atualização automática.",
        "publicado_em": "2026-11-08T00:00:00Z",
    }
    return dados | troca


@pytest.fixture
def publicar(settings, tmp_path):
    def rodar(dados=None, conteudo=CONTEUDO, assinatura=b"\x01" * 64):
        dados = manifesto() if dados is None else dados
        (tmp_path / "setup.exe").write_bytes(conteudo)
        (tmp_path / "m.json").write_bytes(json.dumps(dados).encode())
        (tmp_path / "m.sig").write_bytes(assinatura)
        argv = ["publicar", "--arquivo", str(tmp_path / "setup.exe"), "--manifesto", str(tmp_path / "m.json")]
        return bench_versao.main([*argv, "--assinatura", str(tmp_path / "m.sig"), "--operador", "teste"], settings)

    return rodar


def test_sem_versao_204(cliente):
    r = cliente.get("/v1/bench/versao", headers=AUT)
    assert r.status_code == 204
    assert r.headers["cache-control"] == "no-store"


def test_sem_sessao_401(cliente, publicar):
    assert publicar() == 0
    assert cliente.get("/v1/bench/versao").status_code == 401
    sha = manifesto()["sha256"]
    assert cliente.get(f"/v1/bench/versao/arquivo?sha256={sha}").status_code == 401


def test_publicada_devolve_manifesto_exato(cliente, publicar, tmp_path):
    assert publicar() == 0
    r = cliente.get("/v1/bench/versao", headers=AUT)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["versao"] == "0.16.0"
    import base64

    assert base64.b64decode(corpo["manifesto"]) == (tmp_path / "m.json").read_bytes()
    assert base64.b64decode(corpo["assinatura"]) == b"\x01" * 64


def test_arquivo_inteiro_e_range_206(cliente, publicar):
    assert publicar() == 0
    sha = manifesto()["sha256"]
    r = cliente.get(f"/v1/bench/versao/arquivo?sha256={sha}", headers=AUT)
    assert r.status_code == 200
    assert r.content == CONTEUDO
    assert r.headers["cache-control"] == "no-store"
    r = cliente.get(f"/v1/bench/versao/arquivo?sha256={sha}", headers=AUT | {"Range": "bytes=100-"})
    assert r.status_code == 206
    assert r.content == CONTEUDO[100:]
    assert r.headers["content-range"] == f"bytes 100-{len(CONTEUDO) - 1}/{len(CONTEUDO)}"


def test_retomada_nao_gasta_limite_de_download(cliente, publicar):
    assert publicar() == 0
    url = f"/v1/bench/versao/arquivo?sha256={manifesto()['sha256']}"
    assert cliente.get(url, headers=AUT).status_code == 200
    for _ in range(2):
        assert cliente.get(url, headers=AUT | {"Range": "bytes=10-"}).status_code == 206
    assert cliente.get(url, headers=AUT).status_code == 200  # segundo download, dentro do limite 2
    assert cliente.get(url, headers=AUT | {"Range": "bytes=10-"}).status_code == 429
    r = cliente.get(url, headers=AUT)
    assert r.status_code == 429
    assert "retry-after" in r.headers


def test_hash_que_nao_e_o_atual_404(cliente, publicar):
    assert publicar() == 0
    r = cliente.get(f"/v1/bench/versao/arquivo?sha256={'0' * 64}", headers=AUT)
    assert r.status_code == 404
    assert cliente.get("/v1/bench/versao/arquivo?sha256=../x", headers=AUT).status_code == 422


def test_revogada_some_e_volta_a_anterior(cliente, publicar, settings):
    assert publicar() == 0
    outro = CONTEUDO + b"!"
    assert publicar(manifesto("0.17.0", outro), outro) == 0
    assert cliente.get("/v1/bench/versao", headers=AUT).json()["versao"] == "0.17.0"
    assert bench_versao.main(["revogar", "--versao", "0.17.0", "--operador", "teste"], settings) == 0
    assert cliente.get("/v1/bench/versao", headers=AUT).json()["versao"] == "0.16.0"
    r = cliente.get(f"/v1/bench/versao/arquivo?sha256={hashlib.sha256(outro).hexdigest()}", headers=AUT)
    assert r.status_code == 404


def test_cli_recusa_menor_ou_igual(publicar):
    assert publicar() == 0
    assert publicar(manifesto("0.16.0")) == 1
    assert publicar(manifesto("0.15.9")) == 1


def test_cli_recusa_arquivo_que_nao_confere(publicar):
    assert publicar(manifesto(sha256="a" * 64)) == 1
    assert publicar(manifesto(tamanho=len(CONTEUDO) + 1)) == 1


@pytest.mark.parametrize(
    "troca",
    [
        {"produto": "outro"},
        {"app_id": "{00000000-0000-0000-0000-000000000000}"},
        {"versao": "1.0"},
        {"versao": "01.0.0"},
        {"minima": "0.17.0"},
        {"sha256": "A" * 64},
        {"tamanho": True},
        {"notas": "x" * 501},
        {"notas": "linha\x1b[31m"},
        {"extra": 1},
    ],
)
def test_cli_recusa_manifesto_invalido(publicar, troca):
    assert publicar(manifesto(**troca)) == 1


def test_cli_recusa_assinatura_fora_de_p1363(publicar):
    assert publicar(assinatura=b"\x30" * 70) == 1


def test_cli_sem_operador(publicar, settings):
    assert bench_versao.main(["listar", "--operador", " "], settings) == 1


def test_migracao_cria_tabelas(settings):
    db.migrate(settings.database_path)
    conn = db.connect(settings.database_path)
    nomes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"bench_versoes", "bench_versao_uso"} <= nomes
