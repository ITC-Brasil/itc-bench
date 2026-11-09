# ITC Bench

Aplicativo Windows para a bancada do técnico do Grupo ITC Brasil. Faz a Preparação e o
Diagnóstico dos notebooks das Unidades Móveis, com laudo escrito por IA no servidor.

Substitui o ITC Configurador e o Técnico Assistente. O Técnico Assistente foi descontinuado e o
repositório antigo fica só como referência. Versão atual: **0.16.0**, ainda antes da 1.0.0.

## Para quem

**Gestor.** O Bench prepara e confere um notebook em uma só ferramenta:

- contas locais do técnico e dos usuários;
- identificação da máquina e Wi-Fi;
- acesso remoto;
- instalação de programas;
- políticas (GPO) e bloqueio de USB;
- proteção do login e aparência;
- revisão final do que foi aplicado;
- diagnóstico com laudo gerado pela API.

Escopo, públicos e critérios de sucesso estão em [docs/PRD.md](docs/PRD.md).

**Técnico ou desenvolvedor.** Comece por [AGENTS.md](AGENTS.md): ordem de leitura, regras e
comandos.

## Estrutura do monorepo

| Pasta | Conteúdo |
|---|---|
| `app/` | Programa Windows (Python 3.13 + PySide6), gerenciado pelo uv |
| `api/` | API do Técnico Assistente (FastAPI + SQLite), roda no servidor em container |
| `instalador/` | Script do Inno Setup, build, testes do instalador e varredura (`varrer.py`) |
| `docs/` | Produto, decisões, módulos, segurança e guias (ver mapa abaixo) |
| `.github/workflows/` | CI, build e deploy (tabela abaixo) |

| Workflow | Papel |
|---|---|
| `app-ci.yml` | Lint, tipos e testes do `app/` em PR e em push para `develop` e `main` |
| `app-build.yml` | Gera o instalador: artefato no PR; rascunho de Release na tag `vX.Y.Z` |
| `api-ci.yml` | Testes da API em PR e em push; também é o job de teste do deploy |
| `api-deploy.yml` | Deploy da API no push para `main` que altera `api/**` |
| `gitleaks.yml` | Procura segredos em todo PR e push para `develop` e `main` |

A pasta `.conversa/` (troca de mensagens com o chat de planejamento) fica fora do git.

## Desenvolvimento

### App (Windows)

Da raiz do repositório:

```
uv --directory app sync --frozen                  # ambiente a partir do lock
uv --directory app run itc-bench --dev            # abre sem pedir administrador
uv --directory app run itc-bench --teste          # abre, loga e fecha (código 0)
uv --directory app run itc-bench                  # pede elevação (UAC)
uv --directory app run ruff check . && uv --directory app run ruff format --check .
uv --directory app run mypy
uv --directory app run pytest
```

O `--dev` abre sem administrador e nunca altera a máquina, mesmo elevado: as telas só leem. Não
procura atualização e aceita o endereço da API pela variável `ITC_BENCH_API_URL`, inclusive
`http://` para `localhost`. Sem administrador, o log vai para `%LOCALAPPDATA%\ITC\Bench\logs`.

### API

Testes no container, da raiz do repositório, no PowerShell (comando oficial):

```
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}\api:/app" -w /app python:3.12.14-slim-trixie sh -c "pip install -q --root-user-action=ignore --require-hashes -r requirements-dev.txt && pytest -q"
```

- Variáveis de ambiente: modelo em `api/.env.example`. O `.env` real só existe no servidor.
- Dependências: edite só `api/requirements.in` e `api/requirements-dev.in` e regenere o lock com
  hash (TA-ADR-025; comando no [AGENTS.md](AGENTS.md)).
- Endpoints: [docs/api/API.md](docs/api/API.md).

## Obter e instalar

- Use **só o instalador gerado pelo CI**: o artefato do PR (teste) ou o rascunho da Release
  criado pela tag. Build local e a pasta `app/dist` nunca vão para um notebook.
- Confira o hash antes de instalar, comparando com o `SHA256SUMS` publicado junto:

  ```
  Get-FileHash .\itc-bench-X.Y.Z-setup.exe -Algorithm SHA256
  ```

