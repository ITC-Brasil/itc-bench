r"""Cadastros da API com cache DPAPI (ADR-014). Sem Qt: os módulos 08 a 10 leem por aqui.

Cache em `%ProgramData%\ITC\Bench\protegido\cadastros.dpapi` (DPAPI de máquina, pasta só de
SYSTEM e Administradores, ADR-013), escrita atômica, válido 7 dias desde a última sincronização.
Vencido ou corrompido: apagado, com log. Sem administrador, só em memória. Logout e troca de
técnico não apagam: o cadastro é da máquina.

Segredos (`Servidores.Valor`/`Observacao` sem `Publico`, `WiFi.Senha`) viram `Sensivel` ao ler.
O log tem contagens, a versão curta e `Id`; nunca valor nem SSID.

Unidade da máquina: `HKLM\SOFTWARE\ITC\Bench`, valor `Unidade`, escolhida em Configurações.
"""

import json
import winreg
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from itc_bench.nucleo import dpapi
from itc_bench.nucleo.log import log
from itc_bench.servicos import api
from itc_bench.servicos.api import CHAVE_REGISTRO
from itc_bench.servicos.executor import Sensivel

FORMATO = 1
VALIDADE = timedelta(days=7)
TOLERANCIA_RELOGIO = timedelta(minutes=5)
VERSAO_LOG = 12


@dataclass(frozen=True)
class Servidor:
    id: int
    servico: str
    papel: str
    valor: str | Sensivel
    versao: str
    observacao: str | Sensivel
    publico: bool


@dataclass(frozen=True)
class Instalador:
    id: int
    programa: str
    versao: str
    arquivo: str
    sha256: str
    link: str
    observacao: str
    # ADR-020 / TA-ADR-029; cache antigo sem os campos = instalador.
    tipo: str = "instalador"
    categoria: str = "Programas"
    identificador: str = ""
    argumentos: str = ""
    deteccao: str = ""
    modo: str = "quiosque"


@dataclass(frozen=True)
class Rede:
    id: int
    ssid: str
    senha: Sensivel
    unidade: str
    categoria: str
    atualizado_em: str


@dataclass(frozen=True)
class Unidade:
    id: int
    codigo: str
    nome: str
    cidade: str
    uf: str
    tag_glpi: str
    perfil_padrao: str


@dataclass(frozen=True)
class Cadastros:
    versao: str = field(repr=False)  # no log só os 12 primeiros caracteres
    sincronizado_em: datetime
    por: str
    unidade: str | None  # filtro do Wi-Fi; None = todas as unidades (bancada)
    defasado: bool  # a API serviu a cópia dela com o NocoDB fora do ar
    servidores: tuple[Servidor, ...]
    instaladores: tuple[Instalador, ...]
    redes: tuple[Rede, ...]
    unidades: tuple[Unidade, ...]
    descartados: dict[str, list[Any]] = field(default_factory=dict)

    def servidor(self, servico: str, papel: str) -> Servidor | None:
        return next((s for s in self.servidores if s.servico == servico and s.papel == papel), None)

    def redes_da_unidade(self, codigo: str | None) -> tuple[Rede, ...]:
        return self.redes if codigo is None else tuple(r for r in self.redes if r.unidade == codigo)

    def unidade_por_codigo(self, codigo: str | None) -> Unidade | None:
        return next((u for u in self.unidades if u.codigo == codigo), None)


