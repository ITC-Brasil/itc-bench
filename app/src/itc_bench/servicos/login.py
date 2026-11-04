"""Decide entre login online e offline (ADR-013). Sem Qt; a tela chama por `ui/tarefa.py`."""

from dataclasses import dataclass

from itc_bench.nucleo.log import log
from itc_bench.servicos import api
from itc_bench.servicos.executor import Sensivel
from itc_bench.servicos.offline import Cofre, OfflineRecusado, normalizar

MENSAGENS_OFFLINE = {
    "sem_login_recente": "Sem conexão, e este usuário não entrou nesta máquina nos últimos 7 dias.",
    "expirado": "Sem conexão, e o último login online deste usuário tem mais de 7 dias.",
    "relogio": "O relógio desta máquina está atrasado. Corrija a data e a hora.",
    "senha_errada": "Usuário ou senha incorretos.",
    "bloqueado": "Muitas senhas erradas sem conexão. Entre de novo com a máquina online.",
    "cofre_ilegivel": "Login offline indisponível nesta máquina. Detalhes no log.",
    "sem_pasta_protegida": "Sem conexão, e o login offline não funciona sem administrador.",
    "sem_endereco": "API não configurada, e este usuário não tem login offline.",
}


@dataclass(frozen=True)
class Entrada:
    login: str
    nome: str
    sessao: api.SessaoApi | None  # None: entrou offline

    @property
    def offline(self) -> bool:
        return self.sessao is None

    @property
    def rotulo_log(self) -> str:
        return f"{self.login} (offline)" if self.offline else self.login


def entrar(
    usuario: str, senha: Sensivel, *, base: str | None, maquina: str, cofre: Cofre | None
) -> Entrada:
    """Online primeiro. Só sem servidor (`api.SemConexao`) cai para o offline; recusa da API
    (401, 403, 429) e resposta estranha (`ErroApi`) nunca caem. 401/403 apagam o offline."""
    usuario = normalizar(usuario)
    motivo = "sem_endereco"
    if base:
        try:
            sessao = api.entrar(base, usuario, senha, maquina)
        except api.SemConexao as erro:
            log.info("Login de %s sem servidor (%s); tentando offline.", usuario, erro)
            motivo = "sem_login_recente"
        except api.Recusado as erro:
            if erro.status in (401, 403) and cofre is not None:
                cofre.esquecer(usuario)
            raise
        else:
            if cofre is not None:
                cofre.lembrar(sessao.login, sessao.nome, senha)
            return Entrada(sessao.login, sessao.nome, sessao)
    if cofre is None:
        raise OfflineRecusado("sem_pasta_protegida" if base else motivo)
    try:
        nome = cofre.conferir(usuario, senha)
    except OfflineRecusado as erro:
        if erro.codigo == "sem_login_recente":
            raise OfflineRecusado(motivo) from None
        raise
    return Entrada(usuario, nome, None)


def destravar(atual: Entrada, usuario: str, senha: Sensivel, cofre: Cofre | None) -> bool:
    """Mesmo técnico com verificador local destrava sem rede. Devolve False quando precisa de
    login completo (outro técnico, ou sem pasta protegida)."""
    if cofre is None or normalizar(usuario) != atual.login or not cofre.tem(atual.login):
        return False
    cofre.conferir(atual.login, senha)
    return True


def mensagem(erro: Exception) -> str:
    if isinstance(erro, OfflineRecusado):
        return MENSAGENS_OFFLINE.get(erro.codigo, "Login offline recusado.")
    return api.mensagem(erro)
