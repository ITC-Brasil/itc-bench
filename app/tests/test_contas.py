"""Contas (ADR-017): regras puras, montagem do ambiente, PowerShell real.

Só nomes fictícios. Os testes que criam e apagam contas de verdade rodam apenas com
`ITC_TESTE_CONTAS=1` numa VM de teste elevada (nunca no CI nem numa máquina de uso).
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from itc_bench.nucleo import perfil_conta
from itc_bench.nucleo.elevacao import eh_admin
from itc_bench.servicos import contas, executor
from itc_bench.servicos.cadastros import Cadastros, Servidor
from itc_bench.servicos.contas import Conta, Feito, Lista, recusa, validar_nome
from itc_bench.servicos.executor import Resultado, Sensivel

PROT = frozenset({"suporte"})
SENHA = "Marcador-Senha-7f3a!"
BASE = "S-1-5-21-1-2-3-"


def conta(rid: int, nome: str, **kw: object) -> Conta:
    valores: dict[str, object] = {
        "ativo": True,
        "admin": False,
        "fonte": "Local",
        "logada": False,
        "ultima": None,
        "perfil": None,
        "carregado": False,
    }
    valores.update(kw)
    return Conta(sid=f"{BASE}{rid}", nome=nome, **valores)  # type: ignore[arg-type]


def lista(*cs: Conta) -> Lista:
    return Lista(tuple(cs), (), "PC-TESTE")


NATIVO = conta(500, "Administrador", admin=True, ativo=False)
TECNICO = conta(1001, "Tecnico-Teste", admin=True, logada=True)
SUPORTE = conta(1002, "Suporte", admin=True)
ALUNO = conta(1003, "Aluno-Teste")
MS = conta(1004, "Teste-MS", fonte="MicrosoftAccount", admin=True)


# ---------------------------------------------------------------- nome


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Teste01", None),
        ("Aluno-Novo", None),
        ("", "Digite"),
        ("a" * 21, "20"),
        ("Teste/01", "letras"),
        ("Teste@01", "letras"),
        ("Teste01.", "letras"),
        ("Teste01 ", "letras"),
        (".Teste", "letras"),
        ("ADMINISTRATOR", "reservado"),
        ("convidado", "reservado"),
        ("com3", "reservado"),
        ("LPT9", "reservado"),
        ("SUPORTE", "Suporte"),
        ("pc-teste", "computador"),
        ("aluno-teste", "Já existe"),
        ("ITC", None),  # não é mais protegida (resposta do responsável, 05/11)
    ],
)
def test_validar_nome(nome, esperado):
    problema = validar_nome(nome, lista(ALUNO), PROT)
    assert problema is None if esperado is None else esperado in problema


# ---------------------------------------------------------------- regras


def test_nativo_bloqueia_tudo():
    estado = lista(NATIVO, TECNICO, ALUNO)
    for acao in ("admin", "padrao", "senha", "sem_senha", "excluir"):
        assert recusa(acao, NATIVO, estado, PROT) == "nativo"


def test_conta_microsoft_so_leitura():
    estado = lista(MS, TECNICO)
    for acao in ("admin", "padrao", "senha", "excluir"):
        assert recusa(acao, MS, estado, PROT) == "microsoft"


def test_suporte_protegida_pelo_padrao_e_pelo_cadastrado():
    renomeada = conta(1005, "Suporte-Nova", admin=True)
    estado = lista(SUPORTE, renomeada, TECNICO)
    prot = frozenset({"suporte", "suporte-nova"})
    for alvo in (SUPORTE, renomeada):
        for acao in ("admin", "padrao", "senha", "excluir"):
            assert recusa(acao, alvo, estado, prot) == "suporte"


def test_conta_logada():
    estado = lista(TECNICO, SUPORTE)
    for acao in ("padrao", "senha", "sem_senha", "excluir"):
        assert recusa(acao, TECNICO, estado, PROT) == "logada"
    assert recusa("admin", TECNICO, estado, PROT) is None


def test_ultimo_admin_ativo():
    unico = conta(1010, "Teste01", admin=True)
    desativado = conta(1011, "Teste02", admin=True, ativo=False)
    estado = lista(NATIVO, unico, desativado, ALUNO)
    assert recusa("padrao", unico, estado, PROT) == "ultimo_admin"
    assert recusa("excluir", unico, estado, PROT) == "ultimo_admin"
    outro = conta(1012, "Teste03", admin=True)
    assert recusa("padrao", unico, lista(unico, outro), PROT) is None


def test_perfil_carregado_bloqueia_so_exclusao():
    aberto = conta(1020, "Teste01", carregado=True)
    estado = lista(aberto, SUPORTE)
    assert recusa("excluir", aberto, estado, PROT) == "sessao_aberta"
    assert recusa("admin", aberto, estado, PROT) is None


def test_conta_comum_livre():
    estado = lista(ALUNO, SUPORTE)
    for acao in ("admin", "padrao", "senha", "sem_senha", "excluir"):
        assert recusa(acao, ALUNO, estado, PROT) is None


def test_lote_quem_muda():
    estado = lista(NATIVO, TECNICO, SUPORTE, ALUNO, MS, conta(1030, "Teste01", ativo=False))
    assert contas.mudariam("admin", estado, PROT) == ["Aluno-Teste"]
    # remover administrador: a logada também sai (exceção), Suporte e nativo ficam.
    assert contas.mudariam("padrao", estado, PROT) == ["Tecnico-Teste"]
    assert contas.suporte_ok(estado, PROT)
    sem = lista(TECNICO, conta(1002, "Suporte", admin=False))
    assert not contas.suporte_ok(sem, PROT)
    assert not contas.suporte_ok(lista(conta(1002, "Suporte", admin=True, ativo=False)), PROT)


# ---------------------------------------------------------------- Suporte pelo cadastro


def servidor(i: int, papel: str, valor: str, publico: bool) -> Servidor:
    v: str | Sensivel = valor if publico else Sensivel(valor)
    return Servidor(
        i, contas.SERVICO_SUPORTE, papel, v, "", "" if publico else Sensivel(""), publico
    )


def cad(*servidores: Servidor) -> Cadastros:
    return Cadastros("v", datetime.now(UTC), "t", None, False, servidores, (), (), ())


def test_suporte_do_cadastro():
    assert "sincronize" in contas.suporte_do_cadastro(None)  # type: ignore[operator]
    assert "senha" in contas.suporte_do_cadastro(cad())  # type: ignore[operator]
    nome, senha = contas.suporte_do_cadastro(cad(servidor(1, "senha", SENHA, False)))  # type: ignore[misc]
    assert nome == "Suporte" and senha.revelar() == SENHA
    nome, _ = contas.suporte_do_cadastro(  # type: ignore[misc]
        cad(servidor(1, "senha", SENHA, False), servidor(2, "usuario", "Suporte-Nova", True))
    )
    assert nome == "Suporte-Nova"
    duplicado = cad(servidor(1, "senha", SENHA, False), servidor(2, "senha", "outra", False))
    assert "mais de uma" in contas.suporte_do_cadastro(duplicado)  # type: ignore[operator]
    publica = cad(servidor(1, "senha", SENHA, True))
    assert "não pública" in contas.suporte_do_cadastro(publica)  # type: ignore[operator]
    assert contas.protegidas(cad(servidor(2, "usuario", "Suporte-Nova", True))) == {
        "suporte",
        "suporte-nova",
    }
    assert contas.protegidas(None) == {"suporte"}


# ---------------------------------------------------------------- execução com PowerShell falso


def listagem(*cs: Conta) -> str:
    return json.dumps(
        {
            "contas": [
                {
                    "sid": c.sid,
                    "nome": c.nome,
                    "ativo": c.ativo,
                    "admin": c.admin,
                    "fonte": c.fonte,
                    "logada": c.logada,
                    "ultima": None,
                    "perfil": c.perfil,
                    "carregado": c.carregado,
                }
                for c in cs
            ],
            "outros_admins": [{"sid": "S-1-12-1-9", "nome": "AzureAD\\Teste"}],
            "computador": "PC-TESTE",
        }
    )


class Falso:
    """Responde à listagem com as contas dadas e grava cada chamada de alteração."""

    def __init__(self, *cs: Conta, saida: str = "OK", codigo: int = 0) -> None:
        self.cs, self.saida, self.codigo = cs, saida, codigo
        self.chamadas: list[tuple[str, dict[str, object]]] = []

    def __call__(self, script: str, **kw: object) -> Resultado:
        if "ConvertTo-Json -Compress -Depth 4" in script:
            return Resultado(0, listagem(*self.cs), "", 0.1, False)
        self.chamadas.append((script, kw))
        return Resultado(self.codigo, self.saida, "", 0.1, False)


def test_ler_listagem():
    lido = contas.ler(listagem(TECNICO, ALUNO))
    assert [c.nome for c in lido.contas] == ["Aluno-Teste", "Tecnico-Teste"]
    assert lido.outros_admins == ("AzureAD\\Teste",)
    with pytest.raises(contas.ErroContas):
        contas.ler("{}")


def test_recusa_em_python_nao_chama_powershell():
    falso = Falso(NATIVO, TECNICO, SUPORTE)
    assert not contas.excluir(TECNICO.sid, False, rodar=falso).ok
    assert not contas.trocar_senha(TECNICO.sid, Sensivel(SENHA), rodar=falso).ok
    assert not contas.definir_tipo(NATIVO.sid, "admin", rodar=falso).ok
    assert falso.chamadas == []


def test_senha_so_no_ambiente_e_como_sensivel(caplog):
    falso = Falso(TECNICO, ALUNO, SUPORTE)
    caplog.set_level(logging.DEBUG)
    feito = contas.trocar_senha(ALUNO.sid, Sensivel(SENHA), rodar=falso)
    assert feito.ok
    script, kw = falso.chamadas[0]
    assert isinstance(kw["senha"], Sensivel)
    assert kw["sid"] == ALUNO.sid
    assert SENHA not in script and SENHA not in caplog.text and SENHA not in feito.mensagem
    assert "$env:ITC_SENHA" in script


def test_remover_senha_nao_manda_senha():
    falso = Falso(TECNICO, ALUNO)
    assert contas.trocar_senha(ALUNO.sid, None, rodar=falso).ok
    assert "senha" not in falso.chamadas[0][1]


def test_criar_valida_antes_e_monta_ambiente():
    falso = Falso(TECNICO, ALUNO)
    assert not contas.criar("aluno-teste", None, "padrao", rodar=falso).ok
    assert falso.chamadas == []
    feito = contas.criar("Teste01", Sensivel(SENHA), "admin", clonar_sid=ALUNO.sid, rodar=falso)
    assert feito.ok
    _, kw = falso.chamadas[0]
    assert kw["nome"] == "Teste01" and kw["tipo"] == "admin" and kw["clonar"] == ALUNO.sid
    assert kw["nunca_expira"] == "1" and isinstance(kw["senha"], Sensivel)
    assert kw["protegidas"] == "suporte"


def test_erro_do_powershell_vira_mensagem():
    falso = Falso(TECNICO, ALUNO, saida="ERRO|ultimo_admin|Aluno-Teste", codigo=1)
    feito = contas.definir_tipo(ALUNO.sid, "padrao", rodar=falso)
    assert not feito.ok and "último administrador" in feito.mensagem
    falso = Falso(TECNICO, ALUNO, saida="ERRO|senha|A senha não atende à política", codigo=1)
    assert "política" in contas.trocar_senha(ALUNO.sid, Sensivel("x"), rodar=falso).mensagem


def test_excluir_perfil_que_falhou_e_aviso():
    falso = Falso(
        TECNICO, conta(1003, "Aluno-Teste", perfil="X"), saida="CONTA\nAVISO|perfil|em uso\nOK"
    )
    feito = contas.excluir(ALUNO.sid, True, rodar=falso)
    assert feito.ok and "Limpeza" in feito.mensagem and feito.avisos == ("perfil|em uso",)


def test_lote_padrao_recusa_sem_suporte():
    falso = Falso(TECNICO, ALUNO)
    feito = contas.lote("padrao", rodar=falso)
    assert not feito.ok and "Aplicar conta Suporte" in feito.mensagem and falso.chamadas == []
    falso = Falso(TECNICO, SUPORTE, saida="MUDOU|Tecnico-Teste\nOK")
    feito = contas.lote("padrao", rodar=falso)
    assert feito.ok and feito.alteradas == ("Tecnico-Teste",)


def test_aplicar_suporte_recusas():
    c = cad(servidor(1, "senha", SENHA, False))
    assert not contas.aplicar_suporte(None, rodar=Falso()).ok
    for alvo, texto in ((conta(500, "Suporte"), "nativo"),):
        falso = Falso(alvo)
        assert texto in contas.aplicar_suporte(c, rodar=falso).mensagem
        assert falso.chamadas == []
    falso = Falso(TECNICO, saida="CRIADA\nOK")
    feito = contas.aplicar_suporte(c, rodar=falso)
    assert feito.ok and "criada" in feito.mensagem
    assert isinstance(falso.chamadas[0][1]["senha"], Sensivel)


def test_scripts_cabem_no_limite():
    for nome in ("listar", "criar", "tipo", "senha", "excluir", "suporte", "lote"):
        assert len(executor.ABERTURA_PS + contas.script(nome)) < executor.LIMITE_SCRIPT


def test_tamanho_perfil(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.bin").write_bytes(b"x" * 1000)
    assert contas.tamanho_perfil(str(tmp_path)) == 1000
    assert contas.tamanho_perfil(str(tmp_path), teto=-1) is None
    assert contas.tamanho_perfil(None) is None


def test_sem_wmic_net_user_no_src():
    raiz = Path(contas.__file__).parent.parent
    for arquivo in [*raiz.rglob("*.py"), *raiz.rglob("*.ps1")]:
        texto = arquivo.read_text("utf-8").lower()
        assert "wmic" not in texto, arquivo.name
        assert "net user" not in texto and "net.exe" not in texto, arquivo.name


# ---------------------------------------------------------- PowerShell real (sem alterar nada)


def test_listar_real():
    real = contas.listar()
    assert real.contas and all(c.sid.startswith("S-1-5-21-") for c in real.contas)
    assert not any(c.sid.endswith(("-501", "-503", "-504")) for c in real.contas)


def test_segunda_checagem_no_powershell():
    """As regras de `comum.ps1` sozinhas (Python fora), com contas falsas."""
    teste = (
        "$f = { param($sid, $nome, $fonte) [pscustomobject]@{"
        " SID = [pscustomobject]@{ Value = $sid };"
        " Name = $nome; PrincipalSource = $fonte } }\n"
        f"Write-Output (Recusa 'admin' (& $f '{BASE}500' 'x' 'Local') @() @())\n"
        f"Write-Output (Recusa 'admin' (& $f '{BASE}1' 'x' 'MicrosoftAccount') @() @())\n"
        f"Write-Output (Recusa 'admin' (& $f '{BASE}2' 'SUPORTE-NOVA' 'Local') @() @())\n"
        f"Write-Output (Recusa 'senha' (& $f '{BASE}3' 'x' 'Local') @() @('{BASE}3'))\n"
    )
    r = executor.powershell(
        contas.script("comum") + "\n" + teste, protegidas="suporte\nsuporte-nova"
    )
    assert r.saida.split() == ["nativo", "microsoft", "suporte", "logada"]


# ---------------------------------------------------------- PowerShell real que altera (VM)

so_vm = pytest.mark.skipif(
    os.environ.get("ITC_TESTE_CONTAS") != "1" or not eh_admin(),
    reason="cria e apaga contas: só em VM de teste elevada com ITC_TESTE_CONTAS=1",
)


@so_vm
def test_ciclo_real_em_vm(caplog):
    caplog.set_level(logging.DEBUG)
    l0 = contas.listar()
    for c in l0.contas:
        assert c.nome.lower() != "teste01", "apague Teste01 antes"
    assert contas.criar("Teste01", Sensivel(SENHA), "padrao").ok
    sid = next(c.sid for c in contas.listar().contas if c.nome == "Teste01")
    try:
        assert contas.definir_tipo(sid, "admin").ok
        assert next(c for c in contas.listar().contas if c.sid == sid).admin
        assert contas.definir_tipo(sid, "padrao").ok
        assert contas.trocar_senha(sid, Sensivel(SENHA + "2")).ok
        assert contas.trocar_senha(sid, None).ok
    finally:
        assert contas.excluir(sid, True).ok
    assert SENHA not in caplog.text
    assert all(c.sid != sid for c in contas.listar().contas)


def test_feito_e_imutavel():
    with pytest.raises(AttributeError):
        Feito(True, "x").ok = False  # type: ignore[misc]


def test_senha_fora_da_lista_de_processos():
    """Durante a execução, nenhuma linha de comando (Win32_Process) tem a senha."""
    script = (
        "$m = $env:ITC_SENHA\n"
        "@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
        "$_.CommandLine.Contains($m) }).Count\n"
    )
    r = executor.powershell(script, senha=Sensivel(SENHA))
    assert r.ok and r.saida.strip() == "0"
    assert SENHA not in r.saida and SENHA not in r.erros


def test_aplicar_suporte_com_a_suporte_logada():
    """Emenda do ADR-017: permitido; a tela avisa do cofre de credenciais."""
    from itc_bench.ui.contas import AVISO_SUPORTE_LOGADA, texto_suporte

    c = cad(servidor(1, "senha", SENHA, False))
    logada = conta(1002, "Suporte", admin=True, logada=True)
    falso = Falso(logada, saida="ATUALIZADA\nOK")
    feito = contas.aplicar_suporte(c, rodar=falso)
    assert feito.ok and len(falso.chamadas) == 1
    assert AVISO_SUPORTE_LOGADA in texto_suporte("Suporte", lista(logada))
    assert AVISO_SUPORTE_LOGADA not in texto_suporte("Suporte", lista(SUPORTE))
    # As ações manuais continuam recusando a Suporte.
    assert recusa("senha", logada, lista(logada, TECNICO), PROT) == "suporte"


def test_caminho_de_perfil_fora_do_log(caplog):
    caminho = r"C:\Users\Teste01"
    caplog.set_level(logging.DEBUG)
    aviso = f"CONTA\nAVISO|perfil|0x80041001|Falha ao apagar {caminho}\nOK"
    falso = Falso(TECNICO, conta(1003, "Aluno-Teste", perfil="X"), saida=aviso)
    feito = contas.excluir(ALUNO.sid, True, rodar=falso)
    assert feito.ok and any(caminho in a for a in feito.avisos)  # a tela recebe o detalhe
    assert "perfil: falhou (0x80041001)" in caplog.text
    erro = f"ERRO|senha|Acesso negado em {caminho}"
    falso = Falso(TECNICO, ALUNO, saida=erro, codigo=1)
    feito = contas.trocar_senha(ALUNO.sid, Sensivel("x"), rodar=falso)
    assert caminho in feito.mensagem and "falhou: senha" in caplog.text
    lote = f"AVISO|Aluno-Teste|negado em {caminho}\nOK"
    assert contas.lote("admin", rodar=Falso(TECNICO, ALUNO, saida=lote)).ok
    assert caminho not in caplog.text


# ---------------------------------------------------- filtro e encerrar sessão (ADR-036)


def test_modificavel() -> None:
    prot = frozenset({"suporte"})
    assert contas.modificavel(ALUNO, prot) and contas.modificavel(TECNICO, prot)
    assert not contas.modificavel(NATIVO, prot)
    assert not contas.modificavel(SUPORTE, prot)
    assert not contas.modificavel(MS, prot)


def test_com_sessao() -> None:
    aberta = conta(1005, "Aberta", carregado=True)
    lido = lista(TECNICO, ALUNO, aberta)
    assert [c.nome for c in contas.com_sessao(lido)] == ["Tecnico-Teste", "Aberta"]


def test_encerrar_sessao_pelo_sid_trecho_so_le_e_logoff_pela_api() -> None:
    falso = Falso(TECNICO, ALUNO, saida="SESSAO|2\nSESSAO|3\nOK")
    pedidas: list[int] = []
    feito = contas.encerrar_sessao(
        ALUNO.sid, rodar=falso, encerrar=lambda n: pedidas.append(n) or 0
    )
    assert feito.ok and "Aluno-Teste" in feito.mensagem
    assert pedidas == [2, 3]
    script, kw = falso.chamadas[0]
    assert kw == {"timeout": contas.TIMEOUT_ACAO, "sid": ALUNO.sid}
    assert "GetCurrentProcess().SessionId" in script and "SESSAO|" in script
    # O logoff.exe não existe no Windows Home, e Add-Type é proibido nos trechos (ADR-049).
    sem_comentarios = "\n".join(
        linha for linha in script.splitlines() if not linha.lstrip().startswith("#")
    )
    assert "logoff" not in sem_comentarios.lower() and "Add-Type" not in script


@pytest.mark.parametrize(
    ("saida", "trecho"),
    [
        ("ERRO|propria|", "o Bench está rodando"),
        ("ERRO|sem_sessao|", "não tem sessão aberta"),
        ("ERRO|nao_encontrada|", "não existe mais"),
    ],
)
def test_encerrar_sessao_recusas_do_trecho_nao_chamam_a_api(saida: str, trecho: str) -> None:
    pedidas: list[int] = []
    feito = contas.encerrar_sessao(
        ALUNO.sid,
        rodar=Falso(TECNICO, ALUNO, saida=saida, codigo=1),
        encerrar=lambda n: pedidas.append(n) or 0,
    )
    assert not feito.ok and trecho in feito.mensagem and pedidas == []


def test_encerrar_sessao_falha_da_api_para_e_mostra_o_codigo() -> None:
    pedidas: list[int] = []
    feito = contas.encerrar_sessao(
        ALUNO.sid,
        rodar=Falso(TECNICO, ALUNO, saida="SESSAO|2\nSESSAO|3\nOK"),
        encerrar=lambda n: pedidas.append(n) or 1314,
    )
    assert not feito.ok
    assert feito.mensagem == "O Windows não encerrou a sessão: sessão 2, código 1314"
    assert pedidas == [2]


def test_encerrar_sessao_saida_sem_sessao_valida_nao_chama_a_api() -> None:
    pedidas: list[int] = []
    feito = contas.encerrar_sessao(
        ALUNO.sid,
        rodar=Falso(TECNICO, ALUNO, saida="SESSAO|abc\nSESSAO|1;2\nOK"),
        encerrar=lambda n: pedidas.append(n) or 0,
    )
    assert not feito.ok and "não tem sessão aberta" in feito.mensagem and pedidas == []


def test_encerrar_sessao_conta_que_sumiu() -> None:
    falso = Falso(TECNICO)
    feito = contas.encerrar_sessao(ALUNO.sid, rodar=falso)
    assert not feito.ok and "não existe mais" in feito.mensagem and falso.chamadas == []


def test_encerrar_sessao_sem_injecao_usa_o_nucleo_que_os_testes_bloqueiam() -> None:
    with pytest.raises(AssertionError, match="sessão de verdade"):
        contas.encerrar_sessao(ALUNO.sid, rodar=Falso(TECNICO, ALUNO, saida="SESSAO|2\nOK"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_nucleo_sessoes_recusa_a_propria_e_a_zero_sem_chamar_o_windows() -> None:
    import importlib

    import itc_bench.nucleo.sessoes as modulo

    real = importlib.reload(modulo)  # sem o bloqueio do conftest, só para estas recusas
    try:
        assert real.encerrar(0) == real.ERRO_RECUSADA
        assert real.encerrar(real.sessao_atual()) == real.ERRO_RECUSADA
    finally:
        importlib.reload(modulo)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
def test_encerrar_real_recusa_sid_invalido() -> None:
    r = executor.powershell(contas.script("encerrar"), sid="nao-e-sid")
    assert "ERRO|nao_encontrada" in r.saida


# ---------------------------------------------------- Gestão restrita (ADR-036)

GESTAO = conta(1006, "Gestão", admin=True)


def test_gestao_nao_modificavel_e_recusada_em_toda_acao() -> None:
    lido = lista(TECNICO, ALUNO, GESTAO)
    assert not contas.modificavel(GESTAO, PROT)
    assert not contas.modificavel(conta(1007, "GESTAO"), PROT)  # sem acento e maiúsculas
    for acao in ("admin", "padrao", "senha", "sem_senha", "excluir"):
        assert recusa(acao, GESTAO, lido, PROT) == "restrita"  # type: ignore[arg-type]
    assert "Gestão é protegida" in contas.MENSAGENS["restrita"]


def test_gestao_fora_do_lote_e_nao_conta_como_suporte() -> None:
    lido = lista(TECNICO, ALUNO, GESTAO, conta(1008, "Outro", ativo=True))
    assert "Gestão" not in contas.mudariam("padrao", lido, PROT)
    assert "Gestão" not in contas.mudariam("admin", lista(conta(1006, "Gestão")), PROT)
    assert not contas.suporte_ok(lista(GESTAO), PROT)  # Gestão admin não vale como Suporte


def test_nome_gestao_reservado_na_criacao() -> None:
    assert "Gestão" in (validar_nome("gestão", lista(ALUNO), PROT) or "")
    assert "Gestão" in (validar_nome("Gestao", lista(ALUNO), PROT) or "")


def test_trechos_tem_a_mesma_lista_de_restritas() -> None:
    comum = (contas.RECURSOS / "comum.ps1").read_text("utf-8")
    assert "$RESTRITAS = @('Gestão', 'Gestao')" in comum
    assert "return 'restrita'" in comum
    assert "$RESTRITAS -contains $nome" in contas.script("criar")
    assert "-not ($RESTRITAS -contains $_.Name)" in contas.script("lote")
    assert {"gestão", "gestao"} == contas.RESTRITAS


@pytest.mark.skipif(sys.platform != "win32", reason="Windows")
@pytest.mark.parametrize("nome", ["Gestão", "gestao", "GESTÃO"])
def test_recusa_real_da_gestao_no_powershell(nome: str) -> None:
    """Só a função Recusa do trecho, com uma conta fictícia; nada é alterado no Windows."""
    teste = (
        (contas.RECURSOS / "comum.ps1").read_text("utf-8")
        + "\n$c = [pscustomobject]@{ Name = $env:ITC_NOME; PrincipalSource = 'Local';"
        + " SID = [pscustomobject]@{ Value = 'S-1-5-21-1-2-3-1006' } }\n"
        + "Write-Output ('MOTIVO|' + (Recusa 'senha' $c @() @()))\n"
    )
    r = executor.powershell(teste, nome=nome)
    assert "MOTIVO|restrita" in r.saida


# ---------------------------------------------------- perfil sem entrar (ADR-050)

SID_NOVO = "S-1-5-21-1-2-3-1050"


def test_criar_prepara_o_perfil_com_o_sid_do_trecho() -> None:
    falso = Falso(TECNICO, ALUNO, saida=f"SID|{SID_NOVO}\nOK")
    pedidos: list[tuple[str, str]] = []
    feito = contas.criar(
        "Teste01",
        None,
        "padrao",
        rodar=falso,
        criar_perfil=lambda s, n: pedidos.append((s, n)) or 0,
    )
    assert feito.ok and "Perfil preparado" in feito.mensagem and feito.avisos == ()
    assert pedidos == [(SID_NOVO, "Teste01")]
    assert "SID|" in falso.chamadas[0][0]  # o trecho informa o SID da conta nova


def test_perfil_que_ja_existe_conta_como_preparado() -> None:
    falso = Falso(TECNICO, saida=f"SID|{SID_NOVO}\nOK")
    feito = contas.criar(
        "Teste01", None, "padrao", rodar=falso, criar_perfil=lambda _s, _n: perfil_conta.JA_EXISTE
    )
    assert feito.ok and "Perfil preparado" in feito.mensagem


def test_falha_do_perfil_nao_desfaz_a_conta(caplog) -> None:
    falso = Falso(TECNICO, saida=f"SID|{SID_NOVO}\nOK")
    feito = contas.criar(
        "Teste01", None, "padrao", rodar=falso, criar_perfil=lambda _s, _n: -2147024891
    )
    assert feito.ok and feito.mensagem == "Conta Teste01 criada."
    assert feito.avisos == (f"{contas.PERFIL_NAO_PREPARADO} (código 0x80070005)",)
    assert "0x80070005" in caplog.text and "Users" not in caplog.text


def test_sem_sid_do_trecho_nao_chama_o_windows() -> None:
    pedidos: list[str] = []
    feito = contas.criar(
        "Teste01",
        None,
        "padrao",
        rodar=Falso(TECNICO, saida="SID|nao-e-sid\nOK"),
        criar_perfil=lambda s, _n: pedidos.append(s) or 0,
    )
    assert feito.ok and feito.avisos == (contas.PERFIL_NAO_PREPARADO,) and pedidos == []


def test_conta_que_falhou_nao_prepara_perfil() -> None:
    pedidos: list[str] = []
    feito = contas.criar(
        "Teste01",
        None,
        "padrao",
        rodar=Falso(TECNICO, saida="ERRO|criar|recusado", codigo=1),
        criar_perfil=lambda s, _n: pedidos.append(s) or 0,
    )
    assert not feito.ok and pedidos == []


# ---------------------------------------------------- sem animação do primeiro logon (ADR-051)


def test_trecho_criar_desliga_a_animacao_do_primeiro_logon() -> None:
    trecho = contas.script("criar")
    assert "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" in trecho
    assert "-Name 'EnableFirstLogonAnimation' -PropertyType DWord -Value 0" in trecho
    # depois de criar a conta e antes do SID: falha vira aviso, não desfaz a conta
    assert trecho.index("New-LocalUser") < trecho.index("EnableFirstLogonAnimation")
    assert trecho.index("EnableFirstLogonAnimation") < trecho.index("'SID|'")
    assert "AVISO|animacao|" in trecho


def test_trecho_criar_pula_a_tela_de_privacidade_com_as_respostas() -> None:
    """ADR-054: localização sim; o resto não; tudo antes do SID, falha vira aviso."""
    trecho = contas.script("criar")
    esperado = {
        "'DisablePrivacyExperience', 1",
        "'AllowTelemetry', 1",
        "'AllowInputPersonalization', 0",
        "'DisabledByGroupPolicy', 1",
        "'AllowFindMyDevice', 0",
    }
    for valor in esperado:
        assert valor in trecho
    assert "ConsentStore\\location" in trecho and "-Value 'Allow'" in trecho
    assert trecho.index("New-LocalUser") < trecho.index("DisablePrivacyExperience")
    assert trecho.index("DisablePrivacyExperience") < trecho.index("'SID|'")
    assert "AVISO|privacidade|" in trecho
    # só chaves da máquina, nada de HKCU
    assert "HKCU:" not in trecho


def test_falha_da_animacao_vira_aviso_e_a_conta_fica() -> None:
    aviso = "animacao|Animação do primeiro logon não desligada: negado"
    falso = Falso(TECNICO, saida=f"AVISO|{aviso}\nSID|{SID_NOVO}\nOK")
    feito = contas.criar("Teste01", None, "padrao", rodar=falso, criar_perfil=lambda _s, _n: 0)
    assert feito.ok and aviso in feito.avisos


def test_criar_sem_injecao_usa_o_nucleo_que_os_testes_bloqueiam() -> None:
    with pytest.raises(AssertionError, match="perfil de verdade"):
        contas.criar("Teste01", None, "padrao", rodar=Falso(TECNICO, saida=f"SID|{SID_NOVO}\nOK"))


@pytest.mark.parametrize(
    ("sid", "nome"),
    [
        ("S-1-5-18", "Teste01"),  # SYSTEM, não é conta local
        (SID_NOVO, ""),
        (SID_NOVO, "a" + chr(92) + "b"),  # barra invertida
        (SID_NOVO, "a" + chr(8) + "b"),  # caractere de controle
        (SID_NOVO, "a/b"),
        (SID_NOVO, "nome-com-mais-de-vinte"),
        (SID_NOVO, "termina."),
        (SID_NOVO, "termina "),
    ],
)
def test_nucleo_perfil_recusa_formato_sem_chamar_o_windows(monkeypatch, sid, nome) -> None:
    import importlib

    import itc_bench.nucleo.perfil_conta as modulo

    real = importlib.reload(modulo)  # tira o bloqueio do conftest, só para as recusas
    # E garante que, mesmo assim, o Windows nunca é chamado neste teste.
    monkeypatch.setattr(real, "_userenv", lambda: (_ for _ in ()).throw(AssertionError("chamou")))
    assert real.criar(sid, nome) == real.RECUSADO