def _de_dados(registro: dict[str, Any]) -> Cadastros:
    """Registro do cache (ou corpo da API embrulhado) → Cadastros. KeyError/TypeError/ValueError
    se o formato estiver errado."""
    dados = registro["dados"]

    def segredo(publico: bool, valor: str) -> str | Sensivel:
        return valor if publico else Sensivel(valor)

    return Cadastros(
        versao=str(registro["versao"]),
        sincronizado_em=datetime.fromisoformat(registro["sincronizado_em"]),
        por=str(registro["por"]),
        unidade=registro["unidade"],
        defasado=bool(dados.get("defasado", False)),
        servidores=tuple(
            Servidor(
                int(s["id"]),
                str(s["servico"]),
                str(s["papel"]),
                segredo(s["publico"] is True, str(s["valor"])),
                str(s["versao"]),
                segredo(s["publico"] is True, str(s["observacao"])),
                s["publico"] is True,
            )
            for s in dados["servidores"]
        ),
        instaladores=tuple(
            Instalador(
                int(i["id"]),
                str(i["programa"]),
                str(i["versao"]),
                str(i["arquivo"]),
                str(i["sha256"]),
                str(i["link"]),
                str(i["observacao"]),
                str(i.get("tipo") or "instalador"),
                str(i.get("categoria") or "Programas"),
                str(i.get("identificador") or ""),
                str(i.get("argumentos") or ""),
                str(i.get("deteccao") or ""),
                str(i.get("modo") or "quiosque"),
            )
            for i in dados["instaladores"]
        ),
        redes=tuple(
            Rede(
                int(w["id"]),
                str(w["ssid"]),
                Sensivel(str(w["senha"])),
                str(w["unidade"]),
                str(w["categoria"]),
                str(w["atualizado_em"]),
            )
            for w in dados["wifi"]
        ),
        unidades=tuple(
            Unidade(
                int(u["id"]),
                str(u["codigo"]),
                str(u["nome"]),
                str(u["cidade"]),
                str(u["uf"]),
                str(u["tag_glpi"]),
                str(u["perfil_padrao"]),
            )
            for u in dados["unidades"]
        ),
        descartados=dict(dados.get("descartados") or {}),
    )


