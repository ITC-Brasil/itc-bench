# Módulo 06 — Deploy inicial no glpi-srv

**Branch:** `module/06-initial-deploy` (a partir da `module/05-ci-cd`) · **Data:**
2026-09-28 · **Escopo:** `PROMPT_CLAUDE_CODE.md` §9, §15 (Módulo 06) e §16

**Módulo de preparação.** Tudo que depende do glpi-srv, da Cloudflare, do GitHub
(secrets) e do Uptime Kuma é passo do responsável. Este documento entrega os comandos na
ordem de execução e a tabela de verificação de cada etapa, com a coluna de resultado
**a preencher**. Nenhum passo foi executado nesta sessão: não há acesso ao servidor.
Nenhum código mudou.

Convenções:
- `30XX` é a porta escolhida na etapa 3. Substitua em todos os comandos.
- `admin$` é o terminal do responsável (PowerShell ou bash) com `gh` autenticado;
  `srv$` é o glpi-srv como o usuário administrador; `deploy$` é o glpi-srv como
  `<usuário de deploy>`.
- Nenhum valor secreto aparece aqui. Todo segredo vai para o Vaultwarden no momento em
  que é criado.

## Ordem

| # | Etapa | Onde | Depende de |
|---|---|---|---|
| 1 | Conferir o servidor | glpi-srv | — |
| 2 | Usuário `<usuário de deploy>` e chave SSH | glpi-srv + estação | 1 |
| 3 | Porta | glpi-srv | 1 |
| 4 | Clone por Fine-grained PAT | GitHub + glpi-srv | 2 |
| 5 | `.env` do servidor | glpi-srv | 3, 4 |
| 6 | Secrets do repositório e host key | estação | 2, 3 |
| 7 | Rota `diag.exemplo.invalid` no túnel | glpi-srv + Cloudflare | 3 |
| 8 | Aplicação Cloudflare Access e service token | Cloudflare Zero Trust | 7 |
| 9 | Primeiro deploy pelo pipeline | GitHub | 5, 6 e merges |
| 10 | NocoDB, tokens das carretas e cenário 6 | NocoDB + glpi-srv | 9 |
| 11 | Uptime Kuma, Homepage e backup | glpi-srv | 9 |
| 12 | Verificação ponta a ponta | estação Windows | 8, 10 |

## 1. Conferir o servidor

```
srv$ docker --version
srv$ docker compose version
srv$ git --version
srv$ curl --version | head -1
srv$ cloudflared --version
srv$ systemctl is-active cloudflared
```

| Verificação | Esperado | Resultado |
|---|---|---|
| Docker e Compose | Compose v2 (`docker compose`, não `docker-compose`) | a preencher |
| `git` e `curl` | Instalados (o deploy usa os dois) | a preencher |
| `cloudflared` como serviço | `active` | a preencher |

Registre as versões do Docker e do Compose na §2 de `documentacao-tecnico-assistente.md`
(hoje "a conferir no glpi-srv").

## 2. Usuário `<usuário de deploy>` e chave SSH

O deploy entra como `<usuário de deploy>`, usuário que já existe no servidor. No servidor:

```
srv$ id <usuário de deploy>
srv$ sudo usermod -aG docker <usuário de deploy>
srv$ sudo install -d -m 700 -o <usuário de deploy> -g <usuário de deploy> /home/<usuário de deploy>/.ssh
```

Na estação, gere o par só para este deploy (sem senha, porque o Actions não digita):

```
admin$ ssh-keygen -t ed25519 -N "" -C "github-actions tecnico-assistente" -f <usuário de deploy>-tecnico
```

Acrescente o conteúdo de `<usuário de deploy>-tecnico.pub` numa linha nova no fim do arquivo,
sem apagar as chaves que já estão lá:

```
srv$ sudo nano /home/<usuário de deploy>/.ssh/authorized_keys
srv$ sudo chown <usuário de deploy>:<usuário de deploy> /home/<usuário de deploy>/.ssh/authorized_keys
srv$ sudo chmod 600 /home/<usuário de deploy>/.ssh/authorized_keys
```

