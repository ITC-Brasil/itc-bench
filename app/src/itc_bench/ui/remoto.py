"""Tela Acesso remoto (ADR-019). Regras em `servicos/remoto.py`; aqui só tela.

Senhas e a chave do RustDesk nunca chegam a widget. Texto do cadastro só em texto puro.
"""

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import instaladores, remoto
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Instala e configura o acesso remoto: GLPI Agent (inventário), RustDesk e AnyDesk. "
    "Servidores, chave e senhas vêm do cadastro (Configurações › Servidores); os instaladores, "
    "de Configurações › Instaladores. Senhas nunca aparecem na tela.\n\n"
    "Instalar\n"
    "1. Confira em cada cartão a versão instalada e a do cadastro, o serviço e a configuração.\n"
    "2. Clique em Instalar (ou Atualizar). A confirmação mostra o servidor, a tag, o arquivo, "
    "o SHA-256 e o comando. O Bench baixa o instalador, confere o SHA-256 e só então executa.\n"
    "3. Anote o ID do RustDesk e do AnyDesk que aparece no cartão.\n\n"
    "Versões\n"
    "Igual à do cadastro: só Reconfigurar (servidor, chave, senha). Mais nova que o cadastro: o "
    "Bench não rebaixa; atualize o cadastro. Mais velha: Atualizar instala por cima.\n\n"
    "RustDesk\n"
    "Se o serviço do RustDesk não existir depois do instalador, o Bench o cria; se ele não subir "
    "no tempo, o Bench para e inicia de novo uma vez. A senha permanente é definida pelo próprio "
    "RustDesk (--password) com o serviço rodando, e o Bench confere que ela ficou cifrada. "
    "Para saber se a senha bate, conecte de outro computador com a senha do cadastro.\n\n"
    "Download recusado\n"
    "“Recusou o pedido (HTTP 403/404…)” quer dizer que o servidor do download respondeu, mas "
    "não entregou o arquivo: confira o Link em Instaladores (tem que ser o arquivo, não uma "
    "página) ou use Escolher arquivo….\n\n"
    "Sem internet\n"
    "Use Escolher arquivo… e aponte o instalador num pendrive. O Bench copia e confere o SHA-256 "
    "do cadastro; arquivo diferente é recusado. Linha sem SHA-256 no cadastro aceita o arquivo "
    "escolhido (a confirmação mostra “SHA-256: não cadastrado”).\n\n"
    "Cancelar\n"
    "Vale entre passos, no download e nas esperas. O instalador do Windows não é interrompido no "
    "meio: o cancelamento acontece depois dele.\n\n"
    "Forçar inventário\n"
    "Pede ao GLPI Agent desta máquina que envie o inventário agora.\n\n"
    "Cadastro incompleto\n"
    "O cartão diz qual linha falta em Servidores ou Instaladores e a instalação não começa. A tag "
    "do GLPI é opcional (Unidades › TagGLPI). O Servidor da API do RustDesk também é opcional "
    "(Servidores › RustDesk / api, https://): sem ele, o Bench não mexe nesse campo.\n\n"
    "Sem administrador (modo de teste), a tela só mostra a situação."
)

SERVICO_ROTULO = {"Running": "rodando", "Stopped": "parado", None: "ausente"}
CONFIG_ROTULO = {
    "conferida": "conferida",
    "diferente": "diferente do cadastro",
    "nao_conferida": "não conferida",
    "": "",
}


class _Sinais(QObject):
    texto = Signal(str)


