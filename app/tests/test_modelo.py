"""Modelo de configuração (ADR-076): arquivo, conferência na leitura, pasta indicada e as telas
marcadas pelo modelo. Nada lê nem muda o Windows."""

import json
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from itc_bench.servicos import desinstalar as des
from itc_bench.servicos import modelo
from itc_bench.ui import programas as ui_programas
from itc_bench.ui import tema
from itc_bench.ui.janela import Janela
from itc_bench.ui.log_qt import HandlerTela

DA_PASTA = modelo.da_pasta  # o conftest troca por um falso; estes testes usam o de verdade
NA_PASTA = modelo.na_pasta
COMPLETO = modelo.Modelo(
    perfil="aluno",
    etapas_desmarcadas=("wifi",),
    turnos=("Manha", "Tarde"),
    sufixo="Lab",
    com_sufixo=True,
    redes=("12", "40"),
    programas=("3", "7"),
    remover=(("McAfee LiveSafe", "programa"), ("Spotify", "terminal")),
    politicas=("bloquear_loja",),
    manter_inicializacao=("OneDrive",),
    unidade="UM01",
)


# ---------------------------------------------------------------- arquivo


def test_salvar_e_ler_volta_igual(tmp_path):
    salvo = modelo.salvar(COMPLETO, tmp_path / "um01")
    assert salvo.name == "um01.itcbench"
    texto = salvo.read_text("utf-8")
    assert "senha" not in texto.casefold()
    lido = modelo.ler(salvo)
    for campo in ("perfil", "etapas_desmarcadas", "turnos", "sufixo", "com_sufixo", "redes",
                  "remover", "politicas", "manter_inicializacao", "unidade"):  # fmt: skip
        assert getattr(lido, campo) == getattr(COMPLETO, campo), campo
    assert set(lido.secoes) >= {"configuracao", "identificacao", "wifi", "remover", "politicas"}


def test_resumo_lista_cada_secao():
    texto = "\n".join(COMPLETO.resumo())
    for trecho in ("perfil aluno", "Manha, Tarde", "sufixo Lab", "2 rede(s)", "2 programa(s)",
                   "1 marcada(s)", "1 mantido(s)"):  # fmt: skip
        assert trecho in texto


@pytest.mark.parametrize(
    ("conteudo", "erro"),
    [
        ("não é json", "não é JSON"),
        (json.dumps({"formato": "outro"}), "não é um modelo"),
        (json.dumps({"formato": "itc-bench-modelo", "versao": 99}), "mais nova"),
    ],
)
def test_arquivo_ruim_e_recusado(tmp_path, conteudo, erro):
    arquivo = tmp_path / "x.itcbench"
    arquivo.write_text(conteudo, "utf-8")
    with pytest.raises(ValueError, match=erro):
        modelo.ler(arquivo)


def test_arquivo_grande_demais(tmp_path):
    arquivo = tmp_path / "x.itcbench"
    arquivo.write_text(" " * (modelo.LIMITE_BYTES + 1), "utf-8")
    with pytest.raises(ValueError, match="grande demais"):
        modelo.ler(arquivo)


def test_valores_estranhos_sao_descartados():
    m = modelo.de_dados(
        {
            "formato": "itc-bench-modelo",
            "versao": 1,
            "configuracao": {"perfil": "a b; rm", "etapas_desmarcadas": ["ok", 3, "x" * 300]},
            "identificacao": {"turnos": ["Manha", "Madrugada"], "sufixo": "n/ã o", "com_sufixo": 1},
            "wifi": ["12", {"id": 3}],
            "remover": [["Chrome", "programa"], ["só um"], "texto"],
            "politicas": "bloquear_loja",
        }
    )
    assert m.perfil == "" and m.etapas_desmarcadas == ("ok",)
    assert m.turnos == ("Manha",) and m.sufixo == "" and m.com_sufixo is False
    assert m.redes == ("12",) and m.remover == (("Chrome", "programa"),)
    assert m.politicas == ()
    assert "inicializacao" not in m.secoes  # seção ausente não mexe na tela


