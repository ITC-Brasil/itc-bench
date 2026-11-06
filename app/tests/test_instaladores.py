"""Instaladores com SHA-256 (ADR-019): validação, download, cópia, conferência, limpeza, log.

Só dados fictícios; nenhum download real (o `abrir` é falso).
"""

import hashlib
import io
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from itc_bench.servicos import instaladores as inst
from itc_bench.servicos.cadastros import Cadastros, Instalador

CONTEUDO = b"instalador ficticio " * 1000
SHA = hashlib.sha256(CONTEUDO).hexdigest()
LINK = "https://downloads.exemplo.invalid/programa-1.0.msi"


def linha(
    id_: int = 7,
    sha: str = SHA,
    arquivo: str = "programa-1.0.msi",
    link: str = LINK,
    programa: str = "RustDesk",
    versao: str = "1.0",
) -> Instalador:
    return Instalador(id_, programa, versao, arquivo, sha, link, "")


def cadastros(*linhas: Instalador) -> Cadastros:
    return Cadastros("v" * 64, datetime.now(UTC), "teste", None, False, (), linhas, (), ())


def abrir_fixo(dados: bytes = CONTEUDO):
    pedidos: list[str] = []

    def abrir(url: str) -> io.BytesIO:
        pedidos.append(url)
        return io.BytesIO(dados)

    return abrir, pedidos


def test_validar_aceita_linha_boa() -> None:
    assert inst.validar(linha(), ".msi") is None


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("sha", "abc", "SHA-256"),
        ("arquivo", "programa.exe", ".msi"),
        ("link", "http://downloads.exemplo.invalid/p.msi", "https"),
        ("versao", " ", "versão"),
    ],
)
def test_validar_recusa(campo: str, valor: str, trecho: str) -> None:
    assert trecho in (inst.validar(linha(**{campo: valor}), ".msi") or "")


def test_do_cadastro_ausente_duplicado_e_sem_cadastros() -> None:
    assert "Sem cadastros" in str(inst.do_cadastro(None, "RustDesk"))
    assert "Cadastre" in str(inst.do_cadastro(cadastros(), "RustDesk"))
    assert "mais de uma" in str(inst.do_cadastro(cadastros(linha(1), linha(2)), "RustDesk"))
    assert inst.do_cadastro(cadastros(linha()), "RustDesk") == linha()


def test_obter_baixa_confere_e_nomeia_pelo_hash(tmp_path: Path, caplog) -> None:
    abrir, pedidos = abrir_fixo()
    caplog.set_level(logging.INFO)
    caminho = inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir)
    assert caminho == tmp_path / f"{SHA}.msi"
    assert caminho.read_bytes() == CONTEUDO
    assert pedidos == [LINK]
    assert not list(tmp_path.glob("*.parcial"))
    assert "exemplo.invalid" not in caplog.text  # o Link nunca vai ao log


def test_obter_reaproveita_guardado_sem_baixar(tmp_path: Path) -> None:
    (tmp_path / f"{SHA}.msi").write_bytes(CONTEUDO)
    abrir, pedidos = abrir_fixo()
    inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir)
    assert pedidos == []


def test_obter_rebaixa_guardado_adulterado(tmp_path: Path) -> None:
    (tmp_path / f"{SHA}.msi").write_bytes(b"trocado")
    abrir, pedidos = abrir_fixo()
    assert inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir).read_bytes() == CONTEUDO
    assert pedidos == [LINK]


def test_sha_errado_apaga_e_recusa(tmp_path: Path, caplog) -> None:
    abrir, _ = abrir_fixo(b"outro conteudo")
    with pytest.raises(inst.ErroInstalador, match="SHA-256"):
        inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir)
    assert list(tmp_path.iterdir()) == []
    assert SHA[:12] in caplog.text and SHA not in caplog.text


def test_sem_rede_sugere_escolher_arquivo(tmp_path: Path) -> None:
    def abrir(_url: str) -> io.BytesIO:
        raise OSError("sem rede")

    with pytest.raises(inst.ErroInstalador, match="Escolher arquivo"):
        inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir)


def test_cancelar_no_meio_nao_deixa_arquivo(tmp_path: Path) -> None:
    cancelar = threading.Event()
    cancelar.set()
    abrir, _ = abrir_fixo()
    with pytest.raises(inst.Cancelado):
        inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir, cancelar=cancelar)
    assert list(tmp_path.iterdir()) == []


