"""Faixa da atualização (ADR-026): a única tela nova do Módulo 16. Texto puro (ADR-024)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from itc_bench.servicos.atualizacao import Oferta
from itc_bench.ui import texto as txt

AJUDA = (
    "Atualização do ITC Bench.\n\n"
    "A versão nova foi baixada da API e conferida pela assinatura do responsável. Ela é "
    "instalada quando você fecha o Bench, depois de confirmar aqui. Com Preparação em andamento "
    "ou retomada pendente, o Bench fecha sem atualizar e tenta de novo na próxima vez.\n\n"
    "Obrigatória: a versão em uso está abaixo da mínima; feche o Bench para atualizar.\n"
    "Se a atualização não entrar, o log fica em %ProgramData%\\ITC\\Bench\\protegido\\atualizacao "
    "e o instalador do CI pode ser rodado de novo por um administrador."
)


class FaixaAtualizacao(QFrame):
    fechar_agora = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("faixa")
        self.confirmada = False
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 8, 16, 8)
        self.texto = QLabel()
        self.texto.setTextFormat(Qt.TextFormat.PlainText)
        self.texto.setWordWrap(True)
        self.instalar = QPushButton("Instalar ao fechar")
        self.instalar.setCheckable(True)
        self.instalar.toggled.connect(self._confirmar)
        self.agora = QPushButton("Fechar e atualizar agora")
        self.agora.clicked.connect(self.fechar_agora.emit)
        self.adiar = QPushButton("Agora não")
        self.adiar.clicked.connect(self._adiar)
        ajuda = QPushButton("?")
        ajuda.setFixedWidth(32)
        ajuda.setToolTip(txt.dica(AJUDA))
        ajuda.clicked.connect(lambda: self.texto.setText(AJUDA))
        for w in (self.texto, self.instalar, self.agora, self.adiar, ajuda):
            h.addWidget(w, 1 if w is self.texto else 0)
        self.hide()

    def _adiar(self) -> None:
        self.instalar.setChecked(False)
        self.hide()

    def _confirmar(self, ligado: bool) -> None:
        self.confirmada = ligado

    def mostrar(self, oferta: Oferta) -> None:
        m = oferta.manifesto
        tipo = "obrigatória" if oferta.obrigatoria else "pronta"
        self.texto.setText(f"Versão {m.versao} {tipo}. {m.notas}")
        self.instalar.setChecked(oferta.obrigatoria or self.confirmada)
        self.instalar.setEnabled(not oferta.obrigatoria)
        self.adiar.setVisible(not oferta.obrigatoria)
        self.show()

    def aviso(self, texto: str) -> None:
        self.texto.setText(texto)
        self.instalar.hide()
        self.agora.hide()
        self.show()
