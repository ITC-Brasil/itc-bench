"""Tokens de `docs/UI-UX-BRIEF.md`, fontes embutidas, ícones e folha de estilo."""

from importlib import resources

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QFontDatabase, QIcon, QPainter, QPixmap
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


def aplicar(app: QApplication) -> None:
    carregar_fontes()
    app.setStyleSheet(QSS)


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


QSS = f"""
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
#principal {{ background: {MAIN_FUNDO}; }}
#topo {{ background: #FFFFFF; border-bottom: 1px solid {MAIN_LINHA}; }}
#trilha {{ font: 500 11px "{CORPO}"; color: {MAIN_TRILHA}; }}
#titulo {{ font: 800 20px "{DISPLAY}"; color: {INK}; }}
#ajudaBotao {{ border: 1.5px solid #A5B0B0; border-radius: 10px; color: {MAIN_TRILHA};
               font: 700 11px "{CORPO}"; background: transparent; }}
#ajudaBotao:checked {{ background: {CY9}; border-color: {CY9}; color: #FFFFFF; }}
#ajudaTitulo {{ font: 700 14px "{DISPLAY}"; color: {INK}; }}
#ajudaFechar {{ border: none; background: transparent; color: {MAIN_TRILHA}; }}
#painel {{ background: #FFFFFF; border: 1px solid {MAIN_LINHA}; border-radius: 8px; }}
#vazio {{ font: 400 13px "{CORPO}"; color: {MUTE}; }}
#modulo {{ font: 600 11px "{CORPO}"; color: {CY9}; background: {CY50}; border-radius: 4px;
           padding: 4px 8px; }}
#log {{ font: 11px "Consolas"; color: {INK}; background: {WELL}; border: none; }}
"""
