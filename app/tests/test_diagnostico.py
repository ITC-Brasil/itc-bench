"""Corpo 1.3, saneamento e envio (ADR-015, ADR-016)."""

import json
import logging
from datetime import datetime, timedelta
from io import BytesIO
from urllib.error import HTTPError

import pytest

from itc_bench.servicos import api, coleta, diagnostico
from itc_bench.servicos.executor import Sensivel


def test_caminho_de_perfil_vira_perfil_e_public_fica():
    s = diagnostico.sanear(
        [r"C:\Users\Marcador.Pessoa\AppData\x.exe", r"D:\users\outra\y", r"C:\Users\Public\z"], []
    )
    assert s == [r"%PERFIL%\AppData\x.exe", r"%PERFIL%\y", r"C:\Users\Public\z"]


def test_nome_de_perfil_palavra_inteira_sem_mutilar():
    texto = "Logon de admin falhou; grupo Administrators e administrador intactos; ADMIN saiu."
    s = diagnostico.sanear({"msg": texto, "admin": 1}, ["admin"])
    assert s["msg"] == (
        "Logon de <usuario> falhou; grupo Administrators e administrador intactos; <usuario> saiu."
    )
    assert "admin" in s  # chave não muda


def test_nome_de_tres_letras_e_curtos_ignorados():
    s = diagnostico.sanear(
        "ana entrou; anabela não; jo ficou; Default ficou", ["ana", "jo", "Default"]
    )
    assert s == "<usuario> entrou; anabela não; jo ficou; Default ficou"


def _coleta() -> coleta.Coleta:
    inicio = datetime(2026, 11, 4, 10, 0).astimezone()
    c = coleta.Coleta("TESTE-NB-01", inicio, True, {"numeroSerie": "SERIAL-TESTE", "modelo": "M"})
    c.nomes_pessoais = ["marcador-pessoa"]
    c.modulos["processos"] = coleta.Modulo(
        "processos",
        "ok",
        None,
        inicio,
        1.0,
        {
            "itensInicializacao": [
                {"comando": r"C:\Users\marcador-pessoa\app.exe --user marcador-pessoa"}
            ],
        },
    )
    c.fim = inicio + timedelta(seconds=40)
    c.encerrada_normalmente = True
    return c


def test_corpo_1_3_sem_marcadores():
    corpo = diagnostico.montar(
        _coleta(), "tecnico.login", "0b8f0d7e-0000-4000-8000-000000000000", "UM-01"
    )
    texto = json.dumps(corpo)
    assert "marcador-pessoa" not in texto.lower()
    assert corpo["sessao"]["versaoSchema"] == "1.3" and corpo["sessao"]["origem"] == "bench"
    assert corpo["sessao"]["coletadoPor"] == "tecnico.login"
    assert "usuarioExecucao" not in corpo["sessao"] and corpo["sessao"]["usuarioSessao"] is None
    assert corpo["sessao"]["maquina"]["numeroSerie"] == "SERIAL-TESTE"
    assert corpo["modulos"]["processos"]["dados"]["itensInicializacao"][0]["comando"] == (
        r"%PERFIL%\app.exe --user <usuario>"
    )
    assert corpo["sessao"]["duracaoSegundos"] == 40 and corpo["envio_id"].startswith("0b8f")


def test_corpo_grande_reduzido_na_ordem(monkeypatch):
    c = _coleta()
    c.modulos["eventlog"] = coleta.Modulo(
        "eventlog",
        "ok",
        None,
        c.inicio,
        1,
        {"grupos": [{"id": i, "exemploMensagem": "m" * 300} for i in range(150)]},
    )
    monkeypatch.setattr(diagnostico, "LIMITE_CORPO", 20_000)
    corpo = diagnostico.montar(c, "t", "id", None)
    grupos = corpo["modulos"]["eventlog"]["dados"]["grupos"]
    assert all(g["exemploMensagem"] is None for g in grupos) and len(grupos) == 150
    monkeypatch.setattr(diagnostico, "LIMITE_CORPO", 100)
    with pytest.raises(ValueError):
        diagnostico.montar(c, "t", "id", None)


