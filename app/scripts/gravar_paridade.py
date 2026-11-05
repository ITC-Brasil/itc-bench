r"""Grava saídas do Bench e do pendrive na mesma máquina e anonimiza (ADR-015, teste de paridade).

Uso, de dentro de `app/`, numa máquina de teste, elevado:

    uv run python scripts/gravar_paridade.py <pasta pendrive/ do TA> <pasta de saída> [módulos]
    uv run python scripts/gravar_paridade.py <pasta pendrive/ do TA> <pasta de saída> --de-cru

Grava cru em `<saída>/cru/` (NUNCA no repositório) e anonimizado em `<saída>/anonimo/`;
`--de-cru` só reprocessa o cru (na mesma máquina, que é de onde vêm os nomes a trocar). Só os
arquivos de `anonimo/` vão para `tests/gravacoes/`, depois de conferidos à mão e pelo
`test_gravacoes_anonimas` (com `ITC_BENCH_PROIBIDOS` apontando para a lista local).

Troca, sempre em palavra inteira e sem diferenciar maiúsculas: hostname, perfis e contas,
domínio, serial, SSIDs salvos. Troca também MAC, IPv4/IPv6 (APIPA por `169.254.0.x`), SID de
conta, hosts em UNC e URL, hexadecimal longo (hash de `EdgeAutoLaunch_*`), `DeviceID` da
bateria, rótulo de volume. Dentro do perfil fica só o 2º nível conhecido (`Desktop`, `OneDrive`,
`AppData`…); o resto vira `pasta-N`, e OneDrive com nome de conta vira `OneDrive-conta`.
Programas que não são do Windows nem dos agentes do Grupo viram `programa-N` (serviços, itens de
inicialização, processos com porta, provedores de evento, adaptadores de rede). Nada de
`pendrive/config/` é copiado (o catálogo de disco usado aqui é vazio).
"""

import dataclasses
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from itc_bench.servicos import coleta, executor

PENDRIVE = {
    "processos": ("Coleta-Processos.ps1", "Get-ColetaProcessos"),
    "rede": ("Coleta-Rede.ps1", "Get-ColetaRede"),
    "eventlog": (
        "Coleta-EventLog.ps1",
        "Get-ColetaEventLog -Dias 7 -CaminhoConhecidos $env:ITC_BASE",
    ),
    "bateria": ("Coleta-Bateria.ps1", "Get-ColetaBateria -PastaSessao $env:ITC_PASTA"),
    "disco": (
        "Coleta-Disco.ps1",
        "Get-ColetaDisco -CaminhoClassificacao $env:ITC_CATALOGO -Elevado $true"
        " -RaizFerramenta 'C:\\'",
    ),
}
CATALOGO_VAZIO = {
    "itens": [],
    "regrasPadrao": {"regras": [], "tierFallback": "revisar"},
    "tiers": {},
}
BASE = Path(__file__).parents[2] / "api" / "app" / "eventlog-conhecidos.json"
MAC_FICTICIO = "02-00-5E-10-00-"
SID_FICTICIO = "S-1-5-21-0-0-0-1001"
HASH_FICTICIO = "HASH"
# 2º nível do perfil que fica com o nome real (pasta padrão do Windows).
PASTAS_PADRAO = frozenset(
    {
        "3d objects",
        "appdata",
        "contacts",
        "desktop",
        "documents",
        "downloads",
        "favorites",
        "links",
        "music",
        "onedrive",
        "pictures",
        "saved games",
        "searches",
        "videos",
    }
)
# Agentes do Grupo e programas que vêm com o Windows (nome do item, serviço ou processo).
PROGRAMAS_MANTIDOS = re.compile(
    r"(?i)^(glpi|rustdesk|anydesk|itc|microsoftedge|onedrive|securityhealth|msmpeng|system|idle)"
)
ADAPTADORES_PADRAO = re.compile(
    r"(?i)^(ethernet|wi-?fi|conex|local area|bluetooth|vethernet|loopback)"
)
EVENTOS_DO_WINDOWS = frozenset(
    {
        "acpi",
        "application error",
        "application hang",
        "disk",
        "eventlog",
        "ntfs",
        "service control manager",
        "volmgr",
        "volsnap",
        "vss",
    }
)
SISTEMA = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))


