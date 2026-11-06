r"""Mouse e teclado (ADR-022), sem Qt: a tela Mouse e teclado e o 13 (por id) usam.

Preferências por alvo (contas e Contas futuras), gravadas no hive de cada um pelo serviço do 11,
com valores de uma lista fechada; sem `SystemParametersInfo` (o processo elevado é de outra conta).
São preferências, não política: chave criada só herda a ACL e o aluno pode mudar depois. Vale no
próximo logon. Desfazer = padrão do Windows.
"""

import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from itc_bench.servicos import executor, hive
from itc_bench.servicos.hive import Acao, Alvo, Feito, Rodar

_MOUSE = "Control Panel\\Mouse"
_CURSORES = "Control Panel\\Cursors"
_TECLADO = "Control Panel\\Keyboard"
_ACESS = "Software\\Microsoft\\Accessibility"
_SHIFT = "Control Panel\\Accessibility\\"
# Espelho das chaves exatas do perfil `aparencia` no comum.ps1 (o trecho confere de novo).
CHAVES_ACEITAS = frozenset(
    {
        _MOUSE,
        _CURSORES,
        _TECLADO,
        _SHIFT + "StickyKeys",
        _SHIFT + "Keyboard Response",
        _SHIFT + "ToggleKeys",
        _ACESS,
    }
)

Tipo = Literal["sz", "expand_sz", "dword"]
Escrita = tuple[str, str, Tipo, str | int]  # chave, nome, tipo, dado

# Esquema padrão do Windows (os valores que o próprio sistema grava).
_PADRAO_PONTEIROS = {
    "AppStarting": "%SystemRoot%\\cursors\\aero_working.ani",
    "Arrow": "%SystemRoot%\\cursors\\aero_arrow.cur",
    "Crosshair": "",
    "Hand": "%SystemRoot%\\cursors\\aero_link.cur",
    "Help": "%SystemRoot%\\cursors\\aero_helpsel.cur",
    "IBeam": "",
    "No": "%SystemRoot%\\cursors\\aero_unavail.cur",
    "NWPen": "%SystemRoot%\\cursors\\aero_pen.cur",
    "SizeAll": "%SystemRoot%\\cursors\\aero_move.cur",
    "SizeNESW": "%SystemRoot%\\cursors\\aero_nesw.cur",
    "SizeNS": "%SystemRoot%\\cursors\\aero_ns.cur",
    "SizeNWSE": "%SystemRoot%\\cursors\\aero_nwse.cur",
    "SizeWE": "%SystemRoot%\\cursors\\aero_ew.cur",
    "UpArrow": "%SystemRoot%\\cursors\\aero_up.cur",
    "Wait": "%SystemRoot%\\cursors\\aero_busy.ani",
}
# Preto (_r) e invertido (_i): arquivos de %SystemRoot%\cursors; o Windows 11 não troca a cor só
# por CursorType. Sufixo do tamanho: "" normal, "l" grande, "m" extra grande.
_ARQUIVO_FUNCAO = {
    "AppStarting": "wait",
    "Arrow": "arrow",
    "Crosshair": "cross",
    "Help": "help",
    "IBeam": "beam",
    "No": "no",
    "NWPen": "pen",
    "SizeAll": "move",
    "SizeNESW": "size2",
    "SizeNS": "size4",
    "SizeNWSE": "size1",
    "SizeWE": "size3",
    "UpArrow": "up",
    "Wait": "busy",
}
_MAO = {
    "preto": ("aero_link.cur", "aero_link_l.cur", "aero_link_xl.cur"),
    "invertido": ("aero_link_i.cur", "aero_link_il.cur", "aero_link_im.cur"),
}
CORES = {"branco": "Branco", "preto": "Preto", "invertido": "Invertido"}
TAMANHOS = {"normal": "normal", "grande": "grande", "extra": "extra grande"}
_NIVEL = {"normal": 0, "grande": 1, "extra": 2}


