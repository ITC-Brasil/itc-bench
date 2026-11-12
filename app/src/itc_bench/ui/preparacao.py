"""Tela Preparação completa (ADR-023). Motor em `servicos/preparacao.py`, etapas em
`servicos/etapas.py`, retomada em `servicos/retomada.py`; aqui só tela."""

import threading
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
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
from itc_bench.servicos import contas, etapas, identificacao, perfis, retomada
from itc_bench.servicos import preparacao as prep
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import tarefa, tema
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Roda as etapas do perfil em ordem: Identificação, Contas, Wi-Fi, Acesso remoto, "
    "Programas, Remover pré-instalados, Políticas, USB, Proteção do login, Papel de parede, "
    "Mouse e teclado, Energia, Limpeza e Diagnóstico. Cada etapa usa as mesmas regras da tela "
    "dela.\n\n"
    "Como usar\n"
    "1. Escolha o perfil (vem marcado o da unidade). Desmarque etapas que não quer agora.\n"
    "2. Digite o nome do computador, se for trocar, e marque as contas de aluno.\n"
    "3. Ler situação confere cada etapa no Windows: feito, pendente ou bloqueada (com o motivo).\n"
    "4. Rodar N etapas mostra o que muda e pede confirmação. Etapa já feita é pulada; rodar de "
    "novo não refaz nada.\n"
    "5. Pausar para depois da etapa que está rodando.\n\n"
    "Contas\n"
    "Aplica a conta Suporte e tira administrador de todas as outras, inclusive da conta em uso "
    "(vale na próxima entrada; depois o UAC pede a Suporte). O Administrador nativo não é "
    "alterado: se estiver ativo, desative-o pelo Windows.\n\n"
    "Contas de aluno\n"
    "Contas locais ativas que não são administradoras, menos a Suporte, o Administrador nativo e "
    "a conta em uso. Políticas, USB, papel de parede e mouse valem para elas e para Contas "
    "futuras.\n\n"
    "Falha e bloqueio\n"
    "Etapa que falha não para as outras; as que dependem dela (Políticas, USB, papel e mouse "
    "dependem de Contas) ficam bloqueadas. Veja o motivo na linha e no Registro.\n\n"
    "Reinício\n"
    "Trocar o nome e alguns instaladores pedem reinício. O Bench não reinicia sozinho: use "
    "Reiniciar agora. Depois do reinício, abra o Bench, entre e escolha Continuar; a preparação "
    "relê tudo e roda só o que falta. Vale por 24 horas e até 2 reinícios. Descartar apaga a "
    "preparação guardada.\n\n"
    "Sem administrador (modo de teste), só a leitura."
)
# Situação → tipo de cor do tema (ok, aviso, erro, info, neutro), no modo claro ou escuro.
COR = {
    "feito": "ok",
    "pendente": "aviso",
    "nao_iniciado": "neutro",
    "bloqueada": "neutro",
    "falhou": "erro",
    "aguardando_reinicio": "info",
}


class _Sinais(QObject):
    texto = Signal(str)
    etapa = Signal(str)


