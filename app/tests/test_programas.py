"""Programas (ADR-020): lista, validação, detecção, winget, Web Apps e lote. Só dados fictícios."""

import hashlib
import json
import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from itc_bench.servicos import executor, instaladores
from itc_bench.servicos import programas as pg
from itc_bench.servicos.cadastros import Cadastros, Instalador

CONTEUDO = b"instalador ficticio"
SHA = hashlib.sha256(CONTEUDO).hexdigest()
LINK = "https://downloads.exemplo.invalid/p.msi"
URL = "https://jogos.exemplo.invalid/jogo?x=1"


def inst(id_=1, programa="Editor", arquivo="editor.msi", **kw) -> Instalador:
    base = Instalador(id_, programa, "2.0", arquivo, SHA, LINK, "")
    return replace(base, **kw)


def winget(id_=2, pacote="Exemplo.Pacote", **kw) -> Instalador:
    return replace(
        inst(id_, "Pacote", "", sha256="", link=""), tipo="winget", identificador=pacote, **kw
    )


def webapp(id_=3, **kw) -> Instalador:
    linha = replace(inst(id_, "Jogo", "", sha256="", link="", versao=""), tipo="webapp")
    return replace(linha, **{"identificador": URL, **kw})


def cadastros(*linhas: Instalador) -> Cadastros:
    return Cadastros("v" * 64, datetime.now(UTC), "teste", None, False, (), linhas, (), ())


@pytest.fixture(autouse=True)
def sem_rede_real(monkeypatch):
    """Nenhum teste fala com a rede: download sem o abridor falso falha como sem rede."""

    def recusar(_url, **_k):
        raise OSError("rede desligada nos testes")

    monkeypatch.setattr(instaladores, "_abridor", type("A", (), {"open": staticmethod(recusar)}))


def res(codigo=0, saida="", esgotado=False) -> executor.Resultado:
    return executor.Resultado(None if esgotado else codigo, saida, "", 0.1, esgotado)


# ---------------------------------------------------------------- lista e validação


def test_argumentos_um_por_linha_e_validados() -> None:
    assert pg.argumentos(inst(argumentos="ALLUSERS=1\n\n  NOICON=1 ")) == ["ALLUSERS=1", "NOICON=1"]
    exe = inst(arquivo="setup.exe", argumentos="/S\n--silent\n/D={x}")
    assert pg.argumentos(exe) == ["/S", "--silent", "/D={x}"]
    for ruim in ("/S & calc", '"/S"', "/D=C:\\x", "a b", "%TEMP%", "x|y"):
        with pytest.raises(pg.ErroPrograma):
            pg.argumentos(inst(arquivo="setup.exe", argumentos=ruim))
    with pytest.raises(pg.ErroPrograma, match="PROPRIEDADE"):
        pg.argumentos(inst(argumentos="/quiet"))  # MSI: só PROPRIEDADE=valor


def test_exe_sem_argumentos_e_interativo() -> None:
    assert pg.Item(inst(arquivo="setup.exe")).interativo
    assert not pg.Item(inst(arquivo="setup.exe", argumentos="/S")).interativo
    assert not pg.Item(inst()).interativo


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Jogo: X?", "Jogo X.lnk"),
        ("COM1", None),
        ("nul.txt", None),
        ("a. ", "a.lnk"),
        ("..\\..\\x", None),
        ("  ", None),
        ("x" * 80, "x" * 60 + ".lnk"),
    ],
)
def test_nome_atalho(nome, esperado) -> None:
    assert pg.nome_atalho(nome) == esperado


def test_url_e_modo_do_webapp() -> None:
    assert pg.validar(webapp()) == ""
    for url in ("http://x.exemplo.invalid", "https://x/a b", 'https://x/"', "https://"):
        assert "https" in pg.validar(webapp(identificador=url))
    assert "Modo" in pg.validar(webapp(modo="tela"))
    assert pg.argumentos_webapp(webapp()) == [
        "--kiosk",
        URL,
        "--edge-kiosk-type=fullscreen",
        "--no-first-run",
    ]
    assert pg.argumentos_webapp(webapp(modo="app")) == [f"--app={URL}", "--no-first-run"]


