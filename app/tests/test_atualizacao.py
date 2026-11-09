"""Atualização automática (ADR-026): assinatura CNG, manifesto, download, disparo e recusas."""

import base64
import ctypes
import hashlib
import io
import json
import urllib.error
from ctypes import wintypes
from pathlib import Path, PureWindowsPath

import pytest

from itc_bench import __version__
from itc_bench.nucleo import assinatura
from itc_bench.servicos import atualizacao as at
from itc_bench.servicos import executor
from itc_bench.servicos.executor import Sensivel

# Vetor gerado pelo ECDsaCng.SignData do .NET (P1363), chave descartável de teste.
VETOR_PUB = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEAm6+gCw6+nEXCF1Jj0z7vIkJdNJFRxhUeOwCpfPfMbWWAyrXvxOBiqAX"
    "T20+j1t1rhSG0hHowhbxV3KFf2yO7g=="
)
VETOR_MSG = b'{"vetor":"ITC Bench"}'
VETOR_SIG = base64.b64decode(
    "lOh+ZVPLlLKsB1OPuVN2XpQ3TemaoKyJ6Ib5Dkw5zVmjY/pTDneiUx/G5LzQvbkG3Tg/DQbNkeOJ657/JHjTjQ=="
)
TOKEN = Sensivel("itcbs_" + "x" * 43)


class Chave:
    """Par P-256 efêmero pela CNG, só para assinar nos testes."""

    def __init__(self) -> None:
        self.dll = ctypes.WinDLL("bcrypt")
        alg, self.chave = ctypes.c_void_p(), ctypes.c_void_p()
        assert not self.dll.BCryptOpenAlgorithmProvider(ctypes.byref(alg), "ECDSA_P256", None, 0)
        assert not self.dll.BCryptGenerateKeyPair(alg, ctypes.byref(self.chave), 256, 0)
        assert not self.dll.BCryptFinalizeKeyPair(self.chave, 0)
        blob, n = ctypes.create_string_buffer(72), wintypes.ULONG()
        assert not self.dll.BCryptExportKey(
            self.chave, None, "ECCPUBLICBLOB", blob, 72, ctypes.byref(n), 0
        )
        self.xy = blob.raw[8:72]

    def assinar(self, dados: bytes) -> bytes:
        resumo = hashlib.sha256(dados).digest()
        sig, n = ctypes.create_string_buffer(64), wintypes.ULONG()
        assert not self.dll.BCryptSignHash(
            self.chave, None, resumo, 32, sig, 64, ctypes.byref(n), 0
        )
        return sig.raw


CONTEUDO = b"MZ" + b"instalador falso " * 300


def manifesto(versao="99.0.0", conteudo=CONTEUDO, **troca) -> bytes:
    dados = {
        "produto": "itc-bench",
        "app_id": at.APP_ID,
        "versao": versao,
        "minima": "0.1.0",
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "tamanho": len(conteudo),
        "notas": "Notas assinadas.",
        "publicado_em": "2026-11-08T00:00:00Z",
    }
    return json.dumps(dados | troca).encode()


@pytest.fixture(scope="module")
def chave() -> Chave:
    return Chave()


# --- assinatura ---------------------------------------------------------------------------


def test_vetor_do_dotnet_confere():
    assert assinatura.verificar(assinatura.chave_de_texto(VETOR_PUB), VETOR_MSG, VETOR_SIG)


@pytest.mark.parametrize(
    ("msg", "sig"),
    [
        (VETOR_MSG + b" ", VETOR_SIG),  # campo alterado
        (VETOR_MSG, VETOR_SIG[:63]),  # truncada
        (VETOR_MSG, b"\x30\x44\x02\x20" + VETOR_SIG[:32] + b"\x02\x20" + VETOR_SIG[32:]),  # DER
        (VETOR_MSG, bytes(64)),
    ],
)
def test_vetor_recusas(msg, sig):
    assert not assinatura.verificar(assinatura.chave_de_texto(VETOR_PUB), msg, sig)


