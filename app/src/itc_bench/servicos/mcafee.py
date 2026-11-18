"""Remoção assistida do McAfee (ADR-068), sem Qt.

O MCPR (McAfee Consumer Product Removal) é a ferramenta oficial da McAfee. Ele não tem modo
silencioso: pede que uma pessoa digite um código de validação na tela. Por isso o Bench não o
roda sozinho nem tenta passar dessa tela: baixa o MCPR da linha de Instaladores (ADR-066),
abre, espera o técnico terminar e confere de novo se o McAfee sumiu. O log recebe só o Id da
linha e quantos produtos McAfee sobraram; nunca o Link.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from itc_bench.nucleo.log import log
from itc_bench.servicos import executor, instaladores, programas
from itc_bench.servicos.cadastros import Cadastros, Instalador

NOME = "McAfee"
EXTENSAO = ".exe"
TIMEOUT = 3600.0  # o técnico pode demorar; a remoção leva alguns minutos
AVISO_ETAPA = "McAfee encontrado: remova em Remover programas (MCPR, com o técnico)."

Listar = Callable[[], list[programas.Instalado]]
Rodar = Callable[..., executor.Resultado]


def encontrados(listar: Listar = programas.instalados) -> list[str]:
    """Nomes dos produtos McAfee instalados (DisplayName com "McAfee"), sem repetição."""
    nomes = {i.nome for i in listar() if NOME.casefold() in i.nome.casefold()}
    return sorted(nomes, key=str.casefold)


def linha_mcpr(cadastros: Cadastros | None) -> Instalador | str:
    """A linha ativa do MCPR em Instaladores (ADR-066), ou o que falta no cadastro."""
    if cadastros is None:
        return "Sem cadastros: conecte, entre e sincronize."
    linhas = [i for i in cadastros.instaladores if programas.ferramenta(i)]
    if not linhas:
        return (
            "Cadastre o MCPR em Instaladores (Tipo instalador, ativo, arquivo .exe) e sincronize."
        )
    if len(linhas) > 1:
        return "Há mais de uma linha ativa do MCPR em Instaladores."
    motivo = instaladores.validar(linhas[0], EXTENSAO)
    return motivo or linhas[0]


@dataclass(frozen=True)
class Resultado:
    restantes: list[str]
    mensagem: str

    @property
    def ok(self) -> bool:
        return not self.restantes


def remover(
    cadastros: Cadastros | None,
    *,
    cancelar: threading.Event | None = None,
    progresso: instaladores.Progresso | None = None,
    executar: Rodar = executor.executar,
    listar: Listar = programas.instalados,
    obter: Callable[..., Path] = instaladores.obter,
    conferir: Callable[[Path], bool] = instaladores.conferir,
) -> Resultado:
    """Baixa e confere o MCPR, abre para o técnico, espera fechar e procura o McAfee de novo."""
    linha = linha_mcpr(cadastros)
    if isinstance(linha, str):
        raise instaladores.ErroInstalador(linha)
    arquivo = obter(linha, EXTENSAO, cancelar=cancelar, progresso=progresso)
    if not conferir(arquivo):
        log.error("McAfee: MCPR Id %s com SHA-256 diferente antes de executar", linha.id)
        raise instaladores.ErroInstalador("O arquivo do MCPR não confere com o cadastro.")
    log.info("McAfee: abrindo o MCPR (Id %s) para o técnico", linha.id)
    r = executar(
        [str(arquivo)],
        timeout=TIMEOUT,
        encerrar_no_timeout=False,
        descricao=f"MCPR Id {linha.id}",
    )
    restantes = encontrados(listar)
    log.info(
        "McAfee: MCPR fechou (código %s); %d produto(s) McAfee restante(s)",
        r.codigo,
        len(restantes),
    )
    if r.esgotado:
        return Resultado(
            restantes, "O MCPR passou de 1 hora aberto. Termine nele e confira de novo."
        )
    if restantes:
        return Resultado(
            restantes,
            "Ainda encontrado: " + ", ".join(restantes) + ". Reinicie e rode o MCPR de novo.",
        )
    return Resultado([], "McAfee removido. Reinicie a máquina para concluir.")
