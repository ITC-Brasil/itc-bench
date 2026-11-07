"""Início (alertas) e Registro (leitura, filtro e exportação mascarada), ADR-023."""

import json
from datetime import UTC, datetime, timedelta

from itc_bench.servicos import executor, inicio, protecao, registro
from itc_bench.servicos.cadastros import Cadastros

AGORA = datetime(2026, 11, 6, 12, tzinfo=UTC)


def _cad(quando: datetime) -> Cadastros:
    return Cadastros("v", quando, "tec", None, False, (), (), (), ())


def _prot(acl: str) -> protecao.Situacao:
    b = {
        exe: protecao.Binario(
            exe, "original", acl if exe in protecao.PROTEGIVEIS else "livre", "limpo"
        )
        for exe in protecao.NOMES
    }
    return protecao.Situacao(b, "desligado")


def test_alertas_criticos_e_atalho_para_a_tela():
    a = inicio.alertas(
        protecao_=_prot("livre"),
        politicas_faltando=2,
        nome_pendente=True,
        suporte=False,
        cadastros=_cad(AGORA - timedelta(days=2)),
        fila=1,
        disco_livre=0.05,
        agora=AGORA,
    )
    telas = {x.tela for x in a}
    assert {"protecao", "gpo", "contas", "id", "config", "diag", "limpeza"} <= telas
    criticos = [x for x in a if x.nivel == "critico"]
    assert all(x.tela in ("protecao", "gpo", "contas") for x in criticos) and criticos


def test_sem_alerta_quando_tudo_certo():
    a = inicio.alertas(
        protecao_=_prot("protegido"),
        politicas_faltando=0,
        nome_pendente=False,
        suporte=True,
        cadastros=_cad(AGORA),
        fila=0,
        disco_livre=0.5,
        agora=AGORA,
    )
    assert a == []


def test_maquina_sem_texto_localizado():
    saida = json.dumps(
        {
            "fabricante": "Fab",
            "modelo": "M1",
            "serie": "X",
            "edicao": "Core",
            "versao": "24H2",
            "build": "26100",
            "disco_total": 100,
            "disco_livre": 40,
            "bateria": 80,
            "na_tomada": True,
        }
    )

    def rodar(script, **k):
        assert "Caption" not in script
        return executor.Resultado(0, saida, "", 0.1, False)

    m = inicio.maquina(rodar=rodar)
    assert m.windows == "Windows Home 24H2 build 26100" and m.bateria == 80


LOG = r"""2026-11-06 10:00:00,123 INFO [tec] itc_bench: Contas: criar Teste01: ok
2026-11-06 10:01:00,000 ERROR [tec] itc_bench: falhou em C:\Users\Teste01\AppData no LAB-07
Traceback (most recent call last):
  linha de baixo
2026-11-06 10:02:00,000 WARNING [-] itc_bench: aviso qualquer
"""


def test_ler_rotacionados_em_ordem(tmp_path):
    (tmp_path / "bench.log.1").write_text(LOG, "utf-8")
    (tmp_path / "bench.log").write_text(
        "2026-11-06 11:00:00,000 INFO [tec] itc_bench: novo\n", "utf-8"
    )
    (tmp_path / "outro.txt").write_text(LOG, "utf-8")
    linhas = registro.ler(tmp_path)
    assert [ln.texto.split(": ")[-1] for ln in linhas][-1] == "novo"
    assert len(linhas) == 4 and "linha de baixo" in linhas[1].texto


def test_filtrar_por_nivel_e_texto():
    linhas = registro.interpretar(LOG)
    assert len(registro.filtrar(linhas, "WARNING")) == 2
    assert len(registro.filtrar(linhas, "INFO", "teste01")) == 2


def test_exportar_mascara_sem_dado_novo(tmp_path):
    linhas = registro.interpretar(LOG)
    destino = tmp_path / "saida.txt"
    n = registro.exportar(linhas, destino, "LAB-07", ["Teste01", "tec"])
    texto = destino.read_text("utf-8")
    assert n == 3
    for proibido in ("Teste01", "LAB-07", r"C:\Users"):
        assert proibido not in texto
    assert "<perfil>" in texto and "<computador>" in texto and "<conta-" in texto
    assert texto.count("\n") == sum(str(ln).count("\n") + 1 for ln in linhas)
