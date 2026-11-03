from itc_bench.ui import tema

ICONES = [
    "inicio",
    "prep",
    "id",
    "contas",
    "wifi",
    "remoto",
    "prog",
    "remover",
    "gpo",
    "protecao",
    "usb",
    "aparencia",
    "mouse",
    "energia",
    "diag",
    "hist",
    "limpeza",
    "registro",
    "ajuda",
    "config",
]


def test_fontes_embutidas(qapp):
    assert tema.carregar_fontes() == ["Archivo", "Inter"]


def test_icones_e_simbolo_renderizam(qapp):
    for nome in ICONES:
        assert not tema.icone(nome, tema.CY5).isNull(), nome
    assert not tema.simbolo().isNull()