def rodar_pendrive(pendrive: Path, nome: str, pasta: Path) -> Any:
    arquivo, chamada = PENDRIVE[nome]
    # Só para esta gravação: Invoke-Expression evita depender da política de execução.
    script = (
        "Invoke-Expression ([IO.File]::ReadAllText($env:ITC_ARQUIVO)); "
        f"{chamada} | ConvertTo-Json -Depth 10 -Compress"
    )
    catalogo = pasta / "catalogo-vazio.json"
    catalogo.write_text(json.dumps(CATALOGO_VAZIO), "utf-8")
    r = executor.powershell(
        script,
        timeout=3600,
        arquivo=str(pendrive / "modulos" / arquivo),
        base=str(BASE),
        pasta=str(pasta),
        catalogo=str(catalogo),
    )
    # Get-ColetaDisco escreve progresso com Write-Host antes do JSON: vale a última linha.
    ultima = r.saida.strip().splitlines()[-1] if r.saida.strip() else ""
    return coleta.json_do_coletor(dataclasses.replace(r, saida=ultima))


def rodar_bench(nome: str) -> dict[str, Any]:
    variaveis = {}
    if nome == "eventlog":
        variaveis = {"dias": "7", "pares": json.dumps(coleta.pares_da_base())}
    r = executor.powershell(coleta.script(nome), timeout=300, **variaveis)
    return coleta.json_do_coletor(r)


def info_da_maquina() -> dict[str, Any]:
    return coleta.json_do_coletor(
        executor.powershell(
            "$c = Get-CimInstance Win32_ComputerSystem; $b = Get-CimInstance Win32_BIOS;"
            " [ordered]@{ dominio = $c.Domain; usuario = $c.UserName; serial = $b.SerialNumber;"
            " ssids = @(netsh.exe wlan show profiles | Select-String ':\\s*(.+)$' |"
            " ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() });"
            " servicosDoWindows = @(Get-CimInstance Win32_Service | Where-Object {"
            " $_.PathName -match '^\"?[A-Za-z]:\\\\Windows\\\\' } | ForEach-Object Name) }"
            " | ConvertTo-Json -Compress"
        )
    )


def identificadores(info: dict[str, Any]) -> dict[str, str]:
    """Valores reais desta máquina e o substituto de cada um."""
    mapa: dict[str, str] = {socket.gethostname().split(".")[0]: "TESTE-NB-01"}
    for i, nome in enumerate(coleta.nomes_de_perfil(coleta.raiz_perfis())):
        mapa[nome] = f"usuario-{chr(97 + i)}"
    for variavel, troca in (
        ("USERNAME", "conta-teste"),
        ("USERDOMAIN", "DOMINIO-TESTE"),
        ("USERDNSDOMAIN", "exemplo.invalid"),
    ):
        if os.environ.get(variavel):
            mapa.setdefault(os.environ[variavel], troca)
    if info.get("dominio") and "." in str(info["dominio"]):
        mapa[str(info["dominio"])] = "exemplo.invalid"
    if info.get("usuario"):
        mapa.setdefault(str(info["usuario"]).rsplit("\\", 1)[-1], "usuario-sessao")
    if info.get("serial"):
        mapa[str(info["serial"])] = "SERIAL-TESTE"
    for i, ssid in enumerate(info.get("ssids") or []):
        if ssid:
            mapa[str(ssid)] = f"SSID-TESTE-{i}"
    return mapa


