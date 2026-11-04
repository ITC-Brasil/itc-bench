"""Tela Entrar (docs/design, Tela 0) e o relógio de 15 minutos parado (ADR-013)."""

import platform
import socket
import winreg

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench import __version__
from itc_bench.nucleo.log import log
from itc_bench.servicos import api, login
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.offline import Cofre, OfflineRecusado
from itc_bench.ui import tarefa, tema

OCIOSO_MS = 15 * 60 * 1000
TEXTO_AJUDA_ENTRAR = (
    "Entre com seu usuário e senha do GLPI. Só usuários com o perfil de técnico entram.\n\n"
    "Sem internet, entra quem já fez login online nesta máquina nos últimos 7 dias.\n\n"
    "Depois de 15 minutos sem uso o Bench volta para esta tela; o mesmo técnico destrava com a "
    "senha, mesmo sem rede. Tarefas em andamento continuam."
)
# Tecla, clique e roda contam como uso; movimento do mouse não (ADR-013).
EVENTOS_DE_USO = {QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel}


def versao_windows() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        ) as chave:
            produto = str(winreg.QueryValueEx(chave, "ProductName")[0])
            versao = str(winreg.QueryValueEx(chave, "DisplayVersion")[0])
    except OSError:
        return f"Windows {platform.release()}"
    # O registro do Windows 11 ainda diz "Windows 10" no ProductName; o build decide.
    if int(platform.version().split(".")[-1]) >= 22000:
        produto = produto.replace("Windows 10", "Windows 11")
    return f"{produto} {versao}"


class Ocioso(QObject):
    """Filtro na QApplication: cada uso reinicia o relógio; ao vencer emite `venceu`."""

    venceu = Signal()

    def __init__(self, intervalo_ms: int = OCIOSO_MS) -> None:
        super().__init__()
        self.relogio = QTimer(self)
        self.relogio.setSingleShot(True)
        self.relogio.setInterval(intervalo_ms)
        self.relogio.timeout.connect(self.venceu)

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:
        if evento.type() in EVENTOS_DE_USO and self.relogio.isActive():
            self.relogio.start()
        return False


