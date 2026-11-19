"""Etapas da Preparação completa (ADR-023), sem Qt: cada uma só chama os serviços dos módulos
07 a 12, sem lógica duplicada. `ler()` diz feito/pendente/bloqueada pela situação do Windows;
`aplicar()` faz só o que falta. Mensagens para a tela; o log fica com o motor e os serviços.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from itc_bench.servicos import (
    aparencia,
    contas,
    desinstalar,
    energia,
    hive,
    identificacao,
    instaladores,
    limpeza,
    mcafee,
    papel_de_parede,
    perfis,
    politicas,
    programas,
    protecao,
    remoto,
    steam,
    wifi,
)
from itc_bench.servicos.cadastros import Cadastros
from itc_bench.servicos.preparacao import Etapa, Leitura, Resultado

SEM_ADMIN = "requer administrador"
NATIVO_ATIVO = (
    "O Administrador nativo está ativo. O Bench não o altera (ADR-017): desative-o pelo "
    "Windows e leia de novo."
)


@dataclass
class Contexto:
    """O que a tela entrega ao motor. Os alvos são SIDs; nunca vão ao log."""

    admin: bool
    cadastros: Cadastros | None
    unidade: str | None = None
    nome: str = ""  # nome pedido para o computador; vazio = não renomear
    alvos: tuple[str, ...] = ()  # SIDs das contas de aluno marcadas
    perfil: str = ""  # código do perfil da Configuração (Wi-Fi por perfil, ADR-065)
    avisar: Callable[[str], None] = lambda _t: None
    diagnosticar: Callable[[threading.Event], Resultado] | None = None
    _lista: contas.Lista | None = field(default=None, repr=False)

    def lista(self, nova: bool = False) -> contas.Lista:
        if self._lista is None or nova:
            self._lista = contas.listar()
        return self._lista

    def protegidas(self) -> frozenset[str]:
        return contas.protegidas(self.cadastros)

    def alvos_hive(self, maquina: bool = False) -> list[hive.Alvo]:
        lista = self.lista()
        todos = {a.chave: a for a in hive.alvos(lista)}
        saida = [hive.MAQUINA] if maquina else []
        saida.append(hive.PADRAO)
        saida += [todos[s] for s in self.alvos if s in todos]
        return saida


# Motivo, na tela, de uma conta local que não pode ser alvo (ADR-071). Códigos do ADR-021.
MOTIVO_CONTA = {
    "nativo": "Administrador nativo",
    "suporte": "Suporte",
    "dono": "conta do Bench",
    "desativada": "desativada",
    "admin": "administradora",
    "logada": "conta logada",
    "sem_perfil": "sem perfil",
    "nao_encontrada": "não encontrada",
}


def _motivo_conta(
    c: contas.Conta, lista: contas.Lista, protegidas_: frozenset[str], dono: str
) -> str:
    """Código do motivo de a conta não ser alvo, ou "". Regras do ADR-021, sem mudança."""
    alvo = hive.Alvo(c.sid, c.nome, c.carregado, c.admin)
    recusa = hive.recusa_alvo(alvo, lista, protegidas_, dono or None)
    if recusa in ("nativo", "suporte", "dono"):
        return recusa
    if c.bench:
        return "dono"
    if not c.ativo:
        return "desativada"
    if c.admin:
        return "admin"
    if c.logada:
        return "logada"
    return recusa or ""


def escondida(c: contas.Conta, protegidas_: frozenset[str]) -> bool:
    """Suporte, Gestão e Administrador nativo nunca aparecem nas listas da Configuração e da
    Manutenção (ADR-072): nunca são alvo, e mostrar só confunde."""
    nome = c.nome.lower()
    return c.nativo or nome in protegidas_ or nome in contas.RESTRITAS


def contas_locais(
    lista: contas.Lista, protegidas_: frozenset[str], dono: str = ""
) -> list[tuple[contas.Conta, str]]:
    """Contas locais, com o motivo (texto da tela) de não poderem ser alvo; "" = pode. Contas
    de domínio ou Microsoft ficam de fora (ADR-071); Suporte, Gestão e o Administrador nativo
    também (ADR-072)."""
    return [
        (c, MOTIVO_CONTA[m] if (m := _motivo_conta(c, lista, protegidas_, dono)) else "")
        for c in lista.contas
        if c.local and not escondida(c, protegidas_)
    ]


def contas_de_aluno(
    lista: contas.Lista, protegidas_: frozenset[str], dono: str = ""
) -> list[contas.Conta]:
    """Contas locais ativas não administradoras, menos Suporte, RID 500, a logada e a dona do
    processo, com as recusas do ADR-021 (sem perfil, nativo, Suporte, dono)."""
    return [c for c, motivo in contas_locais(lista, protegidas_, dono) if not motivo]


def _sem(ctx: Contexto, cadastro: bool = False) -> str:
    if not ctx.admin:
        return SEM_ADMIN
    if cadastro and ctx.cadastros is None:
        return "sem cadastros (sincronize ou entre online)"
    return ""


def _bloq(motivo: str) -> Leitura:
    return Leitura("bloqueada", motivo, "bloqueada")


def _falhas(itens: list[Any], ok: Callable[[Any], bool], msg: Callable[[Any], str]) -> Resultado:
    ruins = [i for i in itens if not ok(i)]
    if not ruins:
        return Resultado("ok")
    return Resultado("falha", "; ".join(msg(i) for i in ruins[:3]), "parcial")


# ---------------------------------------------------------------- Identificação


@dataclass
class Identificacao:
    ctx: Contexto
    id: str = "identificacao"

    def ler(self) -> Leitura:
        e = identificacao.estado()
        pedido = identificacao.normalizar(self.ctx.nome) if self.ctx.nome else ""
        if not pedido:
            if e.reinicio_pendente:
                return Leitura(
                    "aguardando_reinicio", f"Nome {e.pendente} vale depois de reiniciar."
                )
            return Leitura("feito", f"Nome atual: {e.ativo}")
        if e.ativo.upper() == pedido:
            return Leitura("feito", f"Nome atual: {e.ativo}")
        if e.pendente.upper() == pedido:
            return Leitura("aguardando_reinicio", f"Nome {pedido} vale depois de reiniciar.")
        if motivo := _sem(self.ctx) or identificacao.validar(pedido, e) or "":
            return _bloq(motivo)
        return Leitura("pendente", f"{e.ativo} → {pedido}")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        f = identificacao.renomear(self.ctx.nome)
        return (
            Resultado("reinicio", f.mensagem)
            if f.ok
            else Resultado("falha", f.mensagem, "renomear")
        )


# ---------------------------------------------------------------- Contas


def _admins_extra(lista: contas.Lista, prot: frozenset[str]) -> list[contas.Conta]:
    """Administradores além da Suporte; as restritas fixas (Gestão, ADR-036) ficam
    administradoras de propósito e não deixam a etapa pendente."""
    ignorar = set(prot) | contas.RESTRITAS
    return [
        c
        for c in lista.contas
        if c.local and c.ativo and c.admin and not c.nativo and c.nome.lower() not in ignorar
    ]


@dataclass
class Contas:
    ctx: Contexto
    id: str = "contas"

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        sup = contas.suporte_do_cadastro(self.ctx.cadastros)
        if isinstance(sup, str):
            return _bloq(sup)
        lista = self.ctx.lista(nova=True)
        prot = self.ctx.protegidas()
        falta = []
        if not contas.suporte_ok(lista, prot):
            falta.append("conta Suporte")
        if contas.gestao_cadastrada(self.ctx.cadastros) and not contas.gestao_ok(lista):
            falta.append("conta Gestão")  # ADR-069: só com as linhas em Servidores
        if extra := _admins_extra(lista, prot):
            falta.append(f"{len(extra)} conta(s) administradora(s) além da Suporte")
        if falta:
            return Leitura("pendente", "Falta: " + ", ".join(falta))
        if any(c.nativo and c.ativo for c in lista.contas):
            return Leitura("pendente", NATIVO_ATIVO, "nativo_ativo")
        return Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        """Só o que falta: Suporte e o lote não rodam de novo se já estão certos."""
        prot = self.ctx.protegidas()
        lista = self.ctx.lista(nova=True)
        if not contas.suporte_ok(lista, prot):
            f = contas.aplicar_suporte(self.ctx.cadastros)
            if not f.ok:
                return Resultado("falha", f.mensagem, "suporte")
            lista = self.ctx.lista(nova=True)
        if contas.gestao_cadastrada(self.ctx.cadastros) and not contas.gestao_ok(lista):
            f = contas.aplicar_gestao(self.ctx.cadastros)  # ADR-069: igual à Suporte
            if not f.ok:
                return Resultado("falha", f.mensagem, "gestao")
            lista = self.ctx.lista(nova=True)
        if _admins_extra(lista, prot):
            f = contas.lote("padrao", protegidas_=prot)
            if not f.ok:
                return Resultado("falha", f.mensagem, "lote_padrao")
            lista = self.ctx.lista(nova=True)
        if any(c.nativo and c.ativo for c in lista.contas):
            # ADR-017: o Bench não altera o Administrador nativo. A etapa fica pendente com o
            # aviso e não bloqueia as dependentes (o pré-requisito delas é a lista e a Suporte).
            return Resultado("parcial", NATIVO_ATIVO, "nativo_ativo")
        return Resultado("ok")

    def mudancas(self) -> str:
        lista = self.ctx.lista()
        n = len(_admins_extra(lista, self.ctx.protegidas()))
        gestao = "; a conta Gestão" if contas.gestao_cadastrada(self.ctx.cadastros) else ""
        return (
            f"aplicar a conta Suporte{gestao}; remover administrador de {n} conta(s), "
            "inclusive a conta "
            "em uso (vale na próxima entrada; depois o UAC pede a Suporte)"
        )


# ---------------------------------------------------------------- Wi-Fi


@dataclass
class Wifi:
    ctx: Contexto
    id: str = "wifi"
    cliente: Callable[[], Any] = field(default=None)  # type: ignore[assignment]

    def _redes(self) -> list[Any]:
        if self.ctx.cadastros is None:
            return []
        return list(self.ctx.cadastros.redes_para(self.ctx.unidade, self.ctx.perfil or None))

    def _abrir(self) -> Any:
        if self.cliente is not None:
            return self.cliente()
        from itc_bench.nucleo import wlan

        return wlan.Cliente()

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        redes = self._redes()
        if not redes:
            return _bloq("nenhuma rede cadastrada para o projeto e o perfil")
        try:
            with self._abrir() as c:
                linhas = wifi.situacao(redes, c, admin=True)
        except wifi.SemWifi:
            return _bloq("sem adaptador Wi-Fi")
        falta = [ln for ln in linhas if ln.situacao != "igual" and ln.situacao != "invalida"]
        return (
            Leitura("pendente", f"{len(falta)} rede(s) a instalar") if falta else Leitura("feito")
        )

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        with self._abrir() as c:
            r = wifi.instalar(self._redes(), c, cancelar=cancelar)
        if r.falhas:
            return Resultado("falha", f"{len(r.falhas)} rede(s) não instalada(s)", "wifi")
        return Resultado("ok")

    def mudancas(self) -> str:
        return f"instalar as redes do projeto e do perfil ({len(self._redes())})"


@dataclass
class WifiSenhas(Wifi):
    """Manutenção (ADR-062): só as redes do cadastro que já estão na máquina com outra senha (ou
    outra configuração) são regravadas. Rede ausente não é instalada."""

    id: str = "wifi_senhas"

    def _redes(self) -> list[Any]:
        """Sem perfil: todas as redes do projeto da unidade (ADR-065)."""
        if self.ctx.cadastros is None:
            return []
        return list(self.ctx.cadastros.redes_para(self.ctx.unidade))

    def _diferentes(self) -> list[Any]:
        with self._abrir() as c:
            linhas = wifi.situacao(self._redes(), c, admin=True)
        return [ln.rede for ln in linhas if ln.situacao == "diferente"]

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        if not self._redes():
            return _bloq("nenhuma rede cadastrada para o projeto da unidade")
        try:
            n = len(self._diferentes())
        except wifi.SemWifi:
            return _bloq("sem adaptador Wi-Fi")
        return Leitura("pendente", f"{n} rede(s) com senha a atualizar") if n else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        diferentes = self._diferentes()
        with self._abrir() as c:
            r = wifi.instalar(diferentes, c, cancelar=cancelar)
        if r.falhas:
            return Resultado("falha", f"{len(r.falhas)} rede(s) não atualizada(s)", "wifi")
        return Resultado("ok")

    def mudancas(self) -> str:
        return f"atualizar a senha das redes já instaladas ({len(self._diferentes())})"


# ---------------------------------------------------------------- Acesso remoto


def _remoto_ok(s: remoto.Situacao) -> bool:
    return s.comparacao in ("igual", "nova") and s.config in ("conferida", "")


@dataclass
class Remoto:
    ctx: Contexto
    id: str = "remoto"

    def _pendentes(self) -> tuple[list[remoto.Situacao], int]:
        sit = remoto.situacao(self.ctx.cadastros, self.ctx.unidade, admin=True)
        completos = [s for s in sit.values() if not s.falta]
        return [s for s in completos if not _remoto_ok(s)], len(completos)

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        falta, total = self._pendentes()
        if not total:
            return _bloq("nenhum programa com cadastro completo")
        if falta:
            return Leitura("pendente", "Falta: " + ", ".join(s.programa for s in falta))
        return Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        falta, _ = self._pendentes()
        instaladores.limpar(self.ctx.cadastros)
        feitos: list[remoto.Feito] = []
        for s in falta:
            if cancelar.is_set():
                break
            d = remoto.dados(self.ctx.cadastros, s.programa, self.ctx.unidade)
            if isinstance(d, str):
                feitos.append(remoto.Feito(False, d))
                continue
            if s.instalada is not None and s.comparacao in ("igual", "nova"):
                feitos.append(remoto.reconfigurar(d, avisar=self.ctx.avisar, cancelar=cancelar))
                continue
            try:
                arquivo = remoto.preparar_arquivo(d, origem=None, cancelar=cancelar)
            except instaladores.ErroInstalador as erro:
                feitos.append(remoto.Feito(False, f"{s.programa}: {erro}"))
                continue
            feitos.append(remoto.instalar(d, arquivo, avisar=self.ctx.avisar, cancelar=cancelar))
        if not all(f.ok for f in feitos):
            return _falhas(feitos, lambda f: f.ok, lambda f: f.mensagem)
        if any(f.reinicio for f in feitos):
            return Resultado("reinicio", "Reinicie para concluir o Acesso remoto.")
        return Resultado("ok")


# ---------------------------------------------------------------- Programas


@dataclass
class Programas:
    ctx: Contexto
    id: str = "programas"

    def _itens(self) -> list[programas.Item]:
        # ADR-074: só os programas do projeto da unidade (e os gerais) que valem para o perfil.
        return itens_programas(self.ctx.cadastros, self.ctx.unidade, self.ctx.perfil or None)

    def _falta(self) -> list[programas.Item]:
        linhas, _ = programas.situacao(self._itens())
        return [ln.item for ln in linhas if ln.situacao in ("nao_instalado", "desatualizado")]

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        if not self._itens():
            return Leitura("feito", "Nenhum programa para o projeto e o perfil.")
        falta = self._falta()
        return (
            Leitura("pendente", f"{len(falta)} programa(s) a instalar")
            if falta
            else Leitura("feito")
        )

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        rs = programas.instalar(self._falta(), avisar=self.ctx.avisar, cancelar=cancelar)
        ruins = [r for r in rs if r.estado not in ("ok", "reinicio")]
        if ruins:
            return Resultado("falha", "; ".join(r.mensagem for r in ruins[:3]), "parcial")
        if any(r.estado == "reinicio" for r in rs):
            return Resultado("reinicio", "Algum programa pede reinício.")
        return Resultado("ok")

    def mudancas(self) -> str:
        return f"instalar {len(self._falta())} programa(s)"


# ---------------------------------------------------------------- Remover pré-instalados


@dataclass
class Preinstalados:
    ctx: Contexto
    id: str = "preinstalados"

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        n = len(self._presentes())
        if n:
            return Leitura("pendente", f"{n} app(s) da Microsoft a remover")
        if mcafee.encontrados():  # ADR-068: só o técnico remove, pelo MCPR
            return Leitura("pendente", mcafee.AVISO_ETAPA)
        return Leitura("feito")

    def _presentes(self) -> list[str]:
        """Appx da lista fechada, o PowerShell ISE (ADR-061) e o Office de fábrica (ADR-063)."""
        nomes = desinstalar.appx_presentes()
        if desinstalar.ise_instalado():
            nomes = [*nomes, desinstalar.NOME_ISE]
        return nomes + [desinstalar.NOME_OFFICE[p] for p in desinstalar.office_presentes()]

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        fs = desinstalar.remover_appx(desinstalar.appx_presentes(), cancelar=cancelar)
        if desinstalar.ise_instalado():
            fs.append(desinstalar.remover_ise(cancelar=cancelar))
        fs += desinstalar.remover_office(desinstalar.office_presentes(), cancelar=cancelar)
        r = _falhas(fs, lambda f: f.estado in ("ok", "pulado"), lambda f: f.mensagem)
        if r.estado == "ok" and mcafee.encontrados():
            # ADR-068: o MCPR pede o técnico; a etapa avisa e não bloqueia as seguintes.
            return Resultado("parcial", mcafee.AVISO_ETAPA, "mcafee")
        return r

    def mudancas(self) -> str:
        return "remover para todas as contas: " + ", ".join(self._presentes())


# ---------------------------------------------------------------- Políticas e USB


@dataclass
class Politicas:
    ctx: Contexto
    usb: bool = False
    id: str = "politicas"

    def __post_init__(self) -> None:
        if self.usb:
            self.id = "usb"

    def _ids(self) -> list[str]:
        if self.usb:
            return [perfis.POLITICA_USB]
        return [*perfis.POLITICAS_USUARIO, *perfis.POLITICAS_MAQUINA]

    def _alvos(self) -> list[hive.Alvo]:
        return self.ctx.alvos_hive(maquina=not self.usb)

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        alvos_ = self._alvos()
        leitura = politicas.ler(alvos_, descarregados=True)
        falta = 0
        for pid in self._ids():
            pol = politicas.POR_ID[pid]
            for a in alvos_:
                if a.escopo in pol.escopos and leitura.situacao.get((pid, a.chave)) != "aplicada":
                    falta += 1
        return Leitura("pendente", f"{falta} item(ns) a aplicar") if falta else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        fs = politicas.aplicar(
            "aplicar",
            self._ids(),
            self._alvos(),
            protegidas_=self.ctx.protegidas(),
            cancelar=cancelar,
            avisar=self.ctx.avisar,
        )
        return _falhas(fs, lambda f: f.ok, lambda f: f"{f.alvo.rotulo}: {f.mensagem}")

    def mudancas(self) -> str:
        n = len(self.ctx.alvos)
        if self.usb:
            return f"bloquear pendrive em Contas futuras e em {n} conta(s) de aluno"
        return f"{len(self._ids())} políticas na máquina, em Contas futuras e em {n} conta(s)"


# ---------------------------------------------------------------- Proteção do login


@dataclass
class Protecao:
    ctx: Contexto
    id: str = "protecao"

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        s = protecao.situacao()
        if any(b.arquivo == "trocado" or b.ifeo == "depurador" for b in s.binarios.values()):
            return _bloq("arquivo trocado ou depurador: resolva na tela Proteção do login")
        falta = s.alertas() + ([] if s.atalho == "desligado" else ["atalho Shift 5x"])
        return Leitura("pendente", "; ".join(falta)) if falta else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        fs = protecao.alterar(True, cancelar=cancelar)
        ok, msg = protecao.atalho_login(True)
        r = _falhas(fs, lambda f: f.ok, lambda f: f.mensagem)
        if r.estado != "ok":
            return r
        return Resultado("ok") if ok else Resultado("falha", msg, "atalho")


# ---------------------------------------------------------------- Papel de parede


@dataclass
class Papel:
    ctx: Contexto
    id: str = "papel"

    def _linha(self) -> Any:
        ls = papel_de_parede.da_unidade(self.ctx.cadastros, self.ctx.unidade)
        return ls[0] if len(ls) == 1 else None

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx, cadastro=True):
            return _bloq(motivo)
        linha = self._linha()
        if linha is None:
            return _bloq("cadastre uma (e só uma) imagem ativa de papel de parede da unidade")
        sit = papel_de_parede.ler(self.ctx.alvos_hive(), linha, descarregados=True)
        falta = [k for k, s in sit.items() if s.estado != "aplicado"]
        return Leitura("pendente", f"{len(falta)} alvo(s)") if falta else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        linha = self._linha()
        if papel_de_parede.caminho(linha) is None:
            papel_de_parede.obter(linha, cancelar=cancelar)
        fs = papel_de_parede.aplicar(
            "aplicar",
            self.ctx.alvos_hive(),
            linha=linha,
            estilo=perfis.ESTILO_PAPEL,
            protegidas_=self.ctx.protegidas(),
            cancelar=cancelar,
            avisar=self.ctx.avisar,
        )
        return _falhas(fs, lambda f: f.ok, lambda f: f"{f.alvo.rotulo}: {f.mensagem}")


# ---------------------------------------------------------------- Mouse e teclado


@dataclass
class Mouse:
    ctx: Contexto
    id: str = "mouse"

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        sit = aparencia.ler(self.ctx.alvos_hive(), descarregados=True)
        falta = [
            k for k, s in sit.items() if k[0] in perfis.MOUSE and s.valor != perfis.MOUSE[k[0]]
        ]
        return Leitura("pendente", f"{len(falta)} alvo(s)") if falta else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        fs = aparencia.aplicar(
            "aplicar",
            perfis.MOUSE,
            self.ctx.alvos_hive(),
            protegidas_=self.ctx.protegidas(),
            cancelar=cancelar,
            avisar=self.ctx.avisar,
        )
        return _falhas(fs, lambda f: f.ok, lambda f: f"{f.alvo.rotulo}: {f.mensagem}")


# ---------------------------------------------------------------- Energia


@dataclass
class Energia:
    """Etapa 10 (planos finais) e, com `ENERGIA_INICIO`, etapa 1 ("nunca desligar")."""

    ctx: Contexto
    id: str = "energia"
    valores: dict[tuple[str, str], int] = field(default_factory=lambda: dict(perfis.ENERGIA))

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        s = energia.situacao()
        falta = [k for k, seg in self.valores.items() if s.valores[k].atual != seg]  # type: ignore[index]
        return Leitura("pendente", f"{len(falta)} ajuste(s)") if falta else Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        fs = energia.tempos(self.valores, cancelar=cancelar)  # type: ignore[arg-type]
        return _falhas(fs, lambda f: f.ok, lambda f: f.mensagem)


# ---------------------------------------------------------------- Limpeza e Diagnóstico


@dataclass
class Limpeza:
    """Sem leitura de "já limpo": roda uma vez por preparação (ADR-023)."""

    ctx: Contexto
    id: str = "limpeza"
    feita: bool = False

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        return Leitura("feito") if self.feita else Leitura("pendente")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        itens = limpeza.limpar(perfis.LIMPEZA)
        self.feita = True
        nao = [i for i in itens if not i.ok]
        if nao:
            return Resultado(
                "falha", "Não limpo: " + ", ".join(limpeza.NOMES[i.id] for i in nao), "parcial"
            )
        return Resultado("ok")


@dataclass
class Diagnostico:
    ctx: Contexto
    id: str = "diagnostico"
    feita: bool = False

    def ler(self) -> Leitura:
        if self.ctx.diagnosticar is None:
            return _bloq("diagnóstico indisponível")
        return Leitura("feito") if self.feita else Leitura("pendente")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        if self.ctx.diagnosticar is None:
            return Resultado("falha", "Diagnóstico indisponível.", "sem_diagnostico")
        r = self.ctx.diagnosticar(cancelar)
        self.feita = r.estado == "ok"
        return r


def ocultas(cadastros: Cadastros | None, unidade: str | None, perfil: str = "") -> frozenset[str]:
    """Etapas que a Preparação não mostra nem roda (ADR-057): 10. Papel de parede quando a
    unidade da máquina não tem papel cadastrado. Sem cadastro, nada some (a etapa fica
    bloqueada pedindo o cadastro, como antes)."""
    fora = set()
    if cadastros is not None and not papel_de_parede.da_unidade(cadastros, unidade):
        fora.add("papel")
    # ADR-065: sem rede para o projeto e o perfil (ou em bancada), a 3 também some.
    if cadastros is not None and not cadastros.redes_para(unidade, perfil or None):
        fora.add("wifi")
    # ADR-074: sem programa para o projeto e o perfil, a 6 também some.
    if cadastros is not None and not itens_programas(cadastros, unidade, perfil or None):
        fora.add("programas")
    return frozenset(fora)


def itens_programas(
    cadastros: Cadastros | None, unidade: str | None, perfil: str | None
) -> list[programas.Item]:
    """Programas que a etapa 6 instala nesta máquina: categoria Programas, sem bloqueio e
    silenciosos, do projeto da unidade (ou gerais) e do perfil (ADR-074)."""
    return [
        i
        for i in programas.listar(cadastros, unidade, perfil)
        if i.linha.categoria == "Programas" and not i.bloqueio and not i.interativo
    ]


def ocultas_manutencao() -> frozenset[str]:
    """Manutenção: 4. Remover Steam só aparece com a Steam instalada (ADR-064)."""
    return frozenset() if steam.instalada() else frozenset({"steam"})


# ---------------------------------------------------------------- Limpeza de usuários e Steam


@dataclass
class LimpezaUsuarios:
    """Manutenção, etapa 1 (ADR-064): arquivos que pesam nas contas de aluno marcadas, pelo
    trecho da limpeza de contas (ADR-042). Configurações, políticas e o registro da conta
    ficam."""

    ctx: Contexto
    id: str = "limpeza_usuarios"
    _previa: list[Any] = field(default_factory=list, repr=False)

    def _alvos(self) -> list[contas.Conta]:
        por_sid = {c.sid: c for c in self.ctx.lista().contas}
        return [por_sid[s] for s in self.ctx.alvos if s in por_sid]

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        alvos_ = self._alvos()
        if not alvos_:
            return _bloq("marque as contas de aluno a limpar")
        self._previa = limpeza.previa_contas(
            alvos_, self.ctx.protegidas(), categorias=CATEGORIAS_LIMPEZA
        )
        total = sum(i.bytes for i in self._previa)
        if not total:
            return Leitura("feito")
        n = len({i.sid for i in self._previa if i.bytes})
        return Leitura("pendente", f"{limpeza.tamanho(total)} em {n} conta(s)")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        itens = limpeza.limpar_contas(
            self._alvos(), self.ctx.protegidas(), categorias=CATEGORIAS_LIMPEZA
        )
        recusadas = [i for i in itens if i.codigo]
        em_uso = sum(i.em_uso for i in itens)
        if recusadas:
            return Resultado("falha", "; ".join(i.motivo for i in recusadas[:3]), "parcial")
        if em_uso:
            return Resultado("falha", f"{em_uso} arquivo(s) em uso ficaram", "parcial")
        return Resultado("ok")

    def mudancas(self) -> str:
        nomes = {c.sid: c.nome for c in self._alvos()}
        por_conta: dict[str, int] = {}
        for i in self._previa:
            por_conta[i.sid] = por_conta.get(i.sid, 0) + i.bytes
        partes = [f"{nomes.get(s, '?')} {limpeza.tamanho(b)}" for s, b in por_conta.items() if b]
        return "apagar para sempre (sem lixeira): " + (", ".join(partes) or "nada")


CATEGORIAS_LIMPEZA = tuple(c for c, _ in limpeza.CATEGORIAS_MANUTENCAO)


@dataclass
class Steam:
    """Manutenção, etapa 4 (ADR-064): desinstala a Steam com os jogos, se estiver instalada."""

    ctx: Contexto
    id: str = "steam"

    def ler(self) -> Leitura:
        if motivo := _sem(self.ctx):
            return _bloq(motivo)
        if steam.instalada():
            return Leitura("pendente", "Steam e jogos instalados")
        return Leitura("feito")

    def aplicar(self, cancelar: threading.Event) -> Resultado:
        ok, mensagem = steam.remover(cancelar=cancelar)
        return Resultado("ok") if ok else Resultado("falha", mensagem, "steam")

    def mudancas(self) -> str:
        return "desinstalar a Steam, com todos os jogos e usuários dela"


def montar(ctx: Contexto) -> list[Etapa]:
    """Configuração (ADR-062): todas as etapas, na ordem de `perfis.CONFIGURACAO`; o andamento
    diz quais rodam. Identificação, Mouse e teclado e Limpeza ficam só nas telas delas."""
    lista: list[Etapa] = [
        Energia(ctx, id="energia_inicio", valores=dict(perfis.ENERGIA_INICIO)),
        Preinstalados(ctx),
        Wifi(ctx),
        Papel(ctx),
        Remoto(ctx),
        Programas(ctx),
        Politicas(ctx),
        Politicas(ctx, usb=True),
        Protecao(ctx),
        Energia(ctx),
        Contas(ctx),
        Diagnostico(ctx),
    ]
    if tuple(e.id for e in lista) != perfis.CONFIGURACAO.ordem:
        raise RuntimeError("Etapas fora da ordem de perfis.CONFIGURACAO.")
    return lista


def montar_manutencao(ctx: Contexto) -> list[Etapa]:
    """Manutenção (ADR-062, ADR-064), na ordem de `perfis.MANUTENCAO`; sem perfil."""
    lista: list[Etapa] = [LimpezaUsuarios(ctx), WifiSenhas(ctx), Diagnostico(ctx), Steam(ctx)]
    if tuple(e.id for e in lista) != perfis.MANUTENCAO.ordem:
        raise RuntimeError("Etapas fora da ordem de perfis.MANUTENCAO.")
    return lista
