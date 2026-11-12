"""Tokens de `docs/UI-UX-BRIEF.md`, fontes embutidas, ícones e folha de estilo.

Dois modos (ADR-037): claro, o do design, e escuro, com as superfícies escuras que o design já
usa. A barra lateral e o lado da marca na tela de entrar são escuros nos dois.
"""

from dataclasses import dataclass
from importlib import resources

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

RECURSOS = resources.files("itc_bench.recursos")

CY = "#008F95"
CY5 = "#30A5AB"
CY9 = "#006C72"
CY12 = "#003C3F"
CY50 = "#E0F4F5"
INK = "#1B1B1B"
MUTE = "#5F594E"
FAINT = "#8A8378"
PAGE = "#E9E5DD"
CARD = "#FDFBF7"
WELL = "#F5F0E8"
LINE = "#D8D2C6"
LINE2 = "#EDE8DE"
OK = "#1A7F3C"
WARN = "#CC7A00"
ERR = "#C0392B"
INFO = "#1565C0"

# Barra lateral e área principal (valores do HTML de design, fora da tabela de tokens).
SIDE_TEXTO = "#D0D0D0"
SIDE_ICONE = "#8E8E8E"
SIDE_SECAO = "#797979"
SIDE_ATIVO = "#2C2C2C"
MAIN_FUNDO = "#F4F6F6"
MAIN_LINHA = "#D8DEDE"
MAIN_TRILHA = "#697272"

DISPLAY = "Archivo"
CORPO = "Inter"

MODOS = ("claro", "escuro")


@dataclass(frozen=True)
class Paleta:
    """Cores da área principal, por modo."""

    nome: str
    fundo: str  # área principal
    superficie: str  # topo, painéis, campos, tabelas
    alternada: str  # linha alternada, cabeçalho de tabela, controle desativado
    linha: str
    linha2: str
    texto: str
    mute: str
    trilha: str
    borda_controle: str  # "?", caixas de marcar, primário desativado
    destaque: str  # texto e foco em ciano
    selecao: str  # fundo de item selecionado
    selecao_texto: str
    log_fundo: str
    log_texto: str
    ok: str
    warn: str
    err: str
    info: str
    idle: str


# Valores do HTML de design (`docs/design/`): .main, .top, .pn, .btn, .inp, .tab, .chk, .pill.
CLARO = Paleta(
    nome="claro",
    fundo=MAIN_FUNDO,
    superficie="#FFFFFF",
    alternada="#FAFBFB",
    linha=MAIN_LINHA,
    linha2="#EEF1F1",
    texto=INK,
    mute=MUTE,
    trilha=MAIN_TRILHA,
    borda_controle="#A5B0B0",
    destaque=CY9,
    selecao=CY50,
    selecao_texto=CY12,
    log_fundo=WELL,
    log_texto=INK,
    ok=OK,
    warn=WARN,
    err=ERR,
    info=INFO,
    idle=FAINT,
)

# Escuro (ADR-037): superfícies escuras do design (`.log` #1A2020, barra #1B1B1B/#2C2C2C), ciano
# sobre escuro (`--cy5`) e estados clareados como no log do design (#7BC896, #E3A64A).
ESCURO = Paleta(
    nome="escuro",
    fundo="#141818",
    superficie="#1A2020",
    alternada="#1F2626",
    linha="#2C3434",
    linha2="#242B2B",
    texto="#E6EAEA",
    mute="#B0A99C",
    trilha="#8E9898",
    borda_controle="#5A6464",
    destaque=CY5,
    selecao=CY12,
    selecao_texto=CY50,
    log_fundo="#121616",
    log_texto="#D8DEDE",
    ok="#7BC896",
    warn="#E3A64A",
    err="#E57368",
    info="#6FA8E8",
    idle="#8E9898",
)

PALETAS = {p.nome: p for p in (CLARO, ESCURO)}
_estado = {"paleta": CLARO}


def atual() -> Paleta:
    return _estado["paleta"]


def cor_situacao(tipo: str) -> str:
    """Cor de "ok", "aviso", "erro" ou "info" na paleta em uso; outro valor é neutro."""
    p = atual()
    return {"ok": p.ok, "aviso": p.warn, "erro": p.err, "info": p.info}.get(tipo, p.idle)


