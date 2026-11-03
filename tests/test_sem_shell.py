"""Nenhum processo externo fora do executor, e nenhum `shell=` verdadeiro em todo o código.

Complementa o ruff (`S602`/`S604`/`TID251`): `# noqa` silencia o lint, mas não este teste.
"""

import ast
from pathlib import Path

import itc_bench

RAIZ = Path(itc_bench.__file__).parent
EXECUTOR = RAIZ / "servicos" / "executor.py"
PROIBIDOS = {
    "subprocess",
    "os.system",
    "os.popen",
    "os.startfile",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    *(
        f"os.{p}{s}"
        for p in ("spawn", "exec")
        for s in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe")
    ),
}
SEM_QT = ("nucleo", "servicos")
# Só monta o texto de parâmetros do ShellExecuteW; não abre processo.
LIBERADOS = {RAIZ / "nucleo" / "elevacao.py": {"subprocess", "subprocess.list2cmdline"}}


def _nomes_usados(arvore: ast.AST) -> set[str]:
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
            nomes.update(f"{no.module}.{a.name}" for a in no.names)
        elif isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
            nomes.add(f"{no.value.id}.{no.attr}")
    return nomes


def _arquivos():
    return sorted(RAIZ.rglob("*.py"))


def test_processo_externo_so_no_executor():
    erros = []
    for arquivo in _arquivos():
        if arquivo == EXECUTOR:
            continue
        usados = _nomes_usados(ast.parse(arquivo.read_text(encoding="utf-8")))
        usados -= LIBERADOS.get(arquivo, set())
        if achados := sorted(n for n in usados if n in PROIBIDOS or n.startswith("subprocess.")):
            erros.append(f"{arquivo.relative_to(RAIZ)}: {achados}")
    assert not erros


def test_nenhum_shell_verdadeiro():
    erros = []
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call):
                for kw in no.keywords:
                    seguro = isinstance(kw.value, ast.Constant) and kw.value.value is False
                    if kw.arg == "shell" and not seguro:
                        erros.append(f"{arquivo.relative_to(RAIZ)}:{no.lineno}")
    assert not erros


def test_nucleo_e_servicos_sem_qt():
    for pasta in SEM_QT:
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            usados = _nomes_usados(ast.parse(arquivo.read_text(encoding="utf-8")))
            assert not any(n.split(".")[0] == "PySide6" for n in usados), arquivo


def test_detector_pega_os_casos(tmp_path):
    codigo = "import subprocess\nimport os\nos.system('x')\nsubprocess.run(['a'], shell=1)\n"
    usados = _nomes_usados(ast.parse(codigo))
    assert {"subprocess", "os.system"} <= usados
