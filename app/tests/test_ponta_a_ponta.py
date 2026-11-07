"""Ponta a ponta simulado (Módulo 14): Preparação completa dos três perfis com os serviços reais.

Nada toca a máquina: o único ponto de processo (`subprocess.Popen` do executor) é falso e
falha ecoando os dados `ITC_*` no stderr, como um erro do PowerShell faria; Wi-Fi (wlanapi),
escrita no registro e rede levantam erro; qualquer escrita em disco fora da pasta do teste é
recusada e registrada. Os cadastros levam marcadores no lugar de segredos e dados reais.
"""

import base64
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError

import pytest

from itc_bench.nucleo import caminhos, wlan
from itc_bench.servicos import (
    api,
    cadastros,
    contas,
    etapas,
    executor,
    identificacao,
    instaladores,
    perfis,
    remoto,
)
from itc_bench.servicos import preparacao as prep

SID = "S-1-5-21-111-222-333-1002"
MARCADORES = {
    "senha do Wi-Fi": "Mk-WifiSenha-91",
    "SSID": "Mk-SSID-Carreta",
    "host": "srv.mk-host.invalid",
    "host do download": "dl.mk-host.invalid",
    "chave RustDesk": "MkChaveRust7xyz",
    "senha RustDesk": "Mk-RustSenha-2",
    "senha AnyDesk": "Mk-AnySenha-3",
    "senha Suporte": "Mk-SupSenha-4",
    "tag GLPI": "MkTagGlpi",
    "SID": SID,
    "perfil": r"C:\Users\MkAluno",
}
# Nos argumentos e no log nunca; no ambiente do filho só como ITC_* (ADR-011).
SITUACOES = {"feito", "pendente", "falhou", "bloqueada", "pulada", "nao_lida", "parcial"}


def _servidor(i, servico, papel, valor, publico=False):
    return dict(
        id=i, servico=servico, papel=papel, valor=valor, versao="", observacao="", publico=publico
    )


def _cadastros() -> cadastros.Cadastros:
    m = MARCADORES
    dados = {
        "servidores": [
            _servidor(1, "Conta Suporte", "usuario", "Suporte", True),
            _servidor(2, "Conta Suporte", "senha", m["senha Suporte"]),
            _servidor(3, "RustDesk", "servidor", m["host"], True),
            _servidor(4, "RustDesk", "chave", m["chave RustDesk"]),
            _servidor(5, "RustDesk", "senha", m["senha RustDesk"]),
            _servidor(6, "AnyDesk", "senha", m["senha AnyDesk"]),
            _servidor(7, "GLPI Agent", "servidor", f"https://{m['host']}/", True),
        ],
        "instaladores": [
            dict(
                id=i,
                programa=programa,
                versao="1.0",
                arquivo=arquivo,
                sha256="ab" * 32,
                link=f"https://{m['host do download']}/{arquivo}",
                observacao="",
                tipo=tipo,
                categoria=categoria,
            )
            for i, programa, arquivo, tipo, categoria in (
                (1, "Programa Mk", "mk.msi", "instalador", "Programas"),
                (2, "RustDesk", "rustdesk.msi", "instalador", "Acesso remoto"),
                (3, "AnyDesk", "anydesk.msi", "instalador", "Acesso remoto"),
                (4, "GLPI Agent", "glpi.msi", "instalador", "Acesso remoto"),
                (5, "Fundo", "fundo.png", "papel", "Papel"),
            )
        ],
        "wifi": [
            dict(
                id=1,
                ssid=m["SSID"],
                senha=m["senha do Wi-Fi"],
                unidade="ABC01",
                categoria="Carreta",
                atualizado_em="",
            )
        ],
        "unidades": [
            dict(
                id=1,
                codigo="ABC01",
                nome="Unidade Teste",
                cidade="",
                uf="",
                tag_glpi=m["tag GLPI"],
                perfil_padrao="sala_de_aula",
            )
        ],
    }
    registro = {
        "versao": "v" * 16,
        "sincronizado_em": datetime.now(UTC).isoformat(),
        "por": "tecnico",
        "unidade": "ABC01",
        "dados": dados,
    }
    return cadastros._de_dados(registro)


def _lista() -> contas.Lista:
    def conta(rid, nome, admin=False, ativo=True, perfil=None):
        return contas.Conta(
            f"S-1-5-21-111-222-333-{rid}", nome, ativo, admin, "Local", False, None, perfil, False
        )

    return contas.Lista(
        (
            conta(500, "Administrador", admin=True, ativo=False),
            conta(1001, "Tecnico", admin=True),  # sem Suporte: a etapa cria (senha pelo executor)
            conta(1002, "Teste01", perfil=MARCADORES["perfil"]),
            conta(1003, "Teste02", admin=True, perfil=MARCADORES["perfil"] + "2"),
        ),
        (),
        "PC-TESTE",
    )


