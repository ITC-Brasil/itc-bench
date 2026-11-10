"""Instaladores do cadastro (ADR-019, SHA-256 opcional pelo ADR-028), sem Qt.

O arquivo fica em `protegido\\instaladores` (só SYSTEM e Administradores), com nome que vem do
hash, nunca de `Instaladores.Arquivo`: `<sha256>.<ext>` quando o cadastro tem SHA-256, e
`c<chave>.<sha256 calculado>.<ext>` quando não tem (`chave` de Id, Link e Versao). O hash é
calculado sobre o que foi gravado ali (download ou cópia) e conferido de novo, pelo nome, logo
antes de executar. O log nunca recebe o `Link`, nem o host.
"""

import hashlib
import re
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import IO, Any
from urllib.parse import urlsplit

from itc_bench import __version__
from itc_bench.nucleo import caminhos
from itc_bench.nucleo.log import log
from itc_bench.servicos.cadastros import Cadastros, Instalador

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
TETO = 300 * 1024 * 1024
BLOCO = 1024 * 1024
TIMEOUT = 30  # por leitura

Progresso = Callable[[int, int | None], None]  # (bytes lidos, total ou None)
Abrir = Callable[[str], IO[bytes]]


class ErroInstalador(Exception):
    """Mensagem para a tela; o log já recebeu só `Id` e motivo."""


class Cancelado(ErroInstalador):
    def __init__(self) -> None:
        super().__init__("Cancelado pelo técnico.")


def pasta() -> Path:
    return caminhos.protegida() / "instaladores"


def do_cadastro(cadastros: Cadastros | None, programa: str) -> Instalador | str:
    """A linha ativa do programa, ou a mensagem do que falta (ADR-008)."""
    if cadastros is None:
        return "Sem cadastros: conecte, entre e sincronize."
    # Só instaladores: um winget ou Web App com o mesmo nome não conta (ADR-020).
    linhas = [
        i for i in cadastros.instaladores if i.tipo == "instalador" and i.programa == programa
    ]
    if not linhas:
        return f"Cadastre o instalador “{programa}” em Instaladores e sincronize."
    if len(linhas) > 1:
        return f"Há mais de uma linha ativa “{programa}” em Instaladores."
    return linhas[0]


def validar(instalador: Instalador, extensao: str) -> str | None:
    """Motivo do cadastro inválido, ou None. `extensao` com ponto, ex.: `.msi`.

    O ícone de Web App (`.ico`) e o papel de parede (ADR-022) não têm versão.
    """
    nome = instalador.programa
    if instalador.tipo == "instalador" and extensao != ".ico" and not instalador.versao.strip():
        return f"O instalador “{nome}” está sem versão em Instaladores."
    sha = instalador.sha256.strip()
    if sha and not SHA256.fullmatch(sha):  # vazio vale (ADR-028); texto errado é digitação
        return f"O instalador “{nome}” tem SHA-256 inválido (64 hexadecimais)."
    if PurePath(instalador.arquivo.strip()).suffix.lower() != extensao:
        return f"O arquivo do instalador “{nome}” tem que ser {extensao}."
    partes = urlsplit(instalador.link.strip())
    if partes.scheme != "https" or not partes.hostname:
        return f"O link do instalador “{nome}” tem que ser https://."
    return None


def cadastrado(instalador: Instalador) -> str:
    """SHA-256 do cadastro em minúsculas, ou "" (ADR-028)."""
    return instalador.sha256.strip().lower()


def chave(instalador: Instalador) -> str:
    """Nome-base do cache sem SHA-256: muda quando Link ou Versao mudam (ADR-028)."""
    texto = f"{instalador.id}\n{instalador.link.strip()}\n{instalador.versao.strip()}"
    return "c" + hashlib.sha256(texto.encode()).hexdigest()


def destino(
    instalador: Instalador, extensao: str, base: Path | None = None, calculado: str = ""
) -> Path:
    """`<sha>.<ext>` com hash no cadastro; `c<chave>.<calculado>.<ext>` sem."""
    sha = cadastrado(instalador)
    nome = sha if sha else f"{chave(instalador)}.{calculado}"
    return (base or pasta()) / f"{nome}{extensao}"