def carregar_fontes() -> list[str]:
    """Registra os TTF embutidos; devolve as famílias carregadas."""
    familias: set[str] = set()
    for pasta in ("archivo", "inter"):
        for arq in RECURSOS.joinpath("fontes", pasta).iterdir():
            if arq.name.endswith(".ttf"):
                ident = QFontDatabase.addApplicationFontFromData(QByteArray(arq.read_bytes()))
                if ident < 0:
                    raise RuntimeError(f"Fonte inválida: {arq.name}")
                familias.update(QFontDatabase.applicationFontFamilies(ident))
    return sorted(familias)


def aplicar(app: QApplication, modo: str = "claro") -> None:
    """Primeira aplicação: fontes, estilo Fusion, paleta e folha de estilo."""
    carregar_fontes()
    app.setStyle("Fusion")
    trocar(app, modo)


def trocar(app: QApplication, modo: str) -> None:
    """Troca o modo com o app aberto. Modo desconhecido vira claro."""
    p = PALETAS.get(modo, CLARO)
    _estado["paleta"] = p
    app.setPalette(paleta_qt(p))
    app.setStyleSheet(qss(p))


def paleta_qt(p: Paleta) -> QPalette:
    """Paleta do Qt: o que a folha de estilo não cobre (diálogos, menus, dicas, setas)."""
    pal = QPalette()
    r = QPalette.ColorRole
    for papel, cor in (
        (r.Window, p.fundo),
        (r.WindowText, p.texto),
        (r.Base, p.superficie),
        (r.AlternateBase, p.alternada),
        (r.Text, p.texto),
        (r.Button, p.superficie),
        (r.ButtonText, p.texto),
        (r.BrightText, "#FFFFFF"),
        (r.ToolTipBase, p.superficie),
        (r.ToolTipText, p.texto),
        (r.PlaceholderText, p.trilha),
        (r.Highlight, CY9),
        (r.HighlightedText, "#FFFFFF"),
        (r.Link, p.destaque),
        (r.Light, p.linha2),
        (r.Midlight, p.linha),
        (r.Mid, p.linha),
        (r.Dark, p.borda_controle),
        (r.Shadow, "#000000"),
    ):
        pal.setColor(papel, QColor(cor))
    for papel in (r.WindowText, r.Text, r.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, papel, QColor(p.trilha))
    return pal


def svg(caminho: str, cor: str | None = None) -> bytes:
    dados = RECURSOS.joinpath(*caminho.split("/")).read_bytes()
    return dados.replace(b"currentColor", cor.encode()) if cor else dados


def pixmap(dados: bytes, tamanho: int) -> QPixmap:
    app = QApplication.instance()
    escala = app.devicePixelRatio() if isinstance(app, QApplication) else 1.0
    px = QPixmap(QSize(tamanho, tamanho) * escala)
    px.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(px)
    QSvgRenderer(QByteArray(dados)).render(pintor)
    pintor.end()
    px.setDevicePixelRatio(escala)
    return px


def icone(nome: str, cor: str, tamanho: int = 16) -> QIcon:
    return QIcon(pixmap(svg(f"icones/{nome}.svg", cor), tamanho))


def simbolo(variante: str = "escuro", tamanho: int = 28) -> QPixmap:
    arquivo = (
        "itc-bench-simbolo.svg" if variante == "principal" else f"itc-bench-simbolo-{variante}.svg"
    )
    return pixmap(svg(f"simbolo/{arquivo}"), tamanho)


def icone_nav(nome: str) -> QIcon:
    """Ícone da barra: cinza normal, ciano quando selecionado, como no design."""
    ic = QIcon()
    for cor, estado in ((SIDE_ICONE, QIcon.State.Off), (CY5, QIcon.State.On)):
        ic.addPixmap(pixmap(svg(f"icones/{nome}.svg", cor), 16), QIcon.Mode.Normal, estado)
    return ic


def icone_janela() -> QIcon:
    ic = QIcon()
    for t in (16, 24, 32, 48, 256):
        ic.addPixmap(simbolo("16" if t <= 24 else "principal", t))
    return ic


def _arquivo(nome: str) -> str:
    """Caminho de um ícone fixo (✓, ponto, seta) para `url()`: a folha de estilo só lê arquivo."""
    return str(RECURSOS.joinpath("icones", f"{nome}.svg")).replace("\\", "/")


