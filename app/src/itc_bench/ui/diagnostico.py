"""Telas Coleta e laudo e Histórico (ADR-015, ADR-016). Regras em `servicos/`; aqui só tela.

Texto vindo de fora (laudo, título, descrição, mensagens do coletor) só em widget de texto puro
ou no `VisorLaudo`: nunca rich text.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.nucleo.log import log
from itc_bench.servicos import api, coleta, diagnostico
from itc_bench.servicos.coleta import ROTULOS, Coleta, Modulo
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.fila import Fila, reenviar
from itc_bench.ui import tarefa
from itc_bench.ui.laudo import AVISO, VisorLaudo

# (base, token, login) da sessão online, ou None (offline ou sem login).
ObterSessao = Callable[[], tuple[str, Sensivel, str] | None]

AJUDA_COLETA = (
    "Faz o diagnóstico que antes rodava do pendrive: processos e memória, rede, erros recentes "
    "do Event Log (7 dias), disco e SMART, bateria. Depois manda ao servidor e mostra o laudo "
    "da IA.\n\n"
    "• Nova coleta leva de 1 a 5 minutos (a varredura das pastas dos usuários é a parte "
    "lenta). Cancelar para no próximo passo e guarda o que já ficou pronto.\n"
    "• Uma área com erro não para as outras.\n"
    "• O que não sai da máquina: nomes de usuário, caminhos e nomes de arquivos pessoais, "
    "senhas de Wi-Fi e dados dos cadastros. O laudo usa o nome da máquina, o modelo e os "
    "números da coleta.\n"
    "• Sem internet, a coleta fica numa fila protegida (até 10 coletas, 14 dias) e vai sozinha "
    "depois do próximo login online.\n"
    "• O laudo pode levar até 2 minutos. Se a IA não responder, a coleta já está no servidor: "
    "use Tentar laudo de novo.\n"
    "• O laudo é gerado por IA. Revise antes de abrir chamado; copie o título e a descrição com "
    "o botão Copiar."
)
AJUDA_HISTORICO = (
    "Mostra os diagnósticos anteriores desta máquina guardados no servidor (os 20 mais "
    "recentes), com quem enviou e o laudo de cada um.\n\n"
    "• Só desta máquina: o nome vem do Windows, não dá para digitar outro.\n"
    '• Coletas que ainda não foram enviadas aparecem no topo como "não enviada". Enviar '
    "pendentes manda agora; senão vão sozinhas depois do login online.\n"
    "• Sem internet, só a fila local aparece."
)


def _rotulo(texto: str = "") -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setTextFormat(Qt.TextFormat.PlainText)
    rotulo.setWordWrap(True)
    return rotulo


def _tabela(cabecalhos: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(cabecalhos))
    t.setHorizontalHeaderLabels(cabecalhos)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def destaque(m: Modulo) -> str:
    """Um ou dois números de cada área, para a lista."""
    d = m.dados
    if m.status != "ok":
        return m.erro or "erro"
    if m.nome == "processos":
        return f"memória em uso {d['memoria']['percentualEmUso']}%"
    if m.nome == "rede":
        r = d["resumo"]
        internet = "ok" if r["internetOk"] else "sem resposta"
        return f"internet {internet} · DNS {'ok' if r['dnsOk'] else 'falhou'}"
    if m.nome == "eventlog":
        return f"{d['totalGrupos']} grupo(s), {d['gruposCriticos']} crítico(s)"
    if m.nome == "disco":
        livres = [v["percentualLivre"] for v in d["volumes"]]
        return f"menor espaço livre {min(livres)}%" if livres else "sem volumes"
    if m.nome == "bateria":
        if not d["presente"]:
            return "sem bateria"
        return f"desgaste {d['desgastePercentual']}% ({d['classificacaoDesgaste']})"
    return ""


def _executar(funcao: Callable[[], Any]) -> Callable[[], tuple[str, Any]]:
    """A tarefa só devolve texto na falha; aqui o tipo da exceção chega à tela."""

    def rodar() -> tuple[str, Any]:
        try:
            return "ok", funcao()
        except (api.SemConexao, api.Recusado, api.ErroApi, api.IaFalhou, ValueError) as erro:
            return "erro", erro

    return rodar


class _Progresso(QObject):
    passo = Signal(str, object)


class PainelColeta(QWidget):
    sessao_expirada = Signal()
    fila_mudou = Signal()

    def __init__(
        self,
        obter_sessao: ObterSessao,
        fila: Fila,
        admin: bool,
        unidade: Callable[[], str | None],
        coletar: Callable[..., Coleta] = coleta.coletar,
    ) -> None:
        super().__init__()
        self.obter_sessao, self.fila, self.admin, self.unidade = obter_sessao, fila, admin, unidade
        self._coletar = coletar
        self.cancelar_evento: threading.Event | None = None
        self.coleta: Coleta | None = None
        self.corpo: dict[str, Any] | None = None
        self.espera: str | None = None  # envio_id que a tela ainda espera
        self.inicio_espera = 0.0

        self.estado = _rotulo()
        self.estado.setObjectName("modulo")
        self.botao_coletar = QPushButton("Nova coleta")
        self.botao_coletar.setObjectName("primario")
        self.botao_coletar.clicked.connect(self.nova_coleta)
        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.clicked.connect(self.cancelar)
        self.botao_cancelar.hide()
        self.botao_enviar = QPushButton("Tentar laudo de novo")
        self.botao_enviar.clicked.connect(self.enviar)
        self.botao_enviar.hide()
        topo = QHBoxLayout()
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.botao_enviar)
        topo.addWidget(self.botao_cancelar)
        topo.addWidget(self.botao_coletar)

        self.areas = _tabela(["Área", "Situação", "Duração", "Destaque"])
        self.areas.setRowCount(len(ROTULOS))
        for i, rotulo in enumerate(ROTULOS.values()):
            self.areas.setItem(i, 0, QTableWidgetItem(rotulo))
        self.areas.setMaximumHeight(200)
        self.mensagem = _rotulo()
        self.mensagem.setObjectName("vazio")

        self.aviso = _rotulo(AVISO)
        self.aviso.setObjectName("modulo")
        self.titulo = _rotulo()
        self.titulo.setObjectName("ajudaTitulo")
        self.descricao = _rotulo()
        self.botao_copiar = QPushButton("Copiar título e descrição")
        self.botao_copiar.clicked.connect(self.copiar)
        self.visor = VisorLaudo()
        self.caixa_laudo = QWidget()
        laudo = QVBoxLayout(self.caixa_laudo)
        laudo.setContentsMargins(0, 0, 0, 0)
        cab = QHBoxLayout()
        cab.addWidget(self.aviso, 1)
        cab.addWidget(self.botao_copiar)
        laudo.addLayout(cab)
        laudo.addWidget(self.titulo)
        laudo.addWidget(self.descricao)
        laudo.addWidget(self.visor, 1)
        self.caixa_laudo.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(topo)
        layout.addWidget(self.areas)
        layout.addWidget(self.mensagem)
        layout.addWidget(self.caixa_laudo, 1)

        self.progresso = _Progresso()
        self.progresso.passo.connect(self._passo)
        self.relogio = QTimer(self)
        self.relogio.setInterval(1000)
        self.relogio.timeout.connect(self._tique)
        self.atualizar_estado()

    # ---- estado

    def atualizar_estado(self) -> None:
        online = self.obter_sessao() is not None
        pendentes = len(self.fila.itens())
        partes = ["API conectada" if online else "Offline: a coleta vai para a fila"]
        if pendentes:
            partes.append(f"{pendentes} coleta(s) aguardando envio")
        if self.fila.arquivo is None:
            partes.append("sem pasta protegida: a fila some ao fechar")
        self.estado.setText(" · ".join(partes))

    # ---- coleta

    def nova_coleta(self) -> None:
        self.cancelar_evento = threading.Event()
        evento, admin, progresso = self.cancelar_evento, self.admin, self.progresso
        for i in range(len(ROTULOS)):
            for j in (1, 2, 3):
                self.areas.setItem(i, j, QTableWidgetItem(""))
        self.coleta = self.corpo = None
        self.espera = None
        self.caixa_laudo.hide()
        self.botao_enviar.hide()
        self.botao_coletar.setEnabled(False)
        self.botao_cancelar.setText("Cancelar")
        self.botao_cancelar.show()
        self.mensagem.setText("Coletando…")
        coletar = self._coletar
        tarefa.iniciar(
            lambda: coletar(
                elevado=admin,
                cancelar=evento,
                ao_progresso=lambda nome, m: progresso.passo.emit(nome, m),
            ),
            self._coletou,
            self._falhou,
        )

    def _passo(self, nome: str, modulo: Modulo | None) -> None:
        linha = list(ROTULOS).index(nome)
        if modulo is None:
            self.areas.setItem(linha, 1, QTableWidgetItem("coletando…"))
            return
        situacao = "ok" if modulo.status == "ok" else "erro"
        self.areas.setItem(linha, 1, QTableWidgetItem(situacao))
        self.areas.setItem(linha, 2, QTableWidgetItem(f"{modulo.duracao:.0f} s"))
        self.areas.setItem(linha, 3, QTableWidgetItem(destaque(modulo)))

    def cancelar(self) -> None:
        if self.cancelar_evento is not None and not self.cancelar_evento.is_set():
            self.cancelar_evento.set()
            self.mensagem.setText("Cancelando…")
            return
        if self.espera is not None and self.corpo is not None:  # cancelar a espera do laudo
            log.info("Espera do laudo %s cancelada pelo técnico.", diagnostico.curto(self.espera))
            self.espera = None
            self.relogio.stop()
            self._guardar(self.corpo)
            self._parado(
                "Espera cancelada. A coleta ficou na fila; use Buscar laudo.", "Buscar laudo"
            )

    def _coletou(self, c: Coleta) -> None:
        self.cancelar_evento = None
        self.coleta = c
        for nome in ROTULOS:
            if nome not in c.modulos:
                linha = list(ROTULOS).index(nome)
                self.areas.setItem(linha, 1, QTableWidgetItem("cancelado"))
        sessao = self.obter_sessao()
        login = sessao[2] if sessao else "-"
        try:
            self.corpo = diagnostico.montar(c, login, diagnostico.novo_envio_id(), self.unidade())
        except ValueError as erro:
            self._parado(str(erro))
            return
        if sessao is None:
            self._guardar(self.corpo)
            self._parado("Sem conexão com o servidor. A coleta ficou na fila para envio.")
            return
        self.enviar()

    def _falhou(self, motivo: str) -> None:
        self.cancelar_evento = None
        self._parado(f"Falha inesperada na coleta: {motivo}")

    # ---- envio

    def enviar(self) -> None:
        sessao = self.obter_sessao()
        if self.corpo is None:
            return
        if sessao is None:
            self._guardar(self.corpo)
            self._parado("Sem conexão com o servidor. A coleta ficou na fila para envio.")
            return
        base, token, _ = sessao
        corpo = self.corpo
        self.espera = corpo["envio_id"]
        self.inicio_espera = time.monotonic()
        self.botao_coletar.setEnabled(False)
        self.botao_enviar.hide()
        self.botao_cancelar.setText("Cancelar espera")
        self.botao_cancelar.show()
        self._tique()
        self.relogio.start()
        envio = corpo["envio_id"]
        tarefa.iniciar(
            _executar(lambda: diagnostico.enviar(base, token, corpo)),
            lambda r: self._enviou(envio, r),
            self._falhou,
        )

    def _tique(self) -> None:
        segundos = int(time.monotonic() - self.inicio_espera)
        self.mensagem.setText(f"Gerando laudo… {segundos} s (até 2 min)")

    def _enviou(self, envio: str, resultado: tuple[str, Any]) -> None:
        if envio != self.espera or self.corpo is None:
            return  # o técnico cancelou a espera; a fila cuida
        self.espera = None
        self.relogio.stop()
        estado, valor = resultado
        if estado == "ok":
            self.fila.remover(envio)
            self.fila_mudou.emit()
            self.mostrar_laudo(valor)
            self._parado("")
            return
        erro: Exception = valor
        texto = diagnostico.mensagem(erro)
        if isinstance(erro, api.IaFalhou):
            self.fila.remover(envio)  # o diagnóstico está no servidor
            self.fila_mudou.emit()
            self._parado(texto, "Tentar laudo de novo")
        elif isinstance(erro, api.Recusado) and erro.status == 401:
            self._guardar(self.corpo)
            self._parado(texto, "Tentar laudo de novo")
            self.sessao_expirada.emit()
        elif isinstance(erro, api.Recusado) and erro.status == 422:
            self.fila.remover(envio)
            self._parado(texto)
        elif isinstance(erro, api.Recusado):  # 409, 429
            self._guardar(self.corpo)
            self._parado(texto, "Tentar laudo de novo")
        else:
            self._guardar(self.corpo)
            self._parado(texto, "Tentar laudo de novo")

    def _guardar(self, corpo: dict[str, Any]) -> None:
        sessao = self.obter_sessao()
        self.fila.guardar(
            corpo, corpo["sessao"].get("coletadoPor") or (sessao[2] if sessao else "-")
        )
        self.fila_mudou.emit()
        self.atualizar_estado()

    def _parado(self, texto: str, botao: str | None = None) -> None:
        self.mensagem.setText(texto)
        self.botao_coletar.setEnabled(True)
        self.botao_cancelar.hide()
        self.botao_enviar.setVisible(botao is not None and self.corpo is not None)
        if botao:
            self.botao_enviar.setText(botao)
        self.atualizar_estado()

    def mostrar_laudo(self, laudo: diagnostico.Laudo) -> None:
        self.titulo.setText(laudo.chamado_titulo)
        self.descricao.setText(laudo.chamado_descricao)
        self.visor.mostrar(laudo.relatorio_md)
        self.caixa_laudo.show()

    def copiar(self) -> None:
        area = QGuiApplication.clipboard()
        area.setText(f"{self.titulo.text()}\n\n{self.descricao.text()}")


class PainelHistorico(QWidget):
    sessao_expirada = Signal()

    def __init__(self, obter_sessao: ObterSessao, fila: Fila) -> None:
        super().__init__()
        self.obter_sessao, self.fila = obter_sessao, fila
        self.itens: list[dict[str, Any]] = []
        self.estado = _rotulo()
        self.estado.setObjectName("modulo")
        self.botao_atualizar = QPushButton("Atualizar")
        self.botao_atualizar.clicked.connect(self.atualizar)
        self.botao_pendentes = QPushButton("Enviar pendentes")
        self.botao_pendentes.clicked.connect(self.enviar_pendentes)
        topo = QHBoxLayout()
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.botao_pendentes)
        topo.addWidget(self.botao_atualizar)
        self.tabela = _tabela(["Data", "Enviado por", "Unidade", "Confiança", "Título ou falha"])
        self.tabela.itemSelectionChanged.connect(self._selecionou)
        self.aviso = _rotulo(AVISO)
        self.aviso.setObjectName("modulo")
        self.visor = VisorLaudo()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(topo)
        layout.addWidget(self.tabela, 1)
        layout.addWidget(self.aviso)
        layout.addWidget(self.visor, 1)
        self.mostrar([], "")

    def atualizar(self) -> None:
        sessao = self.obter_sessao()
        if sessao is None:
            self.mostrar([], "Offline: histórico do servidor indisponível; só a fila local.")
            return
        base, token, _ = sessao
        nome = coleta.hostname()
        self.estado.setText("Carregando…")
        tarefa.iniciar(
            _executar(lambda: diagnostico.historico(base, token, nome)),
            self._carregou,
            lambda motivo: self.mostrar([], f"Falha ao carregar: {motivo}"),
        )

    def _carregou(self, resultado: tuple[str, Any]) -> None:
        estado, valor = resultado
        if estado == "ok":
            self.mostrar(valor, f"Máquina {coleta.hostname()}")
            return
        if isinstance(valor, api.Recusado) and valor.status == 401:
            self.sessao_expirada.emit()
        self.mostrar(
            [],
            diagnostico.mensagem(valor)
            if not isinstance(valor, api.SemConexao)
            else "Sem conexão: histórico do servidor indisponível; só a fila local.",
        )

    def mostrar(self, itens: list[dict[str, Any]], estado: str) -> None:
        pendentes = [
            {
                "recebido_em": i.criado_em.astimezone().strftime("%d/%m %H:%M"),
                "pendente": True,
                "bench_usuario": i.coletado_por,
                "unidade": i.corpo.get("unidade"),
            }
            for i in self.fila.itens()
        ]
        self.itens = pendentes + itens
        self.estado.setText(estado)
        self.botao_pendentes.setEnabled(bool(pendentes) and self.obter_sessao() is not None)
        self.tabela.setRowCount(len(self.itens))
        for linha, item in enumerate(self.itens):
            relatorio = item.get("relatorio") or {}
            if item.get("pendente"):
                ultima = "não enviada"
            elif item.get("falha"):
                ultima = f"sem laudo ({item['falha']})"
            else:
                ultima = str(relatorio.get("chamado_titulo") or "")
            valores = [
                str(item.get("recebido_em") or ""),
                str(item.get("bench_usuario") or item.get("carreta") or ""),
                str(item.get("unidade") or "—"),
                str(relatorio.get("maior_confianca") or ""),
                ultima,
            ]
            for coluna, valor in enumerate(valores):
                self.tabela.setItem(linha, coluna, QTableWidgetItem(valor))
        self.visor.mostrar("")

    def _selecionou(self) -> None:
        linhas = self.tabela.selectionModel().selectedRows()
        if not linhas:
            return
        item = self.itens[linhas[0].row()]
        self.visor.mostrar(str((item.get("relatorio") or {}).get("relatorio_md") or ""))

    def enviar_pendentes(self) -> None:
        sessao = self.obter_sessao()
        if sessao is None:
            return
        base, token, _ = sessao
        fila = self.fila
        self.estado.setText("Enviando pendentes…")
        tarefa.iniciar(
            lambda: reenviar(fila, base, token), self._reenviou, lambda m: self.atualizar()
        )

    def _reenviou(self, resultado: Any) -> None:
        if resultado.sessao_expirada:
            self.sessao_expirada.emit()
        self.atualizar()
