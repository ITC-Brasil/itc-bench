"""Acesso remoto (ADR-019): cadastro, versão, TOML, senha fora de argumento e do log, msiexec.

Só dados fictícios (`*.exemplo.invalid`, chaves e senhas de teste). Nada é instalado: o executor
é falso. O PowerShell real só roda na leitura dos serviços (Windows).
"""

import base64
import hashlib
import logging
import sys
import threading
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from itc_bench.servicos import executor, remoto
from itc_bench.servicos.cadastros import Cadastros, Instalador, Servidor, Unidade
from itc_bench.servicos.executor import Resultado, Sensivel

SENHA_RD = "Marcador-RustDesk-7f3a!"
SENHA_AD = "Marcador-AnyDesk-41be!"
CHAVE = base64.b64encode(b"k" * 32).decode()
HOST = "rd.exemplo.invalid"
URL = "https://glpi.exemplo.invalid/front/inventory.php"
CONTEUDO = b"instalador ficticio"
SHA = hashlib.sha256(CONTEUDO).hexdigest()


def srv(id_: int, servico: str, papel: str, valor: str, publico: bool) -> Servidor:
    v: str | Sensivel = valor if publico else Sensivel(valor)
    return Servidor(id_, servico, papel, v, "", "" if publico else Sensivel(""), publico)


def servidores_ok() -> list[Servidor]:
    return [
        srv(1, "GLPI Agent", "servidor", URL, True),
        srv(2, "RustDesk", "servidor", HOST, True),
        srv(3, "RustDesk", "chave", CHAVE, False),
        srv(4, "RustDesk", "senha", SENHA_RD, False),
        srv(5, "AnyDesk", "senha", SENHA_AD, False),
    ]


def instaladores_ok() -> list[Instalador]:
    link = "https://downloads.exemplo.invalid/"
    return [
        Instalador(11, "GLPI Agent", "1.15", "glpi.msi", SHA, link + "g.msi", ""),
        Instalador(12, "RustDesk", "1.4.5", "rd.msi", SHA, link + "r.msi", ""),
        Instalador(13, "AnyDesk", "8.0.14", "AnyDesk.exe", SHA, link + "a.exe", ""),
    ]


def cad(servidores=None, inst=None, tag: str = "TAG-TESTE") -> Cadastros:
    unidades = (Unidade(1, "ABC01", "Teste", "Cidade", "UF", tag, ""),)
    return Cadastros(
        "v" * 64,
        datetime.now(UTC),
        "teste",
        None,
        False,
        tuple(servidores_ok() if servidores is None else servidores),
        tuple(instaladores_ok() if inst is None else inst),
        (),
        unidades,
    )


def res(codigo: int | None = 0, saida: str = "OK", cancelado: bool = False) -> Resultado:
    return Resultado(
        codigo=codigo, saida=saida, erros="", duracao=0.1, esgotado=False, cancelado=cancelado
    )


class Gravador:
    """Executor falso: guarda argumentos, ambiente e entrada de cada chamada."""

    def __init__(self, codigos: dict[str, int] | None = None, efeito=None) -> None:
        self.chamadas: list[dict] = []
        self.codigos = codigos or {}
        self.efeito = efeito

    def executar(self, argumentos, **kw) -> Resultado:
        self.chamadas.append({"args": list(argumentos), **kw})
        nome = Path(argumentos[0]).name.lower()
        return res(self.codigos.get(nome, 0), saida="123 456 789")

    def rodar(self, script: str, **kw) -> Resultado:
        self.chamadas.append({"script": script[:40], **kw})
        if self.efeito:
            self.efeito(kw)
        return res()

    def tudo(self) -> str:
        return repr(self.chamadas)


@pytest.fixture
def arquivo(tmp_path: Path) -> Path:
    a = tmp_path / f"{SHA}.msi"
    a.write_bytes(CONTEUDO)
    return a


# ---------------------------------------------------------------- cadastro


