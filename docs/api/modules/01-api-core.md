# Módulo 01 — Núcleo da API

**Branch:** `module/01-api-core` · **Data:** 2026-09-28 · **Escopo:**
`PROMPT_CLAUDE_CODE.md` §15, Módulo 01

Cria o esqueleto do serviço central em `api/`: configuração lida do ambiente com o
bloqueio do TA-ADR-011, factory do app FastAPI com a documentação interativa desligada por
padrão, runner de migrações SQL, `GET /v1/saude`, imagem Docker e compose de produção
conforme a §9. O módulo não cria nenhuma tabela de negócio, porque elas entram nos
Módulos 02 e 03. O `pendrive/` não foi alterado.

## O que foi implementado

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `api/app/config.py` | `Settings` (`pydantic-settings`), lida de variáveis de ambiente e de `.env`, com `extra="ignore"`. Só três campos por enquanto: `app_enable_docs` (padrão `False`), `database_path` (padrão `/data/tecnico.db`) e `opencode_go_model` (padrão `mimo-v2.6-flash`). O validador `reject_forbidden_model` aplica `strip()`, compara em minúsculas com o prefixo `muse-spark` e recusa com `ValueError` citando o TA-ADR-011 |
| `api/app/main.py` | `create_app(settings=None)`. Instancia `Settings()` na criação, então um modelo proibido derruba o processo na inicialização. `docs_url`, `redoc_url` e `openapi_url` ficam `None` quando `app_enable_docs` é falso. O `lifespan` roda `db.migrate()` antes de aceitar requisições. Não há `app` no nível do módulo: o uvicorn usa `--factory` |
| `api/app/db.py` | `migrate(database_path, migrations_dir)`, `check(database_path)`, `statements(sql)` e `reject_transaction_control(name, sql)`, só com `sqlite3` e `re` da biblioteca padrão (ver "Runner de migrações") |
| `api/app/routes/saude.py` | `GET /v1/saude`: `200 {"status":"ok"}` ou `503 {"status":"erro"}`, sem versão, caminho nem texto de exceção |
| `api/app/migrations/` | Vazio neste módulo e fora do Git até receber a primeira migração. `migrate()` aceita a pasta ausente |
| `api/requirements.txt` | Dependências de execução com `==`: diretas e transitivas, lidas do `pip freeze` na imagem base |
| `api/requirements-dev.txt` | `-r requirements.txt` + `pytest==9.1.1` e as transitivas dele |
| `api/pytest.ini` | `pythonpath = .`, `testpaths = tests`, `-p no:cacheprovider` (o teste roda com `api/` montado no container e não deixa `.pytest_cache` na árvore) |
| `api/tests/conftest.py` | Fixture `settings` com banco em `tmp_path` e `_env_file=None`, para que um `api/.env` local não vaze para os testes. Fixture `client` com `TestClient` em contexto, que executa o `lifespan` |
| `api/Dockerfile` | `FROM python:3.12.14-slim-trixie`, instala só `requirements.txt`, copia `app/`, cria o usuário `app` (uid 10001), dono de `/data`, e roda `uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$APP_PORT"` |
| `api/.dockerignore` | `.env`, `*.db`, `tests/`, `__pycache__/`, para que o `.env` não entre no contexto de build |
| `api/docker-compose.yml` | Projeto `tecnico-assistente`, serviço `api`, `container_name: tecnico-api`, `restart: always`, `env_file: .env`, `TZ: America/Sao_Paulo`, porta `"127.0.0.1:${APP_PORT}:${APP_PORT}"` (TA-ADR-009), volume nomeado `tecnico-data` em `/data`, sem label do Watchtower |
| `api/.env.example` | As 17 variáveis da §8, com os mesmos valores fictícios (`changeme`, `APP_PORT=30XX`). Comentário acima do `APP_PORT`: a porta é definida no Módulo 06 e `30XX` é inválido de propósito |
| `.gitattributes` | Regra nova `api/** text eol=lf`: Dockerfile, `.env` e scripts rodam no Linux do glpi-srv |

### Runner de migrações

Não há ferramenta de migração (Alembic ou equivalente), então não houve ADR. A §5 já
previa SQL com nome datado, e o volume é baixo. O runner próprio tem cerca de 40 linhas
em `api/app/db.py`:

- Nome obrigatório `NNNN_YYYYMMDD_descricao.sql` (regex `MIGRATION_NAME`). Um nome fora
  do padrão levanta `ValueError` e interrompe a inicialização.
