# Módulo 05 — Cadastros via API com cache DPAPI

**Branch:** `feat/modulo-05-cadastros` · **Data:** 2026-11-04 · **ADR:** ADR-014, TA-ADR-027

Muda `app/` e `api/` no mesmo PR (ADR-012). Desenho proposto e aprovado com ajustes em
`.conversa/` (Etapa 1). Ajustes do responsável: cache filtrado pela unidade da máquina, versão
por HMAC com chave do servidor, uma leitura do NocoDB por vez, `503 cadastros_indisponivel`
separado do `503 glpi_indisponivel`, `Observacao` mascarada sem `Publico`, espelho ligado no
deploy com tokens separados.

## O que entrou

| Item | Onde |
|---|---|
| Leitura do NocoDB isolada: `GET /api/v2/tables/{id}/records` com `fields` e paginação, validação de `Ativo`, campo de exibição, unidade e SHA-256 | `api/app/services/nocodb_cadastros.py` |
| `GET /v1/bench/cadastros[?unidade=]`: sessão `itcbs_`, `ETag` por HMAC, `304`, `422 unidade_invalida`, `503 cadastros_indisponivel`, cópia em memória com TTL e uma leitura por vez, cópia defasada até 24 h | `api/app/routes/cadastros.py`, `api/app/main.py` |
| Migração `0005`: `bench_cadastros_entregas` (auditoria, 90 dias) | `api/app/migrations/0005_20261104_bench_cadastros.sql` |
| Variáveis novas com padrão (sobe sem elas; rota em `503`) | `api/app/config.py`, `api/.env.example` |
| Cliente: `api.cadastros` com `If-None-Match`, `304`, `CadastrosIndisponivel` | `app/src/itc_bench/servicos/api.py` |
| Cache DPAPI em `protegido\cadastros.dpapi`, validade 7 dias, vencido/corrompido apagado, só memória sem admin, filtro por unidade, unidade em HKLM, rótulo do rodapé | `app/src/itc_bench/servicos/cadastros.py`, `app/src/itc_bench/__main__.py` |
| Sincronização após login online, a cada 30 min e sob pedido; rodapé com unidade e "sincronizado HH:MM" | `app/src/itc_bench/ui/janela.py`, `app/src/itc_bench/ui/entrar.py` |
| Tela Configurações só leitura, 4 abas, segredos mascarados, "?" e unidade da máquina | `app/src/itc_bench/ui/configuracoes.py` |

## Decisões de implementação

- **Corrida na cópia em memória (achada pelo teste).** A primeira versão só entrava no lock
  quando o TTL tinha passado; o segundo pedido via o `tentado` já marcado pelo primeiro e
  respondia `503` sem esperar. O teste "dois pedidos sem cópia" pegou; a condição passou a ser
  "sem cópia **ou** TTL vencido". Uma leitura que falhou não se repete dentro do TTL, para o
  NocoDB fora do ar não receber uma leitura por pedido.
- **`versao` curta em todo lugar fora da resposta.** Log da API, auditoria e `bench.log` guardam
  12 caracteres; o `repr` de `Cadastros` não mostra a versão.
- **SSID visível na tela e fora do log.** Logs usam `Id`.
- **SHA-256 do NocoDB não vira rich text.** Texto que não for 64 hex vira vazio na API, e o Bench
  só põe na dica (tooltip do Qt, que interpreta HTML) o que for hex.
- **Troca de unidade sem rede.** O cache é filtrado e regravado com versão vazia: a próxima
  sincronização baixa de novo em vez de receber `304` da versão sem filtro.
- **Logout e troca de técnico não apagam o cache.** O `por` registra quem sincronizou.

## Verificação

