"""Tela Limpeza (ADR-023, item 7). Regras e caminhos em `servicos/limpeza.py`; aqui só tela."""

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import limpeza
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Apaga arquivos que o Windows e os programas deixam para trás. Lista fechada: temporários "
    "do sistema, temporários de cada conta, lixeira de todas as contas, cache de download do "
    "Windows Update e relatórios de erro do Windows.\n\n"
    "Como usar\n"
    "1. Calcular mostra quanto cada item ocupa, sem apagar nada.\n"
    "2. Marque o que quer limpar e confirme. Só os itens marcados são apagados.\n"
    "3. Arquivo em uso fica e aparece como “em uso”.\n\n"
    "Windows Update\n"
    "O Bench para o serviço do Windows Update, apaga o cache de download e volta o serviço como "
    "estava. Com atualização esperando reinício, o item fica “não limpo”: reinicie e limpe de "
    "novo.\n\n"
    "O que a Limpeza não apaga\n"
    "Documentos, Área de Trabalho, Downloads, dados de navegador, perfis de conta, Windows.old e "
    "pontos de restauração. Atalhos e links dentro das pastas são removidos como link, sem "
    "entrar no destino.\n\n"
    "Sem administrador (modo de teste), só a prévia do que dá para ler."
)


class PainelLimpeza(QWidget):
    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.previa: dict[str, limpeza.Item] = {}
        self.ocupado = self.lido = False
        v = QVBoxLayout(self)
        self.estado = _rotulo("")
        v.addWidget(self.estado)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só a prévia."))
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Item", "Arquivos", "Tamanho", "Situação"])
        self.arvore.setColumnWidth(0, 280)
        self.arvore.setRootIsDecorated(False)
        for iid, nome in limpeza.ITENS:
            item = QTreeWidgetItem([nome, "", "", "não calculado"])
            item.setData(0, Qt.ItemDataRole.UserRole, iid)
            item.setCheckState(
                0, Qt.CheckState.Checked if iid != "lixeira" else Qt.CheckState.Unchecked
            )
            self.arvore.addTopLevelItem(item)
        self.arvore.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        v.addWidget(self.arvore, 1)
        acoes = QHBoxLayout()
        self.b_calcular = QPushButton("Calcular")
        self.b_calcular.clicked.connect(self.calcular)
        self.b_limpar = QPushButton("Limpar")
        self.b_limpar.setObjectName("primario")
        self.b_limpar.clicked.connect(self._limpar)
        acoes.addStretch()
        acoes.addWidget(self.b_calcular)
        acoes.addWidget(self.b_limpar)
        v.addLayout(acoes)
        self._ocupar(False)

    def marcar(self, ids: Iterable[str]) -> None:
        fora = set(ids)
        for i in range(self.arvore.topLevelItemCount()):
            item = self.arvore.topLevelItem(i)
            if item is not None:
                iid = item.data(0, Qt.ItemDataRole.UserRole)
                estado = Qt.CheckState.Checked if iid in fora else Qt.CheckState.Unchecked
                item.setCheckState(0, estado)

    def marcados(self) -> list[str]:
        saida = []
        for i in range(self.arvore.topLevelItemCount()):
            item = self.arvore.topLevelItem(i)
            if item is not None and item.checkState(0) == Qt.CheckState.Checked:
                saida.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return saida

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.calcular()

    def calcular(self) -> None:
        self._ocupar(True)
        self.estado.setText("Calculando…")
        tarefa.iniciar(
            lambda: limpeza.previa([i for i, _ in limpeza.ITENS]), self._calculou, self._falhou
        )

    def _mostrar(self, itens: list[limpeza.Item], limpou: bool) -> None:
        por = {i.id: i for i in itens}
        for n in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(n)
            if linha is None:
                continue
            i = por.get(str(linha.data(0, Qt.ItemDataRole.UserRole)))
            if i is None:
                continue
            linha.setText(1, str(i.arquivos))
            linha.setText(2, limpeza.tamanho(i.bytes))
            if limpou:
                situacao = "limpo" if i.ok else f"não limpo: {i.motivo}"
            else:
                situacao = "pronto" if not i.codigo else i.motivo
            if i.em_uso:
                situacao += f" ({i.em_uso} em uso)"
            linha.setText(3, situacao)

    def _calculou(self, itens: list[limpeza.Item]) -> None:
        self.previa = {i.id: i for i in itens}
        self.lido = True
        self._mostrar(itens, False)
        total = sum(i.bytes for i in itens)
        self.estado.setText(f"Total: {limpeza.tamanho(total)}.")
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        ids = [i for i in self.marcados() if i in self.previa]
        total = sum(self.previa[i].bytes for i in ids)
        self.b_limpar.setText(f"Limpar {limpeza.tamanho(total)}" if ids else "Limpar")
        self.b_limpar.setEnabled(self.admin and not ocupado and bool(ids))
        if not self.admin:
            self.b_limpar.setToolTip("Precisa de administrador.")
        self.b_calcular.setEnabled(not ocupado)

    def _limpar(self) -> None:
        ids = [i for i in self.marcados() if i in self.previa]
        nomes = "\n".join(
            f"• {limpeza.NOMES[i]}: {limpeza.tamanho(self.previa[i].bytes)}" for i in ids
        )
        total = limpeza.tamanho(sum(self.previa[i].bytes for i in ids))
        if not confirmar(
            self,
            "Limpeza",
            f"Apagar {total}?\n\n{nomes}\n\nNão dá para desfazer (a lixeira inclusive).",
        ):
            return
        self._ocupar(True)
        self.estado.setText("Limpando…")
        tarefa.iniciar(lambda: limpeza.limpar(ids), self._limpou, self._falhou)

    def _limpou(self, itens: list[limpeza.Item]) -> None:
        self._mostrar(itens, True)
        apagados = sum(i.bytes for i in itens)
        ruins = [i for i in itens if not i.ok]
        self.estado.setText(
            f"Limpeza feita: {limpeza.tamanho(apagados)} examinados."
            + (f" {len(ruins)} item(ns) não limpo(s)." if ruins else "")
        )
        self.previa = {}
        self._ocupar(False)
        if ruins:
            caixa = QMessageBox(
                QMessageBox.Icon.Warning,
                "Limpeza",
                "\n".join(f"{limpeza.NOMES[i.id]}: {i.motivo}" for i in ruins),
                parent=self,
            )
            caixa.setTextFormat(Qt.TextFormat.PlainText)
            caixa.open()