- Tabela de controle `schema_migrations (version INTEGER PRIMARY KEY, name, applied_at)`,
  criada pelo próprio runner com `CREATE TABLE IF NOT EXISTS`.
- **Uma transação por arquivo.** A conexão abre com `isolation_level=None`, e cada
  arquivo roda num único `executescript()` montado como `BEGIN;` + conteúdo +
  `INSERT INTO schema_migrations ...` + `COMMIT;`. O `executescript()` só faz `COMMIT`
  implícito de uma transação *pendente antes* da chamada. Como o `BEGIN` está dentro do
  script, essa transação não existe. Em qualquer `sqlite3.Error` o runner faz `ROLLBACK`
  (se `in_transaction`) e repropaga o erro: nem as instruções anteriores do arquivo nem a
  linha da versão ficam gravadas.
- **Arquivos de migração não podem conter controle de transação.** `BEGIN`, `COMMIT`,
  `END`, `ROLLBACK`, `SAVEPOINT` e `RELEASE` são proibidos, porque o runner é o dono da
  transação: um `COMMIT` no meio do arquivo gravaria as instruções anteriores mesmo que
  as seguintes falhassem. `reject_transaction_control()` recusa o arquivo com
  `ValueError` antes de executar qualquer instrução. A função divide o script com
  `statements()`, que usa `sqlite3.complete_statement()` para não cortar `;` dentro de
  aspas nem o corpo `BEGIN ... END` de um `CREATE TRIGGER`. Depois remove os comentários
  iniciais de cada instrução e compara a primeira palavra.
- `version` e `name` entram no SQL por interpolação. Os dois são restritos pela regex
  (dígitos, e `[a-z0-9_]` no nome), então não há como injetar aspas.

### `/v1/saude`

`db.check()` abre o banco com `Path(database_path).absolute().as_uri() + "?mode=ro"` e
`uri=True`. Com o arquivo ausente, a abertura falha em vez de criar um banco vazio. Em
seguida executa `SELECT 1 FROM schema_migrations LIMIT 1`, que só passa se o runner já
rodou. Qualquer `sqlite3.Error` vira `503 {"status":"erro"}`.

### Escolhas feitas no caminho

- **`pydantic-settings` como dependência nova.** É a única além da §2. Ela resolve
  leitura de `.env`, conversão de tipos (`"false"` → `False`) e validação no mesmo
  modelo Pydantic que a API já usa. A alternativa com `os.environ` puro exigiria parsing
  manual de booleanos e inteiros em cada módulo seguinte. Traz `python-dotenv` como
  transitiva.
- **`Settings` enxuta.** Só as variáveis usadas neste módulo viram campo. As outras da
  §8 ficam no `.env.example` e são ignoradas (`extra="ignore"`) até o módulo que as usa.
  `APP_PORT` é lida só pelo compose e pelo `CMD` do Dockerfile.
- **Docs só pela flag.** `APP_ENABLE_DOCS=false` é o padrão do código e do
  `.env.example`. `APP_ENV` não altera nada neste módulo.
- **Nome de projeto fixo no compose (`name: tecnico-assistente`).** Sem ele, o volume
  se chamaria `<pasta>_tecnico-data`. Se o deploy mudasse de diretório, a API subiria com
  um banco novo e vazio, e o histórico ficaria órfão num volume antigo.
- **Testes dentro da imagem de produção.** A máquina de desenvolvimento só tem o Python
  3.11.9 (`py -0`), e o TA-ADR-004 fixa o 3.12. O pytest roda em
  `python:3.12.14-slim-trixie`, a mesma tag do `Dockerfile`.
- **Sem `HEALTHCHECK` no Dockerfile.** O health check do deploy (Módulo 06) chama
  `/v1/saude` em `127.0.0.1` a partir do servidor (TA-ADR-009).

## Verificação realizada

