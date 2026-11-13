"""Tela Limpeza (ADR-023, item 7). Regras e caminhos em `servicos/limpeza.py`; aqui só tela."""

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from itc_bench.servicos import contas, limpeza
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.ui import tarefa
from itc_bench.ui import texto as txt
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Apaga arquivos que o Windows e os programas deixam para trás. Lista fechada: temporários "
    "do sistema, temporários de cada conta, lixeira de todas as contas, cache de download do "
    "Windows Update e relatórios de erro do Windows.\n\n"
    "Como usar\n"
    "1. Calcular mostra quanto cada item ocupa, sem apagar nada.\n"
    "2. Marque o que quer limpar e confirme. Só os itens marcados são apagados.\n"
    "3. Arquivo em uso fica e aparece como “em uso”.\n\n"
    "Windows Update\n"
    "O Bench para o serviço do Windows Update, apaga o cache de download e volta o serviço como "
    "estava. Com atualização esperando reinício, o item fica “não limpo”: reinicie e limpe de "
    "novo.\n\n"
    "O que a limpeza de manutenção não apaga\n"
    "Documentos, Área de Trabalho, Downloads e dados de navegador (isso fica na Limpeza de "
    "contas, abaixo), perfis de conta, Windows.old e pontos de restauração. Atalhos e links "
    "dentro das pastas são removidos como link, sem entrar no destino.\n\n"
    "Limpeza de contas\n"
    "Esvazia, em cada conta marcada, o que pesa no disco: Área de Trabalho, Documentos, "
    "Downloads, Imagens, Vídeos, Músicas e Jogos salvos; temporários e caches do Windows; cache "
    "do Edge, do Chrome, do Firefox e do Teams; e programas instalados só para a conta. Fica tudo "
    "o que é configuração: o registro da conta (papel de parede, políticas, preferências), o tipo "
    "de conta, favoritos e senhas dos navegadores e os apps da Microsoft Store.\n"
    "1. Calcular contas mostra quanto cada conta ocupa, sem apagar nada.\n"
    "2. Marque as contas e clique em Limpar contas. O Bench pede duas confirmações. Os arquivos "
    "são apagados de vez, sem lixeira.\n"
    "3. A conta precisa estar sem sessão aberta: saia dela ou use Contas › Encerrar sessões….\n"
    "Nunca são limpos: o Administrador nativo, a conta Suporte, a conta Gestão e a conta que está "
    "rodando o Bench.\n\n"
    "Sem administrador (modo de teste), só a prévia do que dá para ler."
)


