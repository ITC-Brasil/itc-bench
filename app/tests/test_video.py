"""Monitores (ADR-041): regras em servicos/video.py com driver falso; nada muda a tela real."""

import ctypes
from dataclasses import dataclass, field

import pytest

from itc_bench.nucleo import video as nucleo
from itc_bench.servicos import video

M = nucleo.Modo


def _bruto(
    dispositivo: str,
    *,
    interno: bool,
    principal: bool,
    atual: nucleo.Modo,
    modos: tuple[nucleo.Modo, ...],
    escala: nucleo.Escala | None,
    nome: str = "",
    orientacao: int = 0,
    posicao: tuple[int, int] = (0, 0),
) -> nucleo.MonitorBruto:
    return nucleo.MonitorBruto(
        dispositivo=dispositivo,
        nome=nome,
        interno=interno,
        principal=principal,
        atual=atual,
        orientacao=orientacao,
        modos=modos,
        escala=escala,
        adaptador=(1, 0),
        origem=0 if principal else 1,
        posicao=posicao,
    )


NOTEBOOK = _bruto(
    r"\\.\DISPLAY1",
    interno=True,
    principal=True,
    atual=M(1920, 1080, 60),
    modos=(M(1280, 720, 60), M(1366, 768, 60), M(1920, 1080, 60), M(1920, 1080, 144)),
    escala=nucleo.Escala(125, 125, (100, 125, 150, 175)),
)
EXTERNO = _bruto(
    r"\\.\DISPLAY2",
    interno=False,
    principal=False,
    nome="Monitor Exemplo 24",
    posicao=(1920, 0),
    atual=M(1920, 1080, 75),
    modos=(M(1280, 1024, 60), M(1920, 1080, 60), M(1920, 1080, 75)),
    escala=nucleo.Escala(100, 100, (100, 125, 150)),
)


@dataclass
class Falso:
    monitores_: list[nucleo.MonitorBruto]
    codigo_modo: int = 0
    codigo_escala: int = 0
    modos: list[tuple[str, nucleo.Modo, int]] = field(default_factory=list)
    escalas: list[tuple[str, int]] = field(default_factory=list)

    def monitores(self) -> list[nucleo.MonitorBruto]:
        return list(self.monitores_)

    def mudar_modo(self, dispositivo: str, modo: nucleo.Modo, orientacao: int) -> int:
        self.modos.append((dispositivo, modo, orientacao))
        return self.codigo_modo

    def mudar_escala(self, adaptador: tuple[int, int], origem: int, percentual: int) -> int:
        self.escalas.append((f"origem{origem}", percentual))
        return self.codigo_escala


def test_estruturas_com_tamanho_do_windows():
    assert ctypes.sizeof(nucleo._DevMode) == 220
    assert ctypes.sizeof(nucleo._ModoInfo) == 64
    assert ctypes.sizeof(nucleo._Caminho) == 72
    assert ctypes.sizeof(nucleo._NomeAlvo) == 420
    assert ctypes.sizeof(nucleo._LerEscala) == 32


def test_ler_dois_monitores_com_nomes_de_tela():
    ms = video.ler(Falso([NOTEBOOK, EXTERNO]))
    assert [m.nome for m in ms] == [
        "1. Tela do notebook (principal)",
        "2. Monitor Exemplo 24",
    ]
    assert ms[0].resolucoes()[0] == (1920, 1080)
    assert ms[0].recomendada() == (1920, 1080)
    assert ms[0].frequencias(1920, 1080) == [144, 60]
    assert ms[1].frequencias(1280, 1024) == [60]


def test_externo_sem_nome_e_varios_externos():
    sem_nome = _bruto(
        r"\\.\DISPLAY3",
        interno=False,
        principal=False,
        atual=M(1280, 1024, 60),
        modos=(M(1280, 1024, 60),),
        escala=None,
    )
    ms = video.ler(Falso([EXTERNO, sem_nome]))
    assert [m.nome for m in ms] == ["1. Monitor Exemplo 24", "2. Monitor externo"]


@pytest.mark.parametrize(
    ("escolha", "motivo"),
    [
        (video.Escolha(r"\\.\DISPLAY9"), "não está mais conectado"),
        (video.Escolha(r"\\.\DISPLAY1", resolucao=(3840, 2160)), "resolução não listada"),
        (
            video.Escolha(r"\\.\DISPLAY1", resolucao=(1366, 768), frequencia=144),
            "frequência não listada para essa",
        ),
        (video.Escolha(r"\\.\DISPLAY2", frequencia=144), "resolução atual"),
        (video.Escolha(r"\\.\DISPLAY1", orientacao=7), "orientação desconhecida"),
        (video.Escolha(r"\\.\DISPLAY1", escala=500), "escala não aceita"),
    ],
)
def test_recusa_valor_fora_da_lista_do_windows(escolha, motivo):
    falso = Falso([NOTEBOOK, EXTERNO])
    assert motivo in video.validar(video.ler(falso), escolha)
    feitos, _ = video.aplicar([escolha], falso)
    assert feitos and not feitos[0].ok
    assert falso.modos == [] and falso.escalas == []


