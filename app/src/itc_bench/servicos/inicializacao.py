"""Inicialização do Windows (ADR-075), sem Qt: o que abre sozinho ao ligar ou entrar na conta,
os serviços de terceiros e o tempo de boot. Desligar é reversível e nunca apaga nada.

Os trechos leem e conferem tudo de novo antes de mexer; o Python só escolhe da leitura. O log
leva só contagens e códigos, nunca o comando (pode ter caminho de conta).
"""

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import resources
from typing import Any

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

Rodar = Callable[..., executor.Resultado]
RECURSOS = resources.files("itc_bench.recursos") / "inicializacao"
TIMEOUT_LER = 180
TIMEOUT_DESLIGAR = 180
MAQUINA = "MAQUINA"

TIPOS = {
    "run": "Registro",
    "run32": "Registro",
    "runuser": "Registro",
    "pasta": "Pasta Inicializar",
    "pastauser": "Pasta Inicializar",
    "app": "App da Loja",
    "tarefa": "Tarefa agendada",
}
# Nunca desligados (conferido também no trecho): acesso remoto, inventário, antivírus, áudio e o
# próprio Bench.
ESSENCIAL = re.compile(
    r"anydesk|rustdesk|glpi|securityhealth|windows ?defender|rtkaud|itc.?bench", re.I
)
# Sem função num notebook de aluno: já vêm marcados para desligar.
RECOMENDADO = re.compile(
    r"one ?drive|tailscale|riot|vanguard|vgtray|roblox|steam|epic ?games|discord|spotify|"
    r"msedge|microsoftedge|teams|copilot|yourphone|phonelink|crossdevice|"
    r"dispositivos m[oó]veis|mobile devices|onenotem|send to onenote|enviar para o onenote|"
    r"webexperience|bingsearch|xbox|gamingapp|lenovonow|mcafee|clipchamp|zunemusic|skype|"
    r"whatsapp|ccleaner|utorrent",
    re.I,
)
CODIGOS = {
    "essencial": "essencial: não é desligado",
    "invalido": "item inválido",
    "sem_conta": "a conta não existe mais",
    "conta_em_uso": "não deu para abrir o registro da conta",
    "sumiu": "não está mais na inicialização",
    "falhou": "o Windows recusou",
}


@dataclass(frozen=True)
class Item:
    tipo: str
    sid: str
    conta: str  # vazio = máquina (todas as contas)
    nome: str
    comando: str
    ativo: bool

    @property
    def chave(self) -> tuple[str, str, str]:
        return (self.tipo, self.sid, self.nome)

    @property
    def titulo(self) -> str:
        if self.tipo == "app":
            return self.comando  # família do pacote, sem o sufixo do editor
        nome = self.nome.rsplit("\\", 1)[-1] if self.tipo == "tarefa" else self.nome
        return re.sub(r"\.lnk$", "", nome, flags=re.I)

    @property
    def essencial(self) -> bool:
        return bool(ESSENCIAL.search(f"{self.nome} {self.comando}"))

    @property
    def recomendado(self) -> bool:
        return not self.essencial and bool(RECOMENDADO.search(f"{self.nome} {self.comando}"))

    @property
    def onde(self) -> str:
        return self.conta or "Todas as contas"


@dataclass(frozen=True)
class Servico:
    nome: str
    rodando: bool
    comando: str


@dataclass(frozen=True)
class Boot:
    data: str
    boot_ms: int
    pos_ms: int


@dataclass(frozen=True)
class Atraso:
    data: str
    nome: str
    atraso_ms: int


@dataclass(frozen=True)
class Leitura:
    itens: tuple[Item, ...]
    servicos: tuple[Servico, ...]
    boots: tuple[Boot, ...]
    atrasos: tuple[Atraso, ...]


@dataclass(frozen=True)
class Resultado:
    item: Item
    codigo: str

    @property
    def ok(self) -> bool:
        return not self.codigo

    @property
    def motivo(self) -> str:
        return CODIGOS.get(self.codigo, self.codigo)


