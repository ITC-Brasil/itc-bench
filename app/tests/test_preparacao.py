"""Preparação completa (ADR-023): perfis, motor, contas de aluno, Appx e Limpeza.

Contas, SIDs e nomes fictícios. A Limpeza real roda só a função de varredura do trecho sobre uma
pasta temporária com junction (nada fora dela é tocado).
"""

import json
import logging
import os
import re
import sys
import threading
from pathlib import Path

import pytest

from itc_bench.servicos import contas, desinstalar, etapas, executor, limpeza, perfis, politicas
from itc_bench.servicos import preparacao as prep
from itc_bench.servicos.preparacao import Leitura, Resultado

# ---------------------------------------------------------------- perfis


def test_perfis_usam_so_etapas_e_parametros_fechados():
    for p in perfis.PERFIS:
        assert set(p.etapas) <= set(perfis.ORDEM)
        assert list(p.etapas) == [e for e in perfis.ORDEM if e in p.etapas]
    for pid in (*perfis.POLITICAS_USUARIO, *perfis.POLITICAS_MAQUINA, perfis.POLITICA_USB):
        assert pid in politicas.POR_ID
    assert set(perfis.LIMPEZA) <= set(limpeza.NOMES)
    assert "lixeira" not in perfis.LIMPEZA


def test_perfil_do_cadastro():
    assert perfis.do_cadastro("administrativo")[0].id == "administrativo"
    assert perfis.do_cadastro(" Sala_de_Aula ")[0].id == "sala_de_aula"
    assert perfis.do_cadastro(None) == (perfis.PADRAO, "")
    perfil, aviso = perfis.do_cadastro("qualquer coisa")
    assert perfil is perfis.PADRAO and "desconhecido" in aviso


def test_montar_segue_a_ordem():
    ctx = etapas.Contexto(admin=False, cadastros=None)
    assert tuple(e.id for e in etapas.montar(ctx)) == perfis.ORDEM


# ---------------------------------------------------------------- motor


OK = Resultado("ok")


class Falsa:
    def __init__(self, id_, leituras, resultado=OK, erro=None):
        self.id = id_
        self.leituras = list(leituras)
        self.resultado = resultado
        self.erro = erro
        self.aplicou = 0

    def ler(self):
        return self.leituras.pop(0) if len(self.leituras) > 1 else self.leituras[0]

    def aplicar(self, cancelar):
        self.aplicou += 1
        if self.erro:
            raise self.erro
        return self.resultado


def _andamento(*ids):
    return prep.Andamento("teste", list(ids), {})


def test_etapa_feita_e_pulada_sem_aplicar():
    e = Falsa("wifi", [Leitura("feito")])
    a = prep.rodar([e], _andamento("wifi"), pausar=threading.Event())
    assert e.aplicou == 0 and a.situacao["wifi"].situacao == "feito"


def test_pendente_aplica_e_le_de_novo():
    e = Falsa("wifi", [Leitura("pendente"), Leitura("feito")])
    a = prep.rodar([e], _andamento("wifi"), pausar=threading.Event())
    assert e.aplicou == 1 and a.situacao["wifi"].situacao == "feito"


def test_rodar_de_novo_nao_refaz():
    e = Falsa("wifi", [Leitura("pendente"), Leitura("feito")])
    a = prep.rodar([e], _andamento("wifi"), pausar=threading.Event())
    prep.rodar([e], a, pausar=threading.Event())
    assert e.aplicou == 1


def test_falha_segue_e_bloqueia_dependentes(caplog):
    caplog.set_level(logging.INFO, logger="itc_bench")
    c = Falsa("contas", [Leitura("pendente")], erro=RuntimeError("C:\\Users\\aluno caiu"))
    pol = Falsa("politicas", [Leitura("pendente")])
    en = Falsa("energia", [Leitura("pendente"), Leitura("feito")])
    a = prep.rodar(
        [c, pol, en], _andamento("contas", "politicas", "energia"), pausar=threading.Event()
    )
    assert a.situacao["contas"].situacao == "falhou"
    assert a.situacao["contas"].codigo == "RuntimeError"
    assert a.situacao["politicas"].situacao == "bloqueada" and pol.aplicou == 0
    assert a.situacao["energia"].situacao == "feito"
    assert any("situacao=" in r.getMessage() for r in caplog.records)
    assert "aluno" not in caplog.text


