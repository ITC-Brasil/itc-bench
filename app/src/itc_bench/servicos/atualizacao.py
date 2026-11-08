r"""Atualização automática do Bench (ADR-026), sem Qt.

A API anuncia a versão com um manifesto assinado pelo responsável (ECDSA P-256, chaves públicas
no pacote: principal e reserva). Nada do manifesto é lido antes de a assinatura conferir. O
instalador é baixado do caminho fixo da API para `protegido\atualizacao\setup-<sha256>.exe`
(só SYSTEM e Administradores), com retomada por `Range` e teto no tamanho assinado. Ao fechar,
com o técnico tendo confirmado, `executor.disparar` roda o instalador, que espera o Bench sair
(`/ESPERAPID`). Recusa versão menor ou igual à em execução e à `DisplayVersion` do HKLM.
"""

import base64
import hashlib
import json
import re
import threading
import urllib.error
import urllib.request
import winreg
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import IO

from itc_bench import __version__
from itc_bench.nucleo import acl, assinatura, caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos import api, executor, retomada
from itc_bench.servicos.executor import Sensivel

PRODUTO = "itc-bench"
APP_ID = "{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}"
CHAVE_DESINSTALAR = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
CAMPOS = {"produto", "app_id", "versao", "minima", "sha256", "tamanho", "notas", "publicado_em"}
SEMVER = re.compile(r"(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})\.(0|[1-9]\d{0,2})")
SHA256 = re.compile(r"[0-9a-f]{64}")
TETO = 300 * 1024 * 1024
NOTAS_MAX = 500
BLOCO = 1024 * 1024
TIMEOUT = 30
TENTATIVAS = 3
MANIFESTO, ASSINATURA, TENTADAS = "manifesto.json", "manifesto.sig", "tentativas.txt"
# Sessão falsa do `--teste-atualizacao` (CI): a API real responde 401 a ela.
# Montada em tempo de execução: constante dobrada pareceria um token na varredura do pacote.
SESSAO_TESTE = "_".join(("itcbs", "t" * 43))

Progresso = Callable[[int, int], None]


class Recusada(Exception):
    """Mensagem para a tela; o log recebe o mesmo motivo, sem endereço nem token."""


@dataclass(frozen=True)
class Manifesto:
    versao: str
    minima: str
    sha256: str
    tamanho: int
    notas: str


@dataclass(frozen=True)
class Oferta:
    manifesto: Manifesto
    cru: bytes
    assinatura: bytes

    @property
    def obrigatoria(self) -> bool:
        return tupla(self.manifesto.minima) > tupla(__version__)


def pasta() -> Path:
    return caminhos.protegida() / "atualizacao"


def tupla(versao: str) -> tuple[int, int, int]:
    achado = SEMVER.fullmatch(versao)
    if not achado:
        raise Recusada(f"Versão fora do formato X.Y.Z: {versao[:20]!r}.")
    a, b, c = (int(p) for p in achado.groups())
    return a, b, c


def chaves() -> list[bytes]:
    """Principal e reserva do pacote; ausente ou inválida fica de fora (com log)."""
    encontradas = []
    raiz = resources.files("itc_bench.recursos") / "atualizacao"
    for nome in ("principal.pub", "reserva.pub"):
        try:
            encontradas.append(assinatura.chave_de_texto((raiz / nome).read_text("ascii")))
        except FileNotFoundError:
            log.warning("Atualização: chave pública %s ausente no pacote.", nome)
        except (OSError, UnicodeDecodeError, assinatura.ChaveInvalida) as erro:
            log.error("Atualização: chave pública %s inválida (%s).", nome, erro)
    return encontradas