class Cartao(QGroupBox):
    def __init__(self, programa: remoto.Programa) -> None:
        super().__init__(programa)
        self.programa = programa
        v = QVBoxLayout(self)
        self.info = _rotulo("Lendo…")
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.info)
        linha = QHBoxLayout()
        self.principal = QPushButton("Instalar")
        self.principal.setObjectName("primario")
        self.arquivo = QPushButton("Escolher arquivo…")
        linha.addWidget(self.principal)
        linha.addWidget(self.arquivo)
        self.inventario: QPushButton | None = None
        if programa == "GLPI Agent":
            self.inventario = QPushButton("Forçar inventário")
            linha.addWidget(self.inventario)
        linha.addStretch()
        v.addLayout(linha)
        self.situacao: remoto.Situacao | None = None

    def mostrar(self, s: remoto.Situacao) -> None:
        self.situacao = s
        partes = [
            f"Instalado: {s.instalada or 'não'}"
            + (f" · cadastro: {s.cadastro}" if s.cadastro else ""),
            f"Serviço: {SERVICO_ROTULO.get(s.servico, s.servico or 'ausente')}",
        ]
        if s.config:
            partes.append(f"Configuração: {CONFIG_ROTULO[s.config]}")
        if s.id_remoto:
            partes.append(f"ID: {s.id_remoto}")
        if s.comparacao == "nova":
            partes.append("Versão instalada mais nova que o cadastro: atualize o cadastro.")
        partes += list(s.detalhes)
        if s.falta:
            partes.append(f"Falta: {s.falta}")
        self.info.setText("\n".join(partes))
        self.principal.setText(acao_rotulo(s.comparacao))


def acao_rotulo(comparacao: remoto.Comparacao | None) -> str:
    return {"ausente": "Instalar", "velha": "Atualizar"}.get(comparacao or "", "Reconfigurar")


