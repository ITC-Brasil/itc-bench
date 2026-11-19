"""Nova tela Início (ADR-073): regras de cor e limite, parser de CPU e memória, estado vazio dos
alertas e a tela montando nos dois modos, com e sem dado. Nada lê o Windows."""

import itertools
import json

import perfis_teste
import pytest
from PySide6.QtWidgets import QApplication

from itc_bench.servicos import executor, inicio
from itc_bench.servicos import preparacao as prep
from itc_bench.ui import inicio as ui_inicio
from itc_bench.ui import tarefa, tema

# O conftest troca carregar por um falso nas telas; aqui a leitura (falsa) é o teste.
CARREGAR = ui_inicio.PainelInicio.carregar

GB = 1 << 30
MAQUINA = inicio.Maquina(
    "Lenovo", "82UM", "S1", "Professional", "26H2", "26300", 100 * GB, 50 * GB, 98, True,
    nome="UM01-EST07", cpu_nome="12th Gen Intel(R) Core(TM) i5-1235U", cpu_nucleos=10,
    cpu_threads=12, cpu_uso=18, mem_total=8 * GB, mem_uso=62, mem_tipo="DDR4", mem_slots=2,
    mem_modulos=1,
)  # fmt: skip


def _rodar(dados: dict):
    def rodar(script, **_k):
        return executor.Resultado(0, json.dumps(dados), "", 0.1, False)

    return rodar


# ---------------------------------------------------------------- regras


@pytest.mark.parametrize(
    ("usado", "esperado"),
    [(None, "normal"), (0.5, "normal"), (0.849, "normal"), (0.85, "atencao"), (0.9, "atencao"),
     (0.91, "critico"), (1.0, "critico")],
)  # fmt: skip
def test_nivel_disco(usado, esperado):
    assert inicio.nivel_disco(usado) == esperado


def test_disco_critico_usa_o_mesmo_limite_do_alerta():
    """O cartão fica "Quase cheio" exatamente quando o alerta de disco aparece."""
    for livre in (0.05, 0.0999, 0.10, 0.2):
        alerta = inicio.alertas(
            protecao_=None, politicas_faltando=None, nome_pendente=False, suporte=None,
            cadastros=None, fila=0, disco_livre=livre,
        )  # fmt: skip
        tem_alerta = any(a.tela == "limpeza" for a in alerta)
        assert tem_alerta == (inicio.nivel_disco(1 - livre) == "critico")


@pytest.mark.parametrize(
    ("carga", "tomada", "esperado"),
    [(None, None, "normal"), (98, True, "normal"), (5, True, "normal"), (50, False, "normal"),
     (29, False, "atencao"), (15, False, "atencao"), (14, False, "critico"), (0, False, "critico")],
)  # fmt: skip
def test_nivel_bateria(carga, tomada, esperado):
    assert inicio.nivel_bateria(carga, tomada) == esperado


@pytest.mark.parametrize(
    ("nome", "curto"),
    [
        ("12th Gen Intel(R) Core(TM) i5-1235U", "Core i5-1235U"),
        ("Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz", "Core i7-8550U"),
        ("AMD Ryzen 5 5500U with Radeon Graphics", "Ryzen 5 5500U"),
        ("Intel(R) Celeron(R) N4020 CPU @ 1.10GHz", "Celeron N4020"),
        ("", ""),
    ],
)
def test_cpu_curto(nome, curto):
    assert inicio.cpu_curto(nome) == curto


def test_tipo_memoria():
    assert inicio.tipo_memoria(26) == "DDR4"
    assert inicio.tipo_memoria(35) == "LPDDR5"
    assert inicio.tipo_memoria(0) == "" and inicio.tipo_memoria(None) == ""


# ---------------------------------------------------------------- parser


def test_parser_dos_dados_novos():
    m = inicio.maquina(
        rodar=_rodar(
            {
                "fabricante": "Lenovo",
                "modelo": "82UM",
                "disco_total": 100,
                "disco_livre": 5,
                "bateria": 98,
                "na_tomada": True,
                "nome": "UM01-EST07",
                "cpu_nome": "12th Gen Intel(R) Core(TM) i5-1235U",
                "cpu_nucleos": 10,
                "cpu_threads": 12,
                "cpu_uso": 18,
                "mem_total": 8 * GB,
                "mem_uso": 62,
                "mem_tipo": 26,
                "mem_slots": 2,
                "mem_modulos": 1,
            }
        )
    )
    assert (m.processador, m.cpu_nucleos, m.cpu_threads, m.cpu_uso) == ("Core i5-1235U", 10, 12, 18)
    assert (m.mem_total, m.mem_uso, m.mem_tipo, m.mem_slots, m.mem_modulos) == (
        8 * GB, 62, "DDR4", 2, 1
    )  # fmt: skip
    assert m.nome == "UM01-EST07" and m.disco_usado == pytest.approx(0.95)