Ambiente: máquina de desenvolvimento, Windows 11 Pro 10.0.26340, Docker 29.6.1, Docker
Compose v5.3.0. Pytest e container em `python:3.12.14-slim-trixie` (Python 3.12.14,
SQLite 3.46.1). Para o container local foi criado um `api/.env` temporário a partir do
`.env.example` com `APP_PORT=3099`, porta só de teste local e não de produção (ignorado pelo Git, conferido com `git check-ignore`),
apagado ao fim, com `docker compose down -v`.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Suite completa | `docker run ... python:3.12.14-slim-trixie ... pytest -q` (comando do `CLAUDE.md`), commit `e285c47` | ✅ 24 passed, 1 warning (ver Pontos de atenção) |
| Modelo padrão aceito | `test_default_model_is_allowed` | ✅ `mimo-v2.6-flash` |
| Modelo permitido com espaços | `test_allowed_model_is_trimmed` | ✅ `" glm-5.3-flash "` → `glm-5.3-flash` |
| TA-ADR-011: caixa e espaço | `test_forbidden_model_is_rejected` com `muse-spark-x`, `" Muse-Spark-x "`, `MUSE-SPARK-1` | ✅ `ValidationError` com "TA-ADR-011" nos três |
| TA-ADR-011 na inicialização | `test_forbidden_model_in_environment_stops_startup` (`OPENCODE_GO_MODEL=" Muse-Spark-x "`) | ✅ `create_app()` levanta `ValidationError` |
| TA-ADR-011 no container real | `.env` com `OPENCODE_GO_MODEL=muse-spark-x`, `docker compose up -d`, `docker logs` | ✅ o processo não sobe: log com `muse-spark-* models are forbidden (TA-ADR-011)`, `RestartCount` 3 em 5 s |
| Migrações em ordem, uma vez | `test_applies_pending_migrations_in_order_once` (arquivos criados fora de ordem, `migrate` duas vezes) | ✅ versões `[1, 2]`, tabelas criadas |
| Migração falha na 2ª instrução | `test_failed_migration_leaves_nothing_applied` (`CREATE TABLE partial` + `INSERT INTO missing`) | ✅ `OperationalError`; versões `[1]`; `partial` não existe |
| O teste de atomicidade pega o defeito | Mutação A: `BEGIN;`/`COMMIT;` removidos do script numa cópia de `db.py` dentro do container | ✅ `test_failed_migration_leaves_nothing_applied` falha: `partial` aparece em `sqlite_master` |
| `BEGIN`/`COMMIT` na migração | `test_transaction_control_in_migration_is_refused`, 6 casos: `BEGIN`…`COMMIT`, `commit` minúsculo na mesma linha, `BEGIN TRANSACTION` depois de comentário `--`, `END` depois de `/* */`, `SAVEPOINT`/`RELEASE`, `ROLLBACK` sem `;` final | ✅ `ValueError` nos 6; nenhuma versão registrada; tabela `x` não criada |
| Trigger e palavra-chave entre aspas | `test_trigger_and_quoted_keywords_are_allowed` (`CREATE TRIGGER ... BEGIN ... END;` e `'x; COMMIT; y'`) | ✅ aplicada, versão `[1]` |
| O teste do guard pega o defeito | Mutação B: chamada a `reject_transaction_control` trocada por `pass` numa cópia de `db.py` | ✅ os 6 casos de `test_transaction_control_in_migration_is_refused` falham |
| Nome de migração inválido | `test_invalid_migration_name_is_refused` (`1_sem_data.sql`) | ✅ `ValueError` |
| `/v1/saude` sem detalhes | `test_saude_ok_without_internal_details` e `curl http://127.0.0.1:3099/v1/saude` no container | ✅ `200`, corpo exatamente `{"status":"ok"}`, sem versão |
| Banco ausente | `test_saude_missing_database_returns_503_and_creates_nothing` | ✅ `503 {"status":"erro"}`; o arquivo continua inexistente depois da chamada |
| `/v1/saude` no container real depois da migração | `docker compose up -d --build` (commit `e285c47`), `docker exec tecnico-api` com `id`, `stat -c "%u:%g"` e leitura `mode=ro` de `sqlite_master`, depois `curl` | ✅ processo `uid=10001(app)`; `/data` `10001:0`; `/data/tecnico.db` `10001:999`; `schema_migrations` criada (0 linhas: nenhuma migração ainda); `200 {"status":"ok"}` |
| Banco ausente no container real | `docker exec tecnico-api rm /data/tecnico.db`, `curl`, `ls -A /data` | ✅ `503 {"status":"erro"}`; `/data` continua vazio (a consulta `mode=ro` não criou arquivo) |
| Recuperação depois do 503 | `docker compose restart`, `curl` | ✅ o `lifespan` recria o banco (`10001:999`) e volta `200 {"status":"ok"}` |
| Docs desligados | Testes com `APP_ENABLE_DOCS` padrão e `curl` no container com `APP_ENABLE_DOCS=false` | ✅ `/docs`, `/redoc` e `/openapi.json` → `404` nos dois |
| Docs ligados pela flag | `test_docs_enabled_by_flag` | ✅ as três rotas → `200` |
| Porta só em loopback | `docker compose config` | ✅ `host_ip: 127.0.0.1`, `published: "3099"`, `target: 3099` |
| Porta só em loopback | `docker port tecnico-api` | ✅ `3099/tcp -> 127.0.0.1:3099` (nenhuma linha `0.0.0.0`) |
| Outra interface do host | `curl` em `172.19.48.1:3099` (primeira IPv4 não loopback, adaptador virtual) | ✅ sem conexão (código `000`) |
| `restart`, `TZ`, usuário, volume | `docker inspect`, `docker exec ... date +%Z; id -un; ls -l /data`, `docker volume ls` | ✅ `always`; `-03`; `app`; `tecnico.db` de `app:app`; volume `tecnico-assistente_tecnico-data` |
| `.env` fora do Git | `git check-ignore -v api/.env` e `git status --short` antes de cada commit | ✅ `.gitignore:2:.env`; nenhum `.env` nem `*.db` preparado |