def test_dados_completos() -> None:
    c = cad()
    g = remoto.dados(c, "GLPI Agent", "ABC01")
    assert isinstance(g, remoto.Dados) and g.servidor == URL and g.tag == "TAG-TESTE"
    r = remoto.dados(c, "RustDesk")
    assert isinstance(r, remoto.Dados) and r.servidor == HOST
    assert repr(r.senha) == "***" and repr(r.chave) == "***"
    assert isinstance(remoto.dados(c, "AnyDesk"), remoto.Dados)


def test_tag_opcional_sem_unidade_ou_vazia() -> None:
    assert remoto.dados(cad(), "GLPI Agent", None).tag == ""  # type: ignore[union-attr]
    assert remoto.dados(cad(tag=""), "GLPI Agent", "ABC01").tag == ""  # type: ignore[union-attr]
    assert "aspas" in str(remoto.dados(cad(tag='a"b'), "GLPI Agent", "ABC01"))


def test_glpi_http_aceito_com_aviso() -> None:
    s = [srv(1, "GLPI Agent", "servidor", "http://glpi.exemplo.invalid:8888/", True)]
    d = remoto.dados(cad(servidores=s), "GLPI Agent")
    assert isinstance(d, remoto.Dados) and "http://" in d.avisos[0]


@pytest.mark.parametrize(
    ("servidores", "programa", "trecho"),
    [
        ([], "RustDesk", "Cadastre “RustDesk” / servidor (pública)"),
        ([srv(2, "RustDesk", "servidor", "  ", True)], "RustDesk", "vazia"),
        (
            [
                srv(2, "RustDesk", "servidor", HOST, True),
                srv(9, "RustDesk", "servidor", HOST, True),
            ],
            "RustDesk",
            "mais de uma",
        ),
        ([srv(5, "AnyDesk", "senha", SENHA_AD, True)], "AnyDesk", "não pública"),
        ([srv(2, "RustDesk", "servidor", HOST, False)], "RustDesk", "tem que ser pública"),
        ([srv(2, "RustDesk", "servidor", HOST + ":21116", True)], "RustDesk", "sem porta"),
        ([srv(1, "GLPI Agent", "servidor", "ftp://x.exemplo.invalid", True)], "GLPI Agent", "http"),
        ([srv(1, "GLPI Agent", "servidor", URL + " x", True)], "GLPI Agent", "espaço"),
    ],
)
def test_dados_recusa(servidores, programa, trecho) -> None:
    resto = [s for s in servidores_ok() if s.servico != programa]
    motivo = remoto.dados(cad(servidores=resto + servidores), programa)
    assert isinstance(motivo, str) and trecho in motivo


def test_chave_invalida_e_sem_instalador() -> None:
    s = [x for x in servidores_ok() if x.papel != "chave"] + [
        srv(3, "RustDesk", "chave", "curta", False)
    ]
    assert "chave" in str(remoto.dados(cad(servidores=s), "RustDesk"))
    assert "Instaladores" in str(remoto.dados(cad(inst=[]), "AnyDesk"))
    assert "Sem cadastros" in str(remoto.dados(None, "AnyDesk"))


# ---------------------------------------------------------------- versão


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("ad 8.0.14", (8, 0, 14)), ("1.4.5", (1, 4, 5)), ("v1.10", (1, 10)), ("sem", None)],
)
def test_versao(texto, esperado) -> None:
    assert remoto.versao(texto) == esperado


@pytest.mark.parametrize(
    ("instalada", "cadastro", "esperado"),
    [
        (None, "1.4.5", "ausente"),
        ("1.4.4", "1.4.5", "velha"),
        ("1.10.0", "1.4.5", "nova"),  # o defeito do Configurador: texto dava "velha"
        ("ad 8.0.14", "8.0.14", "igual"),
        ("1.4", "1.4.0", "igual"),
        ("lixo", "1.0", "velha"),
    ],
)
def test_comparar(instalada, cadastro, esperado) -> None:
    assert remoto.comparar(instalada, cadastro) == esperado


