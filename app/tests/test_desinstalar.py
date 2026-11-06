"""Remover programas (ADR-020): separação da UninstallString, recusas, protegidos e lote.

Caminhos e nomes fictícios; os arquivos "existem" por uma função falsa.
"""

import logging
import threading
from pathlib import Path

import pytest

from itc_bench.servicos import desinstalar as d
from itc_bench.servicos import executor
from itc_bench.servicos.programas import Instalado

PF = r"C:\Program Files"
PF86 = r"C:\Program Files (x86)"
WIN = r"C:\Windows"
EXISTEM = {
    rf"{PF}\Editor Exemplo\uninst.exe",
    rf"{PF}\Editor\unins000.exe",
    rf"{PF86}\Jogo X\uninstall.exe",
    rf"{PF}\Sem Aspas\Pasta Com Espaco\remover.exe",
    rf"{PF}\X\Uninstall.exe",
    r"C:\ProgramData\Fornecedor\setup.exe",
    r"C:\Users\fulano\AppData\Local\App\Update.exe",
    rf"{WIN}\System32\cmd.exe",
    rf"{WIN}\System32\rundll32.exe",
    rf"{WIN}\System32\msiexec.exe",
}


def existe(caminho: str) -> bool:
    return caminho in EXISTEM


@pytest.fixture(autouse=True)
def pastas(monkeypatch):
    monkeypatch.setattr(d, "pastas_aceitas", lambda: (Path(PF), Path(PF86), Path(WIN)))


def igual(caminho: str) -> str:
    return caminho


def plano(**valores) -> d.Entrada:
    i = Instalado(
        valores.pop("chave", "Editor"), valores.pop("nome", "Editor Exemplo"), "1.0", False, valores
    )
    return d.plano(i, existe=existe, resolver=igual)


# ---------------------------------------------------------------- separar


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (rf'"{PF}\Editor Exemplo\uninst.exe"', (rf"{PF}\Editor Exemplo\uninst.exe", [])),
        (rf'"{PF}\Editor Exemplo\uninst.exe" /S', (rf"{PF}\Editor Exemplo\uninst.exe", ["/S"])),
        (
            rf'"{PF}\Editor\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
            (rf"{PF}\Editor\unins000.exe", ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]),
        ),
        # Sem aspas, com espaço no caminho: o primeiro prefixo .exe que existe.
        (
            rf"{PF}\Sem Aspas\Pasta Com Espaco\remover.exe /x /y",
            (rf"{PF}\Sem Aspas\Pasta Com Espaco\remover.exe", ["/x", "/y"]),
        ),
        # NSIS: /D= sem aspas com espaço; o executor junta de volta ao mesmo texto.
        (
            rf'"{PF}\X\Uninstall.exe" /S /D={PF}\X',
            (rf"{PF}\X\Uninstall.exe", ["/S", r"/D=C:\Program", r"Files\X"]),
        ),
        # Espaços repetidos sem aspas: mesmo argv.
        (rf'"{PF}\X\Uninstall.exe"  /S   /Q ', (rf"{PF}\X\Uninstall.exe", ["/S", "/Q"])),
    ],
)
def test_separar_aceita(texto, esperado) -> None:
    assert d.separar(texto, existe) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        rf'"{PF}\X\Uninstall.exe" /X="a b"',  # aspas internas: o texto juntado muda
        rf'"{PF}\X\Uninstall.exe" "arg"',  # aspas que sumiriam
        rf'"{PF}\X\Uninstall.exe',  # aspa sem fechar
        rf'"{PF}\X\Uninstall.exe"/S',  # argumento colado na aspa
        rf"{PF}\Nao Existe\x.exe /S",  # sem aspas e nenhum prefixo existe
        "",
    ],
)
def test_separar_recusa(texto) -> None:
    assert d.separar(texto, existe) is None


# ---------------------------------------------------------------- plano


def test_msi_pelo_product_code_ignora_a_uninstall_string() -> None:
    guid = "{11111111-2222-3333-4444-555555555555}"
    e = plano(chave=guid.lower(), WindowsInstaller="1", UninstallString=f"MsiExec.exe /I{guid}")
    assert e.modo == "silencioso"
    assert e.comando[1:] == ("/x", guid, "/qn", "/norestart")
    assert e.executavel.lower() == "msiexec.exe"


def test_msiexec_sem_ser_msi_e_recusado() -> None:
    e = plano(UninstallString=rf"{WIN}\System32\msiexec.exe /I{{1}}")
    assert e.modo == "recusado"


