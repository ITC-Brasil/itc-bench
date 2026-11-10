"""Telas Identificação e Wi-Fi (ADR-018): botões, só leitura sem admin, sem cadastro."""

from datetime import UTC, datetime

from PySide6.QtCore import Qt

from itc_bench.servicos import wifi
from itc_bench.servicos.cadastros import Cadastros, Rede
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.identificacao import Estado
from itc_bench.ui import identificacao as tela_id
from itc_bench.ui import wifi as tela_wifi

ESTADO = Estado("PC-TESTE", "PC-TESTE", False, frozenset({"TESTE01"}))


def test_identificacao_valida_e_libera(qtbot, monkeypatch):
    monkeypatch.setattr(tela_id.tarefa, "iniciar", lambda *a: None)
    p = tela_id.PainelIdentificacao(admin=True)
    qtbot.addWidget(p)
    p._recebeu(ESTADO)
    assert not hasattr(p, "b_reiniciar")  # o reinício só é oferecido depois de criar (ADR-029)
    p.nome.setText("abc01-nb01")
    assert p.b_executar.isEnabled() and p.erro.text() == ""
    assert p.b_executar.text() == "Renomear e criar usuários"
    p.nome.setText("teste01")
    assert not p.b_executar.isEnabled() and "conta ou grupo" in p.erro.text()
    p.nome.clear()
    p._recebeu(Estado("PC-TESTE", "PC-NOVO", False, frozenset()))
    assert "Depois de reiniciar: PC-NOVO" in p.situacao.text() and p.nome.text() == "PC-NOVO"


def test_identificacao_sem_admin_so_le(qtbot, monkeypatch):
    monkeypatch.setattr(tela_id.tarefa, "iniciar", lambda *a: None)
    p = tela_id.PainelIdentificacao(admin=False)
    qtbot.addWidget(p)
    p._recebeu(Estado("PC-TESTE", "PC-NOVO", False, frozenset()))
    p.nome.setText("ABC01")
    assert not p.b_executar.isEnabled() and "administrador" in p.motivo.text()


def cadastros(*redes: Rede) -> Cadastros:
    return Cadastros("v", datetime.now(UTC), "t", None, False, (), (), redes, ())


def rede(i: int, ssid: str, unidade: str = "ABC01", senha: str = "Senha-Teste-1") -> Rede:
    return Rede(i, ssid, Sensivel(senha), unidade, "Carreta", "")


def painel(qtbot, monkeypatch, cad, admin=True, unidade="ABC01"):
    monkeypatch.setattr(tela_wifi.tarefa, "iniciar", lambda *a: None)
    p = tela_wifi.PainelWifi(admin, lambda: cad, lambda: unidade)
    qtbot.addWidget(p)
    return p


def test_wifi_marca_ausentes_e_filtra_unidade(qtbot, monkeypatch):
    a, b, c = rede(1, "Rede-A"), rede(2, "Rede-B"), rede(3, "Rede-Outra", unidade="XYZ02")
    p = painel(qtbot, monkeypatch, cadastros(a, b, c))
    linhas = (wifi.Linha(a, "ausente"), wifi.Linha(b, "igual"), wifi.Linha(c, "ausente"))
    p.filtro.setCurrentIndex(0)
    p._recebeu(tela_wifi.Leitura(linhas, ("Rede-B", "Outra-Do-Windows")))
    assert p.tabela.rowCount() == 2  # só a unidade ABC01
    assert p.tabela.item(0, 0).checkState() == Qt.CheckState.Checked
    assert p.tabela.item(1, 0).checkState() == Qt.CheckState.Unchecked
    assert p.b_instalar.text() == "Instalar 1 rede(s)" and p.b_instalar.isEnabled()
    p.filtro.setCurrentIndex(1)
    assert p.tabela.rowCount() == 3
    p.filtro.setCurrentIndex(2)
    assert p.tabela.rowCount() == 2 and not p.b_instalar.isEnabled()


def test_wifi_invalida_nao_marca(qtbot, monkeypatch):
    r = rede(1, "Rede-A", senha="")
    p = painel(qtbot, monkeypatch, cadastros(r))
    p.filtro.setCurrentIndex(1)
    p._recebeu(tela_wifi.Leitura((wifi.Linha(r, "invalida", "Senha vazia no cadastro."),), ()))
    assert "Senha vazia" in p.tabela.item(0, 3).text()
    assert not p.b_instalar.isEnabled()


def test_wifi_sem_cadastro_e_sem_admin(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, None, admin=False)
    p._recebeu(tela_wifi.Leitura((), ("Rede-Do-Windows",)))
    assert "Sem cadastros" in p.estado.text()
    assert p.b_windows.isEnabled()
    assert not p.b_instalar.isEnabled()


def test_wifi_sem_adaptador(qtbot, monkeypatch):
    r = rede(1, "Rede-A")
    p = painel(qtbot, monkeypatch, cadastros(r))
    p._recebeu(tela_wifi.Leitura((), (), "Sem adaptador Wi-Fi ou com o serviço de Wi-Fi parado."))
    assert "Sem adaptador" in p.estado.text() and not p.b_instalar.isEnabled()
