"""Laudo hostil renderizado como texto (ADR-015)."""

from PySide6.QtGui import QTextFormat

from itc_bench.ui.laudo import VisorLaudo, documento

HOSTIL = """## Resumo <b>forte</b>
<img src=x onerror=alert(1)>
- [clique](javascript:alert(1))
- ![segredo](file:///C:/Windows/win.ini)
1. <a href="https://exemplo.invalid">link</a>
**negrito** e <script>x()</script>
"""


def _formatos(doc):
    bloco = doc.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            yield it.fragment().charFormat(), it.fragment().text()
            it += 1
        bloco = bloco.next()


def test_html_link_e_imagem_viram_texto(qtbot):
    doc = documento(HOSTIL)
    texto = doc.toPlainText()
    for literal in (
        "<img src=x onerror=alert(1)>",
        "[clique](javascript:alert(1))",
        '<a href="https://exemplo.invalid">link</a>',
        "<script>x()</script>",
        "<b>forte</b>",
    ):
        assert literal in texto
    assert "segredo" in texto and "win.ini" not in texto  # imagem vira só o alt
    for formato, _ in _formatos(doc):
        assert not formato.isAnchor()
        assert not formato.isImageFormat()
        assert formato.objectType() != QTextFormat.ObjectTypes.ImageObject
    assert "<img" not in doc.toHtml().replace("&lt;img", "")


def test_titulos_listas_e_negrito(qtbot):
    doc = documento("# T\n\n- a\n- b\n\n1. um\n\ntexto **forte** fim")
    assert doc.toPlainText().split("\n") == ["T", "a", "b", "um", "texto forte fim"]
    fortes = [t for f, t in _formatos(doc) if f.fontWeight() >= 700]
    assert fortes == ["T", "forte"]
    assert doc.findBlockByNumber(1).textList() is not None


def test_visor_nao_abre_link_nem_carrega_recurso(qtbot):
    v = VisorLaudo()
    qtbot.addWidget(v)
    v.mostrar(HOSTIL)
    assert not v.openLinks() and not v.openExternalLinks()
    assert v.loadResource(2, "file:///C:/Windows/win.ini") is None
    assert "<img src=x" in v.toPlainText()