def test_parser_recusa_valores_fora_da_faixa():
    """Saída estranha não vira número na tela: fica "—"."""
    m = inicio.maquina(
        rodar=_rodar(
            {
                "bateria": 250,
                "cpu_nucleos": 0,
                "cpu_threads": "x",
                "cpu_uso": -1,
                "mem_total": -5,
                "mem_uso": 101,
                "mem_tipo": 999,
                "mem_slots": True,
                "nome": "NOME-MUITO-LONGO-DEMAIS",
            }
        )
    )
    assert m.bateria is None and m.cpu_nucleos is None and m.cpu_threads is None
    assert m.cpu_uso is None and m.mem_total is None and m.mem_uso is None
    assert m.mem_tipo == "" and m.mem_slots is None
    assert len(m.nome) == 15


def test_parser_sem_os_campos_novos_continua_valendo():
    """Saída antiga (sem CPU e memória): tudo novo fica vazio, sem erro."""
    m = inicio.maquina(rodar=_rodar({"fabricante": "Dell", "modelo": "X"}))
    assert m.cpu_nome == "" and m.cpu_nucleos is None and m.mem_total is None and m.nome == ""


def test_trecho_so_le_e_sem_nome_de_usuario():
    texto = (inicio.RECURSOS / "ler.ps1").read_text("utf-8")
    for proibido in ("Set-", "New-Item", "UserName", "Invoke-Expression"):
        assert proibido not in texto
    # Só remove o XML temporário do powercfg, de nome aleatório (ADR-073).
    remocoes = [linha for linha in texto.splitlines() if "Remove-" in linha]
    assert remocoes and all("Remove-Item -LiteralPath $arq" in linha for linha in remocoes)
    for classe in ("Win32_Processor", "Win32_PhysicalMemory", "Win32_PhysicalMemoryArray"):
        assert classe in texto


# ---------------------------------------------------------------- tela


@pytest.fixture(params=["claro", "escuro"])
def modo(request):
    app = QApplication.instance()
    tema.aplicar(app, request.param)
    yield request.param
    tema.trocar(app, "claro")


def _painel(qtbot, monkeypatch, painel: inicio.Painel, andamento=None, admin=True):
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(painel))
    monkeypatch.setattr(ui_inicio.PainelInicio, "carregar", CARREGAR)
    perfil = perfis_teste.POR_ID["aluno"]
    w = ui_inicio.PainelInicio(
        admin, lambda: None, lambda: "UM01", lambda: 0, lambda: perfil, lambda: andamento,
        obter_tecnico=lambda: "tecnico.teste",
    )  # fmt: skip
    qtbot.addWidget(w)
    w.carregar(forcar=True)
    return w


def test_tela_sem_leitura_da_maquina_mostra_tracos(qtbot, monkeypatch, modo):
    w = _painel(qtbot, monkeypatch, inicio.Painel(None, (), ("maquina",)))
    assert w.modelo.text() == "—" and w.campos["serie"].text() == "—"
    assert w.campos["tecnico"].text() == "tecnico.teste"
    assert w.disco_livre.text() == "—" and w.cpu_modelo.text() == "—"
    assert w.mem_total.text() == "—" and w.bateria_carga.text() == "—"
    assert not w.barra_cpu.isVisibleTo(w) and not w.barra_mem.isVisibleTo(w)
    assert "Não lido: maquina." in w.aviso.text()
    assert w.selo_estado.text() == "Leitura incompleta"


def test_estado_vazio_dos_alertas(qtbot, monkeypatch, modo):
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    assert w.vazio.isVisibleTo(w) and not w.linhas_alerta
    assert not w.contador.isVisibleTo(w)
    assert w.selo_estado.text() == "Tudo certo"
    assert w.selo_estado.property("nivel") == "ok"


