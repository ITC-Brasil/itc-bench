# Módulo 04 — Login e sessão

**Branch:** `feat/modulo-04-login` · **Data:** 2026-11-04 · **ADR:** ADR-013

Primeiro módulo que muda `app/` e `api/` no mesmo PR (ADR-012). Desenho proposto e aprovado com
ajustes em `.conversa/` (Etapa 1); acesso pelo **perfil** do GLPI, não pelo grupo, decidido pelo
responsável depois da aprovação.

## O que entrou

| Item | Onde |
|---|---|
| Integração GLPI isolada: API v2, OAuth2 grant `password`, `GET /session`, perfis em qualquer entidade | `api/app/services/glpi.py` |
| Rotas `POST /v1/bench/login`, `POST /v1/bench/logout`, `GET /v1/bench/sessao`, `GET /v1/bench/saude` | `api/app/routes/bench.py`, `api/app/auth.py` (`exigir_sessao`) |
| Migração `0004`: sessões, tentativas, auditoria (sem coluna de senha) | `api/app/migrations/0004_20261104_bench_login.sql` |
| Variáveis novas com padrão (sobe sem elas; login em `503`), recusa de `GLPI_URL` pública em `http://` | `api/app/config.py`, `api/app/main.py`, `api/.env.example` |
| Cliente da API só com stdlib, sem redirecionamento, JSON obrigatório | `app/src/itc_bench/servicos/api.py` |
| Online x offline e destravamento | `app/src/itc_bench/servicos/login.py` |
| Cofre offline: scrypt + DPAPI de máquina | `app/src/itc_bench/servicos/offline.py`, `app/src/itc_bench/nucleo/dpapi.py` |
| Pasta protegida `protegido\` (SY e BA) e reset do ACL da árvore que não toca nela | `app/src/itc_bench/nucleo/acl.py`, `nucleo/caminhos.py` |
| Tela Entrar, bloqueio por 15 min, logout, sessão vencida | `app/src/itc_bench/ui/entrar.py`, `ui/janela.py`, `ui/tema.py`, `__main__.py` |
| Técnico em cada linha do log | `app/src/itc_bench/nucleo/log.py`, `ui/log_qt.py`, `ui/tarefa.py` |

## Decisões de implementação

- **Reset do ACL e pasta protegida.** Testado nesta máquina: `TreeSetNamedSecurityInfoW` com
  `TREE_SEC_INFO_SET`, `RESET` e `RESET_KEEP_EXPLICIT` sobrescreve até a DACL protegida de uma
  subpasta. Reaplicar o ACL do ADR-011 e depois proteger a subpasta deixaria `Usuários` com leitura
  no `logins.dpapi` por alguns milissegundos (e um handle aberto nessa janela continua valendo).
  Por isso `acl.proteger(raiz, exceto=...)` aplica sem recursão na raiz e nas pastas a caminho da
  protegida (o Windows propaga a herança e pula a DACL protegida) e com recursão em cada irmã,
  que volta a só herdar. Um teste espia cada passo e confere que o arquivo nunca tem `BU`.
- **GLPI por `/session`.** O campo `profiles` é o `$_SESSION['glpiprofiles']` (todos os perfis
  do usuário em todas as entidades; `CoreController` do GLPI 11); `active_profile` é ignorado.
- **Limite antes do GLPI, em duas transações.** Conferência e contagem são separadas para não
  segurar o lock do SQLite durante a chamada ao GLPI; tentativas em paralelo podem passar do limite
  por poucas unidades (`ponytail:` no código).
- **Recusa esperada não é falha do programa.** Na tela, `Recusado`, `SemConexao`, `ErroApi` e
  `OfflineRecusado` voltam como valor da tarefa: mensagem na tela e uma linha `INFO`, sem
  traceback.
- **Rich text.** Nome do GLPI e mensagens em `QLabel` com `PlainText`; rodapés com `<br>` usam
  `html.escape` no hostname e no login (achado da auditoria, corrigido em `c81e7be`).
- **Timer da sessão** limitado a `2**31 - 1` ms (o `QTimer` é int32).

## Verificação

API: 194 testes no container (`python:3.12.14-slim-trixie`, comando do `AGENTS.md`), 43 novos em
`api/tests/test_bench.py`, GLPI falso por `httpx.MockTransport`. App: 149 testes (`uv run pytest`,
shell elevado, então os testes `so_admin` rodaram), `ruff check`, `ruff format --check` e
`mypy` limpos; `itc-bench --teste` elevado e `--teste --dev` com código 0.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| A1 | Login certo | `test_login_certo_devolve_sessao_que_vale_em_sessao` | `200`, `itcbs_` válido em `/sessao`, só o SHA-256 no banco, auditoria `ok` |
| A2 | Senha errada | `test_senha_errada_401_e_audita_hmac` | `401 credenciais_invalidas`, auditoria com `h:` + HMAC, sem o usuário |
| A3 | Sem o perfil / perfil só em entidade secundária | `test_acesso_pelo_perfil_em_qualquer_entidade` | sem perfil `403 fora_do_perfil`; com perfil ativo ou secundário `200` |
| A4 | GLPI fora do ar, `500`, formato estranho, `invalid_client` | `test_glpi_fora_lento_ou_estranho_503` | `503 glpi_indisponivel`, não conta tentativa, corpo do GLPI fora do log |
| A5 | GLPI lento (timeout) | mesmo teste (`timeout`) + `test_timeout_usa_glpi_timeout_seconds` | `503`; `GLPI_TIMEOUT_SECONDS` chega ao httpx |
| A6 | Limite atingido e liberado | `test_limite_por_usuario_atinge_e_libera`, `test_limite_por_ip_com_usuarios_diferentes` | 6ª tentativa `429`, `Retry-After` até o fim da janela, GLPI não chamado; janela seguinte `200`; IP com 3 → `429`, outro IP `200` |
| A7 | Sessão expirada | `test_sessao_expirada_401` | `401` depois de 12 h |
| A8 | Sessão revogada no logout | `test_logout_revoga` | `204`; a mesma sessão dá `401`; logout repetido `204` |
| A9 | Senha fora do log e do SQLite (inclusive digitada no campo usuário) | `test_senha_ausente_de_log_e_sqlite`, `test_alerta_no_limite_sem_usuario_por_extenso` | marcadora ausente do arquivo `.db`, das tabelas, do `caplog` e do alerta |
| A10 | Deploy sem parada: sem `GLPI_*`/HMAC, ou `GLPI_URL` pública em `http://` | `test_sem_configuracao_ou_url_publica_sobe_e_responde_503`, `test_defaults_sobem_sem_variaveis_novas` | API sobe, `/v1/saude` `200`, login `503`, GLPI não chamado |
| A11 | Caminhos vizinhos | `test_caminhos_vizinhos_nao_abrem_rota_da_carreta` | `/v1/benchx`, `../relatorio`, `%2e%2e`, `//v1/relatorio` → 401/404/405 na API |
| A12 | Token da carreta x sessão | `test_token_da_carreta_nao_vale_como_sessao_e_vice_versa` | `401` nos dois sentidos |
| B1 | Login online | `test_comeca_na_entrar_e_entra_online` | começa na Entrar; entra; senha limpa do campo; técnico no log; relógio ativo |
| B2 | Offline dentro de 7 dias | `test_senha_certa_dentro_de_7_dias`, `test_sem_servidor_cai_para_offline` | entra com 6 d 23 h; `URLError`, 502, 530 e `glpi_indisponivel` liberam |
| B3 | Offline depois de 7 dias | `test_depois_de_7_dias_recusa_e_apaga` | recusa e apaga a entrada |
| B4 | Senha errada offline | `test_senha_errada_e_bloqueio_apos_5` | `senha_errada` 4×, na 5ª a entrada é apagada |
| B5 | 401/403/429 e não-JSON nunca liberam offline | `test_recusa_nunca_cai_para_offline`, `test_401_e_403_apagam_o_offline` | exceção repassada; 401/403 apagam o offline, 429 não |
| B6 | Resposta da Cloudflare no lugar da API | `test_403_em_html_do_access_nao_e_fora_do_perfil`, `test_redirecionamento_nao_e_seguido`, `test_200_em_html_e_erro_api`, `test_429_com_e_sem_retry_after` | `ErroApi`; 302 não seguido; 429 sem `Retry-After` com mensagem genérica |
| B7 | Relógio voltado | `test_relogio_voltado_recusa` | recusa |
| B8 | scrypt real com `maxmem` | `test_scrypt_real_com_maxmem` | calcula; sem `maxmem` dá `ValueError` |
| B9 | Bloqueio por 15 min | `test_ocioso_conta_tecla_e_vence`, `test_bloqueio_e_destravar_pelo_mesmo_tecnico_sem_rede` | tecla reinicia; ao vencer, Entrar "Bloqueado"; mesmo técnico destrava sem chamar a API |
| B10 | Bloqueio sem pasta protegida (`--dev`) | `test_bloqueio_sem_pasta_protegida_exige_login_completo` | login completo |
| B11 | Troca de técnico, logout, sessão vencida | `test_outro_tecnico_no_bloqueio_vira_troca`, `test_sair_e_sessao_expirada_voltam_para_entrar` | log com o novo técnico; logout e expiração voltam à Entrar |
| B12 | Técnico no log | `test_tecnico_em_cada_linha` + `bench.log` real | `[-]` antes, `[ana.lima]`, `[ana.lima (offline)]`; execução real elevada grava `INFO [-] itc_bench: ...` |
| B13 | Senha ausente de `bench.log` | `test_senha_ausente_do_bench_log` | busca da marcadora no arquivo: ausente, com senha errada, login e destravamento |
| C1 | `icacls` da pasta protegida | execução elevada real | `protegido`: só `AUTORIDADE NT\SISTEMA:(OI)(CI)(F)` e `BUILTIN\Administradores:(OI)(CI)(F)`; SDDL `D:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)`; `logs` segue com `Usuários (RX)` herdado |
| C2 | Reset da árvore nunca dá `BU` à protegida; ACL alterado é refeito | `test_pasta_protegida_nunca_fica_legivel_para_usuarios`, `test_pasta_protegida_com_acl_alterado_e_refeita` | nenhum passo com `BU`; `icacls /grant Usuários:R` desfeito na execução seguinte |
| C3 | Reparse recusado | `test_junction_na_pasta_protegida_e_recusada` | `PontoDeReparse` |
| C4 | Conta comum não lê nem lista `protegido` | `runas /user:<conta comum> cmd` + `dir` e `type` | **Pendente (responsável):** a bancada não tem conta comum de teste; o ACL de C1 não dá nenhuma permissão a `Usuários` |
| D1 | Deploy da API depois do merge na `main` | `api-deploy` | **Pendente (responsável)** |
| D2 | Borda: Bypass em `/v1/bench/` e `curl` dos caminhos vizinhos sem service token | Cloudflare + `curl` | **Pendente (responsável)** |
| D3 | Login real no GLPI (com e sem o perfil) | Bench na bancada com `ApiUrl` | **Pendente (responsável)**, depois de D1 e D2 |

