"""Coletores (ADR-015): regras portadas com os casos do `Testar-Ferramenta.ps1` do pendrive."""

import json
import threading
from datetime import datetime
from pathlib import Path

import pytest

from itc_bench.servicos import coleta
from itc_bench.servicos.executor import Resultado

API_BASE = Path(__file__).parents[2] / "api" / "app" / "eventlog-conhecidos.json"


def res(saida: str = "{}", codigo: int | None = 0, esgotado=False, cancelado=False) -> Resultado:
    return Resultado(codigo, saida, "", 0.1, esgotado, cancelado)


# ---- paridade com o Testar-Ferramenta.ps1


def test_smart_wear_sem_conversao_e_nulo_nunca_zero():
    r: dict = {}
    coleta.contadores_smart(r, {"percentualDesgaste": 3, "temperaturaC": 41})
    assert r["percentualDesgaste"] == 3 and "percentualVidaRestante" not in r
    r = {}
    coleta.contadores_smart(r, {"percentualDesgaste": None, "temperaturaC": 41})
    assert r["percentualDesgaste"] is None


def test_smart_tres_estados_e_temperatura_zero():
    r: dict = {}
    coleta.contadores_smart(r, {"temperaturaC": 41, "percentualDesgaste": 2})
    assert r["estadoSmart"] == "parcial"
    assert "horasLigado" in r["observacao"] and "temperaturaC," not in r["observacao"]
    r = {}
    coleta.contadores_smart(
        r,
        dict.fromkeys(coleta.CONTADORES_SMART[:4], 0)
        | {
            "temperaturaC": 40,
            "temperaturaMaximaC": 70,
            "horasLigado": 1200,
            "percentualDesgaste": 5,
        },
    )
    assert r["estadoSmart"] == "completo" and "observacao" not in r
    r = {}
    coleta.contadores_smart(r, {"numero": "0"})
    assert r["estadoSmart"] == "indisponivel"
    r = {}
    coleta.contadores_smart(
        r, {"temperaturaC": 0, "temperaturaMaximaC": 0, "percentualDesgaste": 0}
    )
    assert r["temperaturaC"] is None and r["temperaturaMaximaC"] is None


def test_apipa():
    assert coleta.apipa("Up", ["169.254.10.20"])
    assert not coleta.apipa("Disconnected", ["169.254.10.20"])
    assert not coleta.apipa("Up", ["192.0.2.10"])
    assert not coleta.apipa("Up", [])


def test_relatorio_de_bateria_e_faixas():
    html = (
        '<table><tr><td class="label">DESIGN CAPACITY</td><td>44.000 mWh</td></tr>\n'
        '<tr><td class="label">FULL CHARGE CAPACITY</td><td>33.000 mWh</td></tr>\n'
        '<tr><td class="label">CYCLE COUNT</td><td>212</td></tr></table>'
    )
    b = coleta.relatorio_bateria(html)
    assert (b["capacidadeProjetoMWh"], b["capacidadeAtualMWh"], b["ciclos"]) == (44000, 33000, 212)
    assert b["desgastePercentual"] == 25
    assert coleta.classificacao_desgaste(25) == "desgaste-moderado"
    assert coleta.relatorio_bateria("<html>sem dados</html>")["desgastePercentual"] is None
    faixas = [
        (None, "desconhecido"),
        (19.9, "saudavel"),
        (20, "desgaste-moderado"),
        (40, "desgaste-alto"),
        (60, "substituicao-recomendada"),
    ]
    for valor, esperado in faixas:
        assert coleta.classificacao_desgaste(valor) == esperado


