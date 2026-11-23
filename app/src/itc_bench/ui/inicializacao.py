"""Tela Inicialização (ADR-075). Leitura e regras em `servicos/inicializacao.py`; aqui só tela."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import inicializacao as ini
from itc_bench.ui import tarefa
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Mostra o que abre sozinho quando o notebook liga ou quando alguém entra numa conta, e deixa "
    "desligar o que não precisa. Desligar não desinstala nem apaga nada.\n\n"
    "Programas\n"
    "Mostra só o que está ligado na inicialização e não tem função num notebook de aluno: "
    "OneDrive, Teams, Copilot, Edge, OneNote, Xbox, Dispositivos móveis, Widgets, jogos como "
    "Riot (Vanguard), Roblox e Steam, "
    "Discord, Spotify, Tailscale e semelhantes. A busca cobre o registro (Run) e a pasta "
    "Inicializar da máquina e de cada conta (também das contas sem sessão aberta), os apps da "
    "Loja e as tarefas "
    "agendadas de logon ou boot. A coluna Onde diz se vale para todas as contas ou para uma só. "
    "O resto (drivers, Office, atualizadores e o que já está desligado) não aparece.\n"
    "1. A leitura é feita ao abrir a tela; Ler de novo repete.\n"
    "2. Todos vêm marcados. Desmarque o que a escola usa (por exemplo, OneDrive).\n"
    "3. Desligar marcados pede confirmação e desliga do mesmo jeito que o Gerenciador de "
    "Tarefas: o item fica Desligado e volta a qualquer hora em Gerenciador de Tarefas › "
    "Aplicativos de inicialização (tarefas agendadas: Agendador de Tarefas › Habilitar).\n"
    "Nunca aparecem nem são desligados: AnyDesk, RustDesk, GLPI Agent, "
    "a central de segurança do Windows, o áudio Realtek e o próprio ITC Bench.\n\n"
    "Na Manutenção\n"
    "A etapa 5. Desligar inicialização de apps não necessários, da Manutenção, faz o mesmo "
    "Desligar marcados de uma vez, depois de encerrar a sessão das outras contas; o que você "
    "desmarcar aqui fica ligado também lá.\n\n"
    "Serviços\n"
    "Serviços automáticos de outros fabricantes (fora da pasta do Windows), se estão rodando e o "
    "caminho. Só leitura.\n\n"
    "Tempo de inicialização\n"
    "Os últimos boots registrados pelo Windows: quanto levou para ligar e quanto levou depois de "
    "entrar na conta. Abaixo, o que mais atrasou a inicialização nos últimos 30 dias, do maior "
    "atraso para o menor. Boot acima de 1 minuto merece olhar.\n\n"
    "Sem administrador (modo de teste), mostra só o que dá para ler e não desliga."
    "\n\nModelo de configuração\n"
    "Com um modelo importado (Sistema › Importar configurações), os itens sem função que "
    "foram desmarcados no modelo vêm desmarcados aqui (ficam ligados)."
)

_COLUNAS = ["Item", "Onde", "Tipo", "Situação"]


def _data(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


class PainelInicializacao(QWidget):
    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.ocupado = self.lido = False
        self.leitura: ini.Leitura | None = None
        self.manter: frozenset[str] = frozenset()  # modelo (ADR-076): sem função, mas fica
        v = QVBoxLayout(self)
        self.estado = _rotulo("")
        v.addWidget(self.estado)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só a leitura, sem desligar."))
        self.abas = QTabWidget()
        v.addWidget(self.abas, 1)

        programas = QWidget()
        vp = QVBoxLayout(programas)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(_COLUNAS)
        self.arvore.setColumnWidth(0, 300)
        self.arvore.setColumnWidth(1, 150)
        self.arvore.setColumnWidth(2, 130)
        self.arvore.setRootIsDecorated(False)
        self.arvore.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        vp.addWidget(self.arvore, 1)
        acoes = QHBoxLayout()
        self.b_ler = QPushButton("Ler de novo")
        self.b_ler.clicked.connect(self.ler)
        self.b_desligar = QPushButton("Desligar marcados")
        self.b_desligar.setObjectName("primario")
        self.b_desligar.clicked.connect(self._desligar)
        acoes.addStretch()
        acoes.addWidget(self.b_ler)
        acoes.addWidget(self.b_desligar)
        vp.addLayout(acoes)
        self.abas.addTab(programas, "Programas")

        self.servicos = QTreeWidget()
        self.servicos.setHeaderLabels(["Serviço", "Situação", "Caminho"])
        self.servicos.setColumnWidth(0, 300)
        self.servicos.setColumnWidth(1, 100)
        self.servicos.setRootIsDecorated(False)
        self.abas.addTab(self.servicos, "Serviços")

        tempo = QWidget()
        vt = QVBoxLayout(tempo)
        self.resumo_boot = _rotulo("")
        vt.addWidget(self.resumo_boot)
        self.boots = QTreeWidget()
        self.boots.setHeaderLabels(["Data", "Até a tela de entrada", "Depois de entrar"])
        self.boots.setColumnWidth(0, 160)
        self.boots.setColumnWidth(1, 170)
        self.boots.setRootIsDecorated(False)
        vt.addWidget(self.boots, 1)
        vt.addWidget(_rotulo("O que mais atrasou a inicialização (últimos 30 dias)"))
        self.atrasos = QTreeWidget()
        self.atrasos.setHeaderLabels(["Item", "Atraso", "Data"])
        self.atrasos.setColumnWidth(0, 340)
        self.atrasos.setColumnWidth(1, 100)
        self.atrasos.setRootIsDecorated(False)
        vt.addWidget(self.atrasos, 2)
        self.abas.addTab(tempo, "Tempo de inicialização")
        self._ocupar(False)

    # ------------------------------------------------------------ leitura

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.ler()

    def ler(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a inicialização de todas as contas… (pode levar um minuto)")
        tarefa.iniciar(ini.ler, self._leu, self._falhou)

    def _leu(self, leitura: ini.Leitura) -> None:
        self.leitura = leitura
        self.lido = True
        self._mostrar_programas(leitura.itens)
        self._mostrar_servicos(leitura.servicos)
        self._mostrar_tempo(leitura.boots, leitura.atrasos)
        inuteis = sum(1 for i in leitura.itens if i.ativo and i.recomendado)
        self.estado.setText(
            f"{inuteis} item(ns) sem função atrasando a inicialização."
            if inuteis
            else "Nada sem função na inicialização."
        )
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _mostrar_programas(self, itens: tuple[ini.Item, ...]) -> None:
        """Só o que está ligado e não tem função (ADR-075): o resto não aparece."""
        self.arvore.blockSignals(True)
        self.arvore.clear()
        inuteis = [i for i in itens if i.ativo and i.recomendado]
        for i in sorted(inuteis, key=lambda i: (i.titulo.casefold(), i.onde.casefold())):
            linha = QTreeWidgetItem([i.titulo, i.onde, ini.TIPOS[i.tipo], "ligado"])
            linha.setData(0, Qt.ItemDataRole.UserRole, i)
            linha.setToolTip(0, txt.dica(i.comando))
            fica = i.titulo in self.manter
            linha.setCheckState(0, Qt.CheckState.Unchecked if fica else Qt.CheckState.Checked)
            self.arvore.addTopLevelItem(linha)
        self.arvore.blockSignals(False)

    def _mostrar_servicos(self, servicos: tuple[ini.Servico, ...]) -> None:
        self.servicos.clear()
        for s in sorted(servicos, key=lambda s: (not s.rodando, s.nome.casefold())):
            linha = QTreeWidgetItem([s.nome, "rodando" if s.rodando else "parado", s.comando])
            linha.setToolTip(2, txt.dica(s.comando))
            self.servicos.addTopLevelItem(linha)

    def _mostrar_tempo(self, boots: tuple[ini.Boot, ...], atrasos: tuple[ini.Atraso, ...]) -> None:
        self.boots.clear()
        for b in boots:
            self.boots.addTopLevelItem(
                QTreeWidgetItem([_data(b.data), ini.segundos(b.boot_ms), ini.segundos(b.pos_ms)])
            )
        self.atrasos.clear()
        for a in atrasos:
            self.atrasos.addTopLevelItem(
                QTreeWidgetItem([a.nome, ini.segundos(a.atraso_ms), _data(a.data)])
            )
        if boots:
            ultimo = boots[0]
            self.resumo_boot.setText(
                f"Último boot: {ini.segundos(ultimo.boot_ms)} até a tela de entrada e "
                f"{ini.segundos(ultimo.pos_ms)} depois de entrar."
            )
        elif self.admin:
            self.resumo_boot.setText("O Windows não registrou tempos de boot.")
        else:
            self.resumo_boot.setText("Os tempos de boot só aparecem com administrador.")

    # ------------------------------------------------------------ desligar

    def marcacoes(self) -> tuple[str, ...]:
        """Os sem função que o técnico desmarcou (ficam ligados), para o modelo (ADR-076)."""
        if not self.lido:
            return tuple(sorted(self.manter))
        marcados = {i.titulo for i in self.marcados()}
        todos = set()
        for n in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(n)
            item = linha.data(0, Qt.ItemDataRole.UserRole) if linha is not None else None
            if isinstance(item, ini.Item):
                todos.add(item.titulo)
        return tuple(sorted((todos - marcados) | (self.manter - todos)))

    def aplicar_modelo(self, manter: tuple[str, ...]) -> None:
        self.manter = frozenset(manter)
        if self.leitura is not None and not self.ocupado:
            self._mostrar_programas(self.leitura.itens)
            self._ocupar(False)

    def marcados(self) -> list[ini.Item]:
        saida = []
        for n in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(n)
            if linha is not None and linha.checkState(0) == Qt.CheckState.Checked:
                item = linha.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(item, ini.Item) and item.ativo and not item.essencial:
                    saida.append(item)
        return saida

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        n = len(self.marcados())
        self.b_desligar.setText(f"Desligar marcados ({n})" if n else "Desligar marcados")
        self.b_desligar.setEnabled(self.admin and not ocupado and bool(n))
        if not self.admin:
            self.b_desligar.setToolTip("Precisa de administrador.")
        self.b_ler.setEnabled(not ocupado)

    def _desligar(self) -> None:
        itens = self.marcados()
        if not itens:
            return
        linhas = "\n".join(f"• {i.titulo} ({i.onde})" for i in itens[:25])
        if len(itens) > 25:
            linhas += f"\n• e mais {len(itens) - 25}"
        if not confirmar(
            self,
            "Inicialização",
            f"Desligar {len(itens)} item(ns) da inicialização?\n\n{linhas}\n\n"
            "Nada é desinstalado. Volta em Gerenciador de Tarefas › Aplicativos de inicialização.",
        ):
            return
        self._ocupar(True)
        self.estado.setText("Desligando…")
        tarefa.iniciar(lambda: ini.desligar(itens), self._desligou, self._falhou)

    def _desligou(self, resultados: list[ini.Resultado]) -> None:
        ruins = [r for r in resultados if not r.ok]
        self.estado.setText(
            f"{len(resultados) - len(ruins)} item(ns) desligado(s)."
            + (f" {len(ruins)} não." if ruins else "")
            + " Vale a partir do próximo boot ou da próxima entrada na conta."
        )
        self._ocupar(False)
        if ruins:
            caixa = QMessageBox(
                QMessageBox.Icon.Warning,
                "Inicialização",
                "\n".join(f"{r.item.titulo} ({r.item.onde}): {r.motivo}" for r in ruins),
                parent=self,
            )
            caixa.setTextFormat(Qt.TextFormat.PlainText)
            caixa.open()
        self.ler()
