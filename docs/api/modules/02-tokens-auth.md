# Módulo 02 — Tokens e autenticação

**Branch:** `module/02-tokens-auth` · **Data:** 2026-09-28 · **Escopo:**
`PROMPT_CLAUDE_CODE.md` §6.5 e §15, Módulo 02

Cria a segunda camada de autenticação do TA-ADR-007: token individual por carreta,
guardado só como hash SHA-256, com CLI de administração e auditoria só de inclusão. O
módulo também entrega a dependência FastAPI que as rotas do Módulo 03 vão usar, o limite
de requisições por token (TA-ADR-021) e o limite de corpo, que vale para todas as rotas.
Nenhuma rota protegida existe em produção neste módulo: os testes montam uma rota só na
fixture. O `pendrive/` não foi alterado.

## O que foi implementado

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `api/app/migrations/0001_20260928_tokens_auth.sql` | Primeira migração: `carretas_tokens`, índice único parcial `carretas_tokens_um_ativo`, `tokens_auditoria` com dois triggers de bloqueio e `tokens_uso` (ver "Schema"). Sem `BEGIN`/`COMMIT`: quem abre e fecha a transação é o runner do Módulo 01 |
| `api/app/db.py` | Novos `BUSY_TIMEOUT_SECONDS = 5.0`, `connect(path)` (`isolation_level=None`, `timeout=5.0`) e `immediate(conn)`, context manager com `BEGIN IMMEDIATE`, `COMMIT` e `ROLLBACK` em qualquer exceção. `migrate()` passa a abrir a conexão por `connect()` |
| `api/app/tokens.py` | CLI `python -m app.tokens` com `create`, `list`, `revoke`, `rotate` e `auditoria` (ver "CLI") |
| `api/app/body_limit.py` | Middleware ASGI `BodyLimit` (ver "Limite de corpo") |
| `api/app/auth.py` | Dependência `exigir_token`, exceção `Refusal` com `refusal_handler`, `utcnow()` e o upsert `COUNT_USE` (ver "Autenticação") |
| `api/app/config.py` | Campos `max_body_bytes = 512 * 1024` e `rate_limit_per_token_per_hour = 60`, lidos de `MAX_BODY_BYTES` e `RATE_LIMIT_PER_TOKEN_PER_HOUR`. O `.env.example` já tinha as duas variáveis desde o Módulo 01 |
| `api/app/main.py` | `create_app()` registra `BodyLimit` com `settings.max_body_bytes` e o handler de `Refusal` |
| `api/tests/conftest.py` | Fixtures novas: `protected_client`, com `POST /teste/protegida` e `Depends(exigir_token)` só no app de teste, e `issue(carreta)`, que cria um token ativo direto no banco |
| `api/tests/test_migrations.py` | 3 testes sobre a migração real: índice parcial e trigger |
| `api/tests/test_tokens_cli.py` | 13 testes da CLI |
| `api/tests/test_body_limit.py` | 11 testes, com rota `POST /teste/eco` só no teste e limite de 16 bytes |
| `api/tests/test_auth.py` | 17 testes, com limite de 3 por hora, corpo de 64 bytes e relógio congelado |
| `docs/TOKENS.md` | Runbook dos sete cenários da §6.5 |

### Schema

| Tabela | Classe | Colunas | Restrições |
|---|---|---|---|
| `carretas_tokens` | ② fonte da verdade | `id`, `carreta`, `token_hash`, `descricao`, `criado_em`, `criado_por`, `ultimo_uso`, `revogado_em`, `revogado_por`, `motivo`, `ativo` | `token_hash UNIQUE`; `ativo IN (0, 1)`; `CREATE UNIQUE INDEX carretas_tokens_um_ativo ON carretas_tokens (carreta) WHERE ativo = 1` |
| `tokens_auditoria` | ② fonte da verdade | `id`, `em`, `operacao`, `operador`, `carreta`, `token_id`, `resultado`, `detalhe` | `resultado IN ('ok', 'recusado', 'falha')`; triggers `tokens_auditoria_sem_update` e `tokens_auditoria_sem_delete` com `RAISE(ABORT, 'tokens_auditoria is append-only')` |
| `tokens_uso` | ② estado operacional | `token_id` (chave), `janela`, `contagem` | Uma linha por token (TA-ADR-021) |