def test_hostname_validado():
    assert diagnostico.hostname_valido("teste-nb-01") == "TESTE-NB-01"
    for ruim in ("../x", "a b", "", "x" * 70, "a/b"):
        with pytest.raises(ValueError):
            diagnostico.hostname_valido(ruim)


class _Resposta:
    def __init__(self, status, corpo, tipo="application/json", headers=None):
        self.status, self._corpo = status, corpo
        self.headers = {"Content-Type": tipo, **(headers or {})}

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _api(monkeypatch, status, corpo, tipo="application/json", headers=None):
    vistos = []

    def abrir(req, timeout):
        vistos.append((req, timeout))
        bruto = json.dumps(corpo).encode() if not isinstance(corpo, bytes) else corpo
        if status >= 400:
            raise HTTPError(
                req.full_url, status, "x", {"Content-Type": tipo, **(headers or {})}, BytesIO(bruto)
            )
        return _Resposta(status, bruto, tipo, headers)

    monkeypatch.setattr(api._abridor, "open", abrir)
    return vistos


LAUDO = {
    "relatorio_md": "## R",
    "chamado_titulo": "T",
    "chamado_descricao": "D",
    "maior_confianca": "ALTA",
    "modelo": "m",
    "diagnostico_id": 7,
}


def test_envio_ok_timeout_longo_e_sessao_no_cabecalho(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    vistos = _api(monkeypatch, 200, LAUDO)
    corpo = {"envio_id": "abcdef12-3456", "sessao": {"x": "marcador-corpo"}}
    laudo = diagnostico.enviar("https://api.exemplo.invalid", Sensivel("itcbs_marcador"), corpo)
    assert laudo.diagnostico_id == 7 and laudo.relatorio_md == "## R"
    req, timeout = vistos[0]
    assert timeout == api.TIMEOUT_RELATORIO
    assert req.full_url.endswith("/v1/bench/relatorio")
    assert req.get_header("Authorization") == "Bearer itcbs_marcador"
    assert "marcador" not in caplog.text and "abcdef12" in caplog.text


@pytest.mark.parametrize(
    ("status", "corpo", "tipo", "esperado"),
    [
        (503, {"erro": "ia_timeout"}, "application/json", api.IaFalhou),
        (502, {"erro": "ia_resposta_invalida"}, "application/json", api.IaFalhou),
        (401, {"erro": "nao_autorizado"}, "application/json", api.Recusado),
        (409, {"erro": "em_processamento"}, "application/json", api.Recusado),
        (429, {"erro": "limite_excedido"}, "application/json", api.Recusado),
        (524, b"<html>timeout</html>", "text/html", api.ErroApi),
        (530, b"<html>tunnel</html>", "text/html", api.SemConexao),
        (503, {"erro": "glpi_indisponivel"}, "application/json", api.SemConexao),
    ],
)
def test_envio_falhas(monkeypatch, status, corpo, tipo, esperado):
    _api(monkeypatch, status, corpo, tipo, {"Retry-After": "120"})
    with pytest.raises(esperado) as erro:
        diagnostico.enviar("https://x.exemplo.invalid", Sensivel("t"), {"envio_id": "e"})
    assert diagnostico.mensagem(erro.value)


def test_mensagens():
    assert "IA" in diagnostico.mensagem(api.IaFalhou("ia_timeout"))
    assert "2 min" in diagnostico.mensagem(api.Recusado(429, "limite_excedido", 120))
    assert "Aguarde" in diagnostico.mensagem(api.Recusado(409, "em_processamento"))
    assert "fila" in diagnostico.mensagem(api.SemConexao("x"))


def test_historico_usa_hostname_validado(monkeypatch):
    vistos = _api(monkeypatch, 200, {"hostname": "TESTE-NB-01", "diagnosticos": [{"a": 1}, 3]})
    itens = diagnostico.historico("https://x.exemplo.invalid", Sensivel("t"), "teste-nb-01")
    assert itens == [{"a": 1}]
    assert vistos[0][0].full_url.endswith("/v1/bench/historico/TESTE-NB-01")
    with pytest.raises(ValueError):
        diagnostico.historico("https://x.exemplo.invalid", Sensivel("t"), "../relatorio")
