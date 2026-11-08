# AGENTS.md — ITC Bench

Instruções canônicas para qualquer agente (Claude Code, OpenCode, OpenChamber, Codex, Hermes).
`CLAUDE.md` só importa este arquivo. Não duplique conteúdo entre os dois.

## O que é

App Windows instalável do Grupo ITC Brasil para a bancada do técnico: prepara notebooks das
unidades móveis (contas, Wi-Fi, acesso remoto, programas, GPO, proteção do login, aparência) e
faz o diagnóstico que rodava do pendrive. Junta o ITC Configurador (`itc-config/configurador`,
fora deste repo) e o Técnico Assistente. Desde o Módulo 03 é monorepo (ADR-012): a API do Técnico
Assistente (FastAPI + SQLite no glpi-srv) vive em `api/`, e o Bench é cliente dela. O repo
`ITC-Brasil/tecnico-assistente` foi descontinuado; o pendrive ficou lá, só como referência.

## Ao chegar sem contexto, leia nesta ordem

1. `.conversa/para-agent.md` (pedidos do chat de planejamento; fora do git, pode não existir)
2. `docs/PROGRESS.md`, bloco **ESTADO ATUAL**
3. `docs/IMPLEMENTATION-PLAN.md` (módulo corrente e checkboxes)
4. `docs/DECISIONS.md` (ADR-001 em diante)
5. `docs/PRD.md`, `docs/TRD.md`, `docs/APP-FLOW.md`, `docs/UI-UX-BRIEF.md`, `docs/BACKEND-SCHEMA.md` conforme o módulo
6. Mexendo em `api/`: `docs/api/` (API, TOKENS, SCHEMA, DEPLOY) e `docs/api/DECISIONS-TA.md` (TA-ADR-001 em diante)

## Antes de encerrar a sessão (ou ao ficar sem cota/contexto)

- Reescreva o bloco **ESTADO ATUAL** de `docs/PROGRESS.md`: branch, último commit, o que está
  pela metade, próximo passo concreto.
- Marque os checkboxes do módulo em `docs/IMPLEMENTATION-PLAN.md`.
- Se o chat de planejamento precisar saber, escreva em `.conversa/para-cowork.md`. Estado durável
  nunca fica só em `.conversa/`.
- `.conversa/` tem um sentido por arquivo: o agente escreve só em `para-cowork.md` (entrada nova
  no topo); o chat de planejamento escreve só em `para-agent.md`. Nunca edite `para-agent.md`,
  nem o campo **Resposta** dele.

## Stack

Monorepo (ADR-012): `app/` é o programa Windows, `api/` é a API (FastAPI + SQLite no glpi-srv).
Dois projetos separados, sem workspace.