def test_chave_errada_recusa(chave):
    assert not assinatura.verificar(chave.xy, VETOR_MSG, VETOR_SIG)


@pytest.mark.parametrize("texto", ["não é base64", base64.b64encode(b"\x30" * 91).decode(), ""])
def test_chave_fora_do_formato(texto):
    with pytest.raises(assinatura.ChaveInvalida):
        assinatura.chave_de_texto(texto)


# --- manifesto ----------------------------------------------------------------------------


def test_manifesto_valido(chave):
    cru = manifesto()
    m = at.conferir(cru, chave.assinar(cru), [chave.xy])
    assert m.versao == "99.0.0" and m.notas == "Notas assinadas."


def test_reserva_tambem_vale(chave):
    cru = manifesto()
    outra = Chave()
    assert at.conferir(cru, chave.assinar(cru), [outra.xy, chave.xy]).versao == "99.0.0"


def test_assinatura_antes_do_json(chave):
    with pytest.raises(at.Recusada, match="assinatura"):
        at.conferir(b"{lixo", chave.assinar(b"outra coisa"), [chave.xy])


def test_sem_chave_no_pacote_recusa(chave):
    cru = manifesto()
    with pytest.raises(at.Recusada, match="chave pública"):
        at.conferir(cru, chave.assinar(cru), [])


@pytest.mark.parametrize(
    "troca",
    [
        {"produto": "outro"},
        {"app_id": "{0}"},
        {"versao": "1.0"},
        {"minima": "100.0.0"},
        {"sha256": "A" * 64},
        {"tamanho": 0},
        {"tamanho": 301 * 1024 * 1024},
        {"notas": "\x1b[31m"},
        {"extra": True},
    ],
)
def test_manifesto_assinado_mas_invalido(chave, troca):
    cru = manifesto(**troca)
    with pytest.raises(at.Recusada):
        at.conferir(cru, chave.assinar(cru), [chave.xy])


@pytest.mark.parametrize("instalada", [None, "0.0.1"])
def test_versao_menor_ou_igual_recusada(chave, instalada):
    cru = manifesto(versao=__version__)
    with pytest.raises(at.Recusada, match="não é maior"):
        at._oferta(cru, chave.assinar(cru), [chave.xy], instalada)


def test_displayversion_maior_vale(chave):
    cru = manifesto(versao="98.0.0")
    with pytest.raises(at.Recusada):
        at._oferta(cru, chave.assinar(cru), [chave.xy], "98.0.0")
    assert at._oferta(cru, chave.assinar(cru), [chave.xy], "97.0.0").manifesto.versao == "98.0.0"


def test_obrigatoria_pela_minima(chave):
    cru = manifesto(minima="99.0.0")
    assert at._oferta(cru, chave.assinar(cru), [chave.xy], "0.0.1").obrigatoria
    cru = manifesto()
    assert not at._oferta(cru, chave.assinar(cru), [chave.xy], "0.0.1").obrigatoria


# --- consulta -----------------------------------------------------------------------------


def test_consultar(monkeypatch, chave):
    cru = manifesto()
    corpo = {
        "manifesto": base64.b64encode(cru).decode(),
        "assinatura": base64.b64encode(chave.assinar(cru)).decode(),
    }
    monkeypatch.setattr(at.api, "_chamar", lambda *a, **k: (200, {}, corpo))
    oferta = at.consultar("https://api.exemplo.invalid", TOKEN, [chave.xy], "0.0.1")
    assert oferta is not None and oferta.cru == cru
    monkeypatch.setattr(at.api, "_chamar", lambda *a, **k: (204, {}, None))
    assert at.consultar("https://api.exemplo.invalid", TOKEN, [chave.xy], "0.0.1") is None


