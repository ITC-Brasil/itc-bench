"""Nome do computador (ADR-018), sem Qt: a tela Identificação e a Preparação completa (13) usam.

O técnico digita o nome inteiro; o Bench só confere as regras do Windows. O nome vai ao
`Rename-Computer` por `ITC_NOME` (executor), nunca no texto do comando.
"""

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import resources

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

RECURSOS = resources.files("itc_bench.recursos") / "identificacao"
TIMEOUT_ESTADO, TIMEOUT_RENOMEAR = 30.0, 60.0
ESPERA_REINICIO = 10  # segundos entre "Reiniciar agora" e o reinício

NOME = re.compile(r"^[A-Z0-9](?:[A-Z0-9-]{0,13}[A-Z0-9])?$")
# Palavras reservadas da Microsoft para nomes de computador (as de uma palavra só; as com espaço
# já caem na regra de caracteres).
RESERVADOS = frozenset(
    {"ANONYMOUS", "BATCH", "BUILTIN", "DIALUP", "INTERACTIVE", "INTERNET", "LOCAL", "NETWORK"}
    | {"NULL", "PROXY", "RESTRICTED", "SELF", "SERVER", "SERVICE", "SYSTEM", "USERS", "WORLD"}
    | {"LOCALHOST"}
)

MENSAGENS = {
    "nome_invalido": "Nome inválido.",
    "dominio": "Máquina em domínio ou Azure AD: o nome é trocado pelo administrador do domínio.",
    "nome_local": "Já existe uma conta ou grupo local com esse nome.",
    "renomear": "O Windows recusou o nome",
}

Rodar = Callable[..., executor.Resultado]


@dataclass(frozen=True)
class Estado:
    ativo: str
    pendente: str  # igual ao ativo quando não há troca esperando reinício
    dominio: bool  # domínio ou Azure AD
    nomes_locais: frozenset[str]  # contas e grupos locais, em maiúsculas

    @property
    def reinicio_pendente(self) -> bool:
        return self.pendente.upper() != self.ativo.upper()


@dataclass(frozen=True)
class Feito:
    ok: bool
    mensagem: str


class ErroIdentificacao(RuntimeError):
    """Falha ao ler o estado (tempo esgotado, saída inválida)."""


def normalizar(nome: str) -> str:
    return nome.strip().upper()


def validar(nome: str, estado: Estado | None = None) -> str | None:
    """Motivo da recusa, ou None. `nome` já normalizado (maiúsculas, sem espaço nas pontas)."""
    if not nome:
        return "Digite o nome do computador."
    if len(nome) > 15:
        return "No máximo 15 caracteres."
    if not NOME.match(nome):
        return "Use só letras sem acento, números e hífen (o hífen não pode ficar na ponta)."
    if nome.isdigit():
        return "O nome não pode ter só números."
    if nome in RESERVADOS:
        return "Nome reservado pelo Windows."
    if estado is not None:
        if estado.dominio:
            return MENSAGENS["dominio"]
        if nome in estado.nomes_locais:
            return MENSAGENS["nome_local"]
        if nome == estado.pendente.upper():
            return (
                "O computador já vai ter esse nome depois de reiniciar."
                if estado.reinicio_pendente
                else "Esse já é o nome do computador."
            )
    return None


def ler(saida: str) -> Estado:
    try:
        cru = json.loads(saida)
        nomes: Iterable[object] = cru.get("nomes") or []
        return Estado(
            ativo=str(cru["ativo"]),
            pendente=str(cru["pendente"] or cru["ativo"]),
            dominio=bool(cru["dominio"]) or bool(cru["azuread"]),
            nomes_locais=frozenset(str(n).upper() for n in nomes),
        )
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as erro:
        raise ErroIdentificacao(f"saída inválida ({type(erro).__name__})") from None


def script(nome: str) -> str:
    return (RECURSOS / f"{nome}.ps1").read_text("utf-8")


def estado(*, rodar: Rodar = executor.powershell) -> Estado:
    r = rodar(script("estado"), timeout=TIMEOUT_ESTADO)
    if not r.ok:
        raise ErroIdentificacao("tempo esgotado" if r.esgotado else f"código {r.codigo}")
    return ler(r.saida)


def _erro(resultado: executor.Resultado) -> tuple[str, str]:
    """(código para o log, mensagem para a tela)."""
    if resultado.esgotado:
        return "tempo_esgotado", "Tempo esgotado."
    for linha in resultado.saida.splitlines():
        if linha.startswith("ERRO|"):
            _, codigo, detalhe = [*linha.strip().split("|", 2), "", ""][:3]
            base = MENSAGENS.get(codigo, codigo)
            return codigo, f"{base}: {detalhe}" if detalhe else base
    return f"powershell_{resultado.codigo}", f"Falha do PowerShell (código {resultado.codigo})."


def renomear(nome: str, *, rodar: Rodar = executor.powershell) -> Feito:
    """Confere de novo sobre uma leitura nova e chama `Rename-Computer`. Vale após reiniciar."""
    nome = normalizar(nome)
    atual = estado(rodar=rodar)
    motivo = validar(nome, atual)
    if motivo:
        log.warning("Identificação: renomear %s recusado: %s", nome, motivo)
        return Feito(False, motivo)
    r = rodar(script("renomear"), timeout=TIMEOUT_RENOMEAR, nome=nome)
    if r.ok and "OK" in r.saida.split():
        log.info("Identificação: renomear %s -> %s: ok (reinício pendente)", atual.ativo, nome)
        return Feito(True, f"Nome trocado para {nome}. Vale depois de reiniciar.")
    codigo, mensagem = _erro(r)
    log.error("Identificação: renomear %s -> %s: falhou: %s", atual.ativo, nome, codigo)
    return Feito(False, mensagem)


def reiniciar(*, rodar: Callable[..., executor.Resultado] = executor.executar) -> Feito:
    r = rodar([executor.sistema32("shutdown.exe"), "/r", "/t", str(ESPERA_REINICIO)], timeout=30)
    if r.ok:
        log.info("Identificação: reinício pedido (%s s)", ESPERA_REINICIO)
        return Feito(True, f"O Windows reinicia em {ESPERA_REINICIO} segundos.")
    log.error("Identificação: reinício falhou: código %s", r.codigo)
    return Feito(False, f"O Windows não aceitou reiniciar (código {r.codigo}).")
