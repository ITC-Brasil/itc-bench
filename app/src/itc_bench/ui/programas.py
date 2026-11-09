"""Telas Programas e Remover programas (ADR-020). Regras em `servicos/programas.py` e
`servicos/desinstalar.py`; aqui só tela. Texto do cadastro e do registro só em texto puro.
"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import desinstalar as des
from itc_bench.servicos import instaladores
from itc_bench.servicos import programas as pg
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import tarefa
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Instala programas, pacotes do winget e atalhos web (Web Apps e jogos) a partir da lista "
    "Instaladores do cadastro. GLPI Agent, RustDesk e AnyDesk ficam em Acesso remoto.\n\n"
    "Instalar\n"
    "1. Filtre pelas abas ou pela busca e marque os itens.\n"
    "2. Clique em Instalar. A confirmação mostra, item a item, a origem, o modo (silencioso ou "
    "com a janela do fabricante) e se o arquivo será baixado ou já está guardado.\n"
    "3. A ordem é: instaladores, winget, atalhos web. Um item que falha não para os outros; o "
    "resumo aparece no fim.\n\n"
    "Origem\n"
    "Instalador: baixado do cadastro e conferido pelo SHA-256 antes de executar (sem SHA-256 no "
    "cadastro, o Bench calcula o dele no download e confere esse). Sem internet, "
    "selecione um instalador e use Escolher arquivo… (o Bench copia e confere).\n"
    "winget: instala do repositório oficial para todos os usuários. O winget confere o arquivo "
    "pelo manifesto dele; o Bench não tem SHA-256 desses pacotes. Pacote sem instalação para "
    "todos os usuários falha com aviso.\n"
    "Atalho web: atalho do Microsoft Edge na área de trabalho de todos os usuários, em tela "
    "cheia (quiosque, sai com Alt+F4) ou janela de app, conforme o cadastro.\n\n"
    "Situação\n"
    "Instalado, desatualizado (instala por cima), mais novo que o cadastro (não rebaixa), não "
    "instalado, ambíguo (mais de um programa com o mesmo nome) ou bloqueado (o motivo aparece "
    "na linha). Para a situação de um instalador .exe, cadastre Programa com o nome que aparece "
    "em Aplicativos instalados do Windows, ou preencha Deteccao.\n\n"
    "Cancelar\n"
    "Vale entre itens e no download. Instalador em andamento não é interrompido. Se passar do "
    'tempo, fica "ainda em execução" e os instaladores seguintes não começam.\n\n'
    "Sem administrador (modo de teste), a tela só mostra a situação."
)

AJUDA_REMOVER = (
    "Remove programas instalados, atalhos web criados pelo Bench e o Windows Terminal.\n\n"
    "1. Atualize a lista, filtre pela busca e marque os itens.\n"
    "2. A confirmação mostra o modo de cada um: silencioso, ou interativo (abre a janela do "
    "fabricante: siga até o fim).\n"
    "3. Um item que falha não para os outros.\n\n"
    "Itens que não podem ser marcados\n"
    "Protegido (cadeado): o Bench, o acesso remoto, drivers e runtimes.\n"
    "Recusado: o comando do registro usa um interpretador, não dá para separar com segurança "
    "ou o desinstalador está fora de Program Files e do Windows (ou numa pasta do Windows em "
    "que usuários gravam). Programa instalado só para um usuário roda apenas de Program Files. "
    "Remova pelo Painel de Controle, logado na conta do usuário.\n"
    "Desinstalador ausente: a entrada sobrou sem o programa; o Bench não apaga.\n\n"
    "O Bench não apaga pastas nem chaves que sobram depois da desinstalação.\n"
    "Programas instalados só para um usuário aparecem quando o perfil dele está carregado.\n"
    "Windows Terminal: removido para todos os usuários e para contas novas.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a lista."
)

ABAS = ("Todos", "Programas", "Jogos", "Atalhos web", "Instalados")
ORIGEM = {"instalador": "instalador", "winget": "winget", "webapp": "atalho web"}
SITUACAO = {
    "instalado": "instalado",
    "desatualizado": "desatualizado",
    "mais_novo": "mais novo que o cadastro",
    "nao_instalado": "não instalado",
    "ambiguo": "ambíguo",
    "desconhecido": "desconhecido",
    "bloqueado": "bloqueado",
}
MODO = {
    "silencioso": "silencioso",
    "interativo": "interativo",
    "recusado": "recusado",
    "protegido": "🔒 protegido",
    "ausente": "desinstalador ausente",
}


class _Sinais(QObject):
    texto = Signal(str)


def _tabela(colunas: tuple[str, ...]) -> QTableWidget:
    t = QTableWidget(0, len(colunas))
    t.setHorizontalHeaderLabels(list(colunas))
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return t


def _celula(texto: str, dica: str = "") -> QTableWidgetItem:
    c = QTableWidgetItem(texto)
    if dica:
        c.setToolTip(txt.dica(dica))
    return c


def _marcavel(texto: str, pode: bool) -> QTableWidgetItem:
    c = QTableWidgetItem(texto)
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    if pode:
        c.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
        c.setCheckState(Qt.CheckState.Unchecked)
    else:
        c.setFlags(flags)
    return c


class _Base(QWidget):
    """Busca, tabela, registro, cancelar e leitura ao abrir."""

    titulo = ""
    colunas: tuple[str, ...] = ()

    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.ocupado = self.lido = False
        self.cancelar_evento: threading.Event | None = None
        self.sinais = _Sinais()
        self.sinais.texto.connect(self._registrar)
        v = QVBoxLayout(self)
        self.topo = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar programa")
        self.busca.textChanged.connect(self._filtrar)
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        self.acao = QPushButton("")
        self.acao.setObjectName("primario")
        self.acao.clicked.connect(self._acao)
        self.topo.addWidget(self.busca, 1)
        self.topo.addWidget(self.atualizar)
        self.topo.addWidget(self.acao)
        v.addLayout(self.topo)
        self.estado = _rotulo("" if admin else "Sem administrador: só leitura.")
        v.addWidget(self.estado)
        self.abas: QTabBar | None = None
        self.corpo = v
        self.tabela = _tabela(self.colunas)
        self.tabela.itemChanged.connect(lambda _i: self._contar())
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)
        self.registro.setMaximumHeight(140)
        baixo = QHBoxLayout()
        self.b_cancelar = QPushButton("Cancelar depois deste passo")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        baixo.addWidget(self.b_cancelar)
        baixo.addStretch()
        self.rodape = baixo

    def _montar(self) -> None:
        self.corpo.addWidget(self.tabela, 1)
        self.corpo.addWidget(self.registro)
        self.corpo.addLayout(self.rodape)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar()

    def carregar(self) -> None:
        raise NotImplementedError

    def _acao(self) -> None:
        raise NotImplementedError

    def _filtrar(self) -> None:
        raise NotImplementedError

    def marcadas(self) -> list[int]:
        return [
            r
            for r in range(self.tabela.rowCount())
            if not self.tabela.isRowHidden(r)
            and (c := self.tabela.item(r, 0)) is not None
            and c.checkState() == Qt.CheckState.Checked
        ]

    def _contar(self) -> None:
        n = len(self.marcadas())
        self.acao.setText(f"{self.verbo} {n} selecionado(s)" if n else self.verbo)
        self.acao.setEnabled(self.admin and not self.ocupado and n > 0)

    verbo = ""

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        self.tabela.setEnabled(not ocupado)
        self._contar()

    def _registrar(self, texto: str) -> None:
        self.registro.appendPlainText(texto)

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando depois deste passo…")

    def _iniciar_lote(self) -> threading.Event:
        self.cancelar_evento = evento = threading.Event()
        self.b_cancelar.setText("Cancelar depois deste passo")
        self.b_cancelar.show()
        self._ocupar(True)
        return evento

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self._ocupar(False)

    def _terminou(self, linhas: list[str], resumo: str, erro: bool) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        for linha in linhas:
            self._registrar(linha)
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
            self.titulo,
            "\n".join([resumo, "", *linhas]),
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
        self.carregar()


# ---------------------------------------------------------------- Programas


class PainelProgramas(_Base):
    titulo = "Programas"
    colunas = ("Programa", "Origem", "Versão", "Instalada", "Situação")
    verbo = "Instalar"

    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__(admin)
        self.obter_cadastros = obter_cadastros
        self.linhas: list[pg.Linha] = []
        self.origens: dict[int, Path] = {}
        self.escolher = QPushButton("Escolher arquivo…")
        self.escolher.setToolTip("Sem internet: aponte o instalador da linha selecionada.")
        self.escolher.clicked.connect(self._escolher)
        self.topo.insertWidget(2, self.escolher)
        self.abas = QTabBar()
        for nome in ABAS:
            self.abas.addTab(nome)
        self.abas.currentChanged.connect(lambda _i: self._filtrar())
        self.corpo.insertWidget(1, self.abas)
        self.tabela.itemSelectionChanged.connect(self._contar)
        self._montar()

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        itens = pg.listar(self.obter_cadastros())
        tarefa.iniciar(lambda: pg.situacao(itens), self._recebeu, self._falhou)

    def _recebeu(self, dados: tuple[list[pg.Linha], str]) -> None:
        self.lido = True
        self.linhas, sem_winget = dados
        avisos = []
        if self.obter_cadastros() is None:
            avisos.append("Sem cadastros: conecte, entre e sincronize.")
        if sem_winget:
            avisos.append(sem_winget)
        if not self.admin:
            avisos.append("Sem administrador: só leitura.")
        self.estado.setText(" ".join(avisos))
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.linhas))
        for r, linha in enumerate(self.linhas):
            item = linha.item
            pode = linha.situacao != "bloqueado"
            self.tabela.setItem(r, 0, _marcavel(item.programa, pode))
            self.tabela.setItem(r, 1, _celula(ORIGEM.get(item.tipo, item.tipo)))
            self.tabela.setItem(r, 2, _celula(item.linha.versao))
            self.tabela.setItem(r, 3, _celula(linha.instalada))
            self.tabela.setItem(r, 4, _celula(SITUACAO[linha.situacao], linha.motivo))
        self.tabela.blockSignals(False)
        self._filtrar()
        self._ocupar(False)

    def _filtrar(self) -> None:
        aba = ABAS[self.abas.currentIndex()] if self.abas is not None else "Todos"
        busca = self.busca.text().casefold()
        for r, linha in enumerate(self.linhas):
            item = linha.item
            mostra = {
                "Todos": True,
                "Programas": item.linha.categoria == "Programas" and item.tipo != "webapp",
                "Jogos": item.linha.categoria == "Jogos",
                "Atalhos web": item.tipo == "webapp",
                "Instalados": linha.situacao in ("instalado", "desatualizado", "mais_novo"),
            }[aba]
            self.tabela.setRowHidden(r, not (mostra and busca in item.programa.casefold()))
        self._contar()

    def _contar(self) -> None:
        super()._contar()
        if not hasattr(self, "escolher"):
            return
        sel = self.tabela.currentRow()
        linha = self.linhas[sel] if 0 <= sel < len(self.linhas) else None
        self.escolher.setEnabled(
            self.admin
            and not self.ocupado
            and linha is not None
            and linha.item.tipo == "instalador"
            and linha.situacao != "bloqueado"
        )

    def _escolher(self) -> None:
        sel = self.tabela.currentRow()
        if not 0 <= sel < len(self.linhas):
            return
        item = self.linhas[sel].item
        caminho, _ = QFileDialog.getOpenFileName(
            self, f"Instalador de {item.programa}", "", f"Instalador (*{item.extensao})"
        )
        if caminho:
            self.origens[item.id] = Path(caminho)
            celula = self.tabela.item(sel, 0)
            if celula is not None:
                celula.setCheckState(Qt.CheckState.Checked)
            self._registrar(f"{item.programa}: arquivo escolhido ({Path(caminho).name}).")

    def confirmacao(self, linhas: list[pg.Linha]) -> str:
        texto = [f"Instalar {len(linhas)} item(ns)?", ""]
        for linha in pg.ordenar(x.item for x in linhas):
            if linha.tipo == "instalador":
                guardado = self.admin and instaladores.guardado(linha.linha, linha.extensao)
                origem = (
                    f"arquivo escolhido ({self.origens[linha.id].name})"
                    if linha.id in self.origens
                    else ("já guardado" if guardado else "baixar")
                )
                modo = "interativo (janela do fabricante)" if linha.interativo else "silencioso"
                detalhe = f"instalador {linha.extensao}, {modo}, {origem}, SHA-256 conferido"
            elif linha.tipo == "winget":
                detalhe = f"winget {linha.linha.identificador} (todos os usuários)"
            else:
                detalhe = f"atalho web ({linha.linha.modo}) na área de trabalho de todos"
            texto.append(f"• {linha.programa} {linha.linha.versao}: {detalhe}")
        avisos = [x for x in linhas if x.situacao in ("ambiguo", "mais_novo")]
        if avisos:
            texto += ["", "Atenção:"]
            texto += [f"• {x.item.programa}: {SITUACAO[x.situacao]}" for x in avisos]
        return "\n".join(texto)

    def _acao(self) -> None:
        escolhidas = [self.linhas[r] for r in self.marcadas()]
        if not escolhidas or not confirmar(self, "Programas", self.confirmacao(escolhidas)):
            return
        evento = self._iniciar_lote()
        emitir = self.sinais.texto.emit
        itens, origens = [x.item for x in escolhidas], dict(self.origens)
        cadastros = self.obter_cadastros()

        def rodar() -> list[pg.Resultado]:
            instaladores.limpar(cadastros)
            return pg.instalar(itens, origens=origens, avisar=emitir, cancelar=evento)

        tarefa.iniciar(rodar, self._feito, self._falhou)

    def _feito(self, resultados: Any) -> None:
        self.origens.clear()
        erro = any(r.estado in ("falha", "em_execucao") for r in resultados)
        resumo = pg.resumo(r.estado for r in resultados)
        self._terminou([r.mensagem for r in resultados], resumo, erro)


# ---------------------------------------------------------------- Remover programas


class PainelRemover(_Base):
    titulo = "Remover programas"
    colunas = ("Programa", "Versão", "Modo", "Desinstalador")
    verbo = "Remover"

    def __init__(self, admin: bool) -> None:
        super().__init__(admin)
        self.entradas: list[des.Entrada] = []
        self._montar()

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo os programas instalados…")
        tarefa.iniciar(des.listar, self._recebeu, self._falhou)

    def _recebeu(self, entradas: list[des.Entrada]) -> None:
        self.lido = True
        self.entradas = entradas
        self.estado.setText("" if self.admin else "Sem administrador: só leitura.")
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(entradas))
        for r, e in enumerate(entradas):
            nome = e.nome + (" (só um usuário)" if e.usuario else "")
            self.tabela.setItem(r, 0, _marcavel(nome, e.selecionavel))
            self.tabela.setItem(r, 1, _celula(e.versao))
            tipo = {"atalho": "atalho web", "terminal": "pacote da Store"}.get(e.tipo, "")
            self.tabela.setItem(r, 2, _celula(tipo or MODO[e.modo], e.motivo))
            self.tabela.setItem(r, 3, _celula(e.executavel))
        self.tabela.blockSignals(False)
        self._filtrar()
        self._ocupar(False)

    def _filtrar(self) -> None:
        busca = self.busca.text().casefold()
        for r, e in enumerate(self.entradas):
            self.tabela.setRowHidden(r, busca not in e.nome.casefold())
        self._contar()

    def confirmacao(self, entradas: list[des.Entrada]) -> str:
        texto = [f"Remover {len(entradas)} item(ns)?", ""]
        for e in entradas:
            if e.tipo == "programa":
                detalhe = f"{MODO[e.modo]}, {e.executavel}"
                if e.modo == "interativo":
                    detalhe += " (abre a janela do fabricante)"
            elif e.tipo == "atalho":
                detalhe = "atalho web do Bench"
            else:
                detalhe = "todos os usuários e contas novas"
            texto.append(f"• {e.nome}: {detalhe}")
        return "\n".join(texto)

    def _acao(self) -> None:
        escolhidas = [self.entradas[r] for r in self.marcadas()]
        if not escolhidas or not confirmar(self, self.titulo, self.confirmacao(escolhidas)):
            return
        evento = self._iniciar_lote()
        emitir = self.sinais.texto.emit
        tarefa.iniciar(
            lambda: des.desinstalar(escolhidas, avisar=emitir, cancelar=evento),
            self._feito,
            self._falhou,
        )

    def _feito(self, feitos: Any) -> None:
        erro = any(f.estado in ("falha", "em_execucao") for f in feitos)
        resumo = pg.resumo(f.estado for f in feitos)
        self._terminou([f.mensagem for f in feitos], resumo, erro)
