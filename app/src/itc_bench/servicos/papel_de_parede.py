r"""Papel de parede (ADR-022), sem Qt: a tela Tela e papel de parede e o 13 usam.

A imagem vem de Instaladores com `Tipo = papel` (SHA-256 conferido, download ou "Escolher
arquivo…") e fica em `%ProgramData%\ITC\Bench\papel\<sha256>.<ext>`, legível por Usuários e
gravável só por Administradores e SYSTEM. Aplicada pela política de usuário `Wallpaper` /
`WallpaperStyle` no hive de cada alvo (serviço do 11); vale no próximo logon. O caminho da imagem
só sai de `caminho()` e nunca vai ao log.
"""

import struct
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Literal

from itc_bench.nucleo import acl
from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, hive, instaladores
from itc_bench.servicos.cadastros import Cadastros, Instalador
from itc_bench.servicos.hive import Acao, Alvo, Feito, Rodar

CHAVE = "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System"
EXTENSOES = (".jpg", ".jpeg", ".png")
TETO = 20 * 1024 * 1024
MINIMO, MAXIMO = (640, 480), (7680, 4320)
ESTILOS = {"preencher": "10", "ajustar": "6", "estender": "22", "centralizar": "0"}
ROTULO_ESTILO = {
    "preencher": "Preencher",
    "ajustar": "Ajustar",
    "estender": "Estender",
    "centralizar": "Centralizar",
}
Estado = Literal["aplicado", "outra_imagem", "diferente", "nao_aplicado", "nao_lida", "sem_acesso"]
ROTULO_ESTADO: dict[Estado, str] = {
    "aplicado": "aplicado",
    "outra_imagem": "outra imagem do Bench",
    "diferente": "outro papel de parede (política)",
    "nao_aplicado": "não aplicado",
    "nao_lida": "não lida",
    "sem_acesso": "sem acesso",
}


class ErroPapel(Exception):
    """Mensagem para a tela; sem caminho."""


def linhas(cadastros: Cadastros | None) -> list[Instalador]:
    return [i for i in (cadastros.instaladores if cadastros else ()) if i.tipo == "papel"]


def extensao(linha: Instalador) -> str:
    return PurePath(linha.arquivo.strip()).suffix.lower()


def validar(linha: Instalador) -> str | None:
    if linha.tipo != "papel":
        return "A linha não é de papel de parede."
    ext = extensao(linha)
    if ext not in EXTENSOES:
        return f"O arquivo de “{linha.programa}” tem que ser .jpg, .jpeg ou .png."
    return instaladores.validar(linha, ext)


# ---------------------------------------------------------------- imagem


def dimensoes(cabeca: bytes, ext: str) -> tuple[int, int] | None:
    """(largura, altura) lida do cabeçalho, se a assinatura de bytes casar com a extensão."""
    if ext == ".png":
        if cabeca[:8] != b"\x89PNG\r\n\x1a\n" or cabeca[12:16] != b"IHDR":
            return None
        largura, altura = struct.unpack(">II", cabeca[16:24])
        return largura, altura
    if cabeca[:3] != b"\xff\xd8\xff":
        return None
    i = 2
    while i + 9 < len(cabeca):
        if cabeca[i] != 0xFF:
            return None
        marca = cabeca[i + 1]
        if marca == 0xFF:  # preenchimento
            i += 1
            continue
        tamanho = struct.unpack(">H", cabeca[i + 2 : i + 4])[0]
        # SOF0 a SOF15, menos DHT (C4), JPG (C8) e DAC (CC).
        if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
            altura, largura = struct.unpack(">HH", cabeca[i + 5 : i + 9])
            return largura, altura
        i += 2 + tamanho
    return None


def conferir_imagem(arquivo: Path, ext: str) -> str | None:
    """Motivo da recusa, ou None."""
    tamanho = arquivo.stat().st_size
    if tamanho > TETO:
        return "A imagem passou de 20 MB."
    with arquivo.open("rb") as f:
        cabeca = f.read(min(tamanho, 512 * 1024))
    dim = dimensoes(cabeca, ext)
    if dim is None:
        return "O arquivo não é uma imagem JPEG/PNG válida (conteúdo diferente da extensão)."
    (lmin, amin), (lmax, amax) = MINIMO, MAXIMO
    if not (lmin <= dim[0] <= lmax and amin <= dim[1] <= amax):
        return f"Imagem de {dim[0]}x{dim[1]}: aceita de 640x480 a 7680x4320."
    return None


# ---------------------------------------------------------------- pasta e arquivo


def pasta() -> Path:
    return instaladores.papeis()


def preparar_pasta(base: Path | None = None) -> Path:
    """Cria a pasta e reaplica a ACL (Usuários leem; só Admin/SYSTEM gravam); confere depois."""
    base = base or pasta()
    base.mkdir(parents=True, exist_ok=True)
    acl.proteger(base, acl.SDDL)
    atual = acl.sddl_atual(base)
    if atual != acl.SDDL:
        raise acl.ErroAcl(0, f"Pasta do papel de parede com ACL inesperado: {atual}")
    return base


def caminho(linha: Instalador, base: Path | None = None) -> Path | None:
    """Arquivo guardado e conferido da linha, ou None. Único produtor do valor `Wallpaper`."""
    return instaladores.guardado(linha, extensao(linha), base or pasta())


