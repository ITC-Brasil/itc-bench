"""Tela Proteção do login (ADR-022, ADR-052). Regras em `servicos/protecao.py`; aqui só tela."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import protecao
from itc_bench.ui import tarefa, tema
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Impede que alguém troque o Utilman (botão de Acessibilidade) ou o Sethc (Shift 5 vezes) "
    "por um Prompt de Comando para redefinir senhas na tela de login.\n\n"
    "Proteger\n"
    "1. Confira no resumo que nenhum arquivo aparece como trocado.\n"
    "2. Proteger nega a execução do Utilman e do Sethc ao SYSTEM (a conta da tela de login). "
    "O dono continua sendo o TrustedInstaller e o resto da permissão não muda.\n"
    "3. Desligar o atalho Shift 5x desliga as Teclas de aderência na tela de login.\n"
    "4. Saia da conta ou reinicie e teste na tela de login: nada deve abrir.\n"
    "\n"
    "O que deixa de funcionar\n"
    "Na tela de login: o botão de Acessibilidade, Win+U (Narrador, Lupa, teclado virtual) e as "
    "Teclas de aderência pelo Shift 5x. Dentro da conta, tudo continua.\n\n"
    "O que a proteção não cobre\n"
    "Quem dá boot por pendrive pode apagar o arquivo e copiar outro no lugar, ou configurar um "
    "depurador (IFEO). Atualização do Windows que troca o arquivo também tira a proteção. Por "
    "isso a tela confere, a cada abertura, os 7 programas de acessibilidade e também o Prompt de "
    "Comando e o PowerShell, que costumam ser o arquivo copiado no lugar: “não protegido” depois "
    "de uma atualização é só proteger de novo. A defesa contra boot por pendrive é BitLocker "
    "(Criptografia do dispositivo), senha de BIOS e boot só pelo disco.\n\n"
    "Em caso de ataque\n"
    "Arquivo trocado ou depurador é sinal de ataque: abra chamado e troque as senhas das contas. "
    "Os botões só ficam ativos quando a tela acha um desses problemas. Remover depurador apaga só "
    "o depurador dos programas da tabela. Restaurar originais usa o sfc do Windows para buscar o "
    "arquivo certo de cada programa trocado ou ausente, um por vez; depois, proteja de novo.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)

# Cor do texto por situação (tema.cor_situacao).
_COR_ARQUIVO = {"original": "ok", "trocado": "erro", "ausente": "erro", "nao_lido": "aviso"}
_COR_ACL = {"protegido": "ok", "livre": "aviso", "dono": "erro", "nao_lida": "aviso"}
_COR_IFEO = {"limpo": "ok", "depurador": "erro", "nao_lido": "aviso"}
_ICONE = {"ok": "✔ ", "aviso": "⚠ ", "erro": "✖ "}


def _celula(item: QTreeWidgetItem, coluna: int, texto: str, tipo: str | None) -> None:
    item.setText(coluna, (_ICONE.get(tipo or "", "")) + texto)
    item.setForeground(coluna, QColor(tema.cor_situacao(tipo or "")))


class PainelProtecao(QWidget):
    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.situacao: protecao.Situacao | None = None
        self.ocupado = self.lido = False

        v = QVBoxLayout(self)
        v.setSpacing(12)

        # Resumo: situação geral, pontos de atenção e a ação principal.
        self.resumo = QFrame()
        self.resumo.setObjectName("cartao")
        r = QHBoxLayout(self.resumo)
        textos = QVBoxLayout()
        self.estado = QLabel("")
        self.estado.setObjectName("cartaoTitulo")
        self.estado.setTextFormat(Qt.TextFormat.PlainText)
        self.alertas = _rotulo("")
        self.alertas.setObjectName("alerta")
        textos.addWidget(self.estado)
        textos.addWidget(self.alertas)
        if not admin:
            textos.addWidget(_rotulo("Sem administrador: só leitura."))
        r.addLayout(textos, 1)
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(self.carregar)
        r.addWidget(self.atualizar, 0, Qt.AlignmentFlag.AlignTop)
        v.addWidget(self.resumo)

        # Tabela: altura das linhas, sem sobra.
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Programa", "Arquivo", "Proteção", "Depurador (IFEO)"])
        self.arvore.setColumnWidth(0, 230)
        self.arvore.setColumnWidth(1, 200)
        self.arvore.setColumnWidth(2, 150)
        self.arvore.setRootIsDecorated(False)
        self.arvore.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.arvore.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        v.addWidget(self.arvore)

        # Ações do dia a dia: um botão por coisa, o texto muda com a situação.
        acoes = QHBoxLayout()
        self.b_proteger = QPushButton("Proteger")
        self.b_proteger.setObjectName("proteger")  # Desproteger: "desproteger" (vermelho)
        self.b_proteger.clicked.connect(self._alternar_protecao)
        self.atalho = _rotulo("")
        self.b_atalho = QPushButton("Desligar atalho Shift 5x")
        self.b_atalho.clicked.connect(self._alternar_atalho)
        acoes.addWidget(self.b_proteger)
        acoes.addWidget(self.b_atalho)
        acoes.addWidget(self.atalho, 1)
        v.addLayout(acoes)

        # Em caso de ataque: só ativo quando há arquivo trocado/ausente ou depurador.
        self.incidente = QFrame()
        self.incidente.setObjectName("faixa")
        inc = QVBoxLayout(self.incidente)
        titulo = QLabel("Em caso de ataque")
        titulo.setObjectName("subtitulo")
        self.incidente_texto = _rotulo("")
        self.incidente_texto.setObjectName("dica")
        botoes = QHBoxLayout()
        self.b_depurador = QPushButton("Remover depurador")
        self.b_depurador.setObjectName("perigo")
        self.b_depurador.clicked.connect(self._remover_depurador)
        self.b_restaurar = QPushButton("Restaurar originais")
        self.b_restaurar.setObjectName("perigo")
        self.b_restaurar.setToolTip("Restaura pelo sfc cada programa trocado ou ausente.")
        self.b_restaurar.clicked.connect(self._restaurar)
        botoes.addWidget(self.b_depurador)
        botoes.addWidget(self.b_restaurar)
        botoes.addStretch()
        inc.addWidget(titulo)
        inc.addWidget(self.incidente_texto)
        inc.addLayout(botoes)
        v.addWidget(self.incidente)

        # Registro: só aparece depois da primeira ação.
        self.registro_titulo = QLabel("Últimas ações")
        self.registro_titulo.setObjectName("rotulo")
        self.registro = QPlainTextEdit()
        self.registro.setObjectName("log")
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)
        self.registro.setFixedHeight(110)
        self.registro_titulo.hide()
        self.registro.hide()
        v.addWidget(self.registro_titulo)
        v.addWidget(self.registro)
        v.addStretch()
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar()

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        tarefa.iniciar(protecao.situacao, self._recebeu, self._falhou)

    def _recebeu(self, s: protecao.Situacao) -> None:
        self.situacao, self.lido = s, True
        self.arvore.clear()
        for exe in protecao.BINARIOS:
            b = s.binarios[exe]
            item = QTreeWidgetItem([protecao.NOMES[exe], "", "", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, exe)
            _celula(item, 1, protecao.ROTULO_ARQUIVO[b.arquivo], _COR_ARQUIVO.get(b.arquivo))
            if exe in protecao.PROTEGIVEIS:
                _celula(item, 2, protecao.ROTULO_ACL[b.acl], _COR_ACL.get(b.acl))
            else:
                _celula(item, 2, "não se aplica", None)
            _celula(item, 3, protecao.ROTULO_IFEO[b.ifeo], _COR_IFEO.get(b.ifeo))
            self.arvore.addTopLevelItem(item)
        self._ajustar_altura()

        self.atalho.setText(
            f"Atalho Shift 5x na tela de login: {protecao.ROTULO_ATALHO[s.atalho]}."
        )
        self.b_atalho.setText(
            "Ligar atalho Shift 5x" if s.atalho == "desligado" else "Desligar atalho Shift 5x"
        )
        protegido = s.protegido()
        self.b_proteger.setText("Desproteger" if protegido else "Proteger")
        self.b_proteger.setObjectName("desproteger" if protegido else "proteger")
        self.b_proteger.style().unpolish(self.b_proteger)
        self.b_proteger.style().polish(self.b_proteger)

        alertas = s.alertas()
        if s.atalho not in ("desligado", "nao_lido"):
            alertas = [*alertas, "Atalho Shift 5x ligado na tela de login"]
        self.alertas.setText("\n".join(f"⚠ {a}" for a in alertas))
        self.alertas.setVisible(bool(alertas))
        grave = bool(s.a_restaurar()) or s.com_depurador()
        if not alertas:
            self.estado.setText("✔ Login protegido")
            tipo = "ok"
        else:
            n = len(alertas)
            self.estado.setText(f"⚠ {n} ponto{'s' if n > 1 else ''} de atenção")
            tipo = "erro" if grave else "aviso"
        self.estado.setStyleSheet(f"color: {tema.cor_situacao(tipo)};")

        trocados = [protecao.NOMES[e] for e in s.a_restaurar()]
        if grave:
            partes = []
            if trocados:
                partes.append("Arquivo trocado ou ausente: " + ", ".join(trocados) + ".")
            if s.com_depurador():
                partes.append("Depurador (IFEO) configurado.")
            self.incidente_texto.setText(
                " ".join(partes) + " Abra chamado e troque as senhas das contas desta máquina."
            )
        else:
            self.incidente_texto.setText("Nenhum sinal de ataque: os botões ficam desativados.")
        self._ocupar(False)

    def _ajustar_altura(self) -> None:
        linhas = self.arvore.topLevelItemCount()
        alto = self.arvore.sizeHintForRow(0) if linhas else 24
        cabecalho = self.arvore.header().sizeHint().height()
        self.arvore.setFixedHeight(
            cabecalho + alto * max(linhas, 1) + 2 * self.arvore.frameWidth() + 4
        )

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self.estado.setStyleSheet(f"color: {tema.cor_situacao('erro')};")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        s = self.situacao
        pode = self.admin and not ocupado and s is not None
        for b in (self.b_proteger, self.b_atalho):
            b.setEnabled(pode)
        self.b_depurador.setEnabled(pode and s is not None and s.com_depurador())
        self.b_restaurar.setEnabled(pode and s is not None and bool(s.a_restaurar()))
        if not self.admin:
            for b in (
                self.b_proteger,
                self.b_atalho,
                self.b_depurador,
                self.b_restaurar,
            ):
                b.setToolTip("Precisa de administrador.")
        self.atualizar.setEnabled(not ocupado)

    def _rodar(
        self, funcao: Callable[[], Any], formatar: Callable[[Any], tuple[bool, str]]
    ) -> None:
        self._ocupar(True)

        def feito(r: Any) -> None:
            ok, texto = formatar(r)
            self.registro_titulo.show()
            self.registro.show()
            self.registro.appendPlainText(texto)
            self._aviso(texto, erro=not ok)
            self.carregar()

        tarefa.iniciar(funcao, feito, self._falhou)

    def confirmacao(self, proteger: bool) -> str:
        if proteger:
            return (
                "Proteger o Utilman e o Sethc?\n\n"
                "Na tela de login deixam de abrir: botão de Acessibilidade, Win+U e Shift 5x. "
                "Dentro da conta tudo continua. Vale já; teste saindo da conta."
            )
        return "Desproteger o Utilman e o Sethc? A acessibilidade volta na tela de login."

    @staticmethod
    def _formatar_feitos(feitos: list[protecao.Feito]) -> tuple[bool, str]:
        if not feitos:
            return True, "Nada a fazer: nenhum programa trocado ou ausente."
        linhas = [f"{protecao.NOMES[f.exe]}: {f.mensagem}" for f in feitos]
        return all(f.ok for f in feitos), "\n".join(linhas)

    def _alternar_protecao(self) -> None:
        proteger = self.situacao is None or not self.situacao.protegido()
        self._alterar(proteger)

    def _alterar(self, proteger: bool) -> None:
        if not confirmar(self, "Proteção do login", self.confirmacao(proteger)):
            return
        self._rodar(lambda: protecao.alterar(proteger), self._formatar_feitos)

    def _alternar_atalho(self) -> None:
        desligar = self.situacao is None or self.situacao.atalho != "desligado"
        self._atalho(desligar)

    def _atalho(self, desligar: bool) -> None:
        texto = (
            "Desligar o Shift 5x na tela de login?"
            if desligar
            else "Voltar o Shift 5x da tela de login ao padrão do Windows (ligado)?"
        )
        if confirmar(self, "Proteção do login", texto):
            self._rodar(lambda: protecao.atalho_login(desligar), lambda r: r)

    def _incidente(self, texto: str) -> bool:
        aviso = (
            "\n\nArquivo trocado ou depurador é sinal de ataque: abra chamado e troque as senhas "
            "das contas desta máquina."
        )
        return confirmar(self, "Incidente", texto + aviso) and confirmar(
            self, "Incidente", "Confirma de novo? A ação mexe em arquivos ou registro do Windows."
        )

    def _remover_depurador(self) -> None:
        if self._incidente(
            "Apagar o depurador (IFEO) dos programas da tabela? Nada além disso muda."
        ):
            self._rodar(protecao.remover_depurador, lambda r: r)

    def _restaurar(self) -> None:
        if self.situacao is None or not self.situacao.a_restaurar():
            self._aviso("Nenhum programa trocado ou ausente.", erro=False)
            return
        nomes = ", ".join(protecao.NOMES[e] for e in self.situacao.a_restaurar())
        if self._incidente(
            f"Restaurar pelo sfc do Windows: {nomes}? Pode levar alguns minutos por arquivo."
        ):
            self._rodar(protecao.restaurar_trocados, self._formatar_feitos)

    def _aviso(self, texto: str, *, erro: bool = True) -> None:
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
            "Proteção do login",
            texto,
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
