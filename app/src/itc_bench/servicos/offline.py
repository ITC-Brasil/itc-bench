r"""Login offline por 7 dias (ADR-013): verificador scrypt, DPAPI de máquina, pasta protegida.

Um arquivo, `%ProgramData%\ITC\Bench\protegido\logins.dpapi`, com uma entrada por técnico:
nome, sal, verificador, último login online, maior horário visto e falhas offline. Nunca a
senha. Só existe em execução elevada (a pasta protegida só é criada como administrador).
"""

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from itc_bench.nucleo import dpapi
from itc_bench.nucleo.log import log
from itc_bench.servicos.executor import Sensivel

VALIDADE = timedelta(days=7)
TOLERANCIA_RELOGIO = timedelta(minutes=5)
MAXIMO_FALHAS = 5
# n=2^15, r=8 usa 32 MiB, o limite padrão do OpenSSL: sem maxmem maior, ValueError.
SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


class OfflineRecusado(Exception):
    """Motivo em `codigo`: sem_login_recente, expirado, relogio, senha_errada, bloqueado,
    cofre_ilegivel."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


def normalizar(usuario: str) -> str:
    return usuario.strip().lower()


def verificador(senha: Sensivel, sal: bytes) -> bytes:
    return hashlib.scrypt(senha.revelar().encode(), salt=sal, **SCRYPT)


class Cofre:
    def __init__(self, arquivo: Path, agora: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.arquivo = arquivo
        self.agora = agora

    def lembrar(self, login: str, nome: str, senha: Sensivel) -> None:
        """Depois de um login online certo."""
        dados = self._ler_ou_vazio()
        agora = self.agora()
        sal = os.urandom(16)
        anterior = dados.get(normalizar(login), {})
        visto = max(agora, _data(anterior["maior_visto"])) if anterior else agora
        dados[normalizar(login)] = {
            "nome": nome,
            "sal": sal.hex(),
            "verificador": verificador(senha, sal).hex(),
            "ultimo_online": agora.isoformat(),
            "maior_visto": visto.isoformat(),
            "falhas": 0,
        }
        self._gravar(dados)

    def esquecer(self, login: str) -> None:
        dados = self._ler_ou_vazio()
        if dados.pop(normalizar(login), None) is not None:
            self._gravar(dados)
            log.info("Login offline de %s apagado desta máquina.", normalizar(login))

    def tem(self, login: str) -> bool:
        return normalizar(login) in self._ler_ou_vazio()

    def conferir(self, login: str, senha: Sensivel) -> str:
        """Devolve o nome do técnico ou levanta `OfflineRecusado`."""
        try:
            dados = self._ler()
        except (OSError, ValueError) as erro:
            log.error("Cofre offline ilegível (%s).", type(erro).__name__)
            raise OfflineRecusado("cofre_ilegivel") from None
        chave = normalizar(login)
        entrada = dados.get(chave)
        if entrada is None:
            raise OfflineRecusado("sem_login_recente")
        agora = self.agora()
        if agora < _data(entrada["maior_visto"]) - TOLERANCIA_RELOGIO:
            log.warning("Relógio desta máquina atrás do último uso; offline recusado.")
            raise OfflineRecusado("relogio")
        if agora - _data(entrada["ultimo_online"]) > VALIDADE:
            del dados[chave]
            self._gravar(dados)
            raise OfflineRecusado("expirado")
        entrada["maior_visto"] = max(agora, _data(entrada["maior_visto"])).isoformat()
        calculado = verificador(senha, bytes.fromhex(entrada["sal"]))
        if not hmac.compare_digest(calculado, bytes.fromhex(entrada["verificador"])):
            entrada["falhas"] += 1
            if entrada["falhas"] >= MAXIMO_FALHAS:
                del dados[chave]
                self._gravar(dados)
                log.warning(
                    "%s senhas erradas offline para %s; login offline apagado.",
                    MAXIMO_FALHAS,
                    chave,
                )
                raise OfflineRecusado("bloqueado")
            self._gravar(dados)
            raise OfflineRecusado("senha_errada")
        entrada["falhas"] = 0
        self._gravar(dados)
        return str(entrada["nome"])

    def _ler(self) -> dict[str, dict[str, Any]]:
        if not self.arquivo.exists():
            return {}
        conteudo: dict[str, dict[str, Any]] = json.loads(dpapi.decifrar(self.arquivo.read_bytes()))
        return conteudo

    def _ler_ou_vazio(self) -> dict[str, dict[str, Any]]:
        try:
            return self._ler()
        except (OSError, ValueError) as erro:
            log.error("Cofre offline ilegível (%s); será refeito.", type(erro).__name__)
            return {}

    def _gravar(self, dados: dict[str, dict[str, Any]]) -> None:
        temporario = self.arquivo.with_suffix(".tmp")
        temporario.write_bytes(dpapi.cifrar(json.dumps(dados).encode()))
        temporario.replace(self.arquivo)


def _data(texto: str) -> datetime:
    return datetime.fromisoformat(texto)
