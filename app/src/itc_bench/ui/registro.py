"""Tela Registro (ADR-023, item 8): o `bench.log` e os rotacionados, só leitura, com filtro e
exportação mascarada. Linhas novas desta sessão chegam ao vivo pelo `HandlerTela`."""

import socket
from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import registro
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo
from itc_bench.ui.log_qt import HandlerTela

AJUDA = (
    "Mostra o registro do Bench (o arquivo bench.log e os quatro anteriores), do mais antigo ao "
    "mais novo. Só leitura: nada aqui apaga o registro.\n\n"
    "Filtrar\n"
    "Escolha o nível mínimo (Avisos mostra avisos e erros) e digite um trecho para buscar.\n\n"
    "O que o registro tem\n"
    "Técnico, ação, resultado e código de cada operação; nomes das contas afetadas e o nome do "
    "computador. Nunca senha, token, nome de rede Wi-Fi, endereço de servidor, SID ou pasta de "
    "perfil.\n\n"
    "Exportar\n"
    "Grava em .txt só as linhas filtradas, trocando o nome do computador, os nomes das contas "
    "e as pastas de perfil por marcadores (<computador>, <conta-1>, <perfil>). Use para anexar "
    "a um chamado."
)
NIVEIS = {"Tudo": "DEBUG", "Informação": "INFO", "Avisos": "WARNING", "Erros": "ERROR"}


class PainelRegistro(QWidget):
    def __init__(
        self,
        handler: HandlerTela | None = None,
        pasta: Path | None = None,
        contas: Callable[[], list[str]] = list,
    ) -> None:
        super().__init__()
        self.pasta = pasta
        self.contas = contas
        self.linhas: list[registro.Linha] = []
        self.lido = False
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.nivel = QComboBox()
        self.nivel.addItems(list(NIVEIS))
        self.nivel.setCurrentText("Informação")
        self.nivel.currentTextChanged.connect(lambda _t: self.mostrar())
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar no registro")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(lambda _t: self.mostrar())
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        self.exportar = QPushButton("Exportar…")
        self.exportar.clicked.connect(self._exportar)
        topo.addWidget(self.nivel)
        topo.addWidget(self.busca, 1)
        topo.addWidget(self.atualizar)
        topo.addWidget(self.exportar)
        v.addLayout(topo)
        self.estado = _rotulo("")
        v.addWidget(self.estado)
        self.texto = QPlainTextEdit()
        self.texto.setObjectName("log")
        self.texto.setReadOnly(True)
        v.addWidget(self.texto, 1)
        if handler is not None:
            # Ao vivo desde a abertura; o arquivo completo entra ao abrir a tela.
            self.texto.setPlainText("\n".join(handler.historico))
            handler.ponte.linha.connect(self._ao_vivo)

    def _ao_vivo(self, linha: str) -> None:
        if not self.busca.text() or self.busca.text().casefold() in linha.casefold():
            self.texto.appendPlainText(linha)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido:
            self.carregar()

    def carregar(self) -> None:
        self.estado.setText("Lendo o registro…")
        pasta = self.pasta
        tarefa.iniciar(lambda: registro.ler(pasta), self._recebeu, self._falhou)

    def _recebeu(self, linhas: list[registro.Linha]) -> None:
        self.linhas, self.lido = linhas, True
        self.mostrar()

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Não foi possível ler o registro: {motivo}")

    def filtradas(self) -> list[registro.Linha]:
        return registro.filtrar(self.linhas, NIVEIS[self.nivel.currentText()], self.busca.text())

    def mostrar(self) -> None:
        if not self.lido:
            return
        lista = self.filtradas()
        self.texto.setPlainText("\n".join(str(ln) for ln in lista))
        self.texto.moveCursor(self.texto.textCursor().MoveOperation.End)
        self.estado.setText(f"{len(lista)} de {len(self.linhas)} linha(s).")

    def _exportar(self) -> None:
        lista = self.filtradas()
        if not lista:
            self.estado.setText("Nada a exportar com esse filtro.")
            return
        nome, _ = QFileDialog.getSaveFileName(
            self, "Exportar registro", "registro-bench.txt", "Texto (*.txt)"
        )
        if not nome:
            return
        try:
            n = registro.exportar(lista, Path(nome), socket.gethostname(), self.contas())
        except OSError as erro:
            QMessageBox.warning(self, "Registro", f"Não foi possível gravar: {erro.strerror}")
            return
        self.estado.setText(f"{n} linha(s) exportada(s), com nomes mascarados.")