- O instalador de release já traz o endereço da API e instala sem parâmetro (duplo clique ou
  `/VERYSILENT`). `/APIURL=https://<endereço da API>` serve para trocar o endereço (ADR-027).
- **O `setup.exe` de release é de uso interno:** o endereço da API fica legível dentro dele.

Parâmetros, desinstalação e conferências: [docs/BUILD.md](docs/BUILD.md).

## Atualização automática

O Bench baixa um manifesto assinado, confere a assinatura e o hash e instala a versão nova ao
ser fechado, depois de confirmação do técnico (ADR-026). Detalhes em
[docs/BUILD.md](docs/BUILD.md#atualização-automática-adr-026).

## Como contribuir

- Branch a partir de `develop` (`feat/modulo-NN-nome`, `fix/...`, `docs/...`) e PR para
  `develop`, integrado por merge commit. O merge é feito pelo responsável.
- Release: PR de `develop` para `main`. O push na `main` dispara o deploy da API; antes de
  migração do banco, faça o backup descrito em [docs/api/DEPLOY.md](docs/api/DEPLOY.md).
- Commits no formato `tipo(escopo): descrição`, em inglês. `git add` arquivo por arquivo,
  conferindo `git status --short`.
- Decisão nova vira ADR: [docs/DECISIONS.md](docs/DECISIONS.md) para o Bench,
  [docs/api/DECISIONS-TA.md](docs/api/DECISIONS-TA.md) para a API.
- Sem force-push em branch publicada.
- Arquivo que aparece modificado só por fim de linha (CRLF) é descartado, não commitado.

## Segurança

- Nunca entram no repositório: hosts, endereços, portas, contas, SIDs, caminhos de perfil, SSIDs,
  chaves privadas, senhas e tokens. Em documentos, use marcadores como `<endereço da API>`.
- Exceção intencional: as chaves públicas de atualização `principal.pub` e `reserva.pub`, em
  `app/src/itc_bench/recursos/atualizacao/`.
- Proteções: gitleaks no CI, `instalador/varrer.py` no build e auditorias por módulo em
  [docs/security/](docs/security/).
- Problema de segurança é comunicado diretamente ao responsável, nunca em issue com detalhes.

## Testes em máquina real

[docs/testes/maquina-real.md](docs/testes/maquina-real.md) reúne os cenários que alteram a
máquina e não rodam no CI. É executado antes da 1.0.0, num notebook reserva, com o instalador
gerado pelo CI. Bug encontrado vira PR para `develop`.

## Mapa da documentação

| Documento | Conteúdo |
|---|---|
| [PRD.md](docs/PRD.md) | Produto: problema, públicos, escopo |
| [TRD.md](docs/TRD.md) | Requisitos técnicos e arquitetura do app |
| [APP-FLOW.md](docs/APP-FLOW.md) | Fluxos de tela e navegação |
| [UI-UX-BRIEF.md](docs/UI-UX-BRIEF.md) | Diretrizes de interface |
| [IMPLEMENTATION-PLAN.md](docs/IMPLEMENTATION-PLAN.md) | Módulos, ordem e checkboxes |
| [PROGRESS.md](docs/PROGRESS.md) | Estado atual e histórico de entregas |
| [DECISIONS.md](docs/DECISIONS.md) | ADRs do Bench |
| [BACKEND-SCHEMA.md](docs/BACKEND-SCHEMA.md) | Dados trocados com a API e cache local |
| [BUILD.md](docs/BUILD.md) | Build, instalador, distribuição e atualização |
| [modules/](docs/modules/) | Um documento por módulo, com verificação |
| [api/](docs/api/) | API: endpoints, tokens, schema, deploy e ADRs (TA-ADR) |
| [security/](docs/security/) | Prompt e relatórios de auditoria |
| [testes/](docs/testes/) | Roteiro de máquina real |
| [design/](docs/design/) | Identidade visual (ADR-001) |
| [referencia/](docs/referencia/) | Análise do ITC Configurador, projeto de origem |

## Uso

Software interno do Grupo ITC Brasil, de uso restrito. Não há licença de distribuição.