def conferir(cru: bytes, sig: bytes, publicas: list[bytes]) -> Manifesto:
    """Assinatura primeiro, sobre os bytes exatos; só então o JSON é lido."""
    if not publicas:
        raise Recusada("O pacote não tem chave pública da atualização.")
    if not any(assinatura.verificar(chave, cru, sig) for chave in publicas):
        raise Recusada("A assinatura do manifesto não confere.")
    try:
        dados = json.loads(cru.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise Recusada("Manifesto assinado ilegível.") from erro
    if not isinstance(dados, dict) or set(dados) != CAMPOS:
        raise Recusada("Manifesto com campos inesperados.")
    if dados["produto"] != PRODUTO or dados["app_id"] != APP_ID:
        raise Recusada("Manifesto de outro produto.")
    texto = ("versao", "minima", "sha256", "notas", "publicado_em")
    if not all(isinstance(dados[c], str) for c in texto):
        raise Recusada("Manifesto com campo de tipo errado.")
    tamanho = dados["tamanho"]
    if not isinstance(tamanho, int) or isinstance(tamanho, bool) or not 0 < tamanho <= TETO:
        raise Recusada("Tamanho do instalador fora de 1 byte a 300 MB.")
    if tupla(dados["minima"]) > tupla(dados["versao"]):
        raise Recusada("Versão mínima acima da versão.")
    if not SHA256.fullmatch(dados["sha256"]):
        raise Recusada("SHA-256 do manifesto inválido.")
    notas = dados["notas"]
    if len(notas) > NOTAS_MAX or any(ord(c) < 32 and c != "\n" for c in notas):
        raise Recusada("Notas do manifesto fora do formato.")
    return Manifesto(dados["versao"], dados["minima"], dados["sha256"], tamanho, notas)


def versao_instalada() -> str | None:
    """`DisplayVersion` da chave de desinstalação do `AppId` (vista 64 bits), ou None."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            CHAVE_DESINSTALAR,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as chave:
            valor, tipo = winreg.QueryValueEx(chave, "DisplayVersion")
    except OSError:
        return None
    return valor if tipo == winreg.REG_SZ and isinstance(valor, str) else None


def referencia(instalada: str | None = None) -> tuple[int, int, int]:
    """Maior entre a versão em execução e a instalada; divergência vai para o log."""
    atual = tupla(__version__)
    instalada = versao_instalada() if instalada is None else instalada
    if instalada is None:
        return atual
    try:
        outra = tupla(instalada)
    except Recusada:
        log.warning("Atualização: DisplayVersion ilegível; vale a versão em execução.")
        return atual
    if outra != atual:
        log.warning("Atualização: em execução %s, instalada %s.", __version__, instalada)
    return max(atual, outra)


def _oferta(cru: bytes, sig: bytes, publicas: list[bytes], instalada: str | None) -> Oferta:
    manifesto = conferir(cru, sig, publicas)
    if tupla(manifesto.versao) <= referencia(instalada):
        raise Recusada(f"Versão {manifesto.versao} não é maior que a instalada.")
    return Oferta(manifesto, cru, sig)


def consultar(
    base: str,
    token: Sensivel,
    publicas: list[bytes] | None = None,
    instalada: str | None = None,
) -> Oferta | None:
    """None sem versão publicada (204); `Recusada` se o anúncio não servir."""
    status, _, corpo = api._chamar(base, "GET", "/v1/bench/versao", sessao=token)
    if status == 204 or corpo is None:
        return None
    if status == 401:
        raise api.Recusado(401, "sessao_invalida")
    if status != 200:
        raise api.ErroApi(f"Resposta inesperada do servidor ({status}).")
    try:
        cru = base64.b64decode(corpo["manifesto"], validate=True)
        sig = base64.b64decode(corpo["assinatura"], validate=True)
    except (KeyError, TypeError, ValueError) as erro:
        raise Recusada("Anúncio de versão sem manifesto assinado.") from erro
    oferta = _oferta(cru, sig, chaves() if publicas is None else publicas, instalada)
    log.info(
        "Atualização: versão %s anunciada (%s…, %d bytes, mínima %s).",
        oferta.manifesto.versao,
        oferta.manifesto.sha256[:12],
        oferta.manifesto.tamanho,
        oferta.manifesto.minima,
    )
    return oferta


def instalador(oferta: Oferta, destino: Path | None = None) -> Path:
    return (destino or pasta()) / f"setup-{oferta.manifesto.sha256}.exe"


def _preparar_pasta(destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    acl.verificar_reparse(destino)  # pasta e tudo dentro; os pais saem da conferência do início


def _abrir(base: str, token: Sensivel, sha: str, inicio: int) -> IO[bytes]:
    cabecalhos = {"User-Agent": "itc-bench", "Authorization": f"Bearer {token.revelar()}"}
    if inicio:
        cabecalhos["Range"] = f"bytes={inicio}-"
    # Mesmo endereço validado da API (https://), mesmo abridor sem redirecionamento.
    requisicao = urllib.request.Request(  # noqa: S310
        f"{base}/v1/bench/versao/arquivo?sha256={sha}", headers=cabecalhos
    )
    resposta: IO[bytes] = api._abridor.open(requisicao, timeout=TIMEOUT)
    return resposta


def baixar(
    base: str,
    token: Sensivel,
    oferta: Oferta,
    destino: Path | None = None,
    cancelar: threading.Event | None = None,
    progresso: Progresso | None = None,
    abrir: Callable[[str, Sensivel, str, int], IO[bytes]] = _abrir,
) -> Path:
    """Instalador conferido em `protegido\\atualizacao`, com o manifesto ao lado."""
    destino = destino or pasta()
    _preparar_pasta(destino)
    final = instalador(oferta, destino)
    esperado, tamanho = oferta.manifesto.sha256, oferta.manifesto.tamanho
    if not (final.is_file() and _hash(final) == esperado):
        parcial = final.with_name(final.name + ".parcial")
        inicio = parcial.stat().st_size if parcial.is_file() else 0
        if inicio >= tamanho:
            parcial.unlink()
            inicio = 0
        try:
            resposta = abrir(base, token, esperado, inicio)
        except urllib.error.HTTPError as erro:
            log.warning("Atualização: download recusado (%s).", erro.code)
            if erro.code == 401:
                raise api.Recusado(401, "sessao_invalida") from None
            raise Recusada(f"O servidor recusou o download ({erro.code}).") from None
        except OSError as erro:
            log.warning("Atualização: download falhou (%s).", type(erro).__name__)
            raise Recusada("Sem conexão para baixar a atualização.") from None
        with resposta:
            status = getattr(resposta, "status", 200)
            if inicio and status != 206:
                inicio = 0  # servidor mandou o arquivo inteiro: recomeça
            lidos = inicio
            try:
                with parcial.open("ab" if inicio else "wb") as saida:
                    while bloco := resposta.read(BLOCO):
                        if cancelar is not None and cancelar.is_set():
                            raise Recusada("Download cancelado.")
                        lidos += len(bloco)
                        if lidos > tamanho:
                            raise Recusada("O instalador passou do tamanho assinado.")
                        saida.write(bloco)
                        if progresso is not None:
                            progresso(lidos, tamanho)
            except OSError as erro:
                log.warning("Atualização: download interrompido (%s).", type(erro).__name__)
                raise Recusada("O download foi interrompido; continua na próxima vez.") from None
        if lidos != tamanho:
            raise Recusada("Download incompleto; continua na próxima vez.")
        obtido = _hash(parcial)
        if obtido != esperado:
            parcial.unlink()
            log.error(
                "Atualização: SHA-256 diferente (%s…, obtido %s…).", esperado[:12], obtido[:12]
            )
            raise Recusada("O instalador baixado não confere com o manifesto assinado.")
        parcial.replace(final)
    (destino / MANIFESTO).write_bytes(oferta.cru)
    (destino / ASSINATURA).write_bytes(oferta.assinatura)
    log.info("Atualização: %s baixada e conferida (%s…).", oferta.manifesto.versao, esperado[:12])
    return final


def _hash(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


def guardada(
    destino: Path | None = None,
    publicas: list[bytes] | None = None,
    instalada: str | None = None,
) -> Oferta | None:
    """Oferta já baixada (vale offline: a assinatura não depende de rede), ou None."""
    destino = destino or pasta()
    try:
        cru = (destino / MANIFESTO).read_bytes()
        sig = (destino / ASSINATURA).read_bytes()
        oferta = _oferta(cru, sig, chaves() if publicas is None else publicas, instalada)
    except FileNotFoundError:
        return None
    except (OSError, Recusada) as erro:
        log.info("Atualização: guardada descartada (%s).", erro)
        return None
    arquivo = instalador(oferta, destino)
    if not arquivo.is_file() or _hash(arquivo) != oferta.manifesto.sha256:
        return None
    return oferta


def limpar(destino: Path | None = None, manter: Oferta | None = None) -> None:
    """Tira o que não é da oferta atual; o log do Inno fica para diagnóstico."""
    destino = destino or pasta()
    if not destino.is_dir():
        return
    acl.verificar_reparse(destino)
    manter_nomes = {MANIFESTO, ASSINATURA, TENTADAS} if manter else set()
    if manter is not None:
        alvo = instalador(manter, destino).name
        manter_nomes |= {alvo, alvo + ".parcial"}
    for item in destino.iterdir():
        if item.name in manter_nomes or item.name.startswith("inno-"):
            continue
        item.unlink()
        log.info("Atualização: removido %s.", item.name)


def tentativas(destino: Path | None = None) -> int:
    try:
        return int(((destino or pasta()) / TENTADAS).read_text("ascii").strip() or "0")
    except (OSError, ValueError):
        return 0


def motivo_para_nao_instalar(preparando: bool) -> str | None:
    """Preparação em andamento ou retomada pendente bloqueiam (ADR-023)."""
    if preparando:
        return "Há uma Preparação em andamento."
    if retomada.ler() is not None:
        return "Há uma Preparação com retomada pendente."
    return None


def argumentos(caminho: Path, versao: str, pid: int) -> list[str]:
    log_inno = caminho.parent / f"inno-{versao}.log"
    # Sem /APIURL: a atualização mantém o endereço gravado no HKLM.
    return [
        str(caminho),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/LOG={log_inno}",
        f"/ESPERAPID={pid}",
    ]


def instalar_ao_fechar(
    oferta: Oferta,
    pid: int,
    preparando: bool,
    destino: Path | None = None,
    soltar_mutex: Callable[[], None] | None = None,
    disparar: Callable[..., int] = executor.disparar,
) -> int | None:
    """Dispara o instalador e devolve o PID dele, ou None se não puder (motivo no log)."""
    destino = destino or pasta()
    if motivo := motivo_para_nao_instalar(preparando):
        log.warning("Atualização ao fechar recusada: %s", motivo)
        return None
    if tentativas(destino) >= TENTATIVAS:
        log.warning("Atualização: %d tentativas sem sucesso; só manual.", TENTATIVAS)
        return None
    caminho = instalador(oferta, destino)
    (destino / TENTADAS).write_text(str(tentativas(destino) + 1), "ascii")
    if soltar_mutex is not None:
        soltar_mutex()
    filho: int = disparar(argumentos(caminho, oferta.manifesto.versao, pid), destino)
    log.info("Atualização para %s disparada ao fechar.", oferta.manifesto.versao)
    return filho


def situacao_no_inicio(destino: Path | None = None) -> str | None:
    """Ao abrir: limpa o que já foi instalado; avisa se a última tentativa não entrou."""
    destino = destino or pasta()
    try:
        cru = (destino / MANIFESTO).read_bytes()
        versao = json.loads(cru.decode("utf-8")).get("versao", "")
        alvo = tupla(versao) if isinstance(versao, str) else None
    except (OSError, ValueError, Recusada):
        return None
    if alvo is not None and alvo <= tupla(__version__):
        limpar(destino)  # já instalada
        log.info("Atualização: versão %s em execução; arquivos removidos.", __version__)
        return None
    if tentativas(destino):
        return (
            f"A atualização para {versao} não foi instalada. Veja o log em {destino} "
            "ou reinstale pelo instalador."
        )
    return None
