# PROGRESS — ITC Bench

## ESTADO ATUAL

- **Branch:** `feat/modulo-01-esqueleto` (PR para `develop`, aguardando revisão)
- **Feito:** Módulo 01 — esqueleto: manifesto e lock, entrada com UAC/`--dev`/`--teste`, caminhos,
  log rotativo, tema com fontes e ícones, janela com os 7 grupos. ADR-010.
- **Pela metade:** verificação manual do pedido real de UAC (cenário 7 de `docs/modules/01-esqueleto.md`).
- **Próximo passo:** após merge, Módulo 02 — executor seguro, incluindo o ACL explícito de
  `%ProgramData%\ITC\Bench` (achado médio de `docs/security/2026-11-03-modulo-01.md`).
- **Pendências externas:** rotas de login e cadastros no repo `tecnico-assistente` (Módulos 03 e 04).

## Registro

| Data | Módulo | Resumo |
|---|---|---|
| 2026-11-03 | 01 — Esqueleto | Python 3.13 + PySide6 6.12 com uv (ADR-010). `src/itc_bench/` com `nucleo/` sem Qt, `ui/`, `recursos/` (Archivo e Inter OFL, 20 ícones, símbolo). UAC/`--dev`/`--teste`, log 1 MiB × 5 com queda para `%LOCALAPPDATA%` sem permissão, janela com 7 grupos e 20 telas vazias com "?". 14 testes; auditoria com 1 achado médio (ACL do ProgramData) planejado no 02. |
| 2026-11-03 | 00 — Kickoff | `.gitignore` em `main`; `develop` criada. `AGENTS.md` canônico, `CLAUDE.md` com `@AGENTS.md`, `PROMPT_CLAUDE_CODE.md`; PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA (4 tabelas do NocoDB lidas por metadados), IMPLEMENTATION-PLAN (módulos 00–15), DECISIONS (ADR-001 a ADR-008), AUDIT-PROMPT e baseline `docs/security/2026-11-03-modulo-00.md`. Inclui `docs/design/` e `docs/referencia/`. |