class Anonimizador:
    IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?:%\d+)?\b")
    MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}\b")
    SID = re.compile(r"S-1-5-21(?:-\d+){3,4}")
    HEX = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{16,}(?![0-9A-Fa-f])")
    UNC = re.compile(r"\\\\[^\\\s\"]+\\")
    URL = re.compile(r"https?://[^\s\"']+")
    PERFIL = re.compile(r"(?i)\b([a-z]:\\users\\[^\\]+)((?:\\[^\\]+)+)")
    MANTER_IP: ClassVar = frozenset(
        {"127.0.0.1", "0.0.0.0", "8.8.8.8", "1.1.1.1", "255.255.255.255"}  # noqa: S104
    )

    def __init__(self, mapa: dict[str, str]) -> None:
        self.mapa = {k.lower(): v for k, v in mapa.items()}
        self.ips: dict[str, str] = {}
        self.macs: dict[str, str] = {}
        self.pastas: dict[str, str] = {}
        chaves = sorted(mapa, key=len, reverse=True)
        self.nomes = (
            re.compile(
                r"(?<!\w)(" + "|".join(re.escape(k) for k in chaves) + r")(?!\w)", re.IGNORECASE
            )
            if mapa
            else None
        )

    def ip(self, m: re.Match[str]) -> str:
        valor = m[0]
        try:
            ip = ipaddress.ip_address(valor.split("%")[0])
        except ValueError:
            return valor
        if valor in self.MANTER_IP or ip.is_loopback:
            return valor
        if valor not in self.ips:
            n = len(self.ips) + 1
            if ip.version == 4:
                self.ips[valor] = f"169.254.0.{n}" if ip.is_link_local else f"192.0.2.{n}"
            else:
                self.ips[valor] = f"2001:db8::{n:x}"
        return self.ips[valor]

    def mac(self, m: re.Match[str]) -> str:
        return self.macs.setdefault(m[0].upper(), MAC_FICTICIO + f"{len(self.macs) + 1:02X}")

    def pasta(self, nome: str) -> str:
        return self.pastas.setdefault(nome.lower(), f"pasta-{len(self.pastas) + 1}")

    def perfil(self, m: re.Match[str]) -> str:
        segundo, *resto = m[2].split("\\")[1:]
        if segundo.lower() in PASTAS_PADRAO:
            pass
        elif segundo.lower().startswith("onedrive"):
            segundo = "OneDrive-conta"
        else:
            segundo = self.pasta(segundo)
        return "\\".join([m[1], segundo, *(self.pasta(p) for p in resto)])

    def texto(self, s: str) -> str:
        if self.nomes:
            s = self.nomes.sub(lambda m: self.mapa[m[0].lower()], s)
        s = self.PERFIL.sub(self.perfil, s)
        s = self.SID.sub(SID_FICTICIO, s)
        s = self.MAC.sub(self.mac, s)
        s = self.IPV6.sub(self.ip, s)
        s = self.IPV4.sub(self.ip, s)
        s = self.HEX.sub(HASH_FICTICIO, s)
        s = self.UNC.sub(r"\\\\servidor.exemplo.invalid\\", s)
        return self.URL.sub("https://exemplo.invalid/", s)

    def __call__(self, valor: Any, chave: str = "") -> Any:
        if isinstance(valor, dict):
            if "caminho" in valor and "extensao" in valor:  # arquivo grande do pendrive: só a pasta
                valor = {**valor, "caminho": str(Path(valor["caminho"]).parent)}
            return {k: self(v, k) for k, v in valor.items()}
        if isinstance(valor, list):
            return [self(v, chave) for v in valor]
        if isinstance(valor, str):
            if chave == "fabricante":  # DeviceID da bateria pode ter número de série
                return "BATERIA-TESTE"
            return self.texto(valor)
        return valor


class Programas:
    """Troca nome de programa de terceiros por `programa-N`, igual no Bench e no pendrive."""

    def __init__(self, servicos_do_windows: list[str]) -> None:
        self.windows = {s.lower() for s in servicos_do_windows}
        self.nomes: dict[str, str] = {}

    def trocar(self, nome: str) -> str:
        return self.nomes.setdefault(nome.lower(), f"programa-{len(self.nomes) + 1}")

    def servico(self, item: dict[str, Any]) -> None:
        base = re.sub(r"_[0-9a-fA-F]+$", "", item["nome"]).lower()
        if base in self.windows or item["nome"].lower() in self.windows:
            return
        if not PROGRAMAS_MANTIDOS.match(item["nome"]):
            item["nomeExibicao"] = item["nome"] = self.trocar(item["nome"])

    def inicializacao(self, item: dict[str, Any]) -> None:
        comando = str(item.get("comando") or "").strip('"').lower()
        if comando.startswith(str(SISTEMA).lower()) or PROGRAMAS_MANTIDOS.match(item["nome"]):
            return
        item["nome"] = self.trocar(item["nome"])

    def processo(self, nome: str) -> str:
        if not nome or PROGRAMAS_MANTIDOS.match(nome):
            return nome
        if (SISTEMA / "System32" / f"{nome}.exe").exists() or (SISTEMA / f"{nome}.exe").exists():
            return nome
        return self.trocar(nome)

    def provedor(self, nome: str, conhecidos: set[str]) -> str:
        n = nome.lower()
        if n.startswith("microsoft-windows-") or n in EVENTOS_DO_WINDOWS or n in conhecidos:
            return nome
        return self.trocar(nome)


