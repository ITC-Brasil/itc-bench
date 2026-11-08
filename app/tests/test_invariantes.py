"""Invariantes do código inteiro (Módulo 14): falham no próximo deslize, não só hoje.

Complementa `test_sem_shell.py` (processo só pelo executor) e `test_texto_puro.py` (rich text).
"""

import ast
import re
from pathlib import Path

import itc_bench

RAIZ = Path(itc_bench.__file__).parent

# Formas de rodar código que fogem do executor ou de "script fixo + dados por ITC_*".
PS_PROIBIDOS = {
    "Invoke-Expression": re.compile(r"(?i)\bInvoke-Expression\b"),
    "iex": re.compile(r"(?i)(^|[\s;|(])iex(\s|$)"),
    "ExecutionPolicy": re.compile(r"(?i)-ExecutionPolicy\b|Set-ExecutionPolicy"),
    "EncodedCommand": re.compile(r"(?i)-e(nc|ncodedcommand)?\s+[A-Za-z0-9+/=]{16,}|EncodedCommand"),
    "Start-Process": re.compile(r"(?i)\bStart-Process\b|\[Diagnostics\.Process\]::Start"),
    "Add-Type": re.compile(r"(?i)\bAdd-Type\b"),
    "cmd /c": re.compile(r"(?i)\bcmd(\.exe)?\s*/[ck]\b"),
    ".bat/.cmd": re.compile(r"(?i)\.(bat|cmd)\b"),
    "ScriptBlock::Create": re.compile(r"(?i)ScriptBlock\]::Create|NewScriptBlock"),
}

# Quem chama a API do Windows direto, fora do executor, e por quê (critério do ADR-018).
WINREG_CTYPES = {
    "nucleo/acl.py": "ACL e dono por SDDL (ADR-011): sem processo, sem texto do icacls",
    "nucleo/caminhos.py": "ProgramData e perfis pelo HKLM, sem o ambiente do usuário (Módulo 14)",
    "nucleo/dpapi.py": "DPAPI: segredo nunca passa por processo (ADR-013/018)",
    "nucleo/elevacao.py": "IsUserAnAdmin e ShellExecuteW runas (Módulo 01)",
    "nucleo/wlan.py": "Wi-Fi pela wlanapi: senha fora de processo (ADR-018)",
    "servicos/api.py": "lê ApiUrl em HKLM (ADR-008)",
    "servicos/cadastros.py": "lê e grava Unidade em HKLM (ADR-014)",
    "servicos/desinstalar.py": "CommandLineToArgvW, sem shell (ADR-020)",
    "servicos/executor.py": "o próprio executor: pasta de sistema e Job Object (ADR-011)",
    "servicos/programas.py": "lê Uninstall de HKLM/HKU (ADR-020)",
    "servicos/remoto.py": "server/tag do GLPI Agent em HKLM e pasta do serviço (ADR-019)",
    "ui/entrar.py": "lê versão do Windows em HKLM (Módulo 04)",
}

CHAMADAS_SCRIPT = {"rodar", "_rodar", "powershell"}
# Montam texto de script com dado constante do código, validado antes (ADR-023, Appx).
SCRIPT_MONTADO = {("servicos/desinstalar.py", "script_appx")}


def _arquivos() -> list[Path]:
    return sorted(RAIZ.rglob("*.py"))


def _rel(arquivo: Path) -> str:
    return arquivo.relative_to(RAIZ).as_posix()


def test_trechos_ps_sem_formas_proibidas():
    trechos = sorted((RAIZ / "recursos").rglob("*.ps1"))
    assert len(trechos) >= 30, "a busca tem que achar os trechos"
    textos = {_rel(t): t.read_text(encoding="utf-8") for t in trechos}
    from itc_bench.servicos import executor

    textos["executor.ABERTURA_PS"] = executor.ABERTURA_PS
    erros = [
        f"{nome}: {regra}"
        for nome, texto in textos.items()
        for regra, padrao in PS_PROIBIDOS.items()
        if padrao.search(texto)
    ]
    assert not erros


def test_trechos_ps_recebem_dados_so_por_itc():
    """`$env:` só para `ITC_*` (dado) ou leitura de pasta pelo PS; nada de variável de usuário."""
    permitidas = {"SystemDrive"}  # só para achar o disco do sistema no Início (leitura)
    erros = []
    for t in sorted((RAIZ / "recursos").rglob("*.ps1")):
        for nome in re.findall(r"(?i)\$env:([A-Za-z_][A-Za-z0-9_]*)", t.read_text("utf-8")):
            if not nome.upper().startswith("ITC_") and nome not in permitidas:
                erros.append(f"{_rel(t)}: $env:{nome}")
    assert not erros


def _nome(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _montado(no: ast.expr) -> bool:
    if isinstance(no, ast.JoinedStr | ast.BinOp):
        return True
    montam = {"format", "replace", "join", "format_map"}
    return isinstance(no, ast.Call) and _nome(no.func) in montam


def test_script_nunca_montado_com_dado():
    erros = []
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            chamada = isinstance(no, ast.Call) and _nome(no.func) in CHAMADAS_SCRIPT and no.args
            if chamada and _montado(no.args[0]):
                erros.append(f"{_rel(arquivo)}:{no.lineno}")
    assert not erros


def test_funcoes_script_so_leem_recursos():
    erros = []
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if not (isinstance(no, ast.FunctionDef) and no.name.startswith("script")):
                continue
            if (_rel(arquivo), no.name) in SCRIPT_MONTADO:
                continue
            if any(isinstance(n, ast.JoinedStr) for n in ast.walk(no) if n is not no):
                # f-string só no nome do arquivo de recurso: f"{nome}.ps1"
                fstrs = [n for n in ast.walk(no) if isinstance(n, ast.JoinedStr)]
                if not all(_so_nome_de_arquivo(f) for f in fstrs):
                    erros.append(f"{_rel(arquivo)}:{no.name}")
    assert not erros


def _so_nome_de_arquivo(f: ast.JoinedStr) -> bool:
    fixos = "".join(v.value for v in f.values if isinstance(v, ast.Constant))
    return fixos == ".ps1"


def test_winreg_e_ctypes_so_na_lista_fechada():
    usam = set()
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            mods = (
                [a.name for a in no.names]
                if isinstance(no, ast.Import)
                else [no.module or ""]
                if isinstance(no, ast.ImportFrom)
                else []
            )
            if any(m.split(".")[0] in {"winreg", "ctypes"} for m in mods):
                usam.add(_rel(arquivo))
    assert usam == set(WINREG_CTYPES)


def test_grupo_administradores_so_pelo_sid():
    nome = re.compile(r"(?i)['\"](BUILTIN\\)?(Administradores|Administrators)['\"]")
    erros = [
        _rel(a)
        for a in [*_arquivos(), *sorted((RAIZ / "recursos").rglob("*.ps1"))]
        if nome.search(a.read_text(encoding="utf-8"))
    ]
    assert not erros
