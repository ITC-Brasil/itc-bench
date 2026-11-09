"""Papel de parede (ADR-022): imagem conferida, pasta com ACL, operações fechadas, hive por alvo.

Só dados fictícios; nenhum download real. O PowerShell real só grava numa chave de teste em HKCU.
"""

import hashlib
import io
import json
import logging
import secrets
import struct
import sys
from pathlib import Path
from typing import Any

import pytest
from test_politicas import ALUNO, DONO, OUTRO, PROT, SUPORTE, Falso, alvo

from itc_bench.servicos import executor, hive, instaladores
from itc_bench.servicos import papel_de_parede as pp
from itc_bench.servicos.cadastros import Instalador


def png(largura: int = 1920, altura: int = 1080) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + struct.pack(">II", largura, altura)
        + b"\x00" * 64
    )


def jpeg(largura: int = 1920, altura: int = 1080) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, altura, largura) + b"\x00" * 10
    return b"\xff\xd8" + app0 + sof + b"\x00" * 32


def linha(conteudo: bytes, arquivo: str = "papel.png", **kw: Any) -> Instalador:
    sha = hashlib.sha256(conteudo).hexdigest()
    return Instalador(
        9,
        "Papel ITC",
        "",
        arquivo,
        sha,
        "https://exemplo.invalid/papel.png",
        "",
        tipo="papel",
        **kw,
    )


def abrir(dados: bytes) -> Any:
    return lambda url: io.BytesIO(dados)


# ---------------------------------------------------------------- imagem


@pytest.mark.parametrize(
    ("dados", "ext", "esperado"),
    [
        (png(800, 600), ".png", (800, 600)),
        (jpeg(1366, 768), ".jpg", (1366, 768)),
        (jpeg(1366, 768), ".jpeg", (1366, 768)),
        (png(), ".jpg", None),  # conteúdo diferente da extensão
        (jpeg(), ".png", None),
        (b"GIF89a" + b"\x00" * 30, ".png", None),
    ],
)
def test_dimensoes(dados: bytes, ext: str, esperado: Any) -> None:
    assert pp.dimensoes(dados, ext) == esperado


def test_obter_confere_hash_e_imagem(tmp_path: Path) -> None:
    dados = png()
    arquivo = pp.obter(linha(dados), base=tmp_path, abrir=abrir(dados))
    assert arquivo.name == f"{hashlib.sha256(dados).hexdigest()}.png"
    assert pp.caminho(linha(dados), base=tmp_path) == arquivo


def test_obter_recusa_imagem_pequena_e_apaga(tmp_path: Path) -> None:
    dados = png(320, 200)
    with pytest.raises(pp.ErroPapel, match="640"):
        pp.obter(linha(dados), base=tmp_path, abrir=abrir(dados))
    assert not list(tmp_path.iterdir())


def test_obter_recusa_hash_diferente(tmp_path: Path) -> None:
    with pytest.raises(pp.ErroPapel, match="SHA-256"):
        pp.obter(linha(png()), base=tmp_path, abrir=abrir(png(1024, 768)))


def test_escolher_arquivo_confere_contra_o_cadastro(tmp_path: Path) -> None:
    dados = jpeg()
    origem = tmp_path / "pendrive.jpg"
    origem.write_bytes(dados)
    base = tmp_path / "papel"
    base.mkdir()
    arquivo = pp.obter(linha(dados, "papel.jpg"), origem, base=base)
    assert arquivo.parent == base and arquivo.read_bytes() == dados
    origem.write_bytes(jpeg(1024, 768))
    with pytest.raises(pp.ErroPapel):
        pp.obter(linha(dados, "outro.jpg"), origem, base=tmp_path / "papel")


@pytest.mark.parametrize("arquivo", ["papel.gif", "papel.bmp", "papel"])
def test_extensao_recusada(arquivo: str) -> None:
    assert ".jpg, .jpeg ou .png" in str(pp.validar(linha(png(), arquivo)))


def test_linhas_so_papel() -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    from itc_bench.servicos.cadastros import Cadastros

    outra = replace(linha(png()), id=10, tipo="instalador")
    c = Cadastros("v" * 64, datetime.now(UTC), "t", None, False, (), (linha(png()), outra), (), ())
    assert [i.id for i in pp.linhas(c)] == [9]
    assert pp.linhas(None) == []


# ---------------------------------------------------------------- operações


