"""Tela Identificação (ADR-018, ADR-029). Regras e execução em `servicos/identificacao.py` e
`servicos/contas_turno.py`; aqui só tela."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import contas, contas_turno, identificacao
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.contas import Lista
from itc_bench.servicos.contas_turno import Previsto, Resumo
from itc_bench.servicos.identificacao import Estado, Feito
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _bloco, _rotulo, confirmar

ROTULO_TURNO = {"Manha": "Manhã", "Tarde": "Tarde", "Noite": "Noite"}
TEXTO_REINICIO = (
    "Todas as configurações foram processadas.\n\n"
    "Algumas alterações podem exigir que o computador seja reiniciado para serem completamente "
    "aplicadas.\n\nDeseja reiniciar o computador agora?"
)
TEXTO_DEPOIS = (
    "Configuração concluída.\n\nO computador não será reiniciado neste momento.\n\n"
    "Algumas alterações poderão ser finalizadas somente após o próximo reinício."
)

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
    "Criação de usuários\n"
    "1. O nome base é o nome do computador (o que vale depois de reiniciar): não precisa "
    "digitar de novo.\n"
    "2. Marque os turnos (Manhã, Tarde, Noite) que vão usar a máquina. Cada turno vira uma conta "
    "NOME-Manha, NOME-Tarde ou NOME-Noite.\n"
    "3. Sem turno marcado, o sufixo opcional cria uma conta só, NOME-Sufixo. Sem turno e sem "
    "sufixo, a conta fica com o nome do computador. Com turno marcado, o sufixo é ignorado.\n"
    "4. Confira a prévia e clique em Criar usuários. As contas são Local (padrão), sem senha; "
    "a que já existe não é recriada.\n"
    "5. No fim, o resumo mostra o que foi criado, o que já existia e o que deu erro, e o Bench "
    "pergunta se pode reiniciar. Ele nunca reinicia sem confirmação.\n\n"
    "Nome de conta tem até 20 caracteres: se passar, encurte o sufixo.\n\n"
    "Sem administrador (modo de teste), a tela só mostra o nome."
)


def aviso(pai: QWidget, titulo: str, texto: str) -> None:
    """Mensagem do Windows só como texto puro (ADR-015)."""
    caixa = QMessageBox(QMessageBox.Icon.Warning, titulo, texto, parent=pai)
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    caixa.exec()


def escolher(pai: QWidget, titulo: str, texto: str, sim: str, nao: str) -> bool:
    """Pergunta com dois botões nomeados; o padrão é o `nao` (nada acontece sem escolha)."""
    caixa = QMessageBox(QMessageBox.Icon.Question, titulo, texto, parent=pai)
    caixa.setTextFormat(Qt.TextFormat.PlainText)
    b_sim = caixa.addButton(sim, QMessageBox.ButtonRole.AcceptRole)
    b_nao = caixa.addButton(nao, QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(b_nao)
    caixa.setEscapeButton(b_nao)
    caixa.exec()
    return caixa.clickedButton() is b_sim


def linha_previa(p: Previsto) -> str:
    if p.problema:
        return f"✕ {p.nome} — {p.problema}"
    if p.existe:
        return f"⚠ {p.nome} — já existe, não será recriada"
    return f"✓ {p.nome}"


def texto_resumo(resumo: Resumo) -> str:
    marca = {"criado": "✓", "existia": "⚠", "erro": "✕"}
    linhas = [
        "CONFIGURAÇÃO CONCLUÍDA",
        "",
        f"Computador: {resumo.computador}",
        "",
        "Usuários:",
        *(f"{marca[i.situacao]} {i.nome} — {i.mensagem}" for i in resumo.itens),
        "",
        f"Total criados: {resumo.criados}",
        f"Já existentes: {resumo.existentes}",
        f"Erros: {resumo.erros}",
    ]
    return "\n".join(linhas)


class PainelIdentificacao(QWidget):
    def __init__(
        self, admin: bool, obter_cadastros: Callable[[], Cadastros | None] = lambda: None
    ) -> None:
        super().__init__()
        self.admin = admin
        self.obter_cadastros = obter_cadastros
        self.estado: Estado | None = None
        self.lista: Lista | None = None
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
        v.addWidget(self._montar_usuarios())
        v.addStretch()
        self._ocupar(False)

    def _montar_usuarios(self) -> QWidget:
        quadro, u = _bloco("Criação de usuários")
        u.addWidget(_rotulo("Nome base"))
        self.base = _rotulo("—")
        self.base.setObjectName("subtitulo")
        u.addWidget(self.base)
        u.addWidget(_rotulo("Turnos"))
        linha = QHBoxLayout()
        self.turnos: dict[str, QCheckBox] = {}
        for turno in contas_turno.TURNOS:
            caixa = QCheckBox(ROTULO_TURNO[turno])
            caixa.toggled.connect(self._atualizar_previa)
            self.turnos[turno] = caixa
            linha.addWidget(caixa)
        linha.addStretch()
        u.addLayout(linha)
        u.addWidget(_rotulo("Sufixo personalizado (opcional)"))
        self.sufixo = QLineEdit()
        self.sufixo.setMaxLength(20)
        self.sufixo.setPlaceholderText("Exemplo: Recepcao, Guiche, Administrativo")
        self.sufixo.textChanged.connect(self._atualizar_previa)
        u.addWidget(self.sufixo)
        self.dica_sufixo = _rotulo()
        self.dica_sufixo.setObjectName("dica")
        u.addWidget(self.dica_sufixo)
        u.addWidget(_rotulo("Prévia"))
        self.previa = _rotulo()
        u.addWidget(self.previa)
        self.motivo_usuarios = _rotulo()
        self.motivo_usuarios.setObjectName("dica")
        u.addWidget(self.motivo_usuarios)
        botoes = QHBoxLayout()
        botoes.addStretch()
        self.b_criar = QPushButton("Criar usuários")
        self.b_criar.setObjectName("primario")
        self.b_criar.clicked.connect(self._criar_usuarios)
        botoes.addWidget(self.b_criar)
        botoes.addStretch()
        u.addLayout(botoes)
        self.resultado = _rotulo()
        u.addWidget(self.resultado)
        return quadro

    # ------------------------------------------------------------ criação de usuários

    def nome_base(self) -> str:
        """Nome que vale depois de reiniciar: o renomeado agora ou o que a máquina já tem."""
        return self.estado.pendente.upper() if self.estado else ""

    def _marcados(self) -> tuple[str, ...]:
        return tuple(t for t, caixa in self.turnos.items() if caixa.isChecked())

    def _protegidas(self) -> frozenset[str]:
        return contas.protegidas(self.obter_cadastros())

    def _previstos(self) -> tuple[Previsto, ...]:
        return contas_turno.previa(
            self.nome_base(), self._marcados(), self.sufixo.text(), self.lista, self._protegidas()
        )

    def _atualizar_previa(self) -> None:
        if not hasattr(self, "b_criar"):
            return  # chamado por _ocupar antes de a seção existir
        base = self.nome_base()
        self.base.setText(base or "—")
        marcados = self._marcados()
        self.sufixo.setEnabled(not marcados)
        self.dica_sufixo.setText(
            "Com turno marcado, o sufixo é ignorado."
            if marcados and self.sufixo.text().strip()
            else ""
        )
        previstos = self._previstos()
        self.previa.setText("\n".join(linha_previa(p) for p in previstos) or "—")
        motivo = ""
        if not self.admin:
            motivo = "Exige administrador."
        elif not base:
            motivo = (
                "Sem nome base: aguarde a leitura do nome do computador ou clique em Atualizar."
            )
        elif any(p.problema for p in previstos):
            motivo = "Corrija o que está marcado com ✕ antes de criar."
        elif previstos and all(p.existe for p in previstos):
            motivo = "Todas as contas da prévia já existem."
        self.motivo_usuarios.setText(motivo)
        self.b_criar.setEnabled(not self.ocupado and not motivo and bool(previstos))

    def _carregar_contas(self) -> None:
        tarefa.iniciar(contas.listar, self._recebeu_contas, self._falhou_contas)

    def _recebeu_contas(self, lista: Lista) -> None:
        self.lista = lista
        self._atualizar_previa()

    def _falhou_contas(self, motivo: str) -> None:
        self.lista = None
        self.resultado.setText(f"Não foi possível ler as contas: {motivo}")
        self._atualizar_previa()

    def _criar_usuarios(self) -> None:
        base = self.nome_base()
        previstos = [p for p in self._previstos() if not p.existe]
        if not base or not previstos:
            aviso(self, "Criar usuários", self.motivo_usuarios.text() or "Nada para criar.")
            return
        lista = "\n".join(f"• {p.nome}" for p in previstos)
        if not confirmar(
            self,
            "Criar usuários",
            f"Criar estas contas Local (padrão), sem senha?\n\n{lista}",
        ):
            return
        marcados, sufixo, prot = self._marcados(), self.sufixo.text(), self._protegidas()
        self._ocupar(True)
        self.resultado.setText("Criando usuários…")
        tarefa.iniciar(
            lambda: contas_turno.criar(base, marcados, sufixo, protegidas_=prot),
            self._criou_usuarios,
            self._falhou_usuarios,
        )

    def _criou_usuarios(self, resumo: Resumo) -> None:
        self.resultado.setText(texto_resumo(resumo))
        self._ocupar(False)
        self._carregar_contas()
        self._perguntar_reinicio()

    def _falhou_usuarios(self, motivo: str) -> None:
        self.resultado.setText(f"✕ Não foi possível criar os usuários: {motivo}")
        self._ocupar(False)
        aviso(self, "Criar usuários", f"Não foi possível criar os usuários: {motivo}")

    def _perguntar_reinicio(self) -> None:
        """Nunca reinicia sem duas confirmações (ADR-023, item 5)."""
        if not escolher(
            self, "Configuração concluída", TEXTO_REINICIO, "Reiniciar agora", "Deixar para depois"
        ):
            caixa = QMessageBox(
                QMessageBox.Icon.Information, "Configuração concluída", TEXTO_DEPOIS, parent=self
            )
            caixa.setTextFormat(Qt.TextFormat.PlainText)
            caixa.exec()
            return
        if escolher(
            self,
            "Reiniciar",
            "O computador será reiniciado agora.\n\nDeseja continuar?",
            "Sim, reiniciar",
            "Cancelar",
        ):
            self._reiniciar(confirmado=True, fechar=True)

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
        self._carregar_contas()

    def _falhou(self, motivo: str) -> None:
        self.situacao.setText(f"Não foi possível ler o nome: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        pendente = self.estado is not None and self.estado.reinicio_pendente
        self.b_reiniciar.setEnabled(self.admin and not ocupado and pendente)
        self._validar()
        self._atualizar_previa()

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

    def _reiniciar(self, confirmado: bool = False, fechar: bool = False) -> None:
        if not confirmado and not confirmar(
            self, "Reiniciar", "Reiniciar o Windows agora? Salve o que estiver aberto."
        ):
            return
        feito = identificacao.reiniciar()
        if not feito.ok:
            aviso(self, "Reiniciar", feito.mensagem)
            return
        self.situacao.setText(feito.mensagem)
        if fechar:
            # Fecha pela janela, para o closeEvent fazer o encerramento normal do Bench.
            self.window().close()