class TelaEntrar(QWidget):
    entrou = Signal(object)  # login.Entrada
    destravou = Signal()

    def __init__(self, base: str | None, cofre: Cofre | None, maquina: str) -> None:
        super().__init__()
        self.base, self.cofre, self.maquina = base, cofre, maquina
        self.atual: login.Entrada | None = None  # preenchido quando é bloqueio, não login
        self.setObjectName("principal")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        lado = QFrame()
        lado.setObjectName("entrarLado")
        lado.setFixedWidth(440)
        simbolo = QLabel()
        simbolo.setPixmap(tema.simbolo("escuro", 58))
        itc = QLabel("ITC")
        itc.setObjectName("entrarItc")
        bench = QLabel("Bench")
        bench.setObjectName("entrarBench")
        nome = QVBoxLayout()
        nome.setSpacing(5)
        nome.addWidget(itc)
        nome.addWidget(bench)
        marca = QHBoxLayout()
        marca.setSpacing(8)
        marca.addWidget(simbolo)
        marca.addLayout(nome)
        marca.addStretch()
        self.rodape = QLabel()
        self.rodape.setObjectName("entrarRodape")
        lat = QVBoxLayout(lado)
        lat.setContentsMargins(40, 40, 40, 40)
        lat.addLayout(marca)
        lat.addStretch()
        lat.addWidget(self.rodape)

        self.titulo = QLabel("Entrar")
        self.titulo.setObjectName("entrarTitulo")
        self.botao_ajuda = QPushButton("?")
        self.botao_ajuda.setObjectName("ajudaBotao")
        self.botao_ajuda.setFixedSize(20, 20)
        self.botao_ajuda.setCheckable(True)
        self.botao_ajuda.setToolTip("Ajuda desta tela")
        self.ajuda = QLabel(TEXTO_AJUDA_ENTRAR)
        self.ajuda.setObjectName("vazio")
        self.ajuda.setWordWrap(True)
        self.ajuda.hide()
        self.botao_ajuda.toggled.connect(self.ajuda.setVisible)
        cab = QHBoxLayout()
        cab.setSpacing(10)
        cab.addWidget(self.titulo)
        cab.addWidget(self.botao_ajuda)
        cab.addStretch()
        self.subtitulo = QLabel("Use seu usuário e senha do GLPI. Acesso só para técnicos.")
        self.subtitulo.setObjectName("entrarSub")
        self.usuario = QLineEdit()
        self.usuario.setObjectName("campo")
        self.usuario.setPlaceholderText("Usuário")
        self.senha = QLineEdit()
        self.senha.setObjectName("campo")
        self.senha.setPlaceholderText("Senha")
        self.senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.botao = QPushButton("Entrar")
        self.botao.setObjectName("primario")
        self.botao.setDefault(True)
        self.mensagem = QLabel()
        self.mensagem.setObjectName("entrarErro")
        self.mensagem.setWordWrap(True)
        self.estado = QLabel()
        self.estado.setObjectName("entrarEstado")
        nota = QLabel("Sem internet, entra quem já fez login nesta máquina nos últimos 7 dias.")
        nota.setObjectName("entrarNota")
        nota.setWordWrap(True)

        rotulo_usuario = QLabel("Usuário")
        rotulo_usuario.setObjectName("rotulo")
        rotulo_senha = QLabel("Senha")
        rotulo_senha.setObjectName("rotulo")
        form = QWidget()
        form.setFixedWidth(360)
        f = QVBoxLayout(form)
        f.setSpacing(8)
        f.addLayout(cab)
        f.addWidget(self.subtitulo)
        f.addWidget(self.ajuda)
        f.addSpacing(8)
        f.addWidget(rotulo_usuario)
        f.addWidget(self.usuario)
        f.addWidget(rotulo_senha)
        f.addWidget(self.senha)
        f.addSpacing(8)
        f.addWidget(self.botao)
        f.addWidget(self.mensagem)
        f.addWidget(self.estado)
        f.addWidget(nota)
        centro = QHBoxLayout()
        centro.addStretch()
        centro.addWidget(form)
        centro.addStretch()
        direita = QVBoxLayout()
        direita.addStretch()
        direita.addLayout(centro)
        direita.addStretch()

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(lado)
        h.addLayout(direita, 1)

        self.botao.clicked.connect(self.enviar)
        self.senha.returnPressed.connect(self.enviar)
        self.usuario.returnPressed.connect(self.senha.setFocus)
        self._rodape("verificando…")

    def _rodape(self, estado_api: str) -> None:
        # Unidade vem do cadastro (Módulo 05); até lá, "—".
        self.rodape.setText(
            f"{socket.gethostname()} · Unidade —<br>{versao_windows()}<br>"
            f"Bench {__version__}<br>API: {estado_api}"
        )

    def verificar_api(self) -> None:
        if not self.base:
            self._mostrar_estado("API não configurada", "erro")
            self._rodape("não configurada")
            return
        base = self.base

        def pronto(ok: object) -> None:
            texto = "conectada" if ok else "sem conexão"
            self._mostrar_estado(f"● Servidor {texto}", "ok" if ok else "aviso")
            self._rodape(texto)

        def falhou(_motivo: str) -> None:
            self._mostrar_estado("● Servidor sem conexão · login offline", "aviso")
            self._rodape("sem conexão")

        tarefa.iniciar(lambda: api.saude(base), pronto, falhou)

    def _mostrar_estado(self, texto: str, tipo: str) -> None:
        if self.cofre is None and tipo != "ok":
            texto += " · offline indisponível sem administrador"
        self.estado.setText(texto)
        self.estado.setProperty("tipo", tipo)
        self.estado.style().polish(self.estado)

    def bloquear(self, atual: login.Entrada) -> None:
        self.atual = atual
        self.titulo.setText("Bloqueado")
        self.subtitulo.setText(
            f"{atual.nome} · entre de novo para continuar. Tarefas em andamento seguem."
        )
        self.usuario.setText(atual.login)
        self._limpar()
        self.senha.setFocus()

    def reiniciar(self, motivo: str = "") -> None:
        self.atual = None
        self.titulo.setText("Entrar")
        self.subtitulo.setText("Use seu usuário e senha do GLPI. Acesso só para técnicos.")
        self.usuario.clear()
        self._limpar()
        self.mensagem.setText(motivo)
        self.usuario.setFocus()

    def _limpar(self) -> None:
        self.senha.clear()
        self.mensagem.clear()
        self.botao.setEnabled(True)

    def enviar(self) -> None:
        usuario = self.usuario.text().strip()
        if not usuario or not self.senha.text():
            self.mensagem.setText("Informe usuário e senha.")
            return
        # A senha sai do campo na hora e só existe como Sensivel (ADR-011).
        senha = Sensivel(self.senha.text())
        self.senha.clear()
        self.botao.setEnabled(False)
        self.mensagem.setText("Conferindo…")
        atual, base, cofre, maquina = self.atual, self.base, self.cofre, self.maquina

        def trabalho() -> object:
            # Recusas esperadas voltam como valor: não são falha do programa (sem traceback).
            try:
                if atual is not None and login.destravar(atual, usuario, senha, cofre):
                    return None
                return login.entrar(usuario, senha, base=base, maquina=maquina, cofre=cofre)
            except (api.Recusado, api.SemConexao, api.ErroApi, OfflineRecusado) as erro:
                return erro

        tarefa.iniciar(trabalho, self._pronto, self._falhou)

    def _pronto(self, resultado: object) -> None:
        if isinstance(resultado, Exception):
            self._falhou(login.mensagem(resultado))
            return
        self._limpar()
        if resultado is None:
            self.destravou.emit()
        else:
            self.entrou.emit(resultado)

    def _falhou(self, texto: str) -> None:
        self.botao.setEnabled(True)
        self.mensagem.setText(texto)
        log.info("Login recusado: %s", texto)
        self.senha.setFocus()
