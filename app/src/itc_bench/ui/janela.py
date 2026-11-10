"""Janela principal: barra lateral com os 7 grupos e uma tela vazia por item."""

import getpass
import html
import os
import socket
import threading
from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from itc_bench import __version__
from itc_bench.nucleo import instalacao
from itc_bench.nucleo.log import definir_tecnico, log
from itc_bench.servicos import api, atualizacao, cadastros, coleta, contas, diagnostico, perfis
from itc_bench.servicos import preparacao as prep
from itc_bench.servicos.cadastros import Armazem, Cadastros, Sincronizacao
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.fila import Fila, Reenvio, reenviar
from itc_bench.servicos.login import Entrada
from itc_bench.servicos.offline import Cofre
from itc_bench.ui import tarefa, tema
from itc_bench.ui import texto as txt
from itc_bench.ui.ajuda import TEXTOS, PainelAjuda
from itc_bench.ui.aparencia import (
    AJUDA_ENERGIA,
    AJUDA_MOUSE,
    AJUDA_TELA,
    PainelEnergia,
    PainelMouse,
    PainelPapel,
)
from itc_bench.ui.atualizacao import FaixaAtualizacao
from itc_bench.ui.configuracoes import AJUDA as AJUDA_CONFIGURACOES
from itc_bench.ui.configuracoes import PainelConfiguracoes
from itc_bench.ui.contas import AJUDA as AJUDA_CONTAS
from itc_bench.ui.contas import PainelContas
from itc_bench.ui.diagnostico import AJUDA_COLETA, AJUDA_HISTORICO, PainelColeta, PainelHistorico
from itc_bench.ui.entrar import Ocioso, TelaEntrar
from itc_bench.ui.identificacao import AJUDA as AJUDA_IDENTIFICACAO
from itc_bench.ui.identificacao import PainelIdentificacao
from itc_bench.ui.inicio import PainelInicio
from itc_bench.ui.limpeza import PainelLimpeza
from itc_bench.ui.log_qt import HandlerTela
from itc_bench.ui.navegacao import GRUPOS, Item
from itc_bench.ui.politicas import AJUDA as AJUDA_POLITICAS
from itc_bench.ui.politicas import AJUDA_USB, PainelPoliticas
from itc_bench.ui.preparacao import PainelPreparacao
from itc_bench.ui.programas import AJUDA as AJUDA_PROGRAMAS
from itc_bench.ui.programas import AJUDA_REMOVER, PainelProgramas, PainelRemover
from itc_bench.ui.protecao import AJUDA as AJUDA_PROTECAO
from itc_bench.ui.protecao import PainelProtecao
from itc_bench.ui.registro import PainelRegistro
from itc_bench.ui.remoto import AJUDA as AJUDA_REMOTO
from itc_bench.ui.remoto import PainelRemoto
from itc_bench.ui.wifi import AJUDA as AJUDA_WIFI
from itc_bench.ui.wifi import PainelWifi

TEXTO_AJUDA = "Instruções desta tela em breve"
SINCRONIA_MS = 30 * 60 * 1000  # ADR-014: a cada 30 min com sessão online