def test_consultar_sem_manifesto(monkeypatch, chave):
    monkeypatch.setattr(at.api, "_chamar", lambda *a, **k: (200, {}, {"versao": "99.0.0"}))
    with pytest.raises(at.Recusada):
        at.consultar("https://api.exemplo.invalid", TOKEN, [chave.xy], "0.0.1")


def test_redirecionamento_nao_e_seguido():
    # O download usa o mesmo abridor da API, que devolve o 3xx como erro (ADR-013).
    assert any(isinstance(h, at.api._SemRedirecionar) for h in at.api._abridor.handlers)


# --- download -----------------------------------------------------------------------------


class Resposta(io.BytesIO):
    def __init__(self, dados: bytes, status: int = 200) -> None:
        super().__init__(dados)
        self.status = status


def oferta(chave, conteudo=CONTEUDO, **troca) -> at.Oferta:
    cru = manifesto(conteudo=conteudo, **troca)
    return at._oferta(cru, chave.assinar(cru), [chave.xy], "0.0.1")


def test_baixar_confere_e_guarda_manifesto(tmp_path, chave):
    o = oferta(chave)
    chamadas = []

    def abrir(base, token, sha, inicio):
        chamadas.append(inicio)
        return Resposta(CONTEUDO)

    caminho = at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=abrir)
    assert caminho.read_bytes() == CONTEUDO
    assert caminho.name == f"setup-{o.manifesto.sha256}.exe"
    assert at.guardada(tmp_path, [chave.xy], "0.0.1") == o
    at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=abrir)  # já guardado: não baixa
    assert chamadas == [0]


def test_baixar_retoma_com_range(tmp_path, chave):
    o = oferta(chave)
    (tmp_path / f"setup-{o.manifesto.sha256}.exe.parcial").write_bytes(CONTEUDO[:1000])
    pedidos = []

    def abrir(base, token, sha, inicio):
        pedidos.append(inicio)
        return Resposta(CONTEUDO[inicio:], 206)

    assert at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=abrir).read_bytes() == CONTEUDO
    assert pedidos == [1000]


def test_retomada_sem_206_recomeca(tmp_path, chave):
    o = oferta(chave)
    (tmp_path / f"setup-{o.manifesto.sha256}.exe.parcial").write_bytes(b"lixo" * 10)
    caminho = at.baixar(
        "https://x.invalid", TOKEN, o, tmp_path, abrir=lambda *a: Resposta(CONTEUDO)
    )
    assert caminho.read_bytes() == CONTEUDO


def test_hash_errado_recusa_e_apaga(tmp_path, chave):
    o = oferta(chave)
    falso = b"X" * len(CONTEUDO)
    with pytest.raises(at.Recusada, match="não confere"):
        at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=lambda *a: Resposta(falso))
    assert not list(tmp_path.glob("setup-*"))


def test_maior_que_o_assinado_recusa(tmp_path, chave):
    o = oferta(chave)
    with pytest.raises(at.Recusada, match="tamanho"):
        at.baixar(
            "https://x.invalid", TOKEN, o, tmp_path, abrir=lambda *a: Resposta(CONTEUDO + b"!")
        )


def test_http_erro_vira_recusa(tmp_path, chave):
    o = oferta(chave)

    def abrir(*_):
        raise urllib.error.HTTPError("u", 302, "Found", {}, None)  # type: ignore[arg-type]

    with pytest.raises(at.Recusada, match="302"):
        at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=abrir)


def test_limpar_mantem_so_a_oferta_e_logs(tmp_path, chave):
    o = oferta(chave)
    at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=lambda *a: Resposta(CONTEUDO))
    (tmp_path / "setup-velho.exe").write_bytes(b"x")
    (tmp_path / "inno-0.1.0.log").write_text("log")
    at.limpar(tmp_path, o)
    nomes = {p.name for p in tmp_path.iterdir()}
    assert nomes == {at.instalador(o, tmp_path).name, at.MANIFESTO, at.ASSINATURA, "inno-0.1.0.log"}


