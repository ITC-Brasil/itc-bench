"""Telas Configuração e Manutenção (ADR-023, ADR-062). Motor em `servicos/preparacao.py`,
etapas em `servicos/etapas.py`, retomada em `servicos/retomada.py`; aqui só tela. As duas
usam a mesma classe: a Manutenção não tem perfil nem retomada."""

import threading
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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

from itc_bench.nucleo.log import log
from itc_bench.servicos import contas, etapas, identificacao, perfis, retomada
from itc_bench.servicos import preparacao as prep
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import contas as ui_contas
from itc_bench.ui import tarefa, tema
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Configura uma máquina nova, com as etapas do perfil, em ordem e com número fixo: "
    "1. Energia: nunca desligar, 2. Remover pré-instalados, 3. Wi-Fi, 4. Papel de parede, "
    "5. Acesso remoto, 6. Programas, 7. Políticas, 8. USB, 9. Proteção do login, 10. Energia: "
    "planos finais, 11. Contas e 12. Diagnóstico. O número não muda com o perfil: um perfil "
    "sem 7 e 8 mostra 1 a 6 e depois 9 a 12. Cada etapa usa as mesmas regras da tela dela. "
    "Identificação (nome do computador) e Mouse e teclado ficam só nas telas deles.\n"
    "\n"
    "Energia (1 e 10)\n"
    "A 1 deixa tela e suspensão em Nunca, na tomada e na bateria, para a máquina não dormir no "
    "meio da configuração. A 10 aplica os planos finais, iguais para todo perfil: desligar a "
    "tela em 30 minutos e suspender em 1 hora, na tomada e na bateria.\n"
    "\n"
    "Remover pré-instalados (2)\n"
    "Remove, para todas as contas e para as contas novas, os apps da Microsoft de uma lista "
    "fechada: Clipchamp, Notícias, Clima, Xbox e Game Bar, Obter Ajuda, Dicas, Microsoft 365 "
    "(hub), Paciência, Realidade Misturada, Pessoas, Power Automate, Skype, To Do, Hub de "
    "Comentários, Mapas, Vincular ao Celular, Groove Música, Filmes e TV e o Windows Terminal. "
    "Também tira o PowerShell ISE (recurso opcional do Windows; o PowerShell continua) e o "
    "Office que vem de fábrica (Microsoft 365 e OneNote pré-instalados); Office corporativo e "
    "o que a etapa 6 (Programas) instala não são tocados. Se houver McAfee, a etapa avisa e "
    "segue: ele sai pela tela Remover programas, com o MCPR e o técnico (pede um código de "
    "validação digitado na tela). Não "
    "mexe na Microsoft Store, no Edge, na Calculadora, no Bloco de Notas nem no App Installer "
    "(winget).\n"
    "\n"
    "Wi-Fi (3)\n"
    "Instala as redes do projeto da unidade desta máquina (cadastro WiFi, coluna Projeto) que "
    "valem para o perfil escolhido (coluna Perfis; vazia = todos). Uma rede de outra unidade do "
    "mesmo projeto também entra. Rede antiga, sem projeto, só na unidade dela. Sem rede para o "
    "projeto e o perfil, ou com a máquina em bancada, a etapa 3 não aparece.\n"
    "\n"
    "Programas (6)\n"
    "Instala os programas do cadastro (Instaladores) que valem para esta máquina: os sem "
    "Projeto e os do projeto da unidade, e, entre eles, os que valem para o perfil escolhido "
    "(coluna Perfis; vazia = todos). Em bancada, só os sem projeto. Sem programa para o "
    "projeto e o perfil, a etapa 6 não aparece.\n"
    "\n"
    "Papel de parede (4)\n"
    "Cada projeto tem o seu, no cadastro (Instaladores, tipo papel, coluna Projeto). A etapa "
    "4 usa o do projeto da unidade desta máquina. Sem papel do projeto, unidade sem projeto "
    "ou máquina em bancada (sem unidade), a etapa 4 não aparece: a lista pula da 3 para a 5.\n"
    "\n"
    "Perfis\n"
    "Vêm do cadastro (tabela Perfis no NocoDB; veja em Configurações › Perfis). Cada perfil "
    "diz quais etapas rodam, pelos números de 1 a 12; o que cada etapa faz não muda com o "
    "perfil. Aparecem os perfis gerais e os do projeto desta unidade; vem marcado o perfil "
    "padrão da unidade. Sem perfil no cadastro, a Configuração não roda: cadastre e "
    "sincronize.\n"
    "\n"
    "Como usar\n"
    "1. Escolha o perfil (vem marcado o da unidade). Desmarque etapas que não quer agora; "
    "Marcar todas e Desmarcar todas mudam a lista inteira.\n"
    "2. Em Contas locais, as contas que podem receber políticas, USB e papel de parede vêm "
    "marcadas: desmarque as que não devem.\n"
    "3. Ler situação (opcional) confere cada etapa no Windows: feito, pendente ou bloqueada "
    "(com o motivo).\n"
    "4. Rodar N etapas roda as etapas marcadas na hora do clique, com ou sem Ler situação "
    "antes. Mostra o que muda e pede confirmação; sem leitura, a confirmação lista as etapas "
    "sem o detalhe. Cada etapa é conferida antes de aplicar: etapa já feita é pulada e rodar "
    "de novo não refaz nada.\n"
    "5. Pausar para depois da etapa que está rodando.\n"
    "\n"
    "Contas (11)\n"
    "Aplica a conta Suporte e tira administrador de todas as outras, inclusive da conta em "
    "uso (vale na próxima entrada; depois o UAC pede a Suporte). Com as linhas Conta Gestão "
    "em Servidores, também aplica a conta Gestão (cria se faltar, ativa e torna "
    "administradora), como a Suporte; sem elas, não mexe na Gestão. A Gestão continua "
    "administradora. O Administrador nativo não é alterado: se estiver ativo, desative-o pelo"
    " Windows.\n"
    "\n"
    "Contas locais\n"
    "Mostra as contas locais desta máquina. Não aparecem nunca: Suporte, Gestão, o "
    "Administrador nativo e contas Microsoft ou de domínio. Recebem políticas, USB e papel de "
    "parede só as contas ativas, que não são administradoras, não estão logadas e já têm "
    "perfil, menos a conta que roda o Bench. As outras ficam cinza, sem marcar, com o motivo "
    "ao lado: administradora, desativada, conta logada, sem perfil ou conta do Bench. Marcar "
    "todas e Desmarcar todas só mexem nas que podem ser "
    "marcadas. Atualizar relê a lista e mantém as marcações. Encerrar sessões… é o mesmo da "
    "tela Contas: escolha as contas, confirme, e o que estiver aberto nelas fecha sem salvar; "
    "a sessão do Bench não é encerrada. Depois, a lista é relida (a conta deixa de estar "
    "logada). As etapas também valem para as contas futuras.\n"
    "\n"
    "Falha\n"
    "Etapa que falha não para as outras. Veja o motivo na linha e no Registro.\n"
    "\n"
    "Reinício\n"
    "Alguns instaladores pedem reinício. O Bench não reinicia sozinho: use Reiniciar agora. "
    "Depois do reinício, abra o Bench, entre e escolha Continuar; a configuração relê tudo e "
    "roda só o que falta. Vale por 24 horas e até 2 reinícios. Descartar apaga a configuração "
    "guardada.\n"
    "\n"
    "Sem administrador (modo de teste), só a leitura."
)
AJUDA_MANUTENCAO = (
    "Cuida de uma máquina que já está em uso. Não usa perfil: as etapas vêm marcadas e você "
    "desmarca as que não quer. Números fixos: 1. Limpeza de usuários, 2. Wi-Fi: atualizar "
    "senhas, 3. Diagnóstico e 4. Remover Steam.\n"
    "\n"
    "Limpeza de usuários (1)\n"
    "Nas contas de aluno marcadas, apaga para sempre, sem como recuperar: Área de Trabalho "
    "(os atalhos ficam), Documentos, Downloads, Imagens, Vídeos, Jogos salvos e todos os dados "
    "do Chrome (contas conectadas, senhas, histórico e favoritos: o Chrome abre como novo). "
    "Políticas, configurações e o resto da conta ficam. A conta tem de estar sem sessão aberta; "
    "Suporte, Gestão, o Administrador nativo e a sua conta nunca entram. Ler situação mostra "
    "quanto vai liberar; a confirmação mostra por conta.\n"
    "\n"
    "Wi-Fi: atualizar senhas (2)\n"
    "Confere as redes do cadastro que já estão instaladas nesta máquina e regrava as que estão "
    "com outra senha. Rede que não está na máquina não é instalada: para isso, use a tela Wi-Fi "
    "ou a Configuração.\n"
    "\n"
    "Diagnóstico (3)\n"
    "A mesma coleta da tela Diagnóstico: processos, rede, erros do Windows, disco e bateria, "
    "com o laudo da IA. Só lê a máquina.\n"
    "\n"
    "Remover Steam (4)\n"
    "Só aparece com a Steam instalada. Desinstala a Steam com os jogos da biblioteca padrão e os "
    "usuários salvos nela, para todas as contas. Feche a Steam antes. Jogos instalados em outra "
    "biblioteca (outro disco) não são apagados.\n"
    "\n"
    "Como usar\n"
    "1. Em Contas locais, marque as contas que serão limpas. Suporte, Gestão e o "
    "Administrador nativo não aparecem; as outras que não podem ser limpas ficam cinza, com o "
    "motivo (administradora, desativada, conta logada, sem perfil ou conta do Bench). Marcar "
    "todas e "
    "Desmarcar todas valem para as etapas e para as contas que podem ser marcadas.\n"
    "2. Conta logada não é limpa: use Encerrar sessões… (o mesmo da tela Contas; o que estiver "
    "aberto fecha sem salvar) e a lista é relida. Atualizar relê a lista e mantém as "
    "marcações.\n"
    "3. Ler situação (opcional) confere cada etapa: feito, pendente ou bloqueada (com o "
    "motivo), e mostra quanto a limpeza vai liberar.\n"
    "4. Rodar N etapas roda as etapas marcadas na hora do clique, com ou sem leitura antes, e "
    "pede confirmação com as contas marcadas. Cada etapa é conferida antes de aplicar; etapa "
    "já feita é pulada.\n"
    "5. Pausar para depois da etapa que está rodando.\n"
    "\n"
    "Sem administrador (modo de teste), só a leitura."
)
# Etapas que agem nas contas marcadas: a confirmação lista as contas (ADR-071).
COM_CONTAS = frozenset({"politicas", "usb", "papel", "mouse", "limpeza_usuarios"})
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
    leitura = Signal()  # começou ou terminou uma leitura ou execução (o Início se atualiza)

    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str | None],
        diagnosticar: Callable[[threading.Event], prep.Resultado] | None = None,
        manutencao: bool = False,
    ) -> None:
        super().__init__()
        self.manutencao = manutencao  # ADR-062: sem perfil e sem retomada
        self.fluxo = perfis.MANUTENCAO if manutencao else perfis.CONFIGURACAO
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
        self._auto_pendente = False  # leitura automática esperando as contas (ADR-073)
        self._ocultas_lista: frozenset[str] = frozenset()
        self._lista_contas: contas.Lista | None = None  # última leitura, para Encerrar sessões
        self._elegiveis: set[str] = set()  # SIDs que podiam ser alvo na última leitura
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
        self._carregar_perfis()  # do cadastro (ADR-060)
        self.perfil.currentIndexChanged.connect(lambda _i: self._montar_lista())
        self.rotulo_perfil = _rotulo("Perfil:")
        topo.addWidget(self.rotulo_perfil)
        topo.addWidget(self.perfil)
        topo.addStretch()
        v.addLayout(topo)
        if manutencao:
            self.rotulo_perfil.hide()
            self.perfil.hide()
        self.aviso = _rotulo("")
        v.addWidget(self.aviso)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só a leitura."))

        meio = QHBoxLayout()
        coluna_etapas = QVBoxLayout()
        self.lista = QTreeWidget()
        self.lista.setHeaderLabels(["Etapa", "Situação", "Detalhe"])
        self.lista.setColumnWidth(0, 210)
        self.lista.setColumnWidth(1, 150)
        self.lista.setRootIsDecorated(False)
        self.lista.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        coluna_etapas.addWidget(self.lista, 1)
        marcar_etapas = QHBoxLayout()
        self.b_etapas_todas = QPushButton("Marcar todas")
        self.b_etapas_todas.clicked.connect(lambda: self._marcar_etapas(True))
        self.b_etapas_nenhuma = QPushButton("Desmarcar todas")
        self.b_etapas_nenhuma.clicked.connect(lambda: self._marcar_etapas(False))
        marcar_etapas.addWidget(self.b_etapas_todas)
        marcar_etapas.addWidget(self.b_etapas_nenhuma)
        marcar_etapas.addStretch()
        coluna_etapas.addLayout(marcar_etapas)

        self.painel_alunos = QWidget()
        self.painel_alunos.setMaximumWidth(320)
        alunos = QVBoxLayout(self.painel_alunos)
        alunos.setContentsMargins(0, 0, 0, 0)
        alunos.addWidget(_rotulo("Contas locais"))
        self.alunos = QListWidget()
        alunos.addWidget(self.alunos, 1)
        marcar_contas = QHBoxLayout()
        self.b_contas_todas = QPushButton("Marcar todas")
        self.b_contas_todas.clicked.connect(lambda: self._marcar_contas(True))
        self.b_contas_nenhuma = QPushButton("Desmarcar todas")
        self.b_contas_nenhuma.clicked.connect(lambda: self._marcar_contas(False))
        marcar_contas.addWidget(self.b_contas_todas)
        marcar_contas.addWidget(self.b_contas_nenhuma)
        alunos.addLayout(marcar_contas)
        acoes_contas = QHBoxLayout()
        self.b_atualizar = QPushButton("Atualizar")
        self.b_atualizar.clicked.connect(lambda: self._carregar_alunos())
        self.b_encerrar = QPushButton("Encerrar sessões…")
        self.b_encerrar.clicked.connect(self._encerrar)
        acoes_contas.addWidget(self.b_atualizar)
        acoes_contas.addWidget(self.b_encerrar)
        alunos.addLayout(acoes_contas)
        meio.addLayout(coluna_etapas, 3)
        meio.addWidget(self.painel_alunos, 1)
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

    def _carregar_perfis(self) -> bool:
        """Preenche o seletor com os perfis do cadastro que valem para a unidade (ADR-060).
        Mantém o escolhido, se ainda existir. True se a lista mudou. Manutenção: nada."""
        if self.manutencao:
            return False
        lista = perfis.disponiveis(self.obter_cadastros(), self.obter_unidade())
        novos = [(p.nome, p.id) for p in lista]
        atuais = [
            (self.perfil.itemText(i), self.perfil.itemData(i)) for i in range(self.perfil.count())
        ]
        if novos == atuais:
            return False
        escolhido = self.perfil.currentData()
        self.perfil.blockSignals(True)
        self.perfil.clear()
        for nome, pid in novos:
            self.perfil.addItem(nome, pid)
        if escolhido is not None and (n := self.perfil.findData(escolhido)) >= 0:
            self.perfil.setCurrentIndex(n)
        self.perfil.blockSignals(False)
        return True

    def perfil_atual(self) -> perfis.Perfil | None:
        if self.manutencao:
            return perfis.Perfil("manutencao", "Manutenção", "", self.fluxo.ordem)
        cad = self.obter_cadastros()
        pid = self.perfil.currentData()
        if cad is None or pid is None:
            return None
        return next((p for p in cad.perfis if p.id == pid), None)

    def perfil_da_unidade(self) -> tuple[perfis.Perfil | None, str]:
        if self.manutencao:
            return self.perfil_atual(), ""
        return perfis.padrao(self.obter_cadastros(), self.obter_unidade())

    def ocultas(self) -> frozenset[str]:
        if self.manutencao:
            return etapas.ocultas_manutencao()  # Steam (ADR-064)
        perfil = str(self.perfil.currentData() or "")
        return etapas.ocultas(self.obter_cadastros(), self.obter_unidade(), perfil)

    def desmarcadas(self) -> list[str]:
        fora = list(self.ocultas())  # etapa escondida não roda (ADR-057)
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item is not None and item.checkState(0) != Qt.CheckState.Checked:
                fora.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return fora

    def alvos(self) -> list[str]:
        """SIDs das contas marcadas; conta bloqueada não tem SID no item e nunca entra."""
        saida = []
        for i in range(self.alunos.count()):
            item = self.alunos.item(i)
            sid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if sid and item is not None and item.checkState() == Qt.CheckState.Checked:
                saida.append(str(sid))
        return saida

    def _andamento_atual(self) -> prep.Andamento | None:
        """Andamento com as etapas marcadas **agora** (ADR-071). Situação da última leitura, se
        houver; sem leitura, todas "não iniciado" (o motor confere cada uma antes de aplicar)."""
        perfil = self.perfil_atual()
        if perfil is None:
            return None
        atual = prep.novo(perfil, self.desmarcadas())
        if self.andamento is not None:
            atual.situacao.update(self.andamento.situacao)
            atual.reinicio = self.andamento.reinicio
        return atual

    def _montar_lista(self, desmarcadas: tuple[str, ...] = ()) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        ocultas = self._ocultas_lista = self.ocultas()
        perfil = self.perfil_atual()
        if perfil is None:
            self.aviso.setText(perfis.SEM_PERFIL)
        for eid in perfil.etapas if perfil is not None else ():
            if eid in ocultas:
                continue  # sem papel do projeto: a lista pula da 3 para a 5 (ADR-057)
            item = QTreeWidgetItem([self.fluxo.rotulo(eid), prep.ROTULO["nao_iniciado"], ""])
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
            # Unidade ou cadastro mudou desde a última vez: os perfis e a etapa 10 mudam
            # (ADR-057, ADR-060).
            mudou = not self.ocupado and self._carregar_perfis()
            if not self.ocupado and (mudou or self.ocultas() != self._ocultas_lista):
                fora = tuple(e for e in self.desmarcadas() if e not in self._ocultas_lista)
                self._montar_lista(fora)
            return
        self._iniciar()

    def _iniciar(self, depois: Callable[[], None] | None = None) -> None:
        """Primeira montagem: perfil da unidade, lista de etapas e contas. `depois` roda quando
        as contas chegarem (a leitura das etapas precisa delas)."""
        self.iniciado = True
        if not self.manutencao:
            self._carregar_perfis()
            perfil, aviso = self.perfil_da_unidade()
            if perfil is not None:
                self.perfil.setCurrentIndex(self.perfil.findData(perfil.id))
        self._montar_lista()
        if not self.manutencao:
            self.aviso.setText(aviso)
        # Sem `depois`, a chamada de antes (os testes trocam _carregar_alunos por um falso).
        if depois is None:
            self._carregar_alunos()
        else:
            self._carregar_alunos(depois=depois)
        if not self.manutencao:
            self._ver_guardado()

    def ler_automatico(self) -> bool:
        """Lê a situação das etapas em segundo plano, uma vez, quando ninguém leu ainda nesta
        sessão (pedido pelo Início, ADR-073). Só leitura: nada é aplicado. True se começou."""
        if self.ocupado or self.andamento is not None:
            return False
        if not self.iniciado:
            self._auto_pendente = True
            self._iniciar(depois=self.ler)
        elif self.perfil_atual() is not None:
            self.ler()
        else:
            return False
        return self.perfil_atual() is not None

    def _carregar_alunos(
        self, marcar: tuple[str, ...] | None = None, depois: Callable[[], None] | None = None
    ) -> None:
        """Lê as contas locais (ADR-071). As que não podem ser alvo ficam cinza, sem marcar, com
        o motivo. `marcar`: SIDs a marcar (retomada); sem ele, mantém as marcações de antes e
        marca as que passaram a poder ser alvo."""
        cad = self.obter_cadastros()
        marcadas, conhecidas = set(self.alvos()), set(self._elegiveis)

        def ler() -> tuple[contas.Lista, list[tuple[contas.Conta, str]]]:
            lista = contas.listar()
            return lista, etapas.contas_locais(lista, contas.protegidas(cad))

        def recebeu(lido: tuple[contas.Lista, list[tuple[contas.Conta, str]]]) -> None:
            self._lista_contas, locais = lido
            self.alunos.clear()
            self._elegiveis = set()
            for c, motivo in locais:
                if motivo:
                    item = QListWidgetItem(f"{c.nome} — {motivo}")
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setFlags(
                        item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsUserCheckable
                    )
                    item.setToolTip(txt.dica(f"Não recebe as etapas: {motivo}."))
                    # O tema pinta item desativado com a cor normal: cinza explícito.
                    item.setForeground(QColor(tema.atual().mute))
                else:
                    item = QListWidgetItem(c.nome)
                    item.setData(Qt.ItemDataRole.UserRole, c.sid)
                    self._elegiveis.add(c.sid)
                    if marcar is not None:
                        sim = c.sid in marcar
                    else:
                        sim = c.sid in marcadas or c.sid not in conhecidas
                    item.setCheckState(Qt.CheckState.Checked if sim else Qt.CheckState.Unchecked)
                self.alunos.addItem(item)
            if not locais:
                self.alunos.addItem("Nenhuma conta local.")
            self._ocupar(self.ocupado)
            if depois is None:
                return
            if not self.ocupado and self.andamento is None:
                depois()
            elif self._auto_pendente:  # o técnico já leu ou rodou: a automática não precisa
                self._auto_pendente = False
                self.leitura.emit()

        def falhou(m: str) -> None:
            self._linha(f"Contas não lidas: {m}")
            if self._auto_pendente:  # sem contas, a leitura automática não começa
                self._auto_pendente = False
                self.leitura.emit()

        tarefa.iniciar(ler, recebeu, falhou)

    def _marcar_etapas(self, sim: bool) -> None:
        estado = Qt.CheckState.Checked if sim else Qt.CheckState.Unchecked
        self.lista.blockSignals(True)
        for i in range(self.lista.topLevelItemCount()):
            item = self.lista.topLevelItem(i)
            if item is not None:
                item.setCheckState(0, estado)
        self.lista.blockSignals(False)
        self._ocupar(self.ocupado)

    def _marcar_contas(self, sim: bool) -> None:
        """Só nas contas que podem ser alvo: as bloqueadas continuam sem marcar."""
        estado = Qt.CheckState.Checked if sim else Qt.CheckState.Unchecked
        for i in range(self.alunos.count()):
            item = self.alunos.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole):
                item.setCheckState(estado)

    def _encerrar(self) -> None:
        """Encerrar sessões (ADR-036), com o diálogo da tela Contas; depois relê as contas."""
        if self._lista_contas is None:
            return
        sids = ui_contas.pedir_encerrar(self, self._lista_contas)
        if not sids:
            return

        def feito(f: contas.Feito) -> None:
            self._ocupar(False)
            self._linha(f.mensagem)
            if not f.ok:
                self._aviso(f.mensagem)
            self._carregar_alunos()

        self._ocupar(True)
        self._linha("Encerrando sessões…")
        tarefa.iniciar(lambda: contas.encerrar_sessoes(sids), feito, self._falhou)

    def _ver_guardado(self) -> None:
        if not self.admin:
            return
        self.guardado = retomada.ler()
        if self.guardado is None:
            self.banner.hide()
            return
        quando = datetime.fromisoformat(self.guardado.criado_em).astimezone()
        cad = self.obter_cadastros()
        achado = (
            next((p for p in cad.perfis if p.id == self.guardado.perfil), None) if cad else None
        )
        nome = achado.nome if achado is not None else f"{self.guardado.perfil}, fora do cadastro"
        self.banner_texto.setText(
            f"Há uma preparação ({nome}) iniciada em {quando:%d/%m %H:%M}, com "
            f"{self.guardado.reinicios} reinício(s). Continuar de onde parou?"
        )
        self.banner.show()

    def _continuar(self) -> None:
        g = self.guardado
        if g is None:
            return
        n = self.perfil.findData(g.perfil)
        if n < 0:
            self._aviso(
                f"O perfil “{g.perfil}” da preparação guardada não está no cadastro desta "
                "unidade. Confira a tabela Perfis e sincronize, ou descarte a preparação."
            )
            return
        self.perfil.setCurrentIndex(n)
        self._montar_lista(g.desmarcadas)
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
        perfil = self.perfil_atual()
        self.ctx.perfil = perfil.id if perfil is not None and not self.manutencao else ""
        self.ctx.nome = ""  # Identificação saiu da Configuração (ADR-062)
        self.ctx.alvos = tuple(self.alvos())
        self.ctx.avisar = self.sinais.texto.emit
        self.ctx._lista = None
        if not self.etapas:
            montar = etapas.montar_manutencao if self.manutencao else etapas.montar
            self.etapas = montar(self.ctx)

    @property
    def lendo(self) -> bool:
        """Lendo ou rodando agora, ou com a leitura automática esperando as contas."""
        return self.ocupado or self._auto_pendente

    def ler(self) -> None:
        self._auto_pendente = False
        perfil = self.perfil_atual()
        if perfil is None:
            self._linha(perfis.SEM_PERFIL)
            self.leitura.emit()
            return
        self._preparar_ctx()
        self.andamento = prep.novo(perfil, self.desmarcadas())
        andamento, lista = self.andamento, self.etapas
        self._ocupar(True)
        self._linha("Lendo a situação das etapas…")
        self.leitura.emit()
        tarefa.iniciar(
            lambda: prep.ler_todas(lista, andamento, self.sinais.etapa.emit),
            self._terminou,
            self._falhou,
        )

    def confirmacao(self, andamento: prep.Andamento | None = None) -> str:
        """Texto da confirmação. Sem leitura, lista as etapas marcadas sem o detalhe."""
        a = andamento if andamento is not None else self.andamento
        if a is None:
            return ""
        linhas = []
        for eid in a.etapas:
            s = a.situacao.get(eid)
            if s is None or s.situacao not in ("pendente", "nao_iniciado"):
                continue
            detalhe = s.detalhe
            if eid == "contas":
                detalhe = etapas.Contas(self.ctx).mudancas()
            linhas.append(f"• {self.fluxo.rotulo(eid)}: {detalhe or 'aplicar'}")
        if COM_CONTAS & set(a.etapas):
            nomes = [
                self.alunos.item(i).text()
                for i in range(self.alunos.count())
                if self.alunos.item(i).data(Qt.ItemDataRole.UserRole) in self.ctx.alvos
            ]
            linhas.append("\nContas marcadas: " + (", ".join(nomes) if nomes else "nenhuma"))
        return f"Rodar a {self.fluxo.nome.lower()}?\n\n" + "\n".join(linhas)

    def _rodar(self) -> None:
        """Roda as etapas marcadas agora, com ou sem leitura antes (ADR-071)."""
        andamento = self._andamento_atual()
        if andamento is None or not andamento.etapas:
            return
        self._preparar_ctx()
        if not confirmar(self, "Preparação completa", self.confirmacao(andamento)):
            return
        self.pausar.clear()
        self.andamento = andamento
        lista, pausar = self.etapas, self.pausar
        self._ocupar(True)
        self._linha(f"Preparação ({andamento.nome or andamento.perfil}) iniciada.")
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
        self.leitura.emit()

    def _falhou(self, motivo: str) -> None:
        self._linha(f"Falha: {motivo}")
        self._ocupar(False)
        self.leitura.emit()

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
                rotulo = self.fluxo.rotulo(eid)
                self._linha(f"{rotulo}: {prep.ROTULO[s.situacao]}. {s.detalhe}".strip())

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
        perfil = self.perfil_atual()
        if perfil is None:
            return
        estado = retomada.novo(
            perfil.id,
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
        # ADR-071: conta pelas marcações atuais, com ou sem leitura.
        if (atual := self._andamento_atual()) is not None:
            pendentes = sum(
                1
                for e in atual.etapas
                if atual.situacao.get(e, prep.Leitura("nao_iniciado")).situacao
                in ("pendente", "nao_iniciado")
            )
        self.b_rodar.setText(f"Rodar {pendentes} etapa(s)" if pendentes else "Rodar etapas")
        self.b_rodar.setEnabled(self.admin and not ocupado and pendentes > 0)
        if not self.admin:
            self.b_rodar.setToolTip("Precisa de administrador.")
        self.b_ler.setEnabled(not ocupado and self.perfil_atual() is not None)
        self.b_pausar.setEnabled(ocupado)
        self.perfil.setEnabled(not ocupado)
        self.b_reiniciar.setEnabled(not ocupado and self.admin)
        for b in (
            self.b_etapas_todas,
            self.b_etapas_nenhuma,
            self.b_contas_todas,
            self.b_contas_nenhuma,
            self.b_atualizar,
        ):
            b.setEnabled(not ocupado)
        self.b_encerrar.setEnabled(self.admin and not ocupado)
        if not self.admin:
            self.b_encerrar.setToolTip("Precisa de administrador.")

    def _linha(self, texto: str) -> None:
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {texto}")

    def _aviso(self, texto: str) -> None:
        caixa = QMessageBox(QMessageBox.Icon.Warning, "Preparação completa", texto, parent=self)
        caixa.setTextFormat(Qt.TextFormat.PlainText)
        caixa.open()
