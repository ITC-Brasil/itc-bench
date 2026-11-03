# Módulo 03 — Relatório com IA

**Branch:** `module/03-ai-report` · **Data:** 2026-09-28 · **Escopo:**
`PROMPT_CLAUDE_CODE.md` §6.2 a §6.4, §7 e §15, Módulo 03

Entrega as duas rotas de negócio da API: `POST /v1/relatorio`, que recebe a sessão do
pendrive, normaliza para o contrato atual, monta o prompt no servidor, chama o OpenCode
Go e grava diagnóstico e relatório, e `GET /v1/historico/{hostname}`. As duas usam o
`exigir_token` do Módulo 02. O módulo também fecha as pendências herdadas: verificação
da frota registrada, `tokens.py` com saída 3 para falha de banco, passos HTTP do runbook
no container e cenário 5 com a tabela `diagnosticos`. O `pendrive/` não foi alterado.

## O que foi implementado

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `api/app/config.py` | `opencode_go_api_key: SecretStr = SecretStr("")` e `opencode_go_timeout_seconds: float = Field(60.0, gt=0, le=90)`, lidos de `OPENCODE_GO_API_KEY` e `OPENCODE_GO_TIMEOUT_SECONDS` |
| `api/app/migrations/0002_20260928_diagnosticos_relatorios.sql` | Tabelas `diagnosticos` e `relatorios` (ver "Schema") |
| `api/app/normalizacao.py` | `normalizar(entrada) -> (sessão, avisos)`, `resumir(sessão)` e a base `BASE_EVENTOS` (ver "Normalização") |
| `api/app/eventlog-conhecidos.json` | Cópia de `pendrive/config/eventlog-conhecidos.json` (TA-ADR-022) |
| `api/app/prompts/relatorio.md` | Prompt de sistema em português, com as regras da §6.4 e as do TA-ADR-019/020 |
| `api/app/prompt.py` | `montar(sessão, avisos, histórico)`: mensagens `system` + `user`, sem `usuarioExecucao`, `numeroSerie` e `macAddress` (TA-ADR-023) |
| `api/app/services/opencode_go.py` | Cliente do Go: `gerar()`, `IAFalha(status, code)`, `Resposta` (ver "Cliente do Go") |
| `api/app/routes/relatorio.py` | Schemas `Sessao` e `Entrada`, `POST /v1/relatorio`, `GET /v1/historico/{hostname}` |
| `api/app/main.py` | `create_app(settings, ia_transport=None)`, handler de `RequestValidationError` com `422 {"erro":"requisicao_invalida"}` e o router novo |
| `api/app/auth.py` | `exigir_token` grava `request.state.token_id` para o `diagnosticos.token_id` |
| `api/app/tokens.py` | Saída `3` para falha de banco (antes `2`, que é também a saída do argparse), docstring corrigida e subcomando `uso` |
| `api/tests/fixtures/sessao-1.0.json`, `sessao-1.1.json` | Sessões sintéticas com os defeitos de 1.0 e o caso da frota (NVMe `parcial`, desgaste 0 sem `horasLigado`, HAL 21) |
| `api/tests/test_normalizacao.py`, `test_prompt.py`, `test_opencode_go.py`, `test_relatorio.py` | 14, 4, 19 e 18 testes |
| `docs/TOKENS.md` | Saídas 2 e 3, subcomando `uso`, cenário 5 com diagnósticos por dia e passos HTTP executados |

### Schema

| Tabela | Classe | Colunas | Restrições |
|---|---|---|---|
| `diagnosticos` | ② fonte da verdade | `id`, `carreta`, `token_id`, `hostname`, `sessao_id`, `projeto`, `sub_perfil`, `versao_schema`, `dados` (sessão normalizada, JSON), `resumo` (JSON), `falha`, `recebido_em` | Índices `(hostname, id)` e `(carreta, recebido_em)` |
| `relatorios` | ② fonte da verdade | `id`, `diagnostico_id`, `modelo`, `tokens_entrada`, `tokens_saida`, `duracao_ms`, `maior_confianca`, `relatorio_md`, `chamado_titulo`, `chamado_descricao`, `espelho_status`, `gerado_em` | `diagnostico_id UNIQUE`; `maior_confianca IN ('ALTA','MÉDIA','BAIXA')` ou `NULL`; `espelho_status IN ('pendente','ok','desligado')`, padrão `pendente` |