def test_operacoes_aplicar_e_desfazer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(instaladores, "papeis", lambda: tmp_path)
    img = tmp_path / ("a" * 64 + ".png")
    ops = pp.operacoes("aplicar", img, "ajustar")
    assert [(o["nome"], o["dado"], o["acao"]) for o in ops] == [
        ("Wallpaper", str(img), "gravar"),
        ("WallpaperStyle", "6", "gravar"),
    ]
    desfazer = pp.operacoes("desfazer")
    assert {(o["nome"], o["acao"]) for o in desfazer} == {
        ("Wallpaper", "apagar"),
        ("WallpaperStyle", "apagar"),
    }
    with pytest.raises(ValueError):
        pp.operacoes("aplicar", Path("C:\\outro") / img.name)
    with pytest.raises(ValueError):
        pp.operacoes("aplicar", img, "lado_a_lado")


def test_aplicar_por_alvo_sem_caminho_no_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    dados = png()
    monkeypatch.setattr(instaladores, "papeis", lambda: tmp_path)
    pp.obter(linha(dados), base=tmp_path, abrir=abrir(dados))
    f = Falso()
    feitos = pp.aplicar(
        "aplicar",
        [hive.MAQUINA, alvo(ALUNO, True), alvo(OUTRO), alvo(SUPORTE), alvo(DONO, True)],
        linha=linha(dados),
        protegidas_=PROT,
        rodar=f,
    )
    por = {x.alvo.chave: x for x in feitos}
    assert hive.MAQUINA.chave not in por  # máquina não recebe papel de parede
    assert por[ALUNO].ok and por[OUTRO].ok
    assert "Suporte não é alterada" in por[SUPORTE].mensagem
    assert not por[DONO].ok
    escritas = [kw for n, kw in f.chamadas if n == "escrever"]
    assert all(kw["perfil"] == "aparencia" for kw in escritas)
    assert f.nomes().count("carregar") == f.nomes().count("descarregar") == 1
    texto = caplog.text
    assert str(tmp_path) not in texto and ALUNO not in texto and "ITCBench_" not in texto
    assert "Papel de parede: aplicar alvo usuario 2 item=papel resultado=ok" in texto


def test_aplicar_sem_imagem_baixada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(instaladores, "papeis", lambda: tmp_path)
    with pytest.raises(pp.ErroPapel, match="baixada"):
        pp.aplicar(
            "aplicar", [alvo(ALUNO, True)], linha=linha(png()), protegidas_=PROT, rodar=Falso()
        )


def test_estado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(instaladores, "papeis", lambda: tmp_path)
    atual = tmp_path / ("a" * 64 + ".png")
    outra = tmp_path / ("b" * 64 + ".jpg")

    def lidos(img: str | None, estilo: str | None = "10") -> dict[str, Any]:
        return {
            "ok": True,
            "valores": {f"{pp.CHAVE}|Wallpaper": img, f"{pp.CHAVE}|WallpaperStyle": estilo},
        }

    assert pp.estado(lidos(str(atual)), atual) == pp.Situacao("aplicado", "preencher")
    assert pp.estado(lidos(str(outra)), atual).estado == "outra_imagem"
    assert pp.estado(lidos("C:\\fora.jpg"), atual).estado == "diferente"
    assert pp.estado(lidos(None, None), atual).estado == "nao_aplicado"
    assert pp.estado(None, atual).estado == "sem_acesso"