def test_icone_do_webapp_exige_hash_e_ico() -> None:
    com = webapp(link="https://x.exemplo.invalid/i.ico", sha256=SHA, arquivo="i.ico")
    assert pg.validar(com) == ""
    assert "SHA-256" in pg.validar(replace(com, sha256="x"))
    assert ".ico" in pg.validar(replace(com, arquivo="i.png"))


def test_listar_tira_acesso_remoto_e_marca_duplicados() -> None:
    linhas = (
        inst(1),
        inst(2, "RustDesk"),  # Acesso remoto: fora
        winget(3),
        winget(4, pacote="exemplo.PACOTE"),  # mesmo ID: duplicado
        webapp(5),
        winget(6, pacote="id com espaço"),
        inst(7, "Papel", "papel.jpg", tipo="papel"),  # papel de parede: fora (ADR-022)
    )
    itens = {i.id: i for i in pg.listar(cadastros(*linhas))}
    assert set(itens) == {1, 3, 4, 5, 6}
    assert itens[1].bloqueio == "" and itens[5].bloqueio == ""
    assert "duplicado" in itens[3].bloqueio and "duplicado" in itens[4].bloqueio
    assert "inválido" in itens[6].bloqueio
    assert pg.listar(None) == []


# ---------------------------------------------------------------- detecção


def instalado(nome, ver, chave="X"):
    return pg.Instalado(chave, nome, ver, False)


@pytest.mark.parametrize(
    ("lista", "esperado"),
    [
        ([], "nao_instalado"),
        ([instalado("Editor 2", "2.0")], "instalado"),
        ([instalado("Editor", "1.9.9")], "desatualizado"),
        ([instalado("Editor", "v 10.0")], "mais_novo"),
        ([instalado("editor x64", "texto")], "desatualizado"),  # ilegível: por cima
        ([instalado("Editor A", "1"), instalado("Editor B", "2")], "ambiguo"),
        ([instalado("Outro Editor", "2.0")], "nao_instalado"),
    ],
)
def test_detectar_por_prefixo(lista, esperado) -> None:
    assert pg.detectar_registro(pg.Item(inst()), lista, None).situacao == esperado


def test_deteccao_substitui_o_programa() -> None:
    item = pg.Item(inst(deteccao="Nome no Windows"))
    lista = [instalado("Nome no Windows 2.0", "2.0")]
    assert pg.detectar_registro(item, lista, None).situacao == "instalado"


def test_msi_pelo_product_code() -> None:
    codigo = "{11111111-2222-3333-4444-555555555555}"
    lista = [instalado("Nome qualquer", "2.0", codigo.lower())]
    assert pg.detectar_registro(pg.Item(inst()), lista, codigo).situacao == "instalado"
    assert pg.detectar_registro(pg.Item(inst()), [], codigo).situacao == "nao_instalado"


# ---------------------------------------------------------------- winget


def test_comando_winget_fixo() -> None:
    cmd = pg.comando_winget(Path("C:/w/winget.exe"), "Exemplo.Pacote")
    assert cmd[1:5] == ["install", "--id", "Exemplo.Pacote", "-e"]
    assert cmd[5:7] == ["--source", "winget"] and cmd[7:9] == ["--scope", "machine"]
    assert "--force" not in cmd and "--ignore-security-hash" not in cmd


def test_winget_confere_pasta_e_assinatura(monkeypatch) -> None:
    monkeypatch.setattr(pg.remoto, "program_files", lambda: Path("C:/Program Files"))
    dentro = "C:/Program Files/WindowsApps/Microsoft.DesktopAppInstaller_x/winget.exe"

    def rodar(saida):
        return lambda *_a, **_k: res(0, json.dumps(saida))

    ok = {"caminho": dentro, "valida": True, "microsoft": True}
    assert isinstance(pg.winget(rodar=rodar(ok)), Path)
    assert "indisponível" in str(pg.winget(rodar=rodar({})))
    assert "assinatura" in str(pg.winget(rodar=rodar({**ok, "microsoft": False})))
    fora = {**ok, "caminho": "C:/Users/x/AppData/Local/Microsoft/WindowsApps/winget.exe"}
    assert "fora" in str(pg.winget(rodar=rodar(fora)))