def test_eventlog_ordem_nivel_e_mensagem_so_fora_da_base():
    cru = {
        "grupos": [
            {"provedor": "disk", "id": 51, "nivelMinimo": 3, "ocorrencias": 53, "mensagem": "x"},
            {
                "provedor": "Outro",
                "id": 7,
                "nivelMinimo": 2,
                "ocorrencias": 2,
                "mensagem": "erro y",
            },
            {"provedor": "Kernel", "id": 41, "nivelMinimo": 1, "ocorrencias": 1, "mensagem": "z"},
            {"provedor": "Lixo", "id": "abc", "nivelMinimo": 2},
            {"provedor": "Lixo", "id": 1, "nivelMinimo": 9},
        ]
    }
    d = coleta.eventlog(cru, ["disk|51"])
    assert [g["nivel"] for g in d["grupos"]] == ["critico", "erro", "aviso"]
    disk = d["grupos"][2]
    assert disk["ocorrencias"] == 53 and disk["exemploMensagem"] is None
    assert d["grupos"][1]["exemploMensagem"] == "erro y"
    assert (d["totalGrupos"], d["gruposCriticos"], d["avisoSomenteBase"]) == (3, 1, True)
    assert "conhecido" not in disk  # a API classifica (TA-ADR-028)


def test_pares_derivados_iguais_a_base_da_api():
    base = json.loads(API_BASE.read_text("utf-8"))["eventos"]
    esperado = sorted({f"{e['provedor']}|{int(e['id'])}" for e in base}, key=str.lower)
    assert coleta.pares_da_base() == esperado


def test_processos_limites_conta_e_sem_usuario_de_inicializacao():
    cru = {
        "memoriaTotalKB": 8 * 2**20,
        "memoriaLivreKB": 2**20,
        "processos": [
            {"nome": f"p{i}", "pid": i, "memoriaBytes": i * 2**20, "cpuSegundos": i}
            for i in range(40)
        ],
        "servicos": [
            {"nome": "a", "contaLogon": "LocalSystem"},
            {"nome": "b", "contaLogon": r"NT AUTHORITY\LocalService"},
            {"nome": "c", "contaLogon": r"DOMINIO\pessoa"},
        ],
        "inicializacao": [{"nome": "x", "comando": "y", "origem": "z", "usuario": "pessoa"}],
    }
    d = coleta.processos(cru)
    assert len(d["processosPorMemoria"]) == 15 and d["processosPorMemoria"][0]["nome"] == "p39"
    assert len(d["processosPorCpu"]) == 10
    assert d["memoria"]["percentualEmUso"] == 87.5 and d["memoria"]["pressaoAlta"]
    assert [s["contaLogon"] for s in d["servicosAutomaticosParados"]] == [
        "LocalSystem",
        r"NT AUTHORITY\LocalService",
        "<conta>",
    ]
    assert "usuario" not in d["itensInicializacao"][0]


def test_saida_hostil_validada():
    cru = {
        "processos": "lixo",
        "servicos": [1, None, {"nome": "x" * 5000}],
        "memoriaTotalKB": "abc",
        "avisos": ["a" * 2000],
    }
    d = coleta.processos(cru)
    assert d["processosPorMemoria"] == []
    assert len(d["servicosAutomaticosParados"][0]["nome"]) <= 103
    assert len(d["avisos"][0]) <= 503
    assert d["memoria"]["totalGB"] is None
    # PS 5.1 entrega objeto onde devia vir lista de um item
    assert len(coleta.rede({"adaptadores": {"nome": "a", "status": "Up"}})["adaptadores"]) == 1


# ---- varredura dos perfis


def test_varredura_sem_nome_de_arquivo_ignora_public_e_link(tmp_path, monkeypatch):
    monkeypatch.setattr(coleta, "ARQUIVO_MINIMO_MB", 0)
    monkeypatch.setattr(coleta, "PASTA_MINIMA_MB", 0)
    docs = tmp_path / "usuario-a" / "Documentos"
    docs.mkdir(parents=True)
    (docs / "relatorio-secreto.PDF").write_bytes(b"x" * 10)
    (tmp_path / "Public" / "Docs").mkdir(parents=True)
    (tmp_path / "Public" / "Docs" / "p.txt").write_bytes(b"x")
    r = coleta.varrer_perfis(tmp_path)
    assert r["pastas"] == [{"caminho": str(docs), "bytes": 10, "arquivos": 1}]
    assert r["arquivos"][0]["extensao"] == ".pdf" and r["arquivos"][0]["pasta"] == str(docs)
    assert "relatorio-secreto" not in json.dumps(r)


