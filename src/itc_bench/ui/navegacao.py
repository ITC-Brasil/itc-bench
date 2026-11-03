"""Menu em 7 grupos (ADR-004), na ordem de `docs/design/itc-bench-identidade-telas.html`."""

from typing import NamedTuple

M04 = "04 — Cadastros via API com cache DPAPI"
M05 = "05 — Diagnóstico"
M06 = "06 — Contas"
M07 = "07 — Identificação e Wi-Fi"
M08 = "08 — Acesso remoto"
M09 = "09 — Programas e Remover programas"
M10 = "10 — Políticas e USB"
M11 = "11 — Proteção do login e Aparência"
M12 = "12 — Preparação completa, Início e Limpeza"


class Item(NamedTuple):
    chave: str  # nome do ícone em recursos/icones
    titulo: str
    modulo: str  # módulo de docs/IMPLEMENTATION-PLAN.md que implementa a tela


GRUPOS: list[tuple[str, list[Item]]] = [
    ("Início", [Item("inicio", "Início", M12), Item("prep", "Preparação completa", M12)]),
    (
        "Preparar",
        [
            Item("id", "Identificação", M07),
            Item("contas", "Contas", M06),
            Item("wifi", "Wi-Fi", M07),
            Item("remoto", "Acesso remoto", M08),
        ],
    ),
    ("Software", [Item("prog", "Programas", M09), Item("remover", "Remover programas", M09)]),
    (
        "Segurança",
        [
            Item("gpo", "Políticas", M10),
            Item("protecao", "Proteção do login", M11),
            Item("usb", "USB", M10),
        ],
    ),
    (
        "Aparência e periféricos",
        [
            Item("aparencia", "Tela e papel de parede", M11),
            Item("mouse", "Mouse e teclado", M11),
            Item("energia", "Energia", M11),
        ],
    ),
    (
        "Diagnóstico",
        [
            Item("diag", "Coleta e laudo", M05),
            Item("hist", "Histórico", M05),
            Item("limpeza", "Limpeza", M12),
        ],
    ),
    (
        "Sistema",
        [
            Item("registro", "Registro", M12),
            Item("ajuda", "Ajuda", M12),
            Item("config", "Configurações", M04),
        ],
    ),
]
