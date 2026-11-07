"""Ajuda consolidada (ADR-007, ADR-023): reúne as constantes `AJUDA*` das telas, sem copiar
texto, na ordem do menu, com busca sem diferenciar acento e maiúscula."""

import unicodedata

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

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
    "Reúne a ajuda de todas as telas, na ordem do menu.\n\n"
    "Digite na busca para ver só os trechos que têm a palavra (acento e maiúscula não importam). "
    "O botão ? de cada tela mostra só a ajuda dela; “Ver toda a ajuda” traz até aqui."
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


class PainelAjuda(QWidget):
    abrir_tela = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar na ajuda")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self.mostrar)
        self.contagem = _rotulo("")
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        v.addWidget(self.busca)
        v.addWidget(self.contagem)
        v.addWidget(self.texto, 1)
        self.mostrar()

    def mostrar(self, busca: str | None = None) -> None:
        lista = secoes(self.busca.text() if busca is None else busca)
        partes = [f"{titulo}\n{'─' * len(titulo)}\n{texto}" for _, titulo, texto in lista]
        self.texto.setPlainText("\n\n\n".join(partes) or "Nada encontrado.")
        self.contagem.setText(f"{len(lista)} tela(s)")

    def ir_para(self, chave: str) -> None:
        """Rola até a seção da tela (botão "Ver toda a ajuda" do popup)."""
        self.busca.clear()
        titulo = next((t for c, t, _ in secoes() if c == chave), "")
        if titulo:
            cursor = self.texto.document().find(titulo)
            if not cursor.isNull():
                self.texto.setTextCursor(cursor)
                self.texto.centerCursor()
