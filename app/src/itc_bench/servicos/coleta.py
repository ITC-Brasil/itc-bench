r"""Coleta do diagnóstico (ADR-015). Sem Qt: o Módulo 13 reusa a varredura de disco.

Cada coletor é um trecho PowerShell em `recursos/coletores/`, rodado pelo executor, que só devolve
JSON cru. As regras do pendrive (`Coleta-*.ps1`) vivem aqui em funções puras, testadas com os
mesmos casos do `Testar-Ferramenta.ps1`. A saída do PowerShell é tratada como não confiável:
tipos e tamanhos validados, listas com teto. Falha de um coletor nunca derruba a coleta.

A `Coleta` guarda nomes de usuário só para o saneamento (`diagnostico.sanear`); nada daqui vai
ao log além de nome do módulo, status, duração e contagens.
"""

import json
import os
import re
import socket
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from itc_bench.nucleo import caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor

RECURSOS = resources.files("itc_bench.recursos") / "coletores"
DIAS_EVENTLOG = 7
# Teto por lista: a saída do coletor não confiável não infla o corpo nem a tela.
TOP_MEMORIA, TOP_CPU = 15, 10
MAX_SERVICOS, MAX_INICIALIZACAO, MAX_PORTAS, MAX_GRUPOS, MAX_ADAPTADORES = 50, 50, 100, 200, 30
MAX_TEXTO = 500
ARQUIVO_MINIMO_MB, PASTA_MINIMA_MB, MAX_ARQUIVOS = 200, 500, 25
TEMPO_VARREDURA = 300.0
PERFIS_IGNORADOS = frozenset({"public", "default", "default user", "all users"})
# Perfis de sistema, além dos acima: nunca tratados como nome de pessoa no saneamento.
PERFIS_SISTEMA = re.compile(r"(?i)^(defaultuser\d*|wdagutilityaccount|defaultapppool)$")
CONTADORES_SMART = (
    "errosLeituraNaoCorrigidos",
    "errosEscritaNaoCorrigidos",
    "errosLeituraCorrigidos",
    "errosEscritaCorrigidos",
    "temperaturaC",
    "temperaturaMaximaC",
    "horasLigado",
    "percentualDesgaste",
)
CONTAS_DE_SISTEMA = re.compile(r"(?i)^(localsystem|nt authority\\.*|nt service\\.*)$")
NIVEIS = {1: "critico", 2: "erro", 3: "aviso"}
ORDEM_NIVEL = {"critico": 0, "erro": 1, "aviso": 2}

ROTULOS = {
    "processos": "Processos, serviços e inicialização",
    "rede": "Rede",
    "eventlog": "Erros recentes (Event Log)",
    "disco": "Disco, espaço e SMART",
    "bateria": "Bateria",
}
TIMEOUTS = {"processos": 60.0, "rede": 60.0, "eventlog": 120.0, "disco": 120.0, "bateria": 60.0}

Rodar = Callable[..., executor.Resultado]


class Cancelado(Exception):
    """O técnico cancelou: a coleta para no próximo ponto de conferência."""


@dataclass
class Modulo:
    nome: str
    status: str  # ok | erro
    erro: str | None
    coletado_em: datetime
    duracao: float
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass
class Coleta:
    hostname: str
    inicio: datetime
    elevado: bool
    maquina: dict[str, Any]
    modulos: dict[str, Modulo] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    fim: datetime | None = None
    encerrada_normalmente: bool = False
    # Só para o saneamento local; nunca vão no corpo.
    nomes_pessoais: list[str] = field(default_factory=list, repr=False)

    @property
    def id(self) -> str:
        return f"{self.inicio:%Y-%m-%d_%H%M}_{self.hostname}"


# ---------------------------------------------------------------- validação da saída crua


def texto(valor: Any, limite: int = MAX_TEXTO) -> str | None:
    if valor is None:
        return None
    conteudo = str(valor)
    return conteudo if len(conteudo) <= limite else conteudo[:limite] + "..."


def inteiro(valor: Any) -> int | None:
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def lista(valor: Any) -> list[dict[str, Any]]:
    if isinstance(valor, dict):  # ConvertTo-Json do PS 5.1 desfaz lista de um item às vezes
        valor = [valor]
    return [item for item in valor if isinstance(item, dict)] if isinstance(valor, list) else []