def segundos(ms: int) -> str:
    return f"{ms / 1000:.1f} s".replace(".", ",")


def _script(nome: str) -> str:
    return (RECURSOS / "comum.ps1").read_text("utf-8") + (RECURSOS / nome).read_text("utf-8")


def _json(r: executor.Resultado, acao: str) -> Any:
    if not r.ok:
        motivo = "tempo esgotado" if r.esgotado else f"código {r.codigo}"
        log.error("Inicialização: %s falhou (%s)", acao, motivo)
        raise RuntimeError(motivo)
    try:
        return json.loads(r.saida)
    except json.JSONDecodeError:
        raise RuntimeError("Saída inválida (JSONDecodeError).") from None


def _lista(d: Any, chave: str) -> list[dict[str, Any]]:
    valor = d.get(chave) if isinstance(d, dict) else None
    if isinstance(valor, dict):
        valor = [valor]
    return [x for x in valor or [] if isinstance(x, dict)]


def _item(d: dict[str, Any]) -> Item | None:
    if d.get("tipo") not in TIPOS or not d.get("nome"):
        return None
    sid = str(d.get("sid") or "")
    return Item(
        str(d["tipo"]),
        sid,
        "" if sid == MAQUINA else str(d.get("conta") or ""),
        str(d["nome"]),
        str(d.get("comando") or ""),
        bool(d.get("ativo")),
    )


def ler(*, rodar: Rodar = executor.powershell) -> Leitura:
    script = _script("ler.ps1")
    d = _json(rodar(script, timeout=TIMEOUT_LER), "leitura")
    try:
        itens = tuple(i for i in map(_item, _lista(d, "itens")) if i is not None)
        servicos = tuple(
            Servico(str(s.get("nome") or ""), bool(s.get("rodando")), str(s.get("comando") or ""))
            for s in _lista(d, "servicos")
        )
        boots = tuple(
            Boot(str(b.get("data") or ""), int(b.get("boot_ms") or 0), int(b.get("pos_ms") or 0))
            for b in _lista(d, "boots")
        )
        atrasos = tuple(
            sorted(
                (
                    Atraso(
                        str(a.get("data") or ""),
                        str(a.get("nome") or ""),
                        int(a.get("atraso_ms") or 0),
                    )
                    for a in _lista(d, "atrasos")
                ),
                key=lambda a: -a.atraso_ms,
            )
        )
    except (TypeError, ValueError) as erro:
        raise RuntimeError(f"Saída inválida ({type(erro).__name__}).") from None
    ativos = sum(i.ativo for i in itens)
    log.info(
        "Inicialização: lidos %s itens (%s ligados), %s serviços, %s boots",
        len(itens),
        ativos,
        len(servicos),
        len(boots),
    )
    return Leitura(itens, servicos, boots, atrasos)


def desligar(itens: Iterable[Item], *, rodar: Rodar = executor.powershell) -> list[Resultado]:
    pedidos = [i for i in itens if i.ativo and not i.essencial and i.tipo in TIPOS]
    if not pedidos:
        return []
    por_chave = {i.chave: i for i in pedidos}
    corpo = json.dumps([{"tipo": i.tipo, "sid": i.sid, "nome": i.nome} for i in pedidos])
    script = _script("desligar.ps1")
    d = _json(rodar(script, timeout=TIMEOUT_DESLIGAR, itens=corpo), "desligar")
    resultados = []
    for r in [d] if isinstance(d, dict) else d or []:
        if not isinstance(r, dict):
            continue
        item = por_chave.get((str(r.get("tipo")), str(r.get("sid")), str(r.get("nome"))))
        if item is not None:
            resultados.append(Resultado(item, str(r.get("codigo") or "")))
    ok = sum(r.ok for r in resultados)
    codigos = sorted({r.codigo for r in resultados if not r.ok})
    log.info(
        "Inicialização: desligar %s pedidos, %s ok%s",
        len(pedidos),
        ok,
        f", códigos {','.join(codigos)}" if codigos else "",
    )
    return resultados