def test_quiet_preferida_e_interativo_como_queda() -> None:
    e = plano(
        QuietUninstallString=rf'"{PF}\Editor\unins000.exe" /VERYSILENT',
        UninstallString=rf'"{PF}\Editor\unins000.exe"',
    )
    assert (e.modo, e.comando[1:]) == ("silencioso", ("/VERYSILENT",))
    e = plano(
        QuietUninstallString=rf'"{PF}\Editor\unins000.exe" /X="a b"',
        UninstallString=rf'"{PF}\Editor\unins000.exe"',
    )
    assert (e.modo, e.comando[1:]) == ("interativo", ())


@pytest.mark.parametrize(
    ("texto", "trecho"),
    [
        (rf"{WIN}\System32\cmd.exe /c del x", "cmd.exe"),
        (rf"{WIN}\System32\rundll32.exe x.dll,Remover", "rundll32.exe"),
        (r'"C:\ProgramData\Fornecedor\setup.exe" /uninstall', "fora de Program Files"),
        (r'"C:\Users\fulano\AppData\Local\App\Update.exe" --uninstall', "fora de Program Files"),
        (rf'"{PF}\X\Uninstall.vbs"', ".exe"),
    ],
)
def test_recusas(texto, trecho) -> None:
    e = plano(UninstallString=texto)
    assert e.modo == "recusado" and trecho in e.motivo and not e.selecionavel


def test_caminho_final_resolvido(monkeypatch) -> None:
    """`..` e junção: vale o caminho final."""
    alvo = rf"{PF}\X\Uninstall.exe"
    i = Instalado("X", "Prog", "1", False, {"UninstallString": f'"{alvo}"'})
    fora = d.plano(i, existe=existe, resolver=lambda _c: r"C:\Users\fulano\x\Uninstall.exe")
    assert fora.modo == "recusado"
    assert d.plano(i, existe=existe, resolver=igual).modo == "interativo"
    assert d.recusa(rf"{PF}\X\..\..\Users\x.exe", resolver=lambda c: str(Path(c).resolve()))


def test_expand_sz_com_program_files() -> None:
    """`REG_EXPAND_SZ` já chega expandido de `programas.instalados`."""
    e = plano(UninstallString=rf'"{PF86}\Jogo X\uninstall.exe" /S')
    assert e.modo == "interativo" and e.executavel == "uninstall.exe"


def test_desinstalador_ausente() -> None:
    assert plano(UninstallString=rf'"{PF}\Sumiu\u.exe"').modo == "ausente"


@pytest.mark.parametrize(
    "nome",
    [
        "ITC Bench",
        "GLPI Agent 1.0",
        "RustDesk",
        "AnyDesk",
        "Microsoft Visual C++ 2015",
        "NVIDIA Driver",
    ],
)
def test_protegidos(nome) -> None:
    e = plano(nome=nome, UninstallString=rf'"{PF}\X\Uninstall.exe"')
    assert e.modo == "protegido" and e.motivo and not e.selecionavel


def test_listar_pula_componentes_atualizacoes_e_duplicatas(monkeypatch) -> None:
    monkeypatch.setattr(
        d.programas, "atalhos", lambda **_k: {"Jogo.lnk": "ITC Bench", "Outro.lnk": "x"}
    )
    monkeypatch.setattr(
        d, "terminal", lambda **_k: d.Entrada("Windows Terminal (Store)", "terminal", "silencioso")
    )
    unins = {"UninstallString": rf'"{PF}\X\Uninstall.exe"'}
    lista = [
        Instalado("A", "Alfa", "1", False, unins),
        Instalado("A", "Alfa", "1", False, unins),  # 64 e 32 bits
        Instalado("B", "Beta", "1", False, {**unins, "SystemComponent": "1"}),
        Instalado("C", "Gama KB1", "1", False, {**unins, "ParentKeyName": "Gama"}),
    ]
    nomes = [(e.nome, e.tipo) for e in d.listar(ler_registro=lambda: lista)]
    assert nomes == [
        ("Alfa", "programa"),
        ("Jogo", "atalho"),
        ("Windows Terminal (Store)", "terminal"),
    ]


# ---------------------------------------------------------------- lote


def res(codigo=0, saida="", esgotado=False) -> executor.Resultado:
    return executor.Resultado(None if esgotado else codigo, saida, "", 0.1, esgotado)


def entrada(nome="Prog", modo="silencioso", tipo="programa") -> d.Entrada:
    return d.Entrada(nome, tipo, modo, (rf"{PF}\X\Uninstall.exe", "/S"))


def test_lote_codigos_e_log_sem_comando(caplog) -> None:
    caplog.set_level(logging.INFO)
    codigos = [0, 3010, 7]
    chamadas = []

    def executar(args, **k):
        chamadas.append(k)
        return res(codigos.pop(0))

    feitos = d.desinstalar([entrada("A"), entrada("B"), entrada("C")], executar=executar)
    assert [f.estado for f in feitos] == ["ok", "reinicio", "falha"]
    assert all(k["encerrar_no_timeout"] is False for k in chamadas)
    assert PF not in caplog.text and "/S" not in caplog.text


