# PyInstaller (ADR-025): onedir, janela, sem UPX, manifesto asInvoker, versão do pacote.
# Rodar de app/: uv run --group build pyinstaller --noconfirm --clean empacotamento/itc-bench.spec
# Artefato distribuível só pelo CI (docs/BUILD.md): o build local embute caminhos da máquina.
import re
import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

RAIZ = Path(SPECPATH).parent  # app/
FONTE = RAIZ / "src" / "itc_bench"
VERSAO = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', (FONTE / "__init__.py").read_text())
NUMEROS = (*map(int, VERSAO.groups()), 0)
TEXTO = ".".join(map(str, NUMEROS[:3]))

versao = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMEROS, prodvers=NUMEROS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "041604B0",  # pt-BR, Unicode
                    [
                        StringStruct("CompanyName", "Grupo ITC Brasil"),
                        StringStruct("FileDescription", "ITC Bench"),
                        StringStruct("FileVersion", TEXTO),
                        StringStruct("InternalName", "ITC Bench"),
                        StringStruct("OriginalFilename", "ITC Bench.exe"),
                        StringStruct("ProductName", "ITC Bench"),
                        StringStruct("ProductVersion", TEXTO),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0416, 1200])]),
    ],
)

a = Analysis(
    [str(FONTE / "__main__.py")],
    pathex=[str(RAIZ / "src")],
    # recursos/ inteiro (.ps1, SVG, fontes com OFL); lido por importlib.resources.
    datas=[(str(FONTE / "recursos"), "itc_bench/recursos")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtWebEngineCore", "PySide6.QtQml"],
    noarchive=False,
    optimize=0,
)
# O OpenSSL do _ssl vem da pasta DLLs do próprio Python: a análise de dependências procura também
# no PATH da máquina de build e pegou um libcrypto de outro programa (o _ssl não carregava).
DLLS_PYTHON = Path(sys.base_prefix) / "DLLs"
OPENSSL = {"libcrypto-3-x64.dll", "libssl-3-x64.dll"}
a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in OPENSSL] + [
    (nome, str(DLLS_PYTHON / nome), "BINARY") for nome in sorted(OPENSSL)
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ITC Bench",
    icon=str(Path(SPECPATH) / "itc-bench.ico"),
    version=versao,
    console=False,
    upx=False,
    uac_admin=False,  # asInvoker: a elevação é do elevacao.py (--dev e --teste sem UAC)
    debug=False,
    strip=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ITC Bench")
