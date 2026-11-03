"""Bring a received session to the current contract before it is stored or prompted (ADR-018).

The pendrive contract lives in pendrive/SCHEMA.md; each version change has a rule here.
"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

VERSOES = ("1.0", "1.1", "1.2")
MODULOS = ("disco", "eventlog", "rede", "processos", "bateria")

# Copy of pendrive/config/eventlog-conhecidos.json (ADR-022); CI fails if they differ.
BASE_EVENTOS = {
    (evento["provedor"].lower(), int(evento["id"])): evento
    for evento in json.loads(Path(__file__).with_name("eventlog-conhecidos.json").read_text("utf-8"))["eventos"]
}
CAMPOS_BASE = ("apelido", "categoria", "peso", "descricao", "acaoSugerida", "nota", "fonteOficial")
ORDEM_NIVEL = {"critico": 0, "erro": 1, "aviso": 2}
# Same list and order as $script:ContadoresSmart in pendrive/modulos/Coleta-Disco.ps1.
CONTADORES_SMART = (
    "errosLeituraNaoCorrigidos", "errosEscritaNaoCorrigidos", "errosLeituraCorrigidos",
    "errosEscritaCorrigidos", "temperaturaC", "temperaturaMaximaC", "horasLigado", "percentualDesgaste",
)

AVISO_PENDRIVE_1_0 = (
    "Sessão no contrato 1.0: o volume e o disco do próprio pendrive podem aparecer em "
    "volumes e discosFisicos."
)
AVISO_EVENTOS_1_0 = (
    "Sessão no contrato 1.0: Avisos (Level 3) do Event Log não foram lidos, então disk 51 "
    "não aparece mesmo que tenha ocorrido."
)


def normalizar(entrada: dict) -> tuple[dict, list[str]]:
    """Return (session in the current contract, notices to show in the report)."""
    sessao = copy.deepcopy(entrada["sessao"])
    modulos = {nome: copy.deepcopy(modulo) for nome, modulo in (entrada.get("modulos") or {}).items() if nome in MODULOS}
    avisos: list[str] = []
    sessao["hostname"] = sessao["hostname"].strip().upper()

    if sessao["versaoSchema"] == "1.0":
        de_1_0(sessao, modulos, avisos)

    # 1.0 and 1.1: usuarioLogado is $env:USERNAME, the account that elevated the tool, not
    # the user of the machine. Kept under its 1.2 name (usuarioExecucao), never prompted;
    # 1.2 already sends usuarioExecucao and usuarioSessao.
    if "usuarioLogado" in sessao:
        sessao["usuarioExecucao"] = sessao.pop("usuarioLogado")
    sessao.setdefault("usuarioSessao", None)

    for disco in lista(dados(modulos, "disco"), "discosFisicos"):
        # Wear 0 with no power-on hours is a driver that reports nothing, not a new disk.
        if disco.get("percentualDesgaste") == 0 and disco.get("horasLigado") is None:
            disco["percentualDesgaste"] = None
            disco["observacao"] = juntar(
                disco.get("observacao"), "percentualDesgaste 0 com horasLigado nulo: tratado como não informado."
            )

    return {"sessao": sessao, "modulos": modulos, "correcoes": copy.deepcopy(entrada.get("correcoes"))}, avisos


def de_1_0(sessao: dict, modulos: dict, avisos: list[str]) -> None:
    disco = dados(modulos, "disco")
    if disco is not None:
        itens = lista(disco, "itensLimpeza")
        resumo = disco.get("resumo")
        if isinstance(resumo, dict):
            # 1.0 always wrote 0 here (Measure-Object over [ordered]); same rule as Get-ResumoTier.
            for tier, campo_bytes, campo_itens in (
                ("seguro", "recuperavelSeguroBytes", "itensSeguroComConteudo"),
                ("revisar", "revisarBytes", "itensRevisar"),
            ):
                com_conteudo = [item for item in itens if item.get("tier") == tier and item.get("bytes")]
                resumo[campo_bytes] = sum(int(item["bytes"]) for item in com_conteudo)
                resumo[campo_itens] = len(com_conteudo)
        for chave in ("itensLimpeza", "maioresPastasPerfil"):
            if chave in disco:
                disco[chave] = sorted(lista(disco, chave), key=lambda item: item.get("bytes") or 0, reverse=True)
        for fisico in lista(disco, "discosFisicos"):
            de_1_0_smart(fisico)
        avisos.append(AVISO_PENDRIVE_1_0)

    eventlog = dados(modulos, "eventlog")
    if eventlog is not None:
        grupos = lista(eventlog, "grupos")
        for grupo in grupos:
            reclassificar(grupo)
        grupos.sort(key=lambda g: (ORDEM_NIVEL.get(g.get("nivel"), 3), -(g.get("ocorrencias") or 0)))
        eventlog["grupos"] = grupos
        eventlog["gruposDesconhecidos"] = sum(1 for g in grupos if not g["conhecido"])
        avisos.append(AVISO_EVENTOS_1_0)

    for adaptador in lista(dados(modulos, "rede"), "adaptadores"):
        # 1.1 rule (Test-Apipa): 169.254.x.x only matters on a connected adapter.
        enderecos = adaptador.get("enderecosIPv4") or []
        adaptador["apipa"] = adaptador.get("status") == "Up" and any(str(ip).startswith("169.254.") for ip in enderecos)

    if sessao.get("ultimaAtualizacao") is None:
        sessao["ultimaAtualizacao"] = aproximar_fim(sessao.get("inicio"), sessao.get("duracaoSegundos"))


def de_1_0_smart(fisico: dict) -> None:
    if "percentualVidaRestante" in fisico:
        # The value was always Wear (ADR-019): copy without converting.
        fisico["percentualDesgaste"] = fisico.pop("percentualVidaRestante")
    disponivel = fisico.pop("smartDisponivel", None)
    for campo in ("temperaturaC", "temperaturaMaximaC"):
        if fisico.get(campo) == 0:
            fisico[campo] = None
    ausentes = [campo for campo in CONTADORES_SMART if fisico.get(campo) is None]
    if not ausentes:
        fisico["estadoSmart"] = "completo"
    elif len(ausentes) == len(CONTADORES_SMART):
        fisico["estadoSmart"] = "indisponivel"
        if disponivel:
            fisico["observacao"] = juntar(fisico.get("observacao"), "O driver não informou nenhum contador SMART.")
    else:
        fisico["estadoSmart"] = "parcial"
        fisico["observacao"] = juntar(
            fisico.get("observacao"), "Contadores não expostos pelo driver: " + ", ".join(ausentes) + "."
        )


def reclassificar(grupo: dict) -> None:
    """ADR-020: known only when provider and id both match the base."""
    try:
        chave = (str(grupo.get("provedor", "")).lower(), int(grupo.get("id")))
    except (TypeError, ValueError):
        chave = None
    evento = BASE_EVENTOS.get(chave)
    grupo["conhecido"] = evento is not None
    for campo in CAMPOS_BASE:
        grupo[campo] = evento.get(campo) if evento else None
    if evento:
        grupo["exemploMensagem"] = None


def aproximar_fim(inicio, duracao):
    try:
        return (datetime.fromisoformat(inicio) + timedelta(seconds=float(duracao))).isoformat()
    except (TypeError, ValueError):
        return None


def resumir(normalizada: dict) -> dict:
    """Few fields per session for the history of the hostname (prompt and GET /v1/historico)."""
    disco = dados(normalizada["modulos"], "disco") or {}
    eventlog = dados(normalizada["modulos"], "eventlog") or {}
    bateria = dados(normalizada["modulos"], "bateria") or {}
    processos = dados(normalizada["modulos"], "processos") or {}
    rede = dados(normalizada["modulos"], "rede") or {}
    return {
        "volumes": [{"letra": v.get("letra"), "percentualLivre": v.get("percentualLivre")} for v in lista(disco, "volumes")],
        "discos": [
            {campo: d.get(campo) for campo in ("modelo", "estadoSmart", "percentualDesgaste", "temperaturaC")}
            for d in lista(disco, "discosFisicos")
        ],
        "eventosPesoAlto": [
            {"apelido": g.get("apelido"), "ocorrencias": g.get("ocorrencias")}
            for g in lista(eventlog, "grupos")
            if g.get("peso") == "alto"
        ],
        "totalGruposEventos": eventlog.get("totalGrupos"),
        "bateriaDesgastePercentual": bateria.get("desgastePercentual"),
        "memoriaPercentualEmUso": (processos.get("memoria") or {}).get("percentualEmUso"),
        "internetOk": (rede.get("resumo") or {}).get("internetOk"),
    }


def dados(modulos: dict, nome: str):
    valor = (modulos.get(nome) or {}).get("dados")
    return valor if isinstance(valor, dict) else None


def lista(origem, chave: str) -> list:
    valor = (origem or {}).get(chave)
    return [item for item in valor if isinstance(item, dict)] if isinstance(valor, list) else []


def juntar(atual, texto: str) -> str:
    return f"{atual} {texto}" if atual else texto