def test_msi_1605_e_1618() -> None:
    msi = d.Entrada("M", "programa", "silencioso", (rf"{WIN}\System32\msiexec.exe", "/x", "{1}"))
    codigos = [1605, 1618]
    feitos = d.desinstalar([msi, msi], executar=lambda *a, **k: res(codigos.pop(0)))
    assert [f.estado for f in feitos] == ["ok", "falha"]
    assert "Outra instalação" in feitos[1].mensagem


def test_timeout_pula_programas_mas_segue_atalho_e_terminal() -> None:
    chamadas = []

    def executar(args, **k):
        chamadas.append(args)
        return res(esgotado=True)

    rodar = lambda *a, **k: res(0, "OK")  # noqa: E731
    lote = [
        entrada("A"),
        entrada("B"),
        entrada("Jogo", tipo="atalho"),
        entrada("T", tipo="terminal"),
    ]
    estados = [f.estado for f in d.desinstalar(lote, executar=executar, rodar=rodar)]
    assert estados == ["em_execucao", "pulado", "ok", "ok"]
    assert len(chamadas) == 1


def test_protegido_e_recusado_nao_executam() -> None:
    lote = [
        d.Entrada("P", "programa", "protegido", motivo="Driver."),
        d.Entrada("R", "programa", "recusado"),
    ]
    feitos = d.desinstalar(lote, executar=lambda *a, **k: pytest.fail("executou"))
    assert [f.estado for f in feitos] == ["pulado", "pulado"]


def test_cancelar_entre_itens() -> None:
    cancelar = threading.Event()

    def executar(args, **k):
        cancelar.set()
        return res(0)

    feitos = d.desinstalar([entrada("A"), entrada("B")], executar=executar, cancelar=cancelar)
    assert [f.estado for f in feitos] == ["ok", "cancelado"]


def test_terminal_por_script_fixo() -> None:
    chamadas = []

    def rodar(script, **k):
        chamadas.append((script, k))
        return res(0, "OK")

    feitos = d.desinstalar([entrada("T", tipo="terminal")], rodar=rodar)
    assert feitos[0].estado == "ok"
    script, k = chamadas[0]
    assert k["acao"] == "remover"
    assert "-Name $nome" in script and "*" not in script.split("$nome =")[1].splitlines()[0]
    assert "Remove-AppxProvisionedPackage" in script


# ---------------------------------------------------------------- locais por origem (revisão)

HKU_PF = rf"{PF}\X\Uninstall.exe"
SYS = rf"{WIN}\System32\ferramenta.exe"
WIN_TEMP = rf"{WIN}\Temp\x.exe"
WIN_COR = rf"{WIN}\System32\spool\drivers\color\x.exe"
WIN_OK = rf"{WIN}\Fornecedor\desinstalar.exe"


def plano_origem(caminho: str, usuario: bool) -> d.Entrada:
    i = Instalado("X", "Prog", "1", usuario, {"UninstallString": f'"{caminho}" /S'})
    return d.plano(i, existe=lambda c: c == caminho or existe(c), resolver=igual)


@pytest.mark.parametrize(
    ("caminho", "usuario", "aceito"),
    [
        (HKU_PF, True, True),  # HKU em Program Files
        (SYS, True, False),  # HKU em System32
        (WIN_TEMP, True, False),  # HKU em Windows\Temp
        (WIN_TEMP, False, False),  # HKLM em Windows\Temp
        (WIN_COR, False, False),  # HKLM em subpasta gravável do spool
        (WIN_OK, False, True),  # HKLM em %WINDIR% legítimo
        (SYS, False, True),  # HKLM em System32
    ],
)
def test_locais_por_origem(caminho, usuario, aceito) -> None:
    e = plano_origem(caminho, usuario)
    assert (e.modo == "interativo") is aceito, e.motivo
    if usuario and not aceito:
        assert "entrando na conta do usuário" in e.motivo


def test_hku_msi_por_product_code_aceito() -> None:
    guid = "{11111111-2222-3333-4444-555555555555}"
    i = Instalado(guid, "Prog", "1", True, {"WindowsInstaller": "1", "UninstallString": "x"})
    e = d.plano(i, existe=existe, resolver=igual)
    assert e.modo == "silencioso" and e.comando[1:3] == ("/x", guid)


def test_subpasta_gravavel_pelo_caminho_final() -> None:
    """Junção de uma pasta legítima para Windows\\Temp: vale o destino."""
    motivo = d.recusa(WIN_OK, resolver=lambda _c: WIN_TEMP)
    assert "gravável por usuários" in motivo