Os horários são `CURRENT_TIMESTAMP` do SQLite, em UTC, apesar do `TZ=America/Sao_Paulo`
do container. O `REFERENCES carretas_tokens (id)` documenta a relação, mas não é
aplicado: o `PRAGMA foreign_keys` continua desligado, como é o padrão do SQLite. As linhas
de token nunca são apagadas, então nenhuma referência fica órfã.

### CLI

`api/app/tokens.py`, executado com `docker exec -it tecnico-api python -m app.tokens ...`.

- **`--operador` é obrigatório em todos os subcomandos**, inclusive `list` e
  `auditoria`, porque toda operação vai para a auditoria. O valor passa por `strip()`, e
  vazio é recusado e auditado com `operador` `''`.
- **A carreta é normalizada** com `strip().upper()` pela função `carreta()`, usada como
  `type=` do argparse: `um-03` e `UM-03` não conseguem ter dois tokens ativos.
- **Execução:** `main()` roda `db.migrate()` (idempotente) e executa o handler dentro de
  `db.immediate(conn)`. O handler grava a própria linha `ok` na mesma transação e devolve
  o texto de saída, que **só é impresso depois do `COMMIT`**. Assim, um token na tela é
  sempre um token gravado.
- **Recusas e falhas:** `Refused` (regra) e `sqlite3.Error` (banco) desfazem a transação.
  Depois do rollback, em autocommit, `main()` grava uma linha `recusado` ou `falha` com a
  mensagem em `detalhe` e devolve a saída 1 ou 2. As mensagens do SQLite citam tabela e
  restrição, nunca valores.
- **`create`** recusa quando a carreta já tem token ativo. O índice parcial é a segunda
  barreira: sob `BEGIN IMMEDIATE`, a checagem e o `INSERT` não têm corrida.
- **`rotate`** revoga o token ativo (`UPDATE ... ativo = 0, motivo = 'rotate'`) **antes**
  do `INSERT` do novo, na mesma transação, porque o índice único parcial é checado a cada
  instrução. A descrição é copiada. A auditoria registra o id novo e
  `substitui o token N`.
- **`list`** mostra todas as linhas, sem token nem hash. **`auditoria [--carreta X]`**
  mostra o histórico e grava a própria consulta.
- **Geração:** `itcta_` + `secrets.token_urlsafe(32)` (43 caracteres, 256 bits). No banco
  fica só `hashlib.sha256(token).hexdigest()`.

### Limite de corpo

`api/app/body_limit.py`, registrado em `create_app()`, vale para qualquer rota, inclusive
as que ainda não existem. Atua só no escopo `http`: `lifespan` e outros escopos passam
direto.

1. Com `Content-Length`: um valor que não é só de dígitos ASCII (`bytes.isdigit`: vazio,
   `-1`, `+1`, `1.5`, `abc`) dá `400 {"erro": "requisicao_invalida"}`. Acima de
   `max_bytes`, dá `413 {"erro": "corpo_grande"}` sem ler o corpo.
2. Sem `Content-Length` (chunked): o middleware lê as mensagens `http.request`, somando
   os bytes, e responde `413` assim que a soma passa do limite.
3. Até o limite, o corpo fica em memória (no máximo 512 KB) e é repassado ao app por um
   `receive` substituto. Como o corpo é lido inteiro antes de qualquer rota ou
   dependência, **a ordem corpo → token → limite fica garantida pela estrutura**, sem
   depender de como o FastAPI resolve dependências e corpo.

### Autenticação

`api/app/auth.py`, `exigir_token(request) -> carreta`:

1. Lê `Authorization`, separa esquema e valor no primeiro espaço e exige esquema `bearer`
   (sem diferenciar maiúsculas, como define a RFC 7235) e valor em
   `TOKEN_FORMAT = itcta_[A-Za-z0-9_-]{43}` com `fullmatch`. Sem cabeçalho, outro
   esquema, valor com espaço extra ou mal formado dão `401` sem abrir o banco.
2. Calcula o SHA-256 do token e, dentro de `db.immediate(conn)`, busca
   `SELECT id, carreta, token_hash FROM carretas_tokens WHERE token_hash = ? AND ativo = 1`.
   Não achar é `401`, e o rollback não grava nada.
