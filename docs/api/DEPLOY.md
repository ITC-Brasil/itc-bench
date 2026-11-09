# Deploy da API

A API roda no glpi-srv, no container `tecnico-api`, publicado só em `127.0.0.1` (TA-ADR-009) e
exposto pelo túnel da Cloudflare no domínio da API (com Cloudflare Access). O deploy sai deste
repositório desde o Módulo 03 (ADR-012); até lá saía de `ITC-Brasil/tecnico-assistente`.
Endereços, porta, usuário e diretório reais **não** ficam aqui: estão nos secrets do environment
`producao` e no servidor.

## Pipeline

| Arquivo | Quando roda | O que faz |
|---|---|---|
| `.github/workflows/api-ci.yml` | PR e push em `develop`/`main` que mudem `api/**`; chamado pelo deploy | pytest dentro de `python:3.12.14-slim-trixie` (comando do `AGENTS.md`) |
| `.github/workflows/gitleaks.yml` | Todo PR e push em `develop`/`main` | gitleaks 8.30.1 (binário da release, SHA-256 conferido) no histórico inteiro |
| `.github/workflows/api-deploy.yml` | Push na `main` que mude `api/**`; manual (`workflow_dispatch`) na `main` (ADR-012) | Job `test` (o `api-ci.yml` por `workflow_call`); job `deploy` no environment `producao`, só depois dele verde |
| `.github/dependabot.yml` | Semanal | PRs para a `develop`: `pip` em `/api`, `uv` em `/app`, actions |

Todas as `uses:` estão fixadas por SHA completo, com a versão em comentário.

## O que o job de deploy faz

1. Grava `DEPLOY_SSH_KEY` em `~/.ssh/id_deploy` (600) e `DEPLOY_KNOWN_HOSTS` em
   `~/.ssh/known_hosts`. Nunca `StrictHostKeyChecking=no` nem `ssh-keyscan` no deploy.
2. `ssh -p $DEPLOY_PORT -o StrictHostKeyChecking=yes -o BatchMode=yes` e executa no servidor, com
   SHA, porta e diretório como argumentos do script:
   - `cd "$DEPLOY_DIR"`, `git checkout main`, `git pull --ff-only origin main`;
   - confere que `HEAD` é o commit testado (`GITHUB_SHA`); se a `main` andou, para com erro;
   - `cd api && docker compose up -d --build`;
   - até 30 tentativas, a cada 2 s, de `curl -fsS http://127.0.0.1:${DEPLOY_APP_PORT}/v1/saude`.
     Sem `200` em 60 s, mostra `docker compose ps` e as últimas 50 linhas do log e falha.
3. Apaga a chave do runner (`if: always()`).

`concurrency: deploy-glpi-srv`, sem cancelar o deploy em andamento.

## Secrets (environment `producao`, restrito à branch `main`)

Settings → Environments → `producao` → Deployment branches: `main`. Só nomes aqui; os valores são
os mesmos do tecnico-assistente, mais `DEPLOY_DIR`.

| Secret | Conteúdo |
|---|---|
| `DEPLOY_HOST` | Host SSH externo do glpi-srv |
| `DEPLOY_PORT` | Porta SSH externa |
| `DEPLOY_USER` | Usuário de deploy (grupo `docker`) |
| `DEPLOY_SSH_KEY` | Chave privada ed25519 do usuário de deploy, sem senha |
| `DEPLOY_KNOWN_HOSTS` | Linha(s) do `known_hosts` do servidor, conferidas pelo responsável |
| `DEPLOY_APP_PORT` | O mesmo `APP_PORT` do `api/.env` do servidor |
| `DEPLOY_DIR` | Caminho absoluto do clone no servidor (o `working_dir` do compose do `tecnico-api`) |

## Servidor

- **Diretório:** `<diretório de deploy>` (secret `DEPLOY_DIR`). Não muda com a migração.
- **Projeto compose:** `name: tecnico-assistente` fixo em `api/docker-compose.yml`, então o volume
  continua `tecnico-assistente_tecnico-data`, qualquer que seja o nome da pasta.
- **`.env`:** só no servidor, em `api/.env`, mantido à mão; ignorado pelo `.gitignore` da raiz.
- **Banco:** `DATABASE_PATH` do `api/.env` (padrão `/data/tecnico.db` em `api/app/config.py`), no
  volume. É a fonte da verdade (TA-ADR-005).
- **Acesso ao GitHub:** deploy key SSH só de leitura, própria do servidor, pelo apelido
  `github-itc-bench` (ADR-012).
- **O servidor hospeda outros projetos com deploy key própria.** Nunca crie um bloco
  `Host github.com` genérico no `~/.ssh/config` nem mude o `core.sshCommand` de outros
  repositórios: cada deploy key tem o seu apelido de host.

## Acesso do servidor ao itc-bench (deploy key) — responsável, uma vez

No servidor, como o usuário de deploy:

```
ssh-keygen -t ed25519 -N "" -C "glpi-srv itc-bench deploy (somente leitura)" -f ~/.ssh/itc_bench_deploy
cat >> ~/.ssh/config <<'EOF'
Host github-itc-bench
    HostName github.com
    User git
    IdentityFile ~/.ssh/itc_bench_deploy
    IdentitiesOnly yes
    StrictHostKeyChecking yes
EOF
chmod 600 ~/.ssh/config
```

O apelido `github-itc-bench` vale só para este repositório; os outros projetos do servidor
continuam com a configuração deles. Não acrescente nem altere bloco `Host github.com`.

Host key do GitHub fixada: grave em `~/.ssh/known_hosts` a linha `github.com ssh-ed25519 ...`
copiada da página oficial "GitHub's SSH key fingerprints" (docs.github.com) e confira:

```
ssh-keygen -lf ~/.ssh/known_hosts -F github.com
```

A busca é por `github.com` (o `HostName`), não pelo apelido: o ssh confere a host key pelo nome real.

A impressão digital SHA256 mostrada precisa ser igual à publicada pelo GitHub para ED25519.

Cadastre `~/.ssh/itc_bench_deploy.pub` em itc-bench → Settings → Deploy keys → Add deploy key,
**sem** "Allow write access". Teste:

```
ssh -T git@github-itc-bench
```

Esperado: `Hi ITC-Brasil/itc-bench! You've successfully authenticated, but GitHub does not provide shell access.`

## Transição do tecnico-assistente para o itc-bench (Módulo 03, uma vez)

Ordem obrigatória. Entre o passo 1 e o 7, nenhum merge na `main` do tecnico-assistente.

1. **No TA:** PR que deixa o `deploy.yml` só com `workflow_dispatch` (sem `push`).
2. **Secrets e environment** `producao` criados no itc-bench; deploy key cadastrada e testada
   (seção anterior).
3. **Caminho real do banco:** `docker exec tecnico-api printenv DATABASE_PATH` (vazio = padrão
   `/data/tecnico.db`). Use esse caminho abaixo como `<banco>`.
4. **Backup** (como o usuário de deploy):

   ```
   docker exec tecnico-api python -c "import sqlite3; s=sqlite3.connect('<banco>'); d=sqlite3.connect('/data/tecnico-antes-monorepo.db'); s.backup(d); d.close()"
   mkdir -p ~/backup && chmod 700 ~/backup
   docker cp tecnico-api:/data/tecnico-antes-monorepo.db ~/backup/tecnico-antes-monorepo.db
   docker exec tecnico-api rm /data/tecnico-antes-monorepo.db
   sha256sum ~/backup/tecnico-antes-monorepo.db
   ```

   O SHA-256 vai para `docs/modules/03-monorepo.md`.
5. **`.env` continua ignorado:** no clone, `git check-ignore -v api/.env` deve apontar uma regra
   `.env`. Depois do passo 6, repita: deve apontar `.gitignore:<linha>:.env` do itc-bench.
6. **Troca do remote** (o `main` do itc-bench não descende do `main` do TA, então `pull --ff-only`
   não serve aqui):

   ```
   cd <diretório de deploy>
   git rev-parse HEAD                      # anote: SHA do TA em produção, para rollback
   git remote set-url origin git@github-itc-bench:ITC-Brasil/itc-bench.git
   git fetch origin main
   git checkout -B main origin/main
   git status --short                      # vazio; api/.env não aparece
   ls -l api/.env
   ```

   O container continua rodando o build anterior até o passo 7.
7. **Primeiro deploy:** Actions → `api-deploy` → Run workflow na `main`.
8. **Verificação:** tabela abaixo, inclusive o relatório de teste.
9. **Depois de tudo verde:** PR aqui devolvendo o gatilho de `push` em `api/**` ao
   `api-deploy.yml` (feito em 2026-11-04); PR no TA trocando o README para apontar este
   repositório, depois da troca da pasta de deploy. Arquivamento do TA é do responsável.

## Cloudflare Access: Bypass para o Bench (responsável, uma vez)

O Bench nos notebooks não tem service token: as rotas `/v1/bench/` se autenticam pela sessão do
técnico (`Authorization: Bearer`). Sem o Bypass, o Access responde 403 e o login falha em todos
os notebooks.

1. Zero Trust → Access → Applications → Add an application → **Self-hosted**.
2. Domínio da API, caminho `v1/bench/`. Aplicação **separada** da aplicação do service token das
   carretas, que continua cobrindo o resto do domínio.
3. Política: ação **Bypass**, regra **Everyone**.

Verificação, de qualquer máquina fora do servidor (no PowerShell 5.1, `curl` é apelido do
`Invoke-WebRequest`; use `curl.exe`):

```
curl.exe -s -D - -o NUL https://<endereço da API>/v1/bench/sessao
```

| Resposta | Significado |
|---|---|
| `401` com `www-authenticate: Bearer`, sem cabeçalho `Cf-Access-*` | Bypass certo: a API respondeu |
| `403` com `Cf-Access-*` | Bypass ausente ou caminho errado: o Access barrou |
| `502` ou `530` | Túnel ou container fora |
## Verificação pós-deploy