def textos(valor: Any, limite: int = 20) -> list[str]:
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list):
        return []
    return [t for t in (texto(v, 100) for v in valor[:limite]) if t]


def avisos_de(cru: dict[str, Any]) -> list[str]:
    return [t for t in (texto(v) for v in (cru.get("avisos") or [])[:20]) if t]


# ---------------------------------------------------------------- regras portadas do pendrive


def processos(cru: dict[str, Any]) -> dict[str, Any]:
    """Coleta-Processos.ps1: memória, top por memória/CPU, serviços parados, inicialização."""
    avisos = avisos_de(cru)
    total_kb, livre_kb = numero(cru.get("memoriaTotalKB")), numero(cru.get("memoriaLivreKB"))
    memoria: dict[str, Any] = {
        "totalGB": None,
        "disponivelGB": None,
        "percentualEmUso": None,
        "pressaoAlta": False,
    }
    if total_kb and livre_kb is not None:
        total, livre = round(total_kb / 2**20, 1), round(livre_kb / 2**20, 1)
        uso = round((total - livre) / total * 100, 1)
        memoria.update(
            totalGB=total, disponivelGB=livre, percentualEmUso=uso, pressaoAlta=uso >= 85
        )

    procs: list[dict[str, Any]] = [
        {
            "nome": texto(p.get("nome"), 100) or "",
            "pid": inteiro(p.get("pid")),
            "bytes": inteiro(p.get("memoriaBytes")) or 0,
            "cpu": numero(p.get("cpuSegundos")),
            "inicio": texto(p.get("inicio"), 40),
            "caminho": texto(p.get("caminho")),
        }
        for p in lista(cru.get("processos"))
    ]
    contagem: dict[str, int] = {}
    for p in procs:
        contagem[p["nome"]] = contagem.get(p["nome"], 0) + 1
    por_memoria = [
        {
            "nome": p["nome"],
            "pid": p["pid"],
            "memoriaMB": round(p["bytes"] / 2**20, 1),
            "instancias": contagem[p["nome"]],
            "inicio": p["inicio"],
            "caminho": p["caminho"],
        }
        for p in sorted(procs, key=lambda p: p["bytes"], reverse=True)[:TOP_MEMORIA]
    ]
    por_cpu = [
        {
            "nome": p["nome"],
            "pid": p["pid"],
            "tempoCpuSegundos": round(p["cpu"], 1),
            "memoriaMB": round(p["bytes"] / 2**20, 1),
        }
        for p in sorted((p for p in procs if p["cpu"]), key=lambda p: p["cpu"], reverse=True)[
            :TOP_CPU
        ]
    ]
    servicos = [
        {
            "nome": texto(s.get("nome"), 100),
            "nomeExibicao": texto(s.get("nomeExibicao"), 200),
            "estado": texto(s.get("estado"), 40),
            "inicio": texto(s.get("inicio"), 40),
            "contaLogon": conta_logon(s.get("contaLogon")),
            "atrasado": s.get("atrasado") is True,
        }
        for s in lista(cru.get("servicos"))[:MAX_SERVICOS]
    ]
    # Sem o campo `usuario` do pendrive: é nome de pessoa (ADR-015).
    inicializacao = [
        {
            "nome": texto(i.get("nome"), 200),
            "comando": texto(i.get("comando")),
            "origem": texto(i.get("origem"), 200),
        }
        for i in lista(cru.get("inicializacao"))[:MAX_INICIALIZACAO]
    ]
    return {
        "memoria": memoria,
        "processosPorMemoria": por_memoria,
        "processosPorCpu": por_cpu,
        "servicosAutomaticosParados": servicos,
        "itensInicializacao": inicializacao,
        "resumo": {
            "totalProcessos": len(procs),
            "servicosAutomaticosParados": len(servicos),
            "itensInicializacao": len(inicializacao),
            "memoriaPressaoAlta": memoria["pressaoAlta"],
        },
        "avisos": avisos,
    }


def conta_logon(valor: Any) -> str | None:
    """Conta de serviço do sistema fica; qualquer outra é de alguém e vira `<conta>`."""
    conta = texto(valor, 200)
    if conta is None or CONTAS_DE_SISTEMA.match(conta):
        return conta
    return "<conta>"


def apipa(status: str | None, enderecos: list[str]) -> bool:
    """Test-Apipa: 169.254.x.x só importa em adaptador conectado."""
    return status == "Up" and any(ip.startswith("169.254.") for ip in enderecos)