3. Na mesma transação: upsert `COUNT_USE` em `tokens_uso`, com a janela
   `utcnow().strftime("%Y-%m-%dT%H")`, e `UPDATE ... SET ultimo_uso = CURRENT_TIMESTAMP`.
4. Depois do `COMMIT`, se `contagem > rate_limit_per_token_per_hour`, responde `429` com
   `Retry-After = 3600 - (minuto * 60 + segundo)`.

As respostas saem pelo `refusal_handler`: `{"erro": "<código>"}` e os cabeçalhos da
recusa, sem texto de exceção. O `401` leva `WWW-Authenticate: Bearer`. O revogado recebe
**o mesmo `401` do inexistente**: o Módulo 07 trata `401` como "token inválido ou
revogado, pedir troca", e quem testa um token roubado não descobre se ele já existiu.
Não há cache: o `revoke` vale na requisição seguinte.

**Tempo constante (TA-ADR-007).** A busca é por igualdade no índice único de `token_hash`,
e a comparação do B-tree do SQLite não é em tempo constante. Mesmo assim, isso atende à
intenção do ADR, que é impedir que o tempo de resposta revele o token aos poucos:

- O índice compara o **SHA-256 da entrada**, não a entrada. O atacante escolhe o token,
  mas não controla o hash: mudar um caractere do token muda o hash inteiro.
- Mesmo que o tempo revelasse quantos caracteres iniciais do hash batem com um hash
  gravado, esse conhecimento não ajuda a montar o token. Para aproveitá-lo, seria
  preciso achar entradas cujo SHA-256 comece com um prefixo escolhido, o que é
  equivalente a atacar a pré-imagem do SHA-256.
- O token tem 256 bits de entropia, então tentativa e erro também não é viável.

Depois da busca, `hmac.compare_digest(row[2], digest)` repete a comparação em tempo
constante. É redundante, porque o `WHERE` já garantiu a igualdade, mas deixa a intenção
do TA-ADR-007 visível no código e protege contra uma mudança futura na consulta.

### Escolhas feitas no caminho

- **Trigger de bloqueio na auditoria.** `BEFORE UPDATE` e `BEFORE DELETE` com
  `RAISE(ABORT, ...)`, aprovado pelo responsável. Fica registrado aqui, e não num ADR,
  porque não há alternativa com consequência real. O guard de controle de transação do
  Módulo 01 compara a primeira palavra de cada instrução, e o `CREATE TRIGGER ... BEGIN
  ... END` começa por `CREATE`. O teste do Módulo 01
  (`test_trigger_and_quoted_keywords_are_allowed`) já cobria esse caso, e a migração real
  passou por ele.
- **A auditoria não guarda token nem hash**, só `token_id` e `carreta`.
  `test_audit_never_holds_a_token_or_its_hash` percorre todas as células da tabela
  depois de todas as operações.
- **`criado_por` vem de `--operador`.** O `docker exec` roda como `uid=10001(app)`
  (conferido no container) e não traz a identidade de quem digitou. O nome é declarado
  por quem usa, não autenticado: o controle real é o acesso ao Docker no glpi-srv, que
  hoje é SSH (§4).
- **Subcomando `auditoria`**, aprovado pelo responsável, porque o cenário 5 do runbook
  precisa ler a auditoria e a imagem slim não tem o binário `sqlite3`.
- **`busy_timeout` pelo `timeout=` do `sqlite3.connect`**, que chama
  `sqlite3_busy_timeout`. As escritas usam `BEGIN IMMEDIATE`, porque uma transação
  adiada que sobe de leitura para escrita recebe `SQLITE_BUSY` na hora, sem passar pelo
  busy handler.
- **Contagem no SQLite, não em memória** (TA-ADR-021).
- **Horários em UTC.** Converter exigiria formatar em cada consulta. O runbook avisa e
  mostra a conversão.
- **Correção no `CLAUDE.md`.** O comando do pytest tinha um byte BEL (0x07) no lugar de
  `\a` em `"${PWD}\api:/app"`, desde o commit `c175c7f`. Um comando copiado dali montaria
  um caminho errado. Corrigido no commit de documentação deste módulo.

