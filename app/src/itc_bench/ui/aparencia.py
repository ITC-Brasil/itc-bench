"""Telas de Aparência e periféricos (ADR-022): Tela e papel de parede, Mouse e teclado, Energia.

Regras em `servicos/papel_de_parede.py`, `servicos/aparencia.py` e `servicos/energia.py`; aqui só
tela. O nome da conta aparece só na tela; os serviços trabalham por SID e não logam nome.
"""

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.nucleo.log import log
from itc_bench.servicos import aparencia as ap
from itc_bench.servicos import contas, energia, executor, hive
from itc_bench.servicos import papel_de_parede as pp
from itc_bench.servicos.cadastros import Cadastros, Instalador
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo, confirmar

_ALVOS = (
    "Alvos\n"
    "Contas futuras: o perfil padrão do Windows, copiado para contas criadas depois. Contas: só "
    "a conta marcada; perfil fechado é aberto, alterado e fechado pelo Bench. O Administrador "
    "nativo, a conta Suporte e a conta que está rodando o Bench são recusados.\n\n"
    "Quando vale\n"
    "No próximo logon da conta. Se a conta estiver aberta, saia e entre de novo.\n\n"
    "Cancelar vale entre contas: a conta em andamento termina.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)

AJUDA_TELA = (
    "Põe o papel de parede do Grupo nas contas e impede o aluno de trocar.\n\n"
    "Aplicar\n"
    "1. Escolha a imagem (vem do cadastro em Instaladores, tipo papel) e o estilo.\n"
    "2. Marque as contas. Aplicar baixa a imagem (ou use Escolher arquivo… sem rede: o Bench "
    "copia e confere o SHA-256 com o cadastro) e grava a política de papel de parede.\n"
    "3. Desfazer apaga a política; a conta volta ao papel de parede dela.\n\n"
    "A imagem fica numa pasta do Bench que o aluno lê, mas não altera. Aceita JPG e PNG, até "
    "20 MB, de 640x480 a 7680x4320.\n\n"
    "Trocou a imagem no cadastro?\n"
    "Reaplique o papel de parede nas contas. O Bench apaga a imagem antiga quando ela sai do "
    "cadastro, e as contas que apontavam para ela ficam sem papel de parede até reaplicar.\n\n"
    "Resolução e escala\n"
    "O Bench não muda: o Windows já usa a resolução recomendada do notebook. Para ajustar, use "
    "Abrir configurações de vídeo, na conta do aluno.\n\n" + _ALVOS
)

AJUDA_MOUSE = (
    "Ajusta mouse e teclado por conta, com valores fixos do Bench.\n\n"
    "1. Marque as contas e os ajustes, escolha o valor de cada um.\n"
    "2. Aplicar mostra o que muda e pede confirmação.\n"
    "3. Desfazer volta os ajustes marcados ao padrão do Windows.\n\n"
    "Ponteiro: branco, preto ou invertido, em três tamanhos (arquivos do próprio Windows). O "
    "aluno pode mudar depois; para travar o ponteiro, use a política em Segurança › Políticas. "
    "Atalho Shift 5x: desliga a janela das Teclas de aderência na conta (na tela de login, use "
    "Proteção do login).\n\n" + _ALVOS
)

AJUDA_ENERGIA = (
    "Ajusta quando a tela desliga, quando o notebook suspende ou hiberna e quando o disco "
    "desliga, na tomada e na bateria, no plano de energia ativo (o Bench não troca o plano).\n\n"
    "1. Escolha os tempos e marque os que quer gravar.\n"
    "2. Aplicar grava e reativa o plano; vale na hora.\n"
    "3. Desfazer volta os marcados ao padrão do próprio plano.\n\n"
    "Hibernação\n"
    "Desligar hibernação apaga o arquivo de hibernação e desliga a Inicialização rápida. Desfazer "
    "volta para ligada.\n\n"
    "O Bench não usa “restaurar planos padrão”: isso apaga os planos do fabricante.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)


def abrir_configuracoes_video() -> None:
    explorer = str(Path(executor.sistema32("explorer.exe")).parent.parent / "explorer.exe")
    executor.executar([explorer, "ms-settings:display"], timeout=15)


class _Sinais(QObject):
    texto = Signal(str)


def _aviso(pai: QWidget, titulo: str, texto: str, *, erro: bool = True) -> None:
    caixa = QMessageBox(
        QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
        titulo,
        texto,
        parent=pai,
    )
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    caixa.open()


# ---------------------------------------------------------------- base com alvos


class _PainelAlvos(QWidget):
    """Lista de alvos (Contas futuras e contas), aplicar/desfazer com cancelamento e registro."""

    titulo = ""

    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__()
        self.admin, self.obter_cadastros = admin, obter_cadastros
        self.todos: list[hive.Alvo] = []
        self.ocupado = self.lido = False
        self.cancelar_evento: threading.Event | None = None
        self.sinais = _Sinais()
        self.sinais.texto.connect(self._registrar)

        self.v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.estado = _rotulo("")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(lambda: self.carregar(False))
        self.ler_fechados = QPushButton("Ler perfis fechados")
        self.ler_fechados.clicked.connect(lambda: self.carregar(True))
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.ler_fechados)
        topo.addWidget(self.atualizar)
        self.v.addLayout(topo)
        if not admin:
            self.v.addWidget(_rotulo("Sem administrador: só leitura."))
        self.meio = QHBoxLayout()
        self.lista_alvos = QListWidget()
        self.lista_alvos.setMaximumWidth(280)
        self.lista_alvos.itemChanged.connect(lambda _: self._mostrar())
        self.meio.addWidget(self.lista_alvos)
        self.v.addLayout(self.meio, 2)

        self.acoes = QHBoxLayout()
        self.b_aplicar = QPushButton("Aplicar")
        self.b_aplicar.setObjectName("primario")
        self.b_aplicar.clicked.connect(lambda: self._executar("aplicar"))
        self.b_desfazer = QPushButton("Desfazer")
        self.b_desfazer.clicked.connect(lambda: self._executar("desfazer"))
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        for b in (self.b_aplicar, self.b_desfazer, self.b_cancelar):
            self.acoes.addWidget(b)
        self.acoes.addStretch()
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)

    def _fechar_layout(self) -> None:
        """As subclasses põem o conteúdo no `meio` e chamam isto no fim do __init__."""
        self.v.addLayout(self.acoes)
        self.v.addWidget(self.registro, 1)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar(False)

    def carregar(self, fechados: bool) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        fechados = fechados and self.admin
        ler = self._ler

        def tudo() -> tuple[list[hive.Alvo], Any]:
            alvos_ = [a for a in hive.alvos(contas.listar()) if a.tipo != "maquina"]
            return alvos_, ler(alvos_, fechados)

        tarefa.iniciar(tudo, self._recebeu, self._falhou)

    def _ler(self, alvos_: list[hive.Alvo], fechados: bool) -> Any:
        raise NotImplementedError

    def _recebeu(self, dados: tuple[list[hive.Alvo], Any]) -> None:
        marcados = {a.chave for a in self.alvos_marcados()}
        self.todos, leitura = dados
        self._guardar(leitura)
        self.lido = True
        self.lista_alvos.blockSignals(True)
        self.lista_alvos.clear()
        for a in self.todos:
            item = QListWidgetItem(self._rotulo_alvo(a))
            item.setData(Qt.ItemDataRole.UserRole, a.chave)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if a.chave in marcados else Qt.CheckState.Unchecked
            )
            self.lista_alvos.addItem(item)
        self.lista_alvos.blockSignals(False)
        self.estado.setText("Vale no próximo logon da conta.")
        self._mostrar()
        self._ocupar(False)

    def _guardar(self, leitura: Any) -> None:
        raise NotImplementedError

    def _rotulo_alvo(self, a: hive.Alvo) -> str:
        return a.rotulo

    def _mostrar(self) -> None:
        """Atualiza o conteúdo pela seleção; padrão: nada."""

    def alvos_marcados(self) -> list[hive.Alvo]:
        chaves = {
            self.lista_alvos.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.lista_alvos.count())
            if self.lista_alvos.item(i).checkState() == Qt.CheckState.Checked
        }
        return [a for a in self.todos if a.chave in chaves]

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._fim()
        self._ocupar(False)

    def _registrar(self, texto: str) -> None:
        self.registro.appendPlainText(texto)

    def _botoes(self) -> list[QPushButton]:
        return [self.b_aplicar, self.b_desfazer, self.ler_fechados]

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pode = self.admin and not ocupado and self.lido
        for b in self._botoes():
            b.setEnabled(pode)
            if not self.admin:
                b.setToolTip("Precisa de administrador.")
        self.atualizar.setEnabled(not ocupado)

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando depois deste passo…")

    def _fim(self) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self.b_cancelar.setText("Cancelar")

    def confirmacao(self, acao: hive.Acao, alvos_: Sequence[hive.Alvo]) -> str | None:
        """Texto da confirmação, ou None com o motivo já mostrado."""
        raise NotImplementedError

    def _tarefa(
        self,
        acao: hive.Acao,
        alvos_: list[hive.Alvo],
        prot: frozenset[str],
        cancelar: threading.Event,
        avisar: Callable[[str], None],
    ) -> Callable[[], list[hive.Feito]]:
        raise NotImplementedError

    def _executar(self, acao: hive.Acao) -> None:
        alvos_ = self.alvos_marcados()
        if not alvos_:
            _aviso(self, self.titulo, "Marque pelo menos uma conta.")
            return
        texto = self.confirmacao(acao, alvos_)
        if texto is None or not confirmar(self, f"{self.titulo} — {acao}", texto):
            return
        self.cancelar_evento = evento = threading.Event()
        self.b_cancelar.show()
        self._ocupar(True)
        prot = contas.protegidas(self.obter_cadastros())
        funcao = self._tarefa(acao, alvos_, prot, evento, self.sinais.texto.emit)
        tarefa.iniciar(funcao, self._feito, self._falhou)

    def _feito(self, feitos: list[hive.Feito]) -> None:
        self._fim()
        linhas = []
        for f in feitos:
            linhas.append(f"{f.alvo.rotulo}: {f.mensagem}")
            linhas += [f"  Aviso: {a}" for a in f.avisos]
        texto = "\n".join(linhas) or "Nada a fazer."
        self._registrar(texto)
        _aviso(self, self.titulo, texto, erro=not all(f.ok for f in feitos))
        self.carregar(False)


