"""Seletor visual do ponteiro do mouse (ADR-045, ADR-046), como em Configurações › Acessibilidade.

Só tela: quadradinhos Branco, Preto, Invertido e Personalizado, desenhados aqui (sem imagem do
Windows), as cores do Personalizado e o tamanho. O valor continua o do catálogo de
`servicos/aparencia.py` (`<cor>_<tamanho>`); no Personalizado, `<cor>` é uma de
`servicos/cursores.CORES`.
"""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from itc_bench.servicos import aparencia as ap
from itc_bench.servicos import cursores
from itc_bench.ui import tema

PERSONALIZADO = "personalizado"
ESTILOS = (*ap.CORES, PERSONALIZADO)
NOMES = {**ap.CORES, PERSONALIZADO: "Personalizado"}

# Seta do ponteiro numa grade de 12 x 19, como o desenho padrão do Windows.
_SETA = (
    (0, 0), (0, 16), (4, 12), (7, 18.5), (9.5, 17.5), (6.5, 11.5), (12, 11.5),
)  # fmt: skip


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _caminho_seta(origem: QPointF, escala: float) -> QPainterPath:
    caminho = QPainterPath()
    for i, (x, y) in enumerate(_SETA):
        ponto = QPointF(origem.x() + x * escala, origem.y() + y * escala)
        if i == 0:
            caminho.moveTo(ponto)
        else:
            caminho.lineTo(ponto)
    caminho.closeSubpath()
    return caminho


class Quadro(QWidget):
    """Um quadradinho clicável com a seta no estilo da opção."""

    clicado = Signal(str)

    def __init__(self, estilo: str) -> None:
        super().__init__()
        self.estilo = estilo
        self.marcado = False
        self.cor_personalizada = next(iter(cursores.CORES))
        self.setFixedSize(QSize(120, 96))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Ponteiro {NOMES[estilo].lower()}")

    def marcar(self, sim: bool) -> None:
        self.marcado = sim
        self.update()

    def mousePressEvent(self, evento: QMouseEvent) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicado.emit(self.estilo)

    def paintEvent(self, _evento: QPaintEvent) -> None:
        p = tema.atual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        caixa = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        pintor.setPen(
            QPen(QColor(p.destaque if self.marcado else p.linha), 2.5 if self.marcado else 1)
        )
        pintor.setBrush(QColor(p.alternada))
        pintor.drawRoundedRect(caixa, 6, 6)
        escala = 1.6
        origem = QPointF(caixa.center().x() - 5 * escala, caixa.center().y() - 9 * escala)
        seta = _caminho_seta(origem, escala)
        if self.estilo == "invertido":
            # Meio branco, meio preto; a seta mostra a cor oposta em cada metade.
            fundo = QRectF(caixa.center().x() - 32, caixa.center().y() - 26, 64, 52)
            alto = QRectF(fundo.left(), fundo.top(), fundo.width(), fundo.height() / 2)
            baixo = QRectF(fundo.left(), alto.bottom(), fundo.width(), fundo.height() / 2)
            pintor.fillRect(alto, QColor("#FFFFFF"))
            pintor.fillRect(baixo, QColor("#000000"))
            for metade, cor in ((alto, "#000000"), (baixo, "#FFFFFF")):
                pintor.save()
                pintor.setClipRect(metade)
                pintor.setPen(QPen(QColor("#808080"), 1))
                pintor.setBrush(QColor(cor))
                pintor.drawPath(seta)
                pintor.restore()
            return
        if self.estilo == PERSONALIZADO:
            preenche = _hex(cursores.CORES[self.cor_personalizada][1])
            contorno = "#000000"
        elif self.estilo == "branco":
            preenche, contorno = "#FFFFFF", "#000000"
        else:
            preenche, contorno = "#000000", "#FFFFFF"
        pintor.setPen(QPen(QColor(contorno), 1.4))
        pintor.setBrush(QColor(preenche))
        pintor.drawPath(seta)


class SetaIcone(QWidget):
    """Seta branca de contorno preto nas pontas do controle de tamanho, como no Windows."""

    def __init__(self, escala: float) -> None:
        super().__init__()
        self.escala = escala
        self.setFixedSize(QSize(int(14 * escala) + 6, int(20 * escala) + 6))

    def paintEvent(self, _evento: QPaintEvent) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(QPen(QColor("#000000"), 1.2))
        pintor.setBrush(QColor("#FFFFFF"))
        pintor.drawPath(_caminho_seta(QPointF(3, 3), self.escala))


class Amostra(QWidget):
    """Bolinha de cor do Personalizado."""

    clicada = Signal(str)

    def __init__(self, cor: str) -> None:
        super().__init__()
        self.cor = cor
        self.marcada = False
        self.setFixedSize(QSize(30, 30))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(cursores.CORES[cor][0])

    def marcar(self, sim: bool) -> None:
        self.marcada = sim
        self.update()

    def mousePressEvent(self, evento: QMouseEvent) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicada.emit(self.cor)

    def paintEvent(self, _evento: QPaintEvent) -> None:
        p = tema.atual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.marcada:
            pintor.setPen(QPen(QColor(p.destaque), 2.5))
            pintor.setBrush(Qt.BrushStyle.NoBrush)
            pintor.drawEllipse(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))
        pintor.setPen(QPen(QColor(p.linha), 1))
        pintor.setBrush(QColor(_hex(cursores.CORES[self.cor][1])))
        pintor.drawEllipse(QRectF(self.rect()).adjusted(6, 6, -6, -6))