## Verificação realizada

Ambiente: Windows 11 Pro 10.0.26340, Docker 29.6.1, Docker Compose v5.3.0. Pytest e
container em `python:3.12.14-slim-trixie` (Python 3.12.14, SQLite 3.46.1). Para o
container local foi criado um `api/.env` temporário a partir do `.env.example`, com
`APP_PORT=3099`, porta só de teste (`git check-ignore -v api/.env` →
`.gitignore:2:.env`). O arquivo foi apagado ao fim, depois de `docker compose down -v`.

As mutações rodaram numa cópia de `api/` dentro do container (montagem `:ro`), com
scripts no scratchpad da sessão. A árvore do repositório não foi alterada.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Suite completa | Comando do `CLAUDE.md`, commit `58a4780` | ✅ 68 passed, 1 warning (o mesmo aviso do `httpx` do Módulo 01): `test_auth` 17, `test_tokens_cli` 13, `test_body_limit` 11, `test_db` 10, `test_saude` 8, `test_config` 6, `test_migrations` 3 |
| Segundo token ativo na mesma carreta | `test_second_active_token_for_same_carreta_is_rejected` | ✅ `IntegrityError` |
| Tokens revogados não contam no índice | `test_revoked_tokens_do_not_count_against_the_active_one` | ✅ 2 revogados + 1 ativo na UM-03, e 1 ativo na UM-04 |
| Auditoria só de inclusão, trigger real | `test_audit_is_append_only` | ✅ `UPDATE` e `DELETE` levantam `IntegrityError` com "append-only"; a linha continua `ok` |
| `create` guarda só o hash; `list` sem segredo | `test_create_stores_only_the_hash_and_shows_the_token_once` | ✅ `token_hash` = SHA-256 do token; `list` sem token nem hash |
| Carreta normalizada | `test_carreta_is_normalized` (`" um-03 "` e depois `UM-03`) | ✅ segundo `create` recusado; uma linha `UM-03` |
| Recusas auditadas | `test_refusals_are_audited` (revoke e rotate de carreta inexistente, carreta vazia), `test_second_create_is_refused_and_audited`, `test_empty_operator_is_refused_and_audited` | ✅ saída 1 e uma linha `recusado` em cada caso |
| `revoke` | `test_revoke_deactivates_the_token` | ✅ `ativo` 0, `revogado_por`, motivo; auditoria com `token_id` 1 |
| (a) `rotate` deixa um ativo | `test_rotate_leaves_exactly_one_active_token` | ✅ exatamente um ativo, com o hash do token novo; antigo com `ativo` 0 e motivo `rotate` |
| (b) Falha no meio do `rotate` | `test_failure_in_the_middle_of_rotate_keeps_the_old_token`: `secrets.token_urlsafe` devolve o token antigo e o `INSERT` falha em `UNIQUE(token_hash)` depois do `UPDATE` | ✅ saída 2; `carretas_tokens` idêntica à de antes; exatamente uma linha `rotate` / `falha`; token antigo fora da saída |
| O teste (a) pega a ordem errada | Mutação: `INSERT` antes do `UPDATE` no `rotate` | ✅ `test_rotate_leaves_exactly_one_active_token` e `test_audit_never_holds_a_token_or_its_hash` falham (índice parcial) |
| Auditoria sem token nem hash | `test_audit_never_holds_a_token_or_its_hash` (create ×2, rotate, revoke, create recusado, list, auditoria) | ✅ nenhum dos 3 tokens nem dos 3 hashes em nenhuma célula nem na saída do `auditoria` |
| `auditoria` filtra e grava a si mesma | `test_auditoria_filters_by_carreta_and_audits_itself` (`--carreta um-04`) | ✅ só UM-04 na saída; última linha `auditoria` / `UM-04` |
| Escritor espera o lock | `test_writer_waits_for_a_busy_database`: outra conexão segura `BEGIN IMMEDIATE` por 0,5 s | ✅ `list` sai com 0 depois de ≥ 0,4 s |
| O teste do lock pega o defeito | Mutação: `BUSY_TIMEOUT_SECONDS = 0` | ✅ o teste falha com `database is locked` |
| Linha de recusa sem transação própria | Mutação: `db.immediate` removido em volta da linha de recusa | Sobreviveu: em autocommit, o `INSERT` avulso é equivalente. O `with` foi removido do código (commit `62f2295`) |
| Corpo no limite exato | `test_body_at_the_limit_passes` (16 bytes) | ✅ `200`, a rota recebe 16 bytes |
| `Content-Length` acima | `test_content_length_over_the_limit_is_refused` | ✅ `413 {"erro":"corpo_grande"}` |
| Chunked acima | `test_chunked_body_over_the_limit_is_refused` (gerador; a requisição sai sem `content-length`) | ✅ `413` |
| Chunked abaixo chega inteiro | `test_chunked_body_under_the_limit_reaches_the_route_whole` | ✅ `200`, 16 bytes |
| O teste chunked pega o defeito | Mutação: contagem por pedaço trocada por `if False` | ✅ `test_chunked_body_over_the_limit_is_refused` falha |
| `Content-Length` malformado | `test_malformed_content_length_is_refused` (`abc`, `-1`, `+1`, `1.5`, vazio) | ✅ `400 {"erro":"requisicao_invalida"}` nos 5 |
| Limite em qualquer rota | `test_limit_applies_to_every_route` | ✅ `POST /v1/saude` com 17 bytes → `413`; `GET` → `200` |
| Token válido | `test_valid_token_passes_and_records_last_use` | ✅ `200 {"carreta":"UM-03"}`; `ultimo_uso` preenchido |
| Credenciais ruins, mesmo `401` | `test_bad_credentials_get_the_same_401`, 10 casos: sem cabeçalho, vazio, `Bearer`, `Bearer `, `Basic`, `Token itcta_...`, curto, sem prefixo, espaço extra, bem formado inexistente | ✅ `401 {"erro":"nao_autorizado"}` e `WWW-Authenticate: Bearer` nos 10 |
| Revogado recusado na hora | `test_revoked_token_is_refused_on_the_next_request` (200, `revoke` pela CLI, nova requisição) | ✅ `401`, mesmo corpo |
| O teste do revogado pega o defeito | Mutação: `AND ativo = 1` removido da busca | ✅ 3 testes falham (revogado, rotate, ordem) |
| `rotate` troca o token aceito | `test_rotate_swaps_the_accepted_token` | ✅ antigo `401`, novo `200` |
| Limite por token | `test_hourly_limit_is_per_token` (3 por hora; 4ª às 14:59:30 UTC) | ✅ `429 {"erro":"limite_excedido"}`, `Retry-After: 30`; outro token `200` |
| Hora nova abre janela nova | `test_new_hour_opens_a_new_window` | ✅ `429` às 14h, `200` às 15:00 |
| O teste da janela pega o defeito | Mutação: `CASE` trocado por `contagem + 1` | ✅ `test_new_hour_opens_a_new_window` falha |
| Ordem corpo → token → limite | `test_order_is_body_then_token_then_limit` | ✅ corpo grande sem token → `413`; corpo grande com token acima do limite → `413`; token acima do limite → `429`; o mesmo token revogado → `401` |
| Recusas não contam | `test_refused_requests_do_not_count` (`413` com token válido e `401`) | ✅ `tokens_uso` vazia |
| Cenários 1 a 5 do runbook | CLI real no container `tecnico-api` local, 2026-09-28 | ✅ ver a tabela em `docs/TOKENS.md` |
| Cenários 6 e 7 do runbook | — | Não executado — depende do Módulo 06/07 |
| Passos HTTP do runbook no container | — | Não executado — sem rota protegida em produção até o Módulo 03; coberto pelo pytest acima |
| Limite de corpo pelo uvicorn real | `curl -X POST` em `/v1/saude` com 524 289 e 524 288 bytes, com `Content-Length` e com `Transfer-Encoding: chunked` | ✅ acima → `413 {"erro":"corpo_grande"}` nos dois modos; exato → `405` da rota (passou pelo middleware) |
| `Content-Length` malformado pelo uvicorn real | `curl -H 'Content-Length: -1'` e `'Content-Length: abc'` | ⚠️ `400 Invalid HTTP request received.` em texto puro, do h11/uvicorn, antes do middleware (ver Pontos de atenção) |
| Persistência e usuário | `docker compose restart`, `list`, `schema_migrations`, `id` | ✅ 4 tokens e 14 linhas de auditoria depois do restart; `[(1, '0001_20260928_tokens_auth.sql')]`; `uid=10001(app)` |
| `.env` fora do Git | `git status --short` antes de cada commit | ✅ nenhum `.env` nem `*.db` preparado |