class PainelRemoto(QWidget):
    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str | None],
    ) -> None:
        super().__init__()
        self.admin, self.obter_cadastros, self.obter_unidade = admin, obter_cadastros, obter_unidade
        self.ocupado = False
        self.lido = False
        self.cancelar_evento: threading.Event | None = None
        self.sinais = _Sinais()
        self.sinais.texto.connect(self._registrar)

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
        self.cartoes: dict[remoto.Programa, Cartao] = {}
        for programa in remoto.PROGRAMAS:
            c = Cartao(programa)
            c.principal.clicked.connect(lambda _=False, p=programa: self._executar(p, None))
            c.arquivo.clicked.connect(lambda _=False, p=programa: self._escolher(p))
            if c.inventario is not None:
                c.inventario.clicked.connect(self._inventario)
            self.cartoes[programa] = c
            v.addWidget(c)
        self.registro = QPlainTextEdit()
        self.registro.setReadOnly(True)
        self.registro.setMaximumBlockCount(500)
        v.addWidget(self.registro, 1)
        baixo = QHBoxLayout()
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self._cancelar)
        self.b_cancelar.hide()
        baixo.addWidget(self.b_cancelar)
        baixo.addStretch()
        v.addLayout(baixo)
        self._ocupar(False)

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.carregar()

    # ------------------------------------------------------------ leitura

    def carregar(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo a situação…")
        cadastros, unidade, admin = self.obter_cadastros(), self.obter_unidade(), self.admin
        tarefa.iniciar(
            lambda: remoto.situacao(cadastros, unidade, admin=admin), self._recebeu, self._falhou
        )

    def _recebeu(self, situacoes: dict[remoto.Programa, remoto.Situacao]) -> None:
        self.lido = True
        for programa, s in situacoes.items():
            self.cartoes[programa].mostrar(s)
        sem = self.obter_cadastros() is None
        self.estado.setText("Sem cadastros: conecte, entre e sincronize." if sem else "")
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._fim()
        self._ocupar(False)

    def _registrar(self, texto: str) -> None:
        self.registro.appendPlainText(texto)

    # ------------------------------------------------------------ botões

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        self.atualizar.setEnabled(not ocupado)
        for c in self.cartoes.values():
            pronto = self.admin and not ocupado and c.situacao is not None and not c.situacao.falta
            c.principal.setEnabled(pronto)
            c.arquivo.setEnabled(
                pronto
                and acao_rotulo(c.situacao.comparacao if c.situacao else None) != "Reconfigurar"
            )
            if c.inventario is not None:
                c.inventario.setEnabled(
                    self.admin
                    and not ocupado
                    and c.situacao is not None
                    and bool(c.situacao.instalada)
                )

    def _cancelar(self) -> None:
        if self.cancelar_evento is not None:
            self.cancelar_evento.set()
            self.b_cancelar.setText("Cancelando depois deste passo…")

    def _fim(self) -> None:
        self.cancelar_evento = None
        self.b_cancelar.hide()
        self.b_cancelar.setText("Cancelar")

    # ------------------------------------------------------------ ações

    def _escolher(self, programa: remoto.Programa) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, f"Instalador de {programa}", "", f"Instalador (*{remoto.EXTENSAO[programa]})"
        )
        if caminho:
            self._executar(programa, Path(caminho))

    def confirmacao(self, d: remoto.Dados, acao: str, origem: Path | None) -> str:
        inst = d.instalador
        guardado = instaladores.guardado(inst, remoto.EXTENSAO[d.programa]) if self.admin else None
        sha = (
            "conferido (já guardado)"
            if guardado
            else ("será conferido sobre a cópia" if origem else "será conferido após o download")
        )
        linhas = [f"{acao} {d.programa} {inst.versao}?", ""]
        if d.servidor:
            linhas.append(f"Servidor: {d.servidor}")
        if d.api:
            linhas.append(f"Servidor da API: {d.api}")
        if d.programa == "GLPI Agent":
            linhas.append(f"Tag: {d.tag or 'sem tag'}")
        if acao != "Reconfigurar":
            linhas += [
                f"Instalador: {inst.arquivo} (cadastro Id {inst.id})",
                f"Origem: {origem.name if origem else 'download do cadastro'}",
                f"SHA-256: {instaladores.cadastrado(inst) or 'não cadastrado'} ({sha})",
                "",
                "Comando:",
                remoto.comando(d, inst.arquivo),
            ]
        linhas += [*d.avisos]
        return "\n".join(linhas)

    def _executar(self, programa: remoto.Programa, origem: Path | None) -> None:
        cartao = self.cartoes[programa]
        cadastros = self.obter_cadastros()
        d = remoto.dados(cadastros, programa, self.obter_unidade())
        if isinstance(d, str):
            self._aviso(d)
            return
        comp = cartao.situacao.comparacao if cartao.situacao else "ausente"
        acao = acao_rotulo(comp) if origem is None else "Instalar"
        if not confirmar(self, f"Acesso remoto — {programa}", self.confirmacao(d, acao, origem)):
            return
        self.cancelar_evento = evento = threading.Event()
        self.b_cancelar.show()
        self._ocupar(True)
        emitir = self.sinais.texto.emit
        emitir(f"— {programa}: {acao.lower()}")

        def rodar() -> remoto.Feito:
            if acao == "Reconfigurar":
                return remoto.reconfigurar(d, avisar=emitir, cancelar=evento)
            instaladores.limpar(cadastros)

            dezenas: set[int] = set()

            def progresso(lidos: int, total: int | None) -> None:
                if total and (d10 := lidos * 10 // total) not in dezenas:
                    dezenas.add(d10)
                    emitir(f"Baixando… {d10 * 10}%")

            try:
                emitir("Obtendo o instalador e conferindo o SHA-256…")
                arquivo = remoto.preparar_arquivo(
                    d, origem=origem, cancelar=evento, progresso=progresso
                )
            except instaladores.Cancelado:
                return remoto.Feito(False, "Cancelado pelo técnico.")
            except instaladores.ErroInstalador as erro:
                return remoto.Feito(False, str(erro))
            emitir("SHA-256 conferido.")
            return remoto.instalar(d, arquivo, avisar=emitir, cancelar=evento)

        tarefa.iniciar(rodar, self._feito, self._falhou)

    def _inventario(self) -> None:
        self._ocupar(True)
        tarefa.iniciar(remoto.forcar_inventario, self._feito, self._falhou)

    def _feito(self, feito: remoto.Feito) -> None:
        self._fim()
        self._registrar(feito.mensagem)
        for aviso in feito.avisos:
            self._registrar(f"Aviso: {aviso}")
        texto = "\n".join([feito.mensagem, *feito.avisos])
        self._aviso(texto, erro=not feito.ok)
        self.carregar()

    def _aviso(self, texto: str, *, erro: bool = True) -> None:
        caixa = QMessageBox(
            QMessageBox.Icon.Warning if erro else QMessageBox.Icon.Information,
            "Acesso remoto",
            texto,
            parent=self,
        )
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