API: 221 testes no container (`python:3.12.14-slim-trixie`), 27 novos em
`api/tests/test_cadastros.py`. App: 186 testes, ruff e mypy limpos, `itc-bench --teste` com
código 0. Nada de NocoDB, API ou GLPI reais nos testes.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| A1 | Sem sessão e sessão inválida | `test_sem_sessao_401` | `401 nao_autorizado`; NocoDB não chamado |
| A2 | Token de carreta na rota do Bench | `test_token_de_carreta_nao_vale` | `401` |
| A3 | Sessão válida | `test_200_conteudo_e_filtros` | `200`, `ETag`, `Cache-Control: no-store` |
| A4 | `304` com versão igual (também `W/` e lista); `304` sem sessão | `test_304_com_versao_igual_e_exige_sessao` | `304` sem corpo; sem sessão `401`; auditoria só nos `200` |
| A5 | Registro inativo, sem campo de exibição, unidade inexistente ou inativa | `test_200_conteudo_e_filtros` | Ausentes; `descartados` só com `Id` |
| A6 | Filtro `?unidade=`; unidade inválida | `test_filtro_por_unidade`, `test_unidade_invalida_422` | Só o Wi-Fi dela, versão diferente; `422 unidade_invalida` |
| A7 | NocoDB fora (rede, timeout, 401, HTML) sem cópia | `test_nocodb_fora_sem_copia_503_e_sessao_intacta` | `503 cadastros_indisponivel`; sessão continua `200`; sem nova leitura no TTL |
| A8 | NocoDB lento | `test_nocodb_lento_respeita_timeout`, `test_teto_total_da_leitura` | `503`; teto de 30 s vira `timeout` |
| A9 | NocoDB cai com cópia | `test_copia_defasada_quando_nocodb_cai` | `200` com `defasado: true`; depois de 24 h, `503`; volta sozinho |
| A10 | Dois pedidos, NocoDB lento, sem cópia e com cópia | `test_uma_leitura_por_vez_*` (5 execuções seguidas) | Uma leitura; com cópia, o segundo responde na hora |
| A11 | Versão não deriva só do conteúdo | `test_versao_nao_e_sha256_do_conteudo` | HMAC; mesma chave = mesma versão; chave aleatória muda |
| A12 | Segredo ausente do log da API e do SQLite | `test_segredos_fora_do_log_e_do_sqlite` | Senha, chave, observação, SSID e versão ausentes do `caplog` e dos bytes do `tecnico.db*` |
| A13 | Token do NocoDB ausente de log e erro | `test_erro_do_nocodb_sem_token`, A7 | Ausente mesmo com o NocoDB ecoando o token |
| A14 | Log de acesso do uvicorn real | `test_log_de_acesso_do_uvicorn_sem_corpo_nem_etag` | Só método, caminho e status; sem `If-None-Match`, corpo nem sessão |
| A15 | Sem configuração | `test_nao_configurado_503` | A API sobe; rota `503` |
| B1 | Sincronização online | `test_sincronizacao_online_grava_cifrado`, `test_cadastros_sincronizam_no_login_e_ficam_no_logout` | Arquivo cifrado, `.tmp` some, rodapé "sincronizado HH:MM" |
| B2 | `304` renova a validade | `test_304_renova_a_validade` | `If-None-Match` enviado; `sincronizado_em` novo |
| B3 | Offline com cache válido (sem rede, `503 cadastros_indisponivel`) | `test_offline_mantem_o_cache`, `test_login_offline_mostra_dados_antigos` | Cache mantido; rodapé "offline · dados de …" |
| B4 | `503 cadastros_indisponivel` não é `SemConexao` | `test_cadastros_503_do_nocodb_nao_e_sem_conexao` | `CadastrosIndisponivel`, fora da hierarquia que libera o login offline |
| B5 | Cache vencido (7 dias) e relógio voltado | `test_cache_vencido_e_apagado`, `test_relogio_voltado_vence` | Apagado, aviso "vencido" |
| B6 | Cache corrompido (5 formas) | `test_cache_corrompido_e_apagado` | Apagado, log, aviso; app segue |
| B7 | Logout e troca de técnico | `test_cadastros_sincronizam_no_login_e_ficam_no_logout` | Cache fica; sincronização periódica para |
| B8 | `401` na sincronização | `test_401_na_sincronizacao_volta_para_entrar` | Volta à Entrar com "Sessão expirada" |
| B9 | Sem admin (`--dev`) | `test_sem_admin_so_em_memoria`, `test_sem_cadastros_e_sem_admin_avisam` | Nada em disco; aviso na tela |
| B10 | Unidade: online ressincroniza filtrado; offline filtra e regrava; rodapé | `test_trocar_unidade_*`, `test_unidade_trocada_e_api_fora_filtra_o_cache`, `test_unidade_no_rodape_so_se_estiver_no_cache` | Só o Wi-Fi da unidade no cache; HKLM gravado com admin; "—" para código fora do cache |
| B11 | Segredo ausente de `bench.log` e da tela | `test_segredos_fora_do_log_e_do_repr`, `test_mostra_cadastros_com_segredos_mascarados`; execução real abaixo | Marcadores ausentes de log, `repr`, rótulos, células, dicas e lista; segredos como `••••••••` |
| B12 | Resposta da API fora do formato | `test_resposta_fora_do_formato_mantem_o_cache`, `test_cadastros_403_html_do_access_e_erro_api` | Cache mantido; HTML do Access é `ErroApi` |
| C1 | `cadastros.dpapi` real em `protegido\` | Bench elevado nesta máquina, `icacls` | `AUTORIDADE NT\SISTEMA:(I)(F)` e `BUILTIN\Administradores:(I)(F)`, nada mais; arquivo sem nenhum marcador em claro |
| C2 | `bench.log` real | Sincronização real com a API simulada, `grep` por `Marcador-`, `Rede-Ficticia` e versão longa | 0 ocorrências; linha com a versão de 12 caracteres |
| C3 | Conta comum não lê `cadastros.dpapi` | `runas /user:<conta comum> cmd` + `type` | **Pendente (responsável)**, junto com o C4 do 04: a bancada não tem conta comum de teste. O ACL de C1 não dá nenhuma permissão a `Usuários` |
| D1 | Deploy da API depois do merge na `main`, sem mudar volume nem container | `api-deploy` | **Pendente (responsável)**, depois do D1 do 04 |
| D2 | Cadastros reais | `.env` + login real + Configurações | **Pendente (responsável)** |

## Passos do responsável, depois do merge na `main`

1. Se ainda não fez: D1–D3 e C4 do Módulo 04.
2. NocoDB: coluna `Publico` (Checkbox) em Servidores, marcando só os valores públicos; usuário de
   leitura com papel **Viewer só na base "ITC Bench"** e o token dele.
3. Espelho: base separada com a tabela dos relatórios (`docs/api/NOCODB.md`), usuário **Editor**
   só nela e o token dele.
4. Deploy (`api-deploy`; migração `0005` roda no arranque).
5. `api/.env`: `NOCODB_CADASTROS_TOKEN`, `NOCODB_TABELA_SERVIDORES`, `NOCODB_TABELA_INSTALADORES`,
   `NOCODB_TABELA_WIFI`, `NOCODB_TABELA_UNIDADES`, `BENCH_CADASTROS_ETAG_KEY`; espelho:
   `NOCODB_ENABLED=true`, `NOCODB_TOKEN`, `NOCODB_TABLE_ID` → `restart`.
6. Bancada: login real, Configurações sincronizada, unidade escolhida, rodapé; C3 com conta comum.

## Limites conhecidos

- O arquivo `cadastros.dpapi` nasce com o dono = conta que rodou o Bench elevado (herança da
  pasta). Essa conta é administradora, então não ganha nada além do que já tem.
- A troca de unidade e a sincronização periódica podem gravar o cache ao mesmo tempo; a escrita é
  atômica e a última vence (`ponytail:` em `ui/janela.py`).
- `Instaladores.Link` não é validado aqui; quem baixar (Módulo 10) confere esquema e SHA-256.
