"""Hive de outro usuário (ADR-021, ADR-022), sem Qt: alvos, ler, escrever e o laço por alvo.

Comum a Políticas (11) e Aparência (12). Leitura e escrita pelos trechos de `recursos/politicas/`
no executor, sempre na vista de 64 bits; `ITC_PERFIL` escolhe as raízes aceitas, que ficam fixas
no `comum.ps1`. Este módulo nunca abre o registro (sem `winreg`): o hive temporário
`HKU\\ITCBench_*` só é tocado pelo trecho. Log sem nome de conta, SID, caminho de perfil nem nome
do hive temporário.
"""

import json
import secrets
import struct
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Literal

from itc_bench.nucleo.log import log
from itc_bench.servicos import contas, executor

RECURSOS = resources.files("itc_bench.recursos") / "politicas"
TIMEOUT_LER, TIMEOUT_ESCREVER, TIMEOUT_HIVE = 60.0, 60.0, 30.0
TENTATIVAS_DESCARREGAR = 3

Escopo = Literal["usuario", "maquina"]
Acao = Literal["aplicar", "desfazer"]
Perfil = Literal["politicas", "aparencia"]
Rodar = Callable[..., executor.Resultado]

MENSAGENS = {
    "nativo": "O Administrador nativo do Windows não recebe políticas pelo Bench.",
    "suporte": "A conta Suporte não recebe políticas (o técnico precisa dela livre).",
    "dono": "É a conta que está rodando o Bench: entre com outra conta para aplicar nesta.",
    "sem_perfil": "A conta ainda não tem perfil (nunca entrou): entre nela uma vez.",
    "perfil_fora": "O perfil não fica em Usuários do disco do Windows: recusado.",
    "perfil_temporario": "Perfil temporário do Windows: recusado.",
    "em_uso": "O perfil está em uso por outro programa: reinicie e tente de novo.",
    "carregar": "O Windows não abriu o perfil da conta: reinicie e tente de novo.",
    "nao_encontrada": "A conta não existe mais. Atualize a lista.",
    "carregado": "O perfil foi carregado nesse meio-tempo. Atualize e tente de novo.",
    "descarregar": "O perfil ainda está carregado: reinicie antes de entrar nessa conta.",
    "tempo_esgotado": "Tempo esgotado.",
    "cancelado": "Cancelado pelo técnico (antes deste alvo).",
    "bits": "O Bench precisa rodar em 64 bits para ler o registro certo.",
}
# Aparência (ADR-022): as mesmas recusas, sem falar em política.
MENSAGENS_APARENCIA = {
    **MENSAGENS,
    "nativo": "O Administrador nativo do Windows não é alterado pelo Bench.",
    "suporte": "A conta Suporte não é alterada (o técnico precisa dela como está).",
}


# ---------------------------------------------------------------- alvos


@dataclass(frozen=True)
class Alvo:
    chave: str  # "maquina", "padrao" ou o SID
    rotulo: str  # só para a tela
    carregado: bool = False
    admin: bool = False

    @property
    def escopo(self) -> Escopo:
        return "maquina" if self.chave == "maquina" else "usuario"

    @property
    def tipo(self) -> str:
        return self.chave if self.chave in ("maquina", "padrao") else "usuario"


MAQUINA = Alvo("maquina", "Máquina")
PADRAO = Alvo("padrao", "Contas futuras")


def alvos(lista: contas.Lista) -> list[Alvo]:
    return [MAQUINA, PADRAO] + [Alvo(c.sid, c.nome, c.carregado, c.admin) for c in lista.contas]


def sids_protegidos(lista: contas.Lista, protegidas_: Iterable[str]) -> list[str]:
    prot = {n.lower() for n in protegidas_}
    return [c.sid for c in lista.contas if c.nativo or c.nome.lower() in prot]


def recusa_alvo(
    alvo: Alvo,
    lista: contas.Lista,
    protegidas_: Iterable[str],
    dono: str | None,
    *,
    permitir_dono: bool = False,
) -> str | None:
    """Código da recusa (chave de MENSAGENS) ou None. O trecho confere de novo.

    `permitir_dono`: Políticas (ADR-034) e a tela do papel de parede (ADR-039) aceitam a conta
    que roda o Bench; mouse e teclado e a Preparação completa não.
    """
    if alvo.tipo != "usuario":
        return None
    conta = lista.por_sid(alvo.chave)
    if conta is None:
        return "nao_encontrada"
    if conta.nativo:
        return "nativo"
    if conta.nome.lower() in {n.lower() for n in protegidas_}:
        return "suporte"
    if dono and conta.sid == dono and not permitir_dono:
        return "dono"
    if not conta.perfil:
        return "sem_perfil"
    return None


# ---------------------------------------------------------------- trechos


def bits() -> None:
    if struct.calcsize("P") != 8:
        raise RuntimeError(MENSAGENS["bits"])


def script(nome: str) -> str:
    return (
        (RECURSOS / "comum.ps1").read_text("utf-8")
        + "\n"
        + (RECURSOS / f"{nome}.ps1").read_text("utf-8")
    )