class PainelPreparacao(QWidget):
    selo = Signal(str)

    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str | None],
        diagnosticar: Callable[[threading.Event], prep.Resultado] | None = None,
    ) -> None:
        super().__init__()
        self.admin = admin
        self.obter_cadastros = obter_cadastros
        self.obter_unidade = obter_unidade
        self.ctx = etapas.Contexto(admin, None, diagnosticar=diagnosticar)
        self.etapas: list[prep.Etapa] = []
        self.andamento: prep.Andamento | None = None
        self.guardado: retomada.Estado | None = None
        self.pausar = threading.Event()
        self.ocupado = False
        self.iniciado = False
        self.sinais = _Sinais()
        self.sinais.texto.connect(self._linha)
        self.sinais.etapa.connect(self._etapa_mudou)

        v = QVBoxLayout(self)
        self.banner = QFrame()
        self.banner.setObjectName("cartao")
        hb = QHBoxLayout(self.banner)
        self.banner_texto = _rotulo("")
        self.b_continuar = QPushButton("Continuar")
        self.b_continuar.clicked.connect(self._continuar)
        self.b_descartar = QPushButton("Descartar preparação")
        self.b_descartar.clicked.connect(self._descartar)
        hb.addWidget(self.banner_texto, 1)
        hb.addWidget(self.b_continuar)
        hb.addWidget(self.b_descartar)
        self.banner.hide()
        v.addWidget(self.banner)

        topo = QHBoxLayout()
        self.perfil = QComboBox()
        for p in perfis.PERFIS:
            self.perfil.addItem(p.nome, p.id)
        self.perfil.currentIndexChanged.connect(lambda _i: self._montar_lista())
        self.nome = QLineEdit()
        self.nome.setPlaceholderText("Nome do computador (vazio = não trocar)")
        self.nome.setMaxLength(15)
        topo.addWidget(_rotulo("Perfil:"))
        topo.addWidget(self.perfil)
        topo.addWidget(self.nome, 1)
        v.addLayout(topo)
        self.aviso = _rotulo("")
        v.addWidget(self.aviso)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só a leitura."))

        meio = QHBoxLayout()
        self.lista = QTreeWidget()
        self.lista.setHeaderLabels(["Etapa", "Situação", "Detalhe"])
        self.lista.setColumnWidth(0, 210)
        self.lista.setColumnWidth(1, 150)
        self.lista.setRootIsDecorated(False)
        self.lista.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        alunos = QVBoxLayout()
        alunos.addWidget(_rotulo("Contas de aluno"))
        self.alunos = QListWidget()
        self.alunos.setMaximumWidth(240)
        alunos.addWidget(self.alunos, 1)
        meio.addWidget(self.lista, 3)
        meio.addLayout(alunos, 1)
        v.addLayout(meio, 3)

        acoes = QHBoxLayout()
        self.b_ler = QPushButton("Ler situação")
        self.b_ler.clicked.connect(self.ler)
        self.b_pausar = QPushButton("Pausar")
        self.b_pausar.clicked.connect(self._pausar)
        self.b_reiniciar = QPushButton("Reiniciar agora")
        self.b_reiniciar.clicked.connect(self._reiniciar)
        self.b_reiniciar.hide()
        self.b_rodar = QPushButton("Rodar etapas")
        self.b_rodar.setObjectName("primario")
        self.b_rodar.clicked.connect(self._rodar)
        acoes.addWidget(self.b_ler)
        acoes.addStretch()
        acoes.addWidget(self.b_reiniciar)
        acoes.addWidget(self.b_pausar)
        acoes.addWidget(self.b_rodar)
        v.addLayout(acoes)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        v.addWidget(self.log, 2)
        self._montar_lista()
        self._ocupar(False)

    # ---- dados

    def perfil_atual(self) -> perfis.Perfil:
        return perfis.POR_ID[str(self.perfil.currentData())]

    def perfil_da_unidade(self) -> tuple[perfis.Perfil, str]:
        cad = self.obter_cadastros()
        u = cad.unidade_por_codigo(self.obter_unidade()) if cad is not None else None
        return perfis.do_cadastro(u.perfil_padrao if u is not None else None)

    def desmarcadas(self) -> list[str]:
        fora = []
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item is not None and item.checkState(0) != Qt.CheckState.Checked:
                fora.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return fora

    def alvos(self) -> list[str]:
        saida = []
        for i in range(self.alunos.count()):
            item = self.alunos.item(i)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                saida.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return saida

    def _montar_lista(self, desmarcadas: tuple[str, ...] = ()) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        for eid in self.perfil_atual().etapas:
            item = QTreeWidgetItem([perfis.NOMES[eid], prep.ROTULO["nao_iniciado"], ""])
            item.setData(0, Qt.ItemDataRole.UserRole, eid)
            marcado = Qt.CheckState.Unchecked if eid in desmarcadas else Qt.CheckState.Checked
            item.setCheckState(0, marcado)
            self.lista.addTopLevelItem(item)
        self.lista.blockSignals(False)
        self.andamento = None
        self._ocupar(self.ocupado)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if self.iniciado:
            return
        self.iniciado = True
        perfil, aviso = self.perfil_da_unidade()
        self.perfil.setCurrentIndex(self.perfil.findData(perfil.id))
        self.aviso.setText(aviso)
        self._carregar_alunos()
        self._ver_guardado()

    def _carregar_alunos(self, marcar: tuple[str, ...] | None = None) -> None:
        cad = self.obter_cadastros()

        def ler() -> list[contas.Conta]:
            return etapas.contas_de_aluno(contas.listar(), contas.protegidas(cad))

        def recebeu(lista: list[contas.Conta]) -> None:
            self.alunos.clear()
            for c in lista:
                item = QListWidgetItem(c.nome)
                item.setData(Qt.ItemDataRole.UserRole, c.sid)
                sim = marcar is None or c.sid in marcar
                item.setCheckState(Qt.CheckState.Checked if sim else Qt.CheckState.Unchecked)
                self.alunos.addItem(item)
            if not lista:
                self.alunos.addItem("Nenhuma conta de aluno.")

        tarefa.iniciar(ler, recebeu, lambda m: self._linha(f"Contas não lidas: {m}"))

    def _ver_guardado(self) -> None:
        if not self.admin:
            return
        self.guardado = retomada.ler()
        if self.guardado is None:
            self.banner.hide()
            return
        quando = datetime.fromisoformat(self.guardado.criado_em).astimezone()
        nome = perfis.POR_ID[self.guardado.perfil].nome
        self.banner_texto.setText(
            f"Há uma preparação ({nome}) iniciada em {quando:%d/%m %H:%M}, com "
            f"{self.guardado.reinicios} reinício(s). Continuar de onde parou?"
        )
        self.banner.show()

    def _continuar(self) -> None:
        g = self.guardado
        if g is None:
            return
        self.perfil.setCurrentIndex(self.perfil.findData(g.perfil))
        self._montar_lista(g.desmarcadas)
        self.nome.setText(g.nome)
        self._carregar_alunos(g.alvos)
        self.banner.hide()
        log.info("Preparação: retomada perfil=%s reinicios=%s", g.perfil, g.reinicios)
        self.ler()

    def _descartar(self) -> None:
        if confirmar(self, "Preparação", "Descartar a preparação guardada?"):
            retomada.descartar()
            self.guardado = None
            self.banner.hide()

    # ---- leitura e execução

    def _preparar_ctx(self) -> None:
        self.ctx.cadastros = self.obter_cadastros()
        self.ctx.unidade = self.obter_unidade()
        self.ctx.nome = (
            identificacao.normalizar(self.nome.text()) if self.nome.text().strip() else ""
        )
        self.ctx.alvos = tuple(self.alvos())
        self.ctx.avisar = self.sinais.texto.emit
        self.ctx._lista = None
        if not self.etapas:
            self.etapas = etapas.montar(self.ctx)

    def ler(self) -> None:
        self._preparar_ctx()
        self.andamento = prep.novo(self.perfil_atual(), self.desmarcadas())
        andamento, lista = self.andamento, self.etapas
        self._ocupar(True)
        self._linha("Lendo a situação das etapas…")
        tarefa.iniciar(
            lambda: prep.ler_todas(lista, andamento, self.sinais.etapa.emit),
            self._terminou,
            self._falhou,
        )

    def confirmacao(self) -> str:
        if self.andamento is None:
            return ""
        linhas = []
        for eid in self.andamento.etapas:
            s = self.andamento.situacao.get(eid)
            if s is None or s.situacao not in ("pendente", "nao_iniciado"):
                continue
            detalhe = s.detalhe
            if eid == "contas":
                detalhe = etapas.Contas(self.ctx).mudancas()
            linhas.append(f"• {perfis.NOMES[eid]}: {detalhe or 'aplicar'}")
        return "Rodar a preparação?\n\n" + "\n".join(linhas)

    def _rodar(self) -> None:
        if self.andamento is None:
            return
        if not confirmar(self, "Preparação completa", self.confirmacao()):
            return
        self._preparar_ctx()
        self.pausar.clear()
        andamento, lista, pausar = self.andamento, self.etapas, self.pausar
        self._ocupar(True)
        self._linha(f"Preparação ({perfis.POR_ID[andamento.perfil].nome}) iniciada.")
        tarefa.iniciar(
            lambda: prep.rodar(lista, andamento, pausar=pausar, avisar=self.sinais.etapa.emit),
            self._terminou,
            self._falhou,
        )

    def _pausar(self) -> None:
        self.pausar.set()
        self.b_pausar.setEnabled(False)
        self._linha("Pausa pedida: para depois da etapa atual.")

    def _terminou(self, a: prep.Andamento) -> None:
        self.andamento = a
        for eid in a.etapas:
            self._etapa_mudou(eid)
        self._ocupar(False)
        self.selo.emit(a.selo())
        pendentes = [
            e
            for e in a.etapas
            if a.situacao.get(e, prep.Leitura("nao_iniciado")).situacao != "feito"
        ]
        self._linha(f"Feitas: {a.selo()}.")
        self.b_reiniciar.setVisible(a.reinicio)
        if not pendentes and self.guardado is not None:
            retomada.descartar()
            self.guardado = None

    def _falhou(self, motivo: str) -> None:
        self._linha(f"Falha: {motivo}")
        self._ocupar(False)

    def _etapa_mudou(self, eid: str) -> None:
        if self.andamento is None:
            return
        s = self.andamento.situacao.get(eid)
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item is None or item.data(0, Qt.ItemDataRole.UserRole) != eid or s is None:
                continue
            item.setText(1, prep.ROTULO[s.situacao])
            item.setText(2, s.detalhe)
            item.setToolTip(2, txt.dica(s.detalhe))
            item.setForeground(1, QColor(tema.cor_situacao(COR[s.situacao])))
            if s.situacao in ("feito", "falhou", "bloqueada", "aguardando_reinicio"):
                self._linha(f"{perfis.NOMES[eid]}: {prep.ROTULO[s.situacao]}. {s.detalhe}".strip())

    def _reiniciar(self) -> None:
        anterior = self.guardado
        if anterior is not None and not anterior.pode_reiniciar:
            self._aviso(
                "Esta preparação já reiniciou 2 vezes. Confira a etapa que pede reinício na "
                "tela dela; o Bench não reinicia de novo por aqui."
            )
            return
        if not confirmar(
            self,
            "Reiniciar",
            "Reiniciar o computador agora?\n\nSalve o que estiver aberto. Depois, abra o ITC "
            "Bench, entre e escolha Continuar.",
        ):
            return
        estado = retomada.novo(
            self.perfil_atual().id,
            self.desmarcadas(),
            self.ctx.nome,
            list(self.ctx.alvos),
            anterior=anterior,
        )
        try:
            retomada.gravar(estado)
        except OSError as erro:
            self._aviso(f"Não foi possível guardar a preparação ({type(erro).__name__}).")
            return
        self.guardado = estado
        f = identificacao.reiniciar()
        self._linha(f.mensagem)
        if not f.ok:
            self._aviso(f.mensagem)

    # ---- tela

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pendentes = 0
        if self.andamento is not None:
            fora = set(self.desmarcadas())
            pendentes = sum(
                1
                for e in self.andamento.etapas
                if e not in fora
                and self.andamento.situacao.get(e, prep.Leitura("nao_iniciado")).situacao
                in ("pendente", "nao_iniciado")
            )
        self.b_rodar.setText(f"Rodar {pendentes} etapa(s)" if pendentes else "Rodar etapas")
        self.b_rodar.setEnabled(self.admin and not ocupado and pendentes > 0)
        if not self.admin:
            self.b_rodar.setToolTip("Precisa de administrador.")
        self.b_ler.setEnabled(not ocupado)
        self.b_pausar.setEnabled(ocupado)
        self.perfil.setEnabled(not ocupado)
        self.nome.setEnabled(not ocupado and self.admin)
        self.b_reiniciar.setEnabled(not ocupado and self.admin)

    def _linha(self, texto: str) -> None:
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {texto}")

    def _aviso(self, texto: str) -> None:
        caixa = QMessageBox(QMessageBox.Icon.Warning, "Preparação completa", texto, parent=self)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
