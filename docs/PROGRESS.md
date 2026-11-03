# PROGRESS — ITC Bench

## ESTADO ATUAL

- **Branch:** `feat/modulo-02-executor` (PR para `develop`, aguardando revisão)
- **Feito:** Módulo 02 — executor seguro (`servicos/executor.py`), testes com entradas hostis,
  proibição de processo fora do executor, tarefa em segundo plano para a UI, ACL explícito em
  `%ProgramData%\ITC`. ADR-011. Pré-requisito do 01 (`sys.excepthook`) no primeiro commit.
- **Pela metade:** nada. Continua pendente a verificação manual do UAC real do Módulo 01 (cenário 7).
- **Próximo passo:** após merge, Módulo 03 — login e sessão (exige rota no `tecnico-assistente`).
  No 04, criar a subpasta sem leitura para Usuários para arquivos DPAPI (ADR-011).
- **Pendências externas:** rotas de login e cadastros no repo `tecnico-assistente` (Módulos 03 e 04).

## Registro

| Data | Módulo | Resumo |
|---|---|---|
| 2026-11-03 | 02 — Executor | `executar()`/`powershell()` com lista de argumentos, caminho absoluto pela API, dados em `ITC_*` ou stdin, `Sensivel` mascarado (inclusive no CLIXML), Job Object no timeout, saída `auto` (UTF-8/OEM). Ruff `TID251` + teste de AST contra processo fora do executor. `ui/tarefa.py`. ACL SDDL em `%ProgramData%\ITC` com recusa de reparse e retry com privilégios. 87 testes; auditoria sem achado aberto acima de informativo; achado médio do 01 fechado. ADR-011. |
| 2026-11-03 | 01 — Esqueleto | Python 3.13 + PySide6 6.12 com uv (ADR-010). `src/itc_bench/` com `nucleo/` sem Qt, `ui/`, `recursos/` (Archivo e Inter OFL, 20 ícones, símbolo). UAC/`--dev`/`--teste`, log 1 MiB × 5 com queda para `%LOCALAPPDATA%` sem permissão, janela com 7 grupos e 20 telas vazias com "?". 14 testes; auditoria com 1 achado médio (ACL do ProgramData) planejado no 02. |
| 2026-11-03 | 00 — Kickoff | `.gitignore` em `main`; `develop` criada. `AGENTS.md` canônico, `CLAUDE.md` com `@AGENTS.md`, `PROMPT_CLAUDE_CODE.md`; PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA (4 tabelas do NocoDB lidas por metadados), IMPLEMENTATION-PLAN (módulos 00–15), DECISIONS (ADR-001 a ADR-008), AUDIT-PROMPT e baseline `docs/security/2026-11-03-modulo-00.md`. Inclui `docs/design/` e `docs/referencia/`. |
