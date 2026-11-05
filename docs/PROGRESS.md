# PROGRESS — ITC Bench

## ESTADO ATUAL

- **Branch:** `feat/modulo-06-diagnostico-v2`, PR para `develop` (merge commit).
- **Feito:** Módulo 06 no código. App: coletores portados em trechos PowerShell embutidos pelo
  executor (agora com cancelamento), regras do pendrive em Python, contrato 1.3 saneado (perfis,
  contas e nomes de arquivo fora), fila DPAPI `protegido\fila-diagnostico.dpapi` (10 itens, 14
  dias), telas Coleta e laudo e Histórico com ajuda, laudo renderizado só com `insertText`
  (266 testes, paridade com o pendrive sobre gravações anonimizadas). API: `POST
  /v1/bench/relatorio` e `GET /v1/bench/historico/{hostname}` com sessão, limite por técnico,
  idempotência por `envio_id` com `409 em_processamento`, migração `0006` (240 testes). ADR-015,
  ADR-016, TA-ADR-028; auditoria sem achado acima de informativo.
- **Pela metade:** nada no código. Verificação real depende do responsável (D1–D4 de
  `docs/modules/06-diagnostico.md`).
- **Próximo passo:** responsável, depois do merge: pendências do 04/05 → backup do SQLite →
  deploy (`0006`) → conferências → `curl` → bancada (coleta, laudo pela borda, fila e reenvio).
  Depois, Módulo 07.
- **Tarefas futuras:** trocar a pasta de deploy no servidor para `itc-bench`; PR no TA trocando o
  README; teste de borda pelo túnel; rótulos de módulo antigos em `ui/navegacao.py`; corrigir no
  pendrive o `Sort-Object LocalPort -Unique` (perde portas ao acaso) se ele continuar em uso.
- **Pendências externas:** UAC real do 01 (cenário 7).

## Registro

| Data | Módulo | Resumo |
|---|---|---|
| 2026-11-04 | 06 — Diagnóstico | App: coletores portados (trechos PS embutidos, regras em Python), executor com cancelamento, contrato 1.3 saneado, fila DPAPI 10/14 dias, telas Coleta e laudo e Histórico, laudo só com `insertText`, paridade com o pendrive sobre gravações anonimizadas (achou 2 defeitos de PS 5.1). API: `/v1/bench/relatorio` e `/historico` com sessão, 30/h por técnico, idempotência por `envio_id`, `0006` reconstrói `diagnosticos`. `itcta_` fora dos notebooks. App 265 testes, API 240. ADR-015, ADR-016, TA-ADR-028. Auditoria: 4 informativos. Deploy e bancada pendentes do responsável. |
| 2026-11-04 | 05 — Cadastros | API: `GET /v1/bench/cadastros[?unidade=]` com sessão `itcbs_`, NocoDB lido por token Viewer em `nocodb_cadastros.py` (inativo, sem nome e unidade inexistente descartados), cópia em memória TTL 60 s com uma leitura por vez, cópia defasada até 24 h, `ETag` HMAC e `304`, `503 cadastros_indisponivel`, auditoria `0005` com 12 caracteres da versão. App: cache DPAPI em `protegido\cadastros.dpapi` (só memória sem admin), 7 dias, vencido/corrompido apagado, mantido no logout, filtro pela unidade da máquina em HKLM, sincronização após login/30 min/manual, rodapé com unidade e "sincronizado HH:MM", tela Configurações só leitura com segredos mascarados. `Servidores.Publico` falha fechado. API 221 testes, app 186. ADR-014, TA-ADR-027. Auditoria: 1 baixo corrigido (dica rich text), 4 informativos. Espelho ligado no deploy (decisão do responsável). Deploy e cadastros reais pendentes do responsável. |
| 2026-11-04 | 04 — Login | API: login pelo GLPI v2 (OAuth2 `password`, `/session`, perfil em qualquer entidade), sessão `itcbs_` de 12 h só em SHA-256, limite 5/usuário (HMAC) e 20/IP em 15 min no SQLite, auditoria sem senha, migração `0004`, sobe sem as variáveis novas (login `503`). App: cliente stdlib sem redirecionamento, tela Entrar, bloqueio 15 min, offline 7 dias com scrypt + DPAPI de máquina em `protegido\` (SY/BA), técnico no log. Reset do ACL da árvore passou a pular a pasta protegida (o Windows sobrescrevia a DACL dela). API 194 testes, app 149. ADR-013. Auditoria: 2 médios corrigidos, 4 informativos. Deploy, Cloudflare e login real pendentes do responsável. |
| 2026-11-04 | 03 — Transição | Servidor passou a puxar do itc-bench (apelido `github-itc-bench`); backup com SHA-256 registrado; primeiro `api-deploy` verde sem recriar o container; volume, loopback, saúde e migrações iguais; relatório de teste `200` (um `503 ia_timeout` antes, latência do provedor). `push` em `api/**` de volta no `api-deploy.yml`. Pendentes: borda pelo túnel, pasta de deploy, README do TA; NocoDB desligado vai para o 05. Módulo 03 concluído. |
| 2026-11-03 | 03 — Monorepo | `app/` (programa Windows, `git mv`) + `api/` importada com histórico (filter-repo `--path api/` + `--replace-text`, fonte `0bc5620`, merge por `--allow-unrelated-histories`). Hosts reais do histórico reescritos antes do merge; regex e gitleaks limpos na cópia e na branch. Workflows `app-ci`, `api-ci`, `api-deploy` (manual, environment `producao`, `DEPLOY_DIR`), `gitleaks`; dependabot com `uv`. `docs/api/` com TA-ADRs. Plano 03–16 sem [TA]. App 87 testes, API 151. Auditoria só com informativos. ADR-012. Transição no servidor pendente. |
| 2026-11-03 | 02 — Executor | `executar()`/`powershell()` com lista de argumentos, caminho absoluto pela API, dados em `ITC_*` ou stdin, `Sensivel` mascarado (inclusive no CLIXML), Job Object no timeout, saída `auto` (UTF-8/OEM). Ruff `TID251` + teste de AST contra processo fora do executor. `ui/tarefa.py`. ACL SDDL em `%ProgramData%\ITC` com recusa de reparse e retry com privilégios. 87 testes; auditoria sem achado aberto acima de informativo; achado médio do 01 fechado. ADR-011. |
| 2026-11-03 | 01 — Esqueleto | Python 3.13 + PySide6 6.12 com uv (ADR-010). `src/itc_bench/` com `nucleo/` sem Qt, `ui/`, `recursos/` (Archivo e Inter OFL, 20 ícones, símbolo). UAC/`--dev`/`--teste`, log 1 MiB × 5 com queda para `%LOCALAPPDATA%` sem permissão, janela com 7 grupos e 20 telas vazias com "?". 14 testes; auditoria com 1 achado médio (ACL do ProgramData) planejado no 02. |
| 2026-11-03 | 00 — Kickoff | `.gitignore` em `main`; `develop` criada. `AGENTS.md` canônico, `CLAUDE.md` com `@AGENTS.md`, `PROMPT_CLAUDE_CODE.md`; PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA (4 tabelas do NocoDB lidas por metadados), IMPLEMENTATION-PLAN (módulos 00–15), DECISIONS (ADR-001 a ADR-008), AUDIT-PROMPT e baseline `docs/security/2026-11-03-modulo-00.md`. Inclui `docs/design/` e `docs/referencia/`. |