# ---------------------------------------------------------------- Tela e papel de parede


class PainelPapel(_PainelAlvos):
    titulo = "Papel de parede"

    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__(admin, obter_cadastros)
        self.situacao: dict[str, pp.Situacao] = {}
        self.origem: Path | None = None
        lado = QVBoxLayout()
        self.imagem = QComboBox()
        self.imagem.currentIndexChanged.connect(lambda _: self._trocou_imagem())
        self.estilo = QComboBox()
        for chave, rotulo in pp.ROTULO_ESTILO.items():
            self.estilo.addItem(rotulo, chave)
        self.detalhe = _rotulo("")
        self.b_escolher = QPushButton("Escolher arquivo…")
        self.b_escolher.clicked.connect(self._escolher)
        self.b_video = QPushButton("Abrir configurações de vídeo")
        self.b_video.clicked.connect(self._video)
        for w in (
            _rotulo("Imagem (cadastro):"),
            self.imagem,
            _rotulo("Estilo:"),
            self.estilo,
            self.detalhe,
            self.b_escolher,
        ):
            lado.addWidget(w)
        lado.addStretch()
        lado.addWidget(_rotulo("Resolução e escala ficam com o Windows."))
        lado.addWidget(self.b_video)
        self.meio.addLayout(lado, 1)
        self._fechar_layout()

    def _botoes(self) -> list[QPushButton]:
        return [*super()._botoes(), self.b_escolher]

    def linha(self) -> Instalador | None:
        indice = self.imagem.currentData()
        return next((i for i in pp.linhas(self.obter_cadastros()) if i.id == indice), None)

    def _ler(self, alvos_: list[hive.Alvo], fechados: bool) -> Any:
        return pp.ler(alvos_, self.linha(), descarregados=fechados)

    def _guardar(self, leitura: Any) -> None:
        self.situacao = leitura
        atual = self.imagem.currentData()
        self.imagem.blockSignals(True)
        self.imagem.clear()
        for i in pp.linhas(self.obter_cadastros()):
            motivo = pp.validar(i)
            self.imagem.addItem(i.programa + (f" (inválida: {motivo})" if motivo else ""), i.id)
        if atual is not None and (n := self.imagem.findData(atual)) >= 0:
            self.imagem.setCurrentIndex(n)
        self.imagem.blockSignals(False)
        self._trocou_imagem()

    def _trocou_imagem(self) -> None:
        self.origem = None
        linha = self.linha()
        if linha is None:
            self.detalhe.setText("Sem imagem no cadastro (Instaladores, tipo papel).")
            return
        guardada = self.admin and pp.caminho(linha) is not None
        self.detalhe.setText(
            f"SHA-256 {linha.sha256.strip()[:12].lower()}… — "
            + ("conferida nesta máquina." if guardada else "será baixada ao aplicar.")
        )

    def _rotulo_alvo(self, a: hive.Alvo) -> str:
        s = self.situacao.get(a.chave)
        return a.rotulo + (f" — {pp.ROTULO_ESTADO[s.estado]}" if s else "")

    def _escolher(self) -> None:
        linha = self.linha()
        if linha is None:
            return
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Papel de parede", "", "Imagem (*.jpg *.jpeg *.png)"
        )
        if caminho:
            self.origem = Path(caminho)
            self.detalhe.setText(f"Arquivo escolhido ({self.origem.name}); conferido ao aplicar.")

    def _video(self) -> None:
        try:
            abrir_configuracoes_video()
        except OSError as erro:
            log.warning("Aparência: configurações de vídeo não abriram (%s)", type(erro).__name__)
            _aviso(self, self.titulo, "Não foi possível abrir as configurações de vídeo.")

    def confirmacao(self, acao: hive.Acao, alvos_: Sequence[hive.Alvo]) -> str | None:
        linha = self.linha()
        if acao == "aplicar" and (linha is None or pp.validar(linha)):
            _aviso(self, self.titulo, "Escolha uma imagem válida do cadastro.")
            return None
        destino = "papel de parede do Grupo" if acao == "aplicar" else "papel de parede da conta"
        linhas = []
        for a in alvos_:
            s = self.situacao.get(a.chave)
            de = pp.ROTULO_ESTADO[s.estado] if s else "?"
            linhas.append(f"{a.rotulo}: {de} → {destino}")
        if acao == "aplicar":
            linhas += ["", f"Estilo: {self.estilo.currentText()}. Vale no próximo logon."]
        if any(a.tipo == "padrao" for a in alvos_):
            linhas.append("Contas futuras: só contas criadas depois recebem.")
        return "\n".join(linhas)

    def _tarefa(
        self,
        acao: hive.Acao,
        alvos_: list[hive.Alvo],
        prot: frozenset[str],
        cancelar: threading.Event,
        avisar: Callable[[str], None],
    ) -> Callable[[], list[hive.Feito]]:
        linha, origem, estilo = self.linha(), self.origem, str(self.estilo.currentData())

        def rodar() -> list[hive.Feito]:
            if acao == "aplicar" and linha is not None:
                avisar("Conferindo a imagem…")
                try:
                    pp.obter(linha, origem, cancelar=cancelar)
                except pp.ErroPapel as erro:
                    return [hive.Feito(hive.PADRAO, False, str(erro))]
            return pp.aplicar(
                acao,
                alvos_,
                linha=linha,
                estilo=estilo,
                protegidas_=prot,
                cancelar=cancelar,
                avisar=avisar,
            )

        return rodar


