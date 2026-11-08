"""Gera `itc-bench.ico` a partir do símbolo (ADR-001), com PNG por tamanho.

Rodar de `app/` quando o símbolo mudar: `uv run python empacotamento/gerar_ico.py`.
O `.ico` fica no repositório; o build não renderiza SVG.
"""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

SIMBOLO = Path("src/itc_bench/recursos/simbolo")
TAMANHOS = (16, 20, 24, 32, 40, 48, 64, 256)
DESTINO = Path(__file__).with_name("itc-bench.ico")


def png(svg: Path, lado: int) -> bytes:
    imagem = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagem.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagem)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(svg)).render(pintor)
    pintor.end()
    dados = QByteArray()
    buffer = QBuffer(dados)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagem.save(buffer, "PNG")
    return bytes(dados.data())


def main() -> None:
    _app = QGuiApplication([])
    imagens = [
        png(SIMBOLO / ("itc-bench-simbolo-16.svg" if lado <= 24 else "itc-bench-simbolo.svg"), lado)
        for lado in TAMANHOS
    ]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    deslocamento = 6 + 16 * len(imagens)
    entradas = b""
    for lado, dados in zip(TAMANHOS, imagens, strict=True):
        byte = lado % 256  # 256 vira 0 no formato
        entradas += struct.pack("<BBBBHHII", byte, byte, 0, 0, 1, 32, len(dados), deslocamento)
        deslocamento += len(dados)
    DESTINO.write_bytes(cabecalho + entradas + b"".join(imagens))
    print(f"{DESTINO.name}: {len(imagens)} tamanhos")


if __name__ == "__main__":
    main()
