"""Etapas e perfis da Preparação completa (ADR-023, ADR-060), sem Qt.

As 14 etapas, a ordem e os parâmetros de cada uma são fechados aqui. Os perfis vêm só do
cadastro (tabela Perfis, ADR-060): cada um diz quais etapas rodam, pelos números de 1 a 14;
nada de texto livre, caminho ou comando. `Unidades.PerfilPadrao` escolhe o perfil pelo código.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from itc_bench.servicos.cadastros import Cadastros

# Ordem fixa da preparação (ADR-023, item 2).
ETAPAS: tuple[tuple[str, str], ...] = (
    ("identificacao", "Identificação"),
    ("contas", "Contas"),
    ("wifi", "Wi-Fi"),
    ("remoto", "Acesso remoto"),
    ("programas", "Programas"),
    ("preinstalados", "Remover pré-instalados"),
    ("politicas", "Políticas"),
    ("usb", "USB"),
    ("protecao", "Proteção do login"),
    ("papel", "Papel de parede"),
    ("mouse", "Mouse e teclado"),
    ("energia", "Energia"),
    ("limpeza", "Limpeza"),
    ("diagnostico", "Diagnóstico"),
)
NOMES = dict(ETAPAS)
ORDEM = tuple(e for e, _ in ETAPAS)
# Número fixo de cada etapa pela ordem acima (ADR-056): igual em todo perfil, mesmo quando o
# perfil pula etapas (Administrativo mostra 1 a 5, depois 9 a 14).
NUMERO = {e: i for i, e in enumerate(ORDEM, start=1)}


def rotulo(etapa: str) -> str:
    """`contas` → `2. Contas`: o nome que aparece na tela, no log e na confirmação."""
    return f"{NUMERO[etapa]}. {NOMES[etapa]}"


# Etapas que usam as contas como alvo: sem a etapa Contas em ordem, ficam bloqueadas.
DEPENDE: dict[str, tuple[str, ...]] = {
    "politicas": ("contas",),
    "usb": ("contas",),
    "papel": ("contas",),
    "mouse": ("contas",),
}

# ---------------------------------------------------------------- parâmetros fechados

# Ids de servicos.politicas.CATALOGO (ADR-021). Máquina + contas de aluno.
POLITICAS_USUARIO = ("cmd", "regedit", "painel", "programas", "temas", "ponteiros", "powershell")
POLITICAS_MAQUINA = ("compartilhamento", "wifidirect", "ics")
POLITICA_USB = "usb"
# Opções de servicos.aparencia.CATALOGO (ADR-022): o aluno não liga as Teclas de aderência.
MOUSE: dict[str, str] = {"atalho_shift": "desligado"}
# (ajuste, fonte) → segundos da lista fechada de servicos.energia.TEMPOS.
ENERGIA: dict[tuple[str, str], int] = {
    ("tela", "ac"): 900,
    ("tela", "dc"): 600,
    ("suspensao", "ac"): 0,
    ("suspensao", "dc"): 1800,
}
ESTILO_PAPEL = "preencher"
# Itens de servicos.limpeza.ITENS usados na preparação; a lixeira fica só na tela Limpeza.
LIMPEZA = ("temp_sistema", "temp_usuarios", "windows_update", "relatorios_erro")


@dataclass(frozen=True)
class Perfil:
    """Perfil da Preparação (ADR-060): vem só do cadastro (tabela Perfis do NocoDB). O cadastro
    escolhe quais das 14 etapas rodam; o que cada etapa faz continua fechado acima."""

    id: str  # Perfis.Codigo
    nome: str
    descricao: str
    etapas: tuple[str, ...]  # ids, sempre na ordem de ORDEM
    projeto: str = ""  # vazio = vale para todas as unidades


SEM_PERFIL = "Nenhum perfil no cadastro (tabela Perfis). Cadastre no NocoDB e sincronize."


def etapas_dos_numeros(numeros: Iterable[Any]) -> tuple[str, ...] | None:
    """[14, 1, 2] → ("identificacao", "contas", "diagnostico"); None se algum número não for
    uma etapa (1 a 14) ou se não houver nenhum."""
    try:
        conjunto = {int(n) for n in numeros}
    except (TypeError, ValueError):
        return None
    if not conjunto or not conjunto <= set(NUMERO.values()):
        return None
    return tuple(e for e in ORDEM if NUMERO[e] in conjunto)


def disponiveis(cadastros: "Cadastros | None", unidade: str | None) -> list[Perfil]:
    """Perfis que valem para a unidade: os sem projeto e os do projeto dela."""
    if cadastros is None:
        return []
    u = cadastros.unidade_por_codigo(unidade)
    projeto = u.projeto if u is not None else ""
    return [p for p in cadastros.perfis if not p.projeto or p.projeto == projeto]


def padrao(cadastros: "Cadastros | None", unidade: str | None) -> tuple[Perfil | None, str]:
    """Perfil que vem marcado: o `Unidades.PerfilPadrao` da unidade; sem ele (ou desconhecido),
    o primeiro disponível, com aviso. Nenhum perfil: (None, aviso)."""
    lista = disponiveis(cadastros, unidade)
    if not lista:
        return None, SEM_PERFIL
    u = cadastros.unidade_por_codigo(unidade) if cadastros is not None else None
    chave = (u.perfil_padrao if u is not None else "").strip().lower()
    if not chave:
        return lista[0], ""
    achado = next((p for p in lista if p.id == chave), None)
    if achado is None:
        return lista[0], f"Perfil padrão da unidade desconhecido; usando {lista[0].nome}."
    return achado, ""


def dependencias(etapa: str) -> tuple[str, ...]:
    return DEPENDE.get(etapa, ())