class PainelLimpeza(QWidget):
    def __init__(
        self, admin: bool, obter_cadastros: Callable[[], Cadastros | None] | None = None
    ) -> None:
        super().__init__()
        self.admin = admin
        self.obter_cadastros = obter_cadastros or (lambda: None)
        self.previa: dict[str, limpeza.Item] = {}
        self.ocupado = self.lido = False
        v = QVBoxLayout(self)
        self.estado = _rotulo("")
        v.addWidget(self.estado)
        if not admin:
            v.addWidget(_rotulo("Sem administrador: só a prévia."))
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Item", "Arquivos", "Tamanho", "Situação"])
        self.arvore.setColumnWidth(0, 280)
        self.arvore.setRootIsDecorated(False)
        for iid, nome in limpeza.ITENS:
            item = QTreeWidgetItem([nome, "", "", "não calculado"])
            item.setData(0, Qt.ItemDataRole.UserRole, iid)
            item.setCheckState(
                0, Qt.CheckState.Checked if iid != "lixeira" else Qt.CheckState.Unchecked
            )
            self.arvore.addTopLevelItem(item)
        self.arvore.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        v.addWidget(self.arvore, 2)
        acoes = QHBoxLayout()
        self.b_calcular = QPushButton("Calcular")
        self.b_calcular.clicked.connect(self.calcular)
        self.b_limpar = QPushButton("Limpar")
        self.b_limpar.setObjectName("primario")
        self.b_limpar.clicked.connect(self._limpar)
        acoes.addStretch()
        acoes.addWidget(self.b_calcular)
        acoes.addWidget(self.b_limpar)
        v.addLayout(acoes)
        self.contas = PainelLimpezaContas(admin, self.obter_cadastros)
        v.addWidget(self.contas, 3)
        self._ocupar(False)

    def marcar(self, ids: Iterable[str]) -> None:
        fora = set(ids)
        for i in range(self.arvore.topLevelItemCount()):
            item = self.arvore.topLevelItem(i)
            if item is not None:
                iid = item.data(0, Qt.ItemDataRole.UserRole)
                estado = Qt.CheckState.Checked if iid in fora else Qt.CheckState.Unchecked
                item.setCheckState(0, estado)

    def marcados(self) -> list[str]:
        saida = []
        for i in range(self.arvore.topLevelItemCount()):
            item = self.arvore.topLevelItem(i)
            if item is not None and item.checkState(0) == Qt.CheckState.Checked:
                saida.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return saida

    def showEvent(self, evento: QShowEvent) -> None:
        super().showEvent(evento)
        if not self.lido and not self.ocupado:
            self.calcular()

    def calcular(self) -> None:
        self._ocupar(True)
        self.estado.setText("Calculando…")
        tarefa.iniciar(
            lambda: limpeza.previa([i for i, _ in limpeza.ITENS]), self._calculou, self._falhou
        )

    def _mostrar(self, itens: list[limpeza.Item], limpou: bool) -> None:
        por = {i.id: i for i in itens}
        for n in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(n)
            if linha is None:
                continue
            i = por.get(str(linha.data(0, Qt.ItemDataRole.UserRole)))
            if i is None:
                continue
            linha.setText(1, str(i.arquivos))
            linha.setText(2, limpeza.tamanho(i.bytes))
            if limpou:
                situacao = "limpo" if i.ok else f"não limpo: {i.motivo}"
            else:
                situacao = "pronto" if not i.codigo else i.motivo
            if i.em_uso:
                situacao += f" ({i.em_uso} em uso)"
            linha.setText(3, situacao)

    def _calculou(self, itens: list[limpeza.Item]) -> None:
        self.previa = {i.id: i for i in itens}
        self.lido = True
        self._mostrar(itens, False)
        total = sum(i.bytes for i in itens)
        self.estado.setText(f"Total: {limpeza.tamanho(total)}.")
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        ids = [i for i in self.marcados() if i in self.previa]
        total = sum(self.previa[i].bytes for i in ids)
        self.b_limpar.setText(f"Limpar {limpeza.tamanho(total)}" if ids else "Limpar")
        self.b_limpar.setEnabled(self.admin and not ocupado and bool(ids))
        if not self.admin:
            self.b_limpar.setToolTip("Precisa de administrador.")
        self.b_calcular.setEnabled(not ocupado)

    def _limpar(self) -> None:
        ids = [i for i in self.marcados() if i in self.previa]
        nomes = "\n".join(
            f"• {limpeza.NOMES[i]}: {limpeza.tamanho(self.previa[i].bytes)}" for i in ids
        )
        total = limpeza.tamanho(sum(self.previa[i].bytes for i in ids))
        if not confirmar(
            self,
            "Limpeza",
            f"Apagar {total}?\n\n{nomes}\n\nNão dá para desfazer (a lixeira inclusive).",
        ):
            return
        self._ocupar(True)
        self.estado.setText("Limpando…")
        tarefa.iniciar(lambda: limpeza.limpar(ids), self._limpou, self._falhou)

    def _limpou(self, itens: list[limpeza.Item]) -> None:
        self._mostrar(itens, True)
        apagados = sum(i.bytes for i in itens)
        ruins = [i for i in itens if not i.ok]
        self.estado.setText(
            f"Limpeza feita: {limpeza.tamanho(apagados)} examinados."
            + (f" {len(ruins)} item(ns) não limpo(s)." if ruins else "")
        )
        self.previa = {}
        self._ocupar(False)
        if ruins:
            caixa = QMessageBox(
                QMessageBox.Icon.Warning,
                "Limpeza",
                "\n".join(f"{limpeza.NOMES[i.id]}: {i.motivo}" for i in ruins),
                parent=self,
            )
            caixa.setTextFormat(Qt.TextFormat.PlainText)
            caixa.open()


# ---------------------------------------------------------------- limpeza de contas (ADR-042)

