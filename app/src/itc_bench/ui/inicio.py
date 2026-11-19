"""Tela Início (ADR-023, item 6; visual do ADR-073): máquina, configuração, indicadores, alertas,
último diagnóstico e ações rápidas, numa grade de 4 colunas iguais."""

import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import inicio, limpeza, perfis, remoto
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.preparacao import Andamento, Leitura
from itc_bench.ui import tarefa, tema
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo
from itc_bench.ui.indicadores import Anel, Barra, Bateria, Desenho, numeros

AJUDA = (
    "Resumo do notebook numa tela só: a máquina, a configuração, quatro indicadores, os "
    "alertas, o último diagnóstico e as ações rápidas.\n"
    "\n"
    "Máquina\n"
    "Fabricante e modelo, série, Windows (10 ou 11, edição, versão e build), nome do computador "
    "e o técnico desta sessão. Se é 10 ou 11 vem do build: 22000 ou mais é Windows 11. O selo "
    "ao lado da unidade diz quantos alertas há, ou Tudo certo.\n"
    "\n"
    "Configuração\n"
    "O anel mostra quantas etapas do perfil já estão feitas e a lista, as pendentes. Na "
    "primeira vez que o Início abre na sessão, a situação é lida sozinha, em segundo plano, "
    "com o perfil padrão da unidade (pode levar alguns minutos; enquanto isso aparece Lendo a "
    "situação das etapas). Só lê: nada é aplicado. Depois, o cartão mostra a última leitura "
    "ou execução feita na tela Configuração.\n"
    "\n"
    "Indicadores\n"
    "Disco: quanto do disco do sistema está usado e quanto está livre. O anel fica laranja a "
    "partir de 85% usado e vermelho, com o cartão marcado Quase cheio, com menos de 10% livre "
    "(o mesmo limite do alerta). Bateria: a carga e se está na tomada; fora da tomada, fica "
    "laranja abaixo de 30% e vermelha abaixo de 15%. Embaixo, a saúde: quanto a bateria segura "
    "hoje em relação à capacidade de fábrica, laranja abaixo de 80% e vermelha abaixo de 50%, "
    "e quantos ciclos de carga já fez (os mesmos números do relatório de bateria do Windows). "
    "Sem bateria, o cartão diz isso. "
    "Processador: modelo, núcleos, threads e o uso no momento da leitura. Memória: total "
    "instalado, uso no momento da leitura, tipo e quantos slots estão livres.\n"
    "\n"
    "Alertas\n"
    "Cada alerta tem o botão da tela que resolve; o de disco quase cheio leva a Limpar "
    "temporários. Críticos (contados no selo vermelho do menu): proteção do login fora do "
    "lugar (arquivo trocado ou ausente, depurador, não protegido, inclusive cmd e PowerShell), "
    "política da máquina do perfil faltando e conta Suporte ausente ou sem administrador. De "
    "atenção: nome do computador esperando reinício, sem cadastros ou cadastros com mais de 1 "
    "dia, diagnóstico na fila de envio e menos de 10% de disco livre.\n"
    "\n"
    "Último diagnóstico\n"
    "Mostra quantos diagnósticos esperam envio. Coleta e laudo abre a tela do diagnóstico.\n"
    "\n"
    "Ações rápidas\n"
    "Forçar inventário GLPI pede ao GLPI Agent desta máquina um inventário agora. Limpar "
    "temporários abre a Limpeza com a prévia; nada é apagado sem confirmação.\n"
    "\n"
    "A leitura roda ao abrir e vale por 1 minuto; Atualizar lê de novo. O que não pôde ser lido "
    "aparece como — e é listado em Não lido. Sem administrador, proteção, políticas e contas "
    "não são lidas."
)


