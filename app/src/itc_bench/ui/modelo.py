"""Tela Importar configurações (ADR-076): salva as marcações das telas num arquivo e carrega o de
outra máquina. Regras e formato em `servicos/modelo.py`; aqui só tela."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from itc_bench.nucleo.log import log
from itc_bench.servicos import modelo
from itc_bench.ui.contas import _rotulo

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
    "2. Na outra máquina, clique em Importar modelo… e escolha o arquivo (.itcbench). Ou ponha o "
    "arquivo na pasta indicada abaixo: ele é carregado sozinho toda vez que o Bench abre (o mais "
    "novo, se houver mais de um).\n"
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
        acoes.addWidget(self.b_salvar)
        acoes.addWidget(self.b_importar)
        acoes.addStretch()
        v.addLayout(acoes)
        self.pasta = _rotulo(f"Pasta indicada (carregada ao abrir o Bench): {modelo.pasta()}")
        v.addWidget(self.pasta)
        self.estado = _rotulo("Nenhum modelo carregado.")
        v.addWidget(self.estado)
        self.detalhe = _rotulo("")
        v.addWidget(self.detalhe)
        v.addStretch()

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
        if caminho:
            self.carregar(Path(caminho))

    def carregar(self, caminho: Path, m: modelo.Modelo | None = None) -> None:
        try:
            m = m or modelo.ler(caminho)
        except ValueError as erro:
            self.estado.setText(f"Modelo recusado: {erro}.")
            return
        self.atual = m
        avisos = self.aplicar(m)
        origem = f" (unidade {m.unidade})" if m.unidade else ""
        self.estado.setText(
            f"Modelo carregado de {caminho.name}{origem}. Confira as telas e rode cada uma."
        )
        linhas = m.resumo() or ["O modelo não tem marcações."]
        self.detalhe.setText("\n".join(linhas + [f"Atenção: {a}" for a in avisos]))
