# PROGRESS — ITC Bench

## ESTADO ATUAL

- **Branch:** `chore/modulo-03-monorepo` (PR para `develop`, por merge commit, aguardando revisão).
  `develop` e `main` têm os Módulos 01 e 02 (PR #6 e PR #7 mergeados).
- **Feito:** Módulo 03, parte do repositório — monorepo `app/` + `api/` (ADR-012), API importada
  com histórico do tecnico-assistente em `0bc5620`, CI por parte, docs em `docs/api/`, plano
  renumerado (03–16).
- **Pela metade:** a transição no glpi-srv e no tecnico-assistente (`docs/api/DEPLOY.md`, seção
  "Transição"), que aguarda aprovação. O `api-deploy.yml` está só com `workflow_dispatch`.
- **Próximo passo:** após aprovação e merge, PR no TA desligando o `push` do deploy; o responsável
  cria o environment `producao`, os 7 secrets e a deploy key; depois backup, troca do remote,
  primeiro deploy e relatório de teste. Em seguida, Módulo 04 — login e sessão (rotas em `api/`).
- **Pendências externas:** passos do responsável no GitHub e no servidor; UAC real do 01 (cenário 7).

## Registro

| Data | Módulo | Resumo |
|---|---|---|
| 2026-11-03 | 03 — Monorepo | `app/` (programa Windows, `git mv`) + `api/` importada com histórico (filter-repo `--path api/` + `--replace-text`, fonte `0bc5620`, merge por `--allow-unrelated-histories`). Hosts reais do histórico reescritos antes do merge; regex e gitleaks limpos na cópia e na branch. Workflows `app-ci`, `api-ci`, `api-deploy` (manual, environment `producao`, `DEPLOY_DIR`), `gitleaks`; dependabot com `uv`. `docs/api/` com TA-ADRs. Plano 03–16 sem [TA]. App 87 testes, API 151. Auditoria só com informativos. ADR-012. Transição no servidor pendente. |
| 2026-11-03 | 02 — Executor | `executar()`/`powershell()` com lista de argumentos, caminho absoluto pela API, dados em `ITC_*` ou stdin, `Sensivel` mascarado (inclusive no CLIXML), Job Object no timeout, saída `auto` (UTF-8/OEM). Ruff `TID251` + teste de AST contra processo fora do executor. `ui/tarefa.py`. ACL SDDL em `%ProgramData%\ITC` com recusa de reparse e retry com privilégios. 87 testes; auditoria sem achado aberto acima de informativo; achado médio do 01 fechado. ADR-011. |
| 2026-11-03 | 01 — Esqueleto | Python 3.13 + PySide6 6.12 com uv (ADR-010). `src/itc_bench/` com `nucleo/` sem Qt, `ui/`, `recursos/` (Archivo e Inter OFL, 20 ícones, símbolo). UAC/`--dev`/`--teste`, log 1 MiB × 5 com queda para `%LOCALAPPDATA%` sem permissão, janela com 7 grupos e 20 telas vazias com "?". 14 testes; auditoria com 1 achado médio (ACL do ProgramData) planejado no 02. |
| 2026-11-03 | 00 — Kickoff | `.gitignore` em `main`; `develop` criada. `AGENTS.md` canônico, `CLAUDE.md` com `@AGENTS.md`, `PROMPT_CLAUDE_CODE.md`; PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA (4 tabelas do NocoDB lidas por metadados), IMPLEMENTATION-PLAN (módulos 00–15), DECISIONS (ADR-001 a ADR-008), AUDIT-PROMPT e baseline `docs/security/2026-11-03-modulo-00.md`. Inclui `docs/design/` e `docs/referencia/`. |
