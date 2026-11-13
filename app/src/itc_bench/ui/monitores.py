"""Aba Monitores da tela "Tela e papel de parede" (ADR-041).

Regras em `servicos/video.py`; aqui só tela. Um cartão por monitor ativo, com listas que só têm
o que o Windows informou. Depois de aplicar, o técnico tem `video.PRAZO` segundos para manter;
sem resposta (a imagem pode ter sumido), o Bench volta sozinho à situação de antes.
"""

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import video
from itc_bench.ui import tarefa, tema
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA_MONITORES = (
    "Monitores\n"
    "Ajusta cada monitor ligado ao notebook: a tela do notebook e os externos, quantos "
    "estiverem conectados.\n\n"
    "1. Ligue os monitores e clique em Atualizar.\n"
    "2. Clique num monitor do desenho (como nas Configurações do Windows) e escolha resolução, "
    "frequência, orientação e escala. As listas só têm o que o próprio monitor informou ao "
    "Windows. Dá para mudar vários monitores e aplicar tudo de uma vez.\n"
    "3. Aplicar mostra o que muda e pede confirmação.\n"
    f"4. Depois de aplicar, clique em Manter em até {video.PRAZO} segundos. Se a imagem sumir ou "
    "ninguém responder, o Bench volta sozinho como estava.\n\n"
    "Resolução, frequência e orientação valem para todas as contas. A escala vale só para a "
    "conta que está rodando o Bench: o Windows guarda a escala por conta.\n\n"
    "A resolução marcada como recomendada é a maior que o monitor informa, que no notebook é a "
    "da própria tela.\n\n"
    "Sem administrador (modo de teste), a aba só mostra a situação."
)


def _chave(r: tuple[int, int]) -> str:
    """O Qt não acha tupla com `findData`; a lista guarda "LxA"."""
    return f"{r[0]}x{r[1]}"


def _resolucao(chave: object) -> tuple[int, int] | None:
    if not isinstance(chave, str) or "x" not in chave:
        return None
    largura, altura = chave.split("x", 1)
    return int(largura), int(altura)


class MapaMonitores(QWidget):
    """Desenho dos monitores na posição e no tamanho da área de trabalho, como no Windows.

    Clique escolhe o monitor; o número grande é o mesmo do cartão. O tamanho do desenho segue a
    resolução e a orientação atuais (as que estão valendo, não as escolhidas ainda).
    """

    escolhido = Signal(int)
    MARGEM = 16.0
    VAO = 6.0  # espaço entre monitores encostados

    def __init__(self) -> None:
        super().__init__()
        self.monitores: list[video.Monitor] = []
        self.atual = 0
        self.alterados: set[int] = set()
        self.setMinimumHeight(190)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(600, 210)

    def mostrar(self, monitores: list[video.Monitor]) -> None:
        self.monitores = monitores
        self.atual = min(self.atual, max(len(monitores) - 1, 0))
        self.alterados.clear()
        self.update()

    def marcar(self, indice: int) -> None:
        if 0 <= indice < len(self.monitores):
            self.atual = indice
            self.update()

    def retangulos(self) -> list[QRectF]:
        """Retângulo de cada monitor na escala do widget."""
        if not self.monitores:
            return []
        reais = [
            QRectF(
                m.bruto.posicao[0],
                m.bruto.posicao[1],
                m.bruto.atual.largura,
                m.bruto.atual.altura,
            )
            for m in self.monitores
        ]
        tudo = reais[0]
        for r in reais[1:]:
            tudo = tudo.united(r)
        area = QRectF(self.rect()).adjusted(self.MARGEM, self.MARGEM, -self.MARGEM, -self.MARGEM)
        fator = min(area.width() / tudo.width(), area.height() / tudo.height())
        dx = area.left() + (area.width() - tudo.width() * fator) / 2
        dy = area.top() + (area.height() - tudo.height() * fator) / 2
        meio = self.VAO / 2
        return [
            QRectF(
                dx + (r.left() - tudo.left()) * fator + meio,
                dy + (r.top() - tudo.top()) * fator + meio,
                r.width() * fator - self.VAO,
                r.height() * fator - self.VAO,
            )
            for r in reais
        ]

    def paintEvent(self, _evento: QPaintEvent) -> None:
        p = tema.atual()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.fillRect(self.rect(), QColor(p.alternada))
        if not self.monitores:
            pintor.setPen(QColor(p.mute))
            pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Nenhum monitor")
            return
        for i, (m, r) in enumerate(zip(self.monitores, self.retangulos(), strict=True)):
            sel = i == self.atual
            pintor.setPen(QPen(QColor(p.destaque if sel else p.linha), 3 if sel else 1.5))
            pintor.setBrush(QColor(p.selecao if sel else p.superficie))
            pintor.drawRoundedRect(r.adjusted(1, 1, -1, -1), 6, 6)
            fonte = QFont(self.font())
            fonte.setPixelSize(max(14, min(int(r.height() * 0.42), 44)))
            fonte.setBold(True)
            pintor.setFont(fonte)
            pintor.setPen(QColor(p.selecao_texto if sel else p.texto))
            pintor.drawText(r, Qt.AlignmentFlag.AlignCenter, str(m.numero))
            pequena = QFont(self.font())
            pequena.setPixelSize(11)
            pintor.setFont(pequena)
            pintor.setPen(QColor(p.mute))
            rodape = r.adjusted(6, 0, -6, -6)
            if m.bruto.principal:
                pintor.drawText(
                    rodape, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, "principal"
                )
            if i in self.alterados:
                pintor.setPen(QColor(p.warn))
                pintor.drawText(
                    rodape, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, "alterado"
                )

    def indice_em(self, ponto: QPointF) -> int:
        for i, r in enumerate(self.retangulos()):
            if r.contains(ponto):
                return i
        return -1

    def mousePressEvent(self, evento: QMouseEvent) -> None:
        i = self.indice_em(evento.position())
        if i >= 0:
            self.marcar(i)
            self.escolhido.emit(i)


