"""Monitores pelo `user32` por ctypes (ADR-041), sem processo, arquivo nem registro.

Lê os monitores ativos (`QueryDisplayConfig`), o nome de cada um, os modos que o driver aceita
(`EnumDisplaySettingsExW`) e a escala. Aplica resolução, frequência e orientação por
`ChangeDisplaySettingsExW` (testado antes com `CDS_TEST`) e a escala por
`DisplayConfigSetDeviceInfo`.

A escala usa os tipos `-3`/`-4` de `DisplayConfigGetDeviceInfo`/`SetDeviceInfo`, que a Microsoft
não documenta (risco aceito no ADR-041): o valor é relativo à escala recomendada do monitor, e o
Windows grava por usuário (vale para a conta que roda o Bench). Nada aqui grava log; erro sai só
com o código.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

QDC_ONLY_ACTIVE_PATHS = 0x2
ERRO_BUFFER = 122  # ERROR_INSUFFICIENT_BUFFER
TIPO_NOME_ORIGEM = 1
TIPO_NOME_ALVO = 2
TIPO_LER_ESCALA = -3  # não documentado
TIPO_GRAVAR_ESCALA = -4  # não documentado
SAIDA_INTERNA = 0x80000000  # DISPLAYCONFIG_OUTPUT_TECHNOLOGY_INTERNAL
SAIDAS_EMBUTIDAS = {11, 13, 0x80000000}  # DisplayPort/UDI embutidos e interna

MODO_ATUAL = 0xFFFFFFFF  # ENUM_CURRENT_SETTINGS
CDS_UPDATEREGISTRY = 0x1
CDS_TEST = 0x2
DM_ORIENTACAO = 0x80
DM_BITS = 0x40000
DM_LARGURA = 0x80000
DM_ALTURA = 0x100000
DM_FREQUENCIA = 0x400000

# Escalas do Windows, em %; o relativo 0 é a recomendada do monitor.
ESCALAS = (100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500)

RESULTADOS = {
    0: "aplicado",
    1: "aplicado, vale depois de reiniciar",
    -1: "o driver recusou",
    -2: "modo não aceito pelo monitor",
    -3: "não foi possível gravar",
    -4: "parâmetro recusado",
    -5: "parâmetro recusado",
    -6: "não aceito com a área de trabalho duplicada",
}


class _Luid(ctypes.Structure):
    _fields_ = (("baixo", wintypes.DWORD), ("alto", wintypes.LONG))


class _Racional(ctypes.Structure):
    _fields_ = (("num", ctypes.c_uint32), ("den", ctypes.c_uint32))


class _Origem(ctypes.Structure):
    _fields_ = (
        ("adaptador", _Luid),
        ("id", ctypes.c_uint32),
        ("modo", ctypes.c_uint32),
        ("estado", ctypes.c_uint32),
    )


class _Alvo(ctypes.Structure):
    _fields_ = (
        ("adaptador", _Luid),
        ("id", ctypes.c_uint32),
        ("modo", ctypes.c_uint32),
        ("saida", ctypes.c_uint32),
        ("rotacao", ctypes.c_uint32),
        ("escalonamento", ctypes.c_uint32),
        ("frequencia", _Racional),
        ("varredura", ctypes.c_uint32),
        ("disponivel", wintypes.BOOL),
        ("estado", ctypes.c_uint32),
    )


class _Caminho(ctypes.Structure):
    _fields_ = (("origem", _Origem), ("alvo", _Alvo), ("flags", ctypes.c_uint32))


class _ModoInfo(ctypes.Structure):
    _fields_ = (
        ("tipo", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("adaptador", _Luid),
        ("dados", ctypes.c_uint64 * 6),  # união de 48 bytes, alinhada a 8
    )


class _Cabecalho(ctypes.Structure):
    _fields_ = (
        ("tipo", ctypes.c_int32),
        ("tamanho", ctypes.c_uint32),
        ("adaptador", _Luid),
        ("id", ctypes.c_uint32),
    )


class _NomeOrigem(ctypes.Structure):
    _fields_ = (("cab", _Cabecalho), ("gdi", ctypes.c_wchar * 32))


class _NomeAlvo(ctypes.Structure):
    _fields_ = (
        ("cab", _Cabecalho),
        ("flags", ctypes.c_uint32),
        ("saida", ctypes.c_uint32),
        ("fabricante", ctypes.c_uint16),
        ("produto", ctypes.c_uint16),
        ("conector", ctypes.c_uint32),
        ("nome", ctypes.c_wchar * 64),
        ("caminho", ctypes.c_wchar * 128),
    )


class _LerEscala(ctypes.Structure):
    _fields_ = (
        ("cab", _Cabecalho),
        ("minimo", ctypes.c_int32),
        ("atual", ctypes.c_int32),
        ("maximo", ctypes.c_int32),
    )


class _GravarEscala(ctypes.Structure):
    _fields_ = (("cab", _Cabecalho), ("relativo", ctypes.c_int32))


class _DevMode(ctypes.Structure):
    _fields_ = (
        ("nome", ctypes.c_wchar * 32),
        ("versao_spec", wintypes.WORD),
        ("versao_driver", wintypes.WORD),
        ("tamanho", wintypes.WORD),
        ("extra", wintypes.WORD),
        ("campos", wintypes.DWORD),
        ("posicao_x", wintypes.LONG),
        ("posicao_y", wintypes.LONG),
        ("orientacao", wintypes.DWORD),
        ("saida_fixa", wintypes.DWORD),
        ("cor", ctypes.c_short),
        ("duplex", ctypes.c_short),
        ("resolucao_y", ctypes.c_short),
        ("tt", ctypes.c_short),
        ("agrupar", ctypes.c_short),
        ("formulario", ctypes.c_wchar * 32),
        ("pixels_log", wintypes.WORD),
        ("bits", wintypes.DWORD),
        ("largura", wintypes.DWORD),
        ("altura", wintypes.DWORD),
        ("flags_tela", wintypes.DWORD),
        ("frequencia", wintypes.DWORD),
        ("icm_metodo", wintypes.DWORD),
        ("icm_intencao", wintypes.DWORD),
        ("midia", wintypes.DWORD),
        ("pontilhado", wintypes.DWORD),
        ("reservado1", wintypes.DWORD),
        ("reservado2", wintypes.DWORD),
        ("panorama_largura", wintypes.DWORD),
        ("panorama_altura", wintypes.DWORD),
    )


TAMANHOS = {_DevMode: 220, _ModoInfo: 64, _Caminho: 72}  # os do SDK do Windows
if any(ctypes.sizeof(t) != n for t, n in TAMANHOS.items()):
    raise ImportError("estruturas de vídeo fora do tamanho do Windows")


class ErroVideo(OSError):
    """Falha do `user32`; `codigo` é o erro Win32 ou o `DISP_CHANGE_*`."""

    def __init__(self, funcao: str, codigo: int) -> None:
        super().__init__(codigo, f"{funcao}: {codigo}")
        self.codigo = codigo


@dataclass(frozen=True)
class Modo:
    largura: int
    altura: int
    frequencia: int
    bits: int = 32


@dataclass(frozen=True)
class Escala:
    atual: int  # %
    recomendada: int  # %
    opcoes: tuple[int, ...]  # % aceitos por este monitor


@dataclass(frozen=True)
class MonitorBruto:
    dispositivo: str  # \\.\DISPLAYn, o nome do GDI
    nome: str  # nome amigável do EDID; vazio se o monitor não informar
    interno: bool
    principal: bool
    atual: Modo
    orientacao: int  # 0, 1, 2, 3 = 0°, 90°, 180°, 270°
    modos: tuple[Modo, ...]
    escala: Escala | None
    adaptador: tuple[int, int]
    origem: int
    posicao: tuple[int, int] = (0, 0)  # canto superior esquerdo na área de trabalho


def _user32() -> ctypes.WinDLL:
    return ctypes.WinDLL("user32", use_last_error=True)


def _caminhos(u: ctypes.WinDLL) -> list[_Caminho]:
    for _ in range(5):
        n_cam, n_modo = ctypes.c_uint32(), ctypes.c_uint32()
        r = u.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_cam), ctypes.byref(n_modo)
        )
        if r:
            raise ErroVideo("GetDisplayConfigBufferSizes", r)
        caminhos = (_Caminho * max(n_cam.value, 1))()
        modos = (_ModoInfo * max(n_modo.value, 1))()
        r = u.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(n_cam),
            caminhos,
            ctypes.byref(n_modo),
            modos,
            None,
        )
        if r == ERRO_BUFFER:
            continue  # um monitor entrou ou saiu entre as duas chamadas
        if r:
            raise ErroVideo("QueryDisplayConfig", r)
        return list(caminhos[: n_cam.value])
    raise ErroVideo("QueryDisplayConfig", ERRO_BUFFER)


def _cabecalho(tipo: int, tamanho: int, adaptador: _Luid, id_: int) -> _Cabecalho:
    return _Cabecalho(tipo, tamanho, _Luid(adaptador.baixo, adaptador.alto), id_)


def _nome_gdi(u: ctypes.WinDLL, c: _Caminho) -> str:
    pedido = _NomeOrigem()
    pedido.cab = _cabecalho(
        TIPO_NOME_ORIGEM, ctypes.sizeof(_NomeOrigem), c.origem.adaptador, c.origem.id
    )
    r = u.DisplayConfigGetDeviceInfo(ctypes.byref(pedido))
    if r:
        raise ErroVideo("DisplayConfigGetDeviceInfo", r)
    return str(pedido.gdi)


def _nome_alvo(u: ctypes.WinDLL, c: _Caminho) -> str:
    pedido = _NomeAlvo()
    pedido.cab = _cabecalho(TIPO_NOME_ALVO, ctypes.sizeof(_NomeAlvo), c.alvo.adaptador, c.alvo.id)
    if u.DisplayConfigGetDeviceInfo(ctypes.byref(pedido)):
        return ""
    return str(pedido.nome).strip()


def _escala(u: ctypes.WinDLL, c: _Caminho) -> Escala | None:
    pedido = _LerEscala()
    pedido.cab = _cabecalho(
        TIPO_LER_ESCALA, ctypes.sizeof(_LerEscala), c.origem.adaptador, c.origem.id
    )
    if u.DisplayConfigGetDeviceInfo(ctypes.byref(pedido)):
        return None
    base = abs(pedido.minimo)
    indices = range(base + pedido.minimo, base + pedido.maximo + 1)
    if not (0 <= base < len(ESCALAS)) or not all(0 <= i < len(ESCALAS) for i in indices):
        return None
    atual = base + pedido.atual
    if not 0 <= atual < len(ESCALAS):
        return None
    return Escala(ESCALAS[atual], ESCALAS[base], tuple(ESCALAS[i] for i in indices))


def _devmode() -> _DevMode:
    d = _DevMode()
    d.tamanho = ctypes.sizeof(_DevMode)
    return d


def _modo_atual(u: ctypes.WinDLL, dispositivo: str) -> _DevMode:
    d = _devmode()
    if not u.EnumDisplaySettingsExW(dispositivo, MODO_ATUAL, ctypes.byref(d), 0):
        raise ErroVideo("EnumDisplaySettingsExW", ctypes.get_last_error())
    return d


def _modos(u: ctypes.WinDLL, dispositivo: str) -> tuple[Modo, ...]:
    vistos: set[Modo] = set()
    i = 0
    while i < 4096:
        d = _devmode()
        if not u.EnumDisplaySettingsExW(dispositivo, i, ctypes.byref(d), 0):
            break
        if d.bits >= 32 and d.frequencia > 1:  # 0 e 1 = "padrão do hardware"
            # Sempre em paisagem: girado, o driver pode listar largura e altura trocadas.
            lado_maior, lado_menor = max(d.largura, d.altura), min(d.largura, d.altura)
            vistos.add(Modo(lado_maior, lado_menor, d.frequencia, d.bits))
        i += 1
    return tuple(sorted(vistos, key=lambda m: (m.largura * m.altura, m.largura, m.frequencia)))


def monitores() -> list[MonitorBruto]:
    """Monitores ativos, na ordem do Windows. Clonados (duplicar) aparecem uma vez."""
    u = _user32()
    saida: list[MonitorBruto] = []
    vistos: set[str] = set()
    for c in _caminhos(u):
        gdi = _nome_gdi(u, c)
        if gdi in vistos:
            continue
        vistos.add(gdi)
        d = _modo_atual(u, gdi)
        saida.append(
            MonitorBruto(
                dispositivo=gdi,
                nome=_nome_alvo(u, c),
                interno=c.alvo.saida in SAIDAS_EMBUTIDAS,
                principal=d.posicao_x == 0 and d.posicao_y == 0,
                atual=Modo(d.largura, d.altura, d.frequencia, d.bits),
                orientacao=int(d.orientacao),
                modos=_modos(u, gdi),
                escala=_escala(u, c),
                adaptador=(int(c.origem.adaptador.baixo), int(c.origem.adaptador.alto)),
                origem=int(c.origem.id),
                posicao=(int(d.posicao_x), int(d.posicao_y)),
            )
        )
    return saida


def mudar_modo(dispositivo: str, modo: Modo, orientacao: int) -> int:
    """Testa e aplica resolução, frequência e orientação; devolve o `DISP_CHANGE_*`.

    Em 90° e 270° o Windows espera largura e altura trocadas: quem chama passa o modo como o
    driver o lista (paisagem) e a troca é feita aqui.
    """
    u = _user32()
    d = _modo_atual(u, dispositivo)
    largura, altura = modo.largura, modo.altura
    if orientacao in (1, 3):
        largura, altura = min(largura, altura), max(largura, altura)
    else:
        largura, altura = max(largura, altura), min(largura, altura)
    d.largura, d.altura, d.frequencia, d.bits = largura, altura, modo.frequencia, modo.bits
    d.orientacao = orientacao
    d.campos = DM_LARGURA | DM_ALTURA | DM_FREQUENCIA | DM_BITS | DM_ORIENTACAO
    teste = int(u.ChangeDisplaySettingsExW(dispositivo, ctypes.byref(d), None, CDS_TEST, None))
    if teste != 0:
        return teste
    return int(
        u.ChangeDisplaySettingsExW(dispositivo, ctypes.byref(d), None, CDS_UPDATEREGISTRY, None)
    )


def mudar_escala(adaptador: tuple[int, int], origem: int, percentual: int) -> int:
    """Grava a escala; devolve 0 ou o erro Win32. `percentual` tem de estar em `ESCALAS`."""
    u = _user32()
    luid = _Luid(adaptador[0], adaptador[1])
    leitura = _LerEscala()
    leitura.cab = _cabecalho(TIPO_LER_ESCALA, ctypes.sizeof(_LerEscala), luid, origem)
    r = int(u.DisplayConfigGetDeviceInfo(ctypes.byref(leitura)))
    if r:
        return r
    base = abs(leitura.minimo)
    alvo = ESCALAS.index(percentual)
    relativo = alvo - base
    if not leitura.minimo <= relativo <= leitura.maximo:
        return -5
    pedido = _GravarEscala()
    pedido.cab = _cabecalho(TIPO_GRAVAR_ESCALA, ctypes.sizeof(_GravarEscala), luid, origem)
    pedido.relativo = relativo
    return int(u.DisplayConfigSetDeviceInfo(ctypes.byref(pedido)))