# ---------------------------------------------------------------- TOML


def test_rustdesk2_preserva_outras_opcoes_e_escapa() -> None:
    existente = '"rendezvous_server" = "velho:21116"\n[options]\nallow-x = "Y"\nkey = "velha"\n'
    texto = remoto.rustdesk2(existente, HOST, CHAVE)
    lido = tomllib.loads(texto)
    assert lido["rendezvous_server"] == f"{HOST}:21116"
    assert lido["options"]["allow-x"] == "Y"
    assert lido["options"]["key"] == CHAVE
    assert lido["options"]["custom-rendezvous-server"] == HOST


def test_toml_texto_hostil_round_trip() -> None:
    hostil = "a'b\"c\\d\n]]>\x01ç"
    assert tomllib.loads(f"x = {remoto.toml_texto(hostil)}")["x"] == hostil


def test_com_senha_troca_so_a_linha_e_preserva_id() -> None:
    existente = "id = '123'\npassword = '00velha'\nsalt = 'abc'\n[options]\npassword = 'nao-mexe'\n"
    texto = remoto.com_senha(existente, SENHA_RD)
    lido = tomllib.loads(texto)
    assert lido["password"] == SENHA_RD and lido["id"] == "123" and lido["salt"] == "abc"
    assert lido["options"]["password"] == "nao-mexe"  # noqa: S105 — fictício
    assert "password" not in tomllib.loads(remoto.com_senha(texto, None))


def test_senha_cifrada() -> None:
    assert remoto.senha_cifrada("password = '00abcd'\n")
    assert not remoto.senha_cifrada(f"password = '{SENHA_RD}'\n")
    assert not remoto.senha_cifrada("")


def test_gravar_atomico_nao_deixa_tmp(tmp_path: Path, monkeypatch) -> None:
    alvo = tmp_path / "RustDesk.toml"

    def falha(*_a) -> None:
        raise OSError("disco")

    monkeypatch.setattr(Path, "replace", falha)
    with pytest.raises(OSError):
        remoto.gravar_atomico(alvo, f"password = '{SENHA_RD}'")
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- instalação


@pytest.mark.parametrize(
    ("codigo", "ok", "reinicio"), [(0, True, False), (3010, True, True), (1641, True, True)]
)
def test_glpi_msiexec_codigos_de_sucesso(arquivo, codigo, ok, reinicio) -> None:
    g = Gravador({"msiexec.exe": codigo})
    d = remoto.dados(cad(), "GLPI Agent", "ABC01")
    feito = remoto.instalar(d, arquivo, rodar=g.rodar, executar=g.executar)  # type: ignore[arg-type]
    assert (feito.ok, feito.reinicio) == (ok, reinicio)
    args = g.chamadas[0]["args"]
    assert f"SERVER={URL}" in args and "TAG=TAG-TESTE" in args and "/qn" in args


def test_glpi_sem_tag_nao_passa_tag(arquivo) -> None:
    g = Gravador()
    d = remoto.dados(cad(), "GLPI Agent", None)
    remoto.instalar(d, arquivo, rodar=g.rodar, executar=g.executar)  # type: ignore[arg-type]
    assert not any(a.startswith("TAG=") for a in g.chamadas[0]["args"])


@pytest.mark.parametrize(
    ("codigo", "trecho"), [(1618, "Outra instalação"), (1603, "1603"), (5, "5")]
)
def test_msiexec_falhas(arquivo, codigo, trecho) -> None:
    g = Gravador({"msiexec.exe": codigo})
    d = remoto.dados(cad(), "GLPI Agent")
    feito = remoto.instalar(d, arquivo, rodar=g.rodar, executar=g.executar)  # type: ignore[arg-type]
    assert not feito.ok and trecho in feito.mensagem


