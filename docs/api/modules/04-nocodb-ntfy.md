# Módulo 04 — NocoDB e ntfy

**Branch:** `module/04-nocodb-ntfy` (a partir da `module/03-ai-report`) · **Data:**
2026-09-28 · **Escopo:** `PROMPT_CLAUDE_CODE.md` §6.6, §6.7 e §15, Módulo 04

Liga os dois canais de saída que não podem atrasar o pendrive: o espelho dos relatórios
no NocoDB, só de ida e com reenvio de pendentes (TA-ADR-005), e os alertas ntfy com
limitação de repetição. Os dois rodam fora do caminho da requisição, com o estado no
SQLite (TA-ADR-024). Nenhuma rota nova; o `pendrive/` não foi alterado.

## O que foi implementado

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `api/app/config.py` | `nocodb_enabled`, `nocodb_url`, `nocodb_token` (`SecretStr`), `nocodb_table_id`, `nocodb_retry_seconds = 300` (mínimo 10); `ntfy_enabled`, `ntfy_url`, `ntfy_topic`, `ntfy_token` (`SecretStr`), `ntfy_repeat_minutes = 60`, `ntfy_failure_threshold_per_hour = 5` |
| `api/.env.example` | Novas `NOCODB_RETRY_SECONDS=300`, `NTFY_ENABLED=false`, `NTFY_REPEAT_MINUTES=60`, `NTFY_FAILURE_THRESHOLD_PER_HOUR=5` |
| `api/app/migrations/0003_20260928_espelho_alertas.sql` | `relatorios` ganha `espelho_tentativas`, `espelho_erro`, `espelho_em` e o índice parcial `relatorios_espelho_pendente`; tabela `alertas` (`chave`, `ultimo_envio`, `suprimidos`) |
| `api/app/services/nocodb.py` | `configurado()`, `registro()`, `espelhar_pendentes()`, `enviar()` |
| `api/app/services/ntfy.py` | `configurado()`, `reservar()`, `alertar()` |
| `api/app/tarefas.py` | Gatilhos: `espelhar(app)`, `falha_ia(app, codigo)`, `token_revogado(app, carreta)`; `em_thread()`, o executor de produção |
| `api/app/main.py` | `create_app(settings, transports, em_segundo_plano)`; `repetir_espelho(app)`, laço no `lifespan` só com o espelho configurado |
| `api/app/auth.py` | Com token não aceito, procura o hash entre os revogados e dispara `token_revogado` **depois** do rollback; o `401` não muda |
| `api/app/routes/relatorio.py` | `tarefas.falha_ia` depois de gravar a falha; `tarefas.espelhar` depois de gravar o relatório |
| `api/tests/test_espelho_alertas.py` | 12 testes com NocoDB, ntfy e Go simulados por `httpx.MockTransport` e tarefas executadas na hora |
| `docs/NOCODB.md` | Configuração, tabela a criar no NocoDB, funcionamento, conferência e reconstrução |

`create_app` trocou o parâmetro `ia_transport` do Módulo 03 por
`transports={"ia", "nocodb", "ntfy"}`. `api/tests/test_relatorio.py` foi ajustado.

### Espelho

Detalhes de operação em `docs/NOCODB.md`. Resumo:

- `configurado()` exige `NOCODB_ENABLED=true`, URL, id da tabela e token diferente de
  vazio e de `changeme`.
- `espelhar_pendentes()` lê até 20 relatórios `pendente` (`LOTE`), em ordem de id, e
  envia um por requisição a `POST {url}/api/v2/tables/{table}/records` com `xc-token`,
  corpo `[{DiagnosticoId, Data, Carreta, Hostname, Projeto, SubPerfil, Modelo,
  MaiorConfianca, ChamadoTitulo, Relatorio}]` e timeout de 10 s. `200` marca `ok`; outro
  status grava `http_<status>`; conexão ou timeout gravam `indisponivel`/`timeout` e
  **encerram o lote**.
- Disparo: depois de cada relatório gravado (`tarefas.espelhar`) e a cada
  `NOCODB_RETRY_SECONDS` (`repetir_espelho`, que dorme antes da primeira passada).
- `_lock` (um `threading.Lock` do módulo) serializa as passadas.

### Alertas

| Chave | Quando | Título |
|---|---|---|
| `ia:ia_cota` | Go respondeu `402`/`429` | `OpenCode Go recusou por cota` |
| `ia:ia_autenticacao` | Go respondeu `401`/`403` | `OpenCode Go recusou a chave` |
| `ia:taxa` | Depois de qualquer falha da IA, se a última hora tem `NTFY_FAILURE_THRESHOLD_PER_HOUR` (5) ou mais diagnósticos com `falha` | `Falhas da IA acima do limiar` |
| `token_revogado:<carreta>` | Requisição com um token revogado (o inexistente não alerta) | `Token revogado em uso (<carreta>)` |

- Envio por publicação JSON do ntfy: `POST {NTFY_URL}` com
  `{"topic", "title", "message", "priority": 4, "tags": ["warning", "tecnico-assistente"]}`,
  `Authorization: Bearer <NTFY_TOKEN>` e timeout de 5 s. O JSON evita codificar título
  com acento em cabeçalho HTTP.
- **Repetição:** `reservar()` abre `BEGIN IMMEDIATE`, lê a linha da chave em `alertas` e,
  se o último envio foi há menos de `NTFY_REPEAT_MINUTES` (60), só soma em `suprimidos`.
  Senão grava o envio e zera a contagem, e a mensagem enviada termina com
  `(N alertas iguais suprimidos desde o último envio.)`. O relógio é `ntfy.utcnow()`, em
  UTC.