def obter(
    linha: Instalador,
    origem: Path | None = None,
    *,
    base: Path | None = None,
    cancelar: threading.Event | None = None,
    abrir: Any = None,
) -> Path:
    """Baixa (ou copia de `origem`) para a pasta, confere o SHA-256 e a imagem."""
    motivo = validar(linha)
    if motivo:
        raise ErroPapel(motivo)
    base = preparar_pasta(base) if base is None else base
    ext = extensao(linha)
    extra = {"abrir": abrir} if abrir is not None else {}
    try:
        if origem is not None:
            arquivo = instaladores.copiar(linha, ext, origem, base=base, cancelar=cancelar)
        else:
            arquivo = instaladores.obter(linha, ext, base=base, cancelar=cancelar, **extra)
    except instaladores.ErroInstalador as erro:
        raise ErroPapel(str(erro)) from None
    motivo = conferir_imagem(arquivo, ext)
    if motivo:
        arquivo.unlink(missing_ok=True)
        log.warning("Papel de parede: Id %s recusado (imagem inválida)", linha.id)
        raise ErroPapel(motivo)
    log.info("Papel de parede: Id %s pronto (%s…)", linha.id, linha.sha256.strip()[:12].lower())
    return arquivo


# ---------------------------------------------------------------- situação


def _chaves() -> list[dict[str, Any]]:
    return [{"escopo": "usuario", "chave": CHAVE, "nomes": ["Wallpaper", "WallpaperStyle"]}]


@dataclass(frozen=True)
class Situacao:
    estado: Estado
    estilo: str | None = None  # chave de ESTILOS, se for um deles


def estado(lidos: dict[str, Any] | None, atual: Path | None) -> Situacao:
    if not isinstance(lidos, dict):
        return Situacao("sem_acesso")
    valores = lidos.get("valores") or {}
    imagem = valores.get(f"{CHAVE}|Wallpaper")
    estilo_ = valores.get(f"{CHAVE}|WallpaperStyle")
    estilo = next((k for k, v in ESTILOS.items() if v == estilo_), None)
    if imagem is None:
        return Situacao("nao_aplicado")
    if atual is not None and str(imagem).lower() == str(atual).lower():
        return Situacao("aplicado", estilo)
    if str(imagem).lower().startswith(str(pasta()).lower() + "\\"):
        return Situacao("outra_imagem", estilo)
    return Situacao("diferente", estilo)


def ler(
    alvos_: Sequence[Alvo],
    linha: Instalador | None,
    *,
    rodar: Rodar = executor.powershell,
    descarregados: bool = False,
) -> dict[str, Situacao]:
    usuarios = [a for a in alvos_ if a.tipo != "maquina"]
    _, _, dados = hive.ler(
        usuarios, _chaves(), perfil="aparencia", rodar=rodar, descarregados=descarregados
    )
    atual = caminho(linha) if linha is not None else None
    saida = {}
    for a in usuarios:
        d = dados.get(a.chave)
        saida[a.chave] = (
            Situacao("nao_lida")
            if d == hive.NAO_LIDA
            else estado(d if isinstance(d, dict) else None, atual)
        )
    return saida


# ---------------------------------------------------------------- aplicar / desfazer


def operacoes(
    acao: Acao, imagem: Path | None = None, estilo: str = "preencher"
) -> list[dict[str, Any]]:
    if acao == "desfazer":
        return [
            {"p": "papel", "chave": CHAVE, "nome": n, "tipo": "sz", "dado": "", "acao": "apagar"}
            for n in ("Wallpaper", "WallpaperStyle")
        ]
    if imagem is None or estilo not in ESTILOS:
        raise ValueError("Imagem ou estilo inválido.")
    if imagem.parent != pasta():
        raise ValueError("A imagem tem que estar na pasta do papel de parede.")
    return [
        {
            "p": "papel",
            "chave": CHAVE,
            "nome": "Wallpaper",
            "tipo": "sz",
            "dado": str(imagem),
            "acao": "gravar",
        },
        {
            "p": "papel",
            "chave": CHAVE,
            "nome": "WallpaperStyle",
            "tipo": "sz",
            "dado": ESTILOS[estilo],
            "acao": "gravar",
        },
    ]


def aplicar(
    acao: Acao,
    alvos_: Sequence[Alvo],
    *,
    linha: Instalador | None = None,
    estilo: str = "preencher",
    protegidas_: Iterable[str],
    rodar: Rodar = executor.powershell,
    cancelar: threading.Event | None = None,
    avisar: Callable[[str], None] = lambda _: None,
) -> list[Feito]:
    """Aplicar exige a imagem já guardada (`obter`) e confere o SHA-256 de novo antes."""
    imagem: Path | None = None
    if acao == "aplicar":
        if linha is None:
            raise ErroPapel("Escolha a imagem do cadastro.")
        imagem = caminho(linha)
        if imagem is None:
            raise ErroPapel("A imagem ainda não foi baixada ou conferida.")
        log.info(
            "Papel de parede: aplicar Id %s (%s…)", linha.id, linha.sha256.strip()[:12].lower()
        )
    ops = operacoes(acao, imagem, estilo)
    return hive.aplicar(
        acao,
        [a for a in alvos_ if a.tipo != "maquina"],
        lambda _: ops,
        nomes={"papel": "Papel de parede"},
        rotulo="Papel de parede",
        item="item",
        perfil="aparencia",
        protegidas_=protegidas_,
        rodar=rodar,
        cancelar=cancelar,
        avisar=avisar,
        mensagens=hive.MENSAGENS_APARENCIA,
    )
