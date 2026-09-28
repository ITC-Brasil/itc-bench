import json
from pathlib import Path

from app import normalizacao, prompt

FIXTURES = Path(__file__).parent / "fixtures"


def messages(history):
    normalized, avisos = normalizacao.normalizar(json.loads((FIXTURES / "sessao-1.0.json").read_text("utf-8")))
    return prompt.montar(normalized, avisos, history)


def test_system_prompt_carries_the_rules():
    system = messages([])[0]
    assert system["role"] == "system"
    for rule in ("nunca decide nem executa", "`null` é **não informado**", "`fonteOficial: false`",
                 "Ausência de erro no SMART", "169.254.x.x", "`percentualDesgaste`", "somente** com um objeto JSON"):
        assert rule in system["content"]


def test_without_history():
    user = messages([])[1]["content"]
    assert user.endswith("## Histórico do hostname\n\n" + prompt.SEM_HISTORICO)
    assert normalizacao.AVISO_PENDRIVE_1_0 in user


def test_with_history():
    history = [{"sessao_id": "anterior", "resumo": {"totalGruposEventos": 9}}]
    user = messages(history)[1]["content"]
    assert user.endswith('## Histórico do hostname\n\n[{"sessao_id":"anterior","resumo":{"totalGruposEventos":9}}]')


def test_identifiers_stay_out_of_the_prompt():
    user = messages([])[1]["content"]
    for secret in ("aluno01", "XXXXXXXX", "00-00-00-00-00-00", "usuarioExecucao", "numeroSerie", "macAddress"):
        assert secret not in user
    assert "TESTE-NB-10" in user