MUTEX_ALHEIO = (
    "Outro usuário deste computador ocupa o identificador do ITC Bench. A atualização "
    "automática continua protegida, mas não rode o instalador manualmente com o Bench aberto."
)
AJUDA_MUTEX = (
    "O ITC Bench marca que está aberto com um identificador do Windows. Outra sessão, de um "
    "usuário sem administrador, criou esse identificador antes. Peça para encerrar a sessão "
    "desse usuário (Gerenciador de Tarefas, aba Usuários, ou sair da conta) e abra o Bench de "
    "novo. Até lá, instale versões novas só com o Bench fechado."
)
# Alerta → (título, ícone, botão), pela tela que resolve. O texto continua o do serviço.
VISUAL_ALERTA = {
    "protecao": ("Proteção do login", "escudo", "Abrir"),
    "gpo": ("Políticas", "escudo", "Abrir"),
    "contas": ("Conta Suporte", "contas", "Abrir"),
    "id": ("Nome do computador", "id", "Abrir"),
    "config": ("Cadastros", "config", "Abrir"),
    "diag": ("Diagnóstico", "diag", "Abrir"),
    "limpeza": ("Disco quase cheio", "disco", "Limpar temporários"),
}
COLUNAS = 4
MINIMO_COLUNA = 220  # 4 x 220 + 3 x 20 cabe em 1366x768 com a barra lateral
PENDENTES_VISIVEIS = 3
NIVEL_TEXTO = {"normal": "Normal", "atencao": "Atenção", "critico": "Quase cheio"}


def _gb(n: int | None) -> str:
    return "—" if n is None else limpeza.tamanho(n)


def _label(texto: str, nome: str, quebra: bool = True) -> QLabel:
    r = QLabel(texto)
    r.setObjectName(nome)
    r.setWordWrap(quebra)
    r.setTextFormat(Qt.TextFormat.PlainText)
    return r


def _nivel(widget: QWidget, nivel: str) -> None:
    """Propriedade usada na folha de estilo (`[nivel="critico"]`); repinta na hora."""
    widget.setProperty("nivel", nivel)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _cartao(colunas: int = 1) -> tuple[QFrame, QVBoxLayout]:
    c = QFrame()
    c.setObjectName("inicioCartao")
    c.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    # Largura vem só da grade (colunas iguais); a altura, do conteúdo.
    c.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    v = QVBoxLayout(c)
    margem = 24 if colunas > 1 else 20
    v.setContentsMargins(margem, margem, margem, margem)
    v.setSpacing(14)
    return c, v