def test_varredura_cancelada(tmp_path):
    (tmp_path / "u" / "d").mkdir(parents=True)
    evento = threading.Event()
    evento.set()
    with pytest.raises(coleta.Cancelado):
        coleta.varrer_perfis(tmp_path, evento)


def test_varredura_estoura_o_tempo(tmp_path):
    (tmp_path / "u" / "d").mkdir(parents=True)
    r = coleta.varrer_perfis(tmp_path, limite=-1)
    assert "interrompida" in r["avisos"][0]


# ---- orquestração


MARCAS = {
    "processos": "processos",
    "rede": "rede",
    "eventlog": "Event Log",
    "disco": "disco",
    "bateria": "bateria",
    "maquina": "Identificação",
}


def _fake(saidas: dict[str, Resultado]):
    def rodar(script: str, **_kw):
        cabecalho = script.splitlines()[0]
        for nome, r in saidas.items():
            if MARCAS[nome] in cabecalho:
                return r
        return res()

    return rodar


def _sem_powercfg(*_a, **_k):
    return res()


def test_coletor_que_falha_ou_esgota_nao_derruba(tmp_path):
    rodar = _fake(
        {
            "processos": res("não é json"),
            "rede": res(esgotado=True, codigo=None),
            "eventlog": res(codigo=3),
        }
    )
    c = coleta.coletar(elevado=True, rodar=rodar, executar=_sem_powercfg, perfis=tmp_path)
    estados = {n: (m.status, m.erro) for n, m in c.modulos.items()}
    assert estados["processos"] == ("erro", "saída que não é JSON")
    assert estados["rede"] == ("erro", "tempo esgotado")
    assert estados["eventlog"] == ("erro", "código 3")
    assert estados["disco"][0] == "ok" and estados["bateria"][0] == "ok"
    assert c.encerrada_normalmente and c.fim is not None


def test_cancelamento_guarda_o_que_ficou_pronto(tmp_path):
    rodar = _fake({"eventlog": res(cancelado=True, codigo=None)})
    progresso: list[str] = []
    c = coleta.coletar(
        elevado=False,
        rodar=rodar,
        executar=_sem_powercfg,
        perfis=tmp_path,
        ao_progresso=lambda n, m: progresso.append(n),
    )
    assert list(c.modulos) == ["processos", "rede"]
    assert not c.encerrada_normalmente
    assert any("cancelada" in a for a in c.avisos)
    assert any("sem administrador" in a for a in c.avisos)


def test_nomes_pessoais_da_sessao_e_perfis(tmp_path, monkeypatch):
    for nome in ("usuario-a", "Public", "defaultuser0", "Default"):
        (tmp_path / nome).mkdir()
    monkeypatch.setenv("USERNAME", "conta-elevada")
    maq = res(json.dumps({"usuarioSessao": r"DOMINIO\pessoa-b", "numeroSerie": "SERIAL-TESTE"}))
    c = coleta.coletar(
        elevado=True,
        rodar=_fake({"maquina": maq}),
        executar=_sem_powercfg,
        perfis=tmp_path,
        agora=lambda: datetime(2026, 11, 4, 10, 0).astimezone(),
    )
    assert c.nomes_pessoais == ["conta-elevada", "pessoa-b", "usuario-a"]
    assert c.maquina["numeroSerie"] == "SERIAL-TESTE"
    assert "usuarioSessao" not in c.maquina
    assert c.id.startswith("2026-11-04_1000_")


@pytest.mark.parametrize("nome", ["processos", "rede", "eventlog", "disco", "bateria", "maquina"])
def test_trechos_powershell_cabem_no_executor(nome):
    from itc_bench.servicos import executor

    assert len(executor.ABERTURA_PS + coleta.script(nome)) < executor.LIMITE_SCRIPT
