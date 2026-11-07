"""Telas do Módulo 13 (ADR-023): Ajuda consolidada, Preparação, Limpeza e Registro, sem tocar
no Windows (serviços trocados por falsos)."""

from itc_bench.servicos import limpeza, perfis, registro
from itc_bench.servicos import preparacao as prep
from itc_bench.ui import ajuda, tarefa
from itc_bench.ui import limpeza as ui_limpeza
from itc_bench.ui import preparacao as ui_prep
from itc_bench.ui import registro as ui_registro
from itc_bench.ui.navegacao import GRUPOS


def _sincrono(monkeypatch):
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(f()))


def test_ajuda_cobre_todas_as_telas_na_ordem_do_menu():
    chaves = [i.chave for _, itens in GRUPOS for i in itens]
    assert [c for c, _, _ in ajuda.secoes()] == chaves
    assert all(ajuda.TEXTOS[c].strip() for c in chaves)


def test_ajuda_busca_sem_acento_e_maiuscula():
    achadas = {c for c, _, _ in ajuda.secoes("JUNCAO")} | {
        c for c, _, _ in ajuda.secoes("reinicio")
    }
    assert "prep" in achadas
    assert ajuda.secoes("palavra-que-nao-existe-em-lugar-nenhum") == []


def test_painel_ajuda_filtra(qtbot):
    p = ajuda.PainelAjuda()
    qtbot.addWidget(p)
    p.busca.setText("lixeira")
    assert "Limpeza" in p.texto.toPlainText() and "Wi-Fi" not in p.contagem.text()


def test_preparacao_sem_admin_so_le(qtbot, monkeypatch):
    _sincrono(monkeypatch)
    monkeypatch.setattr(
        ui_prep.PainelPreparacao, "_carregar_alunos", lambda self, marcar=None: None
    )
    p = ui_prep.PainelPreparacao(False, lambda: None, lambda: None)
    qtbot.addWidget(p)
    p.ler()
    assert p.andamento is not None
    assert all(
        s.situacao in ("bloqueada", "feito", "falhou") for s in p.andamento.situacao.values()
    )
    assert not p.b_rodar.isEnabled()


def test_preparacao_confirmacao_lista_o_que_muda(qtbot):
    p = ui_prep.PainelPreparacao(True, lambda: None, lambda: None)
    qtbot.addWidget(p)
    p.andamento = prep.Andamento(
        "sala_de_aula",
        ["wifi", "energia"],
        {
            "wifi": prep.Leitura("pendente", "2 rede(s) a instalar"),
            "energia": prep.Leitura("feito"),
        },
    )
    texto = p.confirmacao()
    assert "Wi-Fi: 2 rede(s)" in texto and "Energia" not in texto


def test_preparacao_perfil_da_unidade_desconhecido(qtbot):
    p = ui_prep.PainelPreparacao(False, lambda: None, lambda: None)
    qtbot.addWidget(p)
    assert p.perfil_da_unidade()[0] is perfis.PADRAO


def test_limpeza_sem_admin_nao_limpa(qtbot, monkeypatch):
    _sincrono(monkeypatch)
    itens = [limpeza.Item(i, 1, 1024, 0, True) for i, _ in limpeza.ITENS]
    monkeypatch.setattr(limpeza, "previa", lambda ids: itens)
    p = ui_limpeza.PainelLimpeza(False)
    qtbot.addWidget(p)
    p.calcular()
    assert not p.b_limpar.isEnabled() and "KB" in p.estado.text()


def test_limpeza_admin_conta_so_marcados(qtbot, monkeypatch):
    _sincrono(monkeypatch)
    itens = [limpeza.Item(i, 1, 1 << 20, 0, True) for i, _ in limpeza.ITENS]
    monkeypatch.setattr(limpeza, "previa", lambda ids: itens)
    p = ui_limpeza.PainelLimpeza(True)
    qtbot.addWidget(p)
    p.calcular()
    p.marcar(["temp_sistema", "temp_usuarios"])
    assert p.b_limpar.isEnabled() and p.b_limpar.text() == "Limpar 2,0 MB"


def test_registro_filtra(qtbot, monkeypatch):
    _sincrono(monkeypatch)
    linhas = registro.interpretar(
        "2026-11-06 10:00:00,1 INFO [t] x: um\n2026-11-06 10:00:01,1 ERROR [t] x: dois\n"
    )
    monkeypatch.setattr(registro, "ler", lambda pasta=None: linhas)
    p = ui_registro.PainelRegistro()
    qtbot.addWidget(p)
    p.carregar()
    p.nivel.setCurrentText("Erros")
    assert "dois" in p.texto.toPlainText() and "um" not in p.texto.toPlainText()
