"""Etapas e perfis da Configuração e da Manutenção (ADR-023, ADR-060, ADR-062), sem Qt.

As etapas, a ordem e os parâmetros de cada uma são fechados aqui. Os perfis (só da
Configuração) vêm do cadastro (tabela Perfis, ADR-060): cada um diz quais etapas rodam, pelos
números de 1 a 12; nada de texto livre, caminho ou comando. `Unidades.PerfilPadrao` escolhe o
perfil pelo código. A Manutenção não usa perfil.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from itc_bench.servicos.cadastros import Cadastros


@dataclass(frozen=True)
class Fluxo:
    """Lista de etapas de uma tela, com número fixo de cada uma (ADR-056, ADR-062)."""

    id: str
    nome: str
    etapas: tuple[tuple[int, str, str], ...]  # (número, id, nome)

    @property
    def ordem(self) -> tuple[str, ...]:
        return tuple(e for _, e, _ in self.etapas)

    @property
    def numero(self) -> dict[str, int]:
        return {e: n for n, e, _ in self.etapas}

    @property
    def nomes(self) -> dict[str, str]:
        return {e: nome for _, e, nome in self.etapas}

    def rotulo(self, etapa: str) -> str:
        """`wifi` → `3. Wi-Fi`: o nome que aparece na tela, no log e na confirmação."""
        return f"{self.numero[etapa]}. {self.nomes[etapa]}"


# Configuração (ADR-062): máquina nova, com perfil. Ordem e números fixos.
CONFIGURACAO = Fluxo(
    "configuracao",
    "Configuração",
    (
        (1, "energia_inicio", "Energia: nunca desligar"),
        (2, "preinstalados", "Remover pré-instalados"),
        (3, "wifi", "Wi-Fi"),
        (4, "papel", "Papel de parede"),
        (5, "remoto", "Acesso remoto"),
        (6, "programas", "Programas"),
        (7, "politicas", "Políticas"),
        (8, "usb", "USB"),
        (9, "protecao", "Proteção do login"),
        (10, "energia", "Energia: planos finais"),
        (11, "contas", "Contas"),
        (12, "diagnostico", "Diagnóstico"),
    ),
)
# Manutenção (ADR-062, ADR-064): máquina em uso, sem perfil.
MANUTENCAO = Fluxo(
    "manutencao",
    "Manutenção",
    (
        (1, "limpeza_usuarios", "Limpeza de usuários"),
        (2, "wifi_senhas", "Wi-Fi: atualizar senhas"),
        (3, "diagnostico", "Diagnóstico"),
        (4, "steam", "Remover Steam"),
        (5, "inicializacao", "Desligar inicialização de apps não necessários"),  # ADR-080
    ),
)

# Atalhos da Configuração, usados pelos perfis (os números do cadastro são os dela).
ETAPAS: tuple[tuple[str, str], ...] = tuple((e, nome) for _, e, nome in CONFIGURACAO.etapas)
NOMES = CONFIGURACAO.nomes
ORDEM = CONFIGURACAO.ordem
NUMERO = CONFIGURACAO.numero


def rotulo(etapa: str, fluxo: Fluxo = CONFIGURACAO) -> str:
    return fluxo.rotulo(etapa)


# Sem dependência entre etapas desde o ADR-062: Contas foi para o fim e as políticas valem para
# as contas de aluno marcadas, sem precisar da Suporte aplicada antes.
DEPENDE: dict[str, tuple[str, ...]] = {}

# ---------------------------------------------------------------- parâmetros fechados

# Ids de servicos.politicas.CATALOGO (ADR-021). Máquina + contas de aluno.
POLITICAS_USUARIO = ("cmd", "regedit", "painel", "programas", "temas", "ponteiros", "powershell")
POLITICAS_MAQUINA = ("compartilhamento", "wifidirect", "ics")
POLITICA_USB = "usb"
# Opções de servicos.aparencia.CATALOGO (ADR-022): o aluno não liga as Teclas de aderência.
MOUSE: dict[str, str] = {"atalho_shift": "desligado"}
# (ajuste, fonte) → segundos da lista fechada de servicos.energia.TEMPOS (ADR-062).
# Etapa 1: nada desliga durante a configuração.
ENERGIA_INICIO: dict[tuple[str, str], int] = {
    ("tela", "ac"): 0,
    ("tela", "dc"): 0,
    ("suspensao", "ac"): 0,
    ("suspensao", "dc"): 0,
}
# Etapa 10: vídeo em 30 min e suspensão em 1 h, na tomada e na bateria, para todo perfil.
ENERGIA: dict[tuple[str, str], int] = {
    ("tela", "ac"): 1800,
    ("tela", "dc"): 1800,
    ("suspensao", "ac"): 3600,
    ("suspensao", "dc"): 3600,
}
ESTILO_PAPEL = "preencher"
# Itens de servicos.limpeza.ITENS usados na preparação; a lixeira fica só na tela Limpeza.
LIMPEZA = ("temp_sistema", "temp_usuarios", "windows_update", "relatorios_erro")


@dataclass(frozen=True)
class Perfil:
    """Perfil da Configuração (ADR-060): vem só do cadastro (tabela Perfis do NocoDB). O
    cadastro escolhe quais das 12 etapas rodam; o que cada etapa faz continua fechado acima."""

    id: str  # Perfis.Codigo
    nome: str
    descricao: str
    etapas: tuple[str, ...]  # ids, sempre na ordem de ORDEM
    projeto: str = ""  # vazio = vale para todas as unidades


SEM_PERFIL = "Nenhum perfil no cadastro (tabela Perfis). Cadastre no NocoDB e sincronize."


def etapas_dos_numeros(numeros: Iterable[Any]) -> tuple[str, ...] | None:
    """[12, 1, 3] → ("energia_inicio", "wifi", "diagnostico"); None se algum número não for
    uma etapa da Configuração (1 a 12) ou se não houver nenhum."""
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