- **Todo POST aceito grava um diagnóstico**, antes da chamada ao Go. Se a IA falha, a
  linha fica com o código em `falha` e sem relatório. É o que o cenário 5 do runbook
  conta, e o histórico mostra a falha.
- **Uma sessão reenviada vira outro diagnóstico.** Não há `UNIQUE(sessao_id)`: depois de
  uma falha da IA, o reenvio do pendrive precisa ser aceito. O histórico mostra as duas.
- `espelho_status` nasce `pendente` e é tratado no Módulo 04.
- Horários em UTC (`CURRENT_TIMESTAMP`), como no Módulo 02.

### Normalização

`api/app/normalizacao.py`, chamado antes de gravar e antes do prompt. A entrada nunca é
alterada (cópia profunda). Regras de 1.0 (TA-ADR-018):

| Campo | Regra |
|---|---|
| `disco.resumo.recuperavelSeguroBytes`, `itensSeguroComConteudo`, `revisarBytes`, `itensRevisar` | Recalculados de `itensLimpeza`, com a regra de `Get-ResumoTier` (tier igual e `bytes` diferente de 0 e de `null`) |
| `itensLimpeza`, `maioresPastasPerfil` | Ordenados por `bytes`, decrescente |
| `percentualVidaRestante` | Copiado para `percentualDesgaste`, sem conversão (TA-ADR-019) |
| `smartDisponivel` | Descartado; `estadoSmart` derivado dos 8 contadores de `$script:ContadoresSmart`, na mesma ordem, com a mesma `observacao` do pendrive 1.1 |
| `temperaturaC`, `temperaturaMaximaC` iguais a 0 | `null` (regra D9 do 00.1, que o 1.0 não tinha) |
| `eventlog.grupos[]` | Reclassificados pelo par exato provedor + id contra `BASE_EVENTOS`: `conhecido`, `apelido`, `categoria`, `peso`, `descricao`, `acaoSugerida`, `nota`, `fonteOficial` vêm da base atual, ou ficam `null`; reordenados por nível e ocorrências; `gruposDesconhecidos` recontado |
| `rede.adaptadores[].apipa` | Recalculado: `status == "Up"` e algum IPv4 `169.254.*` |
| `sessao.ultimaAtualizacao` ausente | `inicio + duracaoSegundos` |
| Pendrive e Avisos | Dois avisos fixos, `AVISO_PENDRIVE_1_0` e `AVISO_EVENTOS_1_0` (Avisos do Event Log não lidos em 1.0, então `disk 51` não aparece) |

Regras de todas as versões:
- `hostname` com `strip().upper()`.
- `usuarioLogado` vira `usuarioExecucao`, e `usuarioSessao` é `null`. Em 1.0 e 1.1 o
  campo é `$env:USERNAME` (`pendrive/lib/Util-Sessao.ps1`), a conta que elevou a
  ferramenta, e não quem estava logado (verificação da frota). O nome novo deixa o
  significado real no banco; o prompt não recebe o campo (TA-ADR-023). O Módulo 07 grava
  os dois campos no contrato 1.2.
- `percentualDesgaste` 0 com `horasLigado` `null` vira `null`, com uma frase na
  `observacao`. É o caso do NVMe da frota, cujo driver não informa as horas; o desgaste 0
  não distingue disco novo de contador ausente. A regra fica no código (TA-ADR-016), e o
  prompt continua dizendo que `null` é não informado.
- Só os módulos `disco`, `eventlog`, `rede`, `processos` e `bateria` seguem adiante.

Os avisos são enviados no prompt e **também anexados pelo código** ao fim do
`relatorio_md`, numa seção `## Avisos da coleta` (`com_avisos` em
`api/app/routes/relatorio.py`): o técnico sempre os vê, qualquer que seja o texto do
modelo.

`resumir()` guarda por diagnóstico alguns campos para o histórico: `percentualLivre` por
volume, `modelo`/`estadoSmart`/`percentualDesgaste`/`temperaturaC` por disco, grupos de
peso `alto` com ocorrências, total de grupos, desgaste da bateria, memória em uso e
`internetOk`.

### Prompt

- `api/app/prompts/relatorio.md` é o prompt de sistema, lido uma vez na importação de
  `api/app/prompt.py`. Trocar o texto exige só reiniciar o container (TA-ADR-006).
