"""Tela Identificação (ADR-018). Regras e execução em `servicos/identificacao.py`; aqui só tela."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from itc_bench.servicos import identificacao
from itc_bench.servicos.identificacao import Estado, Feito
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _bloco, _rotulo, confirmar

AJUDA = (
    "Troca o nome do computador. O nome novo só vale depois de reiniciar.\n\n"
    "Renomear\n"
    "1. Digite o nome inteiro, como deve ficar (o Bench não sugere nem completa).\n"
    "2. Use até 15 letras sem acento, números e hífen; o hífen não fica na ponta, e o nome não "
    "pode ter só números. O Bench passa tudo para maiúsculas.\n"
    "3. Clique em Renomear e confirme.\n"
    "4. Reinicie agora ou depois. Até reiniciar, a tela mostra o nome atual e o que vale "
    "depois.\n\n"
    "Quando renomear\n"
    "Antes do diagnóstico: o histórico da máquina fica guardado pelo nome. Depois de reiniciar, "
    "as coletas novas aparecem com o nome novo.\n\n"
    "O que o Bench não deixa fazer\n"
    "Renomear máquina em domínio ou Azure AD; usar o nome de uma conta ou grupo local, ou um "
    "nome reservado do Windows.\n\n"
    "Sem administrador (modo de teste), a tela só mostra o nome."
)


def aviso(pai: QWidget, titulo: str, texto: str) -> None:
    """Mensagem do Windows só como texto puro (ADR-015)."""
    caixa = QMessageBox(QMessageBox.Icon.Warning, titulo, texto, parent=pai)
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    caixa.exec()


class PainelIdentificacao(QWidget):
    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.estado: Estado | None = None
        self.ocupado = False

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.situacao = _rotulo("Lendo o nome do computador…")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        topo.addWidget(self.situacao, 1)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só leitura."))

        quadro, b = _bloco("Novo nome do computador")
        self.nome = QLineEdit()
        self.nome.setMaxLength(15)
        self.nome.setPlaceholderText("Nome inteiro, até 15 caracteres")
        self.nome.textChanged.connect(self._validar)
        b.addWidget(self.nome)
        self.erro = _rotulo()
        self.erro.setObjectName("dica")
        b.addWidget(self.erro)
        botoes = QHBoxLayout()
        self.b_renomear = QPushButton("Renomear")
        self.b_renomear.setObjectName("primario")
        self.b_renomear.clicked.connect(self._renomear)
        self.b_reiniciar = QPushButton("Reiniciar agora")
        self.b_reiniciar.clicked.connect(self._reiniciar)
        botoes.addWidget(self.b_renomear)
        botoes.addWidget(self.b_reiniciar)
        botoes.addStretch()
        b.addLayout(botoes)
        v.addWidget(quadro)
        v.addStretch()
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if self.estado is None and not self.ocupado:
            self.carregar()

    def carregar(self) -> None:
        self._ocupar(True)
        tarefa.iniciar(identificacao.estado, self._recebeu, self._falhou)

    def _recebeu(self, estado: Estado) -> None:
        self.estado = estado
        texto = f"Nome atual: {estado.ativo}"
        if estado.reinicio_pendente:
            texto += f" · Depois de reiniciar: {estado.pendente.upper()}"
        if estado.dominio:
            texto += " · Em domínio ou Azure AD"
        self.situacao.setText(texto)
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.situacao.setText(f"Não foi possível ler o nome: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        pendente = self.estado is not None and self.estado.reinicio_pendente
        self.b_reiniciar.setEnabled(self.admin and not ocupado and pendente)
        self._validar()

    def _validar(self) -> None:
        nome = identificacao.normalizar(self.nome.text())
        problema = identificacao.validar(nome, self.estado) if nome else None
        self.erro.setText(problema or ("" if self.admin else "Exige administrador."))
        self.b_renomear.setEnabled(
            self.admin
            and not self.ocupado
            and self.estado is not None
            and bool(nome)
            and problema is None
        )

    def _renomear(self) -> None:
        nome = identificacao.normalizar(self.nome.text())
        atual = self.estado.ativo if self.estado else "?"
        if not confirmar(
            self,
            "Renomear o computador",
            f"Trocar o nome de {atual} para {nome}?\n\nO nome novo só vale depois de reiniciar.",
        ):
            return
        self._ocupar(True)
        self.situacao.setText("Renomeando…")
        tarefa.iniciar(lambda: identificacao.renomear(nome), self._terminou, self._falhou)

    def _terminou(self, feito: Feito) -> None:
        if feito.ok:
            self.nome.clear()
            if confirmar(self, "Renomear o computador", feito.mensagem + "\n\nReiniciar agora?"):
                self._reiniciar(confirmado=True)
        else:
            aviso(self, "Renomear o computador", feito.mensagem)
        self.carregar()

    def _reiniciar(self, confirmado: bool = False) -> None:
        if not confirmado and not confirmar(
            self, "Reiniciar", "Reiniciar o Windows agora? Salve o que estiver aberto."
        ):
            return
        feito = identificacao.reiniciar()
        if not feito.ok:
            aviso(self, "Reiniciar", feito.mensagem)
        else:
            self.situacao.setText(feito.mensagem)
