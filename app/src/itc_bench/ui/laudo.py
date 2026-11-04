"""Laudo da IA em tela sem rich text vindo de fora (ADR-015).

O Markdown é montado num `QTextDocument` só com `QTextCursor.insertText`: títulos (`#` a `###`),
listas (`-`, `*`, `1.`), parágrafos e `**negrito**`. Nada passa por `setHtml`, `setMarkdown` ou
`QLabel` em rich text: HTML aparece como texto, link é texto literal e imagem vira o alt. O
widget não abre link nem carrega recurso.
"""

import re

from PySide6.QtGui import (
    QFont,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
)
from PySide6.QtWidgets import QTextBrowser

AVISO = "Gerado por IA. Revise antes de abrir chamado."
TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
ITEM = re.compile(r"^\s*(?:[-*+]|(\d+)[.)])\s+(.*)$")
IMAGEM = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
NEGRITO = re.compile(r"\*\*(.+?)\*\*")
TAMANHOS = {1: 1.35, 2: 1.2, 3: 1.08}


def _trechos(linha: str, cursor: QTextCursor, base: QTextCharFormat) -> None:
    """Texto literal com negrito; imagem vira só o alt (sem endereço)."""
    linha = IMAGEM.sub(lambda m: m[1], linha)
    posicao = 0
    for m in NEGRITO.finditer(linha):
        cursor.insertText(linha[posicao : m.start()], base)
        forte = QTextCharFormat(base)
        forte.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(m[1], forte)
        posicao = m.end()
    cursor.insertText(linha[posicao:], base)


def documento(markdown: str, fonte: QFont | None = None) -> QTextDocument:
    doc = QTextDocument()
    if fonte is not None:
        doc.setDefaultFont(fonte)
    cursor = QTextCursor(doc)
    normal = QTextCharFormat()
    primeiro = True
    lista_atual = None
    for bruta in markdown.replace("\r\n", "\n").split("\n"):
        linha = bruta.rstrip()
        if not linha.strip():
            lista_atual = None
            continue
        bloco = QTextBlockFormat()
        bloco.setBottomMargin(4)
        if not primeiro:
            cursor.insertBlock(bloco, normal)
        else:
            cursor.setBlockFormat(bloco)
        primeiro = False
        if m := TITULO.match(linha):
            nivel = min(len(m[1]), 3)
            formato = QTextCharFormat()
            formato.setFontWeight(QFont.Weight.Bold)
            tamanho = (fonte.pointSizeF() if fonte else 10) * TAMANHOS[nivel]
            formato.setFontPointSize(tamanho)
            bloco.setTopMargin(8)
            cursor.setBlockFormat(bloco)
            _trechos(m[2], cursor, formato)
            lista_atual = None
        elif m := ITEM.match(linha):
            if lista_atual is None:
                estilo = (
                    QTextListFormat.Style.ListDecimal if m[1] else QTextListFormat.Style.ListDisc
                )
                lista_atual = cursor.createList(estilo)
            else:
                lista_atual.add(cursor.block())
            _trechos(m[2], cursor, normal)
        else:
            lista_atual = None
            _trechos(linha, cursor, normal)
    return doc


class VisorLaudo(QTextBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)

    def mostrar(self, markdown: str) -> None:
        doc = documento(markdown, self.font())
        doc.setParent(self)
        self.setDocument(doc)

    def loadResource(self, tipo: int, nome: object) -> None:
        return None  # nenhum recurso externo ou local, nunca