def linhas(r: executor.Resultado) -> list[str]:
    return [linha.strip() for linha in r.saida.splitlines() if linha.strip()]


def codigo(r: executor.Resultado) -> str:
    if r.esgotado:
        return "tempo_esgotado"
    for linha in linhas(r):
        if linha.startswith("ERRO|"):
            return linha.split("|")[1] or "erro"
    return f"powershell_{r.codigo}"


def grupos(alvo: Alvo) -> list[str]:
    """Quem, se tiver escrita ou for dono da chave, deixa o usuário alterar a política."""
    base = ["S-1-1-0", "S-1-5-11", "S-1-5-4", "S-1-5-32-545"]
    if alvo.tipo == "padrao":
        return base
    return [alvo.chave, *base, *(["S-1-5-32-544"] if alvo.admin else [])]


def ler_hives(
    pedidos: Sequence[tuple[str, Alvo]],
    rodar: Rodar,
    chaves: list[dict[str, Any]],
    perfil: Perfil = "politicas",
) -> tuple[str, str, dict[str, Any]]:
    """`chaves`: [{escopo, chave, nomes}]. Na aparência não há "o usuário pode alterar"."""
    leitura = [
        {"hive": h, "grupos": grupos(a) if a.tipo != "maquina" and perfil == "politicas" else []}
        for h, a in pedidos
    ]
    r = rodar(
        script("ler"),
        timeout=TIMEOUT_LER,
        leitura=json.dumps(leitura),
        chaves=json.dumps(chaves),
        perfil=perfil,
    )
    if not r.ok:
        raise RuntimeError(f"Leitura do registro falhou ({codigo(r)}).")
    try:
        cru = json.loads(r.saida)
        return str(cru["edicao"]), str(cru["dono"]), dict(cru["hives"] or {})
    except (json.JSONDecodeError, KeyError, TypeError) as erro:
        raise RuntimeError(f"Saída inválida da leitura ({type(erro).__name__}).") from None


NAO_LIDA = "nao_lida"


def ler(
    alvos_: Sequence[Alvo],
    chaves: list[dict[str, Any]],
    *,
    perfil: Perfil = "politicas",
    rodar: Rodar,
    descarregados: bool = False,
) -> tuple[str, str, dict[str, dict[str, Any] | str | None]]:
    """(edição, dono, alvo.chave → dados do trecho, None se falhou, ou NAO_LIDA).

    Perfil descarregado (e Contas futuras) só com `descarregados=True` (botão "Ler"), que passa
    pelo carregar/descarregar."""
    bits()
    diretos = [
        (("MAQUINA" if a.tipo == "maquina" else a.chave), a)
        for a in alvos_
        if a.tipo == "maquina" or (a.tipo == "usuario" and a.carregado)
    ]
    edicao, dono, hives = ler_hives(diretos, rodar, chaves, perfil)
    saida: dict[str, dict[str, Any] | str | None] = {}
    for hive, a in diretos:
        saida[a.chave] = hives.get(hive)
    for a in alvos_:
        if a.tipo == "maquina" or (a.tipo == "usuario" and a.carregado):
            continue
        if not descarregados:
            saida[a.chave] = NAO_LIDA
            continue
        limpar_sobras(rodar)
        temp = carregar(a, rodar)
        if not temp.startswith("ITCBench_"):
            log.warning("Hive: ler alvo %s: %s", a.tipo, temp)
            saida[a.chave] = None
            continue
        try:
            _, _, h = ler_hives([(temp, a)], rodar, chaves, perfil)
            saida[a.chave] = h.get(temp)
        finally:
            descarregar(temp, rodar)
    return edicao, dono, saida


def limpar_sobras(rodar: Rodar) -> str:
    """Descarrega `HKU\\ITCBench_*` que sobraram; devolve o SID dono do processo."""
    r = rodar(script("hive"), timeout=TIMEOUT_HIVE, acao="sobras")
    ls = linhas(r)
    falhas = sum(1 for linha in ls if linha == "SOBRA|falhou")
    feitas = sum(1 for linha in ls if linha == "SOBRA|ok")
    if feitas or falhas:
        log.warning("Hive: perfis temporários de antes: %s ok, %s falharam", feitas, falhas)
    for linha in ls:
        if linha.startswith("DONO|"):
            return linha[5:]
    raise RuntimeError(f"Não foi possível conferir a conta do Bench ({codigo(r)}).")


def carregar(alvo: Alvo, rodar: Rodar, prot: Sequence[str] = ()) -> str:
    """Nome do hive temporário, ou o código da falha."""
    temp = f"ITCBench_{secrets.token_hex(4)}"
    sid = "DEFAULT" if alvo.tipo == "padrao" else alvo.chave
    r = rodar(
        script("hive"),
        timeout=TIMEOUT_HIVE,
        acao="carregar",
        sid=sid,
        hive=temp,
        protegidos="\n".join(prot),
    )
    return temp if r.ok and "OK" in linhas(r) else codigo(r)