Guarde a chave privada (`<usuário de deploy>-tecnico`) no Vaultwarden. Ela vira o secret
`DEPLOY_SSH_KEY` na etapa 6 e depois é apagada da estação.

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Login com a chave nova | `admin$ ssh -i <usuário de deploy>-tecnico -p <porta SSH> <usuário de deploy>@glpi.exemplo.invalid id` | `uid=...(<usuário de deploy>) ... docker` | a preencher |
| Acesso ao Docker | `admin$ ssh -i <usuário de deploy>-tecnico -p <porta SSH> <usuário de deploy>@glpi.exemplo.invalid docker ps` | Lista de containers, sem `permission denied` | a preencher |

O grupo `docker` equivale a root no host. É o requisito do §16; a chave fica só no secret
e no Vaultwarden.

## 3. Porta

```
srv$ sudo ss -tlnp | grep -E ':30[0-9]{2}\b'
```

Escolha uma porta `30XX` que não apareça na saída nem esteja reservada nos documentos do
glpi-srv. O `30XX` do `.env.example` é inválido de propósito; `3099` foi porta de teste
local.

| Verificação | Esperado | Resultado |
|---|---|---|
| Porta livre | Nenhuma linha com a porta escolhida | a preencher (porta: ____) |

## 4. Clone por Fine-grained PAT

Deploy keys SSH são bloqueadas no GitHub Free da organização, então o servidor clona por
HTTPS com um PAT.

1. GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token.
   Resource owner **ITC-Brasil**, Repository access **Only select repositories** →
   `tecnico-assistente`, Permissions → Repository → **Contents: Read and write** (§16;
   o `git pull` só precisa de leitura, e `Read-only` também funcionaria). Validade de até
   1 ano, com lembrete para renovar. Guarde no Vaultwarden.
2. No servidor, como `<usuário de deploy>`:

```
srv$ sudo -iu <usuário de deploy>
deploy$ git config --global credential.helper store
deploy$ mkdir -p ~/docker && cd ~/docker
deploy$ git clone https://github.com/ITC-Brasil/tecnico-assistente.git
deploy$ cd tecnico-assistente && git checkout main
deploy$ chmod 600 ~/.git-credentials
```

No `git clone`, o usuário é o seu login do GitHub e a senha é o PAT. O `credential.helper
store` grava o PAT em `~/.git-credentials` (texto puro, modo 600, só o `<usuário de deploy>` lê),
para os `git pull` do deploy.

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Clone no caminho do deploy | `deploy$ git -C ~/docker/tecnico-assistente remote -v` | `https://github.com/ITC-Brasil/tecnico-assistente.git` (sem o PAT na URL) | a preencher |
| Pull sem pedir senha | `deploy$ git -C ~/docker/tecnico-assistente pull --ff-only origin main` | `Already up to date.` sem prompt | a preencher |
| Branch | `deploy$ git -C ~/docker/tecnico-assistente branch --show-current` | `main` | a preencher |

## 5. `.env` do servidor

```
deploy$ cd ~/docker/tecnico-assistente/api
deploy$ cp .env.example .env
deploy$ chmod 600 .env
deploy$ nano .env
```

| Variável | Valor |
|---|---|
| `APP_PORT` | a porta da etapa 3 |
| `OPENCODE_GO_API_KEY` | a chave do Go (Vaultwarden) |
| `OPENCODE_GO_MODEL` | `mimo-v2.6-flash` (nunca `muse-spark-*`: o container não sobe, TA-ADR-011) |
| `NOCODB_ENABLED` / `NOCODB_TOKEN` / `NOCODB_TABLE_ID` | `false` até a etapa 10; depois `true`, o token e o id da tabela |
| `NTFY_ENABLED` / `NTFY_TOKEN` | `true` e o token de publicação no tópico `itc-infra` |

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Fora do Git | `deploy$ git -C ~/docker/tecnico-assistente status --short` | Nada (o `.env` é ignorado) | a preencher |
| Permissão | `deploy$ stat -c '%a %U' .env` | `600 <usuário de deploy>` | a preencher |
| Compose lê a porta | `deploy$ docker compose config \| grep -A2 ports` | `host_ip: 127.0.0.1`, `published: "30XX"` | a preencher |

## 6. Secrets do repositório e host key