def test_pausar_para_depois_da_etapa_corrente():
    pausar = threading.Event()
    um = Falsa("wifi", [Leitura("pendente"), Leitura("feito")])
    dois = Falsa("energia", [Leitura("pendente")])

    def avisar(etapa):
        if etapa == "wifi":
            pausar.set()

    a = prep.rodar([um, dois], _andamento("wifi", "energia"), pausar=pausar, avisar=avisar)
    assert um.aplicou == 1 and dois.aplicou == 0
    assert a.situacao.get("energia") is None


def test_reinicio_marca_andamento():
    e = Falsa("identificacao", [Leitura("pendente")], Resultado("reinicio", "x"))
    a = prep.rodar([e], _andamento("identificacao"), pausar=threading.Event())
    assert a.reinicio and a.situacao["identificacao"].situacao == "aguardando_reinicio"


def test_ok_mas_ainda_pendente_vira_falha():
    e = Falsa("wifi", [Leitura("pendente")])
    a = prep.rodar([e], _andamento("wifi"), pausar=threading.Event())
    assert a.situacao["wifi"].situacao == "falhou"


def test_desmarcadas_nao_rodam_e_selo():
    a = prep.novo(perfis.POR_ID["sala_de_aula"], desmarcadas=["usb", "limpeza"])
    assert "usb" not in a.etapas and a.selo() == f"0/{len(perfis.ORDEM) - 2}"


# ---------------------------------------------------------------- contas de aluno

SUPORTE = "S-1-5-21-1-2-3-1001"


def _c(rid, nome, *, admin=False, ativo=True, logada=False, perfil=True, fonte="Local"):
    return contas.Conta(
        f"S-1-5-21-1-2-3-{rid}",
        nome,
        ativo,
        admin,
        fonte,
        logada,
        None,
        r"C:\Users\x" if perfil else None,
        False,
    )


def test_contas_de_aluno_fechadas():
    lista = contas.Lista(
        (
            _c(500, "Administrador", admin=False),
            _c(1001, "Suporte", admin=True),
            _c(1002, "Teste01"),
            _c(1003, "Teste02", logada=True),
            _c(1004, "Teste03", admin=True),
            _c(1005, "Teste04", ativo=False),
            _c(1006, "Teste05", perfil=False),
            _c(1007, "Teste06", fonte="MicrosoftAccount"),
            _c(1008, "Teste07"),
        ),
        (),
        "PC",
    )
    nomes = [
        c.nome for c in etapas.contas_de_aluno(lista, frozenset({"suporte"}), "S-1-5-21-1-2-3-1008")
    ]
    assert nomes == ["Teste01"]


# ---------------------------------------------------------------- Appx


def test_appx_lista_so_microsoft_e_nomes_validos():
    for n in desinstalar.APPX_PREINSTALADOS:
        assert desinstalar.NOME_APPX.fullmatch(n)
        assert n.lower().startswith(("microsoft.", "clipchamp."))
    assert "Microsoft.WindowsStore" not in desinstalar.APPX_PREINSTALADOS
    assert "Microsoft.WindowsTerminal" not in desinstalar.APPX_PREINSTALADOS


def test_appx_recusa_fora_da_lista_sem_chamar_o_trecho():
    chamadas = []

    def rodar(*a, **k):
        chamadas.append(k)
        return executor.Resultado(0, "", "", 0.1, False)

    fs = desinstalar.remover_appx(["Microsoft.WindowsStore", "Fornecedor.App"], rodar=rodar)
    assert [f.estado for f in fs] == ["pulado", "pulado"] and not chamadas


def test_appx_situacao_filtra_recusas():
    saida = json.dumps(
        [
            {"nome": "Microsoft.BingNews", "recusa": ""},
            {"nome": "Microsoft.ZuneMusic", "recusa": "nao_removivel"},
            {"nome": "Outro.App", "recusa": ""},
        ]
    )

    def rodar(*a, **k):
        return executor.Resultado(0, saida, "", 0.1, False)

    assert desinstalar.appx_presentes(rodar=rodar) == ["Microsoft.BingNews"]


