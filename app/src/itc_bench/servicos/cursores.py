"""Ponteiro colorido (ADR-046), sem Qt: cursores do Windows recoloridos numa lista fechada.

Lê os `aero_*.cur` da pasta de cursores do Windows (bitmaps de 32 bits com transparência),
troca o branco pela cor escolhida mantendo o contorno preto, a sombra e a transparência, e
grava em `%ProgramData%\\ITC\\Bench\\cursores\\<cor>\\`, com a mesma ACL da pasta do papel de
parede (Usuários leem; só Administradores e SYSTEM gravam). Os animados (ocupado e
trabalhando) continuam os do Windows.
"""

import struct
from pathlib import Path, PureWindowsPath

from itc_bench.nucleo import acl, caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

# id → (rótulo, (R, G, B)). Verde-limão é a cor sugerida pelo próprio Windows 11.
CORES: dict[str, tuple[str, tuple[int, int, int]]] = {
    "limao": ("Verde-limão", (0xBF, 0xFF, 0x00)),
    "amarelo": ("Amarelo", (0xFF, 0xE6, 0x00)),
    "ciano": ("Ciano", (0x00, 0xE5, 0xFF)),
    "rosa": ("Rosa", (0xFF, 0x4F, 0xB8)),
    "laranja": ("Laranja", (0xFF, 0x8C, 0x00)),
    "roxo": ("Roxo", (0xA0, 0x60, 0xFF)),
}
# Função do ponteiro (valor em Control Panel\Cursors) → cursor do Windows que vira colorido.
FUNCOES: dict[str, str] = {
    "Arrow": "aero_arrow.cur",
    "Hand": "aero_link.cur",
    "Help": "aero_helpsel.cur",
    "No": "aero_unavail.cur",
    "NWPen": "aero_pen.cur",
    "SizeAll": "aero_move.cur",
    "SizeNESW": "aero_nesw.cur",
    "SizeNS": "aero_ns.cur",
    "SizeNWSE": "aero_nwse.cur",
    "SizeWE": "aero_ew.cur",
    "UpArrow": "aero_up.cur",
}
TETO_ARQUIVO = 2 << 20  # um aero_*.cur tem ~150 KB


class ErroCursor(Exception):
    """Cursor do Windows ausente ou em formato que o Bench não recolore."""


def pasta_windows() -> Path:
    """`<Windows>\\Cursors`, pela API (o `SystemRoot` do ambiente não conta)."""
    return Path(PureWindowsPath(executor.sistema32("x")).parent.parent / "Cursors")


def pasta(cor: str, base: Path | None = None) -> Path:
    if cor not in CORES:
        raise ValueError(f"Cor de ponteiro fora da lista: {cor!r}")
    return (base or caminhos.dados() / "cursores") / cor


def arquivo(cor: str, funcao: str, base: Path | None = None) -> Path:
    """Caminho do cursor colorido; é o único produtor do valor gravado no registro."""
    return pasta(cor, base) / FUNCOES[funcao]


def recolorir(dados: bytes, rgb: tuple[int, int, int]) -> bytes:
    """Troca o branco pela cor em cada imagem do `.cur`; preto, sombra e transparência ficam.

    Cada pixel vira `cor x luminosidade` (branco → cor, preto → preto, cinza → cor escura). Só
    aceita `.cur` (tipo 2) com imagens BMP de 32 bits; qualquer outra coisa é recusada.
    """
    if len(dados) < 6 or len(dados) > TETO_ARQUIVO:
        raise ErroCursor("tamanho")
    reservado, tipo, n = struct.unpack_from("<HHH", dados, 0)
    if reservado != 0 or tipo != 2 or not 1 <= n <= 16 or len(dados) < 6 + 16 * n:
        raise ErroCursor("cabeçalho")
    saida = bytearray(dados)
    r, g, b = rgb
    for i in range(n):
        _, _, _, _, _, _, tamanho, inicio = struct.unpack_from("<BBBBHHII", dados, 6 + 16 * i)
        if inicio + 40 > len(dados) or inicio + tamanho > len(dados):
            raise ErroCursor("entrada")
        cab, largura, altura2, _, bits = struct.unpack_from("<IiiHH", dados, inicio)
        if cab != 40 or bits != 32 or largura <= 0 or altura2 <= 0:
            raise ErroCursor("formato")
        altura = altura2 // 2  # BMP de cursor: imagem + máscara
        pixels = inicio + 40
        fim = pixels + largura * altura * 4
        if fim > inicio + tamanho:
            raise ErroCursor("entrada")
        for p in range(pixels, fim, 4):
            azul, verde, vermelho = saida[p], saida[p + 1], saida[p + 2]
            luz = max(azul, verde, vermelho)
            saida[p] = b * luz // 255
            saida[p + 1] = g * luz // 255
            saida[p + 2] = r * luz // 255
    return bytes(saida)


def preparar(cor: str, *, base: Path | None = None, origem: Path | None = None) -> Path:
    """Gera (ou regera) os cursores da cor na pasta protegida; devolve a pasta da cor."""
    destino = pasta(cor, base)
    raiz = destino.parent
    raiz.mkdir(parents=True, exist_ok=True)
    if base is None:
        acl.proteger(raiz, acl.SDDL)
        atual = acl.sddl_atual(raiz)
        if atual != acl.SDDL:
            raise acl.ErroAcl(0, f"Pasta dos cursores com ACL inesperado: {atual}")
    acl.verificar_reparse(raiz)
    destino.mkdir(exist_ok=True)
    acl.verificar_reparse(destino)
    fonte = origem or pasta_windows()
    rgb = CORES[cor][1]
    for nome in FUNCOES.values():
        try:
            dados = (fonte / nome).read_bytes()
        except OSError as erro:
            raise ErroCursor(f"cursor do Windows ausente ({type(erro).__name__})") from None
        novo = recolorir(dados, rgb)
        alvo = destino / nome
        temporario = alvo.with_suffix(".parcial")
        temporario.write_bytes(novo)
        temporario.replace(alvo)
    log.info("Ponteiro colorido: cor %s pronta (%d cursores)", cor, len(FUNCOES))
    return destino