A host key do servidor é obtida e **conferida contra o próprio servidor** antes de virar
secret. Na estação:

```
admin$ ssh-keyscan -p <porta SSH> -t ed25519 glpi.exemplo.invalid > known_hosts_glpi
admin$ ssh-keygen -lf known_hosts_glpi
```

No servidor, pelo console ou por uma sessão SSH já confiável:

```
srv$ ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

As duas impressões digitais (`SHA256:...`) precisam ser iguais. Se forem diferentes,
**pare**: o `ssh-keyscan` falou com outra máquina.

Com as impressões iguais, grave os seis secrets:

```
admin$ gh secret set DEPLOY_HOST -R ITC-Brasil/tecnico-assistente --body "glpi.exemplo.invalid"
admin$ gh secret set DEPLOY_PORT -R ITC-Brasil/tecnico-assistente --body "<porta SSH>"
admin$ gh secret set DEPLOY_USER -R ITC-Brasil/tecnico-assistente --body "<usuário de deploy>"
admin$ gh secret set DEPLOY_APP_PORT -R ITC-Brasil/tecnico-assistente --body "30XX"
admin$ gh secret set DEPLOY_SSH_KEY -R ITC-Brasil/tecnico-assistente < <usuário de deploy>-tecnico
admin$ gh secret set DEPLOY_KNOWN_HOSTS -R ITC-Brasil/tecnico-assistente < known_hosts_glpi
```

Depois apague `<usuário de deploy>-tecnico` e `known_hosts_glpi` da estação (a privada já está
no Vaultwarden).

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Impressões iguais | Comparação acima | Mesmo `SHA256:` | a preencher |
| Seis secrets | `admin$ gh secret list -R ITC-Brasil/tecnico-assistente` | `DEPLOY_APP_PORT`, `DEPLOY_HOST`, `DEPLOY_KNOWN_HOSTS`, `DEPLOY_PORT`, `DEPLOY_SSH_KEY`, `DEPLOY_USER` | a preencher |
| `DEPLOY_APP_PORT` = `APP_PORT` | Comparação com o `.env` | Iguais | a preencher |

## 7. Rota `diag.exemplo.invalid` no túnel

Edite o arquivo do túnel `<túnel cloudflared>` e acrescente a rota **antes** do catch-all
(`service: http_status:404`), que precisa continuar sendo a última regra:

```
srv$ nano ~/.cloudflared/config.yml
```

```yaml
ingress:
  # ... rotas existentes ...
  - hostname: diag.exemplo.invalid
    service: http://localhost:30XX
  - service: http_status:404
```

```
srv$ cloudflared tunnel --config ~/.cloudflared/config.yml ingress validate
srv$ cloudflared tunnel --config ~/.cloudflared/config.yml ingress rule https://diag.exemplo.invalid
srv$ sudo cp ~/.cloudflared/config.yml /etc/cloudflared/config.yml
srv$ sudo systemctl restart cloudflared
srv$ systemctl status cloudflared --no-pager | head -5
srv$ cloudflared tunnel route dns <túnel cloudflared> diag.exemplo.invalid
```

O último comando cria o CNAME `diag` para o túnel; se o registro já existir, ele avisa e
não muda nada.

| Verificação | Esperado | Resultado |
|---|---|---|
| `ingress validate` | `OK` | a preencher |
| `ingress rule https://diag.exemplo.invalid` | Casa com a regra `diag.exemplo.invalid` → `http://localhost:30XX`, não com o catch-all | a preencher |
| Serviço depois do restart | `active (running)`; as outras rotas do túnel continuam respondendo | a preencher |
| DNS | `nslookup diag.exemplo.invalid` resolve para endereços da Cloudflare | a preencher |

## 8. Aplicação Cloudflare Access e service token

**Antes do primeiro deploy**, para a API nunca ficar exposta sem a borda.

1. Zero Trust → Access → Service Auth → **Create Service Token**, nome
   `tecnico-assistente-pendrives`, duração de 1 ano (a rotação é o cenário 6 do
   `docs/TOKENS.md`). Copie `Client ID` e `Client Secret` para o Vaultwarden: o secret só
   aparece nessa tela.
