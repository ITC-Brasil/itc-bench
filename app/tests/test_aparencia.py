"""Mouse e teclado (ADR-022): lista fechada, tipos nativos, situação, hive por alvo, ACL herdada.

Só dados fictícios. O PowerShell real só grava numa chave de teste em HKCU, apagada no fim.
"""

import json
import logging
import re
import secrets
import sys
from pathlib import Path

import pytest
from test_politicas import ALUNO, OUTRO, PROT, Falso, alvo

from itc_bench.servicos import aparencia as ap
from itc_bench.servicos import executor, hive


def test_catalogo_chaves_aceitas_e_padrao_valido() -> None:
    for a in ap.CATALOGO:
        assert a.padrao in a.opcoes
        for opcao in a.opcoes:
            for chave, _, _, _ in a.escritas(opcao):
                assert chave in ap.CHAVES_ACEITAS, (a.id, chave)


def test_chaves_iguais_ao_trecho() -> None:
    """O espelho em Python e a lista do comum.ps1 não divergem."""
    comum = (Path(hive.__file__).parent.parent / "recursos" / "politicas" / "comum.ps1").read_text(
        "utf-8"
    )
    bloco = comum.split("$EXATAS_APARENCIA = @(")[1].split(")")[0]
    assert set(re.findall(r"'([^']+)'", bloco)) == ap.CHAVES_ACEITAS


def test_tipos_nativos() -> None:
    for a in ap.CATALOGO:
        for opcao in a.opcoes:
            for chave, nome, tipo, _ in a.escritas(opcao):
                if chave == "Control Panel\\Cursors" and nome not in (
                    "Scheme Source",
                    "CursorBaseSize",
                ):
                    assert tipo == "expand_sz"
                elif chave.startswith("Software\\") or nome in ("Scheme Source", "CursorBaseSize"):
                    assert tipo == "dword"
                else:
                    assert tipo == "sz", (chave, nome)


def test_operacoes_recusam_fora_da_lista() -> None:
    with pytest.raises(ValueError):
        ap.operacoes({"velocidade": "21"})
    with pytest.raises(ValueError):
        ap.operacoes({"esquema_cadastro": "x"})
    ops = ap.operacoes({"velocidade": "15", "botoes": "1"})
    assert [(o["nome"], o["dado"]) for o in ops] == [
        ("MouseSensitivity", "15"),
        ("SwapMouseButtons", "1"),
    ]


def test_ponteiro_preto_grande() -> None:
    escritas = {n: d for _, n, _, d in ap.POR_ID["ponteiro"].escritas("preto_grande")}
    assert escritas["Arrow"] == "%SystemRoot%\\cursors\\arrow_rl.cur"
    assert escritas["Hand"] == "%SystemRoot%\\cursors\\aero_link_l.cur"
    assert escritas["CursorSize"] == 1


def test_estado() -> None:
    v = ap.POR_ID["velocidade"]
    assert ap.estado(v, {}).estado == "padrao"  # ausente = padrão
    assert ap.estado(v, {"Control Panel\\Mouse|MouseSensitivity": "15"}) == ap.Situacao(
        "ajustado", "15"
    )
    assert ap.estado(v, {"Control Panel\\Mouse|MouseSensitivity": "99"}).estado == "diferente"
    p = ap.POR_ID["ponteiro"]
    lidos = {f"{c}|{n}": str(d) for c, n, _, d in p.escritas("invertido_extra")}
    assert ap.estado(p, lidos) == ap.Situacao("ajustado", "invertido_extra")


def test_aplicar_e_desfazer_por_alvo(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    f = Falso()
    feitos = ap.aplicar(
        "aplicar",
        {"velocidade": "15"},
        [hive.MAQUINA, alvo(ALUNO, True), alvo(OUTRO)],
        protegidas_=PROT,
        rodar=f,
    )
    assert [x.ok for x in feitos] == [True, True]
    escritas = [kw for n, kw in f.chamadas if n == "escrever"]
    assert all(kw["perfil"] == "aparencia" for kw in escritas)
    f2 = Falso()
    ap.aplicar("desfazer", {"velocidade": "15"}, [alvo(ALUNO, True)], protegidas_=PROT, rodar=f2)
    ops = json.loads(next(kw for n, kw in f2.chamadas if n == "escrever")["operacoes"])
    assert ops[0]["dado"] == "10"
    assert (
        ALUNO not in caplog.text
        and "Mouse e teclado: aplicar alvo usuario 2 ajuste=velocidade" in caplog.text
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_preferencia_herda_acl_e_tipo_nativo() -> None:
    """Chave de preferência criada pelo Bench só herda a ACL (sem SDDL_NOVA); tipos nativos."""
    import winreg

    raiz = f"Software\\ITCBenchTeste_{secrets.token_hex(4)}"
    trecho = (
        hive.script("escrever")
        .replace("Hive-Escrita $env:ITC_HIVE", "")
        .replace(
            "$base = Base $env:ITC_HIVE",
            f"$base = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{raiz}')",
        )
    )
    ops = ap.operacoes({"velocidade": "15", "ponteiro": "preto_normal"})
    try:
        r = executor.powershell(trecho, hive=ALUNO, operacoes=json.dumps(ops), perfil="aparencia")
        assert r.ok, (r.saida, r.erros)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{raiz}\\Control Panel\\Mouse") as k:
            assert winreg.QueryValueEx(k, "MouseSensitivity") == ("15", winreg.REG_SZ)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{raiz}\\Control Panel\\Cursors") as k:
            assert winreg.QueryValueEx(k, "Arrow")[1] == winreg.REG_EXPAND_SZ
            assert winreg.QueryValueEx(k, "Scheme Source") == (1, winreg.REG_DWORD)
        acl = executor.powershell(
            "[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($env:ITC_CHAVE)"
            ".GetAccessControl().AreAccessRulesProtected",
            chave=f"{raiz}\\Control Panel",
        )
        assert acl.saida.strip() == "False"
    finally:
        executor.powershell(
            f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{raiz}', $false)"
        )