- Regras do prompt: nunca decidir nem executar; não inventar; `null` é não informado;
  ausência de erro no SMART de disco `parcial`/`indisponivel` não indica disco saudável;
  `percentualDesgaste` alto é pior (TA-ADR-019); `temperaturaMaximaC` é limite de operação;
  169.254.x.x em adaptador desconectado é normal; **`fonteOficial: false`: citar evento e
  contagem, sem afirmar causa nem recomendar ação, e nunca como evidência principal de
  hipótese ALTA** (TA-ADR-020); `conhecido: false` só com o que a mensagem diz; `nota`
  prevalece; política de limpeza por projeto e sub-perfil (TA-ADR-017), só `tier: seguro`.
- Formato: o modelo responde **só um objeto JSON** com `relatorio_md`, `chamado_titulo`,
  `chamado_descricao` e `maior_confianca`. O laudo tem `## Resumo`, `## Hipóteses`
  (confiança, evidência, ação sugerida), `## Correlação com o histórico` e
  `## Limites desta análise`. Desde o TA-ADR-026: no máximo cerca de 700 palavras, no
  máximo 4 hipóteses, evidência em uma ou duas linhas e sem repetir o Resumo.
- Mensagem do usuário: a sessão normalizada em JSON compacto (sem identificadores), os
  avisos em lista e o histórico dos 5 diagnósticos anteriores do hostname (`resumo`,
  título do chamado, confiança, falha), ou "Sem diagnósticos anteriores deste hostname."
  O histórico é lido **antes** de gravar o diagnóstico atual, então a sessão nunca
  aparece no próprio histórico.

### Cliente do Go

`api/app/services/opencode_go.py`, `gerar(settings, mensagens, sessao_id, transport)`:

- `POST https://opencode.ai/zen/go/v1/chat/completions` com `Authorization: Bearer
  <chave>`, `User-Agent: itc-tecnico-assistente/1.0`, `x-opencode-session: <sessaoId>` e
  corpo `{"model": OPENCODE_GO_MODEL, "messages": [...], "reasoning_effort": "low"}`. O
  `reasoning_effort` vem de `OPENCODE_GO_REASONING_EFFORT` (padrão `low`) e não é enviado
  quando a variável está vazia (TA-ADR-026).
- `httpx.Client(timeout=60.0)`: 60 s em cada fase (conexão, escrita, leitura, pool).
- Chave vazia ou `changeme` (a do `.env.example`) não é enviada: `503
  ia_nao_configurada`.
- Mapa de falhas: timeout → `503 ia_timeout`; erro de conexão ou `5xx` → `503
  ia_indisponivel`; `402`/`429` → `503 ia_cota`; `401`/`403` → `502 ia_autenticacao`;
  outro `4xx` → `502 ia_recusa`; `200` sem o JSON pedido → `502 ia_resposta_invalida`.
  As exceções são relançadas com `from None`, para nenhum traceback carregar o request
  do httpx, que tem o cabeçalho com a chave.
