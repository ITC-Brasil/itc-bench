"""Tela Proteção do login (ADR-022). Regras em `servicos/protecao.py`; aqui só tela."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import protecao
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Impede que alguém troque o Utilman (botão de Acessibilidade) ou o Sethc (Shift 5 vezes) "
    "por um Prompt de Comando para redefinir senhas na tela de login.\n\n"
    "Proteger\n"
    "1. Confira que os dois arquivos aparecem como “original do Windows”.\n"
    "2. Proteger nega a execução desses dois arquivos ao SYSTEM (a conta da tela de login). "
    "O dono continua sendo o TrustedInstaller e o resto da permissão não muda.\n"
    "3. Desligar atalho desliga o Shift 5x na tela de login.\n"
    "4. Saia da conta ou reinicie e teste na tela de login: nada deve abrir.\n\n"
    "O que deixa de funcionar\n"
    "Na tela de login: o botão de Acessibilidade, Win+U (Narrador, Lupa, teclado virtual) e as "
    "Teclas de aderência pelo Shift 5x. Dentro da conta, tudo continua.\n\n"
    "O que a proteção não cobre\n"
    "Quem dá boot por pendrive pode apagar o arquivo e copiar outro no lugar, ou configurar um "
    "depurador (IFEO). Atualização do Windows que troca o arquivo também tira a proteção. Por "
    "isso a tela confere os 7 programas de acessibilidade a cada abertura: “não protegido” "
    "depois de uma atualização é só proteger de novo. A defesa contra boot por pendrive é "
    "BitLocker (Criptografia do dispositivo), senha de BIOS e boot só pelo disco.\n\n"
    "Arquivo trocado ou depurador\n"
    "É sinal de ataque: abra chamado e troque as senhas das contas. Remover depurador apaga só o "
    "depurador desses 7 programas. Restaurar original usa o sfc do Windows para buscar o "
    "arquivo certo; depois, proteja de novo.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)


class PainelProtecao(QWidget):
    def __init__(self, admin: bool) -> None:
        super().__init__()
        self.admin = admin
        self.situacao: protecao.Situacao | None = None
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
        self.alertas = _rotulo("")
        self.alertas.setObjectName("alerta")
        v.addWidget(self.alertas)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Programa", "Arquivo", "Proteção", "Depurador (IFEO)"])
        self.arvore.setColumnWidth(0, 220)
        self.arvore.setColumnWidth(1, 220)
        self.arvore.setRootIsDecorated(False)
        v.addWidget(self.arvore, 2)
        self.atalho = _rotulo("")
        v.addWidget(self.atalho)

        acoes = QHBoxLayout()
        self.b_proteger = QPushButton("Proteger")
        self.b_proteger.setObjectName("primario")
        self.b_proteger.clicked.connect(lambda: self._alterar(True))
        self.b_desproteger = QPushButton("Desproteger")
        self.b_desproteger.clicked.connect(lambda: self._alterar(False))
        self.b_desligar = QPushButton("Desligar atalho")
        self.b_desligar.clicked.connect(lambda: self._atalho(True))
        self.b_ligar = QPushButton("Ligar atalho")
        self.b_ligar.clicked.connect(lambda: self._atalho(False))
        for b in (self.b_proteger, self.b_desproteger, self.b_desligar, self.b_ligar):
            acoes.addWidget(b)
        acoes.addStretch()
        v.addLayout(acoes)
        incidente = QHBoxLayout()
        self.b_depurador = QPushButton("Remover depurador")
        self.b_depurador.clicked.connect(self._remover_depurador)
        self.b_restaurar = QPushButton("Restaurar original")
        self.b_restaurar.setToolTip("Restaura o programa selecionado na tabela pelo sfc.")
        self.b_restaurar.clicked.connect(self._restaurar)
        incidente.addWidget(_rotulo("Incidente:"))
        incidente.addWidget(self.b_depurador)
        incidente.addWidget(self.b_restaurar)
        incidente.addStretch()
        v.addLayout(incidente)
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
        tarefa.iniciar(protecao.situacao, self._recebeu, self._falhou)

    def _recebeu(self, s: protecao.Situacao) -> None:
        self.situacao, self.lido = s, True
        self.arvore.clear()
        for exe in protecao.BINARIOS:
            b = s.binarios[exe]
            protegivel = exe in protecao.PROTEGIVEIS
            item = QTreeWidgetItem(
                [
                    protecao.NOMES[exe],
                    protecao.ROTULO_ARQUIVO[b.arquivo],
                    protecao.ROTULO_ACL[b.acl] if protegivel else "—",
                    protecao.ROTULO_IFEO[b.ifeo],
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, exe)
            self.arvore.addTopLevelItem(item)
        self.atalho.setText(
            f"Atalho Shift 5x na tela de login: {protecao.ROTULO_ATALHO[s.atalho]}."
        )
        alertas = s.alertas()
        self.alertas.setText("\n".join(f"⚠ {a}" for a in alertas))
        self.alertas.setVisible(bool(alertas))
        self.estado.setText(
            "Tudo protegido." if not alertas else f"{len(alertas)} ponto(s) de atenção."
        )
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        pode = self.admin and not ocupado and self.situacao is not None
        for b in (
            self.b_proteger,
            self.b_desproteger,
            self.b_desligar,
            self.b_ligar,
            self.b_depurador,
            self.b_restaurar,
        ):
            b.setEnabled(pode)
            if not self.admin:
                b.setToolTip("Precisa de administrador.")
        self.atualizar.setEnabled(not ocupado)

    def _rodar(
        self, funcao: Callable[[], Any], formatar: Callable[[Any], tuple[bool, str]]
    ) -> None:
        self._ocupar(True)

        def feito(r: Any) -> None:
            ok, texto = formatar(r)
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

    def _alterar(self, proteger: bool) -> None:
        if not confirmar(self, "Proteção do login", self.confirmacao(proteger)):
            return

        def formatar(feitos: list[protecao.Feito]) -> tuple[bool, str]:
            linhas = [f"{protecao.NOMES[f.exe]}: {f.mensagem}" for f in feitos]
            return all(f.ok for f in feitos), "\n".join(linhas)

        self._rodar(lambda: protecao.alterar(proteger), formatar)

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
            "Apagar o depurador (IFEO) dos 7 programas de acessibilidade? Nada além disso muda."
        ):
            self._rodar(protecao.remover_depurador, lambda r: r)

    def _restaurar(self) -> None:
        item = self.arvore.currentItem()
        if item is None:
            self._aviso("Selecione na tabela o programa a restaurar.")
            return
        exe = str(item.data(0, Qt.ItemDataRole.UserRole))
        if self._incidente(
            f"Restaurar {protecao.NOMES[exe]} pelo sfc do Windows? Pode levar alguns minutos."
        ):
            self._rodar(lambda: protecao.restaurar(exe), lambda r: r)

    def _aviso(self, texto: str, *, erro: bool = True) -> None:
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
            "Proteção do login",
            texto,
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
