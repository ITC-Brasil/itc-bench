"""Tela Acesso remoto (ADR-019): rótulos, só leitura sem admin, falta de cadastro, confirmação."""

from test_remoto import CHAVE, SENHA_AD, SENHA_RD, cad

from itc_bench.servicos import remoto
from itc_bench.ui import remoto as tela


def sit(programa, comparacao="ausente", falta="", instalada=None, id_remoto=""):
    return remoto.Situacao(programa, instalada, "1.0", comparacao, None, "", id_remoto, falta)


def painel(qtbot, monkeypatch, admin=True, cadastros=None):
    monkeypatch.setattr(tela.tarefa, "iniciar", lambda *a: None)
    p = tela.PainelRemoto(admin, lambda: cadastros, lambda: "ABC01")
    qtbot.addWidget(p)
    return p


def test_rotulos_por_versao(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch)
    p._recebeu(
        {
            "GLPI Agent": sit("GLPI Agent"),
            "RustDesk": sit("RustDesk", "velha", instalada="0.9", id_remoto="123 456 789"),
            "AnyDesk": sit("AnyDesk", "nova", instalada="ad 9.0"),
        }
    )
    assert p.cartoes["GLPI Agent"].principal.text() == "Instalar"
    assert p.cartoes["RustDesk"].principal.text() == "Atualizar"
    assert "ID: 123 456 789" in p.cartoes["RustDesk"].info.text()
    assert p.cartoes["AnyDesk"].principal.text() == "Reconfigurar"
    assert "atualize o cadastro" in p.cartoes["AnyDesk"].info.text()
    assert not p.cartoes["AnyDesk"].arquivo.isEnabled()  # sem reinstalar por cima de mais nova
    assert p.cartoes["GLPI Agent"].principal.isEnabled()


def test_sem_admin_so_le_e_falta_desabilita(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    p._recebeu({x: sit(x) for x in remoto.PROGRAMAS})
    assert not any(c.principal.isEnabled() for c in p.cartoes.values())
    q = painel(qtbot, monkeypatch)
    q._recebeu({x: sit(x, falta="Cadastre “RustDesk” / chave") for x in remoto.PROGRAMAS})
    assert not q.cartoes["RustDesk"].principal.isEnabled()
    assert "Falta: Cadastre" in q.cartoes["RustDesk"].info.text()


def test_confirmacao_sem_segredo(qtbot, monkeypatch):
    p = painel(qtbot, monkeypatch, admin=False)
    for programa in remoto.PROGRAMAS:
        d = remoto.dados(cad(), programa, "ABC01")
        texto = p.confirmacao(d, "Instalar", None)
        assert "SHA-256" in texto and "Comando:" in texto
        assert SENHA_RD not in texto and SENHA_AD not in texto and CHAVE not in texto
    glpi = p.confirmacao(remoto.dados(cad(tag=""), "GLPI Agent", "ABC01"), "Instalar", None)
    assert "Tag: sem tag" in glpi


def test_confirmacao_sem_sha_cadastrado(qtbot, monkeypatch):
    """ADR-028: linha sem SHA-256 é válida; a tela só indica, sem pedir ação."""
    from dataclasses import replace

    p = painel(qtbot, monkeypatch, admin=False)
    d = remoto.dados(cad(), "RustDesk", "ABC01")
    d = replace(d, instalador=replace(d.instalador, sha256=""))
    assert "SHA-256: não cadastrado" in p.confirmacao(d, "Instalar", None)