- A resposta aceita o JSON dentro de uma cerca ```` ```json ````, que os modelos costumam
  pôr apesar do prompt. `maior_confianca` fora de `ALTA`/`MÉDIA`/`BAIXA` vira `null`
  (`MEDIA` sem acento é aceito). `modelo` vem da resposta, e os tokens de `usage`.
- Nos testes, `create_app(settings, ia_transport=httpx.MockTransport(...))`. Em produção,
  `ia_transport` é `None` e o httpx usa o transporte real.

### Rotas

Contrato completo em `docs/API.md`. `POST /v1/relatorio` é uma rota síncrona (`def`),
executada no threadpool do Starlette: a espera pelo Go não bloqueia o event loop. O
fluxo é: corpo (512 KB) → token e limite → schema → normalização → histórico →
`INSERT diagnosticos` → Go, fora de transação → `INSERT relatorios` ou `UPDATE falha` →
resposta. Um corpo inválido com token válido conta no limite por hora, porque o token é
checado antes do schema.

### Revisões pedidas

- **`volmgr 162`:** a busca em `learn.microsoft.com` e `support.microsoft.com`, em
  2026-09-28, só achou tópicos do Microsoft Q&A, que o critério da base não aceita, e
  eles divergem entre si ("falha ao criar o dump" e "Dump file generation succeeded").
  Sem fonte oficial, a entrada fica como está: descrição neutra, `acaoSugerida: null`,
  peso `baixo`, `fonteOficial: false`. A regra do prompt para `fonteOficial: false` cobre
  o caso.
- **`HAL 21`:** a mesma busca só achou Q&A. A página "Event ID 21 — Local Time
  Synchronization" é de outro provedor (serviço de tempo). **Não entra na base.** Continua
  `conhecido: false`, e o prompt só usa o texto da `exemploMensagem`.

### Escolhas feitas no caminho

- **Resposta em JSON, não em Markdown delimitado.** Um objeto com quatro chaves é
  validado com `json.loads`; delimitadores em texto livre quebram com qualquer variação
  do modelo. Resposta fora do formato vira `502 ia_resposta_invalida`, e o pendrive cai
  no relatório determinístico.
- **Timeout com `503`, não `504`.** A §6.2 pede `502`/`503`; o código `ia_timeout` já
  distingue o caso.
- **Limite de 90 s no `OPENCODE_GO_TIMEOUT_SECONDS`.** A configuração recusa valor acima,
  para não passar do corte de 100 s do túnel (TA-ADR-010).
- **`422` sem eco.** O `422` padrão do FastAPI devolve o valor recebido, que tem
  hostname e caminhos; o handler devolve só `{"erro":"requisicao_invalida"}`. Uma sessão
  2.0 recebe o mesmo `422`.
- **Histórico aberto entre carretas.** Uma máquina pode ser atendida por carretas
  diferentes; qualquer token ativo lê qualquer hostname.
- **`uso` na CLI.** A imagem slim não tem o binário `sqlite3`; o cenário 5 precisa ver
  os diagnósticos por carreta. O subcomando é auditado como os outros.

## Verificação realizada

Ambiente: Windows 11 Pro 10.0.26340, Docker 29.6.1, Docker Compose v5.3.0. Pytest e
container em `python:3.12.14-slim-trixie`. Container local com `api/.env` temporário
copiado do `.env.example` (`APP_PORT=3099`, chave `changeme`), apagado ao fim depois de
`docker compose down -v`. Mutações numa cópia de `api/` dentro do container (montagem
`:ro`).

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Suite completa | Comando do `CLAUDE.md`, commit `20e719f` | ✅ 129 passed, 1 warning (o aviso do `httpx` do Módulo 01): `test_opencode_go` 19, `test_relatorio` 18, `test_auth` 17, `test_tokens_cli` 15, `test_normalizacao` 14, `test_body_limit` 11, `test_db` 10, `test_config` 9, `test_saude` 8, `test_migrations` 4, `test_prompt` 4 |
| 1.0: resumo recalculado | `test_1_0_cleanup_summary_is_recalculated_from_items` | ✅ 400 bytes / 2 itens seguros; 700 / 1 revisar (o `null` e o `bloqueado` ficam fora) |
| 1.0: listas ordenadas | `test_1_0_lists_are_sorted_by_bytes` | ✅ |
| 1.0: SMART | `test_1_0_smart_fields_are_renamed_and_derived` | ✅ `percentualDesgaste` 3, `parcial` com a lista dos ausentes; USB com 0 °C → `null` e `indisponivel` |
| 1.0: eventos pelo par exato | `test_1_0_events_are_reclassified_by_exact_provider_and_id` | ✅ `Perflib 1000` `conhecido: false`, sem descrição; `Kernel-Power 41` ganha peso `alto`; `volmgr 162` recebe a descrição neutra e `fonteOficial: false`; ordem crítico → erro por ocorrências |
| O teste de eventos pega o defeito | Mutação: busca na base só pelo id | ✅ o teste falha |
| 1.0: APIPA, `ultimaAtualizacao`, avisos | `test_1_0_apipa_only_on_connected_adapters`, `test_1_0_session_fields_and_notices` | ✅ `[False, True, False]`; `2026-09-05T14:51:00.123456-03:00` a partir de um `inicio` com 7 casas decimais; os dois avisos |
| 1.1 intacta, fora as regras | `test_1_1_is_kept_except_for_the_documented_rules` | ✅ `eventlog` idêntico, módulo desconhecido descartado, campo novo de sessão preservado, sem avisos |
| `usuarioLogado` em 1.0 e 1.1 | `test_usuario_logado_becomes_the_executing_account` | ✅ `usuarioExecucao` preenchido, `usuarioSessao` `null`, `usuarioLogado` ausente |
| Desgaste 0 sem horas | `test_wear_0_without_power_on_hours_is_not_reported` | ✅ `null` e a frase na `observacao` |
| Prompt com e sem histórico | `test_without_history`, `test_with_history`, `test_system_prompt_carries_the_rules` | ✅ |
| Identificadores fora do prompt | `test_identifiers_stay_out_of_the_prompt` | ✅ sem conta, serial e MAC; hostname presente |
| Cliente: cabeçalhos, modelo, timeout | `test_success_sends_headers_model_and_timeout` | ✅ URL, `Bearer`, `User-Agent`, `x-opencode-session`, timeout 60 nas 4 fases, tokens 9800/950 |
| Cliente: 13 falhas | `test_failures_become_clean_codes_without_provider_text` | ✅ códigos da tabela, sem exceção encadeada e sem a chave |
| Chave fictícia não sai | `test_placeholder_key_is_never_sent` (`""`, `changeme`, `" changeme "`) | ✅ `503 ia_nao_configurada`, transporte não chamado |
| POST 1.1 com mock do Go: sucesso | `test_report_for_a_1_1_session` | ✅ `200` com os 8 campos; `diagnosticos` e `relatorios` gravados; `espelho_status` `pendente`; a conta não vai ao prompt |
| POST 1.0: avisos no laudo | `test_1_0_session_is_normalized_and_notices_reach_the_report` | ✅ `## Avisos da coleta` no fim; banco com a sessão normalizada |
| O teste dos avisos pega o defeito | Mutação: `com_avisos` removido | ✅ o teste falha |
| Histórico no prompt e na rota | `test_history_goes_into_the_prompt_and_the_route` | ✅ 2º prompt com a 1ª sessão, sem a própria; `GET` com 2 itens, mais novo primeiro, sem `dados` |
| Mock do Go: timeout, cota, recusa, autenticação | `test_go_failure_answers_fast_and_keeps_the_diagnostico` | ✅ `503 ia_timeout`, `503 ia_cota`, `502 ia_recusa`, `502 ia_autenticacao`; diagnóstico com `falha`, sem relatório |
| Sem token / revogado | `test_without_token_nothing_is_stored_nor_sent`, `test_revoked_token_is_refused_on_both_routes` | ✅ `401` nas duas rotas, Go não chamado, nada gravado |
| Corpo inválido | `test_invalid_body_is_422_without_echo` (versão 2.0, sem hostname, `../etc`, id vazio, `modulos` lista, sem `sessao`) | ✅ `422 {"erro":"requisicao_invalida"}` nos 6 |
| Saída 3 e erro de uso | `test_failure_in_the_middle_of_rotate_keeps_the_old_token`, `test_usage_error_exits_2_before_the_database` | ✅ `3`; argparse sai com `2` sem criar o banco |
| `uso` | `test_uso_counts_diagnosticos_per_carreta_and_day` | ✅ 2 dias, hostnames distintos, falhas e horários |
| Container: migrações | `schema_migrations` no container | ✅ `0001` e `0002` |
| Container: passos HTTP do runbook | `curl` com token real mascarado | ✅ ver `docs/TOKENS.md` "Verificação": `200` no histórico, `ultimo_uso`, `401` depois do `revoke`, `uso` |
| Container: POST 1.1 e 1.0 sem chave | `curl --data-binary @tests/fixtures/...` | ✅ `503 {"erro":"ia_nao_configurada"}` depois da autenticação; `422` para versão 2.0 |
| Roteiro PowerShell do teste manual | Trecho abaixo, no PS 5.1, contra o container local, com uma pasta de sessão montada da fixture 1.1 | ✅ corpo de 4076 bytes aceito (`503 ia_nao_configurada`, não `422`); `ErrorDetails.Message` traz o corpo do erro |
| Teste manual com a chave real do Go | — | **Não executado** — a chave real fica só com o responsável. Roteiro abaixo |