def test_escala_sem_leitura_recusa():
    sem = _bruto(
        r"\\.\DISPLAY2",
        interno=False,
        principal=False,
        atual=M(1920, 1080, 60),
        modos=(M(1920, 1080, 60),),
        escala=None,
    )
    assert "não informou a escala" in video.validar(
        video.ler(Falso([sem])), video.Escolha(r"\\.\DISPLAY2", escala=100)
    )


def test_aplicar_nos_dois_monitores():
    falso = Falso([NOTEBOOK, EXTERNO])
    feitos, antes = video.aplicar(
        [
            video.Escolha(r"\\.\DISPLAY1", resolucao=(1366, 768), frequencia=60, escala=100),
            video.Escolha(r"\\.\DISPLAY2", orientacao=1),
        ],
        falso,
    )
    assert all(f.ok for f in feitos)
    assert falso.modos == [
        (r"\\.\DISPLAY1", M(1366, 768, 60), 0),
        (r"\\.\DISPLAY2", M(1920, 1080, 75), 1),
    ]
    assert falso.escalas == [("origem0", 100)]
    assert [m.dispositivo for m in antes.monitores] == [r"\\.\DISPLAY1", r"\\.\DISPLAY2"]


def test_sem_mudanca_nao_chama_o_windows():
    falso = Falso([NOTEBOOK, EXTERNO])
    feitos, _ = video.aplicar(
        [
            video.Escolha(
                r"\\.\DISPLAY1", resolucao=(1920, 1080), frequencia=60, orientacao=0, escala=125
            )
        ],
        falso,
    )
    assert feitos == [] and falso.modos == [] and falso.escalas == []


def test_resolucao_nova_mantem_frequencia_se_existir_senao_a_maior():
    falso = Falso([NOTEBOOK])
    video.aplicar([video.Escolha(r"\\.\DISPLAY1", resolucao=(1280, 720))], falso)
    assert falso.modos[-1][1] == M(1280, 720, 60)
    falso2 = Falso([EXTERNO])
    video.aplicar([video.Escolha(r"\\.\DISPLAY2", resolucao=(1280, 1024))], falso2)
    assert falso2.modos[-1][1] == M(1280, 1024, 60)


def test_falha_num_monitor_nao_para_o_outro():
    falso = Falso([NOTEBOOK, EXTERNO], codigo_modo=-2)
    feitos, _ = video.aplicar(
        [
            video.Escolha(r"\\.\DISPLAY1", resolucao=(1366, 768)),
            video.Escolha(r"\\.\DISPLAY2", escala=125),
        ],
        falso,
    )
    assert [f.ok for f in feitos] == [False, True]
    assert "não aceito pelo monitor" in feitos[0].mensagem


def test_desfazer_volta_tudo_como_estava():
    antes = video.Antes(video.ler(Falso([NOTEBOOK, EXTERNO])))
    girado = _bruto(
        r"\\.\DISPLAY2",
        interno=False,
        principal=False,
        nome="Monitor Exemplo 24",
        atual=M(1080, 1920, 60),
        orientacao=1,
        modos=EXTERNO.modos,
        escala=nucleo.Escala(150, 100, (100, 125, 150)),
    )
    menor = _bruto(
        r"\\.\DISPLAY1",
        interno=True,
        principal=True,
        atual=M(1366, 768, 60),
        modos=NOTEBOOK.modos,
        escala=nucleo.Escala(100, 125, (100, 125, 150, 175)),
    )
    falso = Falso([menor, girado])
    feitos = video.desfazer(antes, falso)
    assert all(f.ok for f in feitos)
    assert falso.modos == [
        (r"\\.\DISPLAY1", M(1920, 1080, 60), 0),
        (r"\\.\DISPLAY2", M(1920, 1080, 75), 0),
    ]
    assert falso.escalas == [("origem0", 125), ("origem1", 100)]


def test_mudancas_so_lista_o_que_muda():
    ms = video.ler(Falso([NOTEBOOK, EXTERNO]))
    linhas = video.mudancas(
        ms,
        [
            video.Escolha(r"\\.\DISPLAY1", resolucao=(1920, 1080), frequencia=144, escala=125),
            video.Escolha(r"\\.\DISPLAY2", orientacao=1),
        ],
    )
    assert linhas == [
        "1. Tela do notebook (principal): frequência 60 Hz → 144 Hz",
        "2. Monitor Exemplo 24: orientação Paisagem → Retrato",
    ]


def test_log_sem_nome_do_monitor(caplog):
    falso = Falso([NOTEBOOK, EXTERNO])
    with caplog.at_level("INFO"):
        video.aplicar([video.Escolha(r"\\.\DISPLAY2", escala=125)], falso)
    assert "Exemplo" not in caplog.text


def test_leitura_real_so_le():
    """Na máquina de teste: lê sem mudar nada; ao menos um monitor ativo."""
    ms = video.ler()
    assert ms, "nenhum monitor ativo"
    for m in ms:
        assert m.bruto.atual.largura > 0 and m.resolucoes()
        if m.bruto.escala is not None:
            assert m.bruto.escala.atual in m.bruto.escala.opcoes