def _ponteiro(opcao: str) -> list[Escrita]:
    cor, tam = opcao.split("_")
    nivel = _NIVEL[tam]
    if cor == "branco":
        tamanho = (1, 6, 11)[nivel]
        return [
            *((_CURSORES, n, "expand_sz", v) for n, v in _PADRAO_PONTEIROS.items()),
            (_CURSORES, "Scheme Source", "dword", 2),
            (_CURSORES, "CursorBaseSize", "dword", 32 + (tamanho - 1) * 16),
            (_ACESS, "CursorSize", "dword", tamanho),
            (_ACESS, "CursorType", "dword", 0),
        ]
    sufixo = ("r" if cor == "preto" else "i") + ("", "l", "m")[nivel]
    return [
        *(
            (_CURSORES, n, "expand_sz", f"%SystemRoot%\\cursors\\{base}_{sufixo}.cur")
            for n, base in _ARQUIVO_FUNCAO.items()
        ),
        (_CURSORES, "Hand", "expand_sz", f"%SystemRoot%\\cursors\\{_MAO[cor][nivel]}"),
        (_CURSORES, "Scheme Source", "dword", 1),
        (_CURSORES, "CursorBaseSize", "dword", 32),
        (_ACESS, "CursorSize", "dword", 1),
        (_ACESS, "CursorType", "dword", 0),
    ]


def _um(chave: str, nome: str) -> Callable[[str], list[Escrita]]:
    return lambda v: [(chave, nome, "sz", v)]


_FLAGS = (
    ("StickyKeys", "506", "510"),
    ("Keyboard Response", "122", "126"),
    ("ToggleKeys", "58", "62"),
)


def _atalho(opcao: str) -> list[Escrita]:
    i = 1 if opcao == "desligado" else 2
    return [(_SHIFT + f[0], "Flags", "sz", f[i]) for f in _FLAGS]


@dataclass(frozen=True)
class Ajuste:
    id: str
    nome: str
    opcoes: Mapping[str, str]  # valor → rótulo
    padrao: str
    escritas: Callable[[str], list[Escrita]]


CATALOGO: tuple[Ajuste, ...] = (
    Ajuste(
        "ponteiro",
        "Ponteiro do mouse",
        {f"{c}_{t}": f"{CORES[c]}, {TAMANHOS[t]}" for c in CORES for t in TAMANHOS},
        "branco_normal",
        _ponteiro,
    ),
    Ajuste(
        "velocidade",
        "Velocidade do ponteiro",
        {str(n): str(n) for n in range(1, 21)},
        "10",
        _um(_MOUSE, "MouseSensitivity"),
    ),
    Ajuste(
        "duplo_clique",
        "Velocidade do duplo clique",
        {str(n): f"{n} ms" for n in range(200, 1000, 100)},
        "500",
        _um(_MOUSE, "DoubleClickSpeed"),
    ),
    Ajuste(
        "botoes",
        "Botões do mouse",
        {"0": "normais (principal à esquerda)", "1": "invertidos (canhoto)"},
        "0",
        _um(_MOUSE, "SwapMouseButtons"),
    ),
    Ajuste(
        "teclado_atraso",
        "Atraso da repetição do teclado",
        {"0": "curto", "1": "médio", "2": "longo", "3": "muito longo"},
        "1",
        _um(_TECLADO, "KeyboardDelay"),
    ),
    Ajuste(
        "teclado_velocidade",
        "Velocidade da repetição do teclado",
        {str(n): str(n) for n in range(32)},
        "31",
        _um(_TECLADO, "KeyboardSpeed"),
    ),
    Ajuste(
        "atalho_shift",
        "Atalho Shift 5x (Teclas de aderência)",
        {"desligado": "desligado", "padrao": "ligado (padrão)"},
        "padrao",
        _atalho,
    ),
)
POR_ID = {a.id: a for a in CATALOGO}

Estado = Literal["padrao", "ajustado", "diferente", "nao_lida", "sem_acesso"]
ROTULO_ESTADO: dict[Estado, str] = {
    "padrao": "padrão do Windows",
    "ajustado": "ajustado",
    "diferente": "diferente",
    "nao_lida": "não lida",
    "sem_acesso": "sem acesso",
}


@dataclass(frozen=True)
class Situacao:
    estado: Estado
    valor: str | None = None  # opção reconhecida


