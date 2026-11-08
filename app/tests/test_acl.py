"""ACL de %ProgramData%\\ITC em pastas temporárias reais (os casos que mudam ACL pedem admin)."""

import _winapi
import subprocess
from unittest import mock

import pytest

from itc_bench.nucleo import acl, caminhos
from itc_bench.nucleo.elevacao import eh_admin
from itc_bench.servicos.executor import powershell

so_admin = pytest.mark.skipif(not eh_admin(), reason="aplicar ACL exige execução elevada")


def _sddl(caminho):
    r = powershell("(Get-Acl -LiteralPath $env:ITC_CAMINHO).Sddl", caminho=str(caminho))
    assert r.ok, r.erros
    return r.saida.strip()


def test_junction_na_raiz_e_recusada_antes_de_criar(tmp_path, monkeypatch):
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    programdata = tmp_path / "pd"
    programdata.mkdir()
    _winapi.CreateJunction(str(alvo), str(programdata / "ITC"))
    monkeypatch.setattr(caminhos, "programdata", lambda: programdata)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    with pytest.raises(acl.PontoDeReparse):
        caminhos.inicializar(admin=True)
    assert list(alvo.iterdir()) == []  # nada criado pelo desvio


def test_junction_dentro_da_arvore_e_recusada(tmp_path):
    raiz = tmp_path / "ITC"
    (raiz / "Bench").mkdir(parents=True)
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    antes = _sddl(alvo)
    _winapi.CreateJunction(str(alvo), str(raiz / "Bench" / "desvio"))
    with pytest.raises(acl.PontoDeReparse, match="desvio"):
        acl.proteger(raiz)
    assert _sddl(alvo) == antes


@so_admin
def test_link_simbolico_de_arquivo_e_recusado(tmp_path):
    raiz = tmp_path / "ITC"
    raiz.mkdir()
    (tmp_path / "fora.txt").write_text("x")
    (raiz / "link.txt").symlink_to(tmp_path / "fora.txt")
    with pytest.raises(acl.PontoDeReparse):
        acl.proteger(raiz)


@so_admin
def test_aplica_sddl_dono_e_heranca(tmp_path):
    raiz = tmp_path / "ITC"
    (raiz / "Bench" / "logs").mkdir(parents=True)
    (raiz / "Bench" / "logs" / "bench.log").write_text("x")
    acl.proteger(raiz)
    assert _sddl(raiz).startswith("O:BA")
    assert _sddl(raiz).endswith("D:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)")
    herdado = "D:AI(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;0x1200a9;;;BU)"
    assert _sddl(raiz / "Bench").startswith("O:BA")
    assert _sddl(raiz / "Bench").endswith(herdado)
    arquivo = _sddl(raiz / "Bench" / "logs" / "bench.log")
    assert arquivo.startswith("O:BA")
    assert arquivo.endswith("D:AI(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;0x1200a9;;;BU)")


@so_admin
def test_arquivo_sem_acesso_para_admins_e_recuperado(tmp_path):
    raiz = tmp_path / "ITC"
    raiz.mkdir()
    trancado = raiz / "trancado.txt"
    trancado.write_text("x")
    for args in (["/setowner", "*S-1-5-18"], ["/inheritance:r", "/grant:r", "*S-1-5-18:F"]):
        subprocess.run(
            [r"C:\Windows\System32\icacls.exe", str(trancado), *args],
            check=True,
            capture_output=True,
        )
    acl.proteger(raiz)
    assert _sddl(trancado).startswith("O:BA")


def test_falha_que_sobra_vira_erro(tmp_path):
    falha = [(str(tmp_path / "x"), 5)]
    with (
        mock.patch.object(acl, "_aplicar", return_value=falha) as aplicar,
        mock.patch.object(acl, "_habilitar_privilegios") as privilegios,
        pytest.raises(acl.ErroAcl, match="1 item"),
    ):
        acl.proteger(tmp_path)
    assert aplicar.call_count == 2
    privilegios.assert_called_once()


def test_sem_admin_nao_mexe_no_acl(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "programdata", lambda: tmp_path / "pd")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    with mock.patch.object(acl, "proteger") as proteger:
        caminhos.inicializar(admin=False)
    proteger.assert_not_called()
    assert (tmp_path / "pd" / "ITC" / "Bench" / "logs").is_dir()


@so_admin
def test_pasta_protegida_nunca_fica_legivel_para_usuarios(tmp_path, monkeypatch):
    raiz = tmp_path / "ITC"
    protegida = raiz / "Bench" / "protegido"
    (raiz / "Bench" / "logs").mkdir(parents=True)
    (raiz / "Bench" / "logs" / "bench.log").write_text("x")
    acl.proteger_segredos(raiz, protegida)
    (protegida / "logins.dpapi").write_text("x")
    vistos = []
    original = acl._definir

    def espiar(alvo, *a, **k):
        resultado = original(alvo, *a, **k)
        # Depois de cada passo do reset da árvore, a protegida continua sem Usuários.
        vistos.append(_sddl(protegida / "logins.dpapi"))
        return resultado

    monkeypatch.setattr(acl, "_definir", espiar)
    acl.proteger_segredos(raiz, protegida)  # segunda execução: pasta já existe
    assert vistos and all("BU" not in v for v in vistos)
    assert acl.sddl_atual(protegida) == acl.SDDL_PROTEGIDO
    assert _sddl(protegida / "logins.dpapi").endswith("D:AI(A;ID;FA;;;SY)(A;ID;FA;;;BA)")
    # O resto da árvore fica como no ADR-011.
    assert _sddl(raiz / "Bench" / "logs" / "bench.log").endswith(
        "D:AI(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;0x1200a9;;;BU)"
    )
    assert _sddl(raiz / "Bench").endswith(
        "D:AI(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;0x1200a9;;;BU)"
    )


@so_admin
def test_pasta_protegida_com_acl_alterado_e_refeita(tmp_path):
    raiz = tmp_path / "ITC"
    protegida = raiz / "Bench" / "protegido"
    acl.proteger_segredos(raiz, protegida)
    subprocess.run(
        [r"C:\Windows\System32\icacls.exe", str(protegida), "/grant", "*S-1-5-32-545:R"],
        check=True,
        capture_output=True,
    )
    acl.proteger_segredos(raiz, protegida)
    assert acl.sddl_atual(protegida) == acl.SDDL_PROTEGIDO


def test_junction_na_pasta_protegida_e_recusada(tmp_path):
    raiz = tmp_path / "ITC"
    (raiz / "Bench").mkdir(parents=True)
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    _winapi.CreateJunction(str(alvo), str(raiz / "Bench" / "protegido"))
    with pytest.raises(acl.PontoDeReparse):
        acl.proteger_segredos(raiz, raiz / "Bench" / "protegido")