def rede(cru: dict[str, Any]) -> dict[str, Any]:
    """Coleta-Rede.ps1."""
    adaptadores = []
    for a in lista(cru.get("adaptadores"))[:MAX_ADAPTADORES]:
        status = texto(a.get("status"), 40)
        ipv4 = textos(a.get("enderecosIPv4"))
        adaptadores.append(
            {
                "nome": texto(a.get("nome"), 200),
                "descricao": texto(a.get("descricao"), 200),
                "status": status,
                "tipoConexao": texto(a.get("tipoConexao"), 60),
                "macAddress": texto(a.get("macAddress"), 40),
                "velocidadeMbps": texto(a.get("velocidadeMbps"), 40),
                "enderecosIPv4": ipv4,
                "gateway": texto(a.get("gateway"), 60),
                "servidoresDNS": textos(a.get("servidoresDNS")),
                "dhcp": texto(a.get("dhcp"), 20),
                "semIP": status == "Up" and not ipv4,
                "apipa": apipa(status, ipv4),
            }
        )
    testes = [
        {
            "tipo": texto(t.get("tipo"), 40),
            "alvo": texto(t.get("alvo"), 100),
            "sucesso": t.get("sucesso") is True,
            "latenciaMs": inteiro(t.get("latenciaMs")),
            "detalhe": texto(t.get("detalhe")),
        }
        for t in lista(cru.get("testes"))[:10]
    ]
    portas: list[dict[str, Any]] = []
    vistas: set[int | None] = set()
    # Uma linha por porta (a do pendrive saía ao acaso: Sort-Object -Unique do PS 5.1).
    brutas = sorted(
        lista(cru.get("portas")),
        key=lambda p: (inteiro(p.get("porta")) or 0, str(p.get("enderecoLocal"))),
    )
    for p in brutas:
        if inteiro(p.get("porta")) in vistas or len(portas) >= MAX_PORTAS:
            continue
        vistas.add(inteiro(p.get("porta")))
        local = texto(p.get("enderecoLocal"), 60)
        portas.append(
            {
                "protocolo": "TCP",
                "enderecoLocal": local,
                "porta": inteiro(p.get("porta")),
                "pid": inteiro(p.get("pid")),
                "processo": texto(p.get("processo"), 100) or "desconhecido",
                "escutaExterna": local not in ("127.0.0.1", "::1"),
            }
        )
    ativos = [a for a in adaptadores if a["status"] == "Up"]
    return {
        "adaptadores": adaptadores,
        "testesConectividade": testes,
        "portasEmEscuta": portas,
        "resumo": {
            "adaptadoresAtivos": len(ativos),
            "temIPValido": any(a["enderecosIPv4"] and not a["apipa"] for a in ativos),
            "internetOk": any(t["tipo"] == "ping" and t["sucesso"] for t in testes),
            "dnsOk": any(t["tipo"] == "resolucao-dns" and t["sucesso"] for t in testes),
            "portasEmEscutaTotal": len(portas),
        },
        "avisos": avisos_de(cru),
    }


def pares_da_base() -> list[str]:
    """Pares provedor|id da base da API (lista derivada; teste confere, ADR-015)."""
    dados = json.loads((RECURSOS / "eventlog-pares.json").read_text("utf-8"))
    return list(dados["pares"])


