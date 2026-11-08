"""Tela Configurações (ADR-014): os cadastros do cache, só leitura, e a unidade da máquina.

Editar é no NocoDB. Segredo (`Sensivel`) aparece sempre como `••••••••`, sem botão de revelar.
"""

import re
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.executor import Sensivel
from itc_bench.ui import texto as txt

MASCARA = "••••••••"
HEX = re.compile(r"[0-9a-f]{64}")
SEM_UNIDADE = "— bancada (todas as unidades)"

AJUDA = (
    "Mostra os cadastros centrais que este Bench usa: servidores, redes Wi-Fi, instaladores e "
    "unidades. Eles vêm do cadastro central (NocoDB) pela API, depois do login online.\n\n"
    "• Para mudar um cadastro, edite no NocoDB; aqui é só leitura. A mudança chega na próxima "
    "sincronização (a cada 30 min ou em Sincronizar agora).\n"
    "• Senhas e chaves aparecem como ••••••••, sempre.\n"
    "• Sem internet, o Bench usa a última cópia, guardada protegida nesta máquina, por até 7 "
    "dias. Depois disso, conecte e sincronize.\n"
    "• Unidade desta máquina: escolha a unidade para onde o notebook vai. A cópia passa a guardar "
    "só o Wi-Fi dela. Sem unidade (bancada), guarda o Wi-Fi de todas."
)


def _texto(valor: Any) -> str:
    return MASCARA if isinstance(valor, Sensivel) else str(valor)


class PainelConfiguracoes(QWidget):
    sincronizar = Signal()
    unidade_escolhida = Signal(object)  # código ou None (bancada)

    def __init__(self) -> None:
        super().__init__()
        self.origem = QLabel()
        self.origem.setObjectName("modulo")
        self.botao_sincronizar = QPushButton("Sincronizar agora")
        self.botao_sincronizar.clicked.connect(self.sincronizar.emit)
        self.unidade = QComboBox()
        self.unidade.setMinimumWidth(240)
        self.unidade.activated.connect(
            lambda indice: self.unidade_escolhida.emit(self.unidade.itemData(indice))
        )
        topo = QHBoxLayout()
        topo.addWidget(self.origem)
        topo.addStretch()
        topo.addWidget(QLabel("Unidade desta máquina"))
        topo.addWidget(self.unidade)
        topo.addWidget(self.botao_sincronizar)

        self.aviso = QLabel()
        self.aviso.setObjectName("vazio")
        self.aviso.setWordWrap(True)
        self.aviso.setTextFormat(Qt.TextFormat.PlainText)

        self.abas = QTabWidget()
        self.servidores = self._tabela(["Serviço", "Papel", "Valor", "Versão", "Observação"])
        self.wifi = self._tabela(["SSID", "Unidade", "Categoria", "Senha", "Atualizado em"])
        self.instaladores = self._tabela(["Programa", "Versão", "Arquivo", "SHA-256", "Link"])
        self.unidades = self._tabela(["Código", "Nome", "Cidade/UF", "Tag GLPI", "Perfil padrão"])
        self.abas.addTab(self.servidores, "Servidores")
        self.abas.addTab(self.wifi, "Wi-Fi")
        self.abas.addTab(self.instaladores, "Instaladores")
        self.abas.addTab(self.unidades, "Unidades")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(topo)
        layout.addWidget(self.aviso)
        layout.addWidget(self.abas, 1)

    @staticmethod
    def _tabela(cabecalhos: list[str]) -> QTableWidget:
        tabela = QTableWidget(0, len(cabecalhos))
        tabela.setHorizontalHeaderLabels(cabecalhos)
        tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabela.verticalHeader().setVisible(False)
        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return tabela

    @staticmethod
    def _preencher(tabela: QTableWidget, linhas: list[list[Any]], dicas: dict[int, int]) -> None:
        """dicas: coluna → coluna cujo texto completo vai na dica (SHA-256 encurtado)."""
        tabela.setRowCount(len(linhas))
        for i, linha in enumerate(linhas):
            for j, valor in enumerate(linha[: tabela.columnCount()]):
                item = QTableWidgetItem(_texto(valor))
                # Dica do Qt é rich text: só vai se for hex (dado do NocoDB, validado na API).
                if j in dicas and HEX.fullmatch(dica := _texto(linha[dicas[j]])):
                    item.setToolTip(txt.dica(dica))
                tabela.setItem(i, j, item)

    def mostrar(
        self,
        cadastros: Cadastros | None,
        rotulo: str,
        avisos: list[str],
        unidade: str | None,
        online: bool,
    ) -> None:
        self.origem.setText(f"Cadastro central · {rotulo}")
        self.aviso.setText("\n".join(avisos))
        self.aviso.setVisible(bool(avisos))
        self.botao_sincronizar.setEnabled(online)
        self.botao_sincronizar.setToolTip("" if online else "Precisa de login online.")

        self.unidade.blockSignals(True)
        self.unidade.clear()
        self.unidade.addItem(SEM_UNIDADE, None)
        for u in cadastros.unidades if cadastros else ():
            self.unidade.addItem(f"{u.codigo} · {u.nome}" if u.nome else u.codigo, u.codigo)
        indice = self.unidade.findData(unidade)
        self.unidade.setCurrentIndex(max(0, indice))
        self.unidade.blockSignals(False)

        c = cadastros
        self._preencher(
            self.servidores,
            [[s.servico, s.papel, s.valor, s.versao, s.observacao] for s in c.servidores]
            if c
            else [],
            {},
        )
        self._preencher(
            self.wifi,
            [[r.ssid, r.unidade, r.categoria, r.senha, r.atualizado_em] for r in c.redes]
            if c
            else [],
            {},
        )
        self._preencher(
            self.instaladores,
            [
                [i.programa, i.versao, i.arquivo, i.sha256[:12], i.link, i.sha256]
                for i in c.instaladores
            ]
            if c
            else [],
            {3: 5},
        )
        self._preencher(
            self.unidades,
            [
                [
                    u.codigo,
                    u.nome,
                    "/".join(p for p in (u.cidade, u.uf) if p),
                    u.tag_glpi,
                    u.perfil_padrao,
                ]
                for u in c.unidades
            ]
            if c
            else [],
            {},
        )
