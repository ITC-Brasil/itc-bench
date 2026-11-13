"""Ponteiro colorido (ADR-046): recolorir, gerar numa pasta de teste e gravar só caminhos válidos.

Nada grava na pasta real do Bench nem no registro da conta: a geração usa a pasta do pytest e o
trecho real só é chamado com valores que ele recusa antes de abrir o registro.
"""

import json
import struct
import sys

import pytest
from test_politicas import ALUNO, PROT, Falso, alvo

from itc_bench.servicos import aparencia as ap
from itc_bench.servicos import cursores, executor, hive


def _cur(pixels: list[tuple[int, int, int, int]], lado: int = 2) -> bytes:
    """`.cur` mínimo: uma imagem BMP 32 bits lado x lado, mais a máscara."""
    corpo = struct.pack("<IiiHHIIiiII", 40, lado, lado * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    corpo += b"".join(struct.pack("<BBBB", b, g, r, a) for r, g, b, a in pixels)
    corpo += b"\x00" * (4 * lado)  # máscara AND
    cab = struct.pack("<HHH", 0, 2, 1)
    entrada = struct.pack("<BBBBHHII", lado, lado, 0, 0, 0, 0, len(corpo), 6 + 16)
    return cab + entrada + corpo


def _pixels(dados: bytes, lado: int = 2) -> list[tuple[int, int, int, int]]:
    inicio = 6 + 16 + 40
    saida = []
    for i in range(lado * lado):
        b, g, r, a = struct.unpack_from("<BBBB", dados, inicio + 4 * i)
        saida.append((r, g, b, a))
    return saida


def test_recolorir_troca_o_branco_e_mantem_preto_e_transparencia() -> None:
    origem = _cur([(255, 255, 255, 255), (0, 0, 0, 255), (128, 128, 128, 200), (255, 255, 255, 0)])
    novo = cursores.recolorir(origem, (0xBF, 0xFF, 0x00))
    assert _pixels(novo) == [
        (0xBF, 0xFF, 0x00, 255),
        (0, 0, 0, 255),
        (95, 128, 0, 200),
        (0xBF, 0xFF, 0x00, 0),
    ]
    assert len(novo) == len(origem)


@pytest.mark.parametrize(
    "dados",
    [
        b"",
        struct.pack("<HHH", 0, 1, 1) + b"\x00" * 100,  # .ico, não .cur
        _cur([(1, 1, 1, 1)] * 4).replace(struct.pack("<H", 32), struct.pack("<H", 24), 1),
        _cur([(1, 1, 1, 1)] * 4)[:40],
    ],
)
def test_recolorir_recusa_o_que_nao_conhece(dados: bytes) -> None:
    with pytest.raises(cursores.ErroCursor):
        cursores.recolorir(dados, (1, 2, 3))


def test_cor_fora_da_lista() -> None:
    with pytest.raises(ValueError):
        cursores.pasta("verde-musgo")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_preparar_gera_os_cursores_do_windows_recoloridos(tmp_path) -> None:
    destino = cursores.preparar("limao", base=tmp_path)
    nomes = sorted(p.name for p in destino.iterdir())
    assert nomes == sorted(cursores.FUNCOES.values())
    original = (cursores.pasta_windows() / "aero_arrow.cur").read_bytes()
    assert (destino / "aero_arrow.cur").read_bytes() == cursores.recolorir(
        original, cursores.CORES["limao"][1]
    )


def test_opcoes_e_escritas_do_ponteiro_colorido() -> None:
    p = ap.POR_ID["ponteiro"]
    assert {"limao_1", "roxo_15"} <= set(p.opcoes)
    escritas = {n: d for _, n, _, d in p.escritas("rosa_6")}
    assert escritas["Arrow"] == str(cursores.arquivo("rosa", "Arrow"))
    assert escritas["Wait"] == r"%SystemRoot%\cursors\aero_busy.ani"  # animado fica o do Windows
    assert escritas["CursorType"] == 0 and escritas["CursorSize"] == 6


def test_todo_ponteiro_do_catalogo_passa_na_regra_do_trecho() -> None:
    """A regra de `escrever.ps1` aceita todos os caminhos que o catálogo grava, e só eles."""
    import re

    trecho = hive.script("escrever")
    windows = re.search(r"\$windows = '([^']+)'", trecho)
    assert windows is not None
    regra = re.compile(windows.group(1), re.IGNORECASE)
    pasta_bench = str(cursores.pasta("limao").parent).lower() + "\\"
    cores = "|".join(cursores.CORES)
    assert f"({cores})" in trecho  # a lista de cores do trecho é a mesma do Python
    p = ap.POR_ID["ponteiro"]
    for opcao in p.opcoes:
        for chave, nome, tipo, dado in p.escritas(opcao):
            if chave != r"Control Panel\Cursors" or tipo != "expand_sz" or not dado:
                continue
            valor = str(dado)
            assert regra.match(valor) or valor.lower().startswith(pasta_bench), (opcao, nome)


def test_aplicar_colorido_gera_antes_e_falha_sem_gravar() -> None:
    geradas: list[str] = []
    f = Falso()
    feitos = ap.aplicar(
        "aplicar",
        {"ponteiro": "amarelo_1"},
        [alvo(ALUNO, True)],
        protegidas_=PROT,
        rodar=f,
        preparar_cursores=geradas.append,
    )
    assert geradas == ["amarelo"] and all(x.ok for x in feitos)

    def falha(_cor: str) -> None:
        raise cursores.ErroCursor("cabeçalho")

    f2 = Falso()
    feitos = ap.aplicar(
        "aplicar",
        {"ponteiro": "amarelo_1"},
        [alvo(ALUNO, True)],
        protegidas_=PROT,
        rodar=f2,
        preparar_cursores=falha,
    )
    assert [x.ok for x in feitos] == [False] and "cabeçalho" in feitos[0].mensagem
    assert not [n for n, _ in f2.chamadas if n == "escrever"]
    f3 = Falso()
    ap.aplicar(
        "aplicar",
        {"ponteiro": "preto_1"},
        [alvo(ALUNO, True)],
        protegidas_=PROT,
        rodar=f3,
        preparar_cursores=falha,  # nem chamado: preto vem do Windows
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
@pytest.mark.parametrize(
    "dado",
    [
        r"C:\Temp\virus.cur",
        r"%SystemRoot%\..\x.cur",
        r"C:\ProgramData\ITC\Bench\cursores\verde\aero_arrow.cur",
        r"C:\ProgramData\ITC\Bench\cursores\limao\..\..\x.cur",
    ],
)
def test_trecho_recusa_cursor_fora_das_pastas(dado: str) -> None:
    """Recusa antes de abrir o registro: hive fictício, nenhuma escrita."""
    ops = [{"p": "ponteiro", "chave": r"Control Panel\Cursors", "nome": "Arrow",
            "tipo": "expand_sz", "dado": dado, "acao": "gravar"}]  # fmt: skip
    r = executor.powershell(
        hive.script("escrever"),
        timeout=60,
        perfil="aparencia",
        hive="S-1-5-21-1-2-3-4321",
        operacoes=json.dumps(ops),
        protegidos="",
    )
    assert r.saida.strip() == "ERRO|valor"
