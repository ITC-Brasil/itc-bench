"""Indicadores pequenos e reutilizáveis (ADR-073): anel de progresso, barra e bateria, pintados
com QPainter nas cores da `Paleta` em uso, e o desenho de traço vindo de um SVG."""

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QWidget

from itc_bench.ui import tema


def _cor(tipo: str) -> str:
    """ "ok", "atencao", "critico", "destaque" ou "texto" → cor da paleta em uso."""
    p = tema.atual()
    return {
        "ok": p.ok,
        "atencao": p.warn,
        "critico": p.err,
        "destaque": p.destaque,
        "texto": p.texto,
    }.get(tipo, p.destaque)


def numeros(fonte: QFont) -> QFont:
    """Algarismos de largura fixa (tabular-nums), quando a fonte e o Qt permitem."""
    # Qt sem recursos OpenType (antes do 6.7): os números ficam proporcionais, sem outro efeito.
    if hasattr(QFont, "Tag") and hasattr(fonte, "setFeature"):
        fonte.setFeature(QFont.Tag("tnum"), 1)
    return fonte


class Anel(QWidget):
    """Anel de progresso com o texto no meio (fração de 0 a 1)."""

    def __init__(self, tamanho: int = 72, espessura: int = 10, fonte_px: int = 14) -> None:
        super().__init__()
        self.setFixedSize(tamanho, tamanho)
        self.espessura = espessura
        self.fonte_px = fonte_px
        self.fracao = 0.0
        self.tipo = "destaque"
        self.texto = ""

    def definir(self, fracao: float | None, texto: str, tipo: str = "destaque") -> None:
        self.fracao = 0.0 if fracao is None else min(1.0, max(0.0, fracao))
        self.texto = texto
        self.tipo = tipo
        self.setAccessibleName(texto)
        self.update()

    def paintEvent(self, _evento: QPaintEvent) -> None:
        p = tema.atual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        meio = self.espessura / 2
        caixa = QRectF(meio, meio, self.width() - self.espessura, self.height() - self.espessura)
        caneta = QPen(QColor(p.anel), self.espessura)
        caneta.setCapStyle(Qt.PenCapStyle.FlatCap)
        pintor.setPen(caneta)
        pintor.drawEllipse(caixa)
        if self.fracao > 0:
            caneta.setColor(QColor(_cor(self.tipo)))
            pintor.setPen(caneta)
            # Começa no topo (90°) e anda no sentido horário; o Qt mede em 1/16 de grau.
            pintor.drawArc(caixa, 90 * 16, -round(self.fracao * 360 * 16))
        fonte = numeros(QFont(tema.DISPLAY))
        fonte.setPixelSize(self.fonte_px)
        fonte.setWeight(QFont.Weight.ExtraBold)
        pintor.setFont(fonte)
        pintor.setPen(QColor(p.texto))
        pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.texto)
        pintor.end()


class Barra(QWidget):
    """Barra horizontal de 10 px com a fração preenchida."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fracao = 0.0
        self.tipo = "destaque"

    def definir(self, fracao: float | None, tipo: str = "destaque") -> None:
        self.fracao = 0.0 if fracao is None else min(1.0, max(0.0, fracao))
        self.tipo = tipo
        self.update()

    def paintEvent(self, _evento: QPaintEvent) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        raio = self.height() / 2
        pintor.setBrush(QColor(tema.atual().anel))
        pintor.drawRoundedRect(QRectF(self.rect()), raio, raio)
        if self.fracao > 0:
            pintor.setBrush(QColor(_cor(self.tipo)))
            largura = max(self.height(), self.width() * self.fracao)
            pintor.drawRoundedRect(QRectF(0, 0, largura, self.height()), raio, raio)
        pintor.end()


class Bateria(QWidget):
    """Bateria desenhada com o nível preenchido (0 a 100) ou vazia sem leitura."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(84, 44)
        self.carga: int | None = None
        self.tipo = "ok"

    def definir(self, carga: int | None, tipo: str = "ok") -> None:
        self.carga = carga
        self.tipo = tipo
        self.setAccessibleName("Sem bateria" if carga is None else f"Bateria {carga}%")
        self.update()

    def paintEvent(self, _evento: QPaintEvent) -> None:
        p = tema.atual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(QColor(p.texto), 3))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRoundedRect(QRectF(2, 4, 72, 36), 6, 6)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(p.texto))
        pintor.drawRoundedRect(QRectF(76, 15, 6, 14), 2, 2)
        if self.carga:
            pintor.setBrush(QColor(_cor(self.tipo)))
            pintor.drawRoundedRect(QRectF(8, 10, 60 * min(100, self.carga) / 100, 24), 3, 3)
        pintor.end()


class Desenho(QWidget):
    """SVG de traço (`currentColor`) pintado na cor de destaque da paleta, no tamanho dado."""

    def __init__(self, caminho: str, largura: int, altura: int) -> None:
        super().__init__()
        self.caminho = caminho
        self.setFixedSize(QSize(largura, altura))

    def paintEvent(self, _evento: QPaintEvent) -> None:
        dados = tema.svg(self.caminho, tema.atual().destaque)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(dados)).render(pintor, QRectF(self.rect()))
        pintor.end()