# Títulos curtos na tabela; o nome completo de cada categoria fica na dica da coluna.
_CURTOS = {
    "pessoais": "Pessoais",
    "temporarios": "Temporários",
    "navegadores": "Navegadores",
    "programas": "Programas",
}
_COLUNAS = [_CURTOS[c] for c, _ in limpeza.CATEGORIAS]
Leitura = tuple[list[contas.Conta], list[limpeza.ItemConta]]


class PainelLimpezaContas(QWidget):
    """Prévia por conta e por categoria; limpa só as contas marcadas, com duas confirmações."""

    def __init__(self, admin: bool, obter_cadastros: Callable[[], Cadastros | None]) -> None:
        super().__init__()
        self.admin = admin
        self.obter_cadastros = obter_cadastros
        self.ocupado = False
        self.por_sid: dict[str, contas.Conta] = {}
        self.previa: dict[str, list[limpeza.ItemConta]] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 8, 0, 0)
        v.addWidget(_rotulo("Limpeza de contas"))
        v.addWidget(
            _rotulo(
                "Esvazia arquivos pessoais, caches e programas só da conta, sem mexer em papel de "
                "parede, políticas, preferências nem no tipo de conta. Apaga de vez."
            )
        )
        self.estado = _rotulo("Clique em Calcular contas para ver quanto cada conta ocupa.")
        v.addWidget(self.estado)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Conta", *_COLUNAS, "Total", "Situação"])
        self.arvore.setColumnWidth(0, 200)
        cabecalho = self.arvore.headerItem()
        for n, (cid, nome) in enumerate(limpeza.CATEGORIAS, start=1):
            self.arvore.setColumnWidth(n, 110)
            cabecalho.setToolTip(n, txt.dica(f"{nome}: {limpeza.DETALHE_CATEGORIA[cid]}"))
        self.arvore.setColumnWidth(len(_COLUNAS) + 1, 90)
        self.arvore.setRootIsDecorated(False)
        self.arvore.itemChanged.connect(lambda *_: self._ocupar(self.ocupado))
        v.addWidget(self.arvore, 1)
        acoes = QHBoxLayout()
        self.b_calcular = QPushButton("Calcular contas")
        self.b_calcular.clicked.connect(self.calcular)
        self.b_limpar = QPushButton("Limpar contas")
        self.b_limpar.setObjectName("primario")
        self.b_limpar.clicked.connect(self._limpar)
        acoes.addStretch()
        acoes.addWidget(self.b_calcular)
        acoes.addWidget(self.b_limpar)
        v.addLayout(acoes)
        self._ocupar(False)

    def _protegidas(self) -> frozenset[str]:
        return contas.protegidas(self.obter_cadastros())

    def calcular(self) -> None:
        self._ocupar(True)
        self.estado.setText("Lendo as contas e calculando… (pode levar alguns minutos)")
        prot = self._protegidas()

        def rodar() -> Leitura:
            lista = [c for c in contas.listar().contas if c.perfil]
            return lista, limpeza.previa_contas(lista, prot)

        tarefa.iniciar(rodar, self._calculou, self._falhou)

    def _calculou(self, dados: Leitura) -> None:
        lista, itens = dados
        self.por_sid = {c.sid: c for c in lista}
        self.previa = {}
        for i in itens:
            self.previa.setdefault(i.sid, []).append(i)
        self._mostrar(lista, limpou=False)
        total = sum(i.bytes for i in itens if i.categoria)
        self.estado.setText(f"Total nas contas que podem ser limpas: {limpeza.tamanho(total)}.")
        self._ocupar(False)

    def _mostrar(self, lista: list[contas.Conta], *, limpou: bool) -> None:
        self.arvore.blockSignals(True)
        self.arvore.clear()
        col_total = len(_COLUNAS) + 1
        for c in lista:
            itens = self.previa.get(c.sid, [])
            recusa = next((i for i in itens if not i.categoria), None)
            por_cat = {i.categoria: i for i in itens if i.categoria}
            linha = QTreeWidgetItem([c.nome])
            linha.setData(0, Qt.ItemDataRole.UserRole, c.sid)
            for n, (cid, _) in enumerate(limpeza.CATEGORIAS, start=1):
                i = por_cat.get(cid)
                linha.setText(n, limpeza.tamanho(i.bytes) if i else "")
            total = sum(i.bytes for i in por_cat.values())
            linha.setText(col_total, limpeza.tamanho(total) if por_cat else "")
            if recusa is not None:
                situacao = recusa.motivo
            else:
                erros = [i for i in por_cat.values() if i.codigo]
                em_uso = sum(i.em_uso for i in por_cat.values())
                if erros:
                    situacao = erros[0].motivo
                else:
                    situacao = "limpa" if limpou else "pode limpar"
                    linha.setCheckState(0, Qt.CheckState.Unchecked)
                if em_uso:
                    situacao += f" ({em_uso} em uso)"
            linha.setText(col_total + 1, situacao)
            self.arvore.addTopLevelItem(linha)
        self.arvore.blockSignals(False)

    def marcadas(self) -> list[str]:
        saida = []
        for n in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(n)
            if linha is not None and linha.checkState(0) == Qt.CheckState.Checked:
                saida.append(str(linha.data(0, Qt.ItemDataRole.UserRole)))
        return saida

    def _bytes(self, sids: Iterable[str]) -> int:
        return sum(i.bytes for s in sids for i in self.previa.get(s, []) if i.categoria)

    def _ocupar(self, ocupado: bool) -> None:
        self.ocupado = ocupado
        sids = self.marcadas()
        self.b_limpar.setText(
            f"Limpar contas ({limpeza.tamanho(self._bytes(sids))})" if sids else "Limpar contas"
        )
        self.b_limpar.setEnabled(self.admin and not ocupado and bool(sids))
        if not self.admin:
            self.b_limpar.setToolTip("Precisa de administrador.")
        self.b_calcular.setEnabled(not ocupado)

    def confirmacao(self, sids: list[str]) -> tuple[str, str]:
        linhas = [f"• {self.por_sid[s].nome}: {limpeza.tamanho(self._bytes([s]))}" for s in sids]
        detalhes = "\n".join(f"• {limpeza.DETALHE_CATEGORIA[k]}" for k, _ in limpeza.CATEGORIAS)
        total = limpeza.tamanho(self._bytes(sids))
        primeira = (
            f"Apagar {total} destas contas?\n\n"
            + "\n".join(linhas)
            + f"\n\nO que é apagado:\n{detalhes}\n\n"
            "Ficam: papel de parede, políticas, preferências, tipo de conta, favoritos e senhas."
        )
        segunda = (
            f"Confirma de novo: os arquivos de {len(sids)} conta(s) serão apagados de vez, sem "
            "lixeira. Não dá para desfazer."
        )
        return primeira, segunda

    def _limpar(self) -> None:
        sids = [s for s in self.marcadas() if s in self.por_sid]
        if not sids:
            return
        primeira, segunda = self.confirmacao(sids)
        if not confirmar(self, "Limpeza de contas", primeira):
            return
        if not confirmar(self, "Limpeza de contas — última confirmação", segunda):
            return
        alvo = [self.por_sid[s] for s in sids]
        prot = self._protegidas()
        lista = list(self.por_sid.values())
        self._ocupar(True)
        self.estado.setText("Limpando as contas…")

        def rodar() -> Leitura:
            return lista, limpeza.limpar_contas(alvo, prot)

        tarefa.iniciar(rodar, self._limpou, self._falhou)

    def _limpou(self, dados: Leitura) -> None:
        lista, itens = dados
        feitos = {i.sid for i in itens}
        for s in feitos:
            self.previa[s] = [i for i in itens if i.sid == s]
        self._mostrar([c for c in lista if c.sid in feitos], limpou=True)
        apagado = sum(i.bytes for i in itens if i.categoria)
        avisos = [i for i in itens if i.codigo]
        self.estado.setText(
            f"Limpeza de contas feita: {limpeza.tamanho(apagado)} examinados."
            + (f" {len(avisos)} item(ns) com aviso." if avisos else "")
            + " Clique em Calcular contas para ver o que sobrou."
        )
        self._ocupar(False)

    def _falhou(self, motivo: str) -> None:
        self.estado.setText(f"Falhou: {motivo}")
        self._ocupar(False)
