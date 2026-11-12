"""Modo claro/escuro (ADR-037): preferência do usuário, paletas e troca com o app aberto."""

import re

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from itc_bench.servicos import preferencias
from itc_bench.ui import tema
from itc_bench.ui.configuracoes import PainelConfiguracoes
from itc_bench.ui.preparacao import COR


@pytest.fixture(autouse=True)
def _volta_ao_claro(qapp):
    yield
    tema.trocar(qapp, "claro")


def test_sem_arquivo_e_claro(tmp_path):
    assert preferencias.modo(tmp_path) == "claro"


def test_grava_e_le(tmp_path):
    preferencias.gravar_modo("escuro", tmp_path)
    assert preferencias.modo(tmp_path) == "escuro"
    assert not (tmp_path / "preferencias.tmp").exists()


@pytest.mark.parametrize("conteudo", ["{quebrado", "[1, 2]", '{"modo": "roxo"}', '{"modo": 1}'])
def test_arquivo_ruim_vira_claro(tmp_path, conteudo):
    (tmp_path / preferencias.ARQUIVO).write_text(conteudo, encoding="utf-8")
    assert preferencias.modo(tmp_path) == "claro"


def test_recusa_modo_desconhecido(tmp_path):
    with pytest.raises(ValueError):
        preferencias.gravar_modo("roxo", tmp_path)
    assert not (tmp_path / preferencias.ARQUIVO).exists()


def test_claro_mantem_os_valores_do_design():
    c = tema.CLARO
    assert (c.fundo, c.superficie, c.linha, c.trilha) == (
        "#F4F6F6",
        "#FFFFFF",
        "#D8DEDE",
        "#697272",
    )
    assert (c.ok, c.warn, c.err, c.info) == (tema.OK, tema.WARN, tema.ERR, tema.INFO)
    assert c.texto == tema.INK and c.selecao == tema.CY50


def test_barra_lateral_igual_nos_dois_modos():
    """Só a área principal muda; barra, marca e botão primário ficam como estão."""
    fixo = re.compile(r"^#(lateral|marca\w+|secao|nav\S*|rodape|entrarLado|entrar(Itc|Bench)) .*$")
    claro = [linha for linha in tema.qss(tema.CLARO).splitlines() if fixo.match(linha)]
    escuro = [linha for linha in tema.qss(tema.ESCURO).splitlines() if fixo.match(linha)]
    assert claro and claro == escuro
    for qss in (tema.qss(tema.CLARO), tema.qss(tema.ESCURO)):
        assert f"background: {tema.CY9}; color: #FFFFFF" in qss


def _luminancia(cor: str) -> float:
    canais = [int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("paleta", [tema.CLARO, tema.ESCURO], ids=lambda p: p.nome)
def test_contraste_do_texto(paleta):
    """WCAG AA: 4,5 para texto; 3 para estados e texto secundário pequeno em negrito."""
    assert _contraste(paleta.texto, paleta.superficie) >= 4.5
    assert _contraste(paleta.texto, paleta.fundo) >= 4.5
    assert _contraste(paleta.mute, paleta.superficie) >= 4.5
    assert _contraste(paleta.selecao_texto, paleta.selecao) >= 4.5
    assert _contraste(paleta.log_texto, paleta.log_fundo) >= 4.5
    for cor in (paleta.trilha, paleta.ok, paleta.warn, paleta.err, paleta.info, paleta.destaque):
        assert _contraste(cor, paleta.superficie) >= 3, cor


def test_trocar_muda_paleta_e_folha(qapp):
    tema.trocar(qapp, "escuro")
    assert tema.atual() is tema.ESCURO
    assert qapp.palette().color(QPalette.ColorRole.Base).name().upper() == "#1A2020"
    assert "#1A2020" in qapp.styleSheet()
    assert tema.cor_situacao("erro") == tema.ESCURO.err
    tema.trocar(qapp, "outro")
    assert tema.atual() is tema.CLARO


def test_situacoes_da_preparacao_seguem_o_tema(qapp):
    for modo, paleta in (("claro", tema.CLARO), ("escuro", tema.ESCURO)):
        tema.trocar(qapp, modo)
        assert tema.cor_situacao(COR["feito"]) == paleta.ok
        assert tema.cor_situacao(COR["falhou"]) == paleta.err
        assert tema.cor_situacao(COR["nao_iniciado"]) == paleta.idle


def test_configuracoes_emite_o_modo(qapp):
    tema.aplicar(QApplication.instance(), "escuro")
    painel = PainelConfiguracoes()
    painel.mostrar(None, "sem cópia", [], None, False)
    assert painel.modo.currentData() == "escuro"
    recebidos: list[str] = []
    painel.modo_escolhido.connect(recebidos.append)
    painel.modo.activated.emit(painel.modo.findData("claro"))
    assert recebidos == ["claro"]


def test_preferencia_ilegivel_nao_loga_caminho(tmp_path, caplog):
    """O caminho de %LOCALAPPDATA% tem a pasta do perfil: não vai para o log (ADR-023)."""
    (tmp_path / preferencias.ARQUIVO).write_text("{quebrado", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert preferencias.modo(tmp_path) == "claro"
    assert "ilegíveis" in caplog.text and str(tmp_path) not in caplog.text