class Processos:
    """O `Popen` falso: guarda argumentos, ambiente e entrada; sai com código 1."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[list[str], dict[str, str], bytes | None]] = []

    def __call__(self, argumentos, *, env, stdin, **_):
        dados_itc = [v for k, v in env.items() if k.upper().startswith("ITC_")]
        registro = (list(argumentos), dict(env), None)
        self.chamadas.append(registro)
        chamadas = self.chamadas

        class Falso:
            pid = 0
            returncode = 1
            stdin = None

            def communicate(self, dados=None, timeout=None):
                chamadas[-1] = (registro[0], registro[1], dados)
                # Pior caso: o erro do PowerShell repete os dados recebidos.
                return b"", ("erro com " + " ".join(dados_itc)).encode()

            def kill(self):
                pass

        return Falso()

    def scripts(self) -> list[str]:
        saida = []
        for argumentos, _env, _dados in self.chamadas:
            if "-EncodedCommand" in argumentos:
                cod = argumentos[argumentos.index("-EncodedCommand") + 1]
                saida.append(base64.b64decode(cod).decode("utf-16-le"))
        return saida


@pytest.fixture
def isolado(monkeypatch, tmp_path):
    """Nada sai da pasta do teste; o que tentar sair é recusado e anotado."""
    fora: list[str] = []
    base = str(tmp_path).lower()

    def guarda(nome):
        original = getattr(Path, nome)

        def checado(self, *a, **k):
            modo = a[0] if a else k.get("mode", "r")
            escrita = nome != "open" or any(c in str(modo) for c in "wax+")
            if escrita and not str(self).lower().startswith(base):
                fora.append(f"{nome} {self}")
                raise PermissionError("fora da pasta do teste")
            return original(self, *a, **k)

        monkeypatch.setattr(Path, nome, checado)

    for nome in ("write_text", "write_bytes", "replace", "rename", "unlink", "mkdir", "open"):
        guarda(nome)

    def recusa(*_a, **_k):
        raise OSError("bloqueado no teste")

    pd = tmp_path / "pd"
    (pd / "ITC" / "Bench" / "protegido").mkdir(parents=True)
    monkeypatch.setattr(caminhos, "programdata", lambda: pd)
    processos = Processos()
    monkeypatch.setattr(executor.subprocess, "Popen", processos)
    monkeypatch.setattr(executor, "_Job", lambda pid: _JobFalso())
    monkeypatch.setattr(wlan, "_dll", recusa)
    import winreg

    for nome in ("SetValueEx", "CreateKeyEx", "CreateKey", "DeleteValue", "DeleteKey"):
        monkeypatch.setattr(winreg, nome, recusa)

    def sem_rede(*_a, **_k):
        raise URLError("sem rede no teste")

    monkeypatch.setattr(instaladores._abridor, "open", sem_rede)
    monkeypatch.setattr(api._abridor, "open", sem_rede)
    monkeypatch.setattr(remoto, "gravar_atomico", recusa)
    monkeypatch.setattr(contas, "listar", lambda **_k: _lista())
    return processos, fora


class _JobFalso:
    def encerrar(self):
        pass

    def fechar(self):
        pass


def _rodar_perfis(admin: bool) -> dict[str, prep.Andamento]:
    cad = _cadastros()
    saida = {}
    for perfil in perfis.PERFIS:
        ctx = etapas.Contexto(admin=admin, cadastros=cad, unidade="ABC01", alvos=(SID,))
        andamento = prep.Andamento(perfil.id, list(perfil.etapas), {})
        saida[perfil.id] = prep.rodar(etapas.montar(ctx), andamento, pausar=threading.Event())
    return saida


def _vazamentos(texto: str) -> list[str]:
    return [nome for nome, valor in MARCADORES.items() if valor.lower() in texto.lower()]


def test_preparacao_completa_simulada_sem_vazar_dado(isolado, caplog):
    processos, fora = isolado
    with caplog.at_level(logging.DEBUG):
        resultado = _rodar_perfis(admin=True)
    assert not fora, "escrita fora da pasta do teste"
    for perfil, andamento in resultado.items():
        assert set(andamento.situacao) == set(andamento.etapas), perfil
        assert {s.situacao for s in andamento.situacao.values()} <= SITUACOES, perfil
    assert processos.chamadas, "a simulação tem que chegar ao executor"
    for argumentos, env, _dados in processos.chamadas:
        assert not _vazamentos(" ".join(argumentos)), argumentos[:1]
        fora_itc = " ".join(v for k, v in env.items() if not k.upper().startswith("ITC_"))
        assert not _vazamentos(fora_itc)
    for script in processos.scripts():
        assert not _vazamentos(script)
    assert not _vazamentos(caplog.text)


def test_preparacao_sem_admin_nao_altera_nada(isolado, caplog):
    processos, fora = isolado
    with caplog.at_level(logging.DEBUG):
        resultado = _rodar_perfis(admin=False)
    assert not fora
    # Sem administrador só lê (ADR-017 a 023): nenhum trecho que altera roda.
    leituras = {executor.ABERTURA_PS + identificacao.script("estado")}
    assert len(processos.scripts()) == len(processos.chamadas)
    assert set(processos.scripts()) <= leituras
    for andamento in resultado.values():
        assert {s.situacao for s in andamento.situacao.values()} <= {
            "bloqueada",
            "pulada",
            "falhou",
        }  # falhou: leitura falsa
    assert not _vazamentos(caplog.text)