def test_winget_export_le_json_e_apaga(tmp_path) -> None:
    gravados = []

    def executar(args, **_k):
        destino = Path(args[args.index("-o") + 1])
        gravados.append(destino)
        corpo = {
            "Sources": [{"Packages": [{"PackageIdentifier": "Exemplo.Pacote", "Version": "3.1"}]}]
        }
        destino.write_text(json.dumps(corpo), "utf-8")
        return res(0)

    assert pg.winget_instalados(Path("C:/w.exe"), executar=executar) == {"exemplo.pacote": "3.1"}
    assert not gravados[0].exists()


# ---------------------------------------------------------------- lote


@pytest.fixture
def guardado(tmp_path, monkeypatch):
    """Instalador já guardado e conferido em pasta temporária."""
    monkeypatch.setattr(instaladores, "pasta", lambda: tmp_path)
    for ext in (".msi", ".exe"):
        (tmp_path / f"{SHA}{ext}").write_bytes(CONTEUDO)
    return tmp_path


def gravador(*codigos, esgotado=False):
    chamadas = []
    fila = list(codigos)

    def executar(args, **k):
        chamadas.append((args, k))
        return res(fila.pop(0) if fila else 0, esgotado=esgotado and len(chamadas) == 1)

    return executar, chamadas


def test_msi_monta_lista_sem_matar_no_timeout(guardado, caplog) -> None:
    caplog.set_level(logging.INFO)
    executar, chamadas = gravador(0)
    r = pg.instalar([pg.Item(inst(argumentos="ALLUSERS=1"))], executar=executar)
    assert r[0].estado == "ok"
    args, k = chamadas[0]
    assert args[0].lower().endswith("msiexec.exe")
    assert args[1:] == ["/i", str(guardado / f"{SHA}.msi"), "/qn", "/norestart", "ALLUSERS=1"]
    assert k["encerrar_no_timeout"] is False and "cancelar" not in k
    assert LINK not in caplog.text and str(guardado) not in k["descricao"]


@pytest.mark.parametrize(
    ("codigo", "estado"), [(3010, "reinicio"), (1641, "reinicio"), (1618, "falha"), (1603, "falha")]
)
def test_codigos_do_msiexec(guardado, codigo, estado) -> None:
    executar, _ = gravador(codigo)
    r = pg.instalar([pg.Item(inst())], executar=executar)[0]
    assert r.estado == estado
    if codigo == 1618:
        assert "Outra instalação" in r.mensagem


def test_exe_com_argumentos_e_codigos(guardado) -> None:
    executar, chamadas = gravador(0, 3010, 5)
    itens = [pg.Item(inst(i, f"P{i}", "setup.exe", argumentos="/S")) for i in (1, 2, 3)]
    estados = [r.estado for r in pg.instalar(itens, executar=executar)]
    assert estados == ["ok", "reinicio", "falha"]
    assert chamadas[0][0] == [str(guardado / f"{SHA}.exe"), "/S"]


def test_sha_errado_antes_de_executar(guardado) -> None:
    (guardado / f"{SHA}.msi").write_bytes(b"trocado")
    executar, chamadas = gravador(0)
    r = pg.instalar([pg.Item(inst())], executar=executar, rodar=lambda *a, **k: res(1))
    # O arquivo trocado não é reaproveitado: tenta baixar (falso aqui) e não executa nada.
    assert r[0].estado == "falha" and chamadas == []