class PainelInicio(QWidget):
    abrir = Signal(str)
    criticos = Signal(int)
    ajuda = Signal()

    def __init__(
        self,
        admin: bool,
        obter_cadastros: Callable[[], Cadastros | None],
        obter_unidade: Callable[[], str],
        fila: Callable[[], int],
        obter_perfil: Callable[[], perfis.Perfil | None],
        obter_andamento: Callable[[], Andamento | None],
        mutex_alheio: bool = False,
        obter_tecnico: Callable[[], str] = lambda: "",
        ler_preparacao: Callable[[], bool] = lambda: False,
        obter_lendo: Callable[[], bool] = lambda: False,
    ) -> None:
        super().__init__()
        self.setObjectName("inicio")
        self.admin = admin
        self.obter_cadastros = obter_cadastros
        self.obter_unidade = obter_unidade
        self.fila = fila
        self.obter_perfil = obter_perfil
        self.obter_andamento = obter_andamento
        self.obter_tecnico = obter_tecnico
        # ADR-073: a Configuração lê a situação sozinha, em segundo plano, na primeira vez.
        self.ler_preparacao = ler_preparacao
        self.obter_lendo = obter_lendo
        self.painel: inicio.Painel | None = None
        self.ocupado = False
        # (QLabel ou QPushButton, ícone, tipo de cor, tamanho): repintados ao trocar o modo.
        self._icones: list[tuple[QWidget, str, str, int]] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(20)
        v.addLayout(self._cabecalho())
        self.aviso = _label("", "inicioRotulo")
        self.aviso.hide()
        v.addWidget(self.aviso)
        # ADR-026: Global\ITCBench de outro usuário; o instalador manual não vê o Bench aberto.
        self.aviso_mutex: QLabel | None = None
        if mutex_alheio:
            linha = QHBoxLayout()
            self.aviso_mutex = _rotulo("⚠ " + MUTEX_ALHEIO)
            ajuda = QPushButton("?")
            ajuda.setToolTip(txt.dica(AJUDA_MUTEX))
            linha.addWidget(self.aviso_mutex, 1)
            linha.addWidget(ajuda)
            v.addLayout(linha)

        grade = QGridLayout()
        grade.setHorizontalSpacing(20)
        grade.setVerticalSpacing(20)
        for c in range(COLUNAS):
            grade.setColumnStretch(c, 1)
            grade.setColumnMinimumWidth(c, MINIMO_COLUNA)
        grade.addWidget(self._maquina(), 0, 0, 1, 3)
        grade.addWidget(self._configuracao(), 0, 3)
        grade.addWidget(self._disco(), 1, 0)
        grade.addWidget(self._bateria(), 1, 1)
        grade.addWidget(self._processador(), 1, 2)
        grade.addWidget(self._memoria(), 1, 3)
        grade.addWidget(self._alertas(), 2, 0, 1, 3)
        grade.addWidget(self._diagnostico(), 2, 3)
        v.addLayout(grade)
        v.addLayout(self._acoes())
        v.addStretch()
        self._mostrar_maquina(None)

    # ---- montagem

    def _icone(self, nome: str, tipo: str = "destaque", tamanho: int = 20) -> QLabel:
        r = QLabel()
        r.setFixedSize(tamanho, tamanho)
        self._icones.append((r, nome, tipo, tamanho))
        self._pintar(r, nome, tipo, tamanho)
        return r

    def _caixa_icone(
        self, nome: str, tipo: str = "destaque", objeto: str = "inicioIcone"
    ) -> QLabel:
        r = self._icone(nome, tipo, 20)
        r.setObjectName(objeto)
        r.setFixedSize(36, 36)
        r.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        return r

    def _botao(self, texto: str, icone: str = "", primario: bool = False) -> QPushButton:
        b = QPushButton(texto)
        if primario:
            b.setObjectName("primario")
        if icone:
            self._icones.append((b, icone, "destaque", 18))
            self._pintar(b, icone, "destaque", 18)
        return b

    def _pintar(self, w: QWidget, nome: str, tipo: str, tamanho: int) -> None:
        p = tema.atual()
        cor = {"destaque": p.destaque, "texto": p.texto, "mute": p.mute, "ok": p.ok,
               "critico": p.err, "atencao": p.warn}.get(tipo, p.destaque)  # fmt: skip
        if isinstance(w, QPushButton):
            w.setIcon(tema.icone(nome, cor, tamanho))
        elif isinstance(w, QLabel):
            w.setPixmap(tema.pixmap(tema.svg(f"icones/{nome}.svg", cor), tamanho))

    def changeEvent(self, evento: QEvent) -> None:
        super().changeEvent(evento)
        if evento.type() == QEvent.Type.PaletteChange:  # claro ↔ escuro (ADR-037)
            for w, nome, tipo, tamanho in self._icones:
                self._pintar(w, nome, tipo, tamanho)

    def _cabecalho(self) -> QHBoxLayout:
        h = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(4)
        marca = _label("ITC BENCH", "inicioMarca", quebra=False)
        fonte = marca.font()
        fonte.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 142)
        marca.setFont(fonte)
        textos.addWidget(marca)
        textos.addWidget(_label("Início", "inicioTitulo", quebra=False))
        h.addLayout(textos)
        h.addStretch()
        self.estado = _label("", "inicioMute", quebra=False)
        self.estado.setFont(numeros(self.estado.font()))
        self.atualizar = self._botao("Atualizar", "atualizar")
        self.atualizar.clicked.connect(lambda: self.carregar(forcar=True))
        self.b_ajuda = QPushButton("?")
        self.b_ajuda.setObjectName("inicioAjuda")
        self.b_ajuda.setToolTip("Ajuda desta tela")
        self.b_ajuda.setAccessibleName("Ajuda desta tela")
        self.b_ajuda.clicked.connect(self.ajuda.emit)
        h.addWidget(self.estado, 0, Qt.AlignmentFlag.AlignBottom)
        h.addWidget(self.atualizar, 0, Qt.AlignmentFlag.AlignBottom)
        h.addWidget(self.b_ajuda, 0, Qt.AlignmentFlag.AlignBottom)
        return h

    def _maquina(self) -> QFrame:
        c, v = _cartao(colunas=3)
        h = QHBoxLayout()
        h.setSpacing(28)
        arte = QFrame()
        arte.setObjectName("inicioArte")
        arte.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        arte.setFixedSize(200, 150)
        la = QVBoxLayout(arte)
        la.addWidget(Desenho("icones/notebook.svg", 164, 112), 0, Qt.AlignmentFlag.AlignCenter)
        h.addWidget(arte, 0, Qt.AlignmentFlag.AlignVCenter)
        dados = QVBoxLayout()
        dados.setSpacing(12)
        dados.addStretch()  # o cartão cresce com a Configuração; os dados ficam no meio
        selos = QHBoxLayout()
        selos.setSpacing(8)
        self.selo_unidade = _label("", "inicioSelo", quebra=False)
        self.selo_estado = _label("carregando…", "inicioSelo", quebra=False)
        for s in (self.selo_unidade, self.selo_estado):
            s.setFixedHeight(26)
            selos.addWidget(s)
        selos.addStretch()
        dados.addLayout(selos)
        self.modelo = _label("—", "inicioModelo")
        dados.addWidget(self.modelo)
        campos = QGridLayout()
        campos.setHorizontalSpacing(24)
        campos.setVerticalSpacing(10)
        self.campos: dict[str, QLabel] = {}
        for i, (chave, rotulo) in enumerate(
            (("serie", "Série"), ("windows", "Windows"), ("nome", "Nome do computador"),
             ("tecnico", "Técnico"))
        ):  # fmt: skip
            caixa = QVBoxLayout()
            caixa.setSpacing(2)
            caixa.addWidget(_label(rotulo, "inicioRotulo"))
            valor = _label("—", "inicioValor")
            valor.setFont(numeros(valor.font()))
            caixa.addWidget(valor)
            self.campos[chave] = valor
            campos.addLayout(caixa, i // 2, i % 2)
        campos.setColumnStretch(0, 1)
        campos.setColumnStretch(1, 1)
        dados.addLayout(campos)
        dados.addStretch()
        h.addLayout(dados, 1)
        v.addLayout(h)
        return c

    def _titulo(self, v: QVBoxLayout, icone: str, titulo: str) -> None:
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(self._caixa_icone(icone))
        h.addWidget(_label(titulo, "inicioCartaoTitulo"), 1)
        v.addLayout(h)

    def _configuracao(self) -> QFrame:
        c, v = _cartao()
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)
        self._titulo(v, "lista", "Configuração")
        h = QHBoxLayout()
        h.setSpacing(18)
        self.anel_prep = Anel(84, 9, 20)
        h.addWidget(self.anel_prep)
        textos = QVBoxLayout()
        textos.setSpacing(4)
        self.prep_perfil = _label("", "inicioValor")
        self.prep = _label("", "inicioMute")
        textos.addWidget(self.prep_perfil)
        textos.addWidget(self.prep)
        h.addLayout(textos, 1)
        v.addLayout(h)
        self.v_pendentes = QVBoxLayout()
        self.v_pendentes.setSpacing(8)
        v.addLayout(self.v_pendentes)
        self.linhas_pendentes: list[QWidget] = []
        v.addStretch()
        b = self._botao("Abrir configuração", primario=True)
        b.clicked.connect(lambda: self.abrir.emit("prep"))
        v.addWidget(b)
        return c

    def _cabeca_indicador(self, v: QVBoxLayout, icone: str, titulo: str) -> QLabel:
        h = QHBoxLayout()
        h.setSpacing(8)
        h.addWidget(self._icone(icone, "mute", 20))
        h.addWidget(_label(titulo, "inicioSecao", quebra=False))
        h.addStretch()
        estado = _label("", "inicioEstado", quebra=False)
        h.addWidget(estado)
        v.addLayout(h)
        return estado

    def _disco(self) -> QFrame:
        c, v = _cartao()
        self.cartao_disco = c
        self.disco_estado = self._cabeca_indicador(v, "disco", "Disco")
        h = QHBoxLayout()
        h.setSpacing(16)
        self.anel_disco = Anel(72, 10, 14)
        h.addWidget(self.anel_disco)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.disco_livre = _label("—", "inicioNumero", quebra=False)
        self.disco_livre.setFont(numeros(self.disco_livre.font()))
        self.disco_total = _label("", "inicioMute")
        textos.addWidget(self.disco_livre)
        textos.addWidget(self.disco_total)
        h.addLayout(textos, 1)
        v.addLayout(h)
        v.addStretch()
        return c

    def _bateria(self) -> QFrame:
        c, v = _cartao()
        h0 = QHBoxLayout()
        h0.setSpacing(8)
        h0.addWidget(self._icone("bateria", "mute", 20))
        h0.addWidget(_label("Bateria", "inicioSecao", quebra=False))
        h0.addStretch()
        self.icone_tomada = self._icone("raio", "ok", 14)
        self.bateria_estado = _label("", "inicioEstado", quebra=False)
        h0.addWidget(self.icone_tomada)
        h0.addWidget(self.bateria_estado)
        v.addLayout(h0)
        h = QHBoxLayout()
        h.setSpacing(16)
        self.desenho_bateria = Bateria()
        h.addWidget(self.desenho_bateria)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.bateria_carga = _label("—", "inicioNumero", quebra=False)
        self.bateria_carga.setFont(numeros(self.bateria_carga.font()))
        self.bateria_texto = _label("", "inicioMute")
        textos.addWidget(self.bateria_carga)
        textos.addWidget(self.bateria_texto)
        h.addLayout(textos, 1)
        v.addLayout(h)
        # Saúde: carga máxima de hoje sobre a de fábrica (ADR-073).
        self.bateria_saude = _label("", "inicioEstado")
        self.bateria_saude.setFont(numeros(self.bateria_saude.font()))
        self.bateria_saude.setToolTip(
            "Quanto a bateria segura hoje em relação à capacidade de fábrica. Abaixo de 80% está "
            "gasta; abaixo de 50%, pede troca. Ciclos: quantas cargas completas ela já fez."
        )
        v.addWidget(self.bateria_saude)
        v.addStretch()
        return c

    def _processador(self) -> QFrame:
        c, v = _cartao()
        self._cabeca_indicador(v, "cpu", "Processador")
        self.cpu_modelo = _label("—", "inicioNumero")
        self.cpu_nucleos = _label("", "inicioMute")
        self.barra_cpu = Barra()
        self.cpu_uso = _label("", "inicioRotulo")
        for w in (self.cpu_modelo, self.cpu_nucleos, self.barra_cpu, self.cpu_uso):
            v.addWidget(w)
        v.addStretch()
        return c

    def _memoria(self) -> QFrame:
        c, v = _cartao()
        self._cabeca_indicador(v, "memoria", "Memória")
        h = QHBoxLayout()
        h.setSpacing(8)
        self.mem_total = _label("—", "inicioNumero", quebra=False)
        self.mem_total.setFont(numeros(self.mem_total.font()))
        self.mem_uso = _label("", "inicioMute", quebra=False)
        h.addWidget(self.mem_total, 0, Qt.AlignmentFlag.AlignBaseline)
        h.addWidget(self.mem_uso, 1, Qt.AlignmentFlag.AlignBaseline)
        v.addLayout(h)
        self.barra_mem = Barra()
        self.mem_detalhe = _label("", "inicioRotulo")
        v.addWidget(self.barra_mem)
        v.addWidget(self.mem_detalhe)
        v.addStretch()
        return c

    def _alertas(self) -> QFrame:
        c, v = _cartao(colunas=3)
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(_label("Alertas", "inicioCartaoTitulo", quebra=False))
        self.contador = _label("", "inicioContador", quebra=False)
        self.contador.setFixedHeight(22)
        self.contador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.contador)
        h.addStretch()
        v.addLayout(h)
        self.vazio = QWidget()
        hv = QHBoxLayout(self.vazio)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(10)
        hv.addWidget(self._icone("ok", "ok", 22))
        self.sem_alertas = _label("carregando…", "inicioMute")
        hv.addWidget(self.sem_alertas, 1)
        v.addWidget(self.vazio)
        self.v_alertas = QVBoxLayout()
        self.v_alertas.setSpacing(10)
        v.addLayout(self.v_alertas)
        self.linhas_alerta: list[QWidget] = []
        v.addStretch()
        return c

    def _diagnostico(self) -> QFrame:
        c, v = _cartao()
        v.setContentsMargins(24, 24, 24, 24)
        self._titulo(v, "diag", "Último diagnóstico")
        self.diag = _label("", "inicioMute")
        v.addWidget(self.diag)
        v.addStretch()
        b = self._botao("Coleta e laudo")
        b.clicked.connect(lambda: self.abrir.emit("diag"))
        v.addWidget(b)
        return c

    def _acoes(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(12)
        rotulo = _label("AÇÕES RÁPIDAS", "inicioSecao", quebra=False)
        fonte = rotulo.font()
        fonte.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        rotulo.setFont(fonte)
        h.addWidget(rotulo)
        self.b_inventario = self._botao("Forçar inventário GLPI", "inventario")
        self.b_inventario.clicked.connect(self._inventario)
        self.b_inventario.setEnabled(self.admin)
        b_limpar = self._botao("Limpar temporários", "lixeira")
        b_limpar.clicked.connect(lambda: self.abrir.emit("limpeza"))
        h.addWidget(self.b_inventario)
        h.addWidget(b_limpar)
        h.addStretch()
        return h

    # ---- dados

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        self.mostrar_preparacao()
        self.carregar()

    def mostrar_preparacao(self) -> None:
        perfil = self.obter_perfil()
        a = self.obter_andamento()
        for w in self.linhas_pendentes:
            w.deleteLater()
        self.linhas_pendentes = []
        if a is None:
            lendo = perfil is not None and self.obter_lendo()
            self.anel_prep.definir(None, "…" if lendo else "—")
            self.prep_perfil.setText(f"Perfil {perfil.nome}" if perfil is not None else "")
            if perfil is None:
                self.prep.setText(perfis.SEM_PERFIL)
            elif lendo:
                self.prep.setText("Lendo a situação das etapas…")
            else:
                self.prep.setText("Situação não lida. Abra a configuração e use Ler situação.")
        else:
            total, feitas = len(a.etapas), a.feitas()
            self.anel_prep.definir(feitas / total if total else 0, f"{feitas}/{total}")
            self.prep_perfil.setText(f"Perfil {a.nome or a.perfil}")
            self.prep.setText(
                f"{feitas} de {total} etapas feitas"
                + (" · reinício pendente" if a.reinicio else "")
            )
            pendentes = [
                e
                for e in a.etapas
                if a.situacao.get(e, Leitura("nao_iniciado")).situacao == "pendente"
            ]
            for eid in pendentes[:PENDENTES_VISIVEIS]:
                self._linha_pendente(perfis.CONFIGURACAO.rotulo(eid))
            if len(pendentes) > PENDENTES_VISIVEIS:
                self._linha_pendente(f"e mais {len(pendentes) - PENDENTES_VISIVEIS}", "")
        n = self.fila()
        self.diag.setText(
            f"{n} diagnóstico(s) esperando envio." if n else "Nenhum diagnóstico na fila de envio."
        )

    def _linha_pendente(self, texto: str, situacao: str = "pendente") -> None:
        linha = QFrame()
        linha.setObjectName("inicioCaixa")
        linha.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        h = QHBoxLayout(linha)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)
        h.addWidget(_label(texto, "inicioValor"), 1)
        if situacao:
            h.addWidget(_label(situacao, "inicioPendente", quebra=False))
        self.v_pendentes.addWidget(linha)
        self.linhas_pendentes.append(linha)

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
        if self.obter_andamento() is None and self.ler_preparacao():
            self.mostrar_preparacao()

    def _mostrar_maquina(self, m: inicio.Maquina | None) -> None:
        unidade = self.obter_unidade()
        self.selo_unidade.setText(
            f"Unidade {unidade}" if unidade and unidade != "—" else "Sem unidade"
        )
        self.campos["tecnico"].setText(self.obter_tecnico() or "—")
        if m is None:
            self.modelo.setText("—")
            for chave in ("serie", "windows", "nome"):
                self.campos[chave].setText("—")
        else:
            self.modelo.setText(f"{m.fabricante} {m.modelo}".strip() or "—")
            self.campos["serie"].setText(m.serie or "—")
            self.campos["windows"].setText(m.windows or "—")
            self.campos["nome"].setText(m.nome or "—")
        self._mostrar_disco(m)
        self._mostrar_bateria(m)
        self._mostrar_cpu(m)
        self._mostrar_memoria(m)

    def _mostrar_disco(self, m: inicio.Maquina | None) -> None:
        usado = m.disco_usado if m is not None else None
        nivel = inicio.nivel_disco(usado)
        tipo = {"normal": "destaque", "atencao": "atencao", "critico": "critico"}[nivel]
        self.anel_disco.definir(usado, "—" if usado is None else f"{round(usado * 100)}%", tipo)
        self.disco_livre.setText(_gb(m.disco_livre) if m is not None else "—")
        self.disco_total.setText(
            f"livres de {_gb(m.disco_total)}" if m is not None and m.disco_total else ""
        )
        self.disco_estado.setText("" if usado is None else NIVEL_TEXTO[nivel])
        _nivel(self.disco_estado, nivel)
        _nivel(self.cartao_disco, nivel)

    def _mostrar_bateria(self, m: inicio.Maquina | None) -> None:
        carga = m.bateria if m is not None else None
        tomada = m.na_tomada if m is not None else None
        nivel = inicio.nivel_bateria(carga, tomada)
        tipo = {"normal": "ok", "atencao": "atencao", "critico": "critico"}[nivel]
        self.desenho_bateria.definir(carga, tipo)
        if m is None:
            self.bateria_carga.setText("—")
            self.bateria_texto.setText("")
            self.bateria_estado.setText("")
        elif carga is None:
            self.bateria_carga.setText("—")
            self.bateria_texto.setText("Sem bateria")
            self.bateria_estado.setText("")
        else:
            self.bateria_carga.setText(f"{carga}%")
            self.bateria_texto.setText("na tomada" if tomada else "na bateria")
            self.bateria_estado.setText("Na tomada" if tomada else "Na bateria")
        _nivel(self.bateria_estado, "ok" if tomada else nivel)
        self.icone_tomada.setVisible(bool(tomada) and carga is not None)
        saude = m.bateria_saude if m is not None else None
        self.bateria_saude.setVisible(m is not None and carga is not None)
        ciclos = m.bateria_ciclos if m is not None else None
        texto = f"Saúde: {saude}%" if saude else "Saúde: —"
        if ciclos is not None:
            texto += f" · {ciclos} ciclo" + ("s" if ciclos != 1 else "")
        self.bateria_saude.setText(texto)
        _nivel(self.bateria_saude, inicio.nivel_saude(saude) if saude else "")

    def _mostrar_cpu(self, m: inicio.Maquina | None) -> None:
        self.cpu_modelo.setText(m.processador if m is not None and m.processador else "—")
        partes = []
        if m is not None and m.cpu_nucleos:
            partes.append(f"{m.cpu_nucleos} núcleos")
        if m is not None and m.cpu_threads:
            partes.append(f"{m.cpu_threads} threads")
        self.cpu_nucleos.setText(" · ".join(partes))
        uso = m.cpu_uso if m is not None else None
        self.barra_cpu.setVisible(uso is not None)
        self.barra_cpu.definir(None if uso is None else uso / 100)
        self.cpu_uso.setText("" if uso is None else f"{uso}% de uso agora")

    def _mostrar_memoria(self, m: inicio.Maquina | None) -> None:
        total = m.mem_total if m is not None else None
        self.mem_total.setText(f"{round(total / (1 << 30))} GB" if total else "—")
        uso = m.mem_uso if m is not None else None
        self.mem_uso.setText("" if uso is None else f"{uso}% em uso")
        self.barra_mem.setVisible(uso is not None)
        self.barra_mem.definir(None if uso is None else uso / 100)
        partes = []
        if m is not None and m.mem_tipo:
            partes.append(m.mem_tipo)
        if m is not None and m.mem_slots:
            livres = m.mem_slots - (m.mem_modulos or 0)
            slots = f"{m.mem_slots} slot" + ("s" if m.mem_slots > 1 else "")
            partes.append(f"{slots}, {max(0, livres)} livre" + ("s" if livres > 1 else ""))
        self.mem_detalhe.setText(" · ".join(partes))

    def _texto_alerta(self, a: inicio.Alerta, titulo: str, m: inicio.Maquina | None) -> str:
        if a.tela == "limpeza" and m is not None and m.disco_total and m.disco_livre is not None:
            pct = round(100 * m.disco_livre / m.disco_total)
            return (
                f"Só {_gb(m.disco_livre)} livres ({pct}%). Atualizações e o diagnóstico podem "
                "falhar."
            )
        prefixo = f"{titulo}: "
        return a.texto[len(prefixo) :] if a.texto.startswith(prefixo) else a.texto

    def _linha_alerta(self, a: inicio.Alerta, m: inicio.Maquina | None) -> QWidget:
        titulo, icone, acao = VISUAL_ALERTA.get(a.tela, ("Alerta", "escudo", "Abrir"))
        linha = QFrame()
        linha.setObjectName("inicioAlerta")
        linha.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        _nivel(linha, a.nivel)
        h = QHBoxLayout(linha)
        h.setContentsMargins(14, 14, 14, 14)
        h.setSpacing(14)
        h.addWidget(self._caixa_icone(icone, a.nivel, "inicioIconeAlerta"))
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(_label(titulo, "inicioValor"))
        textos.addWidget(_label(self._texto_alerta(a, titulo, m), "inicioMute"))
        h.addLayout(textos, 1)
        b = QPushButton(acao)
        b.setIcon(tema.icone("avancar", tema.atual().texto, 16))
        b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # seta depois do texto
        b.clicked.connect(lambda _c=False, tela=a.tela: self.abrir.emit(tela))
        h.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return linha

    def _recebeu(self, p: inicio.Painel) -> None:
        self.painel = p
        self.ocupado = False
        self.atualizar.setEnabled(True)
        m = p.maquina
        self._mostrar_maquina(m)
        for w in self.linhas_alerta:
            w.deleteLater()
        self.linhas_alerta = []
        n = len(p.alertas)
        self.vazio.setVisible(not n)
        self.sem_alertas.setText("Nenhum alerta. Tudo certo nesta máquina.")
        self.contador.setVisible(bool(n))
        self.contador.setText(str(n))
        for a in p.alertas:
            linha = self._linha_alerta(a, m)
            self.v_alertas.addWidget(linha)
            self.linhas_alerta.append(linha)
        if n:
            self.selo_estado.setText(f"{n} alerta" + ("s" if n > 1 else ""))
        else:  # sem alerta, mas com leitura falhando: não dá para dizer "Tudo certo"
            self.selo_estado.setText("Leitura incompleta" if p.erros else "Tudo certo")
        _nivel(self.selo_estado, "critico" if n else ("" if p.erros else "ok"))
        self.estado.setText(f"Lido às {time.strftime('%H:%M')}")
        avisos = []
        if p.erros:
            avisos.append(f"Não lido: {', '.join(p.erros)}.")
        if not self.admin:
            avisos.append("Sem administrador: proteção, políticas e contas não lidas.")
        self.aviso.setText(" ".join(avisos))
        self.aviso.setVisible(bool(avisos))
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