def eventlog(cru: dict[str, Any], pares: list[str], dias: int = DIAS_EVENTLOG) -> dict[str, Any]:
    """Coleta-EventLog.ps1, sem a classificação (feita na API pela base, TA-ADR-028).

    Mensagem só para pares fora da base, como no pendrive.
    """
    base = {p.lower() for p in pares}
    grupos: list[dict[str, Any]] = []
    for g in lista(cru.get("grupos")):
        provedor, ident = texto(g.get("provedor"), 200) or "", inteiro(g.get("id"))
        nivel = NIVEIS.get(inteiro(g.get("nivelMinimo")) or 0)
        if ident is None or nivel is None:
            continue
        conhecido = f"{provedor}|{ident}".lower() in base
        grupos.append(
            {
                "log": texto(g.get("log"), 40),
                "provedor": provedor,
                "id": ident,
                "nivel": nivel,
                "ocorrencias": inteiro(g.get("ocorrencias")) or 0,
                "primeiraOcorrencia": texto(g.get("primeiraOcorrencia"), 40),
                "ultimaOcorrencia": texto(g.get("ultimaOcorrencia"), 40),
                "exemploMensagem": None if conhecido else texto(g.get("mensagem"), 303),
            }
        )
    grupos.sort(key=lambda g: (ORDEM_NIVEL[g["nivel"]], -g["ocorrencias"]))
    grupos = grupos[:MAX_GRUPOS]
    return {
        "janelaDias": dias,
        "janelaInicio": texto(cru.get("janelaInicio"), 40),
        "logsAnalisados": ["System", "Application"],
        "niveisAnalisados": ["critico", "erro", "aviso"],
        "avisoSomenteBase": True,
        "totalOcorrencias": inteiro(cru.get("totalOcorrencias")) or 0,
        "totalGrupos": len(grupos),
        "gruposCriticos": sum(1 for g in grupos if g["nivel"] == "critico"),
        "grupos": grupos,
        "avisos": avisos_de(cru),
    }


def contadores_smart(registro: dict[str, Any], contadores: dict[str, Any]) -> None:
    """Set-ContadoresSmart: nulo nunca vira 0; temperatura 0 é driver sem suporte."""
    for campo in CONTADORES_SMART:
        registro[campo] = inteiro(contadores.get(campo))
    for campo in ("temperaturaC", "temperaturaMaximaC"):
        if not registro[campo]:
            registro[campo] = None
    ausentes = [c for c in CONTADORES_SMART if registro[c] is None]
    if not ausentes:
        registro["estadoSmart"] = "completo"
    elif len(ausentes) == len(CONTADORES_SMART):
        registro["estadoSmart"] = "indisponivel"
        registro["observacao"] = "O driver não informou nenhum contador SMART."
    else:
        registro["estadoSmart"] = "parcial"
        registro["observacao"] = "Contadores não expostos pelo driver: " + ", ".join(ausentes) + "."


def disco(cru: dict[str, Any], perfis: dict[str, Any], elevado: bool) -> dict[str, Any]:
    """Coleta-Disco.ps1 sem catálogo de limpeza nem tiers (Módulo 13)."""
    avisos = avisos_de(cru)
    volumes = []
    for v in lista(cru.get("volumes")):
        total, livre = numero(v.get("bytes")), numero(v.get("livres"))
        if not total or livre is None:
            continue
        percentual = round(livre / total * 100, 1)
        volumes.append(
            {
                "letra": texto(v.get("letra"), 2),
                "rotulo": texto(v.get("rotulo"), 100),
                "sistemaArquivos": texto(v.get("sistemaArquivos"), 20),
                "tipo": texto(v.get("tipo"), 20),
                "totalGB": round(total / 2**30, 2),
                "livreGB": round(livre / 2**30, 2),
                "percentualLivre": percentual,
                "critico": percentual < 10,
                "atencao": 10 <= percentual < 20,
            }
        )
    discos = []
    for d in lista(cru.get("discos")):
        registro: dict[str, Any] = {
            "numero": texto(d.get("numero"), 10),
            "modelo": texto(d.get("modelo"), 200),
            "tipoMidia": texto(d.get("tipoMidia"), 40),
            "barramento": texto(d.get("barramento"), 40),
            "tamanhoGB": round((numero(d.get("bytes")) or 0) / 2**30, 1),
            "saude": texto(d.get("saude"), 40),
            "estadoOperacional": texto(d.get("estadoOperacional"), 60),
            "estadoSmart": "indisponivel",
            **dict.fromkeys(CONTADORES_SMART),
            "observacao": None,
        }
        contadores = d.get("contadores")
        if isinstance(contadores, dict):
            contadores_smart(registro, contadores)
        elif not elevado:
            registro["observacao"] = "Contadores SMART exigem execução como administrador."
        elif d.get("erroContadores"):
            registro["observacao"] = "Contadores SMART não disponíveis neste disco: " + (
                texto(d.get("erroContadores"), 200) or ""
            )
        discos.append(registro)
    if not elevado:
        avisos.append(
            "Sem privilégio administrativo: SMART e perfis de outros usuários podem não ser lidos."
        )
    avisos.extend(perfis.get("avisos", []))
    return {
        "unidadeFerramenta": None,
        "volumes": volumes,
        "discosFisicos": discos,
        "maioresPastasPerfil": perfis.get("pastas", []),
        "maioresArquivos": perfis.get("arquivos", []),
        "resumo": {"limiarArquivoMB": ARQUIVO_MINIMO_MB, "limiarPastaMB": PASTA_MINIMA_MB},
        "avisos": avisos,
    }