# ---------------------------------------------------------------- Mouse e teclado


class PainelMouse(_PainelAlvos):
    titulo = "Mouse e teclado"

    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__(admin, obter_cadastros)
        self.situacao: dict[tuple[str, str], ap.Situacao] = {}
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Ajuste", "Valor", "Situação"])
        self.arvore.setColumnWidth(0, 260)
        self.arvore.setColumnWidth(1, 200)
        self.arvore.setRootIsDecorated(False)
        self.itens: dict[str, QTreeWidgetItem] = {}
        self.valores: dict[str, QComboBox] = {}
        for a in ap.CATALOGO:
            item = QTreeWidgetItem([a.nome, "", ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.arvore.addTopLevelItem(item)
            combo = QComboBox()
            for valor, rotulo in a.opcoes.items():
                combo.addItem(rotulo + (" (padrão)" if valor == a.padrao else ""), valor)
            combo.setCurrentIndex(combo.findData(a.padrao))
            self.arvore.setItemWidget(item, 1, combo)
            self.itens[a.id], self.valores[a.id] = item, combo
        self.meio.addWidget(self.arvore, 1)
        self._fechar_layout()

    def _ler(self, alvos_: list[hive.Alvo], fechados: bool) -> Any:
        return ap.ler(alvos_, descarregados=fechados)

    def _guardar(self, leitura: Any) -> None:
        self.situacao = leitura

    def escolhas(self) -> dict[str, str]:
        return {
            aid: str(self.valores[aid].currentData())
            for aid, item in self.itens.items()
            if item.checkState(0) == Qt.CheckState.Checked
        }

    def _texto(self, aid: str, alvos_: Sequence[hive.Alvo]) -> str:
        partes = []
        ajuste = ap.POR_ID[aid]
        for a in alvos_:
            s = self.situacao.get((aid, a.chave))
            if s is None:
                continue
            texto = ap.ROTULO_ESTADO[s.estado]
            if s.estado == "ajustado" and s.valor is not None:
                texto = ajuste.opcoes[s.valor]
            partes.append(f"{a.rotulo}: {texto}")
        return " · ".join(partes)

    def _mostrar(self) -> None:
        alvos_ = self.alvos_marcados() or self.todos
        for aid, item in self.itens.items():
            texto = self._texto(aid, alvos_)
            item.setText(2, texto)
            item.setToolTip(2, texto)

    def confirmacao(self, acao: hive.Acao, alvos_: Sequence[hive.Alvo]) -> str | None:
        escolhas = self.escolhas()
        if not escolhas:
            _aviso(self, self.titulo, "Marque pelo menos um ajuste.")
            return None
        linhas = []
        for a in alvos_:
            for aid, valor in escolhas.items():
                ajuste = ap.POR_ID[aid]
                s = self.situacao.get((aid, a.chave))
                de = ap.ROTULO_ESTADO[s.estado] if s else "?"
                if s and s.estado in ("ajustado", "padrao") and s.valor is not None:
                    de = ajuste.opcoes[s.valor]
                para = ajuste.opcoes[valor if acao == "aplicar" else ajuste.padrao]
                linhas.append(f"{ajuste.nome} — {a.rotulo}: {de} → {para}")
        if any(a.tipo == "padrao" for a in alvos_):
            linhas += ["", "Contas futuras: só contas criadas depois recebem."]
        return "\n".join(linhas)

    def _tarefa(
        self,
        acao: hive.Acao,
        alvos_: list[hive.Alvo],
        prot: frozenset[str],
        cancelar: threading.Event,
        avisar: Callable[[str], None],
    ) -> Callable[[], list[hive.Feito]]:
        escolhas = self.escolhas()
        return lambda: ap.aplicar(
            acao, escolhas, alvos_, protegidas_=prot, cancelar=cancelar, avisar=avisar
        )


# ---------------------------------------------------------------- Energia


class PainelEnergia(QWidget):
    titulo = "Energia"

    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.situacao: energia.Situacao | None = None
        self.ocupado = self.lido = False
        self.cancelar_evento: threading.Event | None = None

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
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Ajuste", "Atual", "Padrão do plano", "Novo valor"])
        self.arvore.setColumnWidth(0, 260)
        self.arvore.setRootIsDecorated(False)
        self.itens: dict[tuple[str, energia.Fonte], QTreeWidgetItem] = {}
        self.valores: dict[tuple[str, energia.Fonte], QComboBox] = {}
        for aid, (nome, _, _) in energia.AJUSTES.items():
            for f in energia.FONTES:
                item = QTreeWidgetItem([f"{nome} — {energia.ROTULO_FONTE[f].lower()}", "", "", ""])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                self.arvore.addTopLevelItem(item)
                combo = QComboBox()
                for seg, rotulo in energia.TEMPOS.items():
                    combo.addItem(rotulo, seg)
                self.arvore.setItemWidget(item, 3, combo)
                self.itens[(aid, f)], self.valores[(aid, f)] = item, combo
        v.addWidget(self.arvore, 2)

        hib = QHBoxLayout()
        self.hibernacao = _rotulo("")
        self.b_hib_off = QPushButton("Desligar hibernação")
        self.b_hib_off.clicked.connect(lambda: self._hibernacao(False))
        self.b_hib_on = QPushButton("Ligar hibernação")
        self.b_hib_on.clicked.connect(lambda: self._hibernacao(True))
        hib.addWidget(self.hibernacao, 1)
        hib.addWidget(self.b_hib_off)
        hib.addWidget(self.b_hib_on)
        v.addLayout(hib)

        acoes = QHBoxLayout()
        self.b_aplicar = QPushButton("Aplicar")
        self.b_aplicar.setObjectName("primario")
        self.b_aplicar.clicked.connect(lambda: self._executar("aplicar"))
        self.b_desfazer = QPushButton("Desfazer")
        self.b_desfazer.clicked.connect(lambda: self._executar("desfazer"))
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        for b in (self.b_aplicar, self.b_desfazer, self.b_cancelar):
            acoes.addWidget(b)
        acoes.addStretch()
        v.addLayout(acoes)
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)
        v.addWidget(self.registro, 1)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar()

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        tarefa.iniciar(energia.situacao, self._recebeu, self._falhou)

    def _recebeu(self, s: energia.Situacao) -> None:
        self.situacao, self.lido = s, True
        for k, item in self.itens.items():
            valor = s.valores.get(k)
            item.setText(1, energia.rotulo_tempo(valor.atual if valor else None))
            item.setText(2, energia.rotulo_tempo(valor.padrao if valor else None))
        hib = {True: "ligada", False: "desligada", None: "não lida"}[s.hibernacao]
        self.hibernacao.setText(f"Hibernação: {hib}.")
        self.estado.setText("Plano de energia ativo. Vale na hora.")
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._fim()
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pode = self.admin and not ocupado and self.situacao is not None
        for b in (self.b_aplicar, self.b_desfazer, self.b_hib_off, self.b_hib_on):
            b.setEnabled(pode)
            if not self.admin:
                b.setToolTip("Precisa de administrador.")
        self.atualizar.setEnabled(not ocupado)

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando depois deste passo…")

    def _fim(self) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self.b_cancelar.setText("Cancelar")

    def marcados(self) -> list[tuple[str, energia.Fonte]]:
        return [k for k, i in self.itens.items() if i.checkState(0) == Qt.CheckState.Checked]

    def confirmacao(self, acao: str) -> str:
        linhas = []
        for k in self.marcados():
            item = self.itens[k]
            if acao == "aplicar":
                para = self.valores[k].currentText()
            else:
                v = self.situacao.valores.get(k) if self.situacao else None
                para = energia.rotulo_tempo(v.padrao if v else None) + " (padrão do plano)"
            linhas.append(f"{item.text(0)}: {item.text(1)} → {para}")
        return "\n".join(linhas)

    def _executar(self, acao: str) -> None:
        marcados = self.marcados()
        if not marcados:
            _aviso(self, self.titulo, "Marque pelo menos um ajuste.")
            return
        if not confirmar(self, f"{self.titulo} — {acao}", self.confirmacao(acao)):
            return
        self.cancelar_evento = evento = threading.Event()
        self.b_cancelar.show()
        self._ocupar(True)
        if acao == "aplicar":
            escolhas = {k: int(self.valores[k].currentData()) for k in marcados}
            tarefa.iniciar(
                lambda: energia.tempos(escolhas, cancelar=evento), self._feito, self._falhou
            )
        else:
            tarefa.iniciar(
                lambda: energia.desfazer(marcados, cancelar=evento), self._feito, self._falhou
            )

    def _feito(self, feitos: list[energia.Feito]) -> None:
        self._fim()
        texto = "\n".join(f"{f.item}: {f.mensagem}" for f in feitos) or "Nada a fazer."
        self.registro.appendPlainText(texto)
        _aviso(self, self.titulo, texto, erro=not all(f.ok for f in feitos))
        self.carregar()

    def confirmacao_hibernacao(self, ligar: bool) -> str:
        atual = {True: "ligada", False: "desligada", None: "não lida"}[
            self.situacao.hibernacao if self.situacao else None
        ]
        if ligar:
            return f"Hibernação agora: {atual}. Ligar (padrão do Windows)?"
        return (
            f"Hibernação agora: {atual}. Desligar? Apaga o arquivo de hibernação e desliga a "
            "Inicialização rápida. Para voltar, use Ligar hibernação."
        )

    def _hibernacao(self, ligar: bool) -> None:
        if not confirmar(self, self.titulo, self.confirmacao_hibernacao(ligar)):
            return
        self._ocupar(True)
        tarefa.iniciar(lambda: [energia.hibernacao(ligar)], self._feito, self._falhou)