## Decisões

Nenhum ADR novo. O runner próprio segue a §5, e `pydantic-settings` e o nome fixo do
projeto no compose estão registrados acima, em "Escolhas feitas no caminho". O TA-ADR-021
fica livre.

## Dependências entre módulos

- **Módulo 02** cria a primeira migração (`0001_YYYYMMDD_...sql` com `carretas_tokens` e
  `tokens_auditoria`) e acrescenta os campos que usar à `Settings`
  (`RATE_LIMIT_PER_TOKEN_PER_HOUR`, `MAX_BODY_BYTES`).
- **Módulo 03** acrescenta `OPENCODE_GO_API_KEY` e `OPENCODE_GO_TIMEOUT_SECONDS` à
  `Settings`. A chave deve ser `SecretStr`, para não aparecer em log nem em `repr`.
- **Módulo 05** usa no CI a mesma imagem e os mesmos arquivos de requirements.
- **Módulo 06** faz o deploy com este compose e o health check em
  `127.0.0.1:${APP_PORT}/v1/saude`. O volume `tecnico-assistente_tecnico-data` precisa
  entrar no backup do glpi-srv (TA-ADR-004).

## Pontos de atenção

- **Aviso do Starlette 1.7 sobre o `httpx`.** O `TestClient` avisa que usar `httpx` com
  `starlette.testclient` está depreciado e sugere o `httpx2`. Não quebra nada hoje. O
  `httpx` continua na stack porque é o cliente HTTP de saída (§2). A troca deve ser
  revista quando uma atualização do Starlette remover o suporte.
- **`APP_PORT=30XX` no `.env.example` não é uma porta válida.** O valor é o da §8, de
  propósito, e o comentário acima da linha avisa que a porta é definida no Módulo 06.
  Sem trocar o valor, o `docker compose config` falha com `invalid containerPort: 30XX`
  (conferido). A 3099 usada na verificação é só porta de teste local.
- **Migração sem `BEGIN`/`COMMIT`.** Quem escrever a primeira migração (Módulo 02) não
  deve abrir nem fechar transação no arquivo: o runner recusa, e a inicialização para
  com `ValueError`.
- **A pasta `api/app/migrations/` não existe no Git.** Ela passa a existir com a
  primeira migração do Módulo 02. O `Dockerfile` copia `app/` inteiro, então não
  precisa de ajuste.
- **O container roda sem root.** Um volume nomeado novo herda o dono de `/data` da
  imagem (`app`). Um bind mount do host em `/data` não herda o dono e precisaria de
  `chown` para o uid 10001.
- **Sem `app` global em `app/main.py`.** Qualquer comando novo de uvicorn precisa de
  `--factory app.main:create_app`.

## Commits

```
e44e907 docs: fix module 00.1 defect count in plan
c96e250 chore(api): pin dependencies and set up pytest with a temporary database
4e47184 feat(api): add numbered SQL migration runner with one transaction per file
3102fb9 feat(api): add settings with TA-ADR-011 model guard and app factory with docs off by default
555e40d feat(api): add GET /v1/saude with read-only database check
365ec54 chore(api): add Dockerfile and compose with loopback-only port
c175c7f docs: document module 01 api core
e285c47 feat(api): refuse transaction control statements in migration files
126a9f8 chore(api): explain placeholder APP_PORT in env example
```

O commit `docs: update module 01 after PR review` fecha a lista.
