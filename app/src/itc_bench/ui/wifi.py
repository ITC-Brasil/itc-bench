"""Tela Wi-Fi (ADR-018). Regras em `servicos/wifi.py`; aqui só tela.

SSID vem do cadastro e é texto livre: só em widget de texto puro. A senha nunca chega aqui.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.nucleo import wlan
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, wifi
from itc_bench.servicos.cadastros import Cadastros, Rede
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Instala no Windows as redes Wi-Fi do cadastro (Configurações › Wi-Fi), para todos os "
    "usuários do notebook. A senha nunca aparece na tela.\n\n"
    "Instalar\n"
    "1. Escolha o filtro: Esta unidade (a unidade gravada em Configurações) ou Todas.\n"
    "2. Confira a situação: Não instalada, Senha ou segurança diferente (a senha da rede mudou "
    "no cadastro), Instalada (igual).\n"
    "3. Marque as redes (o Bench já marca as que faltam ou estão diferentes) e clique em "
    "Instalar. Dá para cancelar entre uma rede e outra.\n\n"
    "A conexão é conferida na carreta, pelo próprio Windows: no escritório as redes das "
    "unidades não estão ao alcance.\n\n"
    "Notebook sem internet e sem cadastro\n"
    "Conecte por cabo, ou clique em Abrir redes do Windows e entre numa rede à mão. Depois entre "
    "no Bench e sincronize em Configurações.\n\n"
    "Cadastro inválido\n"
    "Toda rede tem senha WPA2 (8 a 63 caracteres comuns). Senha vazia, curta ou com acento não "
    "é instalada: corrija no cadastro. WPA3 não é usado (os notebooks não suportam).\n\n"
    "Sem administrador (modo de teste), a tela só mostra as redes, sem conferir a senha."
)

FILTROS = ("Esta unidade", "Todas", "Instaladas no Windows")


@dataclass(frozen=True)
class Leitura:
    linhas: tuple[wifi.Linha, ...]
    instaladas: tuple[str, ...]
    aviso: str = ""  # sem Wi-Fi, serviço parado


def ler(redes: tuple[Rede, ...], admin: bool) -> Leitura:
    try:
        with wlan.Cliente() as cliente:
            return Leitura(
                tuple(wifi.situacao(redes, cliente, admin=admin)),
                tuple(wifi.instaladas(cliente)),
            )
    except (wifi.SemWifi, wlan.ErroWlan) as erro:
        log.warning("Wi-Fi: leitura sem Wi-Fi: %s", erro)
        return Leitura((), (), "Sem adaptador Wi-Fi ou com o serviço de Wi-Fi parado.")


def abrir_redes_windows() -> None:
    """Painel de redes do próprio Windows, para a primeira conexão (sem cadastro)."""
    explorer = str(Path(executor.sistema32("explorer.exe")).parent.parent / "explorer.exe")
    executor.executar([explorer, "ms-availablenetworks:"], timeout=15)


class _Progresso(QObject):
    passo = Signal(int, int)


class PainelWifi(QWidget):
    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str | None],
    ) -> None:
        super().__init__()
        self.admin, self.obter_cadastros, self.obter_unidade = admin, obter_cadastros, obter_unidade
        self.leitura: Leitura | None = None
        self.ocupado = False
        self.cancelar_evento: threading.Event | None = None
        self.progresso = _Progresso()
        self.progresso.passo.connect(self._passo)

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.filtro = QComboBox()
        self.filtro.addItems(FILTROS)
        self.filtro.currentIndexChanged.connect(self._mostrar)
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        self.b_windows = QPushButton("Abrir redes do Windows")
        self.b_windows.clicked.connect(abrir_redes_windows)
        topo.addWidget(self.filtro)
        topo.addStretch()
        topo.addWidget(self.b_windows)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)
        self.estado = _rotulo("Lendo as redes…")
        v.addWidget(self.estado)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só leitura, sem conferir a senha."))

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Rede", "Unidade", "Categoria", "Situação"])
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.itemSelectionChanged.connect(self._botoes)
        self.tabela.itemChanged.connect(lambda _item: self._botoes())
        v.addWidget(self.tabela, 1)

        acoes = QHBoxLayout()
        self.b_instalar = QPushButton("Instalar")
        self.b_instalar.setObjectName("primario")
        self.b_instalar.clicked.connect(self._instalar)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        acoes.addWidget(self.b_instalar)
        acoes.addWidget(self.b_cancelar)
        acoes.addStretch()
        v.addLayout(acoes)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if self.leitura is None and not self.ocupado:
            self.filtro.setCurrentIndex(0 if self.obter_unidade() else 1)
            self.carregar()

    # ------------------------------------------------------------ dados

    def _redes(self) -> tuple[Rede, ...]:
        cadastros = self.obter_cadastros()
        if cadastros is None:
            return ()
        if self.filtro.currentIndex() == 0:
            return cadastros.redes_da_unidade(self.obter_unidade())
        return cadastros.redes

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo as redes…")
        cadastros = self.obter_cadastros()
        redes, admin = (cadastros.redes if cadastros else ()), self.admin
        tarefa.iniciar(lambda: ler(redes, admin), self._recebeu, self._falhou)

    def _recebeu(self, leitura: Leitura) -> None:
        self.leitura = leitura
        self._ocupar(False)
        self._mostrar()

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _mostrar(self) -> None:
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(0)
        leitura = self.leitura
        if leitura is None:
            self.tabela.blockSignals(False)
            return
        if self.filtro.currentIndex() == 2:
            self.tabela.setRowCount(len(leitura.instaladas))
            for i, nome in enumerate(leitura.instaladas):
                self.tabela.setItem(i, 0, QTableWidgetItem(nome))
                for j in (1, 2, 3):
                    self.tabela.setItem(i, j, QTableWidgetItem("" if j < 3 else "Instalada"))
        else:
            ids = {r.id for r in self._redes()}
            linhas = [x for x in leitura.linhas if x.rede.id in ids]
            self.tabela.setRowCount(len(linhas))
            for i, linha in enumerate(linhas):
                situacao = wifi.ROTULOS[linha.situacao]
                if linha.motivo:
                    situacao += f": {linha.motivo}"
                valores = (linha.rede.ssid, linha.rede.unidade, linha.rede.categoria, situacao)
                for j, valor in enumerate(valores):
                    item = QTableWidgetItem(valor)
                    item.setData(Qt.ItemDataRole.UserRole, linha.rede.id)
                    self.tabela.setItem(i, j, item)
                marca = self.tabela.item(i, 0)
                if marca is not None and linha.situacao != "invalida":
                    marca.setFlags(marca.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    padrao = linha.situacao in ("ausente", "diferente")
                    marca.setCheckState(
                        Qt.CheckState.Checked if padrao else Qt.CheckState.Unchecked
                    )
        self.tabela.blockSignals(False)
        self._texto_estado()
        self._botoes()

    def _texto_estado(self) -> None:
        leitura = self.leitura
        if leitura is not None and leitura.aviso:
            self.estado.setText(leitura.aviso)
        elif self.obter_cadastros() is None:
            self.estado.setText(
                "Sem cadastros. Conecte por cabo ou por uma rede do Windows, entre e sincronize "
                "em Configurações."
            )
        elif self.filtro.currentIndex() == 0 and not self.obter_unidade():
            self.estado.setText("A unidade da máquina não foi escolhida em Configurações.")
        else:
            self.estado.setText(f"{self.tabela.rowCount()} rede(s).")

    def _marcadas(self) -> list[Rede]:
        cadastros = self.obter_cadastros()
        if cadastros is None or self.filtro.currentIndex() == 2:
            return []
        por_id = {r.id: r for r in cadastros.redes}
        ids = []
        for i in range(self.tabela.rowCount()):
            item = self.tabela.item(i, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return [por_id[i] for i in ids if i in por_id]

    # ------------------------------------------------------------ botões

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        self.filtro.setEnabled(not ocupado)
        self._botoes()

    def _botoes(self) -> None:
        livre = self.admin and not self.ocupado
        sem_wifi = self.leitura is None or bool(self.leitura.aviso)
        quantas = len(self._marcadas())
        self.b_instalar.setText(f"Instalar {quantas} rede(s)" if quantas else "Instalar")
        self.b_instalar.setEnabled(livre and not sem_wifi and quantas > 0)

    def _iniciar_cancelavel(self) -> threading.Event:
        self.cancelar_evento = threading.Event()
        self.b_cancelar.show()
        self._ocupar(True)
        return self.cancelar_evento

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando…")

    def _fim(self) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self.b_cancelar.setText("Cancelar")

    def _passo(self, feitas: int, total: int) -> None:
        self.estado.setText(f"Instalando… {feitas}/{total}")

    # ------------------------------------------------------------ ações

    def _instalar(self) -> None:
        redes = self._marcadas()
        if not redes:
            return
        nomes = "\n".join(r.ssid for r in redes)
        if not confirmar(
            self,
            "Instalar redes",
            f"Instalar {len(redes)} rede(s) para todos os usuários do notebook?\n\n{nomes}\n\n"
            "Rede já instalada com o mesmo nome é substituída pela do cadastro.",
        ):
            return
        evento, progresso = self._iniciar_cancelavel(), self.progresso

        def rodar() -> wifi.Resumo:
            with wlan.Cliente() as cliente:
                return wifi.instalar(
                    redes,
                    cliente,
                    cancelar=evento,
                    progresso=lambda i, n: progresso.passo.emit(i, n),
                )

        tarefa.iniciar(rodar, self._instalou, self._falhou_acao)

    def _instalou(self, resumo: wifi.Resumo) -> None:
        self._fim()
        cadastros = self.obter_cadastros()
        nomes = {r.id: r.ssid for r in cadastros.redes} if cadastros else {}
        partes = [f"{len(resumo.instaladas)} instalada(s)."]
        for rid, motivo in resumo.falhas:
            partes.append(f"Falhou: {nomes.get(rid, rid)} ({motivo})")
        if resumo.puladas:
            partes.append(f"{len(resumo.puladas)} com cadastro inválido, não instalada(s).")
        if resumo.canceladas:
            partes.append(f"{len(resumo.canceladas)} cancelada(s).")
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if resumo.falhas else QMessageBox.Icon.Information,
            "Wi-Fi",
            "\n".join(partes),
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
        self.carregar()

    def _falhou_acao(self, motivo: str) -> None:
        self._fim()
        self._falhou(motivo)
        self.carregar()