| Cenário | Como verificar | Esperado |
|---|---|---|
| Workflow verde | Aba Actions, run do `api-deploy` | `test` e `deploy` verdes; `healthy after N attempt(s), commit <sha>` |
| Commit no servidor | `git -C <diretório de deploy> rev-parse HEAD` | SHA da `main` do itc-bench |
| Remote | `git -C <diretório de deploy> remote -v` | `git@github-itc-bench:ITC-Brasil/itc-bench.git` |
| Mesmo container e volume | `docker inspect tecnico-api --format '{{range .Mounts}}{{.Name}}{{end}}'` | `tecnico-assistente_tecnico-data` |
| Porta só em loopback | `docker port tecnico-api` | `<APP_PORT>/tcp -> 127.0.0.1:<APP_PORT>` |
| Saúde local | `curl -s http://127.0.0.1:<APP_PORT>/v1/saude` | `{"status":"ok"}` |
| Saúde pelo túnel, com service token | `curl -s -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." https://<domínio da API>/v1/saude` | `{"status":"ok"}` |
| Bypass do Bench | `curl.exe -s -D - -o NUL https://<endereço da API>/v1/bench/sessao` | `401` com `www-authenticate: Bearer`, sem `Cf-Access-*` (seção acima) |
| Borda sem service token | `curl -s -o /dev/null -w '%{http_code}' https://<domínio da API>/v1/saude` | `302` ou `403`, nunca `200` |
| Migrações | `docker exec tecnico-api python -c "import sqlite3; print(sqlite3.connect('<banco>').execute('select version from schema_migrations').fetchall())"` | Iguais às de antes da troca |
| Relatório de teste | Token de carreta de teste (`python -m app.tokens create --carreta TESTE-MONOREPO ...`), `POST /v1/relatorio` com uma sessão de fixture, depois `revoke` | `200` com laudo; linha no SQLite; espelho no NocoDB |

## Rollback

Só manual: depois da troca do remote, o `workflow_dispatch` do TA puxaria o remote novo.

```
cd <diretório de deploy>
git remote set-url origin <remote anterior do TA>   # o que estava antes do passo 6, sem o apelido
git fetch origin main
git checkout -B main origin/main          # ou o SHA anotado no passo 6
cd api && docker compose up -d --build
curl -fsS http://127.0.0.1:<APP_PORT>/v1/saude
```

O código da API não muda nesta migração, então o banco não é afetado. Se for, confira o SHA-256
do backup e restaure com o container parado (o arquivo precisa ficar com o dono `app`, uid 10001):

```
sha256sum ~/backup/tecnico-antes-monorepo.db
cd <diretório de deploy>/api && docker compose stop
docker run --rm -v tecnico-assistente_tecnico-data:/data -v ~/backup:/b:ro python:3.12.14-slim-trixie \
  sh -c 'rm -f <banco>-wal <banco>-shm && cp /b/tecnico-antes-monorepo.db <banco> && chown 10001 <banco>'
docker compose start
```

**Migrações não são desfeitas** (`api/app/db.py` só aplica para a frente). Uma migração que remova
ou renomeie precisa de ADR com o plano de volta.

## Módulo 06 do Bench: backup antes da migração `0006`

A `0006` reconstrói `diagnosticos` (TA-ADR-028) numa transação: mantém ids e
`relatorios.diagnostico_id`, mas um defeito só se desfaz pelo backup. Antes do deploy, como o
usuário de deploy:

```
docker exec tecnico-api python -c "import sqlite3; s=sqlite3.connect('<banco>'); d=sqlite3.connect('/data/tecnico-antes-0006.db'); s.backup(d); d.close()"
docker cp tecnico-api:/data/tecnico-antes-0006.db ~/backup/tecnico-antes-0006.db
chmod 600 ~/backup/tecnico-antes-0006.db
docker exec tecnico-api rm /data/tecnico-antes-0006.db
sha256sum ~/backup/tecnico-antes-0006.db
python3 -c "import sqlite3,os; print(sqlite3.connect(os.path.expanduser('~/backup/tecnico-antes-0006.db')).execute('PRAGMA integrity_check').fetchone())"
```

Depois do deploy: `PRAGMA integrity_check` = `ok`, `PRAGMA foreign_key_check` vazio,
`SELECT count(*) FROM diagnosticos` igual ao de antes, migrações `[1..6]`.

**Restauração** (código anterior de volta e banco do backup, com o container parado; dono `app`,
uid 10001):

```
cd <diretório de deploy>
git checkout <SHA anterior ao merge>
sha256sum ~/backup/tecnico-antes-0006.db          # confere com o anotado
cd api && docker compose stop
docker run --rm -v tecnico-assistente_tecnico-data:/data -v ~/backup:/b:ro python:3.12.14-slim-trixie \
  sh -c 'rm -f <banco>-wal <banco>-shm && cp /b/tecnico-antes-0006.db <banco> && chown 10001 <banco>'
docker compose up -d --build
curl -fsS http://127.0.0.1:<APP_PORT>/v1/saude
```
