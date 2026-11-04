"""Online x offline (ADR-013): só falta de servidor libera o offline."""

import pytest

from itc_bench.servicos import api, login
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.offline import Cofre, OfflineRecusado

SENHA = "Marcador-Senha-7Q2x!"
BASE = "https://api.exemplo.invalid"


@pytest.fixture
def cofre(tmp_path):
    c = Cofre(tmp_path / "logins.dpapi")
    c.lembrar("ana.lima", "Ana Lima", Sensivel(SENHA))
    return c


def api_que(monkeypatch, erro: Exception | None = None):
    def entrar(base, usuario, senha, maquina):
        if erro:
            raise erro
        return api.SessaoApi(Sensivel("itcbs_x"), usuario, "Ana Lima", "2026-11-05T00:00:00Z")

    monkeypatch.setattr(api, "entrar", entrar)


def test_online_lembra_no_cofre(monkeypatch, tmp_path):
    api_que(monkeypatch)
    c = Cofre(tmp_path / "logins.dpapi")
    e = login.entrar("Ana.Lima", Sensivel(SENHA), base=BASE, maquina="NB", cofre=c)
    assert not e.offline and e.rotulo_log == "ana.lima"
    assert c.conferir("ana.lima", Sensivel(SENHA)) == "Ana Lima"


@pytest.mark.parametrize("motivo", ["URLError", "http_502", "http_530", "glpi_indisponivel"])
def test_sem_servidor_cai_para_offline(monkeypatch, cofre, motivo):
    api_que(monkeypatch, api.SemConexao(motivo))
    e = login.entrar("ana.lima", Sensivel(SENHA), base=BASE, maquina="NB", cofre=cofre)
    assert e.offline and e.rotulo_log == "ana.lima (offline)"


@pytest.mark.parametrize(
    "erro",
    [
        api.Recusado(401, "credenciais_invalidas"),
        api.Recusado(403, "fora_do_perfil"),
        api.Recusado(429, "limite_excedido"),
        api.ErroApi("html"),
    ],
)
def test_recusa_nunca_cai_para_offline(monkeypatch, cofre, erro):
    api_que(monkeypatch, erro)
    with pytest.raises(type(erro)):
        login.entrar("ana.lima", Sensivel(SENHA), base=BASE, maquina="NB", cofre=cofre)


@pytest.mark.parametrize(("status", "apaga"), [(401, True), (403, True), (429, False)])
def test_401_e_403_apagam_o_offline(monkeypatch, cofre, status, apaga):
    api_que(monkeypatch, api.Recusado(status, "x"))
    with pytest.raises(api.Recusado):
        login.entrar("ana.lima", Sensivel(SENHA), base=BASE, maquina="NB", cofre=cofre)
    assert cofre.tem("ana.lima") is not apaga


def test_sem_pasta_protegida_sem_offline(monkeypatch):
    api_que(monkeypatch, api.SemConexao("URLError"))
    with pytest.raises(OfflineRecusado, match="sem_pasta_protegida"):
        login.entrar("ana.lima", Sensivel(SENHA), base=BASE, maquina="NB", cofre=None)


def test_sem_endereco_usa_offline(cofre):
    e = login.entrar("ana.lima", Sensivel(SENHA), base=None, maquina="NB", cofre=cofre)
    assert e.offline


def test_destravar(cofre):
    atual = login.Entrada("ana.lima", "Ana Lima", None)
    assert login.destravar(atual, "Ana.Lima", Sensivel(SENHA), cofre)
    with pytest.raises(OfflineRecusado, match="senha_errada"):
        login.destravar(atual, "ana.lima", Sensivel("errada"), cofre)
    # Outro técnico, ou sem pasta protegida: login completo.
    assert not login.destravar(atual, "outro", Sensivel(SENHA), cofre)
    assert not login.destravar(atual, "ana.lima", Sensivel(SENHA), None)