def hash_do_nome(caminho: Path) -> str:
    """O hash que o arquivo do cache tem que ter, tirado do próprio nome."""
    partes = caminho.name.split(".")
    return (partes[1] if len(partes) == 3 else partes[0]).lower()


def hash_de(caminho: Path, cancelar: threading.Event | None = None) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            if cancelar is not None and cancelar.is_set():
                raise Cancelado
            h.update(bloco)
    return h.hexdigest()


def conferir(caminho: Path) -> bool:
    """Confere de novo, pelo hash do nome, logo antes de executar (ADR-019, ADR-028)."""
    try:
        return hash_de(caminho) == hash_do_nome(caminho)
    except OSError:
        return False


def guardado(instalador: Instalador, extensao: str, base: Path | None = None) -> Path | None:
    """Arquivo já baixado com o hash certo, ou None. Sem hash, apaga o que não confere."""
    if cadastrado(instalador):
        alvo = destino(instalador, extensao, base)
        return alvo if alvo.is_file() and conferir(alvo) else None
    raiz = base or pasta()
    if not raiz.is_dir():
        return None
    for item in raiz.glob(f"{chave(instalador)}.*{extensao}"):
        if len(item.name.split(".")) != 3:
            continue
        if conferir(item):
            return item
        log.warning("Instaladores: Id %s guardado não confere; baixando de novo", instalador.id)
        item.unlink(missing_ok=True)
    return None


class _SoHttps(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        if urlsplit(newurl).scheme != "https":
            raise ErroInstalador("O link redirecionou para fora de https://.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_abridor = urllib.request.build_opener(_SoHttps)


# O download do AnyDesk responde 403 ao User-Agent padrão do urllib (`Python-urllib/3.x`),
# testado em 10/11/2026; com um nome próprio, 200. O redirecionamento leva o mesmo cabeçalho.
AGENTE = f"ITC-Bench/{__version__}"


def _abrir(url: str) -> IO[bytes]:
    if urlsplit(url).scheme != "https":  # conferido em validar(); aqui de novo
        raise ErroInstalador("O link tem que ser https://.")
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})  # noqa: S310 — https acima
    resposta: IO[bytes] = _abridor.open(pedido, timeout=TIMEOUT)
    return resposta


def _gravar(
    instalador: Instalador,
    extensao: str,
    fonte: IO[bytes],
    total: int | None,
    base: Path | None,
    cancelar: threading.Event | None,
    progresso: Progresso | None,
) -> Path:
    """Grava `fonte` em `.parcial` calculando o hash; com hash no cadastro, só passa se bater."""
    raiz = base or pasta()
    raiz.mkdir(parents=True, exist_ok=True)
    parcial = raiz / f"{cadastrado(instalador) or chave(instalador)}{extensao}.parcial"
    h = hashlib.sha256()
    lidos = 0
    try:
        with parcial.open("wb") as saida:
            while bloco := fonte.read(BLOCO):
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado
                lidos += len(bloco)
                if lidos > TETO:
                    raise ErroInstalador("O instalador passou de 300 MB.")
                h.update(bloco)
                saida.write(bloco)
                if progresso is not None:
                    progresso(lidos, total)
        obtido = h.hexdigest()
        esperado = cadastrado(instalador)
        if esperado and obtido != esperado:
            log.error(
                "Instaladores: Id %s com SHA-256 diferente (esperado %s…, obtido %s…)",
                instalador.id,
                esperado[:12],
                obtido[:12],
            )
            raise ErroInstalador(
                f"O arquivo de “{instalador.programa}” não confere com o cadastro (SHA-256)."
            )
        alvo = destino(instalador, extensao, base, obtido)
        if not esperado:  # uma cópia por chave: a de conteúdo antigo sai
            for velho in raiz.glob(f"{chave(instalador)}.*{extensao}"):
                if velho != alvo:
                    velho.unlink(missing_ok=True)
            log.info(
                "Instaladores: Id %s sem SHA-256 cadastrado (calculado %s…)",
                instalador.id,
                obtido[:12],
            )
        parcial.replace(alvo)
        return alvo
    finally:
        parcial.unlink(missing_ok=True)