def test_appx_trecho_confere_lista_e_recusas():
    texto = desinstalar.script_appx()
    assert texto.startswith("$LISTA = @('Clipchamp.Clipchamp'")
    for marca in (
        "'System'",
        "NonRemovable",
        "IsFramework",
        "-AllUsers",
        "Remove-AppxProvisionedPackage",
    ):
        assert marca in texto


def test_appx_remove_e_le_saida():
    def rodar(script, **k):
        assert k["nomes"] == "Microsoft.BingNews" and k["acao"] == "remover"
        return executor.Resultado(0, "OK|Microsoft.BingNews\n", "", 0.1, False)

    (f,) = desinstalar.remover_appx(["Microsoft.BingNews"], rodar=rodar)
    assert f.estado == "ok"


def test_appx_recusa_do_trecho():
    def rodar(script, **k):
        return executor.Resultado(0, "ERRO|framework|Microsoft.BingNews\n", "", 0.1, False)

    (f,) = desinstalar.remover_appx(["Microsoft.BingNews"], rodar=rodar)
    assert f.estado == "falha" and "framework" in f.mensagem


# ---------------------------------------------------------------- Limpeza


def test_limpeza_recusa_item_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        limpeza.previa(["perfis"])


def test_limpeza_le_so_numeros(caplog):
    saida = json.dumps(
        [
            {"id": "temp_sistema", "arquivos": 3, "bytes": 2048, "em_uso": 1, "limpo": True},
            {
                "id": "windows_update",
                "arquivos": 0,
                "bytes": 0,
                "em_uso": 0,
                "limpo": False,
                "codigo": "reinicio_pendente",
            },
        ]
    )

    def rodar(script, **k):
        assert k["itens"] == "temp_sistema,windows_update"
        return executor.Resultado(0, saida, "", 0.1, False)

    itens = limpeza.limpar(["temp_sistema", "windows_update"], rodar=rodar)
    assert itens[0].ok and not itens[1].ok and "reinicie" in itens[1].motivo
    assert limpeza.tamanho(2048) == "2,0 KB"


def test_trecho_limpeza_raizes_fixas():
    texto = (Path(limpeza.RECURSOS) / "limpeza.ps1").read_text("utf-8")
    assert "Remove-Item" not in texto and "robocopy" not in texto.lower()
    assert "Set-Service" not in texto and "StartupType" not in texto
    assert "$env:ITC_ITENS" in texto
    assert not re.search(r"\$env:ITC_(?!ACAO|ITENS)", texto)


def _varrer_ps() -> str:
    texto = (Path(limpeza.RECURSOS) / "limpeza.ps1").read_text("utf-8")
    inicio = texto.index("$RP = ")
    fim = texto.index("function Raizes")
    return texto[inicio:fim]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
@pytest.mark.parametrize("acao", ["previa", "limpar"])
def test_varredura_nao_segue_junction(tmp_path, acao):
    raiz = tmp_path / "raiz"
    fora = tmp_path / "fora"
    (raiz / "sub").mkdir(parents=True)
    fora.mkdir()
    (raiz / "a.tmp").write_bytes(b"x" * 10)
    (raiz / "sub" / "b.tmp").write_bytes(b"y" * 20)
    (fora / "importante.txt").write_bytes(b"z" * 1000)
    script = (
        _varrer_ps()
        + "$l = Join-Path $env:ITC_RAIZ 'link'\n"
        + "New-Item -ItemType Junction -Path $l -Target $env:ITC_FORA | Out-Null\n"
        + "$apagar = $env:ITC_ACAO -eq 'limpar'\n"
        + "$acc = @{ arquivos = 0; bytes = [int64]0; em_uso = 0\n"
        + "  pastas_restantes = 0; codigo = '' }\n"
        + "Varrer $env:ITC_RAIZ $acc\n"
        + "ConvertTo-Json -Compress -InputObject ([pscustomobject]$acc)\n"
    )
    r = executor.powershell(script, raiz=str(raiz), fora=str(fora), acao=acao)
    assert r.ok, r.erros
    acc = json.loads(r.saida)
    assert acc["arquivos"] == 2 and acc["bytes"] == 30
    assert (fora / "importante.txt").read_bytes() == b"z" * 1000
    if acao == "limpar":
        assert not os.path.lexists(raiz / "link")
        assert list(raiz.iterdir()) == []
    else:
        assert (raiz / "sub" / "b.tmp").exists()
