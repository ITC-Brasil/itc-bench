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

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.executor import Sensivel

RECURSOS = resources.files("itc_bench.recursos") / "contas"
SUPORTE_PADRAO = "Suporte"
SERVICO_SUPORTE = "Conta Suporte"
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
}


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


def validar_nome(nome: str, lista: Lista | None, protegidas_: Iterable[str]) -> str | None:
    """Mensagem do problema, ou None se o nome serve. O PowerShell confere de novo."""
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
    if lista is not None:
        if baixo == lista.computador.lower():
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
    locais = [c for c in lista.contas if c.local and not c.nativo]
    if lote == "admin":
        return [c.nome for c in locais if c.ativo and not c.admin]
    return [c.nome for c in locais if c.admin and c.nome.lower() not in prot]


def suporte_ok(lista: Lista, protegidas_: Iterable[str]) -> bool:
    prot = set(protegidas_)
    return any(
        c.nome.lower() in prot and c.ativo and c.admin and c.local and not c.nativo
        for c in lista.contas
    )


def suporte_do_cadastro(cadastros: Cadastros | None) -> tuple[str, Sensivel] | str:
    """(nome, senha) da conta Suporte, ou a mensagem do que falta (ADR-008, ADR-017)."""
    if cadastros is None:
        return "Sem cadastros: conecte e sincronize em Configurações."
    linhas = [s for s in cadastros.servidores if s.servico == SERVICO_SUPORTE]
    usuarios = [s for s in linhas if s.papel == "usuario"]
    senhas = [s for s in linhas if s.papel == "senha"]
    if len(usuarios) > 1 or len(senhas) > 1:
        return "Há mais de uma linha “Conta Suporte” para o mesmo papel em Servidores."
    if not senhas or not isinstance(senhas[0].valor, Sensivel) or not senhas[0].valor.revelar():
        return "Cadastre “Conta Suporte” / senha (não pública) em Servidores e sincronize."
    nome = SUPORTE_PADRAO
    if usuarios:
        if not isinstance(usuarios[0].valor, str):
            return "A linha “Conta Suporte” / usuario tem que ser pública."
        nome = usuarios[0].valor.strip() or SUPORTE_PADRAO
    return nome, senhas[0].valor


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
            if codigo in ("criar", "senha", "tipo", "excluir", "suporte", "parcial"):
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
    rodar: Rodar = executor.powershell,
) -> Feito:
    nome = nome.strip()
    problema = validar_nome(nome, listar(rodar=rodar), protegidas_)
    if problema:
        return Feito(False, problema)
    variaveis: dict[str, str | Sensivel] = {
        "nome": nome,
        "tipo": tipo,
        "nunca_expira": "1" if nunca_expira else "0",
        "clonar": clonar_sid or "",
        "protegidas": _ambiente_protegidas(protegidas_),
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
    return feito


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


def aplicar_suporte(cadastros: Cadastros | None, *, rodar: Rodar = executor.powershell) -> Feito:
    origem = suporte_do_cadastro(cadastros)
    if isinstance(origem, str):
        log.warning("Contas: aplicar conta Suporte recusado: %s", origem)
        return Feito(False, origem)
    nome, senha = origem
    lista = listar(rodar=rodar)
    existente = next((c for c in lista.contas if c.nome.lower() == nome.lower()), None)
    if existente is not None:
        motivo = (
            "suporte_nativo" if existente.nativo else "microsoft" if not existente.local else None
        )
        if motivo:
            log.warning("Contas: aplicar conta Suporte recusado: %s", motivo)
            return Feito(False, MENSAGENS[motivo])
    r = rodar(script("suporte"), timeout=TIMEOUT_ACAO, nome=nome, senha=senha)
    # Com a Suporte logada, aplicar é permitido (emenda do ADR-017); a tela avisa do cofre.
    verbo = "criada" if "CRIADA" in _linhas(r) else "atualizada"
    return _feito(
        "aplicar conta Suporte",
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
