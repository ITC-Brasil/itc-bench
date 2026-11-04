r"""Grava saídas do Bench e do pendrive na mesma máquina e anonimiza (ADR-015, teste de paridade).

Uso, de dentro de `app/`, numa máquina de teste, elevado:

    uv run python scripts/gravar_paridade.py <pasta pendrive/ do TA> <pasta de saída>

Grava cru em `<saída>/cru/` (NUNCA no repositório) e anonimizado em `<saída>/anonimo/`. Só os
arquivos de `anonimo/` vão para `tests/gravacoes/`, depois de conferidos à mão e pelo
`test_gravacoes_anonimas`. Troca: hostname, nomes de perfil e conta, domínio, serial, MAC, IPv4
e IPv6, SSIDs salvos, hosts em UNC e URL, `DeviceID` da bateria, nomes de arquivo; nada de
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


def identificadores() -> dict[str, str]:
    """Valores reais desta máquina e o substituto de cada um (mais longo primeiro)."""
    mapa: dict[str, str] = {socket.gethostname().split(".")[0]: "TESTE-NB-01"}
    for i, nome in enumerate(coleta.nomes_de_perfil(coleta.raiz_perfis())):
        mapa[nome] = f"usuario-{chr(97 + i)}"
    for variavel, troca in (
        ("USERNAME", "conta-teste"),
        ("USERDOMAIN", "DOMINIO-TESTE"),
        ("USERDNSDOMAIN", "exemplo.invalid"),
    ):
        if os.environ.get(variavel):
            mapa[os.environ[variavel]] = troca
    info = coleta.json_do_coletor(
        executor.powershell(
            "$c = Get-CimInstance Win32_ComputerSystem; $b = Get-CimInstance Win32_BIOS;"
            " [ordered]@{ dominio = $c.Domain; usuario = $c.UserName; serial = $b.SerialNumber;"
            " ssids = @(netsh.exe wlan show profiles | Select-String ':\\s*(.+)$' |"
            " ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() }) } | ConvertTo-Json -Compress"
        )
    )
    if info.get("dominio") and "." in str(info["dominio"]):
        mapa[str(info["dominio"])] = "exemplo.invalid"
    if info.get("usuario"):
        mapa[str(info["usuario"]).rsplit("\\", 1)[-1]] = "usuario-sessao"
    if info.get("serial"):
        mapa[str(info["serial"])] = "SERIAL-TESTE"
    for i, ssid in enumerate(info.get("ssids") or []):
        if ssid:
            mapa[str(ssid)] = f"SSID-TESTE-{i}"
    return dict(sorted(mapa.items(), key=lambda kv: len(kv[0]), reverse=True))


class Anonimizador:
    IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?:%\d+)?\b")
    MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}\b")
    UNC = re.compile(r"\\\\[^\\\s\"]+\\")
    URL = re.compile(r"https?://[^\s\"']+")
    MANTER_IP: ClassVar = frozenset(
        {"127.0.0.1", "0.0.0.0", "8.8.8.8", "1.1.1.1", "255.255.255.255"}  # noqa: S104
    )

    def __init__(self, mapa: dict[str, str]) -> None:
        self.mapa, self.ips, self.macs = mapa, {}, {}
        self.nomes = (
            re.compile("|".join(re.escape(k) for k in mapa), re.IGNORECASE) if mapa else None
        )

    def ip(self, m: re.Match[str]) -> str:
        valor = m[0]
        try:
            ip = ipaddress.ip_address(valor.split("%")[0])
        except ValueError:
            return valor
        if valor in self.MANTER_IP or ip.is_loopback or (ip.is_link_local and ip.version == 4):
            return valor
        if valor not in self.ips:
            n = len(self.ips) + 1
            self.ips[valor] = f"192.0.2.{n}" if ip.version == 4 else f"2001:db8::{n:x}"
        return self.ips[valor]

    def mac(self, m: re.Match[str]) -> str:
        return self.macs.setdefault(m[0], MAC_FICTICIO + f"{len(self.macs) + 1:02X}")

    def texto(self, s: str) -> str:
        if self.nomes:
            minusculo = {k.lower(): v for k, v in self.mapa.items()}
            s = self.nomes.sub(lambda m: minusculo[m[0].lower()], s)
        s = self.MAC.sub(self.mac, s)
        s = self.IPV6.sub(self.ip, s)
        s = self.IPV4.sub(self.ip, s)
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


def reduzir(nome: str, dados: dict[str, Any]) -> dict[str, Any]:
    """Só o que a paridade compara: nada de inventário de programas da máquina de teste."""
    if nome == "processos":
        bench, pendrive = dados["bench"], dados["pendrive"]
        bench["processos"] = []
        pendrive["processosPorMemoria"] = pendrive["processosPorCpu"] = []
        for lista in (bench["inicializacao"], pendrive["itensInicializacao"]):
            for item in lista:
                item["comando"] = "<comando>"
                item.pop("usuario", None)
        for item in pendrive["servicosAutomaticosParados"]:
            item["contaLogon"] = coleta.conta_logon(item.get("contaLogon"))
        for item in bench["servicos"]:
            item["contaLogon"] = coleta.conta_logon(item.get("contaLogon"))
    if nome == "eventlog":
        for grupo in dados["bench"]["grupos"]:
            grupo["mensagem"] = "<mensagem>" if grupo.get("mensagem") else None
        for grupo in dados["pendrive"]["grupos"]:
            if grupo.get("exemploMensagem"):
                grupo["exemploMensagem"] = "<mensagem>"
    if nome == "rede":
        for porta in dados["bench"]["portas"] + dados["pendrive"]["portasEmEscuta"]:
            porta["pid"] = 0
    return dados


def main() -> None:
    pendrive, saida = Path(sys.argv[1]), Path(sys.argv[2])
    de_cru = "--de-cru" in sys.argv
    cru, anonimo = saida / "cru", saida / "anonimo"
    cru.mkdir(parents=True, exist_ok=True)
    anonimo.mkdir(parents=True, exist_ok=True)
    anonimizar = Anonimizador(identificadores())
    if de_cru:
        for nome in [n for n in PENDRIVE if (cru / f"{n}.json").exists()]:
            dados = reduzir(nome, json.loads((cru / f"{nome}.json").read_text("utf-8")))
            (anonimo / f"{nome}.json").write_text(
                json.dumps(anonimizar(dados), ensure_ascii=False, indent=1) + "\n", "utf-8"
            )
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
            (anonimo / f"{nome}.json").write_text(
                json.dumps(anonimizar(reduzir(nome, dados)), ensure_ascii=False, indent=1) + "\n",
                "utf-8",
            )
            print(f"{nome}: gravado")


if __name__ == "__main__":
    main()
