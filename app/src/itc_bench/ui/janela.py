"""Janela principal: barra lateral com os 7 grupos e uma tela vazia por item."""

import getpass
import socket

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from itc_bench import __version__
from itc_bench.ui import tema
from itc_bench.ui.log_qt import HandlerTela
from itc_bench.ui.navegacao import GRUPOS, Item

TEXTO_AJUDA = "Instruções desta tela em breve"


class PopupAjuda(QWidget):
    """Véu escuro sobre a tela com o cartão de ajuda no canto superior direito, como no design."""

    def __init__(self, pai: QWidget, titulo: str) -> None:
        super().__init__(pai)
        self._pai = pai
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("PopupAjuda { background: rgba(26, 32, 32, 97); }")
        cartao = QFrame(self)
        cartao.setObjectName("painel")
        cartao.setFixedWidth(420)
        nome = QLabel(f"Ajuda · {titulo}")
        nome.setObjectName("ajudaTitulo")
        self.fechar = QPushButton("✕")
        self.fechar.setObjectName("ajudaFechar")
        self.fechar.setFixedSize(24, 24)
        self.fechar.clicked.connect(self.hide)
        cab = QHBoxLayout()
        cab.addWidget(nome)
        cab.addStretch()
        cab.addWidget(self.fechar)
        self.texto = QLabel(TEXTO_AJUDA)
        self.texto.setObjectName("vazio")
        self.texto.setWordWrap(True)
        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(18, 14, 18, 18)
        corpo.setSpacing(12)
        corpo.addLayout(cab)
        corpo.addWidget(self.texto)
        fora = QVBoxLayout(self)
        fora.setContentsMargins(28, 72, 28, 0)
        fora.addWidget(cartao, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        pai.installEventFilter(self)
        self.hide()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        if evento.type() == QEvent.Type.Resize:
            self.setGeometry(self._pai.rect())
        return False

    def mostrar(self) -> None:
        self.setGeometry(self._pai.rect())
        self.show()
        self.raise_()


class Tela(QWidget):
    def __init__(self, grupo: str, item: Item) -> None:
        super().__init__()
        self.setObjectName("principal")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        trilha = QLabel(grupo if grupo == item.titulo else f"{grupo} › {item.titulo}")
        trilha.setObjectName("trilha")
        self.titulo = QLabel(item.titulo)
        self.titulo.setObjectName("titulo")
        self.botao_ajuda = QPushButton("?")
        self.botao_ajuda.setObjectName("ajudaBotao")
        self.botao_ajuda.setFixedSize(20, 20)
        self.botao_ajuda.setCheckable(True)
        self.botao_ajuda.setToolTip("Ajuda desta tela")
        linha = QHBoxLayout()
        linha.setSpacing(10)
        linha.addWidget(self.titulo)
        linha.addWidget(self.botao_ajuda)
        linha.addStretch()
        textos = QVBoxLayout()
        textos.setSpacing(5)
        textos.addWidget(trilha)
        textos.addLayout(linha)
        topo = QFrame()
        topo.setObjectName("topo")
        topo.setFixedHeight(64)
        lt = QHBoxLayout(topo)
        lt.setContentsMargins(24, 0, 24, 0)
        lt.addLayout(textos)

        painel = QFrame()
        painel.setObjectName("painel")
        self.corpo = QVBoxLayout(painel)
        self.corpo.setContentsMargins(20, 20, 20, 20)
        self.corpo.setSpacing(10)
        vazio = QLabel("Esta tela ainda não tem conteúdo.")
        vazio.setObjectName("vazio")
        self.modulo = QLabel(f"Módulo {item.modulo}")
        self.modulo.setObjectName("modulo")
        self.corpo.addWidget(vazio)
        self.corpo.addWidget(self.modulo, 0, Qt.AlignmentFlag.AlignLeft)
        self.corpo.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(topo)
        area = QVBoxLayout()
        area.setContentsMargins(24, 20, 24, 20)
        area.addWidget(painel)
        layout.addLayout(area, 1)

        self.ajuda = PopupAjuda(self, item.titulo)
        self.ajuda.installEventFilter(self)
        self.botao_ajuda.toggled.connect(self._alternar_ajuda)

    def _alternar_ajuda(self, ligado: bool) -> None:
        if ligado:
            self.ajuda.mostrar()
        else:
            self.ajuda.hide()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        if objeto is self.ajuda and evento.type() == QEvent.Type.Hide:
            self.botao_ajuda.setChecked(False)
        return False


class Janela(QMainWindow):
    def __init__(self, handler_tela: HandlerTela) -> None:
        super().__init__()
        self.setWindowTitle("ITC Bench")
        self.setWindowIcon(tema.icone_janela())
        self.resize(1180, 720)
        self.pilha = QStackedWidget()
        self.botoes = QButtonGroup(self)
        self.telas: dict[str, Tela] = {}
        self.nav: dict[str, QPushButton] = {}

        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(232)
        lat = QVBoxLayout(lateral)
        lat.setContentsMargins(10, 16, 10, 12)
        lat.setSpacing(2)
        lat.addWidget(self._marca())
        for indice, (grupo, itens) in enumerate(GRUPOS):
            if indice > 0:
                secao = QLabel(grupo.upper())
                secao.setObjectName("secao")
                lat.addWidget(secao)
            for item in itens:
                lat.addWidget(self._item(grupo, item))
        lat.addStretch()
        rodape = QLabel(f"{socket.gethostname()} · {getpass.getuser()}<br>Bench {__version__}")
        rodape.setObjectName("rodape")
        lat.addWidget(rodape)

        self._log_na_tela(handler_tela)
        self.abrir("inicio")

        centro = QWidget()
        h = QHBoxLayout(centro)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        # Com 20 itens a barra passa de 720 px; rola em telas de 768p em vez de esticar a janela.
        rolagem = QScrollArea()
        rolagem.setObjectName("lateral")
        rolagem.setWidget(lateral)
        rolagem.setWidgetResizable(True)
        rolagem.setFixedWidth(232)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h.addWidget(rolagem)
        h.addWidget(self.pilha, 1)
        self.setCentralWidget(centro)

    def abrir(self, chave: str) -> None:
        self.nav[chave].setChecked(True)
        self.pilha.setCurrentWidget(self.telas[chave])

    def _item(self, grupo: str, item: Item) -> QPushButton:
        tela = Tela(grupo, item)
        self.telas[item.chave] = tela
        self.pilha.addWidget(tela)
        botao = QPushButton(item.titulo)
        botao.setObjectName("nav")
        botao.setCheckable(True)
        botao.setIconSize(QSize(16, 16))
        botao.setIcon(tema.icone_nav(item.chave))
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.clicked.connect(lambda: self.abrir(item.chave))
        self.botoes.addButton(botao)
        self.nav[item.chave] = botao
        return botao

    def _marca(self) -> QWidget:
        simbolo = QLabel()
        simbolo.setPixmap(tema.simbolo("escuro", 28))
        itc = QLabel("ITC")
        itc.setObjectName("marcaItc")
        bench = QLabel("Bench")
        bench.setObjectName("marcaBench")
        nome = QVBoxLayout()
        nome.setSpacing(1)
        nome.addWidget(itc)
        nome.addWidget(bench)
        marca = QWidget()
        h = QHBoxLayout(marca)
        h.setContentsMargins(8, 2, 8, 16)
        h.setSpacing(6)
        h.addWidget(simbolo)
        h.addLayout(nome)
        h.addStretch()
        return marca

    def _log_na_tela(self, handler: HandlerTela) -> None:
        """A tela Registro mostra, ao vivo, as mesmas linhas gravadas no arquivo."""
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setPlainText("\n".join(handler.historico))
        handler.ponte.linha.connect(self.log.appendPlainText)
        corpo = self.telas["registro"].corpo
        corpo.takeAt(corpo.count() - 1)  # tira o espaçador; o log ocupa o painel
        corpo.addWidget(self.log, 1)