def varrer_perfis(
    raiz: Path,
    cancelar: threading.Event | None = None,
    limite: float = TEMPO_VARREDURA,
) -> dict[str, Any]:
    r"""Maiores pastas de 2º nível e maiores arquivos de `C:\Users`, numa varredura só.

    Nunca segue link nem junction. Arquivo sai sem nome (pasta de 2º nível + extensão, ADR-015).
    O caminho da pasta ainda tem o nome do perfil: o saneamento troca por `%PERFIL%`.
    """
    fim = time.monotonic() + limite
    acumulado: dict[tuple[str, str], list[int]] = {}
    grandes: list[dict[str, Any]] = []
    avisos: list[str] = []
    try:
        perfis = [
            e
            for e in os.scandir(raiz)
            if e.is_dir(follow_symlinks=False)
            and not e.is_symlink()
            and not e.is_junction()
            and e.name.lower() not in PERFIS_IGNORADOS
        ]
    except OSError as erro:
        return {"pastas": [], "arquivos": [], "avisos": [f"Perfis não lidos: {erro.strerror}"]}
    limite_arquivo = ARQUIVO_MINIMO_MB * 2**20
    esgotou = False
    for perfil in perfis:
        pilha = [(Path(perfil.path), "")]
        while pilha:
            if cancelar is not None and cancelar.is_set():
                raise Cancelado
            if time.monotonic() > fim:
                esgotou = True
                pilha.clear()
                break
            pasta, segundo = pilha.pop()
            try:
                entradas = list(os.scandir(pasta))
            except OSError:
                continue  # sem acesso: sem admin, parte da árvore fica invisível (como no pendrive)
            for e in entradas:
                try:
                    if e.is_symlink() or e.is_junction():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        pilha.append((Path(e.path), segundo or e.name))
                    elif e.is_file(follow_symlinks=False) and segundo:
                        tamanho = e.stat(follow_symlinks=False).st_size
                        soma = acumulado.setdefault((perfil.name, segundo), [0, 0])
                        soma[0] += tamanho
                        soma[1] += 1
                        if tamanho >= limite_arquivo:
                            grandes.append(
                                {
                                    "pasta": str(Path(perfil.path) / segundo),
                                    "extensao": Path(e.name).suffix.lower()[:20],
                                    "bytes": tamanho,
                                    "ultimaModificacao": datetime.fromtimestamp(
                                        e.stat(follow_symlinks=False).st_mtime
                                    )
                                    .astimezone()
                                    .isoformat(),
                                }
                            )
                except OSError:
                    continue
        if esgotou:
            break
    if esgotou:
        avisos.append(f"Varredura dos perfis interrompida após {limite:.0f} s; resultado parcial.")
    pastas: list[dict[str, Any]] = [
        {"caminho": str(raiz / nome / segundo), "bytes": b, "arquivos": n}
        for (nome, segundo), (b, n) in acumulado.items()
        if b >= PASTA_MINIMA_MB * 2**20
    ]
    pastas.sort(key=lambda p: p["bytes"], reverse=True)
    grandes.sort(key=lambda a: a["bytes"], reverse=True)
    return {"pastas": pastas[:50], "arquivos": grandes[:MAX_ARQUIVOS], "avisos": avisos}


def relatorio_bateria(html: str) -> dict[str, Any]:
    """ConvertFrom-RelatorioBateria: números do HTML do powercfg."""
    corpo = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " "))

    def achar(padrao: str) -> int | None:
        m = re.search(padrao, corpo, re.IGNORECASE)
        return int(re.sub(r"[^\d]", "", m[1])) if m and re.sub(r"[^\d]", "", m[1]) else None

    projeto = achar(r"DESIGN\s+CAPACITY\s+([\d\.,]+)\s*mWh")
    atual = achar(r"FULL\s+CHARGE\s+CAPACITY\s+([\d\.,]+)\s*mWh")
    ciclos = achar(r"CYCLE\s+COUNT\s+([\d\.,]+)")
    desgaste = None
    if projeto and atual is not None:
        desgaste = max(round((projeto - atual) / projeto * 100, 1), 0)
    return {
        "capacidadeProjetoMWh": projeto,
        "capacidadeAtualMWh": atual,
        "ciclos": ciclos,
        "desgastePercentual": desgaste,
    }