class SeletorPonteiro(QWidget):
    """Quadradinhos, cores do Personalizado e tamanho; `mudou` traz `<cor>_<tamanho>`."""

    mudou = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 8)
        titulo = QLabel("Estilo do ponteiro do mouse")
        titulo.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(titulo)
        linha = QHBoxLayout()
        self.quadros: dict[str, Quadro] = {}
        for estilo in ESTILOS:
            q = Quadro(estilo)
            q.clicado.connect(self._estilo)
            self.quadros[estilo] = q
            linha.addWidget(q)
        linha.addStretch()
        v.addLayout(linha)

        # Tamanho de 1 a 15, como o controle deslizante do Windows 11 (ADR-047).
        faixa = QHBoxLayout()
        faixa.setContentsMargins(0, 6, 0, 0)
        r_tamanho = QLabel("Tamanho")
        r_tamanho.setTextFormat(Qt.TextFormat.PlainText)
        faixa.addWidget(r_tamanho)
        faixa.addSpacing(12)
        faixa.addWidget(SetaIcone(0.8))
        self.tamanho = QSlider(Qt.Orientation.Horizontal)
        self.tamanho.setRange(ap.TAMANHOS[0], ap.TAMANHOS[-1])
        self.tamanho.setPageStep(1)
        self.tamanho.setMinimumWidth(220)
        self.tamanho.setAccessibleName("Tamanho do ponteiro")
        self.tamanho.valueChanged.connect(self._tamanho)
        faixa.addWidget(self.tamanho, 1)
        faixa.addWidget(SetaIcone(1.6))
        self.numero = QLabel("1")
        self.numero.setTextFormat(Qt.TextFormat.PlainText)
        self.numero.setMinimumWidth(24)
        faixa.addWidget(self.numero)
        faixa.addStretch(1)
        v.addLayout(faixa)

        # Cores do Personalizado: só aparecem com ele escolhido, como no Windows.
        self.faixa_cores = QWidget()
        cores = QHBoxLayout(self.faixa_cores)
        cores.setContentsMargins(0, 4, 0, 0)
        r_cores = QLabel("Cor do ponteiro:")
        r_cores.setTextFormat(Qt.TextFormat.PlainText)
        cores.addWidget(r_cores)
        self.amostras: dict[str, Amostra] = {}
        for cor in cursores.CORES:
            a = Amostra(cor)
            a.clicada.connect(self._cor_personalizada)
            self.amostras[cor] = a
            cores.addWidget(a)
        self.nome_cor = QLabel("")
        self.nome_cor.setTextFormat(Qt.TextFormat.PlainText)
        cores.addWidget(self.nome_cor)
        cores.addStretch()
        v.addWidget(self.faixa_cores)

        self.estilo = "branco"
        self.cor_personalizada = next(iter(cursores.CORES))
        self.definir(ap.POR_ID["ponteiro"].padrao)

    def valor(self) -> str:
        cor = self.cor_personalizada if self.estilo == PERSONALIZADO else self.estilo
        return f"{cor}_{self.tamanho.value()}"

    def _tamanho(self, n: int) -> None:
        self.numero.setText(str(n))
        self.mudou.emit(self.valor())

    def _mostrar(self) -> None:
        for e, q in self.quadros.items():
            q.marcar(e == self.estilo)
        self.quadros[PERSONALIZADO].cor_personalizada = self.cor_personalizada
        self.quadros[PERSONALIZADO].update()
        for c, a in self.amostras.items():
            a.marcar(c == self.cor_personalizada)
        self.nome_cor.setText(cursores.CORES[self.cor_personalizada][0])
        self.faixa_cores.setVisible(self.estilo == PERSONALIZADO)

    def definir(self, valor: str) -> None:
        """Mostra o valor sem avisar (`mudou` não dispara)."""
        cor, _, tam = valor.rpartition("_")
        n = int(tam) if tam.isdigit() else 0
        if n not in ap.TAMANHOS or (cor not in ap.CORES and cor not in cursores.CORES):
            return
        if cor in cursores.CORES:
            self.estilo, self.cor_personalizada = PERSONALIZADO, cor
        else:
            self.estilo = cor
        self.tamanho.blockSignals(True)
        self.tamanho.setValue(n)
        self.tamanho.blockSignals(False)
        self.numero.setText(str(n))
        self._mostrar()

    def _estilo(self, estilo: str) -> None:
        self.estilo = estilo
        self._mostrar()
        self.mudou.emit(self.valor())

    def _cor_personalizada(self, cor: str) -> None:
        self.estilo, self.cor_personalizada = PERSONALIZADO, cor
        self._mostrar()
        self.mudou.emit(self.valor())
