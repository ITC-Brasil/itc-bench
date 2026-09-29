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


def test_session_user_of_1_2_reaches_the_prompt_and_the_executing_account_does_not():
    from test_normalizacao import v12

    normalized, avisos = normalizacao.normalizar(v12())
    user = prompt.montar(normalized, avisos, [])[1]["content"]
    # JSON escapes the backslash of DOMAIN\user.
    assert r'"usuarioSessao":"TESTE-NB-11\\aluno01"' in user
    assert "tecnico.admin" not in user


def test_system_prompt_limits_the_report_size():
    system = messages([])[0]["content"]
    for limit in ("No máximo 4 hipóteses", "uma ou duas linhas", "cerca de 700 palavras", "não\nrepetem o que já está no Resumo"):
        assert limit in system


def test_system_prompt_carries_the_writing_and_ticket_rules():
    system = messages([])[0]["content"]
    for rule in (
        "Escreva só em português",
        'Não têm "Ação sugerida" própria e não são ligados a\n   outros eventos',
        "Aparecem só em\n   `## Correlação com o histórico`, numa frase curta, e nunca no chamado",
        "Nunca afirma um sintoma ou uma\n  causa que a ação sugerida ainda pede para confirmar",
        "no máximo cerca de 120 palavras",
    ):
        assert rule in system
