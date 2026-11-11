"""Políticas e USB (ADR-021): catálogo, situação, recusas, hive com falha e cancelamento.

Só SIDs e nomes fictícios. O PowerShell real só lê a máquina ou grava numa chave de teste em
HKCU que é apagada no fim.
"""

import ast
import json
import logging
import secrets
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from itc_bench.servicos import executor, politicas
from itc_bench.servicos.executor import Resultado
from itc_bench.servicos.politicas import CATALOGO, POR_ID, Alvo, estado, operacoes, recusa_alvo

BASE = "S-1-5-21-1-2-3-"
DONO = BASE + "1001"
ALUNO = BASE + "1003"  # perfil carregado
OUTRO = BASE + "1004"  # perfil não carregado
SUPORTE = BASE + "1002"
NOMES = {"1001": "Tecnico-Teste", "1002": "Suporte", "1003": "Aluno-Teste", "1004": "Aluno-Dois"}
PROT = frozenset({"suporte"})


def _conta(rid: str, *, carregado: bool = False, perfil: bool = True) -> dict[str, Any]:
    return {
        "sid": BASE + rid,
        "nome": NOMES.get(rid, "Nativo"),
        "ativo": True,
        "admin": rid in ("500", "1001", "1002"),
        "fonte": "Local",
        "logada": rid == "1001",
        "ultima": None,
        "perfil": f"C:\\Users\\{NOMES.get(rid, 'x')}" if perfil else None,
        "carregado": carregado,
    }


LISTA_JSON = json.dumps(
    {
        "contas": [
            _conta("500"),
            _conta("1001", carregado=True),
            _conta("1002"),
            _conta("1003", carregado=True),
            _conta("1004"),
            {**_conta("1005"), "perfil": None, "nome": "Sem-Perfil"},
        ],
        "outros_admins": [],
        "computador": "PC-TESTE",
    }
)


def ok(saida: str = "") -> Resultado:
    return Resultado(0, saida, "", 0.1, False)


class Falso:
    """Executor falso: reconhece o trecho pelo conteúdo e grava cada chamada."""

    def __init__(self, *, escrever: Any = None, descarregar_ok: bool = True) -> None:
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self.escrever = escrever
        self.descarregar_ok = descarregar_ok

    def __call__(self, script: str, **kw: Any) -> Resultado:
        if "Membros-Admin" in script:
            self.chamadas.append(("listar", kw))
            return ok(LISTA_JSON)
        if "ITC_ACAO" in script:
            acao = kw["acao"]
            self.chamadas.append((acao, kw))
            if acao == "sobras":
                return ok(f"DONO|{DONO}\nSOBRA|ok")
            if acao == "carregar":
                return ok("OK")
            return (
                ok("OK") if self.descarregar_ok else Resultado(1, "ERRO|descarregar", "", 0, False)
            )
        if "Abrir-Criando" in script:
            self.chamadas.append(("escrever", kw))
            if callable(self.escrever):
                return self.escrever(kw)
            ops = json.loads(kw["operacoes"])
            return ok("\n".join(f"OK|{o['p']}" for o in ops))
        raise AssertionError("trecho inesperado")

    def nomes(self) -> list[str]:
        return [n for n, _ in self.chamadas]


def alvo(sid: str, carregado: bool = False) -> Alvo:
    return Alvo(sid, "rótulo", carregado)


# ---------------------------------------------------------------- catálogo


def test_catalogo_ids_unicos_e_raizes_aceitas() -> None:
    assert len(POR_ID) == len(CATALOGO)
    for p in CATALOGO:
        assert p.escopos
        for escopo in p.escopos:
            for v in p.valores:
                assert politicas.raiz_aceita(escopo, v.chave), (p.id, escopo, v.chave)


