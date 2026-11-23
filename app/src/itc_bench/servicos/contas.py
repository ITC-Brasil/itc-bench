"""Contas locais da máquina (ADR-017), sem Qt: a tela Contas e a Preparação completa (13) usam.

Cada trecho PowerShell de `recursos/contas/` roda pelo executor com os dados em `ITC_*`. A conta
alvo vai sempre pelo SID. As regras de `recusa()` são conferidas aqui, sobre uma leitura nova, e
de novo dentro do trecho que altera (`comum.ps1`).
"""

import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any, Literal

from itc_bench.nucleo import perfil_conta, sessoes
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.executor import Sensivel

RECURSOS = resources.files("itc_bench.recursos") / "contas"
SUPORTE_PADRAO = "Suporte"
SERVICO_SUPORTE = "Conta Suporte"
# Contas restritas fixas (ADR-036): o Bench não as altera nem as mexe em lote, como a Suporte,
# mas não contam como Suporte. Mesma lista em `recursos/contas/comum.ps1` ($RESTRITAS).
RESTRITAS = frozenset({"gestão", "gestao"})
# Conta Gestão (ADR-069): por enquanto igual à Suporte, pela linha própria em Servidores.
# Opcional: sem as linhas, o Bench não mexe nela. O nome é sempre um das RESTRITAS.
GESTAO_PADRAO = "Gestão"
SERVICO_GESTAO = "Conta Gestão"
TIMEOUT_LISTA, TIMEOUT_ACAO, TIMEOUT_LOTE = 30.0, 60.0, 120.0
TEMPO_TAMANHO = 5.0  # teto para medir o perfil na confirmação de exclusão