class PopupAjuda(QWidget):
    """Véu escuro sobre a tela com o cartão de ajuda no canto superior direito, como no design."""

    def __init__(self, pai: QWidget, titulo: str) -> None:
        super().__init__(pai)
        self._pai = pai
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("PopupAjuda { background: rgba(26, 32, 32, 97); }")
        cartao = QFrame(self)
        cartao.setObjectName("painel")
        cartao.setFixedWidth(420)
        nome = QLabel(f"Ajuda · {titulo}")
        nome.setObjectName("ajudaTitulo")
        self.fechar = QPushButton("✕")
        self.fechar.setObjectName("ajudaFechar")
        self.fechar.setFixedSize(24, 24)
        self.fechar.clicked.connect(self.hide)
        cab = QHBoxLayout()
        cab.addWidget(nome)
        cab.addStretch()
        cab.addWidget(self.fechar)
        self.texto = QLabel(TEXTO_AJUDA)
        self.texto.setObjectName("vazio")
        self.texto.setWordWrap(True)
        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(18, 14, 18, 18)
        corpo.setSpacing(12)
        self.ver_tudo = QPushButton("Ver toda a ajuda")
        self.ver_tudo.setObjectName("link")
        corpo.addLayout(cab)
        corpo.addWidget(self.texto)
        corpo.addWidget(self.ver_tudo, 0, Qt.AlignmentFlag.AlignLeft)
        fora = QVBoxLayout(self)
        fora.setContentsMargins(28, 72, 28, 0)
        fora.addWidget(cartao, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        pai.installEventFilter(self)
        self.hide()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        if evento.type() == QEvent.Type.Resize:
            self.setGeometry(self._pai.rect())
        return False

    def mostrar(self) -> None:
        self.setGeometry(self._pai.rect())
        self.show()
        self.raise_()


class Tela(QWidget):
    def __init__(self, grupo: str, item: Item) -> None:
        super().__init__()
        self.setObjectName("principal")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        trilha = QLabel(grupo if grupo == item.titulo else f"{grupo} › {item.titulo}")
        trilha.setObjectName("trilha")
        self.titulo = QLabel(item.titulo)
        self.titulo.setObjectName("titulo")
        self.botao_ajuda = QPushButton("?")
        self.botao_ajuda.setObjectName("ajudaBotao")
        self.botao_ajuda.setFixedSize(20, 20)
        self.botao_ajuda.setCheckable(True)
        self.botao_ajuda.setToolTip("Ajuda desta tela")
        linha = QHBoxLayout()
        linha.setSpacing(10)
        linha.addWidget(self.titulo)
        linha.addWidget(self.botao_ajuda)
        linha.addStretch()
        textos = QVBoxLayout()
        textos.setSpacing(5)
        textos.addWidget(trilha)
        textos.addLayout(linha)
        topo = QFrame()
        topo.setObjectName("topo")
        topo.setFixedHeight(64)
        lt = QHBoxLayout(topo)
        lt.setContentsMargins(24, 0, 24, 0)
        lt.addLayout(textos)

        painel = QFrame()
        painel.setObjectName("painel")
        self.corpo = QVBoxLayout(painel)
        self.corpo.setContentsMargins(20, 20, 20, 20)
        self.corpo.setSpacing(10)
        vazio = QLabel("Esta tela ainda não tem conteúdo.")
        vazio.setObjectName("vazio")
        self.modulo = QLabel(f"Módulo {item.modulo}")
        self.modulo.setObjectName("modulo")
        self.corpo.addWidget(vazio)
        self.corpo.addWidget(self.modulo, 0, Qt.AlignmentFlag.AlignLeft)
        self.corpo.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(topo)
        area = QVBoxLayout()
        area.setContentsMargins(24, 20, 24, 20)
        area.addWidget(painel)
        layout.addLayout(area, 1)

        self.ajuda = PopupAjuda(self, item.titulo)
        self.ajuda.installEventFilter(self)
        self.botao_ajuda.toggled.connect(self._alternar_ajuda)

    def _alternar_ajuda(self, ligado: bool) -> None:
        if ligado:
            self.ajuda.mostrar()
        else:
            self.ajuda.hide()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        if objeto is self.ajuda and evento.type() == QEvent.Type.Hide:
            self.botao_ajuda.setChecked(False)
        return False


class Janela(QMainWindow):
    def __init__(
        self,
        handler_tela: HandlerTela,
        base: str | None = None,
        cofre: Cofre | None = None,
        maquina: str | None = None,
        armazem: Armazem | None = None,
        admin: bool = False,
        fila: Fila | None = None,
        atualizar: bool = False,
        mutex_alheio: bool = False,
    ) -> None:
        super().__init__()
        self.mutex_alheio = mutex_alheio
        # Atualização (ADR-026): só elevado, fora de --dev e --teste (que não alteram a máquina).
        self.atualizar = atualizar and admin
        self.fila = fila or Fila(None)
        self.base = base
        self.admin = admin
        self.entrada: Entrada | None = None
        # Cache dos cadastros (ADR-014): sem administrador, só em memória.
        self.armazem = armazem or Armazem(None)
        self.cadastros: Cadastros | None = self.armazem.carregar()
        self.cadastros_offline = False
        self.sem_central = False  # última sincronização: API no ar, NocoDB fora (503)
        try:
            self.unidade = cadastros.unidade_da_maquina()
        except OSError as erro:
            log.error("Unidade da máquina ilegível no registro: %s", erro)
            self.unidade = None
        self.setWindowTitle("ITC Bench")
        self.setWindowIcon(tema.icone_janela())
        self.resize(1180, 720)
        self.pilha = QStackedWidget()
        self.botoes = QButtonGroup(self)
        self.telas: dict[str, Tela] = {}
        self.nav: dict[str, QPushButton] = {}

        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(232)
        lat = QVBoxLayout(lateral)
        lat.setContentsMargins(10, 16, 10, 12)
        lat.setSpacing(2)
        lat.addWidget(self._marca())
        for indice, (grupo, itens) in enumerate(GRUPOS):
            if indice > 0:
                secao = QLabel(grupo.upper())
                secao.setObjectName("secao")
                lat.addWidget(secao)
            for item in itens:
                lat.addWidget(self._item(grupo, item))
        lat.addStretch()
        self.rodape = QLabel()
        self.rodape.setObjectName("rodape")
        lat.addWidget(self.rodape)
        self.botao_sair = QPushButton("Sair")
        self.botao_sair.setObjectName("nav")
        self.botao_sair.clicked.connect(self.sair)
        lat.addWidget(self.botao_sair)
        self._atualizar_rodape()

        self._log_na_tela(handler_tela)
        self._configuracoes()
        self._diagnostico()
        self._contas()
        self._preparar()
        self._modulo13()
        self.abrir("inicio")

        centro = QWidget()
        h = QHBoxLayout(centro)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        # Com 20 itens a barra passa de 720 px; rola em telas de 768p em vez de esticar a janela.
        rolagem = QScrollArea()
        rolagem.setObjectName("lateral")
        rolagem.setWidget(lateral)
        rolagem.setWidgetResizable(True)
        rolagem.setFixedWidth(232)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h.addWidget(rolagem)
        # Faixa da atualização (ADR-026) acima de todas as telas.
        self.faixa = FaixaAtualizacao()
        self.faixa.fechar_agora.connect(self.close)
        self.oferta: atualizacao.Oferta | None = None
        direita = QVBoxLayout()
        direita.setContentsMargins(0, 0, 0, 0)
        direita.setSpacing(0)
        direita.addWidget(self.faixa)
        direita.addWidget(self.pilha, 1)
        h.addLayout(direita, 1)
        self._atualizacao_guardada()

        # Entrar cobre tudo antes do login e no bloqueio; o conteúdo (e as tarefas) seguem vivos.
        self.entrar = TelaEntrar(base, cofre, maquina or socket.gethostname())
        self.entrar.entrou.connect(self._entrou)
        self.entrar.destravou.connect(self._destravou)
        self.raiz = QStackedWidget()
        self.raiz.addWidget(self.entrar)
        self.raiz.addWidget(centro)
        self.setCentralWidget(self.raiz)
        self.conteudo = centro

        self.ocioso = Ocioso()
        self.ocioso.venceu.connect(self.bloquear)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self.ocioso)
        self.validade = QTimer(self)
        self.validade.setSingleShot(True)
        self.validade.timeout.connect(self.sessao_expirada)
        self.sincronia = QTimer(self)
        self.sincronia.setInterval(SINCRONIA_MS)
        self.sincronia.timeout.connect(self.sincronizar)
        self.sincronia.timeout.connect(self.reenviar_fila)
        self._atualizar_rodape()
        self.entrar.verificar_api()

    def _atualizar_rodape(self) -> None:
        quem = self.entrada.rotulo_log if self.entrada else getpass.getuser()
        # Rich text por causa do <br>: login e hostname escapados.
        nome = html.escape(f"{socket.gethostname()} · {quem}")
        cad = html.escape(
            f"Unidade {self.codigo_unidade()} · "
            f"{cadastros.rotulo(self.cadastros, self.cadastros_offline)}"
        )
        self.rodape.setText(f"{nome}<br>{cad}<br>Bench {__version__}")
        if hasattr(self, "entrar"):
            self.entrar.definir_unidade(self.codigo_unidade())
        if hasattr(self, "configuracoes"):
            self.configuracoes.mostrar(
                self.cadastros,
                cadastros.rotulo(self.cadastros, self.cadastros_offline),
                self._avisos_cadastros(),
                self.unidade,
                self.entrada is not None and self.entrada.sessao is not None and bool(self.base),
            )

    def _avisos_cadastros(self) -> list[str]:
        avisos = []
        if self.cadastros is None:
            if self.armazem.aviso == "vencido":
                avisos.append(
                    "Cadastros vencidos (mais de 7 dias): conecte a máquina e sincronize."
                )
            elif self.armazem.aviso == "corrompido":
                avisos.append("A cópia dos cadastros estava danificada e foi apagada. Sincronize.")
            else:
                avisos.append("Sem cadastros nesta máquina. Entre online para sincronizar.")
        else:
            if self.sem_central:
                quando = self.cadastros.sincronizado_em.astimezone()
                avisos.append(
                    f"Servidor sem acesso aos cadastros; usando a cópia de {quando:%d/%m %H:%M}."
                )
            elif self.cadastros.defasado:
                avisos.append("O cadastro central está fora do ar; a API mandou a última cópia.")
            descartados = sum(len(v) for v in self.cadastros.descartados.values())
            if descartados:
                avisos.append(
                    f"{descartados} linha(s) com problema no cadastro central foram ignoradas "
                    "(sem nome ou com unidade inexistente). Corrija no NocoDB."
                )
        if self.armazem.arquivo is None:
            avisos.append("Sem administrador: os cadastros ficam só em memória nesta sessão.")
        return avisos

    def escolher_unidade(self, codigo: str | None) -> None:
        """Grava em HKLM (com admin) e ressincroniza filtrado; sem rede, filtra o cache."""
        if codigo == self.unidade:
            return
        self.unidade = codigo
        log.info("Unidade desta máquina: %s.", codigo or "nenhuma (bancada)")
        if self.admin:
            try:
                cadastros.gravar_unidade(codigo)
            except OSError as erro:
                log.error("Não foi possível gravar a unidade no registro: %s", erro)
        else:
            log.info("Sem administrador: a unidade vale só nesta sessão.")
        if self.entrada is not None and self.entrada.sessao is not None and self.base:
            self.sincronizar()
        else:
            self.cadastros = self.armazem.filtrar(codigo)
            self.cadastros_offline = True
        self._atualizar_rodape()

    def _configuracoes(self) -> None:
        tela = self.telas["config"]
        while tela.corpo.count():
            item = tela.corpo.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.configuracoes = PainelConfiguracoes()
        self.configuracoes.sincronizar.connect(self.sincronizar)
        self.configuracoes.unidade_escolhida.connect(self.escolher_unidade)
        tela.corpo.addWidget(self.configuracoes, 1)
        tela.ajuda.texto.setText(AJUDA_CONFIGURACOES)

    def _contas(self) -> None:
        """Contas (ADR-017): a lista é lida ao abrir; ações só com administrador."""
        tela = self.telas["contas"]
        while tela.corpo.count():
            item = tela.corpo.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.contas = PainelContas(self.admin, lambda: self.cadastros)
        tela.corpo.addWidget(self.contas, 1)
        tela.ajuda.texto.setText(AJUDA_CONTAS)

    def _preparar(self) -> None:
        """Identificação, Wi-Fi e Acesso remoto (ADR-018, ADR-019): leem ao abrir; ação só admin."""
        self.identificacao = PainelIdentificacao(self.admin, lambda: self.cadastros)
        self.wifi = PainelWifi(self.admin, lambda: self.cadastros, lambda: self.unidade)
        self.remoto = PainelRemoto(self.admin, lambda: self.cadastros, lambda: self.unidade)
        # Software (ADR-020): mesmo padrão, leem ao abrir; ação só admin.
        self.programas = PainelProgramas(self.admin, lambda: self.cadastros)
        self.remover = PainelRemover(self.admin)
        # Segurança (ADR-021): Políticas e USB pelo mesmo serviço; leem ao abrir; ação só admin.
        self.politicas = PainelPoliticas(self.admin, lambda: self.cadastros)
        self.usb = PainelPoliticas(self.admin, lambda: self.cadastros, usb=True)
        # Proteção do login e Aparência (ADR-022): leem ao abrir; ação só admin.
        self.protecao = PainelProtecao(self.admin)
        self.papel = PainelPapel(self.admin, lambda: self.cadastros)
        self.mouse = PainelMouse(self.admin, lambda: self.cadastros)
        self.energia = PainelEnergia(self.admin)
        paineis: tuple[tuple[str, QWidget, str], ...] = (
            ("id", self.identificacao, AJUDA_IDENTIFICACAO),
            ("wifi", self.wifi, AJUDA_WIFI),
            ("remoto", self.remoto, AJUDA_REMOTO),
            ("prog", self.programas, AJUDA_PROGRAMAS),
            ("remover", self.remover, AJUDA_REMOVER),
            ("gpo", self.politicas, AJUDA_POLITICAS),
            ("usb", self.usb, AJUDA_USB),
            ("protecao", self.protecao, AJUDA_PROTECAO),
            ("aparencia", self.papel, AJUDA_TELA),
            ("mouse", self.mouse, AJUDA_MOUSE),
            ("energia", self.energia, AJUDA_ENERGIA),
        )
        for chave, painel, ajuda in paineis:
            tela = self.telas[chave]
            while tela.corpo.count():
                item = tela.corpo.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.deleteLater()
            tela.corpo.addWidget(painel, 1)
            tela.ajuda.texto.setText(ajuda)

    def sessao_online(self) -> tuple[str, Sensivel, str] | None:
        if self.entrada is None or self.entrada.sessao is None or not self.base:
            return None
        return self.base, self.entrada.sessao.token, self.entrada.login

    def _diagnostico(self) -> None:
        """Coleta e laudo, Histórico (ADR-015): os painéis trocam o conteúdo vazio das telas."""
        self.coleta = PainelColeta(self.sessao_online, self.fila, self.admin, lambda: self.unidade)
        self.historico = PainelHistorico(self.sessao_online, self.fila)
        paineis: list[tuple[str, PainelColeta | PainelHistorico, str]] = [
            ("diag", self.coleta, AJUDA_COLETA),
            ("hist", self.historico, AJUDA_HISTORICO),
        ]
        for chave, painel, ajuda in paineis:
            tela = self.telas[chave]
            while tela.corpo.count():
                item = tela.corpo.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.deleteLater()
            tela.corpo.addWidget(painel, 1)
            tela.ajuda.texto.setText(ajuda)
            painel.sessao_expirada.connect(self.sessao_expirada)
        self.coleta.fila_mudou.connect(lambda: self.historico.mostrar([], ""))

    def reenviar_fila(self) -> None:
        """Depois do login online e a cada 30 min: um pendente por vez (ADR-015)."""
        sessao = self.sessao_online()
        if sessao is None or not self.fila.itens():
            return
        base, token, _ = sessao
        fila = self.fila
        tarefa.iniciar(lambda: reenviar(fila, base, token), self._reenviou, lambda _m: None)

    def _reenviou(self, resultado: Reenvio) -> None:
        log.info(
            "Fila de diagnósticos: %d enviado(s), %d pendente(s).",
            resultado.enviados,
            resultado.pendentes,
        )
        if resultado.sessao_expirada:
            self.sessao_expirada()
            return
        self.coleta.atualizar_estado()
        self.historico.atualizar()

    def codigo_unidade(self) -> str:
        """A unidade gravada só aparece se for uma Unidade ativa do cache; senão, "—"."""
        if self.cadastros is not None and self.cadastros.unidade_por_codigo(self.unidade):
            return str(self.unidade)
        return "—"

    def sincronizar(self) -> None:
        """Em segundo plano, com If-None-Match. Só com sessão online (login offline não tenta)."""
        sessao = self.entrada.sessao if self.entrada else None
        if sessao is None or not self.base or self.entrada is None:
            return
        base, token, por, unidade = self.base, sessao.token, self.entrada.login, self.unidade
        armazem = self.armazem
        # ponytail: o arquivo do cache não tem lock; sincronização e troca de unidade raramente
        # se cruzam, e a escrita é atômica (o pior caso é a última gravação vencer).
        tarefa.iniciar(
            lambda: cadastros.sincronizar(base, token, armazem, por, unidade),
            self._sincronizou,
            self._sincronizacao_falhou,
        )

    def _sincronizou(self, resultado: Sincronizacao) -> None:
        if resultado.estado == "sessao":
            self.sessao_expirada()
            return
        self.cadastros = resultado.cadastros
        self.cadastros_offline = resultado.estado not in ("ok", "igual")
        self.sem_central = resultado.estado == "sem_central"
        if self.armazem.aviso:
            log.info("Cache dos cadastros: %s.", self.armazem.aviso)
        self._atualizar_rodape()

    def _sincronizacao_falhou(self, _motivo: str) -> None:
        self.cadastros_offline = True
        self._atualizar_rodape()

    def _entrou(self, entrada: Entrada) -> None:
        anterior = self.entrada
        if anterior is not None and anterior.login != entrada.login:
            log.info("Troca de técnico: %s → %s.", anterior.login, entrada.login)
        self.entrada = entrada
        definir_tecnico(entrada.rotulo_log)
        log.info("Técnico %s entrou%s.", entrada.login, " offline" if entrada.offline else "")
        self._atualizar_rodape()
        self.validade.stop()
        if entrada.sessao is not None:
            restante = datetime.fromisoformat(entrada.sessao.expira_em) - datetime.now(UTC)
            # QTimer aceita int32 (~24 dias); a sessão é de 12 h, o teto só evita OverflowError.
            ms = int(restante.total_seconds() * 1000)
            self.validade.start(min(max(0, ms), 2**31 - 1))
            self.sincronia.start()
            self.sincronizar()
            self.reenviar_fila()
            self.procurar_atualizacao()
        else:
            self.sincronia.stop()
            self.cadastros_offline = True
            self._atualizar_rodape()
        self.coleta.atualizar_estado()
        self.historico.atualizar()
        self._mostrar_conteudo()

    def _atualizacao_guardada(self) -> None:
        """Ao abrir: só elevado (a pasta é protegida). Vale offline (assinatura local)."""
        if not self.atualizar:
            return
        try:
            if aviso := atualizacao.situacao_no_inicio():
                log.warning("%s", aviso)
                self.faixa.aviso(aviso)
            self.oferta = atualizacao.guardada()
        except OSError as erro:
            log.error("Atualização: pasta ilegível (%s).", erro)
            return
        if self.oferta is not None:
            self.faixa.mostrar(self.oferta)

    def procurar_atualizacao(self) -> None:
        """Depois do login online: consulta e baixa em segundo plano (decisão 5)."""
        sessao = self.sessao_online()
        if not self.atualizar or sessao is None:
            return
        base, token, _ = sessao

        def trabalho() -> atualizacao.Oferta | None:
            oferta = atualizacao.consultar(base, token)
            atualizacao.limpar(manter=oferta)
            if oferta is not None:
                atualizacao.baixar(base, token, oferta)
            return oferta

        tarefa.iniciar(trabalho, self._atualizacao_pronta, self._atualizacao_falhou)

    def _atualizacao_pronta(self, oferta: atualizacao.Oferta | None) -> None:
        if oferta is None:
            return
        self.oferta = oferta
        self.faixa.mostrar(oferta)

    def _atualizacao_falhou(self, motivo: str) -> None:
        log.warning("Atualização não oferecida: %s", motivo)

    def closeEvent(self, evento: QCloseEvent) -> None:
        oferta = self.oferta
        if oferta is not None and (self.faixa.confirmada or oferta.obrigatoria):
            preparando = bool(getattr(self.preparacao, "ocupado", False))
            motivo = atualizacao.motivo_para_nao_instalar(preparando)
            if motivo:
                txt.aviso(self, "ITC Bench", f"{motivo}\n\nO Bench fecha sem atualizar.")
            else:
                try:
                    atualizacao.instalar_ao_fechar(
                        oferta, os.getpid(), preparando, soltar_mutex=instalacao.soltar_mutex
                    )
                except (OSError, ValueError) as erro:
                    log.error("Atualização não disparada: %s", erro)
                    txt.aviso(self, "ITC Bench", f"A atualização não foi iniciada.\n\n{erro}")
        super().closeEvent(evento)

    def _destravou(self) -> None:
        log.info("Bench destravado por %s.", self.entrada.login if self.entrada else "-")
        self._mostrar_conteudo()

    def _mostrar_conteudo(self) -> None:
        self.raiz.setCurrentWidget(self.conteudo)
        self.ocioso.relogio.start()

    def bloquear(self) -> None:
        """15 minutos sem uso: Entrar cobre a janela; sessão e tarefas continuam (ADR-013)."""
        if self.entrada is None or self.raiz.currentWidget() is self.entrar:
            return
        log.info("Bloqueado após 15 minutos sem uso.")
        self.entrar.bloquear(self.entrada)
        self.raiz.setCurrentWidget(self.entrar)

    def sessao_expirada(self) -> None:
        """Sessão de 12 h vencida (ou 401 da API em uso): login completo; tarefas continuam."""
        log.info("Sessão expirou; login de novo.")
        self._encerrar("Sessão expirada. Entre de novo.")

    def sair(self) -> None:
        sessao, base = (self.entrada.sessao if self.entrada else None), self.base
        log.info("Logout.")
        if sessao is not None and base:
            token = sessao.token
            tarefa.iniciar(lambda: api.sair(base, token), lambda _: None, lambda _: None)
        self._encerrar("")

    def _encerrar(self, motivo: str) -> None:
        # O cache dos cadastros fica: é da máquina, não do técnico (ADR-014).
        self.entrada = None
        self.validade.stop()
        self.sincronia.stop()
        self.ocioso.relogio.stop()
        definir_tecnico(None)
        self._atualizar_rodape()
        self.coleta.atualizar_estado()
        self.entrar.reiniciar(motivo)
        self.raiz.setCurrentWidget(self.entrar)

    def abrir(self, chave: str) -> None:
        self.nav[chave].setChecked(True)
        self.pilha.setCurrentWidget(self.telas[chave])

    def _item(self, grupo: str, item: Item) -> QPushButton:
        tela = Tela(grupo, item)
        self.telas[item.chave] = tela
        self.pilha.addWidget(tela)
        botao = QPushButton(item.titulo)
        botao.setObjectName("nav")
        botao.setCheckable(True)
        botao.setIconSize(QSize(16, 16))
        botao.setIcon(tema.icone_nav(item.chave))
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.clicked.connect(lambda: self.abrir(item.chave))
        self.botoes.addButton(botao)
        self.nav[item.chave] = botao
        return botao

    def _marca(self) -> QWidget:
        simbolo = QLabel()
        simbolo.setPixmap(tema.simbolo("escuro", 28))
        itc = QLabel("ITC")
        itc.setObjectName("marcaItc")
        bench = QLabel("Bench")
        bench.setObjectName("marcaBench")
        nome = QVBoxLayout()
        nome.setSpacing(1)
        nome.addWidget(itc)
        nome.addWidget(bench)
        marca = QWidget()
        h = QHBoxLayout(marca)
        h.setContentsMargins(8, 2, 8, 16)
        h.setSpacing(6)
        h.addWidget(simbolo)
        h.addLayout(nome)
        h.addStretch()
        return marca

    def _log_na_tela(self, handler: HandlerTela) -> None:
        """Registro (ADR-023): o arquivo com filtro e exportação; linhas novas chegam ao vivo."""
        self.registro = PainelRegistro(handler, contas=self._nomes_contas)
        self.log: QPlainTextEdit = self.registro.texto
        self._trocar("registro", self.registro)

    @staticmethod
    def _nomes_contas() -> list[str]:
        """Para a máscara do Exportar; sem a lista, exporta só com computador e perfil."""
        try:
            return [c.nome for c in contas.listar().contas]
        except (contas.ErroContas, OSError) as erro:
            log.warning("Registro: contas não lidas para a máscara: %s", type(erro).__name__)
            return []

    def _trocar(self, chave: str, painel: QWidget) -> None:
        tela = self.telas[chave]
        while tela.corpo.count():
            item = tela.corpo.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        tela.corpo.addWidget(painel, 1)

    def _modulo13(self) -> None:
        """Início, Preparação completa, Limpeza e Ajuda (ADR-023); ajuda de todas as telas."""
        self.preparacao = PainelPreparacao(
            self.admin, lambda: self.cadastros, lambda: self.unidade, self._diagnosticar
        )
        self.preparacao.selo.connect(self._selo_preparacao)
        self.preparacao.selo.connect(lambda _s: self.reenviar_fila())
        self.inicio = PainelInicio(
            self.admin,
            lambda: self.cadastros,
            self.codigo_unidade,
            lambda: len(self.fila.itens()),
            lambda: self.preparacao.perfil_da_unidade()[0],
            lambda: self.preparacao.andamento,
            mutex_alheio=self.mutex_alheio,
        )
        self.inicio.abrir.connect(self._abrir_do_inicio)
        self.inicio.criticos.connect(self._selo_alertas)
        self.limpeza = PainelLimpeza(self.admin)
        self.ajuda_geral = PainelAjuda()
        for chave, painel in (
            ("inicio", self.inicio),
            ("prep", self.preparacao),
            ("limpeza", self.limpeza),
            ("ajuda", self.ajuda_geral),
        ):
            self._trocar(chave, painel)
        for chave, tela in self.telas.items():
            tela.ajuda.texto.setText(TEXTOS.get(chave, TEXTO_AJUDA))
            tela.ajuda.ver_tudo.clicked.connect(lambda _c=False, k=chave: self._ver_ajuda(k))

    def _ver_ajuda(self, chave: str) -> None:
        self.telas[chave].ajuda.hide()
        self.abrir("ajuda")
        self.ajuda_geral.ir_para(chave)

    def _abrir_do_inicio(self, chave: str) -> None:
        if chave == "limpeza":
            self.limpeza.marcar(perfis.LIMPEZA[:2])  # atalho "Limpar temporários"
        self.abrir(chave)

    def _selo_preparacao(self, selo: str) -> None:
        self.nav["prep"].setText(f"Preparação completa  {selo}")

    def _selo_alertas(self, criticos: int) -> None:
        self.nav["inicio"].setText(f"Início  ⛔ {criticos}" if criticos else "Início")
        self.nav["inicio"].setToolTip(
            txt.dica(f"{criticos} alerta(s) crítico(s)" if criticos else "")
        )

    def _diagnosticar(self, cancelar: threading.Event) -> prep.Resultado:
        """Etapa Diagnóstico: coleta e põe na fila; o envio segue pela fila (ADR-015)."""
        c = coleta.coletar(elevado=self.admin, cancelar=cancelar)
        login = self.entrada.login if self.entrada else "-"
        corpo = diagnostico.montar(c, login, diagnostico.novo_envio_id(), self.unidade)
        self.fila.guardar(corpo, login)
        return prep.Resultado("ok", "Coleta guardada na fila de envio.")