# --- instalar ao fechar ------------------------------------------------------------------


def test_retomada_pendente_bloqueia(monkeypatch, tmp_path, chave):
    monkeypatch.setattr(at.retomada, "ler", lambda: object())
    disparos = []
    assert (
        at.instalar_ao_fechar(
            oferta(chave), 1, False, tmp_path, disparar=lambda *a: disparos.append(a)
        )
        is None
    )
    assert disparos == []


def test_preparacao_em_andamento_bloqueia(monkeypatch, tmp_path, chave):
    monkeypatch.setattr(at.retomada, "ler", lambda: None)
    assert at.instalar_ao_fechar(oferta(chave), 1, True, tmp_path, disparar=lambda *a: 1) is None


def test_argumentos_e_tentativas(monkeypatch, tmp_path, chave):
    monkeypatch.setattr(at.retomada, "ler", lambda: None)
    o = oferta(chave)
    vistos, soltou = [], []
    for _ in range(4):
        at.instalar_ao_fechar(
            o,
            4321,
            False,
            tmp_path,
            soltar_mutex=lambda: soltou.append(1),
            disparar=lambda args, pasta: vistos.append((args, pasta)) or 9,
        )
    assert len(vistos) == at.TENTATIVAS == len(soltou)
    args, pasta = vistos[0]
    assert args[1:4] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    assert args[-1] == "/ESPERAPID=4321"
    assert not any(a.upper().startswith("/APIURL") for a in args)
    assert pasta == tmp_path


def test_situacao_no_inicio(tmp_path, chave):
    o = oferta(chave)
    at.baixar("https://x.invalid", TOKEN, o, tmp_path, abrir=lambda *a: Resposta(CONTEUDO))
    assert at.situacao_no_inicio(tmp_path) is None  # ainda não tentou
    (tmp_path / at.TENTADAS).write_text("1")
    assert "não foi instalada" in (at.situacao_no_inicio(tmp_path) or "")
    velho = manifesto(versao="0.0.1")
    (tmp_path / at.MANIFESTO).write_bytes(velho)
    assert at.situacao_no_inicio(tmp_path) is None
    assert not (tmp_path / at.MANIFESTO).exists()  # já instalada: limpou


# --- executor.disparar ---------------------------------------------------------------------


def _exe_falso(pasta: Path) -> Path:
    """Cópia do cmd.exe com nome de instalador: roda `/c` e sai."""
    dados = Path(executor.sistema32("cmd.exe")).read_bytes()
    destino = pasta / f"setup-{hashlib.sha256(dados).hexdigest()}.exe"
    destino.write_bytes(dados)
    return destino


def test_disparar_aceita_so_instalador_conferido(tmp_path):
    exe = _exe_falso(tmp_path)
    marca = tmp_path / "rodou.txt"
    pid = executor.disparar([str(exe), "/d", "/c", f"echo ok> {marca}"], PureWindowsPath(tmp_path))
    assert pid > 0
    import time

    for _ in range(100):
        if marca.exists():
            break
        time.sleep(0.1)
    assert marca.read_text().strip() == "ok"


@pytest.mark.parametrize("caso", ["fora_da_pasta", "nome", "relativo", "texto"])
def test_disparar_recusa_caminho(tmp_path, caso):
    exe = _exe_falso(tmp_path)
    args: object = {
        "fora_da_pasta": [str(exe)],
        "nome": [str(tmp_path / "setup.exe")],
        "relativo": [exe.name],
        "texto": str(exe),
    }[caso]
    pasta = tmp_path / "outra" if caso == "fora_da_pasta" else tmp_path
    with pytest.raises((ValueError, TypeError)):
        executor.disparar(args, PureWindowsPath(pasta))  # type: ignore[arg-type]