def test_sem_rede_e_sem_arquivo(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(instaladores, "pasta", lambda: tmp_path)

    def sem_rede(_url, **_k):
        raise OSError("sem rede")

    monkeypatch.setattr(instaladores, "_abridor", type("A", (), {"open": staticmethod(sem_rede)}))
    executar, chamadas = gravador(0)
    r = pg.instalar([pg.Item(inst())], executar=executar)[0]
    assert r.estado == "falha" and "Escolher arquivo" in r.mensagem and chamadas == []


def test_arquivo_escolhido_sem_rede(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(instaladores, "pasta", lambda: tmp_path / "guardados")
    origem = tmp_path / "pendrive.msi"
    origem.write_bytes(CONTEUDO)
    executar, chamadas = gravador(0)
    r = pg.instalar([pg.Item(inst())], origens={1: origem}, executar=executar)[0]
    assert r.estado == "ok" and str(origem) not in chamadas[0][0]


def test_um_falha_os_outros_seguem(guardado, monkeypatch) -> None:
    monkeypatch.setattr(pg, "winget", lambda **_k: Path("C:/w/winget.exe"))
    executar, _ = gravador(1603, 0)
    r = pg.instalar([pg.Item(winget()), pg.Item(inst())], executar=executar)
    assert [(x.item.tipo, x.estado) for x in r] == [("instalador", "falha"), ("winget", "ok")]


def test_timeout_pula_instaladores_e_winget_mas_segue_webapp(guardado, monkeypatch) -> None:
    monkeypatch.setattr(pg, "winget", lambda **_k: Path("C:/w/winget.exe"))
    monkeypatch.setattr(pg, "_webapp", lambda item, **_k: pg.Resultado(item, "ok", "ok"))
    executar, chamadas = gravador(esgotado=True)
    itens = [pg.Item(inst(1)), pg.Item(inst(2, "Outro")), pg.Item(winget()), pg.Item(webapp())]
    estados = [r.estado for r in pg.instalar(itens, executar=executar)]
    assert estados == ["em_execucao", "pulado", "pulado", "ok"]
    assert len(chamadas) == 1


def test_cancelar_entre_itens(guardado) -> None:
    cancelar = threading.Event()

    def executar(args, **k):
        cancelar.set()  # o técnico cancela durante o primeiro
        return res(0)

    itens = [pg.Item(inst(1)), pg.Item(inst(2, "Outro"))]
    r = pg.instalar(itens, executar=executar, cancelar=cancelar)
    assert [x.estado for x in r] == ["ok", "cancelado"]


@pytest.mark.parametrize(
    ("codigo", "estado", "trecho"),
    [
        (0, "ok", "instalado"),
        (0x8A150109, "reinicio", "Reinicie"),
        (0x8A150014, "falha", "não existe"),
        (0x8A150010, "falha", "escopo de máquina"),
        (0x8A150045, "falha", "rede"),
        (0x8A15FFFF, "falha", "0x8a15ffff"),
    ],
)
def test_codigos_do_winget(monkeypatch, codigo, estado, trecho) -> None:
    monkeypatch.setattr(pg, "winget", lambda **_k: Path("C:/w/winget.exe"))
    # O Windows devolve o HRESULT com sinal; o Bench normaliza.
    assinado = codigo - (1 << 32) if codigo >= 1 << 31 else codigo
    executar, chamadas = gravador(assinado)
    r = pg.instalar([pg.Item(winget())], executar=executar)[0]
    assert r.estado == estado and trecho in r.mensagem
    assert chamadas[0][1]["timeout"] == pg.TIMEOUT_WINGET
    assert chamadas[0][1]["encerrar_no_timeout"] is False


def test_winget_ausente_falha_so_os_itens_winget(monkeypatch, guardado) -> None:
    monkeypatch.setattr(pg, "winget", lambda **_k: "winget indisponível neste Windows.")
    executar, _ = gravador(0)
    r = pg.instalar([pg.Item(winget()), pg.Item(inst())], executar=executar)
    assert [x.estado for x in r] == ["ok", "falha"]


def test_bloqueado_nao_executa(guardado) -> None:
    executar, chamadas = gravador(0)
    r = pg.instalar([pg.Item(inst(), "Cadastro duplicado.")], executar=executar)
    assert r[0].estado == "pulado" and chamadas == []


# ---------------------------------------------------------------- Web Apps


def test_webapp_cria_atalho_por_variaveis(monkeypatch, tmp_path, caplog) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        pg, "edge", lambda: Path("C:/Program Files (x86)/Microsoft/Edge/msedge.exe")
    )
    monkeypatch.setattr(pg, "area_publica", lambda: tmp_path)
    chamadas = []

    def rodar(script, **k):
        chamadas.append(k)
        return res(0, "[]" if k["acao"] == "listar" else "OK")

    r = pg.instalar([pg.Item(webapp())], rodar=rodar)[0]
    assert r.estado == "ok"
    criar = chamadas[-1]
    assert criar["acao"] == "criar" and criar["nome"] == "Jogo.lnk"
    assert criar["argumentos"] == f"--kiosk {URL} --edge-kiosk-type=fullscreen --no-first-run"
    assert criar["icone"] == ""
    assert URL not in caplog.text


def test_webapp_nao_sobrescreve_atalho_alheio(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pg, "edge", lambda: Path("C:/Program Files/Edge/msedge.exe"))
    monkeypatch.setattr(pg, "area_publica", lambda: tmp_path)

    def rodar(script, **k):
        return res(0, json.dumps([{"nome": "Jogo.lnk", "descricao": "Outro"}]))

    r = pg.instalar([pg.Item(webapp())], rodar=rodar)[0]
    assert r.estado == "falha" and "não é do Bench" in r.mensagem


def test_webapp_sem_edge(monkeypatch) -> None:
    monkeypatch.setattr(pg, "edge", lambda: None)
    r = pg.instalar([pg.Item(webapp())], rodar=lambda *a, **k: res(0, "[]"))[0]
    assert r.estado == "falha" and "Edge" in r.mensagem


def test_webapp_com_icone_baixa_com_hash_e_protege_pasta(monkeypatch, tmp_path) -> None:
    import io

    monkeypatch.setattr(pg, "edge", lambda: Path("C:/Program Files/Edge/msedge.exe"))
    monkeypatch.setattr(pg, "area_publica", lambda: tmp_path / "desktop")
    monkeypatch.setattr(instaladores, "icones", lambda: tmp_path / "icones")
    abridor = type("A", (), {"open": staticmethod(lambda _u, **_k: io.BytesIO(CONTEUDO))})
    monkeypatch.setattr(instaladores, "_abridor", abridor)
    protegidas = []
    monkeypatch.setattr(pg.acl, "proteger", lambda p, sddl: protegidas.append((p, sddl)))
    chamadas = []

    def rodar(script, **k):
        chamadas.append(k)
        return res(0, "[]" if k["acao"] == "listar" else "OK")

    linha = webapp(link="https://x.exemplo.invalid/i.ico", sha256=SHA, arquivo="i.ico")
    assert pg.instalar([pg.Item(linha)], rodar=rodar)[0].estado == "ok"
    assert chamadas[-1]["icone"] == str(tmp_path / "icones" / f"{SHA}.ico")
    assert protegidas == [(tmp_path / "icones", pg.acl.SDDL)]


def test_situacao_mistura_tipos(monkeypatch) -> None:
    monkeypatch.setattr(pg, "winget", lambda **_k: Path("C:/w/winget.exe"))
    monkeypatch.setattr(pg, "winget_instalados", lambda *_a, **_k: {"exemplo.pacote": "1.0"})
    monkeypatch.setattr(pg, "atalhos", lambda **_k: {"Jogo.lnk": pg.DESCRICAO_ATALHO})
    itens = [pg.Item(inst()), pg.Item(winget(versao="2.0")), pg.Item(webapp())]
    linhas, sem = pg.situacao(itens, ler_registro=lambda: [instalado("Editor", "2.0")])
    assert sem == ""
    assert [x.situacao for x in linhas] == ["instalado", "desatualizado", "instalado"]


def test_resumo() -> None:
    item = pg.Item(inst())
    rs = [pg.Resultado(item, e, "") for e in ("ok", "ok", "falha", "em_execucao")]
    assert pg.resumo(r.estado for r in rs) == "2 ok, 1 com falha, 1 ainda em execução"