def reduzir(
    nome: str, dados: dict[str, Any], programas: Programas, adaptadores: dict[str, str]
) -> dict[str, Any]:
    """Só o que a paridade compara: sem inventário de programas e sem comandos da máquina."""
    if nome == "processos":
        bench, pendrive = dados["bench"], dados["pendrive"]
        bench["processos"] = []
        pendrive["processosPorMemoria"] = pendrive["processosPorCpu"] = []
        for lista in (bench["inicializacao"], pendrive["itensInicializacao"]):
            for item in lista:
                programas.inicializacao(item)
                item["comando"] = "<comando>"
                item.pop("usuario", None)
        for item in pendrive["servicosAutomaticosParados"] + bench["servicos"]:
            programas.servico(item)
            item["contaLogon"] = coleta.conta_logon(item.get("contaLogon"))
    if nome == "eventlog":
        conhecidos = {p.split("|")[0].lower() for p in coleta.pares_da_base()}
        for grupo in dados["bench"]["grupos"] + dados["pendrive"]["grupos"]:
            grupo["provedor"] = programas.provedor(grupo["provedor"], conhecidos)
        for grupo in dados["bench"]["grupos"]:
            grupo["mensagem"] = "<mensagem>" if grupo.get("mensagem") else None
        for grupo in dados["pendrive"]["grupos"]:
            if grupo.get("exemploMensagem"):
                grupo["exemploMensagem"] = "<mensagem>"
    if nome == "rede":
        for porta in dados["bench"]["portas"] + dados["pendrive"]["portasEmEscuta"]:
            porta["pid"] = 0
            porta["processo"] = programas.processo(porta.get("processo") or "")
        for adaptador in dados["bench"]["adaptadores"] + dados["pendrive"]["adaptadores"]:
            if not ADAPTADORES_PADRAO.match(adaptador["nome"]):
                troca = adaptadores.setdefault(
                    adaptador["nome"], f"adaptador-{len(adaptadores) + 1}"
                )
                adaptador["nome"] = adaptador["descricao"] = troca
    if nome == "disco":
        rotulos: dict[str, str] = {}
        for volume in dados["bench"]["volumes"] + dados["pendrive"]["volumes"]:
            if volume.get("rotulo"):
                volume["rotulo"] = rotulos.setdefault(
                    volume["rotulo"], f"rotulo-{len(rotulos) + 1}"
                )
    return dados


def main() -> None:
    pendrive, saida = Path(sys.argv[1]), Path(sys.argv[2])
    de_cru = "--de-cru" in sys.argv
    cru, anonimo = saida / "cru", saida / "anonimo"
    cru.mkdir(parents=True, exist_ok=True)
    anonimo.mkdir(parents=True, exist_ok=True)
    info = info_da_maquina()
    anonimizar = Anonimizador(identificadores(info))
    programas = Programas(info.get("servicosDoWindows") or [])
    adaptadores: dict[str, str] = {}

    def gravar(nome: str, dados: dict[str, Any]) -> None:
        dados = anonimizar(reduzir(nome, dados, programas, adaptadores))
        (anonimo / f"{nome}.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=1) + "\n", "utf-8"
        )

    if de_cru:
        for nome in [n for n in PENDRIVE if (cru / f"{n}.json").exists()]:
            gravar(nome, json.loads((cru / f"{nome}.json").read_text("utf-8")))
            print(f"{nome}: reprocessado")
        return
    so = [n for n in sys.argv[3:] if n in PENDRIVE] or list(PENDRIVE)
    with tempfile.TemporaryDirectory() as pasta:
        for nome in so:
            dados = {
                "bench": rodar_bench(nome),
                "pendrive": rodar_pendrive(pendrive, nome, Path(pasta)),
            }
            if nome == "disco":
                dados["varredura"] = coleta.varrer_perfis(coleta.raiz_perfis())
            (cru / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
            gravar(nome, dados)
            print(f"{nome}: gravado")


if __name__ == "__main__":
    main()