2. Zero Trust → Access → Applications → **Add an application** → Self-hosted:
   - Application domain: `diag.exemplo.invalid`, path vazio (toda a API).
   - Policy: nome `pendrives`, **Action: Service Auth**, Include → **Service Token** →
     `tecnico-assistente-pendrives`.
   - Nenhuma outra política (sem login de pessoas: TA-ADR-007 e TA-ADR-008).

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Borda sem token | `admin$ curl -s -o /dev/null -w '%{http_code}\n' https://diag.exemplo.invalid/v1/saude` | `302` ou `403`, **nunca** `200` | a preencher |
| Borda com token | `admin$ curl -s -H "CF-Access-Client-Id: <id>" -H "CF-Access-Client-Secret: <secret>" https://diag.exemplo.invalid/v1/saude` | `{"status":"ok"}` depois da etapa 9 (antes: `502`/`530` do túnel, porque o container ainda não existe) | a preencher |

Não deixe o `curl` com o secret no histórico do shell: use uma variável lida por
`read -s` (bash) ou `Read-Host -AsSecureString` (PowerShell), ou limpe o histórico.

## 9. Primeiro deploy pelo pipeline

1. Merge, nesta ordem, dos PRs para a `develop`: #5 (03), #6 (04), #7 (05), o PR deste
   módulo e o do Módulo 07.
2. PR `develop` → `main`, aberto quando você pedir (§10). O merge dispara o
   `deploy.yml`, porque a mudança inclui `api/**`.
3. Acompanhe em Actions → `deploy`.

| Verificação | Comando | Esperado | Resultado |
|---|---|---|---|
| Workflow | Aba Actions | `test` e `deploy` verdes; `healthy after N attempt(s), commit <sha>` | a preencher |
| Commit no servidor | `deploy$ git -C ~/docker/tecnico-assistente rev-parse HEAD` | SHA do merge na `main` | a preencher |
| Porta em loopback | `srv$ docker port tecnico-api` | `30XX/tcp -> 127.0.0.1:30XX` | a preencher |
| Nada na LAN | `srv$ sudo ss -tlnp \| grep 30XX` | Só `127.0.0.1:30XX` | a preencher |
| Migrações | `srv$ docker exec tecnico-api python -c "import sqlite3; print(sqlite3.connect('/data/tecnico.db').execute('select version from schema_migrations').fetchall())"` | `[(1,), (2,), (3,)]` | a preencher |
| Volume | `srv$ docker volume ls \| grep tecnico` | `tecnico-assistente_tecnico-data` | a preencher |
| Docs desligados | `srv$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:30XX/docs` | `404` | a preencher |

Se o workflow falhar no health check, o log do job traz `docker compose ps` e as últimas
50 linhas do container. Causas prováveis: `APP_PORT` diferente de `DEPLOY_APP_PORT`,
`.env` ausente, modelo proibido.

## 10. NocoDB, tokens das carretas e cenário 6

1. **NocoDB:** crie a tabela com as colunas de `docs/NOCODB.md`, gere um token de API de
   uma conta com acesso só a essa base, preencha `NOCODB_ENABLED=true`, `NOCODB_TOKEN` e
   `NOCODB_TABLE_ID` no `.env` e aplique:
   ```
   deploy$ cd ~/docker/tecnico-assistente/api && docker compose up -d
   ```
2. **Tokens das carretas:** um `create` por carreta, direto no terminal (não redirecione a
   saída), guardando cada token no Vaultwarden:
   ```
   srv$ docker exec -it tecnico-api python -m app.tokens create --carreta UM-01 --descricao "Pendrive da UM-01" --operador matheus
   srv$ docker exec -it tecnico-api python -m app.tokens list --operador matheus
   ```
3. **Cenário 6 do `docs/TOKENS.md`** (rotação do service token): execute uma vez, criando
   um segundo token e removendo o primeiro, para confirmar o procedimento com a borda
   real. Se preferir não girar agora, registre só a verificação de "borda com token" da
   etapa 8.

