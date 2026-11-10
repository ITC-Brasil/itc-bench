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
from itc_bench.servicos.identificacao import Estado
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
    "Configura o computador num passo só: nome e usuários. Nada reinicia sem confirmação.\n\n"
    "Nome do computador\n"
    "1. A tela já traz o nome atual (ou o que vale depois de reiniciar). Para trocar, digite o "
    "nome inteiro, como deve ficar (o Bench não sugere nem completa).\n"
    "2. Use até 15 letras sem acento, números e hífen; o hífen não fica na ponta, e o nome não "
    "pode ter só números. O Bench passa tudo para maiúsculas.\n\n"
    "Usuários\n"
    "3. Marque os turnos (Manhã, Tarde, Noite) que vão usar a máquina. Cada turno vira uma conta "
    "NOME-Manha, NOME-Tarde ou NOME-Noite.\n"
    "4. Sem turno marcado, o sufixo opcional cria uma conta só, NOME-Sufixo. Sem turno e sem "
    "sufixo, a conta fica com o nome do computador. Com turno marcado, o sufixo é ignorado.\n"
    "5. Confira a prévia e clique em Renomear e criar usuários. O Bench renomeia (se o nome "
    "mudou) e cria as contas Local (padrão), sem senha; a que já existe não é recriada. Se o "
    "renomear falhar, nenhuma conta é criada.\n"
    "6. No fim, o resumo mostra o que foi criado, o que já existia e o que deu erro, e o Bench "
    "pergunta se pode reiniciar. O nome novo só vale depois de reiniciar.\n\n"
    "Nome de conta tem até 20 caracteres: se passar, encurte o sufixo ou o nome.\n\n"
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
        *([f"Nome: {resumo.renomeio.mensagem}"] if resumo.renomeio else []),
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
    """Nome do computador e usuários num bloco só; o reinício só é oferecido depois de criar."""

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

        quadro, b = _bloco("Configuração do computador")
        b.addWidget(_rotulo("Nome do computador"))
        self.nome = QLineEdit()
        self.nome.setMaxLength(15)
        self.nome.setPlaceholderText("Nome inteiro, até 15 caracteres")
        self.nome.textChanged.connect(self._atualizar)
        b.addWidget(self.nome)
        self.erro = _rotulo()
        self.erro.setObjectName("dica")
        b.addWidget(self.erro)

        b.addWidget(_rotulo("Turnos"))
        linha = QHBoxLayout()
        self.turnos: dict[str, QCheckBox] = {}
        for turno in contas_turno.TURNOS:
            caixa = QCheckBox(ROTULO_TURNO[turno])
            caixa.toggled.connect(self._atualizar)
            self.turnos[turno] = caixa
            linha.addWidget(caixa)
        linha.addStretch()
        b.addLayout(linha)
        b.addWidget(_rotulo("Sufixo personalizado (opcional)"))
        self.sufixo = QLineEdit()
        self.sufixo.setMaxLength(20)
        self.sufixo.setPlaceholderText("Exemplo: Recepcao, Guiche, Administrativo")
        self.sufixo.textChanged.connect(self._atualizar)
        b.addWidget(self.sufixo)
        self.dica_sufixo = _rotulo()
        self.dica_sufixo.setObjectName("dica")
        b.addWidget(self.dica_sufixo)

        b.addWidget(_rotulo("Prévia"))
        self.previa = _rotulo()
        b.addWidget(self.previa)
        self.motivo = _rotulo()
        self.motivo.setObjectName("dica")
        b.addWidget(self.motivo)
        botoes = QHBoxLayout()
        botoes.addStretch()
        self.b_executar = QPushButton("Renomear e criar usuários")
        self.b_executar.setObjectName("primario")
        self.b_executar.clicked.connect(self._executar)
        botoes.addWidget(self.b_executar)
        botoes.addStretch()
        b.addLayout(botoes)
        self.resultado = _rotulo()
        b.addWidget(self.resultado)
        v.addWidget(quadro)
        v.addStretch()
        self._ocupar(False)

    # ------------------------------------------------------------ leitura

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
        if not self.nome.text().strip():
            self.nome.setText(estado.pendente.upper())  # o operador só digita se for trocar
        self._ocupar(False)
        self._carregar_contas()

    def _falhou(self, motivo: str) -> None:
        self.situacao.setText(f"Não foi possível ler o nome: {motivo}")
        self._ocupar(False)

    def _carregar_contas(self) -> None:
        tarefa.iniciar(contas.listar, self._recebeu_contas, self._falhou_contas)

    def _recebeu_contas(self, lista: Lista) -> None:
        self.lista = lista
        self._atualizar()

    def _falhou_contas(self, motivo: str) -> None:
        self.lista = None
        self.resultado.setText(f"Não foi possível ler as contas: {motivo}")
        self._atualizar()

    # ------------------------------------------------------------ regras da tela

    def nome_base(self) -> str:
        """O nome digitado (já preenchido com o que vale depois de reiniciar), em maiúsculas."""
        return identificacao.normalizar(self.nome.text())

    def precisa_renomear(self) -> bool:
        return self.estado is not None and self.nome_base() != self.estado.pendente.upper()

    def _problema_nome(self) -> str | None:
        nome = self.nome_base()
        if not nome:
            return "Digite o nome do computador."
        if self.estado is not None and not self.precisa_renomear():
            return None  # já é (ou já vai ser) esse nome: só cria as contas
        return identificacao.validar(nome, self.estado)

    def _marcados(self) -> tuple[str, ...]:
        return tuple(t for t, caixa in self.turnos.items() if caixa.isChecked())

    def _protegidas(self) -> frozenset[str]:
        return contas.protegidas(self.obter_cadastros())

    def _previstos(self) -> tuple[Previsto, ...]:
        return contas_turno.previa(
            self.nome_base(), self._marcados(), self.sufixo.text(), self.lista, self._protegidas()
        )

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        self._atualizar()

    def _atualizar(self) -> None:
        if not hasattr(self, "b_executar"):
            return  # sinais disparados enquanto a tela é montada
        problema_nome = self._problema_nome() if self.nome.text().strip() else None
        self.erro.setText(problema_nome or "")
        marcados = self._marcados()
        self.sufixo.setEnabled(not marcados)
        self.dica_sufixo.setText(
            "Com turno marcado, o sufixo é ignorado."
            if marcados and self.sufixo.text().strip()
            else ""
        )
        previstos = self._previstos()
        linhas = [linha_previa(p) for p in previstos]
        if self.estado is not None and self.precisa_renomear() and problema_nome is None:
            linhas.insert(0, f"✓ Renomear {self.estado.pendente.upper()} → {self.nome_base()}")
        self.previa.setText("\n".join(linhas) or "—")
        motivo = ""
        if not self.admin:
            motivo = "Exige administrador."
        elif self.estado is None:
            motivo = "Aguarde a leitura do nome do computador ou clique em Atualizar."
        elif problema_nome or not self.nome_base():
            motivo = "Corrija o nome do computador."
        elif any(p.problema for p in previstos):
            motivo = "Corrija o que está marcado com ✕ antes de continuar."
        elif all(p.existe for p in previstos) and not self.precisa_renomear():
            motivo = "Nada a fazer: o nome já é esse e as contas já existem."
        self.motivo.setText(motivo)
        self.b_executar.setText(
            "Renomear e criar usuários" if self.precisa_renomear() else "Criar usuários"
        )
        self.b_executar.setEnabled(not self.ocupado and not motivo and bool(previstos))

    # ------------------------------------------------------------ execução

    def _executar(self) -> None:
        if self.motivo.text() or self.estado is None:
            aviso(self, "Configuração do computador", self.motivo.text() or "Nada a fazer.")
            return
        nome, renomear = self.nome_base(), self.precisa_renomear()
        novas = [p.nome for p in self._previstos() if not p.existe]
        partes = []
        if renomear:
            partes.append(
                f"Renomear o computador de {self.estado.pendente.upper()} para {nome} "
                "(vale depois de reiniciar)."
            )
        if novas:
            partes.append(
                "Criar estas contas Local (padrão), sem senha:\n"
                + "\n".join(f"• {n}" for n in novas)
            )
        texto = "\n\n".join(partes) + "\n\nContinuar?"
        if not confirmar(self, "Configuração do computador", texto):
            return
        marcados, sufixo, prot = self._marcados(), self.sufixo.text(), self._protegidas()
        self._ocupar(True)
        self.resultado.setText(
            "Renomeando e criando usuários…" if renomear else "Criando usuários…"
        )
        tarefa.iniciar(
            lambda: contas_turno.configurar(
                nome, marcados, sufixo, renomear=renomear, protegidas_=prot
            ),
            self._terminou,
            self._falhou_execucao,
        )

    def _terminou(self, resumo: Resumo) -> None:
        self._ocupar(False)
        if resumo.renomeio is not None and not resumo.renomeio.ok:
            self.resultado.setText(
                f"✕ O computador não foi renomeado: {resumo.renomeio.mensagem}\n"
                "Nenhuma conta foi criada."
            )
            aviso(self, "Configuração do computador", resumo.renomeio.mensagem)
            self.carregar()
            return
        self.resultado.setText(texto_resumo(resumo))
        self.carregar()
        self._perguntar_reinicio()

    def _falhou_execucao(self, motivo: str) -> None:
        self.resultado.setText(f"✕ Não foi possível concluir: {motivo}")
        self._ocupar(False)
        aviso(self, "Configuração do computador", f"Não foi possível concluir: {motivo}")

    def _perguntar_reinicio(self) -> None:
        """Único lugar que reinicia, e só com duas confirmações (ADR-023, item 5; ADR-029)."""
        if not escolher(
            self, "Configuração concluída", TEXTO_REINICIO, "Reiniciar agora", "Deixar para depois"
        ):
            caixa = QMessageBox(
                QMessageBox.Icon.Information, "Configuração concluída", TEXTO_DEPOIS, parent=self
            )
            caixa.setTextFormat(Qt.TextFormat.PlainText)
            caixa.exec()
            return
        if not escolher(
            self,
            "Reiniciar",
            "O computador será reiniciado agora.\n\nDeseja continuar?",
            "Sim, reiniciar",
            "Cancelar",
        ):
            return
        feito = identificacao.reiniciar()
        if not feito.ok:
            aviso(self, "Reiniciar", feito.mensagem)
            return
        self.situacao.setText(feito.mensagem)
        # Fecha pela janela, para o closeEvent fazer o encerramento normal do Bench.
        self.window().close()
