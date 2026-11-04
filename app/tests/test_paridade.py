"""Paridade com o pendrive (ADR-015) sobre saídas gravadas na mesma máquina e anonimizadas.

Cada `tests/gravacoes/<módulo>.json` tem o JSON cru do trecho do Bench (`bench`) e o do coletor
do pendrive (`pendrive`), gravados em seguida por `scripts/gravar_paridade.py`. Compara só o que
não muda entre as duas execuções (memória e carga, por exemplo, mudam).
"""

import ipaddress
import json
import os
import re
from pathlib import Path

import pytest

from itc_bench.servicos import coleta

GRAVACOES = Path(__file__).parent / "gravacoes"
DOCUMENTACAO = [
    ipaddress.ip_network(r) for r in ("192.0.2.0/24", "198.51.100.0/24", "2001:db8::/32")
]
IPS_PERMITIDOS = {"0.0.0.0", "1.1.1.1", "8.8.8.8", "255.255.255.255", "::"}  # noqa: S104
MAC_FICTICIO = "02-00-5E-10-00-"
PERFIS_FICTICIOS = re.compile(r"(?i)^(usuario-[a-z]|usuario-sessao|public|default)$")


def gravacao(nome: str) -> dict:
    return json.loads((GRAVACOES / f"{nome}.json").read_text("utf-8"))


def test_gravacoes_anonimas():
    arquivos = sorted(GRAVACOES.glob("*.json"))
    assert {a.stem for a in arquivos} == set(coleta.ROTULOS)
    proibidos = {
        v.lower() for v in (os.environ.get("COMPUTERNAME"), os.environ.get("USERNAME")) if v
    }
    for arquivo in arquivos:
        texto = arquivo.read_text("utf-8")
        for bruto in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", texto):
            try:
                ip = ipaddress.ip_address(bruto)
            except ValueError:
                continue  # versão de programa, não endereço
            ok = bruto in IPS_PERMITIDOS or ip.is_loopback or ip.is_link_local
            assert ok or any(ip in rede for rede in DOCUMENTACAO), f"{arquivo.name}: IP {bruto}"
        for mac in re.findall(r"\b(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}\b", texto):
            assert mac.upper().startswith(MAC_FICTICIO), f"{arquivo.name}: MAC {mac}"
        for perfil in re.findall(r"(?i)\\\\users\\\\([^\\\\\"]+)", texto):
            assert PERFIS_FICTICIOS.match(perfil), f"{arquivo.name}: perfil {perfil}"
        for valor in proibidos:
            assert valor not in texto.lower(), f"{arquivo.name}: nome desta máquina ou conta"


def test_processos():
    g = gravacao("processos")
    bench, pendrive = coleta.processos(g["bench"]), g["pendrive"]
    chave = lambda s: (s["nome"], s["contaLogon"], s["atrasado"])  # noqa: E731
    assert sorted(map(chave, bench["servicosAutomaticosParados"])) == sorted(
        map(chave, pendrive["servicosAutomaticosParados"])
    )
    item = lambda i: (i["nome"], i["origem"])  # noqa: E731
    assert sorted(map(item, bench["itensInicializacao"])) == sorted(
        map(item, pendrive["itensInicializacao"])
    )
    assert bench["memoria"]["totalGB"] == pendrive["memoria"]["totalGB"]


def test_rede():
    g = gravacao("rede")
    bench, pendrive = coleta.rede(g["bench"]), g["pendrive"]
    campos = (
        "nome",
        "status",
        "macAddress",
        "enderecosIPv4",
        "gateway",
        "servidoresDNS",
        "dhcp",
        "semIP",
        "apipa",
    )
    assert [[a[c] for c in campos] for a in bench["adaptadores"]] == [
        [a[c] for c in campos] for a in pendrive["adaptadores"]
    ]
    for chave in ("adaptadoresAtivos", "temIPValido", "internetOk", "dnsOk"):
        assert bench["resumo"][chave] == pendrive["resumo"][chave], chave
    # Portas não entram: Get-NetTCPConnection devolve conjuntos diferentes a cada chamada, e o
    # pendrive ainda descartava portas ao acaso (Sort-Object -Unique do PS 5.1). Uma por porta:
    portas = [p["porta"] for p in bench["portasEmEscuta"]]
    assert portas == sorted(set(portas))


