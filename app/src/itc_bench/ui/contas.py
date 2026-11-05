"""Tela Contas (ADR-017). Regras e execução em `servicos/contas.py`; aqui só tela.

Nome de conta vem do Windows e é texto livre: só em widget de texto puro, nunca rich text.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import contas
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.contas import Conta, Feito, Lista
from itc_bench.servicos.executor import Sensivel
from itc_bench.ui import tarefa

AJUDA = (
    "Cria, altera e exclui contas locais. A lista mostra o tipo de cada conta (Administrador ou "
    "Local padrão) e marca você, a conta nativa, a Suporte, as contas Microsoft e as "
    "desativadas.\n\n"
    "Criar uma conta\n"
    "1. Preencha o nome, com até 20 caracteres.\n"
    "2. Digite a senha duas vezes, ou deixe vazio para criar sem senha.\n"
    "3. Escolha Local (padrão) ou Administrador.\n"
    "4. Se quiser, em Clonar grupos de escolha uma conta existente: a nova entra nos mesmos "
    "grupos (menos Administradores, que segue o tipo escolhido). Pastas e arquivos não são "
    "copiados.\n"
    "5. Clique em Criar conta e confirme o resumo.\n\n"
    "Mudar o tipo, trocar a senha ou excluir\n"
    "1. Clique na conta na lista.\n"
    "2. Use Tornar Administrador ou Tornar Local, ou digite a nova senha duas vezes e clique em "
    "Alterar senha.\n"
    "3. Para excluir, decida se apaga a pasta e digite o nome para confirmar.\n\n"
    "Conta Suporte e ações em lote\n"
    "• Aplicar conta Suporte cria a conta (ou troca a senha, ativa e torna administradora) com o "
    "nome e a senha de Configurações › Servidores. Sem cadastro sincronizado, não roda.\n"
    "• Tornar todos administradores: para a preparação ou a manutenção, quando é preciso rodar "
    "coisas fora do Bench.\n"
    "• Remover administrador de todos (exceto Suporte): ao terminar. Inclui a conta em uso, que "
    "vira comum na próxima entrada. Só roda com a Suporte ativa e administradora.\n\n"
    "O que o Bench não deixa fazer\n"
    "Mexer no Administrador nativo e nas contas Microsoft ou de domínio; alterar a Suporte fora "
    "de Aplicar conta Suporte; rebaixar, excluir ou trocar a senha da conta em uso; excluir "
    "conta com sessão aberta; rebaixar ou excluir o último administrador ativo.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a lista."
)

SEM_CLONE = "Nenhum"


def _rotulo(texto: str = "") -> QLabel:
    r = QLabel(texto)
    r.setTextFormat(Qt.TextFormat.PlainText)
    r.setWordWrap(True)
    return r


def _senha(dica: str) -> QLineEdit:
    campo = QLineEdit()
    campo.setEchoMode(QLineEdit.EchoMode.Password)
    campo.setPlaceholderText(dica)
    return campo


def _bloco(titulo: str) -> tuple[QFrame, QVBoxLayout]:
    quadro = QFrame()
    quadro.setObjectName("cartao")
    v = QVBoxLayout(quadro)
    v.setContentsMargins(12, 10, 12, 10)
    nome = _rotulo(titulo)
    nome.setObjectName("subtitulo")
    v.addWidget(nome)
    return quadro, v


def confirmar(pai: QWidget, titulo: str, texto: str) -> bool:
    caixa = QMessageBox(QMessageBox.Icon.Question, titulo, texto, parent=pai)
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    caixa.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    caixa.setDefaultButton(QMessageBox.StandardButton.No)
    return caixa.exec() == QMessageBox.StandardButton.Yes


def marcas(c: Conta, prot: frozenset[str]) -> str:
    m = []
    if c.logada:
        m.append("em uso")
    if c.nativo:
        m.append("nativa")
    if c.nome.lower() in prot:
        m.append("Suporte")
    if not c.local:
        m.append("Conta Microsoft")
    if c.carregado and not c.logada:
        m.append("sessão aberta")
    return ", ".join(m)


class ConfirmarExclusao(QDialog):
    """Resumo, caixa de apagar a pasta e o nome digitado para liberar o botão."""

    def __init__(self, pai: QWidget, conta: Conta, tamanho: int | None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Excluir conta")
        self.nome = conta.nome
        v = QVBoxLayout(self)
        tipo = "Administrador" if conta.admin else "Local padrão"
        if conta.perfil is None:
            pasta = "sem pasta"
        elif tamanho is None:
            pasta = "pasta com tamanho não calculado"
        else:
            pasta = f"pasta com cerca de {tamanho / 1024**3:.1f} GB"
        v.addWidget(
            _rotulo(f"Excluir a conta {conta.nome} ({tipo}, {pasta})? Não dá para desfazer.")
        )
        self.apagar = QCheckBox("Apagar também a pasta e os arquivos da conta (irreversível)")
        self.apagar.setEnabled(conta.perfil is not None)
        v.addWidget(self.apagar)
        v.addWidget(_rotulo("Digite o nome da conta para confirmar:"))
        self.digitado = QLineEdit()
        v.addWidget(self.digitado)
        self.botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Excluir")
        self.botoes.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        v.addWidget(self.botoes)
        self.digitado.textChanged.connect(
            lambda t: self.botoes.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                t == self.nome
            )
        )


class PainelContas(QWidget):
    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__()
        self.admin, self.obter_cadastros = admin, obter_cadastros
        self.lista: Lista | None = None
        self.ocupado = False
        self.acoes: list[QWidget] = []

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.estado = _rotulo("Lendo contas…")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só leitura."))

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["Nome", "Tipo", "Situação", "Última entrada", "Marcas"]
        )
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.itemSelectionChanged.connect(self._selecao)
        v.addWidget(self.tabela, 1)
        self.outros = _rotulo()
        v.addWidget(self.outros)

        linha = QHBoxLayout()
        # Conta selecionada
        quadro, s = _bloco("Conta selecionada")
        self.b_admin = QPushButton("Tornar Administrador")
        self.b_padrao = QPushButton("Tornar Local")
        self.b_admin.clicked.connect(lambda: self._tipo("admin"))
        self.b_padrao.clicked.connect(lambda: self._tipo("padrao"))
        tipos = QHBoxLayout()
        tipos.addWidget(self.b_admin)
        tipos.addWidget(self.b_padrao)
        s.addLayout(tipos)
        self.nova1, self.nova2 = _senha("Nova senha"), _senha("Repita a nova senha")
        s.addWidget(self.nova1)
        s.addWidget(self.nova2)
        senhas = QHBoxLayout()
        self.b_senha = QPushButton("Alterar senha")
        self.b_sem = QPushButton("Remover senha")
        self.b_senha.clicked.connect(self._alterar_senha)
        self.b_sem.clicked.connect(self._remover_senha)
        senhas.addWidget(self.b_senha)
        senhas.addWidget(self.b_sem)
        s.addLayout(senhas)
        self.b_excluir = QPushButton("Excluir conta…")
        self.b_excluir.setObjectName("perigo")
        self.b_excluir.clicked.connect(self._excluir)
        s.addWidget(self.b_excluir)
        self.motivo = _rotulo()
        self.motivo.setObjectName("dica")
        s.addWidget(self.motivo)
        s.addStretch()
        linha.addWidget(quadro, 1)

        # Criar
        quadro, c = _bloco("Criar conta")
        grade = QGridLayout()
        self.nome = QLineEdit()
        self.nome.setMaxLength(20)
        self.nome.setPlaceholderText("Até 20 caracteres")
        self.nome.textChanged.connect(self._validar)
        self.senha1, self.senha2 = _senha("Vazio = sem senha"), _senha("Repita a senha")
        self.senha1.textChanged.connect(self._validar)
        self.senha2.textChanged.connect(self._validar)
        self.r_padrao, self.r_admin = QRadioButton("Local (padrão)"), QRadioButton("Administrador")
        self.r_padrao.setChecked(True)
        grupo = QButtonGroup(self)
        grupo.addButton(self.r_padrao)
        grupo.addButton(self.r_admin)
        tipo = QHBoxLayout()
        tipo.addWidget(self.r_padrao)
        tipo.addWidget(self.r_admin)
        tipo.addStretch()
        self.clone = QComboBox()
        self.nunca = QCheckBox("A senha nunca expira")
        self.nunca.setChecked(True)
        for i, (rotulo, campo) in enumerate(
            (
                ("Nome", self.nome),
                ("Senha", self.senha1),
                ("", self.senha2),
                ("Clonar grupos de", self.clone),
            )
        ):
            grade.addWidget(_rotulo(rotulo), i, 0)
            grade.addWidget(campo, i, 1)
        c.addLayout(grade)
        c.addLayout(tipo)
        c.addWidget(self.nunca)
        self.erro_nome = _rotulo()
        self.erro_nome.setObjectName("dica")
        c.addWidget(self.erro_nome)
        self.b_criar = QPushButton("Criar conta")
        self.b_criar.setObjectName("primario")
        self.b_criar.clicked.connect(self._criar)
        c.addWidget(self.b_criar)
        c.addStretch()
        linha.addWidget(quadro, 1)

        # Lote
        quadro, lo = _bloco("Suporte e todas as contas")
        self.b_suporte = QPushButton("Aplicar conta Suporte")
        self.b_todos_admin = QPushButton("Tornar todos administradores")
        self.b_todos_padrao = QPushButton("Remover administrador de todos (exceto Suporte)")
        self.b_suporte.clicked.connect(self._suporte)
        self.b_todos_admin.clicked.connect(lambda: self._lote("admin"))
        self.b_todos_padrao.clicked.connect(lambda: self._lote("padrao"))
        for b in (self.b_suporte, self.b_todos_admin, self.b_todos_padrao):
            lo.addWidget(b)
        lo.addStretch()
        linha.addWidget(quadro, 1)
        v.addLayout(linha)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        # Lê ao abrir a tela, não ao montar a janela (a lista roda PowerShell).
        super().showEvent(evento)
        if self.lista is None and not self.ocupado:
            self.carregar()

    # ------------------------------------------------------------ dados

    def prot(self) -> frozenset[str]:
        return contas.protegidas(self.obter_cadastros())

    def carregar(self) -> None:
        self.estado.setText("Lendo contas…")
        self._ocupar(True)
        tarefa.iniciar(contas.listar, self._recebeu, self._falhou_leitura)

    def _recebeu(self, lista: Lista) -> None:
        self.lista = lista
        sid = self._sid()
        prot = self.prot()
        self.tabela.setRowCount(len(lista.contas))
        for i, c in enumerate(lista.contas):
            ultima = c.ultima.astimezone().strftime("%d/%m/%Y %H:%M") if c.ultima else "nunca"
            valores = (
                c.nome,
                "Administrador" if c.admin else "Local padrão",
                "ativa" if c.ativo else "desativada",
                ultima,
                marcas(c, prot),
            )
            for j, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setData(Qt.ItemDataRole.UserRole, c.sid)
                self.tabela.setItem(i, j, item)
            if c.sid == sid:
                self.tabela.selectRow(i)
        self.outros.setText(
            "Outros administradores (domínio/Azure AD, só leitura): "
            + ", ".join(lista.outros_admins)
            if lista.outros_admins
            else ""
        )
        self.clone.clear()
        self.clone.addItem(SEM_CLONE, "")
        for c in lista.contas:
            if c.local:
                self.clone.addItem(c.nome, c.sid)
        self.estado.setText(f"{len(lista.contas)} conta(s) local(is).")
        self._ocupar(False)

    def _falhou_leitura(self, motivo: str) -> None:
        self.estado.setText(f"Não foi possível ler as contas: {motivo}")
        self._ocupar(False)

    def _sid(self) -> str | None:
        linhas = self.tabela.selectionModel().selectedRows() if self.tabela.selectionModel() else []
        if not linhas:
            return None
        item = self.tabela.item(linhas[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _conta(self) -> Conta | None:
        sid = self._sid()
        return self.lista.por_sid(sid) if self.lista and sid else None

    # ------------------------------------------------------------ estado dos botões

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        self._selecao()
        self._validar()
        for b in (self.b_suporte, self.b_todos_admin, self.b_todos_padrao):
            b.setEnabled(self.admin and not ocupado and self.lista is not None)

    def _selecao(self) -> None:
        conta = self._conta()
        botoes: dict[QPushButton, contas.Acao] = {
            self.b_admin: "admin",
            self.b_padrao: "padrao",
            self.b_senha: "senha",
            self.b_sem: "sem_senha",
            self.b_excluir: "excluir",
        }
        motivos = []
        for botao, acao in botoes.items():
            motivo = None
            if conta is not None and self.lista is not None:
                motivo = contas.recusa(acao, conta, self.lista, self.prot())
            botao.setEnabled(
                self.admin and not self.ocupado and conta is not None and motivo is None
            )
            if motivo:
                motivos.append(contas.MENSAGENS[motivo])
        if not self.admin:
            self.motivo.setText("Exige administrador.")
        elif conta is None:
            self.motivo.setText("Selecione uma conta na lista.")
        else:
            self.motivo.setText(" ".join(dict.fromkeys(motivos)))

    def _validar(self) -> None:
        nome = self.nome.text().strip()
        problema = contas.validar_nome(nome, self.lista, self.prot()) if nome else None
        if problema is None and self.senha1.text() != self.senha2.text():
            problema = "As senhas não conferem."
        self.erro_nome.setText(problema or "")
        self.b_criar.setEnabled(self.admin and not self.ocupado and bool(nome) and problema is None)

    # ------------------------------------------------------------ ações

    def _rodar(self, funcao: Callable[[], Feito]) -> None:
        self._ocupar(True)
        self.estado.setText("Aplicando…")
        tarefa.iniciar(funcao, self._terminou, self._falhou)

    def _terminou(self, feito: Feito) -> None:
        texto = feito.mensagem
        if feito.alteradas:
            texto += " " + ", ".join(feito.alteradas)
        if feito.avisos:
            texto += " Avisos: " + "; ".join(feito.avisos)
        caixa = QMessageBox(
            QMessageBox.Icon.Information if feito.ok else QMessageBox.Icon.Warning,
            "Contas",
            texto,
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
        self.carregar()

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)
        self.carregar()

    def _tipo(self, tipo: Any) -> None:
        conta = self._conta()
        if conta is None:
            return
        rotulo = "Administrador" if tipo == "admin" else "Local padrão"
        aviso = "\n\nA conta terá controle total do computador." if tipo == "admin" else ""
        if confirmar(self, "Tipo de conta", f"Tornar {conta.nome} {rotulo}?{aviso}"):
            prot = self.prot()
            self._rodar(lambda: contas.definir_tipo(conta.sid, tipo, protegidas_=prot))

    def _alterar_senha(self) -> None:
        conta = self._conta()
        if conta is None:
            return
        if not self.nova1.text():
            QMessageBox.warning(self, "Senha", "Digite a nova senha, ou use Remover senha.")
            return
        if self.nova1.text() != self.nova2.text():
            QMessageBox.warning(self, "Senha", "As senhas não conferem.")
            return
        senha = Sensivel(self.nova1.text())
        self.nova1.clear()
        self.nova2.clear()
        if confirmar(self, "Alterar senha", f"Alterar a senha de {conta.nome}?"):
            prot = self.prot()
            self._rodar(lambda: contas.trocar_senha(conta.sid, senha, protegidas_=prot))

    def _remover_senha(self) -> None:
        conta = self._conta()
        if conta and confirmar(
            self, "Remover senha", f"Deixar {conta.nome} sem senha? Qualquer pessoa entra nela."
        ):
            prot = self.prot()
            self._rodar(lambda: contas.trocar_senha(conta.sid, None, protegidas_=prot))

    def _excluir(self) -> None:
        conta = self._conta()
        if conta is None:
            return
        dialogo = ConfirmarExclusao(self, conta, contas.tamanho_perfil(conta.perfil))
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            apagar, prot = dialogo.apagar.isChecked(), self.prot()
            self._rodar(lambda: contas.excluir(conta.sid, apagar, protegidas_=prot))

    def _criar(self) -> None:
        nome = self.nome.text().strip()
        tipo: Any = "admin" if self.r_admin.isChecked() else "padrao"
        senha = Sensivel(self.senha1.text()) if self.senha1.text() else None
        clonar = self.clone.currentData() or None
        avisos = []
        if tipo == "admin":
            avisos.append("A conta terá controle total do computador (Administrador).")
        if senha is None:
            avisos.append("A conta será criada SEM SENHA.")
        if clonar:
            avisos.append(f"Entra nos mesmos grupos de {self.clone.currentText()}.")
        resumo = f"Criar a conta {nome} ({'Administrador' if tipo == 'admin' else 'Local padrão'})?"
        if not confirmar(
            self, "Criar conta", resumo + ("\n\n" + "\n".join(avisos) if avisos else "")
        ):
            return
        nunca, prot = self.nunca.isChecked(), self.prot()
        for campo in (self.nome, self.senha1, self.senha2):
            campo.clear()
        self._rodar(
            lambda: contas.criar(
                nome, senha, tipo, clonar_sid=clonar, nunca_expira=nunca, protegidas_=prot
            )
        )

    def _suporte(self) -> None:
        cadastros = self.obter_cadastros()
        origem = contas.suporte_do_cadastro(cadastros)
        if isinstance(origem, str):
            QMessageBox.warning(self, "Conta Suporte", origem)
            return
        if confirmar(
            self,
            "Conta Suporte",
            f"Aplicar a conta {origem[0]}: cria se faltar, ou troca a senha pela do "
            "cadastro, ativa e torna administradora?",
        ):
            self._rodar(lambda: contas.aplicar_suporte(cadastros))

    def _lote(self, tipo: Any) -> None:
        if self.lista is None:
            return
        prot = self.prot()
        if tipo == "padrao" and not contas.suporte_ok(self.lista, prot):
            QMessageBox.warning(self, "Contas", contas.MENSAGENS["suporte_ausente"])
            return
        nomes = contas.mudariam(tipo, self.lista, prot)
        if not nomes:
            QMessageBox.information(self, "Contas", "Nenhuma conta precisa mudar.")
            return
        if tipo == "admin":
            texto = "Tornar administradoras estas contas?\n\n" + "\n".join(nomes)
        else:
            texto = "Remover o administrador destas contas (a Suporte fica)?\n\n" + "\n".join(nomes)
            logadas = [c.nome for c in self.lista.contas if c.logada and c.nome in nomes]
            if logadas:
                texto += f"\n\n{', '.join(logadas)} está em uso: vira comum na próxima entrada."
        if confirmar(self, "Todas as contas", texto):
            self._rodar(lambda: contas.lote(tipo, protegidas_=prot))