def test_pasta_pega_o_mais_novo_e_pula_o_ruim(tmp_path, monkeypatch):
    monkeypatch.setattr(modelo, "pasta", lambda: tmp_path)
    monkeypatch.setattr(modelo, "da_pasta", DA_PASTA)
    monkeypatch.setattr(modelo, "na_pasta", NA_PASTA)
    velho = modelo.salvar(modelo.Modelo(perfil="aluno"), tmp_path / "velho")
    novo = modelo.salvar(modelo.Modelo(perfil="pedagogo"), tmp_path / "novo")
    ruim = tmp_path / "ruim.itcbench"
    ruim.write_text("{", "utf-8")
    os.utime(velho, (1, 1))
    os.utime(novo, (2, 2))
    achado = modelo.da_pasta()
    assert achado is not None and achado[0] == novo and achado[1].perfil == "pedagogo"
    os.utime(ruim, (3, 3))
    assert modelo.da_pasta()[0] == novo  # o ruim é mais novo, mas é pulado


def test_pasta_vazia_ou_inexistente(tmp_path, monkeypatch):
    monkeypatch.setattr(modelo, "pasta", lambda: tmp_path / "nao_existe")
    monkeypatch.setattr(modelo, "da_pasta", DA_PASTA)
    monkeypatch.setattr(modelo, "na_pasta", NA_PASTA)
    assert modelo.da_pasta() is None


# ---------------------------------------------------------------- telas


def _janela(qtbot):
    tema.aplicar(QApplication.instance())
    j = Janela(HandlerTela())
    qtbot.addWidget(j)
    return j


def test_aplicar_e_coletar_pela_janela(qtbot):
    j = _janela(qtbot)
    avisos = j._aplicar_modelo(modelo.de_dados(modelo.para_dados(COMPLETO)))
    assert avisos == ["perfil aluno não está no cadastro desta unidade"]  # teste sem cadastro
    assert j.identificacao.turnos["Manha"].isChecked()
    assert not j.identificacao.turnos["Noite"].isChecked()
    assert j.identificacao.sufixo.text() == "Lab" and j.identificacao.com_sufixo.isChecked()
    m = j._coletar_modelo()
    assert m.turnos == ("Manha", "Tarde") and m.sufixo == "Lab"
    assert m.redes == ("12", "40")  # telas ainda sem leitura: guardam o do modelo
    assert m.programas == ("3", "7")
    assert set(m.remover) == set(COMPLETO.remover)
    assert m.politicas == ("bloquear_loja",)
    assert m.manter_inicializacao == ("OneDrive",)


def test_tela_importar_mostra_resumo_e_avisos(qtbot, tmp_path):
    j = _janela(qtbot)
    arquivo = modelo.salvar(COMPLETO, tmp_path / "um01")
    j.modelo.carregar(arquivo)
    assert "um01.itcbench" in j.modelo.estado.text() and "UM01" in j.modelo.estado.text()
    assert "Atenção: perfil aluno" in j.modelo.detalhe.text()
    ruim = tmp_path / "ruim.itcbench"
    ruim.write_text("{", "utf-8")
    j.modelo.carregar(ruim)
    assert j.modelo.estado.text() == "Modelo recusado: arquivo não é JSON."


def test_remover_marca_do_modelo_e_guarda_removidos(qtbot):
    p = ui_programas.PainelRemover(True)
    qtbot.addWidget(p)
    p.aplicar_modelo((("Spotify", "programa"), ("Protegido", "programa")))
    entradas = [
        des.Entrada("Spotify", "programa", "silencioso", ("u.exe",)),
        des.Entrada("Protegido", "programa", "recusado"),
        des.Entrada("Chrome", "programa", "silencioso", ("c.exe",)),
    ]
    p._recebeu(entradas)
    marcados = {p.tabela.item(r, 0).text() for r in p.marcadas()}
    assert marcados == {"Spotify"}  # o protegido não ganha marca
    p.tabela.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    p._feito([des.Feito(entradas[2], "ok", "removido")])
    assert ("Chrome", "programa") in p.marcacoes()  # removido nesta sessão vai para o modelo
    assert ("Spotify", "programa") not in p.marcacoes()


