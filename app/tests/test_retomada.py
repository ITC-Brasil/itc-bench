"""Retomada (ADR-023, item 5): estado em disco validado, vencido, ACL e reparse."""

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

from itc_bench.servicos import retomada as rt

SID = "S-1-5-21-1-2-3-1002"
AGORA = datetime(2026, 11, 6, 12, tzinfo=UTC)


def sim(_c):
    return True


def nao(_c):
    return False


def test_gravar_e_ler(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="itc_bench")
    e = rt.novo("sala_de_aula", ["usb"], "LAB-01", [SID], agora=AGORA)
    rt.gravar(e, tmp_path, conferir=sim)
    lido = rt.ler(tmp_path, AGORA + timedelta(hours=1), conferir=sim)
    assert lido == e and lido.reinicios == 1 and lido.pode_reiniciar
    assert SID not in caplog.text and "LAB-01" not in caplog.text


def test_limite_de_reinicios(tmp_path):
    e = rt.novo("sala_de_aula", [], "", [], agora=AGORA)
    e2 = rt.novo("sala_de_aula", [], "", [], anterior=e, agora=AGORA)
    assert e2.reinicios == 2 and not e2.pode_reiniciar
    assert e2.criado_em == e.criado_em


def test_vencido_e_apagado(tmp_path):
    rt.gravar(rt.novo("sala_de_aula", [], "", [], agora=AGORA), tmp_path, conferir=sim)
    assert rt.ler(tmp_path, AGORA + timedelta(hours=25), conferir=sim) is None
    assert not rt.arquivo(tmp_path).exists()


def test_acl_errada_apaga(tmp_path):
    rt.gravar(rt.novo("sala_de_aula", [], "", [], agora=AGORA), tmp_path, conferir=sim)
    assert rt.ler(tmp_path, AGORA, conferir=nao) is None
    assert not rt.arquivo(tmp_path).exists()


@pytest.mark.parametrize(
    "corpo",
    [
        "{nao e json",
        json.dumps({"formato": 9, "perfil": "sala_de_aula"}),
        json.dumps({"formato": 1, "perfil": "outro", "criado_em": AGORA.isoformat()}),
        json.dumps({"formato": 1, "perfil": "sala_de_aula", "criado_em": "2026-11-06T12:00:00"}),
    ],
)
def test_invalido_apaga(tmp_path, corpo):
    rt.arquivo(tmp_path).write_text(corpo, "utf-8")
    assert rt.ler(tmp_path, AGORA, conferir=sim) is None
    assert not rt.arquivo(tmp_path).exists()


def test_ids_fora_do_catalogo_descartados(tmp_path):
    cru = {
        "formato": 1,
        "perfil": "sala_de_aula",
        "desmarcadas": ["usb", "formatar_disco"],
        "nome": "nome com espaço",
        "alvos": [SID, "S-1-5-18", "C:/Users/x"],
        "criado_em": AGORA.isoformat(),
        "reinicios": 1,
    }
    rt.arquivo(tmp_path).write_text(json.dumps(cru), "utf-8")
    e = rt.ler(tmp_path, AGORA, conferir=sim)
    assert e is not None
    assert e.desmarcadas == ("usb",) and e.alvos == (SID,) and e.nome == ""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_link_simbolico_apagado_sem_seguir(tmp_path):
    alvo = tmp_path / "outro.json"
    alvo.write_text("{}", "utf-8")
    try:
        rt.arquivo(tmp_path).symlink_to(alvo)
    except OSError:
        pytest.skip("sem privilégio para criar link simbólico")
    assert rt.ler(tmp_path, AGORA, conferir=sim) is None
    assert alvo.exists() and not os.path.lexists(rt.arquivo(tmp_path))


def test_criterio_de_acl(monkeypatch):
    casos = {
        "O:BAG:SYD:AI(A;ID;FA;;;SY)(A;ID;FA;;;BA)": True,
        "O:SYD:(A;;FA;;;SY)": True,
        "O:BAD:AI(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;0x1200a9;;;BU)": False,
        "O:S-1-5-21-1-2-3-1002D:(A;;FA;;;SY)": False,
        "O:BAD:(D;;FA;;;BU)(A;;FA;;;SY)": False,
    }
    for sddl, ok in casos.items():
        monkeypatch.setattr(rt.acl, "sddl_atual", lambda _c, s=sddl: s)
        assert rt.acl_ok(rt.arquivo()) is ok, sddl
