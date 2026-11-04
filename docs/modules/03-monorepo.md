# Módulo 03 — Migração da API para o monorepo

**Branch:** `chore/modulo-03-monorepo` · **Data:** 2026-11-03 · **ADR:** ADR-012 (substitui o ADR-003)

**Fonte:** `ITC-Brasil/tecnico-assistente`, `main` em `0bc5620d303fea2a0b56a27b03a6df3d2f0ae976`
(PR #22; run do `deploy.yml` nesse SHA: `success`, 2026-09-29). O `8646754`
(`feat/projetos-conservadores`) está nela, via PR #21. Cópia filtrada: `fe08b2c08b104e9c61609ce7069bd0f51215978e`.

## O que entrou

| Item | Onde | Commit |
|---|---|---|
| ADR-012; ADR-003 marcado como substituído; status do ADR-006 | `docs/DECISIONS.md` | `7843aa0` |
| Programa Windows em `app/` (`git mv`) e `.gitattributes` | `app/`, `.gitattributes` | `822705f` |
| Comandos do app a partir de `app/` | `AGENTS.md` | `5d81445` |
| `api/` com histórico (28 commits de conteúdo, 36 com os merges) | `api/` | `c7d3481` (merge) |
| Regras de ignore da API e LF em `api/**` | `.gitignore`, `.gitattributes` | `3c93ac1` |
| `app-ci.yml`, `api-ci.yml`, `api-deploy.yml` (só `workflow_dispatch`, environment `producao`, `DEPLOY_DIR`), `gitleaks.yml`, `dependabot.yml` (`pip`, `uv`, actions) | `.github/` | `f004653` |
| Docs da API (API, TOKENS, ARCHITECTURE, NOCODB, SCHEMA, DEPLOY reescrito, TA-ADRs, PROGRESS e módulos de lá como histórico) | `docs/api/` | `144ad39` |
| Regras da API no `AGENTS.md`; plano renumerado (03–16), sem [TA]; referências de número de módulo em PRD/TRD/APP-FLOW/BACKEND-SCHEMA | `AGENTS.md`, `docs/` | `14a73b4` |

## Como a importação foi feita

```
git clone --no-local --branch main <cópia local do TA> ta-f      # depois: reset para origin/main = 0bc5620
git filter-repo --force --path api/ --replace-text regras.txt
# regras: hosts reais do Grupo (ver ADR-012) -> *.exemplo.invalid; usuário de deploy -> usuario-deploy
#         (arquivo de regras só no scratchpad, fora do repo)
git remote add ta <ta-f>; git fetch ta
git merge --allow-unrelated-histories ta/main; git remote remove ta
```

`git filter-repo` 2.47.0 (`uv tool install`). Os caminhos são os mesmos do TA (`api/...`), então
`git log`/`git blame` funcionam sem `--follow`. **O PR para `develop` precisa ser merge commit**:
squash apagaria os commits importados.

## Decisões de implementação

- **Dois projetos, sem workspace uv:** Python 3.13 no app, 3.12.14 na API (ADR-012).
- **`windows-2025` fixo** no `app-ci.yml` (não `windows-latest`), com uv 0.12.17 igual ao
  `required-version`. O runner hospedado roda elevado, então os testes `so_admin` de ACL rodam lá;
  sem elevação eles já se marcam como pulados com o motivo.
- **`api/** text eol=lf`** veio do `.gitattributes` do TA: a API roda em Linux.
- **Testes de acento usam a página OEM real** (`_codec("oem")`): o runner en-US não tem "ã" na
  OEM 437. O teste do `cmd` é pulado com motivo nessa situação; nas máquinas pt-BR (850) roda.
  Achado pelo CI novo; o código do executor não mudou.
- **Comparação da base de Event Log com o pendrive saiu do CI** (ADR-012, consequência do TA-ADR-022).
- **Docs do TA sem histórico**, com `ADR-NNN` → `TA-ADR-NNN` e marcadores no lugar de host, porta
  SSH, usuário e diretório de deploy. `pendrive/SCHEMA.md` (contrato da sessão, que a API normaliza)
  veio como `docs/api/SCHEMA.md`.
- **Sem `.gitleaksignore`:** o gitleaks não acusou nada no histórico completo (nem o `b70473b` do
  ADR-009, porque as regras padrão não pegam hostname).

## Verificação (local, antes do PR)

| Cenário | Como | Resultado real |
|---|---|---|
| `origin/main` do TA | `git fetch origin` na cópia local; `git rev-parse origin/main` | `0bc5620d303fea2a0b56a27b03a6df3d2f0ae976` |
| Deploy do TA verde no SHA | `gh run list -R ITC-Brasil/tecnico-assistente -w deploy.yml` | `success` (push, 2026-09-29) |
| `8646754` incluído | `git merge-base --is-ancestor 8646754 origin/main` | sim |
| PR #7 em `main` | `gh pr view 7` | `MERGED` (`ade5763`) |
| Só `api/` na cópia filtrada | `git ls-files \| cut -d/ -f1 \| sort -u` | `api` |
| Regex na cópia reescrita | ver auditoria | só IPs de fixture; hosts reais: 0 |
| gitleaks na cópia | `gitleaks git . --redact` | 28 commits, `no leaks found` |
| gitleaks na branch com o merge | idem, na raiz | 65 commits, `no leaks found` |
| gitleaks em `docs/api/` | `gitleaks dir docs/api` | `no leaks found` |
| Histórico da API | `git log --oneline -- api \| wc -l`; `git blame api/app/main.py` | 28; linhas atribuídas a `5ecf8294` (commit original reescrito) |
| Recursos sem conversão | `git check-attr text app/src/itc_bench/recursos/fontes/OFL.txt` | `unset` |
| SHA-256 das fontes | `sha256sum` × README das fontes | iguais |
| Lint e tipos do app | `uv --directory app run ruff check .`, `ruff format --check .`, `mypy` | limpos (29 arquivos; 16 fontes) |
| Testes do app | `uv --directory app run pytest -q` | 87 passed (88 depois da divisão do teste de acento) |
| App abre e fecha | `uv --directory app run itc-bench --teste` | código 0 |
| Testes da API | pytest no `python:3.12.14-slim-trixie` (comando do `AGENTS.md`) | 151 passed, 1 warning |
| Compose igual ao de produção | `docker compose config` com `.env` de teste (apagado depois) | `name: tecnico-assistente`, `container_name: tecnico-api`, `host_ip: 127.0.0.1`, volume `tecnico-assistente_tecnico-data` |
| `.env` ignorado | `git check-ignore -v api/.env` | `.gitignore:22:.env` |
| YAML válido | `yaml.safe_load` nos 4 workflows e no `dependabot.yml` | ok |
| CI no GitHub, 1ª execução | PR #8, `app-ci` | falhou: 2 testes de acento supunham OEM 850; o runner é en-US (437) |
| CI no GitHub, depois da correção | PR #8: `app-ci`, `api-ci`, `gitleaks` | verdes; `app-ci` com 87 passed, 1 skipped (`test_acento_cmd`, motivo: OEM sem "ã"); `--teste` código 0 |

## Transição no servidor e no TA (2026-11-04)

Procedimento em `docs/api/DEPLOY.md`, seção "Transição". Executada pelo responsável; host,
usuário, caminho e porta reais ficam fora deste documento.

| Passo | Quem | Resultado real |
|---|---|---|
| 1. PR no TA: `deploy.yml` só com `workflow_dispatch` | agente | TA PR #31 mergeado e levado à `main` de lá (`a80111d`); nenhum run do `deploy` do TA depois disso |
| 2. Environment `producao` + 7 secrets; deploy key só leitura com apelido `github-itc-bench` | responsável | feito; `ssh -T git@github-itc-bench` autenticou; host key do GitHub conferida |
| 3. Caminho do banco (`printenv DATABASE_PATH`) | responsável | padrão, `/data/tecnico.db` |
| 4. Backup fora do volume; SHA-256 | responsável | 303 104 bytes; SHA-256 `ab41cec6dc06b7def46856c14b64521acff0f20af79c5186ab42d30730859432`; `integrity_check` = `ok`; modo 600; cópia dentro de `/data` apagada |
| 5. `git check-ignore -v api/.env` antes e depois | responsável | antes: regra do `.gitignore` do TA; depois: `.gitignore:22:.env` do itc-bench; `.env` intacto (600) |
| 6. `set-url`, `fetch`, `checkout -B main origin/main` | responsável | SHA anterior em produção `0bc5620d303fea2a0b56a27b03a6df3d2f0ae976`; `fetch` com "forced update" (esperado, históricos diferentes); `HEAD` = `9bc90146f72c931f9da7654fa92c271dcdf3d2e5`; `status` limpo antes e depois |
| 7. `api-deploy` por `workflow_dispatch` | responsável | 2026-11-04 00:16 UTC; job `test` 151 passed; `deploy`: imagem igual, `Container tecnico-api Running` (não recriado, sem parada); `healthy after 1 attempt(s), commit 9bc9014…`; log sem host, usuário, porta nem chave |
| 8. Verificação pós-deploy | responsável + agente | tabela abaixo |
| 9. `push` em `api/**` de volta | agente | este PR; README do TA fica para depois da troca da pasta de deploy |

### Verificação pós-deploy

| Cenário | Resultado real |
|---|---|
| Workflow verde | `test` e `deploy` verdes; `healthy after 1 attempt(s), commit 9bc9014…` |
| Commit no servidor | `9bc90146f72c931f9da7654fa92c271dcdf3d2e5` |
| Remote | `git@github-itc-bench:ITC-Brasil/itc-bench.git` |
| Mesmo container e volume | `tecnico-api`, volume `tecnico-assistente_tecnico-data` |
| Porta só em loopback | só `127.0.0.1` |
| Saúde local | `{"status":"ok"}` |
| Saúde pelo túnel, com service token | **não feito** (pendente) |
| Borda sem service token | **não feito** (pendente) |
| Migrações | `[1, 2, 3]`, as três do repo; nenhuma nova |
| Relatório de teste | carreta `TESTE-MONOREPO`: 1ª chamada `503 ia_timeout` (informativo: o OpenCode Go passou do limite de 90 s; latência do provedor, não da migração); 2ª `200` em 39 s com laudo; token revogado pelo responsável |
| Espelho no NocoDB | não se aplica: desligado desde o deploy inicial do TA (`NOCODB_ENABLED=false`, tabela não configurada); 4 relatórios `pendente` com 0 tentativas, inclusive o de teste (id 4). Não é efeito da migração |

## Pendências

- Teste de borda pelo túnel, com e sem service token.
- Fora do módulo: espelho do NocoDB desligado (4 relatórios `pendente`). Ligar o espelho ou
  decidir por ADR que ele não é mais necessário, no Módulo 05 (Cadastros).
- Troca da pasta de deploy no servidor para `itc-bench` e README do TA (ver `docs/PROGRESS.md`).
- Do 01: UAC real manual (cenário 7).