def test_teto_de_tamanho(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(inst, "TETO", 10)
    abrir, _ = abrir_fixo()
    with pytest.raises(inst.ErroInstalador, match="300 MB"):
        inst.obter(linha(), ".msi", base=tmp_path, abrir=abrir)
    assert list(tmp_path.iterdir()) == []


def test_copiar_calcula_hash_sobre_a_copia(tmp_path: Path) -> None:
    origem = tmp_path / "pendrive.msi"
    origem.write_bytes(CONTEUDO)
    base = tmp_path / "protegido"
    caminho = inst.copiar(linha(), ".msi", origem, base=base)
    assert caminho.read_bytes() == CONTEUDO and caminho.parent == base


def test_copiar_arquivo_errado_recusa(tmp_path: Path) -> None:
    origem = tmp_path / "pendrive.msi"
    origem.write_bytes(b"outro")
    base = tmp_path / "protegido"
    with pytest.raises(inst.ErroInstalador, match="SHA-256"):
        inst.copiar(linha(), ".msi", origem, base=base)
    assert list(base.iterdir()) == []


def test_conferir(tmp_path: Path) -> None:
    arquivo = tmp_path / "x"
    arquivo.write_bytes(CONTEUDO)
    assert inst.conferir(arquivo, SHA.upper())
    assert not inst.conferir(arquivo, "0" * 64)
    assert not inst.conferir(tmp_path / "nao-existe", SHA)


def test_limpar_usa_todas_as_linhas_ativas(tmp_path: Path) -> None:
    outro = "b" * 64  # linha de outro programa (Módulo 10)
    for nome in (f"{SHA}.msi", f"{outro}.exe", f"{'c' * 64}.msi", f"{SHA}.msi.parcial"):
        (tmp_path / nome).write_bytes(b"x")
    apagados = inst.limpar(cadastros(linha(), linha(8, sha=outro, programa="Outro")), tmp_path)
    assert sorted(apagados) == sorted([f"{'c' * 64}.msi", f"{SHA}.msi.parcial"])
    assert (tmp_path / f"{outro}.exe").exists()


def test_limpar_sem_cadastros_nao_apaga(tmp_path: Path) -> None:
    (tmp_path / f"{'c' * 64}.msi").write_bytes(b"x")
    assert inst.limpar(None, tmp_path) == []
    assert len(list(tmp_path.iterdir())) == 1


def test_redirecionamento_para_http_recusado() -> None:
    with pytest.raises(inst.ErroInstalador, match="https"):
        inst._SoHttps().redirect_request(None, None, 302, "", {}, "http://x.exemplo.invalid/a")


def test_do_cadastro_ignora_winget_e_webapp_com_o_mesmo_nome() -> None:
    """ADR-020: só `Tipo = instalador` serve ao Acesso remoto."""
    from dataclasses import replace

    winget = replace(linha(2), tipo="winget", identificador="Exemplo.Pacote")
    webapp = replace(linha(3), tipo="webapp", identificador="https://exemplo.invalid")
    assert inst.do_cadastro(cadastros(linha(), winget, webapp), "RustDesk") == linha()
    assert "Cadastre" in str(inst.do_cadastro(cadastros(winget), "RustDesk"))


def test_icone_sem_versao_e_valido() -> None:
    from dataclasses import replace

    icone = replace(linha(arquivo="jogo.ico", versao=""), tipo="webapp")
    assert inst.validar(icone, ".ico") is None
    assert "versão" in str(inst.validar(linha(versao=""), ".msi"))


def test_limpar_sem_base_trata_instaladores_e_icones(tmp_path: Path, monkeypatch) -> None:
    pastas = tmp_path / "instaladores", tmp_path / "icones"
    for p in pastas:
        p.mkdir()
        (p / f"{'c' * 64}.ico").write_bytes(b"x")
        (p / f"{SHA}.ico").write_bytes(b"x")
    monkeypatch.setattr(inst, "pasta", lambda: pastas[0])
    monkeypatch.setattr(inst, "icones", lambda: pastas[1])
    assert len(inst.limpar(cadastros(linha()))) == 2
    assert all((p / f"{SHA}.ico").exists() for p in pastas)