- `alertar()` nunca levanta exceção de rede. As mensagens não levam token, chave nem
  texto do provedor.

### Execução fora da requisição

`app.state.em_segundo_plano` é `tarefas.em_thread` em produção: uma thread daemon por
tarefa, com `log.exception` em falha. Nos testes é `lambda funcao: funcao()`, o que
torna o resultado determinístico. Os gatilhos rodam **depois** de fechar a transação da
requisição: com a execução direta dos testes, o alerta de token revogado disparado
dentro da transação de `exigir_token` travou no lock do SQLite, e por isso ele passou
para o `finally`, depois do rollback.

## Verificação realizada

Ambiente igual ao Módulo 03 (Windows 11 Pro 10.0.26340, Docker 29.6.1, imagem
`python:3.12.14-slim-trixie`). NocoDB e ntfy reais **não** foram chamados.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Suite completa | Comando do `CLAUDE.md`, commit `40bc9a1` | ✅ 142 passed, 1 warning (aviso do `httpx`): 12 novos em `test_espelho_alertas`, 1 novo em `test_config` |
| Campos e cabeçalho do espelho | `test_report_is_mirrored_with_the_documented_fields` | ✅ URL `/api/v2/tables/mtabela/records`, `xc-token`, os 10 campos, `ok` com 1 tentativa |
| NocoDB fora do ar não afeta a resposta | `test_nocodb_down_does_not_affect_the_response_and_is_resent` (conexão recusada e `500`) | ✅ `200` com o relatório; `pendente` com `indisponivel`/`http_500`; reenvio → `ok` com 2 tentativas; terceira passada não reenvia |
| Lote para com o NocoDB fora | `test_nocodb_down_stops_the_batch_at_the_first_failure` (3 pendentes) | ✅ 1 requisição |
| O teste do lote pega o defeito | Mutação: `break` trocado por `pass` | ✅ o teste falha |
| Espelho desligado | `test_mirror_disabled_sends_nothing_and_keeps_pending` | ✅ nenhuma requisição; `pendente` |
| Reenvio periódico | `test_retry_loop_resends_pending_without_new_reports` (`asyncio.sleep` simulado) | ✅ espera de 300 s; pendente vira `ok` sem relatório novo |
| Alerta não se repete em tempestade | `test_quota_storm_sends_one_alert_then_reports_the_suppressed` (10 `429` do Go, limiar 3) | ✅ 2 mensagens (cota e taxa), não 18; `suprimidos` 9 e 7; depois de 61 min, nova mensagem com "9 alertas iguais suprimidos" |
| O teste da tempestade pega o defeito | Mutação: janela de repetição desligada | ✅ 2 testes falham |
| Chave inválida alerta, timeout não | `test_auth_failure_of_the_go_alerts_and_timeout_does_not` | ✅ só "OpenCode Go recusou a chave" |
| Token revogado alerta uma vez; inexistente não | `test_revoked_token_alerts_once_and_unknown_token_does_not` | ✅ 3 `401` com o revogado → 1 alerta; token inexistente → nenhum |
| O teste do revogado pega o defeito | Mutação: disparo do alerta desligado em `auth.py` | ✅ o teste falha |
| ntfy fora do ar não afeta a resposta | `test_ntfy_down_does_not_affect_the_response` | ✅ `503 {"erro":"ia_cota"}` normal |
| Tokens fictícios desligam | `test_placeholder_tokens_disable_the_services` (`""`, `changeme`) | ✅ |
| Container com o espelho ligado | `.env` temporário com `NOCODB_ENABLED=true`, URL inalcançável e `NOCODB_RETRY_SECONDS=10`, 25 s no ar | ✅ `/v1/saude` 200; migrações 1, 2 e 3; laço rodou sem erro no log |
| Espelho no NocoDB real | — | **Não executado** — a tabela e o token são criados pelo responsável no Módulo 06 (`docs/NOCODB.md`) |
| Alerta no ntfy real | — | **Não executado** — tópico e token do glpi-srv, Módulo 06 |

## Decisões

- **TA-ADR-024** — Espelho e alertas em thread do próprio processo, com estado no SQLite.
  Ver `docs/DECISIONS.md`.

## Dependências entre módulos

- **Módulo 05:** nada novo no CI; os testes deste módulo já usam só `MockTransport`.
- **Módulo 06:** criar a tabela do NocoDB com as colunas de `docs/NOCODB.md`, o token do
  NocoDB e o do ntfy, e ligar `NOCODB_ENABLED` e `NTFY_ENABLED` no `.env` do servidor.
  Conferir um alerta real (por exemplo, token revogado) e um espelho real.

## Pontos de atenção

- **Um processo só.** O lock do espelho e a ordem das threads pressupõem o `CMD` sem
  `--workers` (TA-ADR-021, TA-ADR-024).
- **ntfy fora do ar perde o alerta daquela janela**: a reserva é gravada antes do envio
  (comentário `ponytail:` em `ntfy.py`).
- **Duplicata possível no NocoDB** se a API cair entre o `200` e o `UPDATE`
  (`DiagnosticoId` mostra).
- **`espelho_status = 'desligado'` não é usado**: com o espelho desligado, os relatórios
  ficam `pendente` e são enviados quando ele for ligado, 20 por passada.
- **O limiar de taxa conta todas as falhas**, inclusive `ia_nao_configurada`: um servidor
  sem chave alerta assim que passar do limiar, o que é o comportamento desejado.

## Commits

```
de8362c feat(api): add NocoDB and ntfy settings and mirror/alert migration
40bc9a1 feat(api): mirror reports to NocoDB and alert on ntfy off the request path
```

O commit `docs: document module 04 nocodb ntfy` fecha a lista.