NOME = re.compile(r"^\w[\w .-]{0,19}$")
RESERVADOS = frozenset(
    {"administrador", "administrator", "convidado", "guest", "defaultaccount"}
    | {"wdagutilityaccount", "system", "con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

Acao = Literal["admin", "padrao", "senha", "sem_senha", "excluir"]
Rodar = Callable[..., executor.Resultado]

MENSAGENS = {
    "nativo": "O Administrador nativo do Windows não é alterado pelo Bench.",
    "microsoft": "Conta Microsoft ou de domínio: no Bench, só leitura.",
    "suporte": "A conta Suporte só muda por “Aplicar conta Suporte”.",
    "logada": "Conta em uso agora (sessão aberta ou rodando o Bench).",
    "ultimo_admin": "É o último administrador ativo: crie ou promova outro antes.",
    "sessao_aberta": "A conta está com a sessão aberta: saia dela ou reinicie antes de excluir.",
    "nao_encontrada": "A conta não existe mais. Atualize a lista.",
    "nome_existe": "Já existe uma conta com esse nome.",
    "nome_grupo": "Já existe um grupo local com esse nome.",
    "nome_computador": "O nome da conta não pode ser igual ao nome do computador.",
    "suporte_nativo": "O nome da conta Suporte é o do Administrador nativo. Corrija o cadastro.",
    "suporte_ausente": "A conta Suporte não existe, está desativada ou não é administradora. "
    "Rode “Aplicar conta Suporte” antes.",
    "parcial": "A conta foi criada, mas um passo seguinte falhou",
    # Encerrar sessão (ADR-036)
    "restrita": "A conta Gestão é protegida: o Bench não a altera.",
    "sem_sessao": "A conta não tem sessão aberta agora.",
    "propria": "É a sessão em que o Bench está rodando: saia pelo próprio Windows.",
    "encerrar": "O Windows não encerrou a sessão",
}
# ADR-050: a conta foi criada, mas o perfil fica para o primeiro logon, como antes.
PERFIL_NAO_PREPARADO = "Perfil não preparado: entre na conta uma vez antes de aplicar políticas"


@dataclass(frozen=True)
class Conta:
    sid: str
    nome: str
    ativo: bool
    admin: bool
    fonte: str  # Local | MicrosoftAccount | AzureAD | ...
    logada: bool
    ultima: datetime | None
    perfil: str | None  # caminho do perfil: nunca vai para o log
    carregado: bool
    bench: bool = False  # a conta que roda o Bench (ADR-071); só para mostrar o motivo

    @property
    def nativo(self) -> bool:
        return self.sid.endswith("-500")

    @property
    def local(self) -> bool:
        return self.fonte in ("", "Local")


@dataclass(frozen=True)
class Lista:
    contas: tuple[Conta, ...]
    outros_admins: tuple[str, ...]  # membros de domínio/AzureAD do grupo Administradores
    computador: str

    def por_sid(self, sid: str) -> Conta | None:
        return next((c for c in self.contas if c.sid == sid), None)


@dataclass(frozen=True)
class Feito:
    ok: bool
    mensagem: str
    alteradas: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()


class ErroContas(RuntimeError):
    """Falha ao ler as contas (tempo esgotado, saída inválida)."""


# ---------------------------------------------------------------- regras (puras)


def protegidas(cadastros: Cadastros | None) -> frozenset[str]:
    """Nomes da Suporte, em minúsculas: sempre `Suporte` e o nome cadastrado (ADR-017, ajuste 2)."""
    nomes = {SUPORTE_PADRAO.lower()}
    for s in cadastros.servidores if cadastros else ():
        if s.servico == SERVICO_SUPORTE and s.papel == "usuario" and isinstance(s.valor, str):
            nomes.add(s.valor.strip().lower())
    return frozenset(n for n in nomes if n)


def tecnica(conta: Conta, cadastros: Cadastros | None) -> bool:
    """Suporte, Gestão ou o Administrador nativo (ADR-082): as contas da Manutenção. A Gestão
    tem sempre um dos nomes de RESTRITAS (ADR-069)."""
    nome = conta.nome.lower()
    return conta.nativo or nome in protegidas(cadastros) or nome in RESTRITAS


def validar_nome(
    nome: str,
    lista: Lista | None,
    protegidas_: Iterable[str],
    *,
    permitir_nome_computador: bool = False,
) -> str | None:
    """Mensagem do problema, ou None se o nome serve. O PowerShell confere de novo.

    `permitir_nome_computador`: só as contas por turno (ADR-029) aceitam o nome igual ao do
    computador; a tela Contas continua recusando.
    """
    if not nome:
        return "Digite o nome da conta."
    if len(nome) > 20:
        return "Use até 20 caracteres."
    if not NOME.fullmatch(nome) or nome.endswith((".", " ")):
        return "Use letras, números, espaço, ponto, hífen ou _; sem terminar em ponto ou espaço."
    baixo = nome.lower()
    if baixo in RESERVADOS:
        return "Nome reservado pelo Windows."
    if baixo in protegidas_:
        return "Nome reservado para a conta Suporte."
    if baixo in RESTRITAS:
        return "Nome reservado para a conta Gestão."
    if lista is not None:
        if baixo == lista.computador.lower() and not permitir_nome_computador:
            return MENSAGENS["nome_computador"]
        if any(c.nome.lower() == baixo for c in lista.contas):
            return MENSAGENS["nome_existe"]
    return None


def recusa(acao: Acao, conta: Conta, lista: Lista, protegidas_: Iterable[str]) -> str | None:
    """Código da regra que impede a ação, ou None (mesma ordem de `Recusa` em `comum.ps1`)."""
    if conta.nativo:
        return "nativo"
    if not conta.local:
        return "microsoft"
    if conta.nome.lower() in protegidas_:
        return "suporte"
    if conta.nome.lower() in RESTRITAS:
        return "restrita"
    if acao in ("padrao", "excluir", "senha", "sem_senha") and conta.logada:
        return "logada"
    if acao in ("padrao", "excluir") and conta.admin:
        outros = [c for c in lista.contas if c.sid != conta.sid and c.admin and c.ativo]
        if not outros:
            return "ultimo_admin"
    if acao == "excluir" and conta.carregado:
        return "sessao_aberta"
    return None


def mudariam(
    lote: Literal["admin", "padrao"], lista: Lista, protegidas_: Iterable[str]
) -> list[str]:
    """Quem a ação em lote altera, para a confirmação (o PowerShell recalcula)."""
    prot = set(protegidas_)
    locais = [
        c for c in lista.contas if c.local and not c.nativo and c.nome.lower() not in RESTRITAS
    ]
    if lote == "admin":
        return [c.nome for c in locais if c.ativo and not c.admin]
    return [c.nome for c in locais if c.admin and c.nome.lower() not in prot]


def suporte_ok(lista: Lista, protegidas_: Iterable[str]) -> bool:
    prot = set(protegidas_)
    return any(
        c.nome.lower() in prot and c.ativo and c.admin and c.local and not c.nativo
        for c in lista.contas
    )


def _conta_do_cadastro(
    cadastros: Cadastros | None, servico: str, padrao: str
) -> tuple[str, Sensivel] | str:
    """(nome, senha) das linhas `servico` em Servidores, ou a mensagem do que falta."""
    if cadastros is None:
        return "Sem cadastros: conecte e sincronize em Configurações."
    linhas = [s for s in cadastros.servidores if s.servico == servico]
    usuarios = [s for s in linhas if s.papel == "usuario"]
    senhas = [s for s in linhas if s.papel == "senha"]
    if len(usuarios) > 1 or len(senhas) > 1:
        return f"Há mais de uma linha “{servico}” para o mesmo papel em Servidores."
    if not senhas or not isinstance(senhas[0].valor, Sensivel) or not senhas[0].valor.revelar():
        return f"Cadastre “{servico}” / senha (não pública) em Servidores e sincronize."
    nome = padrao
    if usuarios:
        if not isinstance(usuarios[0].valor, str):
            return f"A linha “{servico}” / usuario tem que ser pública."
        nome = usuarios[0].valor.strip() or padrao
    return nome, senhas[0].valor


def suporte_do_cadastro(cadastros: Cadastros | None) -> tuple[str, Sensivel] | str:
    """(nome, senha) da conta Suporte, ou a mensagem do que falta (ADR-008, ADR-017)."""
    return _conta_do_cadastro(cadastros, SERVICO_SUPORTE, SUPORTE_PADRAO)


def gestao_cadastrada(cadastros: Cadastros | None) -> bool:
    """Há alguma linha “Conta Gestão” em Servidores? Sem nenhuma, o Bench não mexe (ADR-069)."""
    return cadastros is not None and any(s.servico == SERVICO_GESTAO for s in cadastros.servidores)


def gestao_do_cadastro(cadastros: Cadastros | None) -> tuple[str, Sensivel] | str:
    """(nome, senha) da conta Gestão (ADR-069). O nome tem que ser Gestão (ou Gestao): é o
    nome que as outras ações do Bench já protegem (ADR-036)."""
    origem = _conta_do_cadastro(cadastros, SERVICO_GESTAO, GESTAO_PADRAO)
    if isinstance(origem, tuple) and origem[0].lower() not in RESTRITAS:
        return "A linha “Conta Gestão” / usuario tem que ser Gestão."
    return origem


def gestao_ok(lista: Lista) -> bool:
    """A Gestão existe, local, ativa e administradora."""
    return any(
        c.nome.lower() in RESTRITAS and c.ativo and c.admin and c.local and not c.nativo
        for c in lista.contas
    )


# ---------------------------------------------------------------- execução


def script(nome: str) -> str:
    return (
        (RECURSOS / "comum.ps1").read_text("utf-8")
        + "\n"
        + (RECURSOS / f"{nome}.ps1").read_text("utf-8")
    )


def _ambiente_protegidas(protegidas_: Iterable[str]) -> str:
    return "\n".join(sorted(n.replace("\n", "") for n in protegidas_))


def _linhas(resultado: executor.Resultado) -> list[str]:
    return [linha.strip() for linha in resultado.saida.splitlines() if linha.strip()]


def _erro(resultado: executor.Resultado) -> str:
    if resultado.esgotado:
        return "Tempo esgotado."
    for linha in _linhas(resultado):
        if linha.startswith("ERRO|"):
            _, codigo, detalhe = [*linha.split("|", 2), "", ""][:3]
            base = MENSAGENS.get(codigo)
            if codigo in ("criar", "senha", "tipo", "excluir", "suporte", "parcial", "encerrar"):
                return f"{base}: {detalhe}" if base else detalhe or "Falha do Windows."
            return base or detalhe or codigo
    return f"Falha do PowerShell (código {resultado.codigo})."


def _codigo(resultado: executor.Resultado) -> str:
    """Só o código da falha, para o log: a mensagem do Windows pode ter caminho de perfil."""
    if resultado.esgotado:
        return "tempo_esgotado"
    for linha in _linhas(resultado):
        if linha.startswith("ERRO|"):
            return linha.split("|", 2)[1] or "erro"
    return f"powershell_{resultado.codigo}"


def _avisos_log(linhas: list[str]) -> str:
    """`AVISO|tipo|...` → só o tipo (e o HResult do perfil); o detalhe fica na tela."""
    resumo = []
    for linha in linhas:
        if linha.startswith("AVISO|"):
            partes = linha.split("|")
            tipo = partes[1] if len(partes) > 1 else "?"
            resumo.append(
                f"{tipo}: falhou ({partes[2]})" if tipo == "perfil" and len(partes) > 3 else tipo
            )
    return "; ".join(resumo)


def _avisos(resultado: executor.Resultado) -> tuple[str, ...]:
    return tuple(
        linha.split("|", 1)[1] for linha in _linhas(resultado) if linha.startswith("AVISO|")
    )


def _feito(acao: str, nome: str, resultado: executor.Resultado, sucesso: str) -> Feito:
    linhas = _linhas(resultado)
    alteradas = tuple(linha.split("|", 1)[1] for linha in linhas if linha.startswith("MUDOU|"))
    avisos = _avisos_log(linhas)
    if resultado.ok and "OK" in linhas:
        log.info(
            "Contas: %s %s: ok%s%s",
            acao,
            nome,
            f" ({', '.join(alteradas)})" if alteradas else "",
            f"; avisos: {avisos}" if avisos else "",
        )
        return Feito(True, sucesso, alteradas, _avisos(resultado))
    motivo = _erro(resultado)
    log.error("Contas: %s %s: falhou: %s", acao, nome, _codigo(resultado))
    return Feito(False, motivo, alteradas, _avisos(resultado))


def _data(valor: Any) -> datetime | None:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def ler(saida: str) -> Lista:
    """JSON da listagem → Lista. ErroContas se o formato estiver errado."""
    try:
        cru = json.loads(saida)
        contas = tuple(
            Conta(
                sid=str(c["sid"]),
                nome=str(c["nome"]),
                ativo=bool(c["ativo"]),
                admin=bool(c["admin"]),
                fonte=str(c.get("fonte") or ""),
                logada=bool(c["logada"]),
                ultima=_data(c.get("ultima")),
                perfil=c["perfil"] if isinstance(c.get("perfil"), str) else None,
                carregado=bool(c.get("carregado")),
                bench=bool(c.get("bench")),
            )
            for c in cru["contas"] or []
        )
        outros = tuple(str(o["nome"]) for o in cru["outros_admins"] or [])
        return Lista(
            tuple(sorted(contas, key=lambda c: c.nome.lower())), outros, str(cru["computador"])
        )
    except (json.JSONDecodeError, KeyError, TypeError) as erro:
        raise ErroContas(f"saída inválida da listagem ({type(erro).__name__})") from None


def listar(*, rodar: Rodar = executor.powershell, cancelar: threading.Event | None = None) -> Lista:
    r = rodar(script("listar"), timeout=TIMEOUT_LISTA, cancelar=cancelar)
    if r.esgotado or r.cancelado or r.codigo != 0:
        raise ErroContas("tempo esgotado" if r.esgotado else f"código {r.codigo}")
    avisos = _avisos_log(r.erros.splitlines())
    if avisos:
        log.warning("Contas: leitura com aviso: %s", avisos)
    return ler(r.saida)


def _conferir(sid: str, acao: Acao, prot: frozenset[str], rodar: Rodar) -> Conta | Feito:
    """Leitura nova e regras em Python antes de alterar; Feito = recusado."""
    lista = listar(rodar=rodar)
    conta = lista.por_sid(sid)
    if conta is None:
        return Feito(False, MENSAGENS["nao_encontrada"])
    motivo = recusa(acao, conta, lista, prot)
    if motivo:
        log.warning("Contas: %s %s recusado: %s", acao, conta.nome, motivo)
        return Feito(False, MENSAGENS[motivo])
    return conta


def criar(
    nome: str,
    senha: Sensivel | None,
    tipo: Literal["admin", "padrao"],
    *,
    clonar_sid: str | None = None,
    nunca_expira: bool = True,
    protegidas_: frozenset[str] = frozenset({SUPORTE_PADRAO.lower()}),
    permitir_nome_computador: bool = False,
    rodar: Rodar = executor.powershell,
    criar_perfil: Callable[[str, str], int] | None = None,
) -> Feito:
    """Cria a conta e já prepara o perfil dela, sem entrar (ADR-050)."""
    nome = nome.strip()
    problema = validar_nome(
        nome,
        listar(rodar=rodar),
        protegidas_,
        permitir_nome_computador=permitir_nome_computador,
    )
    if problema:
        return Feito(False, problema)
    variaveis: dict[str, str | Sensivel] = {
        "nome": nome,
        "tipo": tipo,
        "nunca_expira": "1" if nunca_expira else "0",
        "clonar": clonar_sid or "",
        "protegidas": _ambiente_protegidas(protegidas_),
        "permitir_nome_pc": "1" if permitir_nome_computador else "0",
    }
    if senha is not None and senha.revelar():
        variaveis["senha"] = senha
    r = rodar(script("criar"), timeout=TIMEOUT_ACAO, **variaveis)
    rotulo = "administrador" if tipo == "admin" else "padrão"
    feito = _feito(
        f"criar ({rotulo}{', sem senha' if 'senha' not in variaveis else ''})",
        nome,
        r,
        f"Conta {nome} criada.",
    )
    grupos = [linha.split("|", 1)[1] for linha in _linhas(r) if linha.startswith("GRUPO|")]
    if grupos:
        log.info("Contas: grupos copiados para %s: %s", nome, ", ".join(grupos))
    if not feito.ok:
        return feito
    sids = [x.split("|", 1)[1] for x in _linhas(r) if re.fullmatch(r"SID\|S-1-5-21-[\d-]+", x)]
    aviso = preparar_perfil(nome, sids[0] if sids else None, criar_perfil=criar_perfil)
    if aviso:
        return Feito(True, feito.mensagem, feito.alteradas, (*feito.avisos, aviso))
    return Feito(
        True,
        f"{feito.mensagem} Perfil preparado: já dá para aplicar políticas e aparência sem "
        "entrar nela.",
        feito.alteradas,
        feito.avisos,
    )


def preparar_perfil(
    nome: str,
    sid: str | None,
    *,
    criar_perfil: Callable[[str, str], int] | None = None,
) -> str | None:
    """Cria o perfil da conta recém-criada sem entrar nela (ADR-050); devolve o aviso ou None.

    `sid` vem da linha `SID|` do `criar.ps1`. Falha aqui não desfaz a conta: ela existe e
    funciona; o perfil sai no primeiro logon, como antes. O log leva só o nome da conta e o
    código, nunca o caminho do perfil.
    """
    if not sid:
        log.warning("Contas: perfil de %s não preparado: SID não informado", nome)
        return PERFIL_NAO_PREPARADO
    if criar_perfil is None:
        criar_perfil = perfil_conta.criar  # lido aqui: o conftest troca nos testes
    codigo = criar_perfil(sid, nome)
    if codigo not in (0, perfil_conta.JA_EXISTE):
        log.warning("Contas: perfil de %s não preparado: código 0x%08X", nome, codigo & 0xFFFFFFFF)
        return f"{PERFIL_NAO_PREPARADO} (código 0x{codigo & 0xFFFFFFFF:08X})"
    log.info("Contas: perfil de %s preparado sem entrar", nome)
    return None


def definir_tipo(
    sid: str,
    tipo: Literal["admin", "padrao"],
    *,
    protegidas_: frozenset[str] = frozenset({SUPORTE_PADRAO.lower()}),
    rodar: Rodar = executor.powershell,
) -> Feito:
    conta = _conferir(sid, tipo, protegidas_, rodar)
    if isinstance(conta, Feito):
        return conta
    r = rodar(
        script("tipo"),
        timeout=TIMEOUT_ACAO,
        sid=sid,
        tipo=tipo,
        protegidas=_ambiente_protegidas(protegidas_),
    )
    rotulo = "Administrador" if tipo == "admin" else "Local padrão"
    return _feito(f"tornar {rotulo}", conta.nome, r, f"{conta.nome} agora é {rotulo}.")


def trocar_senha(
    sid: str,
    senha: Sensivel | None,
    *,
    protegidas_: frozenset[str] = frozenset({SUPORTE_PADRAO.lower()}),
    rodar: Rodar = executor.powershell,
) -> Feito:
    """Senha None ou vazia remove a senha."""
    remover = senha is None or not senha.revelar()
    conta = _conferir(sid, "sem_senha" if remover else "senha", protegidas_, rodar)
    if isinstance(conta, Feito):
        return conta
    variaveis: dict[str, str | Sensivel] = {
        "sid": sid,
        "protegidas": _ambiente_protegidas(protegidas_),
    }
    if not remover and senha is not None:
        variaveis["senha"] = senha
    r = rodar(script("senha"), timeout=TIMEOUT_ACAO, **variaveis)
    if remover:
        return _feito("remover senha", conta.nome, r, f"Senha de {conta.nome} removida.")
    return _feito("trocar senha", conta.nome, r, f"Senha de {conta.nome} alterada.")


def excluir(
    sid: str,
    apagar_perfil: bool,
    *,
    protegidas_: frozenset[str] = frozenset({SUPORTE_PADRAO.lower()}),
    rodar: Rodar = executor.powershell,
) -> Feito:
    conta = _conferir(sid, "excluir", protegidas_, rodar)
    if isinstance(conta, Feito):
        return conta
    r = rodar(
        script("excluir"),
        timeout=TIMEOUT_ACAO,
        sid=sid,
        perfil="1" if apagar_perfil else "0",
        protegidas=_ambiente_protegidas(protegidas_),
    )
    linhas = _linhas(r)
    acao = "excluir (com perfil)" if apagar_perfil else "excluir (sem perfil)"
    if "CONTA" not in linhas:
        return _feito(acao, conta.nome, r, "")
    if not apagar_perfil:
        extra = " A pasta da conta foi mantida."
    elif "PERFIL" in linhas:
        extra = " Pasta e arquivos apagados."
    elif conta.perfil is None:
        extra = " A conta não tinha pasta."
    else:
        extra = " Não foi possível apagar a pasta; use a Limpeza."
    # A conta saiu mesmo se o perfil falhou: sucesso, com o aviso.
    avisos = _avisos_log(linhas)
    log.info("Contas: %s %s: ok%s%s", acao, conta.nome, extra, f" ({avisos})" if avisos else "")
    return Feito(True, f"Conta {conta.nome} excluída.{extra}", (), _avisos(r))


def modificavel(conta: Conta, protegidas_: Iterable[str]) -> bool:
    """Conta que a tela Contas deixa alterar (ADR-036): local, fora o Administrador nativo, a
    Suporte e as restritas fixas (Gestão). As outras regras (conta em uso, último
    administrador) continuam por ação."""
    prot = {n.lower() for n in protegidas_} | RESTRITAS
    return conta.local and not conta.nativo and conta.nome.lower() not in prot


def com_sessao(lista: Lista) -> list[Conta]:
    """Contas com sessão aberta (perfil carregado ou em uso), para "Encerrar sessões"."""
    return [c for c in lista.contas if c.carregado or c.logada]


def encerrar_sessao(
    sid: str,
    *,
    rodar: Rodar = executor.powershell,
    encerrar: Callable[[int], int] | None = None,
) -> Feito:
    """Encerra as sessões do Windows da conta (ADR-036, ADR-049).

    O trecho só acha as sessões (e recusa a do Bench); o logoff é por `WTSLogoffSession` em
    `nucleo/sessoes.py`, que também recusa a sessão do Bench e a sessão 0.
    """
    conta = listar(rodar=rodar).por_sid(sid)
    if conta is None:
        return Feito(False, MENSAGENS["nao_encontrada"])
    r = rodar(script("encerrar"), timeout=TIMEOUT_ACAO, sid=sid)
    linhas = _linhas(r)
    if not (r.ok and "OK" in linhas):
        return _feito("encerrar sessão", conta.nome, r, "")
    numeros = [int(x.split("|", 1)[1]) for x in linhas if re.fullmatch(r"SESSAO\|\d{1,5}", x)]
    if not numeros:
        log.error("Contas: encerrar sessão %s: falhou: sem_sessao", conta.nome)
        return Feito(False, MENSAGENS["sem_sessao"])
    if encerrar is None:
        encerrar = sessoes.encerrar  # lido aqui: o conftest troca nos testes
    for n in numeros:
        codigo = encerrar(n)
        if codigo:
            log.error(
                "Contas: encerrar sessão %s: falhou: sessão %d, código %d", conta.nome, n, codigo
            )
            return Feito(False, f"{MENSAGENS['encerrar']}: sessão {n}, código {codigo}")
    log.info("Contas: encerrar sessão %s: ok (%d sessão(ões))", conta.nome, len(numeros))
    return Feito(True, f"Sessão de {conta.nome} encerrada.", (), _avisos(r))


def encerrar_sessoes(sids: Iterable[str]) -> Feito:
    """Encerra as sessões das contas, uma por vez (tela Contas, Configuração e Manutenção)."""
    feitos = [encerrar_sessao(sid) for sid in sids]
    return Feito(all(f.ok for f in feitos), "\n".join(f.mensagem for f in feitos))


def encerrar_outras_sessoes(avisar: Callable[[str], None] = lambda _t: None) -> int:
    """Manutenção (ADR-081): encerra as sessões abertas de todas as contas, menos a de quem está
    na frente da tela e a que roda o Bench. Devolve quantas; erro se alguma não fechou."""
    lista = listar()
    try:
        frente = sessoes.usuario_da_sessao().lower()
    except OSError:
        frente = ""
    outras = [c for c in lista.contas if c.logada and not c.bench and c.nome.lower() != frente]
    if not outras:
        return 0
    avisar("Encerrando as sessões de " + ", ".join(c.nome for c in outras) + "…")
    feito = encerrar_sessoes([c.sid for c in outras])
    if not feito.ok:
        raise RuntimeError(f"não deu para encerrar as sessões: {feito.mensagem}")
    return len(outras)


def aplicar_suporte(cadastros: Cadastros | None, *, rodar: Rodar = executor.powershell) -> Feito:
    return _aplicar("Suporte", suporte_do_cadastro(cadastros), rodar)


def aplicar_gestao(cadastros: Cadastros | None, *, rodar: Rodar = executor.powershell) -> Feito:
    """Igual a Aplicar conta Suporte, com as linhas “Conta Gestão” (ADR-069)."""
    return _aplicar("Gestão", gestao_do_cadastro(cadastros), rodar)


def _aplicar(rotulo: str, origem: tuple[str, Sensivel] | str, rodar: Rodar) -> Feito:
    """Cria a conta, ou troca a senha, ativa e torna administradora (trecho `suporte.ps1`)."""
    if isinstance(origem, str):
        log.warning("Contas: aplicar conta %s recusado: %s", rotulo, origem)
        return Feito(False, origem)
    nome, senha = origem
    lista = listar(rodar=rodar)
    existente = next((c for c in lista.contas if c.nome.lower() == nome.lower()), None)
    if existente is not None:
        motivo = (
            "suporte_nativo" if existente.nativo else "microsoft" if not existente.local else None
        )
        if motivo:
            log.warning("Contas: aplicar conta %s recusado: %s", rotulo, motivo)
            return Feito(False, MENSAGENS[motivo])
    r = rodar(script("suporte"), timeout=TIMEOUT_ACAO, nome=nome, senha=senha)
    # Com a conta logada, aplicar é permitido (emenda do ADR-017); a tela avisa do cofre.
    verbo = "criada" if "CRIADA" in _linhas(r) else "atualizada"
    return _feito(
        f"aplicar conta {rotulo}",
        nome,
        r,
        f"Conta {nome} {verbo}: administradora, senha do cadastro.",
    )


def lote(
    tipo: Literal["admin", "padrao"],
    *,
    protegidas_: frozenset[str] = frozenset({SUPORTE_PADRAO.lower()}),
    rodar: Rodar = executor.powershell,
) -> Feito:
    """`admin`: todas as contas locais ativas viram administradoras. `padrao`: todas deixam de ser,
    menos a Suporte e o nativo, inclusive a logada (ADR-017, item 6)."""
    if tipo == "padrao" and not suporte_ok(listar(rodar=rodar), protegidas_):
        log.warning("Contas: remover administrador de todos recusado: suporte_ausente")
        return Feito(False, MENSAGENS["suporte_ausente"])
    r = rodar(
        script("lote"),
        timeout=TIMEOUT_LOTE,
        lote=tipo,
        protegidas=_ambiente_protegidas(protegidas_),
    )
    acao = "tornar todos administradores" if tipo == "admin" else "remover administrador de todos"
    feito = _feito(acao, "-", r, "")
    if not feito.ok:
        return feito
    n = len(feito.alteradas)
    texto = f"{n} conta(s) alterada(s)." if n else "Nenhuma conta precisou mudar."
    return Feito(True, texto, feito.alteradas, feito.avisos)


def tamanho_perfil(caminho: str | None, teto: float = TEMPO_TAMANHO) -> int | None:
    """Bytes do perfil, ou None se não existe ou passou do teto de tempo (ADR-017, ajuste 3)."""
    if not caminho:
        return None
    limite = time.monotonic() + teto
    total, pendentes = 0, [caminho]
    while pendentes:
        if time.monotonic() > limite:
            return None
        try:
            with os.scandir(pendentes.pop()) as itens:
                for item in itens:
                    if item.is_dir(follow_symlinks=False):
                        pendentes.append(item.path)
                    elif item.is_file(follow_symlinks=False):
                        total += item.stat(follow_symlinks=False).st_size
        except OSError as erro:
            # Pasta sem acesso: conta o resto; o número na confirmação é aproximado.
            log.debug("Contas: pasta do perfil ilegível ao medir: %s", type(erro).__name__)
    return total
