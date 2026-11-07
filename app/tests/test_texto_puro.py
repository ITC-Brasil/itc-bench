"""Dado de fora nunca vira rich text no Qt (Módulo 14).

`QMessageBox.warning()`/`critical()`/... e `setToolTip()` usam rich text automático. Toda caixa
estática passa por `ui/texto.aviso` (texto puro) e toda dica não constante por `ui/texto.dica`.
"""

import ast
from pathlib import Path

import itc_bench
from itc_bench.ui import texto as txt

RAIZ = Path(itc_bench.__file__).parent
ESTATICAS = {"warning", "information", "critical", "question", "about"}


def _permitida(no: ast.expr) -> bool:
    if isinstance(no, ast.Constant):
        return True
    if isinstance(no, ast.IfExp):
        return _permitida(no.body) and _permitida(no.orelse)
    return (
        isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "dica"
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id == "txt"
    )


def test_sem_caixa_estatica_nem_dica_crua():
    erros = []
    for arquivo in sorted(RAIZ.rglob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
                continue
            onde = f"{arquivo.relative_to(RAIZ)}:{no.lineno}"
            f = no.func
            if (
                f.attr in ESTATICAS
                and isinstance(f.value, ast.Name)
                and f.value.id == "QMessageBox"
            ):
                erros.append(f"{onde} QMessageBox.{f.attr}")
            if f.attr == "setToolTip" and no.args and not _permitida(no.args[-1]):
                erros.append(f"{onde} setToolTip")
            if f.attr in {"setHtml", "setMarkdown"}:
                erros.append(f"{onde} {f.attr}")
    assert not erros


def test_dica_escapa_marcacao():
    assert txt.dica('<img src="x">a & b') == "<p>&lt;img src=&quot;x&quot;&gt;a &amp; b</p>"
    assert txt.dica("") == ""