@pytest.mark.parametrize(
    ("escopo", "chave", "aceita"),
    [
        ("usuario", "Software\\Policies\\X", True),
        ("usuario", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", True),
        ("usuario", "Software\\Microsoft\\Windows\\CurrentVersion\\Run", False),
        ("usuario", "Software\\Policies\\..\\X", False),
        ("maquina", "SYSTEM\\CurrentControlSet\\Services\\SharedAccess", True),
        ("maquina", "SYSTEM\\CurrentControlSet\\Services\\Outro", False),
        ("usuario", "SYSTEM\\CurrentControlSet\\Services\\SharedAccess", False),
        ("maquina", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", False),
    ],
)
def test_raiz_aceita(escopo: politicas.Escopo, chave: str, aceita: bool) -> None:
    assert politicas.raiz_aceita(escopo, chave) is aceita


def test_sem_wallpaper_nem_unidade_c() -> None:
    nomes = {v.nome for p in CATALOGO for v in p.valores}
    assert not nomes & {"Wallpaper", "WallpaperStyle", "NoDrives", "NoViewOnDrive"}


def test_operacoes_powershell_aplicar_e_desfazer() -> None:
    aplicar = operacoes("aplicar", ["powershell"], "usuario")
    assert [o["nome"] for o in aplicar] == ["ITCBench1", "ITCBench2", "ITCBench3", "DisallowRun"]
    assert all(o["acao"] == "gravar" for o in aplicar)
    desfazer = {o["nome"]: o for o in operacoes("desfazer", ["powershell"], "usuario")}
    assert desfazer["1"]["acao"] == "apagar_se_igual" and desfazer["1"]["dado"] == "PowerShell.exe"
    assert desfazer["DisallowRun"]["acao"] == "apagar_se_vazia"
    assert list(desfazer)[-1] == "DisallowRun"  # depois de esvaziar a lista


def test_ics_desfazer_volta_manual_e_escopo() -> None:
    (op,) = operacoes("desfazer", ["ics"], "maquina")
    assert op["acao"] == "gravar" and op["dado"] == 3
    assert operacoes("aplicar", ["ics"], "usuario") == []
    assert len(operacoes("aplicar", ["usb", "store"], "usuario")) == 2
    assert len(operacoes("aplicar", ["usb", "store"], "maquina")) == 2


# ---------------------------------------------------------------- situação


def _k(pid: str, nome: str) -> str:
    v = next(v for v in POR_ID[pid].valores if v.nome == nome)
    return f"{v.chave}|{v.nome}"


def test_estado() -> None:
    usb = POR_ID["usb"]
    assert estado(usb, {}) == "nao_aplicada"
    assert estado(usb, {_k("usb", "Deny_All"): "1"}) == "aplicada"
    assert estado(usb, {_k("usb", "Deny_All"): "0"}) == "diferente"
    ics = POR_ID["ics"]
    assert estado(ics, {_k("ics", "Start"): "3"}) == "nao_aplicada"
    assert estado(ics, {_k("ics", "Start"): "4"}) == "aplicada"
    assert estado(ics, {_k("ics", "Start"): "2"}) == "diferente"


def test_estado_powershell_legado() -> None:
    ps = POR_ID["powershell"]
    legado = {_k("powershell", "DisallowRun"): "1", _k("powershell", "1"): "POWERSHELL.EXE"}
    assert estado(ps, legado) == "diferente"
    so_outro = {_k("powershell", "1"): "outro.exe"}
    assert estado(ps, so_outro) == "nao_aplicada"
    tudo = {_k("powershell", n): str(v.dado) for v in ps.valores if not v.legado for n in [v.nome]}
    assert estado(ps, tudo) == "aplicada"


def test_aviso_edicao() -> None:
    assert politicas.aviso_edicao(POR_ID["store"], "Professional") == politicas.AVISO_EDICAO
    assert politicas.aviso_edicao(POR_ID["store"], "Enterprise") is None
    assert politicas.aviso_edicao(POR_ID["usb"], "Core") == politicas.AVISO_EDICAO
    assert politicas.aviso_edicao(POR_ID["usb"], "Professional") is None
    assert politicas.aviso_edicao(POR_ID["cmd"], "CoreSingleLanguage") is None


# ---------------------------------------------------------------- recusas


def test_recusa_alvo() -> None:
    from itc_bench.servicos import contas

    lista = contas.ler(LISTA_JSON)
    assert recusa_alvo(alvo(BASE + "500"), lista, PROT, DONO) == "nativo"
    assert recusa_alvo(alvo(SUPORTE), lista, PROT, DONO) == "suporte"
    assert recusa_alvo(alvo(DONO), lista, PROT, DONO) == "dono"
    assert recusa_alvo(alvo(BASE + "1005"), lista, PROT, DONO) == "sem_perfil"
    assert recusa_alvo(alvo(BASE + "9999"), lista, PROT, DONO) == "nao_encontrada"
    assert recusa_alvo(alvo(ALUNO), lista, PROT, DONO) is None
    assert recusa_alvo(politicas.PADRAO, lista, PROT, DONO) is None
    assert recusa_alvo(politicas.MAQUINA, lista, PROT, DONO) is None


# ---------------------------------------------------------------- aplicar


def test_aplicar_carregado_maquina_e_padrao() -> None:
    f = Falso()
    feitos = politicas.aplicar(
        "aplicar",
        ["cmd", "usb", "ics"],
        [politicas.MAQUINA, alvo(ALUNO, True), politicas.PADRAO],
        protegidas_=PROT,
        rodar=f,
    )
    assert all(x.ok for x in feitos), feitos
    assert f.nomes() == [
        "sobras",
        "listar",
        "escrever",
        "escrever",
        "carregar",
        "escrever",
        "descarregar",
    ]
    hives = [kw["hive"] for n, kw in f.chamadas if n == "escrever"]
    assert hives[:2] == ["MAQUINA", ALUNO] and hives[2].startswith("ITCBench_")
    carregar = next(kw for n, kw in f.chamadas if n == "carregar")
    assert carregar["sid"] == "DEFAULT" and carregar["hive"] == hives[2]
    assert SUPORTE in next(kw for n, kw in f.chamadas if n == "escrever")["protegidos"]
    assert feitos[0].politicas == {"usb": True, "ics": True}


def test_recusado_nao_escreve() -> None:
    f = Falso()
    feitos = politicas.aplicar(
        "aplicar", ["cmd"], [alvo(SUPORTE), alvo(BASE + "500")], protegidas_=PROT, rodar=f
    )
    assert [x.ok for x in feitos] == [False, False]
    assert "escrever" not in f.nomes() and "carregar" not in f.nomes()


def test_conta_que_roda_o_bench_recebe_politica() -> None:
    """ADR-034: Políticas aceitam a conta que roda o Bench; o trecho recebe ITC_PERMITIR_DONO."""
    f = Falso()
    feitos = politicas.aplicar("aplicar", ["cmd"], [alvo(DONO, True)], protegidas_=PROT, rodar=f)
    assert [x.ok for x in feitos] == [True]
    escritas = [kw for nome, kw in f.chamadas if nome == "escrever"]
    assert len(escritas) == 1
    assert escritas[0]["hive"] == DONO and escritas[0]["permitir_dono"] == "1"
    assert escritas[0]["perfil"] == "politicas"


def test_recusa_dono_so_sem_permissao() -> None:
    """A recusa da conta que roda o Bench continua sendo o padrão (Aparência, Preparação)."""
    from itc_bench.servicos import contas

    lista = contas.ler(LISTA_JSON)
    assert recusa_alvo(alvo(DONO), lista, PROT, DONO) == "dono"
    assert recusa_alvo(alvo(DONO), lista, PROT, DONO, permitir_dono=True) is None
    assert recusa_alvo(alvo(SUPORTE), lista, PROT, DONO, permitir_dono=True) == "suporte"
    assert recusa_alvo(alvo(BASE + "500"), lista, PROT, DONO, permitir_dono=True) == "nativo"


def test_trecho_libera_dono_so_para_politicas() -> None:
    """A segunda conferência, no PowerShell, só libera com perfil politicas e a variável."""
    from itc_bench.servicos import hive as hive_

    comum = hive_.script("escrever")
    assert "$donoOk = ($PERFIL -ceq 'politicas') -and ($env:ITC_PERMITIR_DONO -eq '1')" in comum
    assert "Falhar 'dono'" in comum


def test_falha_no_meio_descarrega() -> None:
    def explode(_: dict[str, Any]) -> Resultado:
        raise OSError("falha simulada")

    f = Falso(escrever=explode)
    with pytest.raises(OSError):
        politicas.aplicar("aplicar", ["cmd"], [alvo(OUTRO)], protegidas_=PROT, rodar=f)
    assert f.nomes()[-3:] == ["carregar", "escrever", "descarregar"]


def test_falha_parcial_por_politica() -> None:
    f = Falso(
        escrever=lambda kw: Resultado(
            0, "OK|cmd\nERRO|UnauthorizedAccessException|regedit", "", 0, False
        )
    )
    (feito,) = politicas.aplicar(
        "aplicar", ["cmd", "regedit"], [alvo(OUTRO)], protegidas_=PROT, rodar=f
    )
    assert not feito.ok and feito.politicas == {"cmd": True, "regedit": False}
    assert "Editor do Registro" in feito.mensagem
    assert f.nomes()[-1] == "descarregar"


def test_cancelar_entre_alvos_sem_interromper_escrita() -> None:
    evento = threading.Event()

    def escreve_e_cancela(kw: dict[str, Any]) -> Resultado:
        evento.set()  # técnico cancela durante a escrita do primeiro alvo
        return ok("\n".join(f"OK|{o['p']}" for o in json.loads(kw["operacoes"])))

    f = Falso(escrever=escreve_e_cancela)
    feitos = politicas.aplicar(
        "aplicar",
        ["cmd"],
        [alvo(OUTRO), alvo(ALUNO, True)],
        protegidas_=PROT,
        rodar=f,
        cancelar=evento,
    )
    assert feitos[0].ok and not feitos[1].ok and "Cancelado" in feitos[1].mensagem
    assert f.nomes().count("escrever") == 1 and f.nomes()[-1] == "descarregar"
    # A escrita roda sem o evento de cancelamento: nunca é morta no meio.
    assert all("cancelar" not in kw for n, kw in f.chamadas if n in ("escrever", "descarregar"))


def test_descarregar_falha_vira_aviso() -> None:
    f = Falso(descarregar_ok=False)
    (feito,) = politicas.aplicar("desfazer", ["cmd"], [alvo(OUTRO)], protegidas_=PROT, rodar=f)
    assert feito.ok and politicas.MENSAGENS["descarregar"] in feito.avisos
    assert f.nomes().count("descarregar") == politicas.TENTATIVAS_DESCARREGAR


def test_politica_desconhecida() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        politicas.aplicar("aplicar", ["x"], [politicas.MAQUINA], protegidas_=PROT, rodar=Falso())


def test_log_sem_sid_nome_nem_hive(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    f = Falso(escrever=lambda kw: Resultado(0, "ERRO|X|cmd", "", 0, False))
    politicas.aplicar(
        "aplicar",
        ["cmd"],
        [alvo(OUTRO), alvo(ALUNO, True), alvo(DONO, True), politicas.PADRAO],
        protegidas_=PROT,
        rodar=f,
    )
    texto = caplog.text
    assert "politica=cmd" in texto
    for proibido in [BASE, "ITCBench_", "Aluno", "Tecnico", "C:\\Users"]:
        assert proibido not in texto, proibido


# ---------------------------------------------------------------- leitura


def test_ler_nao_carrega_sem_pedido() -> None:
    chamadas: list[str] = []

    def rodar(script: str, **kw: Any) -> Resultado:
        chamadas.append(kw.get("acao", "ler"))
        hives = {
            h["hive"]: {"ok": True, "valores": {}, "alteravel": {}}
            for h in json.loads(kw["leitura"])
        }
        return ok(json.dumps({"edicao": "Core", "dono": DONO, "hives": hives}))

    leitura = politicas.ler([politicas.MAQUINA, alvo(OUTRO), politicas.PADRAO], rodar=rodar)
    assert chamadas == ["ler"]
    assert leitura.situacao[("cmd", OUTRO)] == "nao_lida"
    assert leitura.situacao[("usb", "maquina")] == "nao_aplicada"
    assert ("cmd", "maquina") not in leitura.situacao


def test_ler_descarregado_carrega_e_descarrega() -> None:
    chamadas: list[str] = []

    def rodar(script: str, **kw: Any) -> Resultado:
        acao = kw.get("acao", "ler")
        chamadas.append(acao)
        if acao == "sobras":
            return ok(f"DONO|{DONO}")
        if acao in ("carregar", "descarregar"):
            return ok("OK")
        hives = {
            h["hive"]: {
                "ok": True,
                "valores": {},
                "alteravel": {_k("usb", "Deny_All").split("|")[0]: True},
            }
            for h in json.loads(kw["leitura"])
        }
        return ok(json.dumps({"edicao": "Professional", "dono": DONO, "hives": hives}))

    leitura = politicas.ler([alvo(OUTRO)], rodar=rodar, descarregados=True)
    assert chamadas == ["ler", "sobras", "carregar", "ler", "descarregar"]
    assert leitura.situacao[("cmd", OUTRO)] == "nao_aplicada"
    assert leitura.alteravel[("usb", OUTRO)] is True


# ---------------------------------------------------------------- regras do módulo


def test_servico_nao_abre_registro() -> None:
    """O processo Python nunca abre o hive temporário: o serviço nem importa winreg."""
    arquivo = Path(politicas.__file__)
    arvore = ast.parse(arquivo.read_text("utf-8"))
    importados = {
        n.name
        for no in ast.walk(arvore)
        if isinstance(no, ast.Import | ast.ImportFrom)
        for n in no.names
    } | {no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
    assert not {"winreg", "_winreg", "ctypes"} & importados


def test_trechos_em_64_bits() -> None:
    pasta = Path(politicas.__file__).parent.parent / "recursos" / "politicas"
    textos = {p.name: p.read_text("utf-8") for p in pasta.glob("*.ps1")}
    assert "Registry64" in textos["comum.ps1"]
    for nome, texto in textos.items():
        assert "WOW6432Node" not in texto, nome
        assert "Registry32" not in texto, nome
        # Toda abertura de base passa pela vista de 64 bits.
        assert texto.count("OpenBaseKey(") == texto.count("$Vista)"), nome
    assert sys.maxsize > 2**32


def test_bits_recusa_32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(politicas.struct, "calcsize", lambda _: 4)
    with pytest.raises(RuntimeError, match="64 bits"):
        politicas.ler([politicas.MAQUINA], rodar=Falso())


def test_sobras_configurador(tmp_path: Path) -> None:
    for nome in [
        "itc_security_check.bat",
        "itc_security_check.ps1",
        "itc_security_check2.bat",
        "outro.bat",
    ]:
        (tmp_path / nome).write_text("x")
    achadas = politicas.sobras_configurador(tmp_path)
    assert sorted(p.name for p in achadas) == ["itc_security_check.bat", "itc_security_check.ps1"]
    assert politicas.remover_sobras(tmp_path)[0]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["itc_security_check2.bat", "outro.bat"]


# ---------------------------------------------------------------- PowerShell real


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_ler_maquina_real() -> None:
    leitura = politicas.ler([politicas.MAQUINA])
    assert leitura.edicao
    assert leitura.dono.startswith("S-1-5-")
    assert {k[0] for k in leitura.situacao} == {p.id for p in CATALOGO if "maquina" in p.escopos}
    assert "sem_acesso" not in leitura.situacao.values()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_escrever_real_em_chave_de_teste() -> None:
    """Escrita, apagar_se_igual e apagar_se_vazia de verdade, numa chave de teste em HKCU."""
    import winreg  # só no teste: o serviço nunca importa

    raiz = f"Software\\ITCBenchTeste_{secrets.token_hex(4)}"
    trecho = (
        politicas.script("escrever")
        .replace("Hive-Escrita $env:ITC_HIVE", "")
        .replace(
            "$base = Base $env:ITC_HIVE",
            f"$base = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{raiz}')",
        )
    )
    trecho = trecho.replace("$SDDL_NOVA)", "'D:(A;CI;KA;;;WD)')")
    try:
        r = executor.powershell(
            trecho,
            hive="MAQUINA",
            operacoes=json.dumps(operacoes("aplicar", ["usb", "store"], "maquina")),
        )
        assert r.ok and r.saida.split() == ["OK|usb", "OK|store"], (r.saida, r.erros)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            raiz + "\\SOFTWARE\\Policies\\Microsoft\\Windows\\RemovableStorageDevices",
        ) as k:
            assert winreg.QueryValueEx(k, "Deny_All") == (1, winreg.REG_DWORD)
        r = executor.powershell(
            trecho, hive="MAQUINA", operacoes=json.dumps(operacoes("desfazer", ["usb"], "maquina"))
        )
        assert r.ok
        with (
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                raiz + "\\SOFTWARE\\Policies\\Microsoft\\Windows\\RemovableStorageDevices",
            ) as k,
            pytest.raises(FileNotFoundError),
        ):
            winreg.QueryValueEx(k, "Deny_All")
        # Raiz fora do catálogo é recusada pelo trecho.
        ruim = [
            {
                "p": "x",
                "chave": "SOFTWARE\\Microsoft\\Run",
                "nome": "a",
                "tipo": "sz",
                "dado": "b",
                "acao": "gravar",
            }
        ]
        r = executor.powershell(trecho, hive="MAQUINA", operacoes=json.dumps(ruim))
        assert not r.ok and "ERRO|raiz" in r.saida
    finally:
        executor.powershell(
            "[Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($env:ITC_RAIZ, $false)",
            raiz=raiz,
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_hive_recusa_nome_e_sid() -> None:
    script = politicas.script("hive")
    r = executor.powershell(script, acao="carregar", hive="HKLM\\X", sid="DEFAULT")
    assert "ERRO|hive" in r.saida
    r = executor.powershell(script, acao="descarregar", hive="S-1-5-18")
    assert "ERRO|hive" in r.saida
    r = executor.powershell(script, acao="carregar", hive="ITCBench_0000abcd", sid=BASE + "500")
    assert "ERRO|nativo" in r.saida


@pytest.mark.parametrize(
    ("codigo", "trecho"), [("em_uso", "em uso por outro programa"), ("carregar", "não abriu")]
)
def test_falha_ao_carregar_por_codigo(codigo: str, trecho: str) -> None:
    f = Falso()
    original = f.__call__

    def rodar(script: str, **kw: Any) -> Resultado:
        if kw.get("acao") == "carregar":
            f.chamadas.append(("carregar", kw))
            return Resultado(1, f"ERRO|{codigo}", "", 0, False)
        return original(script, **kw)

    (feito,) = politicas.aplicar("aplicar", ["cmd"], [alvo(OUTRO)], protegidas_=PROT, rodar=rodar)
    assert not feito.ok and trecho in feito.mensagem
    assert "escrever" not in f.nomes() and "descarregar" not in f.nomes()


def test_hive_em_uso_so_pela_abertura_exclusiva() -> None:
    texto = (
        Path(politicas.__file__).parent.parent / "recursos" / "politicas" / "hive.ps1"
    ).read_text("utf-8")
    load = next(linha for linha in texto.splitlines() if "'load'" in linha)
    assert "Falhar 'carregar'" in load and "em_uso" not in load
    assert "'Read', 'None'" in texto


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
@pytest.mark.parametrize(
    ("perfil", "permitir", "esperado"),
    [
        ("politicas", "1", "PASSOU"),  # ADR-034
        ("politicas", "0", "ERRO|dono"),
        ("aparencia", "1", "ERRO|dono"),  # a Aparência continua recusando
    ],
)
def test_hive_escrita_real_conta_que_roda(perfil: str, permitir: str, esperado: str) -> None:
    """Só a conferência do trecho, com o SID da conta atual; nada é gravado no registro."""
    trecho = hive_script_comum()
    teste = (
        trecho
        + "\n$eu = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value\n"
        + "if ($eu -notmatch '^S-1-5-21-') { Write-Output 'PASSOU'; exit 0 }\n"
        + "Hive-Escrita $eu\nWrite-Output 'PASSOU'\n"
    )
    r = executor.powershell(teste, perfil=perfil, permitir_dono=permitir, protegidos="")
    assert esperado in r.saida


def hive_script_comum() -> str:
    from itc_bench.servicos import hive as hive_

    return (hive_.RECURSOS / "comum.ps1").read_text("utf-8")