class Armazem:
    """O cache. `arquivo=None` (sem administrador): só em memória, nada em disco."""

    def __init__(
        self, arquivo: Path | None, agora: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.arquivo = arquivo
        self.agora = agora
        self._memoria: dict[str, Any] | None = None
        self.aviso: str | None = None  # "vencido" ou "corrompido" na última leitura

    def carregar(self) -> Cadastros | None:
        self.aviso = None
        registro = self._ler()
        if registro is None:
            return None
        try:
            if registro.get("formato") != FORMATO:
                raise ValueError("formato")
            cadastros = _de_dados(registro)
        except (KeyError, TypeError, ValueError, AttributeError) as erro:
            self._descartar("corrompido", type(erro).__name__)
            return None
        idade = self.agora() - cadastros.sincronizado_em
        if idade > VALIDADE or idade < -TOLERANCIA_RELOGIO:
            self._descartar("vencido", f"sincronizado em {cadastros.sincronizado_em:%d/%m %H:%M}")
            return None
        return cadastros

    def gravar(self, registro: dict[str, Any]) -> Cadastros:
        cadastros = _de_dados(registro)  # confere o formato antes de tocar no arquivo
        registro = {"formato": FORMATO, **registro}
        if self.arquivo is None:
            self._memoria = registro
        else:
            temporario = self.arquivo.with_suffix(".tmp")
            temporario.write_bytes(dpapi.cifrar(json.dumps(registro).encode()))
            temporario.replace(self.arquivo)
        return cadastros

    def filtrar(self, unidade: str | None) -> Cadastros | None:
        """Troca de unidade sem rede: só o Wi-Fi dela fica no cache (o resto já é global)."""
        registro = self._ler()
        atual = self.carregar() if registro is not None else None
        if registro is None or atual is None:
            return None
        if unidade is None:
            return atual  # sem rede não há como trazer as outras unidades de volta
        dados = dict(registro["dados"])
        dados["wifi"] = [w for w in dados["wifi"] if w.get("unidade") == unidade]
        # versão vazia: a próxima sincronização baixa de novo em vez de receber um 304
        novo = {**registro, "dados": dados, "unidade": unidade, "versao": ""}
        novo.pop("formato", None)
        log.info("Cache dos cadastros filtrado para a unidade %s (sem rede).", unidade)
        return self.gravar(novo)

    def _ler(self) -> dict[str, Any] | None:
        if self.arquivo is None:
            return self._memoria
        try:
            bruto = self.arquivo.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as erro:
            self._descartar("corrompido", type(erro).__name__)
            return None
        try:
            registro = json.loads(dpapi.decifrar(bruto))
        except (OSError, ValueError) as erro:
            self._descartar("corrompido", type(erro).__name__)
            return None
        if not isinstance(registro, dict):
            self._descartar("corrompido", "formato")
            return None
        return registro

    def _descartar(self, aviso: str, detalhe: str) -> None:
        self.aviso = aviso
        log.warning("Cache dos cadastros %s (%s); apagado.", aviso, detalhe)
        self._memoria = None
        if self.arquivo is not None:
            try:
                self.arquivo.unlink(missing_ok=True)
            except OSError as erro:
                log.error("Não foi possível apagar o cache dos cadastros: %s", erro)


@dataclass(frozen=True)
class Sincronizacao:
    """estado: ok (baixou), igual (304), offline (sem servidor ou NocoDB fora; cache mantido),
    sessao (401: login de novo), unidade_invalida, erro (resposta estranha; cache mantido)."""

    estado: str
    cadastros: Cadastros | None


def sincronizar(
    base: str, token: Sensivel, armazem: Armazem, por: str, unidade: str | None
) -> Sincronizacao:
    atual = armazem.carregar()
    versao = atual.versao if atual is not None and atual.unidade == unidade else None
    try:
        corpo = api.cadastros(base, token, versao or None, unidade)
    except (api.SemConexao, api.CadastrosIndisponivel) as erro:
        log.info("Cadastros sem sincronizar (%s); usando o cache.", erro)
        if unidade is not None and atual is not None and atual.unidade != unidade:
            atual = armazem.filtrar(unidade)  # unidade trocada sem rede: só o Wi-Fi dela fica
        return Sincronizacao("offline", atual)
    except api.Recusado as erro:
        log.warning("Cadastros recusados pela API (%s).", erro.codigo)
        return Sincronizacao("sessao" if erro.status == 401 else erro.codigo, atual)
    except api.ErroApi as erro:
        log.error("Cadastros: %s", erro)
        return Sincronizacao("erro", atual)
    agora = armazem.agora().isoformat()
    if corpo is None:
        registro = armazem._ler()
        if atual is None or registro is None:  # 304 só vem com a versão do cache
            log.error("Cadastros: 304 sem cache local.")
            return Sincronizacao("erro", None)
        registro = {**registro, "sincronizado_em": agora, "por": por}
        registro.pop("formato", None)
        log.info("Cadastros sem mudança (versão %s).", atual.versao[:VERSAO_LOG])
        return Sincronizacao("igual", armazem.gravar(registro))
    registro = {
        "versao": str(corpo.get("versao", "")),
        "sincronizado_em": agora,
        "por": por,
        "unidade": unidade,
        "dados": corpo,
    }
    try:
        cadastros = armazem.gravar(registro)
    except (KeyError, TypeError, ValueError, AttributeError) as erro:
        log.error("Cadastros: resposta fora do formato (%s); cache mantido.", type(erro).__name__)
        return Sincronizacao("erro", atual)
    log.info(
        "Cadastros sincronizados: versão %s, %d servidores, %d instaladores, %d redes, "
        "%d unidades, unidade %s%s.",
        cadastros.versao[:VERSAO_LOG],
        len(cadastros.servidores),
        len(cadastros.instaladores),
        len(cadastros.redes),
        len(cadastros.unidades),
        unidade or "todas",
        ", defasado na API" if cadastros.defasado else "",
    )
    return Sincronizacao("ok", cadastros)


def rotulo(cadastros: Cadastros | None, offline: bool, agora: datetime | None = None) -> str:
    """Texto do rodapé: sincronizado HH:MM, DD/MM HH:MM, offline · dados de …, sem cadastros."""
    if cadastros is None:
        return "sem cadastros"
    agora = agora or datetime.now(UTC)
    local = cadastros.sincronizado_em.astimezone()
    quando = (
        f"{local:%H:%M}" if local.date() == agora.astimezone().date() else f"{local:%d/%m %H:%M}"
    )
    if offline or cadastros.defasado:
        return f"offline · dados de {quando}"
    return f"sincronizado {quando}"


def unidade_da_maquina() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE_REGISTRO) as chave:
            valor, _ = winreg.QueryValueEx(chave, "Unidade")
    except FileNotFoundError:
        return None
    return str(valor).strip() or None


def gravar_unidade(codigo: str | None) -> None:
    """Exige administrador (HKLM); PermissionError sem ele."""
    with winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE, CHAVE_REGISTRO, 0, winreg.KEY_SET_VALUE
    ) as chave:
        if codigo is None:
            try:
                winreg.DeleteValue(chave, "Unidade")
            except FileNotFoundError:
                return
        else:
            winreg.SetValueEx(chave, "Unidade", 0, winreg.REG_SZ, codigo)
