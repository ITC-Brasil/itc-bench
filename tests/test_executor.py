"""Executor: processos reais no Windows, sem mock."""

import logging
import time

import pytest

from itc_bench.servicos import executor
from itc_bench.servicos.executor import Sensivel, executar, powershell, sistema32

PS = sistema32(r"WindowsPowerShell\v1.0\powershell.exe")


def test_codigo_saida_e_duracao():
    r = powershell("Write-Output 'oi'; exit 3")
    assert (r.codigo, r.saida.strip(), r.esgotado, r.ok) == (3, "oi", False, False)
    assert r.duracao > 0


def test_recusa_texto_caminho_relativo_e_sensivel_em_argumento():
    with pytest.raises(TypeError):
        executar("cmd /c echo x")
    with pytest.raises(ValueError, match="absoluto"):
        executar(["cmd.exe", "/c", "echo"])
    with pytest.raises(TypeError):
        executar([PS, Sensivel("x")])  # type: ignore[list-item]


def test_nome_de_variavel_validado():
    for nome in ("SENHA", "ITC_minusculo", "ITC_A;B", "ITC_"):
        with pytest.raises(ValueError, match="variável"):
            executar([PS, "-Command", "1"], ambiente={nome: "x"})


def test_itc_herdado_nao_chega_ao_filho(monkeypatch):
    monkeypatch.setenv("ITC_HERDADO", "vazou")
    r = powershell('Write-Output "[$env:ITC_HERDADO]"')
    assert r.saida.strip() == "[]"


def test_sensivel_mascarado_em_repr_saida_erro_e_log(caplog):
    senha = Sensivel("Inventada#2026")
    assert repr(senha) == str(senha) == f"{senha}" == "***"
    with caplog.at_level(logging.INFO):
        r = powershell('Write-Output $env:ITC_SENHA; throw "falhou: $env:ITC_SENHA"', senha=senha)
    assert not r.ok
    assert "Inventada" not in r.saida + r.erros + caplog.text + repr(r)
    assert "***" in r.saida
    assert "***" in r.erros
    assert "ITC_SENHA" in caplog.text


@pytest.mark.parametrize("valor", ["Inv<ent>&ada\"'", "Inv_x0041_ada", "Invção#1"])
def test_sensivel_com_caracteres_escapados_no_clixml(valor):
    r = powershell('throw "erro: $env:ITC_SENHA"', senha=Sensivel(valor))
    assert not r.ok
    assert "#< CLIXML" not in r.erros
    assert "erro: ***" in r.erros
    assert "Inv" not in r.erros


def test_entrada_pelo_stdin_mascarada():
    r = executar(
        [PS, "-NoProfile", "-Command", "$input | ForEach-Object { 'lido:' + $_ }"],
        entrada=Sensivel("Pin#Inventado"),
    )
    assert r.saida.strip() == "lido:***"


def test_timeout_encerra_processo_e_filho():
    marca = f"itc-teste-{time.monotonic_ns()}"
    # O PowerShell abre um filho (ping longo) e dorme; os dois têm que morrer no timeout.
    r = powershell(
        "Start-Process -NoNewWindow $env:ITC_PING -ArgumentList '-n','60',$env:ITC_MARCA;"
        " Start-Sleep 60",
        timeout=3,
        ping=sistema32("PING.EXE"),
        marca=marca,
    )
    assert r.esgotado
    assert r.codigo is None
    assert r.duracao < 15
    time.sleep(0.5)
    vivos = powershell(
        "@(Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" |"
        ' Where-Object CommandLine -like "*$env:ITC_MARCA*").Count',
        marca=marca,
    )
    assert vivos.saida.strip() == "0"


def test_acento_powershell_e_cmd():
    assert powershell("Write-Output 'ação Ç'").saida.strip() == "ação Ç"
    assert executar([sistema32("cmd.exe"), "/c", "echo ação"]).saida.strip() == "ação"


def test_netsh_legivel():
    # O netsh do Windows 11 escreve UTF-8 com acento ("Versão", "Proteção") mesmo com OEM 850.
    r = executar([sistema32("netsh.exe"), "wlan", "show", "drivers"])
    assert "�" not in r.saida + r.erros
    assert "Ã" not in r.saida
    assert "├" not in r.saida


def test_auto_cai_para_oem_quando_nao_e_utf8():
    assert executor._decodificar("ação".encode("cp850"), "auto") == "ação"
    assert executor._decodificar("ação".encode(), "auto") == "ação"


def test_script_grande_demais():
    with pytest.raises(ValueError, match="limite"):
        powershell("#" * executor.LIMITE_SCRIPT)


def test_politica_restricted_nao_impede_modulos():
    r = executar(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Restricted",
            "-Command",
            "(Get-LocalUser).Count; (Get-NetAdapter).Count",
        ]
    )
    assert r.ok, r.erros