| Verificação | Esperado | Resultado |
|---|---|---|
| Um token ativo por carreta | `list` com uma linha `ativo` = 1 por carreta, `criado_por` `matheus` | a preencher |
| Espelho real | Depois da etapa 12, a linha aparece no NocoDB e `espelho_status` fica `ok` (consulta em `docs/NOCODB.md`) | a preencher |
| Cenário 6 | Token novo `200` na borda; antigo barrado depois de removido | a preencher |

## 11. Uptime Kuma, Homepage e backup

**Uptime Kuma.** A Cloudflare Access barra requisições sem service token, então há duas
formas de monitorar. Recomendado: pela borda, que prova o caminho inteiro.
- Tipo **HTTP(s) - Keyword**, URL `https://diag.exemplo.invalid/v1/saude`, keyword `"ok"`,
  intervalo de 60 s, com os cabeçalhos em "Headers":
  `{"CF-Access-Client-Id": "<id>", "CF-Access-Client-Secret": "<secret>"}`.
- Alternativa local: URL `http://127.0.0.1:30XX/v1/saude` se o Kuma usar a rede do host;
  com o Kuma em container de rede própria, `127.0.0.1` é o próprio container e a URL não
  funciona.
- Notificação para o mesmo ntfy `itc-infra`.

**Homepage** (`services.yaml`, no grupo dos serviços do glpi-srv):

```yaml
- Técnico Assistente:
    icon: mdi-stethoscope
    description: API de diagnóstico das carretas (tecnico-api)
    href: https://diag.exemplo.invalid/v1/saude
    server: glpi-srv
    container: tecnico-api
```

**Backup.** Inclua o volume `tecnico-assistente_tecnico-data` na rotina. Para uma cópia
consistente com o container no ar, gere um arquivo pela API de backup do SQLite antes da
rotina e faça backup dele:

```
srv$ docker exec tecnico-api python -c "import sqlite3; s = sqlite3.connect('/data/tecnico.db'); d = sqlite3.connect('/data/tecnico-backup.db'); s.backup(d); d.close(); print('ok')"
srv$ docker volume inspect tecnico-assistente_tecnico-data --format '{{ .Mountpoint }}'
```

O arquivo `tecnico-backup.db` fica no mesmo volume, no caminho mostrado pelo `inspect`.

| Verificação | Esperado | Resultado |
|---|---|---|
| Monitor do Kuma | Verde; ao parar o container (`docker stop tecnico-api` numa janela de manutenção), vermelho e alerta no ntfy; `docker start tecnico-api` volta ao verde | a preencher |
| Homepage | Card com o status do container | a preencher |
| Backup | O `tecnico-backup.db` aparece no destino da rotina; restaurar numa pasta de teste e ler `select count(*) from diagnosticos` | a preencher |

## 12. Verificação ponta a ponta

Numa estação Windows com PowerShell 5.1, simulando o pendrive, com um token de carreta de
teste (`--carreta TESTE`) e o service token:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$cf = @{ 'CF-Access-Client-Id' = (Read-Host 'CF id'); 'CF-Access-Client-Secret' = (Read-Host 'CF secret') }
$token = Read-Host 'token da carreta de teste'
Invoke-RestMethod -Uri 'https://diag.exemplo.invalid/v1/saude' -Headers $cf
$h = $cf + @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri 'https://diag.exemplo.invalid/v1/historico/TESTE-NB-11' -Headers $h
```

Depois, o `POST /v1/relatorio` com uma sessão real, usando o trecho do teste manual de
`docs/modules/03-ai-report.md`, trocando a URL por `https://diag.exemplo.invalid/v1/relatorio` e
os cabeçalhos por `$h`. Esse passo também serve como o teste com a chave real do Módulo 03.

| Verificação | Esperado | Resultado |
|---|---|---|
| TLS 1.2 no PS 5.1 | `/v1/saude` → `status ok` | a preencher |
| Token de carreta pela borda | `historico` → `diagnosticos: []` | a preencher |
| Relatório real | `200` com laudo; tokens e tempo registrados na tabela do Módulo 03; linha no NocoDB | a preencher |
| Token revogado | `revoke` do token de teste → `401` na requisição seguinte e alerta no ntfy | a preencher |
| Sem service token | `401`/`403` da Cloudflare, sem chegar à API | a preencher |

## Rascunhos para os documentos canônicos do glpi-srv

