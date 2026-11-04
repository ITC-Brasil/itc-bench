"""Login offline (ADR-013): scrypt real, DPAPI real, relógio injetado."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from itc_bench.nucleo import dpapi
from itc_bench.servicos import offline
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.offline import Cofre, OfflineRecusado

SENHA = "Marcador-Senha-7Q2x!"


class Relogio:
    def __init__(self) -> None:
        self.agora = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.agora


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def cofre(tmp_path, relogio) -> Cofre:
    c = Cofre(tmp_path / "logins.dpapi", relogio)
    c.lembrar("Ana.Lima", "Ana Lima", Sensivel(SENHA))
    return c


def test_scrypt_real_com_maxmem(tmp_path):
    # n=2^15, r=8 estoura o maxmem padrão (32 MiB); o cálculo real tem de passar.
    inicio = time.monotonic()
    valor = offline.verificador(Sensivel(SENHA), b"0" * 16)
    assert len(valor) == 32
    assert time.monotonic() - inicio > 0.01  # não é um hash rápido
    with pytest.raises(ValueError):
        import hashlib

        hashlib.scrypt(SENHA.encode(), salt=b"0" * 16, n=2**15, r=8, p=1)


def test_dpapi_ida_e_volta():
    cifrado = dpapi.cifrar(b"texto")
    assert cifrado != b"texto" and dpapi.decifrar(cifrado) == b"texto"


def test_senha_certa_dentro_de_7_dias(cofre, relogio):
    relogio.agora += timedelta(days=6, hours=23)
    assert cofre.conferir(" ana.lima ", Sensivel(SENHA)) == "Ana Lima"


def test_depois_de_7_dias_recusa_e_apaga(cofre, relogio):
    relogio.agora += timedelta(days=7, minutes=1)
    with pytest.raises(OfflineRecusado, match="expirado"):
        cofre.conferir("ana.lima", Sensivel(SENHA))
    assert not cofre.tem("ana.lima")


def test_senha_errada_e_bloqueio_apos_5(cofre):
    for _ in range(offline.MAXIMO_FALHAS - 1):
        with pytest.raises(OfflineRecusado, match="senha_errada"):
            cofre.conferir("ana.lima", Sensivel("errada"))
    with pytest.raises(OfflineRecusado, match="bloqueado"):
        cofre.conferir("ana.lima", Sensivel("errada"))
    with pytest.raises(OfflineRecusado, match="sem_login_recente"):
        cofre.conferir("ana.lima", Sensivel(SENHA))


def test_senha_certa_zera_falhas(cofre):
    for _ in range(offline.MAXIMO_FALHAS - 1):
        with pytest.raises(OfflineRecusado):
            cofre.conferir("ana.lima", Sensivel("errada"))
    cofre.conferir("ana.lima", Sensivel(SENHA))
    for _ in range(offline.MAXIMO_FALHAS - 1):
        with pytest.raises(OfflineRecusado, match="senha_errada"):
            cofre.conferir("ana.lima", Sensivel("errada"))


def test_relogio_voltado_recusa(cofre, relogio):
    relogio.agora += timedelta(days=2)
    cofre.conferir("ana.lima", Sensivel(SENHA))
    relogio.agora -= timedelta(days=1)
    with pytest.raises(OfflineRecusado, match="relogio"):
        cofre.conferir("ana.lima", Sensivel(SENHA))


def test_usuario_desconhecido(cofre):
    with pytest.raises(OfflineRecusado, match="sem_login_recente"):
        cofre.conferir("outro", Sensivel(SENHA))


def test_esquecer(cofre):
    cofre.esquecer("ANA.LIMA")
    assert not cofre.tem("ana.lima")


def test_arquivo_cifrado_sem_senha(cofre):
    bruto = cofre.arquivo.read_bytes()
    assert b"Ana Lima" not in bruto  # cifrado
    claro = dpapi.decifrar(bruto)
    assert SENHA.encode() not in claro and b"Ana Lima" in claro
    assert not list(cofre.arquivo.parent.glob("*.tmp"))


def test_arquivo_corrompido(cofre):
    cofre.arquivo.write_bytes(b"lixo")
    with pytest.raises(OfflineRecusado, match="cofre_ilegivel"):
        cofre.conferir("ana.lima", Sensivel(SENHA))