def descarregar(temp: str, rodar: Rodar) -> bool:
    """Sem cancelamento; até 3 tentativas. False = ficou carregado (a tela avisa)."""
    for _ in range(TENTATIVAS_DESCARREGAR):
        r = rodar(script("hive"), timeout=TIMEOUT_HIVE, acao="descarregar", hive=temp)
        if r.ok:
            return True
    log.error("Hive: perfil temporário não descarregado (código %s)", codigo(r))
    return False


# ---------------------------------------------------------------- escrever por alvo


@dataclass(frozen=True)
class Feito:
    alvo: Alvo
    ok: bool
    mensagem: str
    politicas: dict[str, bool] = field(default_factory=dict)  # id do item → ok
    avisos: tuple[str, ...] = ()


def escrever(
    hive: str,
    ops: list[dict[str, Any]],
    prot: list[str],
    rodar: Rodar,
    perfil: Perfil,
    permitir_dono: bool = False,
) -> tuple[dict[str, bool], str | None]:
    r = rodar(
        script("escrever"),
        timeout=TIMEOUT_ESCREVER,
        hive=hive,
        operacoes=json.dumps(ops),
        protegidos="\n".join(prot),
        perfil=perfil,
        permitir_dono="1" if permitir_dono else "0",
    )
    por: dict[str, bool] = {}
    for linha in linhas(r):
        partes = linha.split("|")
        if partes[0] == "OK" and len(partes) == 2:
            por.setdefault(partes[1], True)
        elif partes[0] == "ERRO" and len(partes) == 3:
            por[partes[2]] = False
    return por, (None if r.ok else codigo(r))


def aplicar(
    acao: Acao,
    alvos_: Sequence[Alvo],
    operacoes: Callable[[Alvo], list[dict[str, Any]]],
    *,
    nomes: Mapping[str, str],
    rotulo: str,
    item: str,
    perfil: Perfil,
    protegidas_: Iterable[str],
    rodar: Rodar,
    cancelar: threading.Event | None = None,
    avisar: Callable[[str], None] = lambda _: None,
    mensagens: Mapping[str, str] = MENSAGENS,
    permitir_dono: bool = False,
) -> list[Feito]:
    """Uma chamada de escrita por alvo, nunca interrompida; cancelar vale entre alvos.

    `rotulo`/`item` só formam a linha de log ("Políticas"/"politica")."""
    bits()
    prot_nomes = frozenset(protegidas_)
    dono = limpar_sobras(rodar)
    lista = contas.listar(rodar=rodar)
    prot = sids_protegidos(lista, prot_nomes)
    feitos: list[Feito] = []
    for n, alvo in enumerate(alvos_, 1):
        rotulo_log = alvo.tipo if alvo.tipo != "usuario" else f"usuario {n}"
        if cancelar is not None and cancelar.is_set():
            feitos.append(Feito(alvo, False, mensagens["cancelado"]))
            log.warning("%s: %s alvo %s: cancelado", rotulo, acao, rotulo_log)
            continue
        ops = operacoes(alvo)
        if not ops:
            continue
        motivo = recusa_alvo(alvo, lista, prot_nomes, dono, permitir_dono=permitir_dono)
        if motivo:
            feitos.append(Feito(alvo, False, mensagens[motivo]))
            log.warning("%s: %s alvo %s: recusado (%s)", rotulo, acao, rotulo_log, motivo)
            continue
        avisar(f"{alvo.rotulo}: {acao}…")
        conta = lista.por_sid(alvo.chave) if alvo.tipo == "usuario" else None
        temp: str | None = None
        avisos: list[str] = []
        if alvo.tipo == "maquina":
            hive = "MAQUINA"
        elif conta is not None and conta.carregado:
            hive = alvo.chave
        else:
            carregado = carregar(alvo, rodar, prot)
            if not carregado.startswith("ITCBench_"):
                feitos.append(Feito(alvo, False, mensagens.get(carregado, carregado)))
                log.error("%s: %s alvo %s: carregar: %s", rotulo, acao, rotulo_log, carregado)
                continue
            hive = temp = carregado
        try:
            por, geral = escrever(hive, ops, prot, rodar, perfil, permitir_dono)
        finally:
            if temp is not None and not descarregar(temp, rodar):
                avisos.append(mensagens["descarregar"])
        pedidos = list(dict.fromkeys(op["p"] for op in ops))
        for pid in pedidos:
            ok = por.get(pid, False) and geral is None
            log.info(
                "%s: %s alvo %s %s=%s resultado=%s codigo=%s",
                rotulo,
                acao,
                rotulo_log,
                item,
                pid,
                "ok" if ok else "erro",
                "0" if ok else (geral or "parcial"),
            )
        resultado = {pid: bool(por.get(pid)) and geral is None for pid in pedidos}
        ok = all(resultado.values())
        if ok:
            msg = "Feito."
        elif geral:
            msg = mensagens.get(geral, f"Falhou ({geral}).")
        else:
            msg = "Falhou em: " + ", ".join(nomes[p] for p, v in resultado.items() if not v)
        feitos.append(Feito(alvo, ok, msg, resultado, tuple(avisos)))
    return feitos