def test_programas_marca_do_modelo_e_guarda_instalados(qtbot):
    from itc_bench.servicos import programas as pg
    from itc_bench.servicos.cadastros import Instalador

    def linha(i, nome, situacao="nao_instalado"):
        cad = Instalador(i, nome, "", "", "", "", "", tipo="winget", identificador=f"x.{i}")
        return pg.Linha(pg.Item(cad), situacao)

    p = ui_programas.PainelProgramas(True, lambda: None)
    qtbot.addWidget(p)
    p.aplicar_modelo(("3", "5", "9"))
    linhas = [linha(3, "VLC"), linha(5, "Duplicado", "bloqueado"), linha(7, "Chrome")]
    p._recebeu((linhas, ""))
    assert {p.tabela.item(r, 0).text() for r in p.marcadas()} == {"VLC"}
    p._feito([pg.Resultado(linhas[2].item, "ok", "instalado")])
    assert set(p.marcacoes()) == {"3", "7"}


# ---------------------------------------------------------------- usar sempre (ADR-078)


def _pasta_real(monkeypatch, tmp_path):
    destino = tmp_path / "modelos"
    monkeypatch.setattr(modelo, "pasta", lambda: destino)
    monkeypatch.setattr(modelo, "na_pasta", NA_PASTA)
    monkeypatch.setattr(modelo, "da_pasta", DA_PASTA)
    return destino


def test_usar_sempre_copia_e_vence_os_antigos(tmp_path, monkeypatch):
    destino = _pasta_real(monkeypatch, tmp_path)
    antigo = modelo.salvar(modelo.Modelo(perfil="aluno"), destino.parent / "antigo")
    destino.mkdir()
    velho = modelo.salvar(modelo.Modelo(perfil="pedagogo"), destino / "velho")
    os.utime(velho, (2_000_000_000, 2_000_000_000))  # "do futuro": a cópia nova ainda vence
    copia = modelo.usar_sempre(antigo)
    assert copia.parent == destino and antigo.exists()
    os.utime(velho, (1, 1))
    assert modelo.da_pasta()[1].perfil == "aluno"
    assert modelo.parar_de_usar() == 2 and modelo.na_pasta() == []
    assert antigo.exists()  # o original não é mexido


def test_importar_com_usar_sempre_guarda_na_pasta(qtbot, tmp_path, monkeypatch):
    from itc_bench.ui import modelo as ui_modelo

    destino = _pasta_real(monkeypatch, tmp_path)
    arquivo = modelo.salvar(COMPLETO, tmp_path / "um01")
    p = ui_modelo.PainelModelo(lambda: COMPLETO, lambda _m: [])
    qtbot.addWidget(p)
    assert p.usar_sempre.isChecked() and not p.b_parar.isEnabled()
    monkeypatch.setattr(ui_modelo.QFileDialog, "getOpenFileName", lambda *_a: (str(arquivo), ""))
    p._importar()
    assert (destino / "um01.itcbench").exists() and "ao abrir o Bench" in p.estado.text()
    assert p.b_parar.isEnabled() and "Em uso: um01.itcbench" in p.pasta.text()
    monkeypatch.setattr(ui_modelo, "confirmar", lambda *_a: True)
    p._parar()
    assert modelo.na_pasta() == [] and not p.b_parar.isEnabled()


def test_importar_sem_usar_sempre_nao_copia(qtbot, tmp_path, monkeypatch):
    from itc_bench.ui import modelo as ui_modelo

    destino = _pasta_real(monkeypatch, tmp_path)
    arquivo = modelo.salvar(COMPLETO, tmp_path / "um01")
    p = ui_modelo.PainelModelo(lambda: COMPLETO, lambda _m: [])
    qtbot.addWidget(p)
    p.usar_sempre.setChecked(False)
    monkeypatch.setattr(ui_modelo.QFileDialog, "getOpenFileName", lambda *_a: (str(arquivo), ""))
    p._importar()
    assert not destino.exists() or not list(destino.iterdir())
