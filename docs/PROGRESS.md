# PROGRESS — ITC Bench

## ESTADO ATUAL

- **Branch:** `feat/modulo-05-cadastros`, PR para `develop` (merge commit).
- **Feito:** Módulo 05 no código. API: `GET /v1/bench/cadastros[?unidade=]` com sessão, leitura
  do NocoDB isolada em `api/app/services/nocodb_cadastros.py` (Viewer, ids pelo `.env`), cópia em
  memória com TTL e uma leitura por vez, cópia defasada até 24 h, `ETag` por HMAC, `304`,
  migração `0005` (auditoria) (221 testes). App: cache `protegido\cadastros.dpapi` 7 dias, filtro
  pela unidade da máquina (HKLM), sincronização após login/30 min/manual, rodapé "sincronizado
  HH:MM", tela Configurações só leitura (186 testes). ADR-014 e TA-ADR-027; auditoria sem achado
  aberto acima de informativo.
- **Pela metade:** nada no código. Verificação real depende do responsável (abaixo).
- **Próximo passo:** responsável, nesta ordem: D1–D3 e C4 do 04 → merge → NocoDB (`Publico` em
  Servidores, usuário Viewer na "ITC Bench", base separada + usuário Editor para o espelho) →
  deploy → `.env` (`NOCODB_CADASTROS_TOKEN`, `NOCODB_TABELA_*`, `BENCH_CADASTROS_ETAG_KEY`,
  espelho `NOCODB_ENABLED`/`NOCODB_TOKEN`/`NOCODB_TABLE_ID`) → restart → login real e
  Configurações na bancada, C3 com conta comum (`docs/modules/05-cadastros.md`). Depois, Módulo 06.
- **Tarefas futuras:** trocar a pasta de deploy no servidor para `itc-bench`; PR no TA trocando o
  README; teste de borda pelo túnel. Proposta do ADR-013 para o 06: `/v1/relatorio` aceitar a
  sessão do técnico. Rótulos de módulo antigos em `ui/navegacao.py` (numeração anterior ao ADR-012).
- **Pendências externas:** UAC real do 01 (cenário 7).

## Registro

| Data | Módulo | Resumo |
|---|---|---|
| 2026-11-04 | 05 — Cadastros | API: `GET /v1/bench/cadastros[?unidade=]` com sessão `itcbs_`, NocoDB lido por token Viewer em `nocodb_cadastros.py` (inativo, sem nome e unidade inexistente descartados), cópia em memória TTL 60 s com uma leitura por vez, cópia defasada até 24 h, `ETag` HMAC e `304`, `503 cadastros_indisponivel`, auditoria `0005` com 12 caracteres da versão. App: cache DPAPI em `protegido\cadastros.dpapi` (só memória sem admin), 7 dias, vencido/corrompido apagado, mantido no logout, filtro pela unidade da máquina em HKLM, sincronização após login/30 min/manual, rodapé com unidade e "sincronizado HH:MM", tela Configurações só leitura com segredos mascarados. `Servidores.Publico` falha fechado. API 221 testes, app 186. ADR-014, TA-ADR-027. Auditoria: 1 baixo corrigido (dica rich text), 4 informativos. Espelho ligado no deploy (decisão do responsável). Deploy e cadastros reais pendentes do responsável. |
| 2026-11-04 | 04 — Login | API: login pelo GLPI v2 (OAuth2 `password`, `/session`, perfil em qualquer entidade), sessão `itcbs_` de 12 h só em SHA-256, limite 5/usuário (HMAC) e 20/IP em 15 min no SQLite, auditoria sem senha, migração `0004`, sobe sem as variáveis novas (login `503`). App: cliente stdlib sem redirecionamento, tela Entrar, bloqueio 15 min, offline 7 dias com scrypt + DPAPI de máquina em `protegido\` (SY/BA), técnico no log. Reset do ACL da árvore passou a pular a pasta protegida (o Windows sobrescrevia a DACL dela). API 194 testes, app 149. ADR-013. Auditoria: 2 médios corrigidos, 4 informativos. Deploy, Cloudflare e login real pendentes do responsável. |
| 2026-11-04 | 03 — Transição | Servidor passou a puxar do itc-bench (apelido `github-itc-bench`); backup com SHA-256 registrado; primeiro `api-deploy` verde sem recriar o container; volume, loopback, saúde e migrações iguais; relatório de teste `200` (um `503 ia_timeout` antes, latência do provedor). `push` em `api/**` de volta no `api-deploy.yml`. Pendentes: borda pelo túnel, pasta de deploy, README do TA; NocoDB desligado vai para o 05. Módulo 03 concluído. |
| 2026-11-03 | 03 — Monorepo | `app/` (programa Windows, `git mv`) + `api/` importada com histórico (filter-repo `--path api/` + `--replace-text`, fonte `0bc5620`, merge por `--allow-unrelated-histories`). Hosts reais do histórico reescritos antes do merge; regex e gitleaks limpos na cópia e na branch. Workflows `app-ci`, `api-ci`, `api-deploy` (manual, environment `producao`, `DEPLOY_DIR`), `gitleaks`; dependabot com `uv`. `docs/api/` com TA-ADRs. Plano 03–16 sem [TA]. App 87 testes, API 151. Auditoria só com informativos. ADR-012. Transição no servidor pendente. |
| 2026-11-03 | 02 — Executor | `executar()`/`powershell()` com lista de argumentos, caminho absoluto pela API, dados em `ITC_*` ou stdin, `Sensivel` mascarado (inclusive no CLIXML), Job Object no timeout, saída `auto` (UTF-8/OEM). Ruff `TID251` + teste de AST contra processo fora do executor. `ui/tarefa.py`. ACL SDDL em `%ProgramData%\ITC` com recusa de reparse e retry com privilégios. 87 testes; auditoria sem achado aberto acima de informativo; achado médio do 01 fechado. ADR-011. |
| 2026-11-03 | 01 — Esqueleto | Python 3.13 + PySide6 6.12 com uv (ADR-010). `src/itc_bench/` com `nucleo/` sem Qt, `ui/`, `recursos/` (Archivo e Inter OFL, 20 ícones, símbolo). UAC/`--dev`/`--teste`, log 1 MiB × 5 com queda para `%LOCALAPPDATA%` sem permissão, janela com 7 grupos e 20 telas vazias com "?". 14 testes; auditoria com 1 achado médio (ACL do ProgramData) planejado no 02. |
| 2026-11-03 | 00 — Kickoff | `.gitignore` em `main`; `develop` criada. `AGENTS.md` canônico, `CLAUDE.md` com `@AGENTS.md`, `PROMPT_CLAUDE_CODE.md`; PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA (4 tabelas do NocoDB lidas por metadados), IMPLEMENTATION-PLAN (módulos 00–15), DECISIONS (ADR-001 a ADR-008), AUDIT-PROMPT e baseline `docs/security/2026-11-03-modulo-00.md`. Inclui `docs/design/` e `docs/referencia/`. |
