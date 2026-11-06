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


def _oem_representa(texto: str) -> bool:
    try:
        texto.encode(executor._codec("oem"))
    except UnicodeEncodeError:
        return False
    return True


def test_acento_powershell():
    assert powershell("Write-Output 'ação Ç'").saida.strip() == "ação Ç"


# O cmd escreve na página OEM. As máquinas de campo são pt-BR (850); o runner do CI é en-US
# (437), que não tem "ã".
@pytest.mark.skipif(not _oem_representa("ação"), reason="a página OEM desta máquina não tem 'ã'")
def test_acento_cmd():
    assert executar([sistema32("cmd.exe"), "/c", "echo ação"]).saida.strip() == "ação"


def test_netsh_legivel():
    # O netsh do Windows 11 escreve UTF-8 com acento ("Versão", "Proteção") mesmo com OEM 850.
    r = executar([sistema32("netsh.exe"), "wlan", "show", "drivers"])
    assert "�" not in r.saida + r.erros
    assert "Ã" not in r.saida
    assert "├" not in r.saida


def test_auto_cai_para_oem_quando_nao_e_utf8():
    texto = "ação" if _oem_representa("ação") else "çé"
    assert executor._decodificar(texto.encode(executor._codec("oem")), "auto") == texto
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


def test_sistema32_ignora_systemroot_do_ambiente(monkeypatch):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Falso")
    assert not sistema32("cmd.exe").lower().startswith(r"c:\falso")
    r = powershell("$env:PSModulePath")
    assert "falso" not in r.saida.lower()
    assert r.saida.strip().lower().endswith(r"\windowspowershell\modules")


def test_cancelar_encerra_processo_e_filho():
    import threading

    marca = f"itc-cancela-{time.monotonic_ns()}"
    evento = threading.Event()
    threading.Timer(1.0, evento.set).start()
    r = powershell(
        "Start-Process -NoNewWindow $env:ITC_PING -ArgumentList '-n','60',$env:ITC_MARCA;"
        " Start-Sleep 60",
        timeout=60,
        cancelar=evento,
        ping=sistema32("PING.EXE"),
        marca=marca,
    )
    assert (r.cancelado, r.esgotado, r.codigo, r.ok) == (True, False, None, False)
    assert r.duracao < 10
    time.sleep(0.5)
    vivos = powershell(
        "@(Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" |"
        ' Where-Object CommandLine -like "*$env:ITC_MARCA*").Count',
        marca=marca,
    )
    assert vivos.saida.strip() == "0"


def test_cancelar_sem_sinal_termina_normal_e_respeita_timeout():
    import threading

    evento = threading.Event()
    r = powershell("Write-Output 'oi'", cancelar=evento)
    assert (r.ok, r.saida.strip(), r.cancelado) == (True, "oi", False)
    r = powershell("Start-Sleep 30", timeout=2, cancelar=evento)
    assert (r.esgotado, r.cancelado) == (True, False)


def test_cancelar_com_entrada_no_stdin():
    import threading

    r = executar(
        [PS, "-NoProfile", "-Command", "$input | Write-Output"],
        entrada="linha",
        cancelar=threading.Event(),
    )
    assert r.saida.strip() == "linha"


def test_timeout_sem_encerrar_deixa_o_processo_rodando():
    """ADR-020: instalador não é morto no timeout; o Resultado volta esgotado."""
    marca = str(4000 + time.monotonic_ns() % 50000)  # -w único, para achar o processo
    ping = sistema32("PING.EXE")
    r = executar([ping, "-n", "8", "-w", marca, "127.0.0.1"], timeout=1, encerrar_no_timeout=False)
    assert (r.esgotado, r.codigo, r.ok) == (True, None, False)
    vivos = powershell(
        "@(Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" |"
        ' Where-Object CommandLine -like "*-w $env:ITC_MARCA *").Count',
        marca=marca,
    )
    assert vivos.saida.strip() == "1"
    powershell(
        "Get-CimInstance Win32_Process -Filter \"Name='PING.EXE'\" |"
        ' Where-Object CommandLine -like "*-w $env:ITC_MARCA *" |'
        " Invoke-CimMethod -MethodName Terminate",
        marca=marca,
    )


def test_sem_encerrar_nao_aceita_cancelar():
    import threading

    with pytest.raises(ValueError):
        executar([PS], cancelar=threading.Event(), encerrar_no_timeout=False)
