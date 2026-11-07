"""Perfis da Preparação completa (ADR-023), sem Qt: fechados no código.

Perfil = id, nome e tupla ordenada de ids de etapa. Os parâmetros das etapas vêm só das listas
fechadas abaixo ou das linhas ativas do cadastro; nada de texto livre, caminho ou comando.
`Unidades.PerfilPadrao` escolhe o perfil pelo id.
"""

from dataclasses import dataclass

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
    id: str
    nome: str
    descricao: str
    etapas: tuple[str, ...]


PERFIS: tuple[Perfil, ...] = (
    Perfil("sala_de_aula", "Sala de aula", "Notebook de aluno: todas as etapas.", ORDEM),
    Perfil(
        "administrativo",
        "Administrativo",
        "Notebook da equipe: sem Políticas, USB e Remover pré-instalados.",
        tuple(e for e in ORDEM if e not in ("preinstalados", "politicas", "usb")),
    ),
    Perfil("so_diagnostico", "Só diagnóstico", "Só a coleta do diagnóstico.", ("diagnostico",)),
)
POR_ID = {p.id: p for p in PERFIS}
PADRAO = PERFIS[0]


def do_cadastro(texto: str | None) -> tuple[Perfil, str]:
    """Perfil pelo `Unidades.PerfilPadrao`; texto desconhecido cai no padrão, com aviso."""
    chave = (texto or "").strip().lower()
    if not chave:
        return PADRAO, ""
    perfil = POR_ID.get(chave)
    if perfil is None:
        return PADRAO, "Perfil padrão da unidade desconhecido; usando Sala de aula."
    return perfil, ""


def dependencias(etapa: str) -> tuple[str, ...]:
    return DEPENDE.get(etapa, ())
