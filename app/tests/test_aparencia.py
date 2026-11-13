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


def test_ponteiro_preto_tamanho_6() -> None:
    """ADR-047: o tamanho vem do CursorBaseSize; os arquivos são os do tamanho base."""
    escritas = {n: d for _, n, _, d in ap.POR_ID["ponteiro"].escritas("preto_6")}
    assert escritas["Arrow"] == r"%SystemRoot%\cursors\arrow_r.cur"
    assert escritas["Hand"] == r"%SystemRoot%\cursors\aero_link.cur"
    assert escritas["CursorSize"] == 6 and escritas["CursorBaseSize"] == 112


def test_ponteiro_tamanhos_de_1_a_15() -> None:
    p = ap.POR_ID["ponteiro"]
    assert p.padrao == "branco_1"
    for n in (1, 8, 15):
        escritas = {nome: d for _, nome, _, d in p.escritas(f"branco_{n}")}
        assert escritas["CursorSize"] == n and escritas["CursorBaseSize"] == 32 + (n - 1) * 16
    assert "branco_16" not in p.opcoes and "branco_0" not in p.opcoes


def test_estado() -> None:
    v = ap.POR_ID["velocidade"]
    assert ap.estado(v, {}).estado == "padrao"  # ausente = padrão
    assert ap.estado(v, {"Control Panel\\Mouse|MouseSensitivity": "15"}) == ap.Situacao(
        "ajustado", "15"
    )
    assert ap.estado(v, {"Control Panel\\Mouse|MouseSensitivity": "99"}).estado == "diferente"
    p = ap.POR_ID["ponteiro"]
    lidos = {f"{c}|{n}": str(d) for c, n, _, d in p.escritas("invertido_11")}
    assert ap.estado(p, lidos) == ap.Situacao("ajustado", "invertido_11")


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
    ops = ap.operacoes({"velocidade": "15", "ponteiro": "preto_1"})
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


# ---------------------------------------------------------------- modo do Windows (ADR-044)


def test_modo_windows_grava_os_dois_valores_do_tema() -> None:
    ops = ap.operacoes({"modo_windows": "escuro"})
    assert [(o["chave"], o["nome"], o["tipo"], o["dado"]) for o in ops] == [
        (ap._TEMA, "AppsUseLightTheme", "dword", 0),
        (ap._TEMA, "SystemUsesLightTheme", "dword", 0),
    ]
    assert [o["dado"] for o in ap.operacoes({"modo_windows": "claro"})] == [1, 1]
    with pytest.raises(ValueError):
        ap.operacoes({"modo_windows": "azul"})


def test_modo_windows_fora_de_mouse_e_teclado() -> None:
    """A tela Mouse e teclado continua só com o CATALOGO; o modo fica na aba Papel de parede."""
    assert "modo_windows" not in ap.POR_ID
    assert ap.MODO_WINDOWS.padrao == "claro"
    for opcao in ap.MODO_WINDOWS.opcoes:
        for chave, _, _, _ in ap.MODO_WINDOWS.escritas(opcao):
            assert chave in ap.CHAVES_ACEITAS


def test_modo_windows_estado_e_desfazer() -> None:
    m = ap.MODO_WINDOWS
    assert ap.estado(m, {}).estado == "padrao"  # ausente = claro, padrão do Windows
    escuro = {f"{ap._TEMA}|AppsUseLightTheme": "0", f"{ap._TEMA}|SystemUsesLightTheme": "0"}
    assert ap.estado(m, escuro) == ap.Situacao("ajustado", "escuro")
    f = Falso()
    ap.aplicar(
        "desfazer",
        {"modo_windows": "escuro"},
        [alvo(ALUNO, True)],
        protegidas_=PROT,
        rodar=f,
        rotulo="Modo do Windows",
    )
    ops = json.loads(next(kw for n, kw in f.chamadas if n == "escrever")["operacoes"])
    assert [o["dado"] for o in ops] == [1, 1]