def qss(p: Paleta) -> str:
    return f"""
* {{ font-family: "{CORPO}"; }}
#lateral {{ background: {INK}; }}
#marcaItc {{ font: 600 8px "{DISPLAY}"; letter-spacing: 3px; color: {CY5}; }}
#marcaBench {{ font: 800 18px "{DISPLAY}"; color: #FFFFFF; }}
#secao {{ font: 600 9.5px "{CORPO}"; letter-spacing: 1.5px; color: {SIDE_SECAO};
          padding: 14px 10px 6px 10px; }}
#nav {{ text-align: left; padding: 7px 10px; border: none; border-radius: 6px;
        font: 500 12.5px "{CORPO}"; color: {SIDE_TEXTO}; background: transparent; }}
#nav:hover {{ background: #242424; }}
#nav:checked {{ background: {SIDE_ATIVO}; color: #FFFFFF; border-left: 2px solid {CY5}; }}
#rodape {{ font: 400 10.5px "{CORPO}"; color: {SIDE_ICONE}; border-top: 1px solid {SIDE_ATIVO};
           padding: 12px 10px 0 10px; }}
#principal {{ background: {p.fundo}; }}
#topo {{ background: {p.superficie}; border-bottom: 1px solid {p.linha}; }}
#trilha {{ font: 500 11px "{CORPO}"; color: {p.trilha}; }}
#titulo {{ font: 800 20px "{DISPLAY}"; color: {p.texto}; }}
#ajudaBotao {{ border: 1.5px solid {p.borda_controle}; border-radius: 10px; color: {p.trilha};
               font: 700 11px "{CORPO}"; background: transparent; padding: 0; }}
#ajudaBotao:hover {{ border-color: {p.destaque}; color: {p.destaque}; }}
#ajudaBotao:checked {{ background: {CY9}; border-color: {CY9}; color: #FFFFFF; }}
#ajudaTitulo {{ font: 700 14px "{DISPLAY}"; color: {p.texto}; }}
#ajudaConteudo {{ background: transparent; }}
#ajudaNome {{ font: 800 18px "{DISPLAY}"; color: {p.texto}; }}
#ajudaTexto {{ font: 400 12.5px "{CORPO}"; color: {p.texto}; }}
#ajudaAbertura {{ background: {p.selecao}; border-radius: 8px; }}
#ajudaAbertura #ajudaTexto {{ color: {p.selecao_texto}; }}
#cartao QLabel#ajudaPasso {{ font: 700 10.5px "{CORPO}"; color: #FFFFFF; background: {CY9};
                             border-radius: 10px; }}
#cartao QLabel#ajudaTopico {{ font: 700 14px "{CORPO}"; color: {p.destaque}; }}
QTreeView#ajudaIndice {{ font: 500 12.5px "{CORPO}"; }}
QTreeView#ajudaIndice::item {{ padding: 5px 4px; }}
#ajudaFechar {{ border: none; background: transparent; color: {p.trilha}; padding: 0; }}
#painel, #cartao, #faixa {{ background: {p.superficie}; border: 1px solid {p.linha};
                            border-radius: 8px; }}
#cartao QLabel, #faixa QLabel {{ background: transparent; border: none; }}
#cartaoTitulo, #subtitulo {{ font: 700 13px "{DISPLAY}"; color: {p.texto}; }}
#vazio {{ font: 400 13px "{CORPO}"; color: {p.mute}; }}
#dica {{ font: 400 11.5px "{CORPO}"; color: {p.trilha}; }}
#modulo {{ font: 600 11px "{CORPO}"; color: {p.selecao_texto}; background: {p.selecao};
           border-radius: 4px; padding: 4px 8px; }}
#entrarLado {{ background: {INK}; }}
#entrarItc {{ font: 600 11px "{DISPLAY}"; letter-spacing: 4px; color: {CY5}; }}
#entrarBench {{ font: 800 36px "{DISPLAY}"; color: #FFFFFF; }}
#entrarRodape {{ font: 400 12px "{CORPO}"; color: {SIDE_ICONE}; }}
#entrarTitulo {{ font: 800 24px "{DISPLAY}"; color: {p.texto}; }}
#entrarSub {{ font: 400 12.5px "{CORPO}"; color: {p.trilha}; }}
#rotulo {{ font: 600 11px "{CORPO}"; color: {p.trilha}; }}
#entrarErro {{ font: 500 12px "{CORPO}"; color: {p.err}; }}
#entrarEstado {{ font: 500 11.5px "{CORPO}"; color: {p.trilha}; }}
#entrarEstado[tipo="ok"] {{ color: {p.ok}; }}
#entrarEstado[tipo="aviso"] {{ color: {p.warn}; }}
#entrarEstado[tipo="erro"] {{ color: {p.err}; }}
#entrarNota {{ font: 400 11px "{CORPO}"; color: {p.trilha}; }}

QToolTip {{ background: {p.superficie}; color: {p.texto}; border: 1px solid {p.linha};
            padding: 4px 6px; }}

QPushButton {{ font: 600 12px "{CORPO}"; padding: 7px 14px; border-radius: 6px;
               border: 1px solid {p.linha}; background: {p.superficie}; color: {p.texto}; }}
QPushButton:hover, QPushButton:focus {{ border-color: {p.borda_controle}; }}
QPushButton:pressed, QPushButton:checked {{ background: {p.selecao};
                                            color: {p.selecao_texto}; border-color: {CY}; }}
QPushButton:disabled {{ color: {p.borda_controle}; font-weight: 500; background: {p.alternada};
                        border-color: {p.linha2}; }}
#primario {{ font: 600 13px "{CORPO}"; padding: 9px 14px; border: 1px solid {CY9};
             background: {CY9}; color: #FFFFFF; }}
#primario:hover {{ background: {CY}; border-color: {CY}; }}
#primario:disabled {{ background: {p.borda_controle}; border-color: {p.borda_controle};
                      color: #FFFFFF; }}
#perigo {{ color: {p.err}; }}
#perigo:hover {{ border-color: {p.err}; }}
#perigo:disabled {{ color: {p.borda_controle}; border-color: {p.linha2}; }}
#link {{ border: none; background: transparent; padding: 0; color: {p.destaque};
         text-decoration: underline; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
    border: 1px solid {p.linha}; border-radius: 6px; background: {p.superficie};
    color: {p.texto}; selection-background-color: {CY9}; selection-color: #FFFFFF; }}
QLineEdit, QComboBox, QSpinBox {{ padding: 6px 9px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {CY}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {p.trilha}; background: {p.alternada}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{_arquivo("seta")}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {p.superficie}; color: {p.texto};
    border: 1px solid {p.linha}; selection-background-color: {p.selecao};
    selection-color: {p.selecao_texto}; outline: 0; }}
#campo {{ font: 400 13px "{CORPO}"; padding: 8px 10px; }}
#log {{ font: 11px "Consolas"; color: {p.log_texto}; background: {p.log_fundo}; border: none; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTreeView::indicator, QListView::indicator, QTableView::indicator {{
    width: 14px; height: 14px; border-radius: 4px; border: 1.5px solid {p.borda_controle};
    background: {p.superficie}; }}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked,
QTableView::indicator:checked {{ background: {CY9}; border-color: {CY9};
    image: url("{_arquivo("marcado")}"); }}
QCheckBox::indicator:disabled, QTreeView::indicator:disabled, QListView::indicator:disabled {{
    border-color: {p.linha}; background: {p.alternada}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px;
    border: 1.5px solid {p.borda_controle}; background: {p.superficie}; }}
QRadioButton::indicator:checked {{ background: {CY9}; border-color: {CY9};
    image: url("{_arquivo("ponto")}"); }}

QTableView, QTreeView, QListView {{ background: {p.superficie};
    alternate-background-color: {p.alternada}; color: {p.texto}; border: 1px solid {p.linha};
    border-radius: 8px; gridline-color: {p.linha2}; outline: 0; }}
QTableView::item, QTreeView::item, QListView::item {{ padding: 4px 6px; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {p.selecao}; color: {p.selecao_texto}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {p.alternada}; color: {p.trilha}; border: none;
    border-bottom: 1px solid {p.linha}; padding: 7px 8px; font: 600 11px "{CORPO}"; }}
QTableCornerButton::section {{ background: {p.alternada}; border: none; }}

QTabWidget::pane {{ border: 1px solid {p.linha}; border-radius: 8px;
                    background: {p.superficie}; top: -1px; }}
QTabBar::tab {{ font: 600 12px "{CORPO}"; padding: 10px 12px; color: {p.trilha};
                background: transparent; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.texto}; border-bottom-color: {CY}; }}
QTabBar::tab:hover {{ color: {p.texto}; }}

QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle {{ background: {p.linha}; border-radius: 3px; min-height: 24px;
                      min-width: 24px; }}
QScrollBar::handle:hover {{ background: {p.borda_controle}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {p.superficie}; color: {p.texto}; border: 1px solid {p.linha}; }}
QMenu::item:selected {{ background: {p.selecao}; color: {p.selecao_texto}; }}
"""


QSS = qss(CLARO)