def test_sha_errado_antes_de_executar(tmp_path) -> None:
    errado = tmp_path / "x.msi"
    errado.write_bytes(b"trocado")
    g = Gravador()
    feito = remoto.instalar(
        remoto.dados(cad(), "GLPI Agent"), errado, rodar=g.rodar, executar=g.executar
    )  # type: ignore[arg-type]
    assert not feito.ok and "SHA-256" in feito.mensagem and g.chamadas == []


def test_anydesk_senha_pela_entrada_nunca_em_argumento(
    arquivo, tmp_path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    pasta = tmp_path / "x86"
    (pasta / "AnyDesk").mkdir(parents=True)
    (pasta / "AnyDesk" / "AnyDesk.exe").write_bytes(b"")
    monkeypatch.setattr(remoto, "program_files_x86", lambda: pasta)
    g = Gravador()
    feito = remoto.instalar(
        remoto.dados(cad(), "AnyDesk"), arquivo, rodar=g.rodar, executar=g.executar
    )  # type: ignore[arg-type]
    assert feito.ok, feito.mensagem
    instalar_args = g.chamadas[0]["args"]
    assert "--start-with-win" in instalar_args and "--create-desktop-icon" not in instalar_args
    senha = [c for c in g.chamadas if c.get("args", [""])[-1] == "--set-password"]
    assert isinstance(senha[0]["entrada"], Sensivel)
    assert senha[0]["entrada"].revelar() == SENHA_AD
    assert all(SENHA_AD not in a for c in g.chamadas for a in c.get("args", []))
    assert SENHA_AD not in caplog.text


def rustdesk_falso(tmp_path, monkeypatch, cifra: bool):
    pasta = tmp_path / "config"
    monkeypatch.setattr(remoto, "windows", lambda: tmp_path)
    monkeypatch.setattr(remoto, "program_files", lambda: tmp_path / "pf")

    def efeito(kw) -> None:
        if kw.get("acao") == "esperar":
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "RustDesk.toml").write_text("id = '987654321'\nsalt = 'abc'\n", "utf-8")
        if kw.get("acao") == "iniciar" and cifra:
            texto = (pasta / "RustDesk.toml").read_text("utf-8")
            if SENHA_RD in texto:  # o RustDesk regrava cifrada
                (pasta / "RustDesk.toml").write_text(
                    remoto.com_senha(texto, "00cifradaTeste"), "utf-8"
                )

    return pasta, Gravador(efeito=efeito)