def test_alertas_com_botao_da_tela_e_disco_cheio(qtbot, monkeypatch, modo):
    cheia = inicio.Maquina(**{**MAQUINA.__dict__, "disco_livre": 4 * GB})
    alertas = (
        inicio.Alerta("atencao", "Menos de 10% de disco livre: use a Limpeza", "limpeza"),
        inicio.Alerta("critico", "Proteção do login: utilman trocado", "protecao"),
    )
    w = _painel(qtbot, monkeypatch, inicio.Painel(cheia, alertas))
    abertas = []
    w.abrir.connect(abertas.append)
    assert len(w.linhas_alerta) == 2 and w.contador.text() == "2"
    assert w.selo_estado.text() == "2 alertas" and w.selo_estado.property("nivel") == "critico"
    from PySide6.QtWidgets import QLabel, QPushButton

    textos = [lb.text() for lb in w.linhas_alerta[0].findChildren(QLabel)]
    assert "Disco quase cheio" in textos and any(t.startswith("Só 4,0 GB livres") for t in textos)
    assert "utilman trocado" in [lb.text() for lb in w.linhas_alerta[1].findChildren(QLabel)]
    botoes = [b for linha in w.linhas_alerta for b in linha.findChildren(QPushButton)]
    assert [b.text() for b in botoes] == ["Limpar temporários", "Abrir"]
    for b in botoes:
        b.click()
    assert abertas == ["limpeza", "protecao"]
    assert w.disco_estado.text() == "Quase cheio"
    assert w.cartao_disco.property("nivel") == "critico"


def test_indicadores_com_dados(qtbot, monkeypatch, modo):
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    assert w.modelo.text() == "Lenovo 82UM" and w.campos["nome"].text() == "UM01-EST07"
    assert (
        w.cpu_modelo.text() == "Core i5-1235U" and w.cpu_nucleos.text() == "10 núcleos · 12 threads"
    )
    assert w.cpu_uso.text() == "18% de uso agora"
    assert w.mem_total.text() == "8 GB" and w.mem_uso.text() == "62% em uso"
    assert w.mem_detalhe.text() == "DDR4 · 2 slots, 1 livre"
    assert w.bateria_carga.text() == "98%" and w.bateria_estado.text() == "Na tomada"
    assert w.anel_disco.texto == "50%" and w.disco_estado.text() == "Normal"


def test_configuracao_com_andamento_lido(qtbot, monkeypatch, modo):
    perfil = perfis_teste.POR_ID["aluno"]
    a = prep.novo(perfil)
    for i, e in enumerate(a.etapas):
        a.situacao[e] = prep.Leitura("pendente" if i < 5 else "feito")
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()), andamento=a)
    total = len(a.etapas)
    assert w.anel_prep.texto == f"{total - 5}/{total}"
    assert w.prep.text() == f"{total - 5} de {total} etapas feitas"
    assert len(w.linhas_pendentes) == ui_inicio.PENDENTES_VISIVEIS + 1  # 3 e "e mais 2"


def test_sem_admin_avisa_e_inventario_desativado(qtbot, monkeypatch, modo):
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()), admin=False)
    assert "Sem administrador" in w.aviso.text()
    assert not w.b_inventario.isEnabled()


def test_botao_de_ajuda_emite_sinal(qtbot, monkeypatch):
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    with qtbot.waitSignal(w.ajuda, timeout=500):
        w.b_ajuda.click()


def test_quatro_colunas_iguais(qtbot, monkeypatch):
    """A divisão da coluna da direita desce reta: as três faixas usam as mesmas colunas."""
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    w.resize(1086, 1100)
    w.show()
    qtbot.waitExposed(w)
    from PySide6.QtWidgets import QFrame

    cartoes = [c for c in w.findChildren(QFrame) if c.objectName() == "inicioCartao"]
    bordas_direitas = {c.geometry().right() for c in cartoes}
    assert len(bordas_direitas) == 4  # 4 colunas: toda borda direita é uma das quatro
    lefts = sorted({c.geometry().left() for c in cartoes})
    larguras = [b - a for a, b in itertools.pairwise(lefts)]
    assert max(larguras) - min(larguras) <= 2


# ---------------------------------------------------------------- Windows 10/11 e saúde da bateria


@pytest.mark.parametrize(
    ("edicao", "build", "esperado"),
    [
        ("Professional", "26300", "Windows 11 Pro 26H2 build 26300"),
        ("Professional", "22000", "Windows 11 Pro 26H2 build 22000"),
        ("Professional", "19045", "Windows 10 Pro 26H2 build 19045"),
        ("Core", "19045", "Windows 10 Home 26H2 build 19045"),
        ("Education", "", "Windows Education 26H2"),
    ],
)
def test_windows_10_ou_11_pelo_build(edicao, build, esperado):
    assert inicio.Maquina(edicao=edicao, versao="26H2", build=build).windows == esperado


@pytest.mark.parametrize(
    ("projeto", "cheia", "saude"),
    [(50000, 46000, 92), (50000, 52000, 100), (None, 46000, None), (50000, None, None)],
)
def test_saude_da_bateria(projeto, cheia, saude):
    m = inicio.Maquina(bateria_projeto=projeto, bateria_cheia=cheia)
    assert m.bateria_saude == saude


@pytest.mark.parametrize(
    ("saude", "esperado"),
    [(None, "normal"), (100, "normal"), (80, "normal"), (79, "atencao"), (50, "atencao"),
     (49, "critico")],
)  # fmt: skip
def test_nivel_saude(saude, esperado):
    assert inicio.nivel_saude(saude) == esperado