### Latência com sessão real (TA-ADR-026)

Medição do responsável no servidor, com a sessão da máquina RESERVA-06 e
`mimo-v2.6-flash`, antes desta correção e com o `reasoning_effort` enviado à mão:

| Execução | Prompt | Saída | Raciocínio | Tempo | Resultado |
|---|---|---|---|---|---|
| Padrão do provedor | 12.543 | 9.002 | 5.344 | 126,7 s | ❌ acima dos 90 s permitidos e do corte de ~100 s da Cloudflare |
| `reasoning_effort: "low"` | 12.543 | 4.934 | 2.085 | 62,2 s | Aceito pelo provedor; abaixo de 90 s, acima do padrão de 60 s |

Verificação da correção:

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Suite completa | Comando do `CLAUDE.md` | ✅ 149 passed, 1 warning (145 anteriores + 4 novos) |
| `reasoning_effort` no corpo por padrão | `test_success_sends_headers_model_and_timeout` | ✅ `"reasoning_effort": "low"` |
| Ausente quando vazio | `test_empty_reasoning_effort_is_not_sent` (`""` e `"  "`) | ✅ campo fora do corpo |
| Lido do ambiente | `test_reasoning_effort_comes_from_the_environment` (`medium`) | ✅ |
| Limites de tamanho no prompt | `test_system_prompt_limits_the_report_size` | ✅ os quatro limites presentes; regras da §6.4 e dos TA-ADR-019/020 sem alteração (`diff` do `relatorio.md` só na seção "Formato da resposta") |
| Tempo real com a sessão RESERVA-06 depois do deploy | Medição do responsável em produção, 2026-09-29 | 75 s, 13.117 tokens de entrada e 3.722 de saída (tabela do teste manual abaixo) |

