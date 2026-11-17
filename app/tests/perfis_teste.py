"""Perfis de teste (ADR-060): os perfis vêm do cadastro, então os testes trazem os seus."""

from itc_bench.servicos import perfis
from itc_bench.servicos.perfis import Perfil

# (código, nome, números das etapas da Configuração, ADR-062)
LINHAS = (
    ("aluno", "Aluno", list(range(1, 13))),
    ("administrativo", "Administrativo", [1, 3, 4, 5, 6, 9, 10, 11, 12]),
    ("so_diagnostico", "Só diagnóstico", [12]),
)


def corpo() -> list[dict]:
    """Como a API entrega em `perfis` (TA-ADR-037)."""
    return [
        {"id": i, "codigo": c, "nome": n, "etapas": e, "projeto": "", "descricao": ""}
        for i, (c, n, e) in enumerate(LINHAS, start=1)
    ]


PERFIS: tuple[Perfil, ...] = tuple(
    Perfil(c, n, "", perfis.etapas_dos_numeros(e) or ()) for c, n, e in LINHAS
)
POR_ID = {p.id: p for p in PERFIS}
