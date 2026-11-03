from unittest import mock

from itc_bench.nucleo import elevacao


def test_precisa_elevar():
    assert elevacao.precisa_elevar(["itc-bench"], admin=False)
    assert not elevacao.precisa_elevar(["itc-bench"], admin=True)
    assert not elevacao.precisa_elevar(["itc-bench", "--dev"], admin=False)
    assert not elevacao.precisa_elevar(["itc-bench", "--teste"], admin=False)


def test_comando_elevado_congelado():
    exe, args = elevacao.comando_elevado([r"C:\x\ITCBench.exe", "--a"], r"C:\x\ITCBench.exe", True)
    assert (exe, args) == (r"C:\x\ITCBench.exe", ["--a"])


def test_comando_elevado_modulo():
    _, args = elevacao.comando_elevado(["qualquer", "--a"], r"C:\py\python.exe", False)
    assert args == ["-m", "itc_bench", "--a"]


def test_pedir_elevacao_chama_runas():
    with mock.patch.object(elevacao.ctypes, "windll") as windll:
        windll.shell32.ShellExecuteW.return_value = 42
        assert elevacao.pedir_elevacao(["itc-bench", "a b"])
        _, verbo, _, params, _, _ = windll.shell32.ShellExecuteW.call_args.args
        assert verbo == "runas"
        assert params.endswith('"a b"')
        windll.shell32.ShellExecuteW.return_value = 5  # recusado
        assert not elevacao.pedir_elevacao(["itc-bench"])
