"""Tela Importar configurações (ADR-076): salva as marcações das telas num arquivo e carrega o de
outra máquina. Regras e formato em `servicos/modelo.py`; aqui só tela."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from itc_bench.nucleo.log import log
from itc_bench.servicos import modelo
from itc_bench.ui.contas import _rotulo, confirmar

AJUDA = (
    "Leva as marcações de uma máquina para outras da mesma unidade ou do mesmo projeto: prepare "
    "uma, salve o modelo e carregue nas outras.\n\n"
    "O que vai no modelo\n"
    "• Configuração: o perfil e as etapas desmarcadas.\n"
    "• Identificação: os turnos marcados, o sufixo e Criar também o usuário do sufixo.\n"
    "• Wi-Fi: as redes marcadas.\n"
    "• Programas: o perfil escolhido, os marcados para instalar e os já instalados nesta "
    "sessão.\n"
    "• Remover programas: os marcados e os que já foram removidos nesta sessão.\n"
    "• Políticas: as marcadas.\n"
    "• Inicialização: os itens sem função que você desmarcou (ficam ligados).\n"
    "Nunca vão: senhas, nome do computador, contas, nem a unidade da máquina.\n\n"
    "Como usar\n"
    "1. Na primeira máquina, marque tudo nas telas e clique em Salvar modelo….\n"
    "2. Na outra máquina, clique em Importar modelo… e escolha o arquivo (.itcbench). Com Usar "
    "sempre nesta máquina marcado (vem marcado), o Bench guarda uma cópia na pasta indicada e "
    "carrega o modelo sozinho toda vez que abre; desmarcado, vale só até fechar o Bench. Pôr o "
    "arquivo na pasta à mão faz o mesmo (vale o mais novo, se houver mais de um). Parar de usar "
    "tira os modelos da pasta; o arquivo original não é mexido.\n"
    "3. As telas ficam marcadas como no modelo. Confira e rode cada uma como sempre: importar "
    "não aplica nada sozinho.\n\n"
    "Perfil, rede, política ou programa que não existe nesta máquina é ignorado; o resumo diz o "
    "que não deu para marcar."
)


class PainelModelo(QWidget):
    def __init__(
        self,
        coletar: Callable[[], modelo.Modelo],
        aplicar: Callable[[modelo.Modelo], list[str]],
    ) -> None:
        super().__init__()
        self.coletar = coletar
        self.aplicar = aplicar
        self.atual: modelo.Modelo | None = None
        v = QVBoxLayout(self)
        v.addWidget(
            _rotulo(
                "Salve as marcações desta máquina (Configuração, Identificação, Wi-Fi, Programas, "
                "Remover programas, Políticas e Inicialização) e carregue em outras da mesma "
                "unidade ou projeto. Senhas e o nome do computador nunca vão no arquivo."
            )
        )
        acoes = QHBoxLayout()
        self.b_salvar = QPushButton("Salvar modelo…")
        self.b_salvar.clicked.connect(self._salvar)
        self.b_importar = QPushButton("Importar modelo…")
        self.b_importar.setObjectName("primario")
        self.b_importar.clicked.connect(self._importar)
        self.b_parar = QPushButton("Parar de usar nesta máquina")
        self.b_parar.clicked.connect(self._parar)
        acoes.addWidget(self.b_salvar)
        acoes.addWidget(self.b_importar)
        acoes.addStretch()
        acoes.addWidget(self.b_parar)
        v.addLayout(acoes)
        self.usar_sempre = QCheckBox("Usar sempre nesta máquina (carrega ao abrir o Bench)")
        self.usar_sempre.setChecked(True)
        v.addWidget(self.usar_sempre)
        self.pasta = _rotulo(f"Pasta indicada (carregada ao abrir o Bench): {modelo.pasta()}")
        v.addWidget(self.pasta)
        self.estado = _rotulo("Nenhum modelo carregado.")
        v.addWidget(self.estado)
        self.detalhe = _rotulo("")
        v.addWidget(self.detalhe)
        v.addStretch()
        self._ver_pasta()

    def _ver_pasta(self) -> None:
        arquivos = modelo.na_pasta()
        self.b_parar.setEnabled(bool(arquivos))
        ativo = f" Em uso: {arquivos[0].name}." if arquivos else " Nenhum modelo nela."
        self.pasta.setText(f"Pasta indicada (carregada ao abrir o Bench): {modelo.pasta()}.{ativo}")

    def _salvar(self) -> None:
        m = self.coletar()
        if not m.resumo():
            self.estado.setText("Nada marcado nas telas para salvar.")
            return
        nome = f"modelo-{m.unidade or 'bench'}{modelo.EXTENSAO}"
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar modelo", nome, f"Modelo do ITC Bench (*{modelo.EXTENSAO})"
        )
        if not caminho:
            return
        try:
            salvo = modelo.salvar(m, Path(caminho))
        except OSError as erro:
            log.error("Modelo: salvar falhou (%s)", type(erro).__name__)
            self.estado.setText(f"Não deu para salvar ({type(erro).__name__}).")
            return
        self.estado.setText(f"Modelo salvo em {salvo}.")
        self.detalhe.setText("\n".join(m.resumo()))

    def _importar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar modelo", "", f"Modelo do ITC Bench (*{modelo.EXTENSAO})"
        )
        if not caminho or not self.carregar(Path(caminho)):
            return
        if not self.usar_sempre.isChecked():
            return
        try:
            modelo.usar_sempre(Path(caminho))
        except OSError as erro:
            log.error("Modelo: cópia para a pasta falhou (%s)", type(erro).__name__)
            self.estado.setText(
                self.estado.text()
                + f" Não deu para guardar na pasta ({type(erro).__name__}): vale só até fechar."
            )
        else:
            self.estado.setText(self.estado.text() + " Vai carregar sozinho ao abrir o Bench.")
        self._ver_pasta()

    def _parar(self) -> None:
        if not confirmar(
            self,
            "Importar configurações",
            "Tirar os modelos da pasta indicada? O Bench deixa de carregá-los ao abrir. As telas "
            "continuam marcadas até fechar, e o arquivo original não é mexido.",
        ):
            return
        try:
            saiu = modelo.parar_de_usar()
        except OSError as erro:
            self.estado.setText(f"Não deu para tirar da pasta ({type(erro).__name__}).")
        else:
            self.estado.setText(f"{saiu} modelo(s) tirado(s) da pasta: não carrega mais ao abrir.")
        self._ver_pasta()

    def carregar(self, caminho: Path, m: modelo.Modelo | None = None) -> bool:
        try:
            m = m or modelo.ler(caminho)
        except ValueError as erro:
            self.estado.setText(f"Modelo recusado: {erro}.")
            return False
        self.atual = m
        avisos = self.aplicar(m)
        origem = f" (unidade {m.unidade})" if m.unidade else ""
        self.estado.setText(
            f"Modelo carregado de {caminho.name}{origem}. Confira as telas e rode cada uma."
        )
        linhas = m.resumo() or ["O modelo não tem marcações."]
        self.detalhe.setText("\n".join(linhas + [f"Atenção: {a}" for a in avisos]))
        return True
