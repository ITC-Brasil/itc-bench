"""Texto de fora (cadastro, Windows, erro) na tela sempre como texto puro (Módulo 14).

`QMessageBox.warning()` e afins e `setToolTip()` usam rich text automático: um `<` no dado vira
marcação. Qualquer dado que não seja constante do código passa por aqui.
"""

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def aviso(
    pai: QWidget | None,
    titulo: str,
    texto: str,
    icone: QMessageBox.Icon = QMessageBox.Icon.Warning,
) -> None:
    caixa = QMessageBox(icone, titulo, texto, parent=pai)
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    caixa.exec()


def dica(texto: str) -> str:
    """Dica do Qt não tem formato: força rich text com o dado escapado."""
    return f"<p>{html.escape(texto)}</p>" if texto else ""