## Teste manual com a chave real (passo do responsável)

Na máquina de desenvolvimento, com Docker e uma sessão real da Fase 1 no pendrive.

1. Na pasta `api/`, crie o `.env` a partir do exemplo, com a porta de teste e a chave
   real (copiada do Vaultwarden, digitada no editor, nunca na linha de comando):
   ```
   copy .env.example .env
   notepad .env
   ```
   Troque `APP_PORT=30XX` por `APP_PORT=3099` e `OPENCODE_GO_API_KEY=changeme` pela
   chave. Confira que o `.env` está fora do Git: `git check-ignore -v .env`.
2. Suba o container e crie um token de teste:
   ```
   docker compose up -d --build
   docker exec -it tecnico-api python -m app.tokens create --carreta TESTE --descricao "teste manual modulo 03" --operador matheus
   ```
3. No PowerShell 5.1, ajuste `$pasta` para a sessão real e cole o token em `$token`:
   ```powershell
   $pasta = 'D:\TecnicoAssistente\sessoes\<AAAA-MM-DD_HHmm_HOSTNAME>'
   $token = Read-Host 'token'
   $ler = { param($f) [IO.File]::ReadAllText($f, [Text.Encoding]::UTF8) }
   $modulos = Get-ChildItem $pasta -Filter *.json | Where-Object { $_.Name -notin 'sessao.json', 'correcoes.json' } | ForEach-Object { '"' + $_.BaseName + '":' + (& $ler $_.FullName) }
   $correcoes = if (Test-Path "$pasta\correcoes.json") { ',"correcoes":' + (& $ler "$pasta\correcoes.json") } else { '' }
   $corpo = [Text.Encoding]::UTF8.GetBytes('{"sessao":' + (& $ler "$pasta\sessao.json") + ',"modulos":{' + ($modulos -join ',') + '}' + $correcoes + '}')
   "$($corpo.Length) bytes"
   $inicio = Get-Date
   try {
     $r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:3099/v1/relatorio' -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json; charset=utf-8' -Body $corpo -TimeoutSec 90
     $r.StatusCode
     $j = $r.Content | ConvertFrom-Json
     $j.relatorio_md | Out-File "$env:TEMP\relatorio-teste.md" -Encoding utf8
     $j | Select-Object chamado_titulo, maior_confianca, modelo, tokens_entrada, tokens_saida, diagnostico_id
   } catch { [int]$_.Exception.Response.StatusCode; $_.ErrorDetails.Message }
   "{0:N1} s" -f ((Get-Date) - $inicio).TotalSeconds
   ```
4. Registre na tabela abaixo: status, `tokens_entrada`, `tokens_saida`, tempo, modelo e
   uma avaliação do laudo (`notepad $env:TEMP\relatorio-teste.md`): as hipóteses citam os
   dados? Algum grupo `fonteOficial: false` recebeu causa ou ação? O SMART `parcial` foi
   tratado como disco saudável? Algum dado foi inventado?
5. Repita o passo 3 uma vez, para ver a sessão anterior em "Correlação com o histórico".
6. Limpe: `docker compose down -v` e apague o `api/.env`. O `-v` apaga o banco de teste,
   que tem a sessão real.

