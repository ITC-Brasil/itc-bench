"""Varredura do artefato atrás de dado real (ADR-025, ADR-009).

Olha a árvore instalada (que é o conteúdo do instalador já descomprimido), os `.zip` dentro dela
(`base_library.zip`) e o arquivo embutido no EXE do PyInstaller (o `PYZ`, descomprimido módulo a
módulo), que `strings` não enxerga.

Uso, de `app/`:  uv run --group build python ../instalador/varrer.py <pasta> [--extra arquivo]

Padrões sempre: SID de conta real, prefixo de token do Bench/TA, pasta do perfil e do checkout da
máquina de build (do ambiente), `.conversa`. Só no código do Bench (módulos `itc_bench` e
`recursos/`): toda URL fora dos domínios esperados. `--extra`: um padrão (regex) por linha, a lista
real fica fora do repositório (AGENTS.md). A saída diz arquivo e nome do padrão, nunca o valor.
Código de saída 1 se achar algo.
"""

import io
import os
import re
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

URL = re.compile(rb"https?://([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# Domínios que o próprio código do Bench cita (documentação de terceiros e exemplos).
URL_ESPERADAS = re.compile(
    rb"(^|\.)(exemplo\.invalid|example\.(com|org|invalid)|microsoft\.com|"
    rb"windows\.net|w3\.org|qt\.io|python\.org|github\.com|sil\.org|c2pa\.org|127\.0\.0\.1)$"
)


def padroes(extra: Path | None) -> dict[str, re.Pattern[bytes]]:
    fixos = {
        "sid-de-conta": rb"S-1-5-21-\d{6,}-\d{6,}-\d{6,}",
        "token-itcta": rb"itcta_[A-Za-z0-9_-]{16,}",
        "token-itcbs": rb"itcbs_[A-Za-z0-9_-]{16,}",
        "conversa": rb"\.conversa[\\/]",
    }
    for nome, var in (("perfil-de-build", "USERPROFILE"), ("checkout", "GITHUB_WORKSPACE")):
        if valor := os.environ.get(var):
            fixos[nome] = re.escape(valor.encode()) + rb"|" + re.escape(valor.encode("utf-16-le"))
    if extra:
        linhas = extra.read_text("utf-8").splitlines()
        for n, linha in enumerate(filter(None, map(str.strip, linhas)), 1):
            fixos[f"extra-{n}"] = linha.encode()
    return {nome: re.compile(p, re.IGNORECASE) for nome, p in fixos.items()}


def blobs(pasta: Path) -> Iterator[tuple[str, bytes, bool]]:
    """(nome, conteúdo, é código do Bench)."""
    for arquivo in sorted(p for p in pasta.rglob("*") if p.is_file()):
        nome = arquivo.relative_to(pasta).as_posix()
        dados = arquivo.read_bytes()
        yield nome, dados, "itc_bench/recursos/" in nome
        if arquivo.suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                for item in z.namelist():
                    yield f"{nome}!{item}", z.read(item), False
        if arquivo.suffix == ".exe" and dados[:2] == b"MZ":
            yield from _pyinstaller(arquivo, nome)


def _pyinstaller(exe: Path, nome: str) -> Iterator[tuple[str, bytes, bool]]:
    try:
        carchive = CArchiveReader(str(exe))
    except Exception:  # noqa: BLE001 — EXE sem arquivo do PyInstaller (o desinstalador)
        return
    for item in carchive.toc:
        dados = carchive.extract(item)
        if item.endswith(".pyz"):
            pyz = carchive.open_embedded_archive(item)
            assert isinstance(pyz, ZlibArchiveReader)
            for modulo in pyz.toc:
                # raw=True: já descomprimido, sem unmarshal (strings do .pyc legíveis).
                codigo = pyz.extract(modulo, raw=True)
                yield f"{nome}!{item}!{modulo}", codigo, modulo.startswith("itc_bench")
        elif dados:
            yield f"{nome}!{item}", dados, item == "__main__"


def main() -> int:
    pasta = Path(sys.argv[1])
    extra = Path(sys.argv[sys.argv.index("--extra") + 1]) if "--extra" in sys.argv else None
    regras = padroes(extra)
    achados, vistos = [], 0
    for nome, dados, do_bench in blobs(pasta):
        vistos += 1
        achados += [f"{nome}: {regra}" for regra, p in regras.items() if p.search(dados)]
        if do_bench:
            hosts = {h.lower() for h in URL.findall(dados)}
            achados += [f"{nome}: url-fora-da-lista" for h in hosts if not URL_ESPERADAS.search(h)]
    print(f"Varredura: {vistos} itens, padrões: {', '.join(regras)}")
    print("\n".join(sorted(set(achados))) or "Nada encontrado.")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
