"""Tela Início (ADR-023, item 6): estado da máquina, preparação, alertas e atalhos."""

import time
from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import inicio, limpeza, perfis, remoto
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.preparacao import Andamento
from itc_bench.ui import tarefa
from itc_bench.ui.contas import _rotulo

AJUDA = (
    "Resumo do notebook: modelo, série, Windows, unidade, disco e bateria; como está a "
    "preparação; diagnósticos esperando envio; e alertas.\n\n"
    "Alertas\n"
    "Cada alerta tem um botão que leva à tela que resolve. Críticos (contados no selo vermelho "
    "do menu): proteção do login fora do lugar (arquivo trocado, depurador, não protegido), "
    "política da máquina do perfil faltando e conta Suporte ausente. De atenção: nome do "
    "computador esperando reinício, cadastros velhos, fila de diagnóstico e pouco disco.\n\n"
    "Preparação\n"
    "Mostra a última leitura feita nesta sessão. Ler todas as etapas leva alguns minutos; use "
    "“Abrir preparação” e “Ler situação”.\n\n"
    "Atalhos\n"
    "Forçar inventário GLPI pede ao GLPI Agent desta máquina um inventário agora. Limpar "
    "temporários abre a Limpeza com a prévia; nada é apagado sem confirmação.\n\n"
    "A leitura roda ao abrir e vale por 1 minuto; Atualizar lê de novo. Sem administrador, "
    "proteção, políticas e contas não são lidas."
)


def _cartao(titulo: str) -> tuple[QFrame, QVBoxLayout]:
    c = QFrame()
    c.setObjectName("cartao")
    v = QVBoxLayout(c)
    t = QLabel(titulo)
    t.setObjectName("cartaoTitulo")
    v.addWidget(t)
    return c, v


def _gb(n: int | None) -> str:
    return "—" if n is None else limpeza.tamanho(n)