def classificacao_desgaste(percentual: float | None) -> str:
    """Get-ClassificacaoDesgaste."""
    if percentual is None:
        return "desconhecido"
    if percentual < 20:
        return "saudavel"
    if percentual < 40:
        return "desgaste-moderado"
    if percentual < 60:
        return "desgaste-alto"
    return "substituicao-recomendada"


def bateria(cru: dict[str, Any], html: str | None, aviso_powercfg: str | None) -> dict[str, Any]:
    """Coleta-Bateria.ps1; o HTML já foi lido e apagado por quem chama."""
    avisos = avisos_de(cru)
    baterias = [
        {
            "nome": texto(b.get("nome"), 100),
            "fabricante": texto(b.get("fabricante"), 100),
            "cargaAtualPercentual": inteiro(b.get("cargaAtualPercentual")),
            "statusCodigo": inteiro(b.get("statusCodigo")),
            "emUsoDeBateria": b.get("emUsoDeBateria") is True,
        }
        for b in lista(cru.get("baterias"))[:4]
    ]
    extraido = relatorio_bateria(html) if html is not None else relatorio_bateria("")
    if aviso_powercfg:
        avisos.append(aviso_powercfg)
    if baterias and html is not None and extraido["capacidadeProjetoMWh"] is None:
        avisos.append("O relatório do powercfg foi gerado, mas as capacidades não foram extraídas.")
    return {
        "presente": bool(baterias),
        "baterias": baterias,
        "capacidadeProjetoMWh": extraido["capacidadeProjetoMWh"],
        "capacidadeAtualMWh": extraido["capacidadeAtualMWh"],
        "desgastePercentual": extraido["desgastePercentual"],
        "classificacaoDesgaste": classificacao_desgaste(extraido["desgastePercentual"]),
        "ciclosCarga": extraido["ciclos"],
        "relatorioGerado": html is not None,
        "avisos": avisos,
    }


