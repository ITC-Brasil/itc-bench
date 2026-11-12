"""Ajuda consolidada (ADR-007, ADR-023): reúne as constantes `AJUDA*` das telas, sem copiar
texto, na ordem do menu, com busca sem diferenciar acento e maiúscula.

A tela tem um índice por grupo do menu à esquerda e, à direita, a ajuda da tela escolhida em
seções: o parágrafo de abertura e um cartão por subtítulo, com passos numerados e tópicos.
Tudo em texto puro (QLabel PlainText), nunca HTML.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.ui import tema
from itc_bench.ui.aparencia import AJUDA_ENERGIA, AJUDA_MOUSE, AJUDA_TELA
from itc_bench.ui.configuracoes import AJUDA as AJUDA_CONFIGURACOES
from itc_bench.ui.contas import AJUDA as AJUDA_CONTAS
from itc_bench.ui.contas import _rotulo
from itc_bench.ui.diagnostico import AJUDA_COLETA, AJUDA_HISTORICO
from itc_bench.ui.identificacao import AJUDA as AJUDA_IDENTIFICACAO
from itc_bench.ui.inicio import AJUDA as AJUDA_INICIO
from itc_bench.ui.limpeza import AJUDA as AJUDA_LIMPEZA
from itc_bench.ui.navegacao import GRUPOS
from itc_bench.ui.politicas import AJUDA as AJUDA_POLITICAS
from itc_bench.ui.politicas import AJUDA_USB
from itc_bench.ui.preparacao import AJUDA as AJUDA_PREPARACAO
from itc_bench.ui.programas import AJUDA as AJUDA_PROGRAMAS
from itc_bench.ui.programas import AJUDA_REMOVER
from itc_bench.ui.protecao import AJUDA as AJUDA_PROTECAO
from itc_bench.ui.registro import AJUDA as AJUDA_REGISTRO
from itc_bench.ui.remoto import AJUDA as AJUDA_REMOTO
from itc_bench.ui.wifi import AJUDA as AJUDA_WIFI

AJUDA = (
    "Reúne a ajuda de todas as telas, separada pelos grupos do menu.\n\n"
    "Como usar\n"
    "1. Escolha a tela no índice à esquerda.\n"
    "2. Leia a abertura e as seções; os passos estão numerados na ordem em que se faz.\n"
    "3. Use Abrir esta tela para ir direto a ela.\n\n"
    "Buscar\n"
    "Digite na busca para deixar no índice só as telas que têm a palavra (acento e maiúscula "
    "não importam).\n\n"
    "Atalho\n"
    "O botão ? de cada tela mostra só a ajuda dela; Ver toda a ajuda traz até aqui, já na "
    "tela certa."
)

TEXTOS: dict[str, str] = {
    "inicio": AJUDA_INICIO,
    "prep": AJUDA_PREPARACAO,
    "id": AJUDA_IDENTIFICACAO,
    "contas": AJUDA_CONTAS,
    "wifi": AJUDA_WIFI,
    "remoto": AJUDA_REMOTO,
    "prog": AJUDA_PROGRAMAS,
    "remover": AJUDA_REMOVER,
    "gpo": AJUDA_POLITICAS,
    "protecao": AJUDA_PROTECAO,
    "usb": AJUDA_USB,
    "aparencia": AJUDA_TELA,
    "mouse": AJUDA_MOUSE,
    "energia": AJUDA_ENERGIA,
    "diag": AJUDA_COLETA,
    "hist": AJUDA_HISTORICO,
    "limpeza": AJUDA_LIMPEZA,
    "registro": AJUDA_REGISTRO,
    "ajuda": AJUDA,
    "config": AJUDA_CONFIGURACOES,
}

PASSO = re.compile(r"^(\d+)\.\s+(.*)$", re.DOTALL)
TOPICO = re.compile(r"^[•-]\s+(.*)$", re.DOTALL)
FIM_DE_FRASE = tuple(".,;:!?)…")


def _normal(texto: str) -> str:
    sem = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem if not unicodedata.combining(c)).casefold()


def secoes(busca: str = "") -> list[tuple[str, str, str]]:
    """(chave, "Grupo › Tela", texto) na ordem do menu, filtradas pela busca."""
    termo = _normal(busca.strip())
    saida = []
    for grupo, itens in GRUPOS:
        for item in itens:
            texto = TEXTOS.get(item.chave, "")
            titulo = item.titulo if grupo == item.titulo else f"{grupo} › {item.titulo}"
            if termo and termo not in _normal(f"{titulo}\n{texto}"):
                continue
            saida.append((item.chave, titulo, texto))
    return saida


@dataclass
class Bloco:
    """Seção da ajuda: subtítulo (None na abertura) e linhas ("texto", "passo", "topico")."""

    titulo: str | None
    linhas: list[tuple[str, str, str]] = field(default_factory=list)  # (tipo, marca, texto)


def _subtitulo(linha: str) -> bool:
    linha = linha.strip()
    return (
        0 < len(linha) <= 60
        and not linha.endswith(FIM_DE_FRASE)
        and not PASSO.match(linha)
        and not TOPICO.match(linha)
    )


def blocos(texto: str) -> list[Bloco]:
    """Separa o texto de ajuda em seções pelos subtítulos que as telas já usam.

    Subtítulo = primeira linha curta de um parágrafo, sem pontuação final e seguida de texto.
    Parágrafo sem subtítulo continua a seção anterior (ou a abertura).
    """
    saida = [Bloco(None)]
    for paragrafo in texto.strip().split("\n\n"):
        linhas = [ln for ln in paragrafo.split("\n") if ln.strip()]
        if not linhas:
            continue
        if len(linhas) > 1 and _subtitulo(linhas[0]):
            saida.append(Bloco(linhas[0].strip()))
            linhas = linhas[1:]
        alvo = saida[-1]
        for ln in linhas:
            ln = ln.strip()
            if m := PASSO.match(ln):
                alvo.linhas.append(("passo", m[1], m[2]))
            elif m := TOPICO.match(ln):
                alvo.linhas.append(("topico", "•", m[1]))
            else:
                alvo.linhas.append(("texto", "", ln))
    return [b for b in saida if b.linhas or b.titulo]


def _corpo(linhas: list[tuple[str, str, str]]) -> QVBoxLayout:
    v = QVBoxLayout()
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)
    for tipo, marca, texto in linhas:
        rotulo = _rotulo(texto)
        rotulo.setObjectName("ajudaTexto")
        rotulo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if tipo == "texto":
            v.addWidget(rotulo)
            continue
        h = QHBoxLayout()
        h.setSpacing(10)
        selo = QLabel(marca)
        selo.setTextFormat(Qt.TextFormat.PlainText)
        selo.setObjectName("ajudaPasso" if tipo == "passo" else "ajudaTopico")
        selo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selo.setFixedSize(20, 20)
        h.addWidget(selo, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(rotulo, 1)
        v.addLayout(h)
    return v


class PainelAjuda(QWidget):
    abrir_tela = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.atual: str | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        topo = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar na ajuda (ex.: senha, Wi-Fi, reinício)")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self.mostrar)
        self.contagem = _rotulo("")
        self.contagem.setObjectName("dica")
        topo.addWidget(self.busca, 1)
        topo.addWidget(self.contagem)
        v.addLayout(topo)

        self.indice = QTreeWidget()
        self.indice.setObjectName("ajudaIndice")
        self.indice.setHeaderHidden(True)
        self.indice.setRootIsDecorated(False)
        self.indice.setIndentation(8)
        self.indice.setMinimumWidth(220)
        self.itens: dict[str, QTreeWidgetItem] = {}
        self.grupos: list[QTreeWidgetItem] = []
        nomes = {i.chave: i.titulo for _, itens in GRUPOS for i in itens}
        for grupo, itens in GRUPOS:
            cab = QTreeWidgetItem([grupo.upper()])
            cab.setFlags(Qt.ItemFlag.ItemIsEnabled)
            fonte = cab.font(0)
            fonte.setBold(True)
            fonte.setPointSizeF(max(7.0, fonte.pointSizeF() - 1.5))
            cab.setFont(0, fonte)
            self.indice.addTopLevelItem(cab)
            self.grupos.append(cab)
            for item in itens:
                filho = QTreeWidgetItem([nomes[item.chave]])
                filho.setData(0, Qt.ItemDataRole.UserRole, item.chave)
                filho.setIcon(0, tema.icone(item.chave, tema.CY))
                cab.addChild(filho)
                self.itens[item.chave] = filho
        self.indice.expandAll()
        self.indice.currentItemChanged.connect(self._escolheu)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.conteudo = QWidget()
        self.area.setWidget(self.conteudo)

        divisor = QSplitter()
        divisor.addWidget(self.indice)
        divisor.addWidget(self.area)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([240, 760])
        divisor.setChildrenCollapsible(False)
        v.addWidget(divisor, 1)
        self.mostrar()

    def mostrar(self, busca: str | None = None) -> None:
        """Filtra o índice pela busca e mantém (ou escolhe) uma tela visível."""
        achadas = {c for c, _, _ in secoes(self.busca.text() if busca is None else busca)}
        for cab in self.grupos:
            visiveis = 0
            for i in range(cab.childCount()):
                filho = cab.child(i)
                if filho is None:
                    continue
                esconder = filho.data(0, Qt.ItemDataRole.UserRole) not in achadas
                filho.setHidden(esconder)
                visiveis += not esconder
            cab.setHidden(visiveis == 0)
        self.contagem.setText(f"{len(achadas)} tela(s)")
        if not achadas:
            self._pintar(None)
        elif self.atual not in achadas:
            primeira = next(c for c, _, _ in secoes() if c in achadas)
            self.indice.setCurrentItem(self.itens[primeira])

    def _escolheu(self, item: QTreeWidgetItem | None, _anterior: object = None) -> None:
        chave = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(chave, str):
            self._pintar(chave)

    def _pintar(self, chave: str | None) -> None:
        self.atual = chave
        antigo = self.area.takeWidget()
        if antigo is not None:
            antigo.deleteLater()
        self.conteudo = QWidget()
        self.conteudo.setObjectName("ajudaConteudo")
        v = QVBoxLayout(self.conteudo)
        v.setContentsMargins(4, 4, 12, 12)
        v.setSpacing(12)
        if chave is None:
            vazio = _rotulo("Nada encontrado. Tente outra palavra.")
            vazio.setObjectName("vazio")
            v.addWidget(vazio)
            v.addStretch()
            self.area.setWidget(self.conteudo)
            return
        _, caminho, texto = next(s for s in secoes() if s[0] == chave)
        trilha = _rotulo(caminho)
        trilha.setObjectName("trilha")
        titulo = _rotulo(caminho.split(" › ")[-1])
        titulo.setObjectName("ajudaNome")
        abrir = QPushButton("Abrir esta tela")
        abrir.clicked.connect(lambda _c=False, k=chave: self.abrir_tela.emit(k))
        abrir.setVisible(chave != "ajuda")
        cab = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(4)
        textos.addWidget(trilha)
        textos.addWidget(titulo)
        cab.addLayout(textos, 1)
        cab.addWidget(abrir, 0, Qt.AlignmentFlag.AlignBottom)
        v.addLayout(cab)
        for bloco in blocos(texto):
            if bloco.titulo is None:
                abertura = QFrame()
                abertura.setObjectName("ajudaAbertura")
                corpo = _corpo(bloco.linhas)
                corpo.setContentsMargins(14, 10, 14, 10)
                abertura.setLayout(corpo)
                v.addWidget(abertura)
                continue
            cartao = QFrame()
            cartao.setObjectName("cartao")
            c = QVBoxLayout(cartao)
            c.setContentsMargins(16, 12, 16, 14)
            c.setSpacing(8)
            nome = _rotulo(bloco.titulo)
            nome.setObjectName("subtitulo")
            c.addWidget(nome)
            c.addLayout(_corpo(bloco.linhas))
            v.addWidget(cartao)
        v.addStretch()
        self.area.setWidget(self.conteudo)
        self.area.verticalScrollBar().setValue(0)

    def ir_para(self, chave: str) -> None:
        """Mostra a ajuda da tela (botão "Ver toda a ajuda" do popup)."""
        self.busca.clear()
        if chave in self.itens:
            self.indice.setCurrentItem(self.itens[chave])

    def texto_atual(self) -> str:
        """Texto da tela mostrada (para teste e cópia), sem formatação."""
        if self.atual is None:
            return ""
        return next(t for c, _, t in secoes() if c == self.atual)