class PainelInicio(QWidget):
    abrir = Signal(str)
    criticos = Signal(int)

    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str],
        fila: Callable[[], int],
        obter_perfil: Callable[[], perfis.Perfil],
        obter_andamento: Callable[[], Andamento | None],
    ) -> None:
        super().__init__()
        self.admin = admin
        self.obter_cadastros = obter_cadastros
        self.obter_unidade = obter_unidade
        self.fila = fila
        self.obter_perfil = obter_perfil
        self.obter_andamento = obter_andamento
        self.painel: inicio.Painel | None = None
        self.ocupado = False

        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.estado = _rotulo("")
        self.atualizar = QPushButton("Atualizar")
        self.atualizar.clicked.connect(lambda: self.carregar(forcar=True))
        topo.addWidget(self.estado, 1)
        topo.addWidget(self.atualizar)
        v.addLayout(topo)

        grade = QGridLayout()
        c_maq, self.v_maq = _cartao("Máquina")
        self.maquina = _rotulo("carregando…")
        self.v_maq.addWidget(self.maquina)
        c_prep, v_prep = _cartao("Preparação")
        self.prep = _rotulo("")
        b_prep = QPushButton("Abrir preparação")
        b_prep.clicked.connect(lambda: self.abrir.emit("prep"))
        v_prep.addWidget(self.prep)
        v_prep.addWidget(b_prep)
        c_diag, v_diag = _cartao("Último diagnóstico")
        self.diag = _rotulo("")
        b_diag = QPushButton("Coleta e laudo")
        b_diag.clicked.connect(lambda: self.abrir.emit("diag"))
        v_diag.addWidget(self.diag)
        v_diag.addWidget(b_diag)
        c_alert, self.v_alertas = _cartao("Alertas")
        self.sem_alertas = _rotulo("carregando…")
        self.v_alertas.addWidget(self.sem_alertas)
        self.linhas_alerta: list[QWidget] = []
        grade.addWidget(c_maq, 0, 0)
        grade.addWidget(c_prep, 0, 1)
        grade.addWidget(c_alert, 1, 0)
        grade.addWidget(c_diag, 1, 1)
        v.addLayout(grade)

        atalhos = QHBoxLayout()
        self.b_inventario = QPushButton("Forçar inventário GLPI")
        self.b_inventario.clicked.connect(self._inventario)
        self.b_inventario.setEnabled(admin)
        b_limpar = QPushButton("Limpar temporários")
        b_limpar.clicked.connect(lambda: self.abrir.emit("limpeza"))
        atalhos.addWidget(self.b_inventario)
        atalhos.addWidget(b_limpar)
        atalhos.addStretch()
        v.addLayout(atalhos)
        v.addStretch()

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        self.mostrar_preparacao()
        self.carregar()

    def mostrar_preparacao(self) -> None:
        perfil = self.obter_perfil()
        a = self.obter_andamento()
        if a is None:
            self.prep.setText(f"Perfil {perfil.nome}: situação ainda não lida nesta sessão.")
        else:
            self.prep.setText(
                f"Perfil {perfis.POR_ID[a.perfil].nome}: {a.selo()} etapas feitas"
                + (" · reinício pendente" if a.reinicio else "")
            )
        n = self.fila()
        self.diag.setText(
            f"{n} diagnóstico(s) esperando envio." if n else "Nenhum diagnóstico na fila de envio."
        )

    def carregar(self, forcar: bool = False) -> None:
        if self.ocupado:
            return
        if (
            not forcar
            and self.painel is not None
            and time.monotonic() - self.painel.lido_em < inicio.CACHE
        ):
            return
        self.ocupado = True
        self.atualizar.setEnabled(False)
        self.estado.setText("Lendo…")
        admin, cad, fila, perfil = (
            self.admin,
            self.obter_cadastros(),
            self.fila(),
            self.obter_perfil(),
        )
        tarefa.iniciar(
            lambda: inicio.ler(admin=admin, cadastros=cad, fila=fila, perfil=perfil),
            self._recebeu,
            self._falhou,
        )

    def _recebeu(self, p: inicio.Painel) -> None:
        self.painel = p
        self.ocupado = False
        self.atualizar.setEnabled(True)
        m = p.maquina
        if m is None:
            self.maquina.setText("Não foi possível ler a máquina.")
        else:
            bateria = "sem bateria" if m.bateria is None else f"{m.bateria}%"
            if m.na_tomada:
                bateria += " (na tomada)"
            self.maquina.setText(
                f"{m.fabricante} {m.modelo}\nSérie: {m.serie or '—'}\n{m.windows}\n"
                f"Unidade: {self.obter_unidade()}\n"
                f"Disco: {_gb(m.disco_livre)} livres de {_gb(m.disco_total)}\nBateria: {bateria}"
            )
        for w in self.linhas_alerta:
            w.deleteLater()
        self.linhas_alerta = []
        self.sem_alertas.setText("Nenhum alerta." if not p.alertas else "")
        self.sem_alertas.setVisible(not p.alertas)
        for a in p.alertas:
            linha = QWidget()
            h = QHBoxLayout(linha)
            h.setContentsMargins(0, 0, 0, 0)
            r = _rotulo(("⛔ " if a.nivel == "critico" else "⚠ ") + a.texto)
            r.setObjectName("alerta" if a.nivel == "critico" else "")
            b = QPushButton("Abrir")
            b.clicked.connect(lambda _c=False, tela=a.tela: self.abrir.emit(tela))
            h.addWidget(r, 1)
            h.addWidget(b)
            self.v_alertas.addWidget(linha)
            self.linhas_alerta.append(linha)
        nao = f" Não lido: {', '.join(p.erros)}." if p.erros else ""
        sem = "" if self.admin else " Sem administrador: proteção, políticas e contas não lidas."
        self.estado.setText(f"Lido às {time.strftime('%H:%M')}.{nao}{sem}")
        self.mostrar_preparacao()
        self.criticos.emit(p.criticos)

    def _falhou(self, motivo: str) -> None:
        self.ocupado = False
        self.atualizar.setEnabled(True)
        self.estado.setText(f"Falhou: {motivo}")

    def _inventario(self) -> None:
        self.b_inventario.setEnabled(False)

        def fim(f: remoto.Feito) -> None:
            self.b_inventario.setEnabled(True)
            self.estado.setText(f.mensagem)

        def falhou(m: str) -> None:
            self.b_inventario.setEnabled(True)
            self.estado.setText(f"Falhou: {m}")

        tarefa.iniciar(remoto.forcar_inventario, fim, falhou)