- **app/**: Python 3.13 + PySide6 6.12 (ADR-002, ADR-010). Manifesto em `app/pyproject.toml`, lock
  em `app/uv.lock`, gerenciado pelo uv; comandos rodam de dentro de `app/`. Código em
  `app/src/itc_bench/`: `nucleo/` e `servicos/` sem Qt (ruff `TID251`), `ui/` com Qt, `recursos/`
  lidos por `importlib.resources`. Identificadores em português.
- **api/**: Python 3.12.14 (imagem `python:3.12.14-slim-trixie`, a mesma no `Dockerfile` e nos
  testes) + FastAPI, Uvicorn, httpx, Pydantic, pydantic-settings; SQLite do `sqlite3` da imagem.
  Dependências diretas em `api/requirements.in`, lock `requirements.txt` por pip-compile com hash
  (TA-ADR-025). Sem ruff/mypy, como no repo de origem.

## Regras invioláveis

- **Nada de segredo no repositório nem em `.conversa/`**: endereços de servidor, chaves, senhas,
  SSIDs reais. Só o endereço da API vai no instalador (ADR-008).
- **Documento que lista padrões de varredura ou regras de substituição usa placeholders**
  ("hosts reais do Grupo → `*.exemplo.invalid`"), nunca o valor procurado. A lista real fica fora
  do repo (scratchpad).
- **O Bench nunca fala com o GLPI nem com o NocoDB.** Tudo passa pela API em `api/`
  (ADR-005, ADR-006).
- **Sem `shell=True` e sem interpolar entrada em comando.** Lista de argumentos; dados por variável
  de ambiente, no padrão de `backend/contas.py` do Configurador (Módulo 02).
- **Cache local de cadastros e hash de login só com DPAPI.** Nunca senha em preferência de UI.
- **Caminhos**: binários em `Program Files`, dados em `%ProgramData%\ITC\Bench` (logs em
  `%ProgramData%\ITC\Bench\logs`), preferências em `%LOCALAPPDATA%`. Nada ao lado do EXE.
- **Sem `except: pass`.** Erro vai para o log em arquivo e para a tela.
- **Grupo Administradores pelo SID `S-1-5-32-544`**, nunca pelo nome localizado.
- **Identidade visual** de `docs/design/` (ADR-001); menu em 7 grupos (ADR-004); botão "?" em
  toda tela (ADR-007).
- **A UI CustomTkinter do Configurador (`main_moderno.py`, `ui/`) não vem para cá.**
- Nunca copiar do Configurador: `config/segredos.json`, `config/config.ini`, `config/wifi_db.json`,
  `instaladores/`, `ferramentas/`.

### Regras da API (`api/`, vindas do Técnico Assistente)

- **SQLite é a fonte da verdade**; o NocoDB é espelho só de ida, e só a API fala com ele
  (TA-ADR-005, revisado para cadastros pelo ADR-006).
- **Tokens de carreta (`itcta_`) só como hash SHA-256 no banco**, comparação em tempo constante
  (TA-ADR-007). A CLI `app.tokens` imprime o token uma vez: nunca redirecionar para arquivo ou log.
- **Porta do container só em `127.0.0.1`** (TA-ADR-009); exposição só pelo túnel com Cloudflare
  Access. Sem frontend (TA-ADR-008).
- **IA só no servidor** (OpenCode Go, TA-ADR-003); a IA correlaciona e escreve, nunca decide nem
  executa (TA-ADR-016).
- **`.env` só no servidor** (`api/.env`), nunca no git; variáveis em `api/.env.example`.
- **Testes nunca chamam OpenCode Go, NocoDB ou ntfy reais**; banco temporário por suite.
- Escritas novas no SQLite por `db.connect()` + `db.immediate()`. Migrações só para a frente;
  remover ou renomear coluna exige ADR com plano de volta.
- `api/app/eventlog-conhecidos.json` é a única cópia da base de Event Log (ADR-012).
- Actions fixadas por SHA completo verificado na release oficial.
- Deploy pelo `api-deploy.yml`, environment `producao`; procedimento em `docs/api/DEPLOY.md`.

## Modo de execução

- Um módulo por sessão, na ordem de `docs/IMPLEMENTATION-PLAN.md`.
- Branch por módulo saindo de `develop`: `feat/modulo-NN-nome` (ou `docs/...` para só documentação).
  PR para `develop`. Merge só pelo responsável. `main` recebe releases.
- Pare e pergunte quando a decisão tiver consequência de produto; registre como ADR.

## Fechamento de módulo (gate)

1. `docs/modules/NN-nome.md` com verificação em tabela de cenários e resultados reais
2. Entrada no topo de `docs/PROGRESS.md`; ADRs novos em `docs/DECISIONS.md`
3. Auditoria de segurança com `docs/security/AUDIT-PROMPT.md`, salva em
   `docs/security/AAAA-MM-DD-modulo-NN.md`. Achado crítico ou alto bloqueia o fechamento; risco
   aceito vira ADR.

## Commits

`tipo(escopo): descrição` em inglês. Tipos: `feat`, `fix`, `security`, `refactor`, `test`, `docs`,
`chore`, `perf`, `ci`, `style`. `git add` arquivo por arquivo, conferindo `git status --short`.
Nunca `git add -A`.

## Comandos úteis

```
uv --directory app sync --frozen                  # ambiente a partir do lock
uv --directory app run itc-bench --dev            # abre sem pedir administrador
uv --directory app run itc-bench --teste          # abre, loga e fecha (código 0)
uv --directory app run itc-bench                  # pede elevação (UAC)
uv --directory app run ruff check . && uv --directory app run ruff format --check .
uv --directory app run mypy
uv --directory app run pytest
```

API, da raiz do repositório, no PowerShell (o pytest roda no container, que é o comando oficial):

```
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}pi:/app" -w /app python:3.12.14-slim-trixie sh -c "pip install -q --root-user-action=ignore --require-hashes -r requirements-dev.txt && pytest -q"
```

Lock da API (TA-ADR-025): editar só `api/requirements.in`/`requirements-dev.in` e regenerar:

```
docker run --rm -v "${PWD}pi:/app" -w /app python:3.12.14-slim-trixie sh -c "pip install -q --root-user-action=ignore pip-tools==7.5.3 click==8.1.8 && pip-compile --quiet --strip-extras --generate-hashes --output-file=requirements.txt requirements.in && pip-compile --quiet --strip-extras --generate-hashes --output-file=requirements-dev.txt requirements-dev.in"
```

CLI de tokens (runbook em `docs/api/TOKENS.md`): `docker exec -it tecnico-api python -m app.tokens
create|list|revoke|rotate|auditoria|uso ... --operador <nome>`.