def _chaves() -> list[dict[str, Any]]:
    nomes: dict[str, list[str]] = {}
    for a in CATALOGO:
        for opcao in a.opcoes:
            for chave, nome, _, _ in a.escritas(opcao):
                lista = nomes.setdefault(chave, [])
                if nome not in lista:
                    lista.append(nome)
    return [{"escopo": "usuario", "chave": c, "nomes": n} for c, n in nomes.items()]


def estado(ajuste: Ajuste, valores: Mapping[str, str | None]) -> Situacao:
    """`valores`: "chave|nome" → texto lido. Valor ausente conta como o padrão do Windows."""
    padrao = {(c, n): str(d) for c, n, _, d in ajuste.escritas(ajuste.padrao)}

    def casa(opcao: str) -> bool:
        for c, n, _, d in ajuste.escritas(opcao):
            lido = valores.get(f"{c}|{n}")
            if (lido if lido is not None else padrao.get((c, n))) != str(d):
                return False
        return True

    if casa(ajuste.padrao):
        return Situacao("padrao", ajuste.padrao)
    for opcao in ajuste.opcoes:
        if casa(opcao):
            return Situacao("ajustado", opcao)
    return Situacao("diferente")


def ler(
    alvos_: Sequence[Alvo], *, rodar: Rodar = executor.powershell, descarregados: bool = False
) -> dict[tuple[str, str], Situacao]:
    """(ajuste, alvo.chave) → situação."""
    usuarios = [a for a in alvos_ if a.tipo != "maquina"]
    _, _, dados = hive.ler(
        usuarios, _chaves(), perfil="aparencia", rodar=rodar, descarregados=descarregados
    )
    saida = {}
    for a in usuarios:
        d = dados.get(a.chave)
        for aj in CATALOGO:
            if d == hive.NAO_LIDA:
                saida[(aj.id, a.chave)] = Situacao("nao_lida")
            elif not isinstance(d, dict) or not d.get("ok"):
                saida[(aj.id, a.chave)] = Situacao("sem_acesso")
            else:
                saida[(aj.id, a.chave)] = estado(aj, d.get("valores") or {})
    return saida


def operacoes(escolhas: Mapping[str, str]) -> list[dict[str, Any]]:
    """`escolhas`: ajuste → opção (desfazer = a opção padrão). Só valores do catálogo."""
    ops = []
    for aid, opcao in escolhas.items():
        ajuste = POR_ID.get(aid)
        if ajuste is None or opcao not in ajuste.opcoes:
            raise ValueError(f"Ajuste ou valor fora da lista: {aid!r}")
        for chave, nome, tipo, dado in ajuste.escritas(opcao):
            if chave not in CHAVES_ACEITAS:
                raise ValueError(f"Chave fora da lista: {aid}")
            ops.append(
                {
                    "p": aid,
                    "chave": chave,
                    "nome": nome,
                    "tipo": tipo,
                    "dado": dado,
                    "acao": "gravar",
                }
            )
    return ops


def aplicar(
    acao: Acao,
    escolhas: Mapping[str, str],
    alvos_: Sequence[Alvo],
    *,
    protegidas_: Iterable[str],
    rodar: Rodar = executor.powershell,
    cancelar: threading.Event | None = None,
    avisar: Callable[[str], None] = lambda _: None,
) -> list[Feito]:
    """Aplicar as opções escolhidas, ou desfazer (padrão do Windows) os ajustes das chaves."""
    if acao == "desfazer":
        escolhas = {aid: POR_ID[aid].padrao if aid in POR_ID else "" for aid in escolhas}
    ops = operacoes(escolhas)
    return hive.aplicar(
        acao,
        [a for a in alvos_ if a.tipo != "maquina"],
        lambda _: ops,
        nomes={a.id: a.nome for a in CATALOGO},
        rotulo="Mouse e teclado",
        item="ajuste",
        perfil="aparencia",
        protegidas_=protegidas_,
        rodar=rodar,
        cancelar=cancelar,
        avisar=avisar,
        mensagens=hive.MENSAGENS_APARENCIA,
    )