## Decisões

- **TA-ADR-021** — Contar requisições por token no SQLite, em janela fixa de uma hora UTC.
  Ver `docs/DECISIONS.md`.

## Dependências entre módulos

- **Módulo 03** protege `POST /v1/relatorio` e `GET /v1/historico/{hostname}` com
  `Depends(exigir_token)`, que devolve a carreta a gravar em `diagnosticos`. O corpo de
  512 KB já está limitado pelo middleware. Executa no container os passos HTTP do
  runbook (`200`, `401` depois do `revoke`, `ultimo_uso`). Atualiza o cenário 5 do
  `docs/TOKENS.md` para usar a tabela `diagnosticos` (requisições por carreta), além do
  `ultimo_uso`, que só mostra a última.
- **Módulo 04** alerta no ntfy quando chegar requisição com token revogado (§6.7). Hoje o
  revogado e o inexistente seguem o mesmo caminho em `exigir_token`: separar os dois só
  para o alerta exige uma segunda consulta sem `AND ativo = 1`, sem mudar a resposta.
- **Módulo 06** executa o cenário 6 do runbook (service token do Cloudflare Access) e cria
  o primeiro token real de cada carreta no glpi-srv.
- **Módulo 07** grava o token em `pendrive/config/api.json`, envia
  `Authorization: Bearer itcta_...` e trata `401` (pedir troca do token), `413`, `429`
  (`Retry-After`) e `400` em texto puro. Executa o cenário 7.