def test_disparar_recusa_arquivo_alterado(tmp_path):
    exe = _exe_falso(tmp_path)
    with exe.open("ab") as f:
        f.write(b"!")
    with pytest.raises(ValueError, match="mudou"):
        executor.disparar([str(exe)], PureWindowsPath(tmp_path))


# --- faixa ---------------------------------------------------------------------------------


def test_faixa_adiavel_e_obrigatoria(qtbot, chave):
    from itc_bench.ui.atualizacao import FaixaAtualizacao

    faixa = FaixaAtualizacao()
    qtbot.addWidget(faixa)
    faixa.mostrar(oferta(chave))
    assert not faixa.confirmada and faixa.instalar.isEnabled()
    faixa.instalar.click()
    assert faixa.confirmada
    faixa.adiar.click()
    assert not faixa.confirmada and faixa.isHidden()
    faixa.mostrar(oferta(chave, minima="99.0.0"))
    assert faixa.confirmada and not faixa.instalar.isEnabled() and faixa.adiar.isHidden()
    assert "<" not in faixa.texto.text() or faixa.texto.textFormat().name == "PlainText"


# --- achados da revisão do PR #43 ----------------------------------------------------------


@pytest.mark.parametrize("estado", ["alheio", "criado", "sem_admin"])
def test_inicio_avisa_so_mutex_alheio(qtbot, estado):
    from itc_bench.ui.inicio import PainelInicio

    painel = PainelInicio(
        True,
        lambda: None,
        lambda: "",
        lambda: 0,
        lambda: None,
        lambda: None,  # type: ignore[arg-type,return-value]
        mutex_alheio=estado == "alheio",  # mesma expressão do __main__
    )
    qtbot.addWidget(painel)
    if estado == "alheio":
        assert painel.aviso_mutex is not None
        assert painel.aviso_mutex.textFormat().name == "PlainText"
        assert "S-1-" not in painel.aviso_mutex.text()
    else:
        assert painel.aviso_mutex is None


def test_marcador_de_teste_fora_do_pacote():
    assert not at.copia_de_teste()


@pytest.fixture
def modo_teste(monkeypatch):
    from itc_bench import __main__ as principal

    chamadas: list[str] = []
    monkeypatch.setattr(principal.api, "endereco", lambda _dev: "https://api.exemplo.invalid")
    monkeypatch.setattr(principal.api, "validar", lambda base, _dev: base)
    monkeypatch.setattr(at, "limpar", lambda manter=None: None)

    def consultar(_base, sessao):
        chamadas.append(sessao.revelar())

    monkeypatch.setattr(at, "consultar", consultar)
    return principal, chamadas


def test_teste_atualizacao_sem_marcador_recusa(modo_teste, monkeypatch):
    principal, chamadas = modo_teste
    monkeypatch.setenv(at.VARIAVEL_TESTE, "itcts_job")
    monkeypatch.setattr(at, "copia_de_teste", lambda: False)
    assert principal._teste_atualizacao(True) == 5
    assert chamadas == []


def test_teste_atualizacao_sem_variavel_recusa(modo_teste, monkeypatch):
    principal, chamadas = modo_teste
    monkeypatch.delenv(at.VARIAVEL_TESTE, raising=False)
    monkeypatch.setattr(at, "copia_de_teste", lambda: True)
    assert principal._teste_atualizacao(True) == 5
    assert chamadas == []


def test_teste_atualizacao_com_os_dois_segue(modo_teste, monkeypatch):
    import os

    principal, chamadas = modo_teste
    monkeypatch.setenv(at.VARIAVEL_TESTE, "itcts_job")
    monkeypatch.setattr(at, "copia_de_teste", lambda: True)
    principal._teste_atualizacao(True)  # sem versão anunciada (consultar falso) sai 5
    assert chamadas == ["itcts_job"]
    assert at.VARIAVEL_TESTE not in os.environ  # não passa adiante