# ---------------------------------------------------------------- PowerShell real


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_trecho_aparencia_recusa_valor_e_caminho_fora() -> None:
    """Perfil aparência: em Policies\\System só Wallpaper/WallpaperStyle; caminho só o do Bench."""
    import winreg

    raiz = f"Software\\ITCBenchTeste_{secrets.token_hex(4)}"
    trecho = (
        hive.script("escrever")
        .replace(
            "$base = Base $env:ITC_HIVE",
            f"$base = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{raiz}')",
        )
        .replace("Hive-Escrita $env:ITC_HIVE", "")
    )

    def rodar(ops: list[dict[str, Any]]) -> executor.Resultado:
        return executor.powershell(
            trecho, hive=ALUNO, operacoes=json.dumps(ops), perfil="aparencia"
        )

    try:
        outro = [
            {
                "p": "x",
                "chave": pp.CHAVE,
                "nome": "DisableRegistryTools",
                "tipo": "dword",
                "dado": 0,
                "acao": "apagar",
            }
        ]
        assert "ERRO|valor" in rodar(outro).saida
        fora = [
            {
                "p": "papel",
                "chave": pp.CHAVE,
                "nome": "Wallpaper",
                "tipo": "sz",
                "dado": "C:\\x.jpg",
                "acao": "gravar",
            }
        ]
        assert "ERRO|valor" in rodar(fora).saida
        estilo = [
            {
                "p": "papel",
                "chave": pp.CHAVE,
                "nome": "WallpaperStyle",
                "tipo": "sz",
                "dado": "5",
                "acao": "gravar",
            }
        ]
        assert "ERRO|valor" in rodar(estilo).saida
        raiz_ruim = [
            {
                "p": "x",
                "chave": "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                "nome": "a",
                "tipo": "sz",
                "dado": "b",
                "acao": "gravar",
            }
        ]
        assert "ERRO|raiz" in rodar(raiz_ruim).saida
        ok = [
            {
                "p": "papel",
                "chave": pp.CHAVE,
                "nome": "WallpaperStyle",
                "tipo": "sz",
                "dado": "22",
                "acao": "gravar",
            }
        ]
        r = rodar(ok)
        assert r.ok and "OK|papel" in r.saida, (r.saida, r.erros)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{raiz}\\{pp.CHAVE}") as k:
            assert winreg.QueryValueEx(k, "WallpaperStyle") == ("22", winreg.REG_SZ)
    finally:
        executor.powershell(
            f"[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{raiz}', $false)"
        )


# ---------------------------------------------------------------- nome no escrever.ps1 (ADR-028)


def _padrao_wallpaper() -> str:
    """O trecho do nome do arquivo na lista de permissões do `Wallpaper` em escrever.ps1."""
    import re

    script = hive.script("escrever")
    achado = re.search(r"\[regex\]::Escape\(\$pasta\) \+ '([^']+)'", script)
    assert achado, "regex do Wallpaper não encontrada no escrever.ps1"
    return achado.group(1)


def _nomes_do_cache(tmp_path: Path) -> list[str]:
    """Os dois formatos que o Bench grava: com e sem SHA-256 no cadastro."""
    import dataclasses

    conteudo = png()
    com = linha(conteudo)
    sem = dataclasses.replace(com, sha256="")
    return [
        instaladores.destino(com, ".png", tmp_path).name,
        instaladores.destino(sem, ".png", tmp_path, hashlib.sha256(conteudo).hexdigest()).name,
    ]


RECUSADOS = [
    "papel.png",
    "a" * 64 + ".gif",
    "a" * 63 + ".png",
    "c" + "a" * 64 + ".png",  # sem o hash calculado
    "x" + "a" * 64 + "." + "b" * 64 + ".png",
    "c" + "a" * 64 + "." + "b" * 64 + ".png.exe",
    "..\\" + "a" * 64 + ".png",
]


def test_escrever_aceita_os_dois_nomes_do_cache(tmp_path: Path) -> None:
    """Regressão da v0.17.0: papel sem SHA-256 caía em 'Falhou (valor)'."""
    import re

    padrao = re.compile("^" + _padrao_wallpaper(), re.IGNORECASE)  # -match ignora caixa
    nomes = _nomes_do_cache(tmp_path)
    assert nomes[1].startswith("c") and nomes[1].count(".") == 2
    assert all(padrao.fullmatch(n) for n in nomes), nomes
    assert not any(padrao.fullmatch(n) for n in RECUSADOS)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_escrever_aceita_os_dois_nomes_no_powershell(tmp_path: Path) -> None:
    """O mesmo trecho avaliado pelo `-match` do PowerShell, com a pasta real."""
    nomes = _nomes_do_cache(tmp_path)
    r = executor.powershell(
        "$pasta = [Environment]::GetFolderPath('CommonApplicationData') + '\\ITC\\Bench\\papel\\'\n"
        "$padrao = '^' + [regex]::Escape($pasta) + $env:ITC_PADRAO\n"
        "foreach ($n in ($env:ITC_NOMES | ConvertFrom-Json)) "
        "{ [string](($pasta + $n) -match $padrao) }",
        padrao=_padrao_wallpaper(),
        nomes=json.dumps(nomes + RECUSADOS),
    )
    assert r.ok, r.erros
    assert r.saida.split() == ["True"] * len(nomes) + ["False"] * len(RECUSADOS)