## Pontos de atenção

- **`Content-Length` malformado nunca chega ao middleware no uvicorn.** O h11 recusa com
  `400 Invalid HTTP request received.` em texto puro. O `400 {"erro":
  "requisicao_invalida"}` do `BodyLimit` só aparece com um servidor que deixe o cabeçalho
  passar, e é esse o caso coberto pelo pytest. O cliente do Módulo 07 não deve depender
  do corpo JSON num `400`.
- **Todo `create` e `rotate` imprime o token.** Use `docker exec -it` e não redirecione
  a saída para arquivo nem para log. No teste do container, a transcrição passou por
  `sed` com o token mascarado.
- **O `ultimo_uso` é atualizado também na requisição que passa do limite** (`429`),
  porque o token é válido e foi usado. As recusas por corpo e por token não tocam nele.
- **O `rotate` zera a contagem de requisições da carreta.** O token novo é outra linha,
  com outro `token_id`, e o `tokens_uso` é indexado por `token_id`. Então o token novo
  começa a hora com a cota cheia, mesmo que o antigo já tivesse gasto parte dela. Não é
  risco, porque só o administrador faz `rotate`, pelo `docker exec` no glpi-srv, e quem
  tem esse acesso já pode criar tokens.
- **A regra de "um token ativo" está no banco.** Qualquer código novo que insira em
  `carretas_tokens` precisa revogar o ativo antes, na mesma transação, como o `rotate`.
- **Escritas novas no banco devem usar `db.immediate()`.** Uma transação adiada que sobe
  para escrita falha na hora com `database is locked`, sem esperar o busy timeout.
- **`tokens_auditoria` não aceita `UPDATE` nem `DELETE`.** Uma migração futura que
  precise mudar a estrutura dela terá de recriar a tabela (`CREATE ... AS SELECT`) ou
  derrubar os triggers antes, e isso deve ser registrado em ADR.

## Commits

```
dfc2c8f docs: append progress entries in chronological order
265f118 feat(api): add token, audit and usage tables migration
62f2295 feat(api): add token CLI
6ab4fc7 feat(api): limit request body size
58a4780 feat(api): add per-token auth and hourly rate limit
17c2a38 docs: add token runbook
```

```
b536ec8 docs: document module 02 tokens auth
```

O commit `docs: update module 02 after PR review` fecha a lista.
