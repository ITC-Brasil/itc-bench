"""Telas Políticas e USB (ADR-021). Regras em `servicos/politicas.py`; aqui só tela.

O nome da conta aparece só na tela; o serviço trabalha por SID e não loga nome.
"""

import threading
from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
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

from itc_bench.servicos import contas, politicas
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import tarefa
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

_COMUM = (
    "Alvos\n"
    "Máquina: vale para todas as contas. Contas futuras: o perfil padrão do Windows, copiado "
    "para contas criadas depois (as que já existem não mudam). Contas: só a conta marcada. O "
    "Administrador nativo e a conta Suporte são recusados. A conta que está rodando o Bench "
    "(você) é aceita, com aviso: a restrição vale para ela no próximo logon. Conta "
    "administradora é aceita, com aviso: um administrador consegue desfazer.\n\n"
    "Situação\n"
    "Aplicada, não aplicada, diferente (outro valor, outra ferramenta ou parte da política), "
    "não lida (perfil fechado: use Ler perfis fechados) e sem acesso (sem administrador). "
    "“Usuário pode alterar” quer dizer que a conta tem permissão na chave e pode desfazer.\n\n"
    "Edição do Windows\n"
    "“Efeito não confirmado nesta edição”: a Microsoft não garante a política nessa edição "
    "(Home; a Microsoft Store só no Enterprise/Education). O Bench aplica mesmo assim; confira "
    "na conta.\n\n"
    "Quando vale\n"
    "No próximo logon da conta (ou reinício, para o ICS). Perfil fechado é aberto, alterado e "
    "fechado de novo pelo Bench; se não conseguir fechar, reinicie antes de entrar na conta.\n\n"
    "Cancelar\n"
    "Vale entre alvos: o alvo em andamento termina.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)

AJUDA = (
    "Aplica e desfaz restrições do Windows (as “GPOs” do Configurador) por conta ou na "
    "máquina. A lista é fixa no Bench; não vem do cadastro.\n\n"
    "Aplicar\n"
    "1. Marque os alvos e as políticas. “Marcar todas” marca a lista inteira; clicando de novo "
    "(“Desmarcar todas”), desmarca.\n"
    "2. Aplicar mostra o que muda em cada alvo e pede confirmação.\n"
    "3. Desfazer volta ao padrão do Windows (o ICS volta para Manual).\n"
    "4. Desativar todas desfaz todas as políticas da lista nos alvos marcados, mesmo as "
    "desmarcadas, com a mesma confirmação.\n\n"
    "Bloquear PowerShell pelo Explorer impede abrir pelo Iniciar, Executar e duplo clique; uma "
    "cópia renomeada abre. Programas e Recursos esconde só o painel antigo.\n\n"
    "Script do Configurador\n"
    "Se a tela mostrar o script de logon antigo do Configurador (itc_security_check), remova: o "
    "Bench grava a política na conta certa e não precisa reaplicar no logon.\n\n" + _COMUM
)

AJUDA_USB = (
    "Bloqueia ou libera pendrive, HD externo, cartão de memória, CD/DVD e celular como disco.\n\n"
    "Desabilitar bloqueia leitura e gravação; Habilitar volta ao padrão do Windows. Por conta, "
    "o bloqueio vale só para ela (a Suporte e o técnico continuam usando pendrive); na Máquina, "
    "vale para todos, inclusive o técnico.\n\n"
    "Mouse, teclado e impressora USB continuam funcionando. Um pendrive já espetado pode "
    "continuar aberto até ser removido.\n\n" + _COMUM
)


class _Sinais(QObject):
    texto = Signal(str)


def _situacao(
    leitura: politicas.Leitura, p: politicas.Politica, alvos_: Sequence[politicas.Alvo]
) -> str:
    partes = []
    for a in alvos_:
        e = leitura.situacao.get((p.id, a.chave))
        if e is None:
            continue
        texto = f"{a.rotulo}: {politicas.ESTADO_ROTULO[e]}"
        if leitura.alteravel.get((p.id, a.chave)):
            texto += " (usuário pode alterar)"
        partes.append(texto)
    aviso = politicas.aviso_edicao(p, leitura.edicao)
    return " · ".join(partes) + (f" — {aviso}" if aviso else "")


class PainelPoliticas(QWidget):
    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        *,
        usb: bool = False,
    ) -> None:
        super().__init__()
        self.admin, self.obter_cadastros, self.usb = admin, obter_cadastros, usb
        self.catalogo = [p for p in politicas.CATALOGO if (p.id == "usb") == usb]
        self.leitura: politicas.Leitura | None = None
        self.todos: list[politicas.Alvo] = []
        self.itens: dict[str, QTreeWidgetItem] = {}
        self.ocupado = self.lido = False
        self.cancelar_evento: threading.Event | None = None
        self.sinais = _Sinais()
        self.sinais.texto.connect(self._registrar)

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.estado = _rotulo("")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(lambda: self.carregar(False))
        self.ler_fechados = QPushButton("Ler perfis fechados")
        self.ler_fechados.clicked.connect(lambda: self.carregar(True))
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.ler_fechados)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só leitura."))

        self.sobras = QWidget()
        hs = QHBoxLayout(self.sobras)
        hs.setContentsMargins(0, 0, 0, 0)
        hs.addWidget(
            _rotulo("Há o script de logon antigo do Configurador na pasta Inicializar."), 1
        )
        self.b_sobras = QPushButton("Remover")
        self.b_sobras.clicked.connect(self._remover_sobras)
        hs.addWidget(self.b_sobras)
        self.sobras.hide()
        if not usb:
            v.addWidget(self.sobras)

        # Marcar/desmarcar e desativar todas (ADR-033): só na tela Políticas; a USB tem uma só.
        self.b_marcar_todas = QPushButton("Marcar todas")
        self.b_marcar_todas.setToolTip("Marca ou desmarca todas as políticas da lista.")
        self.b_marcar_todas.clicked.connect(self._alternar_todas)
        if not usb:
            linha_marcar = QHBoxLayout()
            linha_marcar.addStretch()
            linha_marcar.addWidget(self.b_marcar_todas)
            v.addLayout(linha_marcar)

        meio = QHBoxLayout()
        self.lista_alvos = QListWidget()
        self.lista_alvos.setMaximumWidth(240)
        self.lista_alvos.itemChanged.connect(lambda _: self._mostrar())
        meio.addWidget(self.lista_alvos)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Política", "Escopo", "Situação"])
        self.arvore.setColumnWidth(0, 280)
        self.arvore.setColumnWidth(1, 110)
        self.arvore.itemChanged.connect(lambda *_: self._atualizar_marcar_todas())
        meio.addWidget(self.arvore, 1)
        v.addLayout(meio, 2)

        acoes = QHBoxLayout()
        self.b_aplicar = QPushButton("Desabilitar USB" if usb else "Aplicar")
        self.b_aplicar.setObjectName("primario")
        self.b_aplicar.clicked.connect(lambda: self._executar("aplicar"))
        self.b_desfazer = QPushButton("Habilitar USB" if usb else "Desfazer")
        self.b_desfazer.clicked.connect(lambda: self._executar("desfazer"))
        self.b_desativar_todas = QPushButton("Desativar todas")
        self.b_desativar_todas.setToolTip(
            "Desfaz todas as políticas de segurança nos alvos marcados, sem depender das caixas."
        )
        self.b_desativar_todas.clicked.connect(self._desativar_todas)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        acoes.addWidget(self.b_aplicar)
        acoes.addWidget(self.b_desfazer)
        if not usb:
            acoes.addWidget(self.b_desativar_todas)
        acoes.addWidget(self.b_cancelar)
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
            self.carregar(False)

    # ------------------------------------------------------------ leitura

    def carregar(self, fechados: bool) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        admin = self.admin

        def ler() -> tuple[list[politicas.Alvo], politicas.Leitura, bool]:
            alvos_ = politicas.alvos(contas.listar())
            leitura = politicas.ler(alvos_, descarregados=fechados and admin)
            return alvos_, leitura, bool(politicas.sobras_configurador())

        tarefa.iniciar(ler, self._recebeu, self._falhou)

    def _recebeu(self, dados: tuple[list[politicas.Alvo], politicas.Leitura, bool]) -> None:
        marcados = {a.chave for a in self._alvos_marcados()}
        self.todos, self.leitura, sobras = dados
        self.lido = True
        self.sobras.setVisible(sobras)
        self.lista_alvos.blockSignals(True)
        self.lista_alvos.clear()
        for a in self.todos:
            item = QListWidgetItem(a.rotulo + (" (admin)" if a.admin else ""))
            item.setData(Qt.ItemDataRole.UserRole, a.chave)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if a.chave in marcados else Qt.CheckState.Unchecked
            )
            self.lista_alvos.addItem(item)
        self.lista_alvos.blockSignals(False)
        edicao = self.leitura.edicao or "?"
        self.estado.setText(f"Windows {edicao}. Vale no próximo logon da conta.")
        self._mostrar()
        self._ocupar(False)

    def _alvos_marcados(self) -> list[politicas.Alvo]:
        chaves = {
            self.lista_alvos.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.lista_alvos.count())
            if self.lista_alvos.item(i).checkState() == Qt.CheckState.Checked
        }
        return [a for a in self.todos if a.chave in chaves]

    def _politicas_marcadas(self) -> list[politicas.Politica]:
        if self.usb:
            return self.catalogo
        return [
            p
            for p in self.catalogo
            if p.id in self.itens and self.itens[p.id].checkState(0) == Qt.CheckState.Checked
        ]

    def _mostrar(self) -> None:
        marcadas = {p.id for p in self._politicas_marcadas()} if not self.usb else set()
        self.arvore.blockSignals(True)
        try:
            self._montar_arvore(marcadas)
        finally:
            self.arvore.blockSignals(False)
        self._atualizar_marcar_todas()

    def _montar_arvore(self, marcadas: set[str]) -> None:
        self.arvore.clear()
        self.itens = {}
        alvos_ = self._alvos_marcados() or self.todos
        grupos: dict[str, QTreeWidgetItem] = {}
        for p in self.catalogo:
            grupo = grupos.get(p.grupo)
            if grupo is None:
                grupo = grupos[p.grupo] = QTreeWidgetItem([p.grupo])
                self.arvore.addTopLevelItem(grupo)
                grupo.setExpanded(True)
            escopo = " e ".join(
                {"usuario": "conta", "maquina": "máquina"}[e]
                for e in sorted(p.escopos, reverse=True)
            )
            texto = _situacao(self.leitura, p, alvos_) if self.leitura else ""
            item = QTreeWidgetItem([p.nome, escopo, texto])
            item.setToolTip(0, txt.dica(p.descricao))
            item.setToolTip(2, txt.dica(texto))
            self.itens[p.id] = item
            if not self.usb:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, Qt.CheckState.Checked if p.id in marcadas else Qt.CheckState.Unchecked
                )
            grupo.addChild(item)

    def _todas_marcadas(self) -> bool:
        return bool(self.itens) and all(
            item.checkState(0) == Qt.CheckState.Checked for item in self.itens.values()
        )

    def _atualizar_marcar_todas(self) -> None:
        self.b_marcar_todas.setText("Desmarcar todas" if self._todas_marcadas() else "Marcar todas")

    def _alternar_todas(self) -> None:
        """Marca todas; se já estão todas marcadas, desmarca todas. Só a tela, nada no Windows."""
        estado = Qt.CheckState.Unchecked if self._todas_marcadas() else Qt.CheckState.Checked
        self.arvore.blockSignals(True)
        try:
            for item in self.itens.values():
                item.setCheckState(0, estado)
        finally:
            self.arvore.blockSignals(False)
        self._atualizar_marcar_todas()

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._fim()
        self._ocupar(False)

    def _registrar(self, texto: str) -> None:
        self.registro.appendPlainText(texto)

    # ------------------------------------------------------------ ações

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pode = self.admin and not ocupado and self.leitura is not None
        altera = (
            self.b_aplicar,
            self.b_desfazer,
            self.b_desativar_todas,
            self.b_sobras,
            self.ler_fechados,
        )
        for b in altera:
            b.setEnabled(pode)
        self.atualizar.setEnabled(not ocupado)
        self.b_marcar_todas.setEnabled(not ocupado)  # só marca na tela: vale sem administrador
        if not self.admin:
            for b in altera:
                b.setToolTip("Precisa de administrador.")

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando depois deste passo…")

    def _fim(self) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self.b_cancelar.setText("Cancelar")

    def confirmacao(
        self,
        acao: politicas.Acao,
        escolhidas: Sequence[politicas.Politica],
        alvos_: Sequence[politicas.Alvo],
    ) -> str:
        destino = politicas.ESTADO_ROTULO["aplicada" if acao == "aplicar" else "nao_aplicada"]
        linhas = []
        for a in alvos_:
            for p in escolhidas:
                if a.escopo not in p.escopos:
                    continue
                atual = self.leitura.situacao.get((p.id, a.chave)) if self.leitura else None
                de = politicas.ESTADO_ROTULO[atual] if atual else "?"
                linhas.append(f"{p.nome} — {a.rotulo}: {de} → {destino}")
        avisos = []
        dono = self.leitura.dono if self.leitura else None
        if dono and any(a.chave == dono for a in alvos_):
            avisos.append(
                "A conta que está rodando o Bench (você) está marcada: a restrição vale para ela "
                "no próximo logon. Para desfazer, use Desfazer ou Desativar todas nela."
            )
        if any(a.admin for a in alvos_):
            avisos.append("Conta administradora marcada: ela consegue desfazer a política.")
        if any(a.tipo == "padrao" for a in alvos_):
            avisos.append("Contas futuras: só contas criadas depois recebem.")
        if self.leitura:
            for p in escolhidas:
                if politicas.aviso_edicao(p, self.leitura.edicao):
                    avisos.append(f"{p.nome}: {politicas.AVISO_EDICAO}.")
        return "\n".join(linhas + (["", *avisos] if avisos else []))

    def _desativar_todas(self) -> None:
        """Desfaz o catálogo inteiro desta tela nos alvos marcados (ADR-033), sem depender das
        caixas de política. Mesmo caminho e mesma confirmação detalhada do Desfazer."""
        self._executar(
            "desfazer",
            self.catalogo,
            cabecalho=(
                "Desativar TODAS as políticas de segurança nos alvos marcados (volta ao "
                "padrão do Windows):"
            ),
        )

    def _executar(
        self,
        acao: politicas.Acao,
        escolhidas: Sequence[politicas.Politica] | None = None,
        *,
        cabecalho: str = "",
    ) -> None:
        escolhidas = list(self._politicas_marcadas() if escolhidas is None else escolhidas)
        alvos_ = [
            a for a in self._alvos_marcados() if any(a.escopo in p.escopos for p in escolhidas)
        ]
        if not escolhidas or not alvos_:
            self._aviso("Marque pelo menos um alvo e uma política que valha para ele.")
            return
        texto = self.confirmacao(acao, escolhidas, alvos_)
        if cabecalho:
            texto = f"{cabecalho}\n\n{texto}"
        titulo = "USB" if self.usb else "Políticas"
        if not confirmar(self, f"{titulo} — {acao}", texto):
            return
        self.cancelar_evento = evento = threading.Event()
        self.b_cancelar.show()
        self._ocupar(True)
        prot = contas.protegidas(self.obter_cadastros())
        ids = [p.id for p in escolhidas]
        emitir = self.sinais.texto.emit
        tarefa.iniciar(
            lambda: politicas.aplicar(
                acao, ids, alvos_, protegidas_=prot, cancelar=evento, avisar=emitir
            ),
            self._feito,
            self._falhou,
        )

    def _feito(self, feitos: list[politicas.Feito]) -> None:
        self._fim()
        linhas = []
        for f in feitos:
            linhas.append(f"{f.alvo.rotulo}: {f.mensagem}")
            linhas += [f"  Aviso: {a}" for a in f.avisos]
        texto = "\n".join(linhas) or "Nada a fazer."
        self._registrar(texto)
        self._aviso(texto, erro=not all(f.ok for f in feitos))
        self.carregar(False)

    def _remover_sobras(self) -> None:
        if not confirmar(
            self,
            "Políticas",
            "Remover o script de logon do Configurador (itc_security_check.bat e .ps1) da pasta "
            "Inicializar de todos os usuários?",
        ):
            return
        ok, msg = politicas.remover_sobras()
        self._registrar(msg)
        self._aviso(msg, erro=not ok)
        self.carregar(False)

    def _aviso(self, texto: str, *, erro: bool = True) -> None:
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
            "USB" if self.usb else "Políticas",
            texto,
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