def test_rustdesk_instala_configura_e_senha_some(arquivo, tmp_path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    pasta, g = rustdesk_falso(tmp_path, monkeypatch, cifra=True)
    d = remoto.dados(cad(), "RustDesk")
    feito = remoto.instalar(d, arquivo, rodar=g.rodar, executar=g.executar, pasta_rustdesk=pasta)  # type: ignore[arg-type]
    assert feito.ok, feito.mensagem
    config = (pasta / "RustDesk.toml").read_text("utf-8")
    assert SENHA_RD not in config and "987654321" in config
    opcoes = tomllib.loads((pasta / "RustDesk2.toml").read_text("utf-8"))["options"]
    assert opcoes["key"] == CHAVE
    assert not list(pasta.glob("*.tmp"))
    assert SENHA_RD not in g.tudo() and CHAVE not in g.tudo()
    for segredo in (SENHA_RD, CHAVE, HOST):
        assert segredo not in caplog.text
    assert all(SENHA_RD not in a and CHAVE not in a for c in g.chamadas for a in c.get("args", []))
    opcoes_cmd = [c["args"][1:] for c in g.chamadas if "--option" in c.get("args", [])]
    assert opcoes_cmd == [
        ["--option", "stop-service-hide-tray", "Y"],
        ["--option", "hide-icon", "Y"],
    ]


def test_rustdesk_senha_nao_cifrada_e_retirada(arquivo, tmp_path, monkeypatch) -> None:
    pasta, g = rustdesk_falso(tmp_path, monkeypatch, cifra=False)
    monkeypatch.setattr(remoto, "ESPERA_CIFRAR", 2)
    monkeypatch.setattr(remoto.time, "sleep", lambda _s: None)
    d = remoto.dados(cad(), "RustDesk")
    feito = remoto.instalar(d, arquivo, rodar=g.rodar, executar=g.executar, pasta_rustdesk=pasta)  # type: ignore[arg-type]
    assert not feito.ok and "retirada" in feito.mensagem
    for item in pasta.iterdir():
        assert SENHA_RD not in item.read_text("utf-8"), item.name


def test_rustdesk_cancelado_na_espera_tira_a_senha(arquivo, tmp_path, monkeypatch) -> None:
    pasta, g = rustdesk_falso(tmp_path, monkeypatch, cifra=False)
    cancelar = threading.Event()
    monkeypatch.setattr(remoto.time, "sleep", lambda _s: cancelar.set())
    d = remoto.dados(cad(), "RustDesk")
    feito = remoto.instalar(
        d, arquivo, cancelar=cancelar, rodar=g.rodar, executar=g.executar, pasta_rustdesk=pasta
    )  # type: ignore[arg-type]
    assert not feito.ok and "Cancelado" in feito.mensagem
    for item in pasta.iterdir():
        assert SENHA_RD not in item.read_text("utf-8"), item.name


def test_cancelar_antes_de_comecar(arquivo) -> None:
    cancelar = threading.Event()
    cancelar.set()
    g = Gravador()
    feito = remoto.instalar(
        remoto.dados(cad(), "GLPI Agent"),
        arquivo,
        cancelar=cancelar,
        rodar=g.rodar,
        executar=g.executar,
    )  # type: ignore[arg-type]
    assert not feito.ok and "Cancelado" in feito.mensagem and g.chamadas == []


def test_servico_que_nao_sobe(arquivo) -> None:
    g = Gravador()
    g.rodar = lambda script, **kw: res(3, "ERRO|tempo|Running")  # type: ignore[method-assign]
    feito = remoto.instalar(
        remoto.dados(cad(), "GLPI Agent"), arquivo, rodar=g.rodar, executar=g.executar
    )  # type: ignore[arg-type]
    assert not feito.ok and "não respondeu" in feito.mensagem


def test_reconfigurar_glpi_tag_vazia_nao_apaga(monkeypatch) -> None:
    gravado: list[tuple[str, str]] = []
    monkeypatch.setattr(remoto, "gravar_glpi_registro", lambda s, t: gravado.append((s, t)))
    g = Gravador()
    feito = remoto.reconfigurar(remoto.dados(cad(tag=""), "GLPI Agent", "ABC01"), rodar=g.rodar)  # type: ignore[arg-type]
    assert feito.ok and gravado == [(URL, "")]  # gravar_glpi_registro ignora tag vazia


def test_forcar_inventario() -> None:
    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_a) -> None:
            return None

    pedidos = []
    assert remoto.forcar_inventario(abrir=lambda url, timeout: pedidos.append(url) or Resp()).ok
    assert pedidos == ["http://127.0.0.1:62354/now"]

    def falha(*_a, **_k):
        raise OSError("recusado")

    assert not remoto.forcar_inventario(abrir=falha).ok


def test_comando_sem_segredo() -> None:
    for programa in remoto.PROGRAMAS:
        texto = remoto.comando(remoto.dados(cad(), programa, "ABC01"))  # type: ignore[arg-type]
        assert SENHA_RD not in texto and SENHA_AD not in texto and CHAVE not in texto


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell real")
def test_leitura_real_dos_servicos() -> None:
    estados = remoto.servicos()
    assert set(estados) == {"glpi-agent", "RustDesk", "AnyDesk"}
    for programa in remoto.PROGRAMAS:
        ver, local = remoto.desinstalacao(programa)
        assert ver is None or isinstance(ver, str)
        assert local is None or not local.startswith('"')  # AnyDesk grava entre aspas
    assert executor.sistema32("msiexec.exe").lower().endswith("msiexec.exe")