def test_eventlog():
    g = gravacao("eventlog")
    bench = coleta.eventlog(g["bench"], coleta.pares_da_base())
    pendrive = g["pendrive"]
    campos = (
        "log",
        "provedor",
        "id",
        "nivel",
        "ocorrencias",
        "primeiraOcorrencia",
        "ultimaOcorrencia",
    )
    # Empate de ocorrências: o Sort-Object do pendrive não é estável; compara sem a ordem.
    chave = lambda x: [x[c] for c in campos] + [x["exemploMensagem"] is None]  # noqa: E731
    assert sorted(map(chave, bench["grupos"])) == sorted(map(chave, pendrive["grupos"]))
    nivel = [coleta.ORDEM_NIVEL[x["nivel"]] for x in bench["grupos"]]
    assert nivel == sorted(nivel)
    for chave in ("totalOcorrencias", "totalGrupos", "gruposCriticos"):
        assert bench[chave] == pendrive[chave], chave


def test_disco():
    g = gravacao("disco")
    bench = coleta.disco(g["bench"], g["varredura"], elevado=True)
    pendrive = g["pendrive"]
    volume = lambda v: (v["letra"], v["tipo"], v["totalGB"], v["sistemaArquivos"])  # noqa: E731
    assert list(map(volume, bench["volumes"])) == list(map(volume, pendrive["volumes"]))
    campos = (
        "numero",
        "modelo",
        "barramento",
        "tamanhoGB",
        "estadoSmart",
        "percentualDesgaste",
        "errosLeituraNaoCorrigidos",
    )
    assert [[d[c] for c in campos] for d in bench["discosFisicos"]] == [
        [d[c] for c in campos] for d in pendrive["discosFisicos"]
    ]
    assert {p["caminho"] for p in bench["maioresPastasPerfil"]} == {
        p["caminho"] for p in pendrive["maioresPastasPerfil"]
    }
    # Arquivo grande: no Bench só a pasta de 2º nível (sem nome); no pendrive a gravação guarda a
    # pasta onde o arquivo está. Mesmos tamanhos, e a pasta do pendrive fica dentro da do Bench.
    bench_arq = sorted((a["bytes"], a["pasta"]) for a in bench["maioresArquivos"])
    pend_arq = sorted((a["bytes"], a["caminho"]) for a in pendrive["maioresArquivos"])
    assert [b for b, _ in bench_arq] == [b for b, _ in pend_arq]
    pastas = {p for _, p in bench_arq}
    assert all(any(c == p or c.startswith(p + "\\") for p in pastas) for _, c in pend_arq)


def test_bateria():
    g = gravacao("bateria")
    bench = coleta.bateria(g["bench"], None, None)
    pendrive = g["pendrive"]
    assert bench["presente"] == pendrive["presente"]
    assert [b["nome"] for b in bench["baterias"]] == [b["nome"] for b in pendrive["baterias"]]


@pytest.mark.parametrize("nome", list(coleta.ROTULOS))
def test_saneamento_das_gravacoes(nome):
    """O corpo montado a partir da gravação não leva caminho de perfil nem nome fictício."""
    from itc_bench.servicos import diagnostico

    texto = json.dumps(diagnostico.sanear(gravacao(nome)["bench"], ["usuario-a", "usuario-b"]))
    assert "usuario-a" not in texto and "usuario-b" not in texto
    assert not re.search(r"(?i)[a-z]:\\\\users\\\\usuario-", texto)