class _Cartao(QFrame):
    """Um monitor: listas de resolução, frequência, orientação e escala."""

    mudou = Signal()

    def __init__(self, monitor: video.Monitor, admin: bool) -> None:
        super().__init__()
        self.setObjectName("cartao")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.monitor = monitor
        b = monitor.bruto
        v = QVBoxLayout(self)
        v.addWidget(_rotulo(monitor.nome))
        atual = monitor.atual_paisagem()
        escala = f", escala {b.escala.atual}%" if b.escala else ""
        v.addWidget(
            _rotulo(
                f"Agora: {atual[0]}x{atual[1]}, {b.atual.frequencia} Hz, "
                f"{video.ORIENTACOES.get(b.orientacao, '?').lower()}{escala}."
            )
        )
        form = QFormLayout()
        self.resolucao = QComboBox()
        recomendada = monitor.recomendada()
        for r in monitor.resolucoes():
            rotulo = f"{r[0]} x {r[1]}" + (" (recomendada)" if r == recomendada else "")
            self.resolucao.addItem(rotulo, _chave(r))
        self.resolucao.setCurrentIndex(max(self.resolucao.findData(_chave(atual)), 0))
        self.frequencia = QComboBox()
        self.orientacao = QComboBox()
        for k, nome in video.ORIENTACOES.items():
            self.orientacao.addItem(nome, k)
        self.orientacao.setCurrentIndex(max(self.orientacao.findData(b.orientacao), 0))
        self.escala = QComboBox()
        if b.escala is None:
            self.escala.addItem("não informada pelo Windows", None)
            self.escala.setEnabled(False)
        else:
            for p in b.escala.opcoes:
                rotulo = f"{p}%" + (" (recomendada)" if p == b.escala.recomendada else "")
                self.escala.addItem(rotulo, p)
            self.escala.setCurrentIndex(max(self.escala.findData(b.escala.atual), 0))
        self.resolucao.currentIndexChanged.connect(self._frequencias)
        self._frequencias()
        form.addRow("Resolução", self.resolucao)
        form.addRow("Frequência", self.frequencia)
        form.addRow("Orientação", self.orientacao)
        form.addRow("Escala", self.escala)
        v.addLayout(form)
        for c in (self.resolucao, self.frequencia, self.orientacao):
            c.setEnabled(admin)
        if b.escala is not None:
            self.escala.setEnabled(admin)
        for c in (self.resolucao, self.frequencia, self.orientacao, self.escala):
            c.currentIndexChanged.connect(self.mudou)

    def alterado(self) -> bool:
        return bool(video.mudancas([self.monitor], [self.escolha()]))

    def _frequencias(self) -> None:
        res = _resolucao(self.resolucao.currentData())
        anterior = self.frequencia.currentData()
        self.frequencia.clear()
        if res is None:
            return
        for f in self.monitor.frequencias(*res):
            self.frequencia.addItem(f"{f} Hz", f)
        alvo = anterior if anterior is not None else self.monitor.bruto.atual.frequencia
        i = self.frequencia.findData(alvo)
        if i < 0:
            i = self.frequencia.findData(self.monitor.bruto.atual.frequencia)
        self.frequencia.setCurrentIndex(max(i, 0))

    def escolha(self) -> video.Escolha:
        return video.Escolha(
            self.monitor.dispositivo,
            resolucao=_resolucao(self.resolucao.currentData()),
            frequencia=self.frequencia.currentData(),
            orientacao=self.orientacao.currentData(),
            escala=self.escala.currentData(),
        )