Texto pronto para colar nos documentos do servidor. Sem valores secretos.

### `contexto` — seção "Técnico Assistente"

> Serviço central do Técnico Assistente, a ferramenta de diagnóstico dos 595 notebooks
> das Unidades Móveis. Recebe as sessões dos pendrives, gera o laudo com o OpenCode Go e
> guarda o histórico por hostname. Clone do repositório `ITC-Brasil/tecnico-assistente`
> em `<diretório de deploy>`, atualizado pelo deploy do GitHub Actions,
> que entra por SSH como `<usuário de deploy>`. Container `tecnico-api` (imagem construída da pasta
> `api/` desse clone), `restart: always`, porta
> `127.0.0.1:30XX` (só loopback, porque o Docker contorna o UFW), publicado pelo
> `<túnel cloudflared>` em `diag.exemplo.invalid` atrás de uma aplicação Cloudflare Access com service
> token. Banco SQLite no volume `tecnico-assistente_tecnico-data` (fonte da verdade);
> espelho só de ida no NocoDB; alertas no ntfy `itc-infra`. Sem interface web.

### `guia` — operação

> - **Deploy:** automático no merge para a `main` com mudança em `api/**`
>   (`.github/workflows/deploy.yml`), como `<usuário de deploy>`, em
>   `<diretório de deploy>`. Rollback em `docs/DEPLOY.md`.
> - **Logs:** `docker logs --tail 100 tecnico-api`.
> - **Saúde:** `curl -s http://127.0.0.1:30XX/v1/saude`.
> - **Tokens das carretas:** `docker exec -it tecnico-api python -m app.tokens <create|list|revoke|rotate|auditoria|uso> ... --operador <nome>`; runbook em `docs/TOKENS.md`.
> - **`.env`:** `api/.env` no diretório acima, modo 600, fora do Git. Mudança exige
>   `docker compose up -d` na pasta `api/`.
> - **Backup:** volume `tecnico-assistente_tecnico-data`, com cópia consistente pelo
>   `sqlite3.backup` antes da rotina.

### `credenciais` — onde está cada segredo (sem valores)

> | Segredo | Onde fica | Quem usa |
> |---|---|---|
> | Chave SSH do `<usuário de deploy>` | Vaultwarden + secret `DEPLOY_SSH_KEY` | GitHub Actions |
> | Fine-grained PAT do clone | Vaultwarden + `~<usuário de deploy>/.git-credentials` | `git pull` do deploy |
> | `OPENCODE_GO_API_KEY` | Vaultwarden + `api/.env` | API |
> | Token do NocoDB | Vaultwarden + `api/.env` | API (espelho) |
> | Token do ntfy | Vaultwarden + `api/.env` | API (alertas) |
> | Service token Cloudflare Access `tecnico-assistente-pendrives` | Vaultwarden + `config/api.json` de cada pendrive + monitor do Uptime Kuma | Pendrives, Kuma |
> | Tokens das carretas `itcta_...` | Vaultwarden (um item por carreta) + `config/api.json` do pendrive; no banco só o SHA-256 | Pendrives |

### `licoes-aprendidas`

> - **Docker contorna o UFW.** Porta publicada sem `127.0.0.1:` fica exposta na LAN do
>   RB1100 mesmo com o UFW fechado. Publicar sempre em loopback (TA-ADR-009).
> - **Cloudflare corta requisição proxied em 100 s** (erro 524). Chamada externa lenta
>   precisa de timeout menor e erro limpo (TA-ADR-010: 60 s no Go).
> - **GitHub Free bloqueia deploy key SSH em organização.** O servidor clona por HTTPS com
>   Fine-grained PAT, e a host key do servidor vai em secret para o Actions.
> - **PowerShell 5.1 corrompe acento sem BOM.** Os `.ps1` do pendrive são UTF-8 com BOM e
>   CRLF (`.gitattributes`).
> - **Sessão elevada muda `$env:USERNAME`.** Na frota, o técnico eleva com outra conta, e o
>   `usuarioLogado` das sessões 1.0/1.1 é essa conta, não o usuário da máquina.

## Decisões

Nenhum ADR novo.

## Commits

O commit `docs: document module 06 initial deploy` é o único deste módulo.