def test_parser_da_saude_recusa_fora_da_faixa():
    m = inicio.maquina(rodar=_rodar({"bateria_projeto": 0, "bateria_cheia": 46000}))
    assert m.bateria_projeto is None and m.bateria_saude is None
    m = inicio.maquina(rodar=_rodar({"bateria_projeto": 50000, "bateria_cheia": 35000}))
    assert m.bateria_saude == 70


def test_trecho_le_a_saude_pelo_powercfg_e_wmi_de_reserva():
    texto = (inicio.RECURSOS / "ler.ps1").read_text("utf-8")
    assert "SystemDirectory) 'powercfg.exe') /batteryreport /xml /output $arq" in texto
    assert "[guid]::NewGuid()" in texto and "XmlResolver = $null" in texto
    assert "BatteryStaticData" in texto and "BatteryFullChargedCapacity" in texto


@pytest.mark.parametrize(
    ("ciclos", "texto"), [(45, "Saúde: 93% · 45 ciclos"), (1, "Saúde: 93% · 1 ciclo")]
)
def test_cartao_mostra_os_ciclos(qtbot, monkeypatch, ciclos, texto):
    m = inicio.Maquina(
        **{
            **MAQUINA.__dict__,
            "bateria_projeto": 38000,
            "bateria_cheia": 35260,
            "bateria_ciclos": ciclos,
        }
    )
    w = _painel(qtbot, monkeypatch, inicio.Painel(m, ()))
    assert w.bateria_saude.text() == texto


def test_parser_dos_ciclos():
    m = inicio.maquina(rodar=_rodar({"bateria_ciclos": 45}))
    assert m.bateria_ciclos == 45
    assert inicio.maquina(rodar=_rodar({"bateria_ciclos": -1})).bateria_ciclos is None


def test_cartao_mostra_a_saude(qtbot, monkeypatch, modo):
    gasta = inicio.Maquina(**{**MAQUINA.__dict__, "bateria_projeto": 50000, "bateria_cheia": 20000})
    w = _painel(qtbot, monkeypatch, inicio.Painel(gasta, ()))
    assert w.bateria_saude.text() == "Saúde: 40%"
    assert w.bateria_saude.property("nivel") == "critico"
    w2 = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    assert w2.bateria_saude.text() == "Saúde: —"  # sem a capacidade de fábrica (sem admin)
    sem = inicio.Maquina(**{**MAQUINA.__dict__, "bateria": None, "na_tomada": None})
    w3 = _painel(qtbot, monkeypatch, inicio.Painel(sem, ()))
    assert not w3.bateria_saude.isVisibleTo(w3)  # desktop sem bateria: sem linha de saúde


# ------------------------------------------------------- leitura automática da Configuração


def test_inicio_pede_a_leitura_e_mostra_lendo(qtbot, monkeypatch):
    pedidos = []
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(inicio.Painel(MAQUINA, ())))
    monkeypatch.setattr(ui_inicio.PainelInicio, "carregar", CARREGAR)
    perfil = perfis_teste.POR_ID["aluno"]
    w = ui_inicio.PainelInicio(
        True, lambda: None, lambda: "UM01", lambda: 0, lambda: perfil, lambda: None,
        ler_preparacao=lambda: pedidos.append(1) or True, obter_lendo=lambda: True,
    )  # fmt: skip
    qtbot.addWidget(w)
    w.carregar(forcar=True)
    assert pedidos == [1]
    assert w.prep.text() == "Lendo a situação das etapas…" and w.anel_prep.texto == "…"


def test_inicio_nao_pede_leitura_quando_ja_leu(qtbot, monkeypatch):
    pedidos = []
    perfil = perfis_teste.POR_ID["aluno"]
    a = prep.novo(perfil)
    monkeypatch.setattr(tarefa, "iniciar", lambda f, ok, falha: ok(inicio.Painel(MAQUINA, ())))
    monkeypatch.setattr(ui_inicio.PainelInicio, "carregar", CARREGAR)
    w = ui_inicio.PainelInicio(
        True, lambda: None, lambda: "UM01", lambda: 0, lambda: perfil, lambda: a,
        ler_preparacao=lambda: pedidos.append(1) or True,
    )  # fmt: skip
    qtbot.addWidget(w)
    w.carregar(forcar=True)
    assert pedidos == []


def test_inicio_sem_leitura_explica_como_ler(qtbot, monkeypatch):
    w = _painel(qtbot, monkeypatch, inicio.Painel(MAQUINA, ()))
    assert w.prep.text() == "Situação não lida. Abra a configuração e use Ler situação."