## Passos do responsável, nesta ordem

1. Merge `develop` → `main`: o `api-deploy` aplica a `0004` (só aditiva; volume e container iguais).
2. `.env` do servidor: `GLPI_URL` (interna), `GLPI_OAUTH_CLIENT_ID`, `GLPI_OAUTH_CLIENT_SECRET`,
   `GLPI_PERFIL_TECNICOS_ID`, `BENCH_LOGIN_HMAC_KEY` (gerada com `secrets.token_urlsafe(32)`).
   No GLPI: cliente OAuth com grant `password` e escopo `api`.
3. `docker compose restart` (ou novo deploy).
4. Cloudflare: aplicação Access com Bypass em `/v1/bench/`; regra de rate limiting em
   `/v1/bench/login` por IP (plano Free: 10 s de janela, 10 s de bloqueio; reforço apenas).
5. `curl` sem service token: `/v1/bench/saude` → `200`; `/v1/relatorio`,
   `/v1/bench/../relatorio`, `/v1/bench/%2e%2e/relatorio`, `//v1/relatorio`, `/v1/benchx` →
   barrados pelo Access ou `404`.
6. Bancada: `HKLM\SOFTWARE\ITC\Bench`, valor `ApiUrl` com o endereço da API; login real; teste
   C4 com uma conta comum.

## Limites conhecidos

- Técnico desligado ou senha trocada no GLPI vale offline por até 7 dias sem rede (risco aceito,
  ADR-013).
- O técnico do log é global: tarefa de A que termina depois da troca para B sai com B (a tarefa
  registra quem a iniciou na mensagem de falha).
- Dois Bench abertos ao mesmo tempo podem gravar o cofre em sequência e perder a contagem de
  falhas de um deles (o último `replace` vence).