def maquina(cru: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Get-ModeloNotebook; o usuário da sessão volta à parte, só para o saneamento."""
    dados = {
        "fabricante": texto(cru.get("fabricante"), 100),
        "modelo": texto(cru.get("modelo"), 100),
        "familia": texto(cru.get("familia"), 100),
        "numeroSerie": texto(cru.get("numeroSerie"), 100),
        "memoriaTotalGB": numero(cru.get("memoriaTotalGB")),
        "processador": texto(cru.get("processador"), 200),
        "sistema": texto(cru.get("sistema"), 200),
        "versaoSistema": texto(cru.get("versaoSistema"), 40),
        "erro": texto(cru.get("erro")),
    }
    return dados, texto(cru.get("usuarioSessao"), 200)


# ---------------------------------------------------------------- execução


def script(nome: str) -> str:
    return (RECURSOS / f"{nome}.ps1").read_text("utf-8")


def json_do_coletor(resultado: executor.Resultado) -> dict[str, Any]:
    if resultado.cancelado:
        raise Cancelado
    if resultado.esgotado:
        raise RuntimeError("tempo esgotado")
    if resultado.codigo != 0:
        raise RuntimeError(f"código {resultado.codigo}")
    try:
        valor = json.loads(resultado.saida.strip() or "null")
    except json.JSONDecodeError:
        raise RuntimeError("saída que não é JSON") from None
    if not isinstance(valor, dict):
        raise RuntimeError("saída que não é um objeto JSON")
    return valor


def hostname() -> str:
    """Nome NetBIOS da máquina, nunca digitado pelo técnico."""
    return socket.gethostname().split(".")[0].upper()


def nomes_de_perfil(raiz: Path) -> list[str]:
    try:
        nomes = [e.name for e in os.scandir(raiz) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    return [n for n in nomes if n.lower() not in PERFIS_IGNORADOS and not PERFIS_SISTEMA.match(n)]


def raiz_perfis() -> Path:
    return caminhos.pasta_do_sistema("ProfilesDirectory")


def coletar(
    *,
    elevado: bool,
    cancelar: threading.Event | None = None,
    ao_progresso: Callable[[str, Modulo | None], None] | None = None,
    rodar: Rodar = executor.powershell,
    executar: Rodar = executor.executar,
    perfis: Path | None = None,
    agora: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> Coleta:
    """Roda os cinco coletores em sequência. Cancelado: devolve o que já ficou pronto."""
    raiz = perfis or raiz_perfis()
    inicio = agora()
    maq_cru: dict[str, Any] = {}
    try:
        maq_cru = json_do_coletor(rodar(script("maquina"), timeout=60, cancelar=cancelar))
    except Cancelado:
        pass
    except RuntimeError as erro:
        maq_cru = {"erro": str(erro)}
    dados_maquina, usuario_sessao = maquina(maq_cru)
    coleta = Coleta(hostname(), inicio, elevado, dados_maquina)
    nomes = nomes_de_perfil(raiz)
    for conta in (usuario_sessao, os.environ.get("USERNAME")):
        if conta:
            nomes.append(conta.rsplit("\\", 1)[-1])
    coleta.nomes_pessoais = sorted({n for n in nomes if n}, key=str.lower)
    if not elevado:
        coleta.avisos.append("Coleta sem administrador: SMART e perfis de outros usuários faltam.")

    pares = pares_da_base()
    passos: dict[str, Callable[[], dict[str, Any]]] = {
        "processos": lambda: processos(
            json_do_coletor(
                rodar(script("processos"), timeout=TIMEOUTS["processos"], cancelar=cancelar)
            )
        ),
        "rede": lambda: rede(
            json_do_coletor(rodar(script("rede"), timeout=TIMEOUTS["rede"], cancelar=cancelar))
        ),
        "eventlog": lambda: eventlog(
            json_do_coletor(
                rodar(
                    script("eventlog"),
                    timeout=TIMEOUTS["eventlog"],
                    cancelar=cancelar,
                    dias=str(DIAS_EVENTLOG),
                    pares=json.dumps(pares),
                )
            ),
            pares,
        ),
        "disco": lambda: disco(
            json_do_coletor(rodar(script("disco"), timeout=TIMEOUTS["disco"], cancelar=cancelar)),
            varrer_perfis(raiz, cancelar),
            elevado,
        ),
        "bateria": lambda: _bateria(rodar, executar, cancelar),
    }
    try:
        for nome, passo in passos.items():
            if ao_progresso:
                ao_progresso(nome, None)
            t0, momento = time.monotonic(), agora()
            try:
                modulo = Modulo(nome, "ok", None, momento, 0.0, passo())
            except Cancelado:
                raise
            except Exception as erro:  # noqa: BLE001 — um coletor nunca derruba a coleta
                log.warning("Coletor %s falhou: %s", nome, type(erro).__name__)
                modulo = Modulo(nome, "erro", texto(str(erro), 200), momento, 0.0, {})
            modulo.duracao = round(time.monotonic() - t0, 1)
            coleta.modulos[nome] = modulo
            log.info("Coletor %s: %s em %.1f s", nome, modulo.status, modulo.duracao)
            if ao_progresso:
                ao_progresso(nome, modulo)
        coleta.encerrada_normalmente = True
    except Cancelado:
        log.warning("Coleta cancelada pelo técnico após %d módulo(s).", len(coleta.modulos))
        coleta.avisos.append("Coleta cancelada pelo técnico; módulos incompletos.")
    coleta.fim = agora()
    return coleta


def _bateria(rodar: Rodar, executar: Rodar, cancelar: threading.Event | None) -> dict[str, Any]:
    cru = json_do_coletor(rodar(script("bateria"), timeout=TIMEOUTS["bateria"], cancelar=cancelar))
    html: str | None = None
    aviso: str | None = None
    # O HTML tem dados da máquina: pasta temporária própria, apagada ao sair.
    with tempfile.TemporaryDirectory(prefix="itc-bateria-") as pasta:
        arquivo = Path(pasta) / "batteryreport.html"
        resultado = executar(
            [executor.sistema32("powercfg.exe"), "/batteryreport", "/output", str(arquivo)],
            timeout=TIMEOUTS["bateria"],
            cancelar=cancelar,
        )
        if resultado.cancelado:
            raise Cancelado
        if arquivo.exists():
            html = arquivo.read_text("utf-8", errors="replace")
        else:
            aviso = "powercfg não gerou o relatório de bateria."
    return bateria(cru, html, aviso)