def obter(
    instalador: Instalador,
    extensao: str,
    *,
    base: Path | None = None,
    cancelar: threading.Event | None = None,
    progresso: Progresso | None = None,
    abrir: Abrir = _abrir,
) -> Path:
    """Arquivo guardado com o hash certo, ou baixado do `Link` e conferido."""
    motivo = validar(instalador, extensao)
    if motivo:
        raise ErroInstalador(motivo)
    pronto = guardado(instalador, extensao, base)
    if pronto is not None:
        log.info("Instaladores: Id %s já guardado (%s…)", instalador.id, pronto.stem[:12])
        return pronto
    log.info(
        "Instaladores: baixando Id %s (%s %s)",
        instalador.id,
        instalador.programa,
        instalador.versao,
    )
    try:
        resposta = abrir(instalador.link.strip())
    except ErroInstalador:
        raise
    except OSError as erro:  # URLError, HTTPError, timeout
        log.warning(
            "Instaladores: download do Id %s falhou (%s)", instalador.id, type(erro).__name__
        )
        raise ErroInstalador(
            f"Não foi possível baixar “{instalador.programa}”. Sem rede, use “Escolher arquivo…”."
        ) from erro
    with resposta:
        cabecalhos = getattr(resposta, "headers", None)
        tamanho = cabecalhos.get("Content-Length") if cabecalhos is not None else None
        total = int(tamanho) if tamanho and str(tamanho).isdigit() else None
        if total is not None and total > TETO:
            raise ErroInstalador("O instalador passou de 300 MB.")
        try:
            caminho = _gravar(instalador, extensao, resposta, total, base, cancelar, progresso)
        except OSError as erro:
            log.warning(
                "Instaladores: download do Id %s interrompido (%s)",
                instalador.id,
                type(erro).__name__,
            )
            raise ErroInstalador(
                f"O download de “{instalador.programa}” foi interrompido."
            ) from erro
    log.info("Instaladores: Id %s baixado e conferido (%s…)", instalador.id, caminho.stem[:12])
    return caminho


def copiar(
    instalador: Instalador,
    extensao: str,
    origem: Path,
    *,
    base: Path | None = None,
    cancelar: threading.Event | None = None,
) -> Path:
    """Arquivo escolhido pelo técnico: copiado para `.parcial` e conferido sobre a cópia."""
    motivo = validar(instalador, extensao)
    if motivo:
        raise ErroInstalador(motivo)
    try:
        with origem.open("rb") as fonte:
            caminho = _gravar(instalador, extensao, fonte, None, base, cancelar, None)
    except OSError as erro:
        log.warning(
            "Instaladores: cópia para o Id %s falhou (%s)", instalador.id, type(erro).__name__
        )
        raise ErroInstalador(f"Não foi possível ler o arquivo escolhido: {erro.strerror}") from erro
    log.info("Instaladores: Id %s copiado de arquivo escolhido e conferido", instalador.id)
    return caminho


def icones() -> Path:
    r"""%ProgramData%\ITC\Bench\icones: ícones dos Web Apps, legíveis por Usuários (ADR-020)."""
    return caminhos.dados() / "icones"


def papeis() -> Path:
    r"""%ProgramData%\ITC\Bench\papel: papéis de parede, legíveis por Usuários (ADR-022)."""
    return caminhos.dados() / "papel"


def limpar(cadastros: Cadastros | None, base: Path | None = None) -> list[str]:
    r"""Apaga o que não corresponde a nenhuma linha ativa de Instaladores; sem cadastros, nada.

    Sem `base`, vale para `protegido\instaladores`, `icones` (ADR-020) e `papel` (ADR-022).
    """
    if cadastros is None:
        return []
    ativos = {cadastrado(i) or chave(i) for i in cadastros.instaladores}
    apagados = []
    for raiz in [base] if base is not None else [pasta(), icones(), papeis()]:
        if not raiz.is_dir():
            continue
        for item in raiz.iterdir():
            sha = item.name.split(".", 1)[0].lower()
            if item.is_file() and (sha not in ativos or item.name.endswith(".parcial")):
                try:
                    item.unlink()
                    apagados.append(item.name)
                except OSError as erro:
                    log.warning("Instaladores: não apagou %s… (%s)", sha[:12], type(erro).__name__)
    if apagados:
        log.info("Instaladores: %d arquivo(s) sem cadastro apagado(s)", len(apagados))
    return apagados