| Execução | Status | Tokens entrada / saída | Tempo | Modelo | Avaliação |
|---|---|---|---|---|---|
| 1ª — produção, RESERVA-06, `reasoning_effort: low` (2026-09-29, depois do TA-ADR-026) | `200` | 13.117 / 3.722 | 75 s | `mimo-v2.6-flash` | RESERVA-06, diagnóstico 4, avaliado só no texto do laudo; os valores não foram conferidos contra os JSONs da sessão. Hipóteses citam os dados: sim. Grupo `fonteOficial: false` com causa ou ação: não exercitado nesta sessão, porque nenhum grupo assim apareceu. SMART `parcial` tratado como saudável: não. Dado inventado: não identificado no texto. Defeitos: título do chamado afirmava um sintoma que a ação ainda pedia para confirmar; HAL 21 e DCOM 10010 (`conhecido: false`) receberam ação própria e ligação por horário ao SCM 7011; uma palavra em inglês; falhas `ia_timeout` do histórico citadas no chamado. Corrigidos no prompt do #18. |
| 2ª (com histórico) | **Não executado** | | | | Depende de uma nova execução no servidor |
| Depois do `fix/prompt-relatorio-2` | **Não executado** | | | | Medição de tempo e nova avaliação no servidor, depois do deploy desta correção |

Em caso de `502 ia_resposta_invalida`, o modelo não devolveu o JSON pedido: registre e
ajuste o prompt. Em `502 ia_autenticacao`, a chave está errada.

## Decisões

- **TA-ADR-022** — Manter na API uma cópia da base de Event Log para normalizar sessões 1.0.
- **TA-ADR-023** — Tirar do prompt identificadores que não servem ao diagnóstico.
- **TA-ADR-026** — Pedir raciocínio baixo ao modelo e limitar o tamanho do laudo (correção
  posterior, 2026-09-29).

Ver `docs/DECISIONS.md`.

## Dependências entre módulos

- **Módulo 04** espelha `relatorios` com `espelho_status = 'pendente'` no NocoDB e
  alerta no ntfy em `ia_cota` e `ia_autenticacao` (§6.7).
- **Módulo 05** compara `api/app/eventlog-conhecidos.json` com
  `pendrive/config/eventlog-conhecidos.json` no CI (TA-ADR-022).
- **Módulo 07** monta o corpo `{"sessao", "modulos", "correcoes"}` como no roteiro acima,
  trata qualquer status diferente de `200` como fallback, grava `relatorio_md` e o
  chamado, e sobe o contrato para 1.2 com `usuarioExecucao` e `usuarioSessao`. A API
  precisa aceitar `1.2` em `VERSOES` e normalizar o `usuarioLogado` de 1.1.

## Pontos de atenção

- **O timeout de 60 s é por fase do httpx, não total.** Um provedor que mande bytes aos
  poucos pode passar de 60 s (comentário `ponytail:` em `opencode_go.py`).
- **Mudança na base de Event Log exige os dois arquivos** (TA-ADR-022).
- **Sessão 1.0 recebe o texto da base atual.** Um evento que mudou de descrição aparece
  com o texto novo, não com o que o técnico viu na tela da Fase 1.
- **`usuarioLogado` não é o usuário da máquina** em 1.0 e 1.1; não use `usuarioExecucao`
  para identificar quem usa o notebook.
- **O prompt é lido na importação.** Editar `relatorio.md` no servidor exige
  `docker compose up -d --build` (o arquivo está na imagem).
- **Corpo inválido com token válido conta no limite por hora.**
- **62,2 s medidos com `low` passam do padrão de 60 s.** Se a nova medição, com o limite
  de tamanho, continuar acima de 60 s, ajuste `OPENCODE_GO_TIMEOUT_SECONDS` no `.env` do
  servidor para um valor até 90 (TA-ADR-026).

## Commits

```
aca65eb docs: record phase 1 fleet verification
9731899 fix(api): exit 3 on token CLI database failure
5f6b87f feat(api): add OpenCode Go key and timeout settings
f3371e1 feat(api): add diagnosticos and relatorios migration
db2cb55 feat(api): normalize 1.0 and 1.1 sessions to the current contract
f5e1877 feat(api): add report prompt and server-side assembly
5be1d23 feat(api): add OpenCode Go client with clean error codes
92d6bb1 feat(api): add report and history routes behind carreta token
951364d feat(api): add uso subcommand listing diagnosticos per carreta
20e719f docs: run token runbook HTTP steps and add uso to scenario 5
```

O commit `docs: document module 03 ai report` fecha a lista.