class PainelMonitores(QWidget):
    titulo = "Monitores"

    def __init__(
        self, admin: bool, abrir_video: Callable[[], None] | None = None, prazo: int = video.PRAZO
    ) -> None:
        super().__init__()
        self.admin = admin
        self.prazo = prazo
        self.monitores: list[video.Monitor] = []
        self.cartoes: list[_Cartao] = []
        self.ocupado = self.lido = False

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.estado = _rotulo("")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só leitura."))

        # Como nas Configurações do Windows: desenho dos monitores e, embaixo, o escolhido.
        self.mapa = MapaMonitores()
        self.mapa.escolhido.connect(self.escolher)
        v.addWidget(self.mapa)
        self.pilha = QStackedWidget()
        v.addWidget(self.pilha, 1)

        acoes = QHBoxLayout()
        self.b_aplicar = QPushButton("Aplicar")
        self.b_aplicar.setObjectName("primario")
        self.b_aplicar.clicked.connect(self._aplicar)
        acoes.addWidget(self.b_aplicar)
        if abrir_video is not None:
            self.b_windows = QPushButton("Abrir configurações de vídeo")
            self.b_windows.clicked.connect(abrir_video)
            acoes.addWidget(self.b_windows)
        acoes.addStretch()
        v.addLayout(acoes)
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)
        self.registro.setMaximumHeight(120)
        v.addWidget(self.registro)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar()

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo os monitores…")
        tarefa.iniciar(video.ler, self._recebeu, self._falhou)

    def _recebeu(self, monitores: list[video.Monitor]) -> None:
        self.monitores, self.lido = monitores, True
        for c in self.cartoes:
            self.pilha.removeWidget(c)
            c.deleteLater()
        self.cartoes = [_Cartao(m, self.admin) for m in monitores]
        for i, c in enumerate(self.cartoes):
            self.pilha.addWidget(c)
            c.mudou.connect(lambda i=i: self._marcar_alterado(i))
        self.mapa.mostrar(monitores)
        if self.cartoes:
            self.escolher(self.mapa.atual)
        n = len(monitores)
        self.estado.setText(
            f"{n} monitor{'es' if n != 1 else ''} conectado{'s' if n != 1 else ''}."
            if n
            else "Nenhum monitor ativo encontrado."
        )
        self._ocupar(False)

    def escolher(self, indice: int) -> None:
        if 0 <= indice < len(self.cartoes):
            self.mapa.marcar(indice)
            self.pilha.setCurrentIndex(indice)

    def _marcar_alterado(self, indice: int) -> None:
        if self.cartoes[indice].alterado():
            self.mapa.alterados.add(indice)
        else:
            self.mapa.alterados.discard(indice)
        self.mapa.update()

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pode = self.admin and not ocupado and bool(self.cartoes)
        self.b_aplicar.setEnabled(pode)
        if not self.admin:
            self.b_aplicar.setToolTip("Precisa de administrador.")
        self.atualizar.setEnabled(not ocupado)

    def escolhas(self) -> list[video.Escolha]:
        return [c.escolha() for c in self.cartoes]

    def _aplicar(self) -> None:
        escolhas = self.escolhas()
        linhas = video.mudancas(self.monitores, escolhas)
        if not linhas:
            self.estado.setText("Nada mudou.")
            return
        texto = "\n".join(linhas) + (
            f"\n\nDepois de aplicar, você terá {self.prazo} segundos para manter. Sem resposta, "
            "o Bench volta como estava."
        )
        if not confirmar(self, f"{self.titulo} — aplicar", texto):
            return
        self._ocupar(True)
        self.estado.setText("Aplicando…")
        tarefa.iniciar(lambda: video.aplicar(escolhas), self._aplicado, self._falhou)

    def _aplicado(self, resultado: tuple[list[video.Feito], video.Antes]) -> None:
        feitos, antes = resultado
        self.registro.appendPlainText(
            "\n".join(f"{f.item}: {f.mensagem}" for f in feitos) or "Nada a fazer."
        )
        if not any(f.ok for f in feitos):
            self.estado.setText("Nada foi aplicado.")
            self.carregar()
            return
        if self.manter():
            self.estado.setText("Mantido.")
            self.registro.appendPlainText("Mantido pelo técnico.")
            self.carregar()
        else:
            self.estado.setText("Voltando como estava…")
            tarefa.iniciar(lambda: video.desfazer(antes), self._desfeito, self._falhou)

    def manter(self) -> bool:
        """Pergunta com contagem; sem resposta no prazo, é "Voltar"."""
        caixa = QMessageBox(QMessageBox.Icon.Question, self.titulo, "", parent=self)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        manter = caixa.addButton("Manter", QMessageBox.ButtonRole.AcceptRole)
        voltar = caixa.addButton("Voltar como estava", QMessageBox.ButtonRole.RejectRole)
        caixa.setDefaultButton(voltar)
        restante = [self.prazo]

        def contar() -> None:
            caixa.setText(f"Manter estas configurações? Volta sozinho em {restante[0]} s.")
            if restante[0] <= 0:
                caixa.reject()
                return
            restante[0] -= 1

        relogio = QTimer(caixa)
        relogio.timeout.connect(contar)
        contar()
        relogio.start(1000)
        caixa.exec()
        relogio.stop()
        return caixa.clickedButton() is manter

    def _desfeito(self, feitos: list[video.Feito]) -> None:
        self.registro.appendPlainText(
            "Voltou: " + ("; ".join(f"{f.item}: {f.mensagem}" for f in feitos) or "nada a fazer")
        )
        self.carregar()
