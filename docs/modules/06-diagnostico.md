# Módulo 06 — Diagnóstico (coleta, laudo por IA e Histórico)

**Branch:** `feat/modulo-06-diagnostico` · **Data:** 2026-11-04 · **ADR:** ADR-015, ADR-016,
TA-ADR-028

Muda `app/` e `api/` no mesmo PR (ADR-012). Desenho proposto e aprovado com ajustes em
`.conversa/` (Etapa 1). Ajustes do responsável: `maioresArquivos` sem nome de arquivo, fila de 10
itens e 14 dias, 30 envios por hora por técnico, coluna `unidade` própria com `carreta =
'BANCADA'`, saída do `itcta_` dos notebooks trazida para o 06, `coletadoPor` fora do prompt,
revisão do TA-ADR-023 para o Bench, saneamento por palavra inteira, `409 em_processamento`,
migração testada com banco povoado, gravações anonimizadas em commit próprio.

## O que entrou

| Item | Onde |
|---|---|
| Executor com cancelamento (`cancelar: threading.Event`, espera em fatias, job encerrado) | `app/src/itc_bench/servicos/executor.py` |
| Coletores em trechos PowerShell embutidos (processos, rede, eventlog, disco, bateria, máquina) | `app/src/itc_bench/recursos/coletores/*.ps1` |
| Regras do pendrive em Python, validação da saída, varredura dos perfis, powercfg com HTML apagado | `app/src/itc_bench/servicos/coleta.py` |
| Lista de pares provedor+id derivada da base da API (teste confere) | `app/src/itc_bench/recursos/coletores/eventlog-pares.json` |
| Corpo 1.3, saneamento, limite de 480 KB, envio e histórico | `app/src/itc_bench/servicos/diagnostico.py`, `servicos/api.py` |
| Fila DPAPI de não enviados e reenvio | `app/src/itc_bench/servicos/fila.py` |
| Telas Coleta e laudo e Histórico, renderizador seguro, ajuda das duas | `app/src/itc_bench/ui/diagnostico.py`, `ui/laudo.py`, `ui/janela.py` |
| `POST /v1/bench/relatorio`, `GET /v1/bench/historico/{hostname}`, limite por técnico, idempotência | `api/app/routes/bench_relatorio.py`, `routes/relatorio.py` (`gerar_laudo`) |
| Contrato 1.3 classificado pela base; `coletadoPor`/`bench_usuario` fora do prompt | `api/app/normalizacao.py`, `api/app/prompt.py` |
| Migração `0006`: `diagnosticos` reconstruída, `bench_relatorio_uso` | `api/app/migrations/0006_20261104_bench_diagnostico.sql` |
| Gravação e anonimização das saídas para a paridade | `app/scripts/gravar_paridade.py`, `app/tests/gravacoes/` |

## Decisões de implementação

- **Dois defeitos achados pela paridade (corrigidos, `b59e12d`).** No PS 5.1,
  `@($env:ITC_PARES | ConvertFrom-Json)` embrulhava o array inteiro num item: os Avisos da base
  (disk 51) não eram lidos. E `Sort-Object LocalPort -Unique`, herdado do pendrive, compara o
  texto do objeto CIM (igual em todos) e descarta portas ao acaso; o pendrive em produção tem o
  mesmo defeito. No Bench a deduplicação por porta é em Python.
- **Portas fora da paridade.** Nesta máquina o `Get-NetTCPConnection -State Listen` devolveu
  conjuntos diferentes em chamadas seguidas; a comparação de portas não é reproduzível. Fica o
  teste da regra (uma linha por porta, em ordem).
- **Ordem dos grupos do Event Log com empate.** O `Sort-Object` do pendrive não é estável; a
  paridade compara os grupos sem a ordem e confere à parte a ordem por nível.
- **Processos sem paridade de lista.** Memória e CPU mudam entre duas execuções; a paridade
  compara serviços parados, itens de inicialização e memória total. As gravações não têm a lista
  de processos nem os comandos de inicialização (inventário da máquina de teste).
- **Bateria:** a gravação tem só o `Win32_Battery`; o parse do HTML é testado com os casos do
  `Testar-Ferramenta.ps1`.
- **Cancelar a espera do laudo** não aborta o HTTP: a tarefa termina sozinha no timeout e o
  resultado é descartado; a coleta vai para a fila e o mesmo `envio_id` busca o laudo depois.
- **`carreta` continua `NOT NULL`.** Com `'BANCADA'` fixo, só `token_id` precisou aceitar nulo.

## Verificação

API: 240 (19 novos em `test_bench_relatorio.py` e `test_migrations.py`) testes no container. App: 265 testes, ruff e mypy limpos,
`itc-bench --teste --dev` com código 0. Nada de IA, NocoDB, GLPI ou ntfy reais nos testes.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| C1 | Coleta completa real, elevada | `coleta.coletar(elevado=True)` nesta máquina | Os cinco módulos `ok` (máquina de desenvolvimento, administrador): 258 s no total, 275 s numa execução anterior; quase todo o tempo é a varredura dos perfis em `C:\Users` |
| C2 | Sem admin (`--dev`) | `test_cancelamento_guarda_o_que_ficou_pronto` (aviso), `contadores_smart`/`disco(elevado=False)` | Aviso "sem administrador", SMART com a observação do pendrive, coleta segue |
| C3 | Coletor que falha, devolve lixo ou estoura o tempo | `test_coletor_que_falha_ou_esgota_nao_derruba`, `test_saida_hostil_validada` | Módulo `erro` com motivo curto; os outros `ok` |
| C4 | Cancelamento (coleta e processo filho) | `test_cancelar_encerra_processo_e_filho`, `test_cancelamento_guarda_o_que_ficou_pronto`, `test_cancelar_coleta_guarda_o_que_ficou_pronto`, `test_varredura_cancelada` | Processo e filho encerrados; módulos prontos guardados, os outros "cancelado" |
| C5 | Paridade com o pendrive | `tests/test_paridade.py` sobre gravações da mesma máquina | Passa nos cinco módulos (`processos`, `rede`, `eventlog`, `disco`, `bateria`); achou os dois defeitos de PS 5.1 descritos acima |
| C6 | Gravações anonimizadas | `test_gravacoes_anonimas` | IPs só em faixas de documentação/loopback/link-local, MAC no prefixo fictício, perfis fictícios, sem nome da máquina nem da conta |
| E1 | Envio online com laudo | `test_envio_com_sessao_grava_auditoria_e_classifica`, `test_coleta_online_mostra_areas_e_laudo_como_texto` | `200`; `carreta BANCADA`, `bench_usuario`, `unidade`; laudo na tela |
| E2 | IA fora / lenta | `test_ia_falha_e_reenvio_tenta_na_mesma_linha`, `test_falhas_do_envio[ia_timeout]`, `test_ia_fora_e_tentar_de_novo_usa_o_mesmo_envio` | `503 ia_*`, linha com `falha`; reenvio na mesma linha, mesmo `envio_id` |
| E3 | `401` com sessão expirada no meio | `test_sessao_expirada_401`, `test_janela_401_volta_a_entrar_com_coleta_preservada` | Volta à Entrar; coleta na fila |
| E4 | `429` | `test_limite_por_tecnico_e_nao_por_sessao`, `test_falhas_do_envio[429]` | Limite soma as sessões do técnico; `Retry-After`; coleta na fila |
| E5 | Reenvio concorrente | `test_reenvio_concorrente_409_sem_segunda_ia`, `test_processando_antigo_e_falha_presumida` | `409 em_processamento`, uma chamada à IA; depois de 120 s, nova tentativa |
| E6 | `envio_id` inválido e idempotência | `test_envio_id_invalido_422`, `test_mesmo_envio_devolve_o_gravado_sem_nova_ia` | `422`; mesmo `envio_id` (até em maiúsculas) devolve o gravado, uma linha |
| E7 | Unidade fora da lista | `test_unidade_fora_da_lista_fica_nula` | `unidade` nula, valor fora do log |
| F1 | Offline: coleta vai à fila | `test_offline_vai_para_a_fila`, `test_falhas_do_envio[SemConexao]` | Fila com 1 item, aviso na tela |
| F2 | Reenvio ao voltar a rede, sem duplicata | `test_reenvio_um_por_vez_e_para_sem_conexao`, `test_reenvio_ia_fora_e_422_saem_429_fica`, E6 | Um por vez; para sem conexão; a API grava uma linha por `envio_id` |
| F3 | Fila corrompida ou de formato desconhecido | `test_corrompida_vira_prova_e_fila_recomeca`, `test_formato_desconhecido_e_corrompido` | Renomeada para `.corrompida`, fila recomeça |
| F4 | Limites 10 itens / 14 dias | `test_limite_de_itens_tira_o_mais_antigo`, `test_item_com_mais_de_14_dias_sai` | Mais antigo sai, com log |
| F5 | Logout/troca de técnico | `Fila` é da máquina (`janela._encerrar` não toca nela); `test_reenvio_401_para_e_avisa` | Itens ficam; quem estiver logado envia |
| F6 | Sem admin | `test_sem_admin_so_em_memoria` | Nada em disco; aviso na tela |
| H1 | Histórico com rede | `test_historico_bench_traz_laudo_e_quem_enviou`, `test_historico_com_rede_mostra_laudo_e_pendentes` | Laudos e quem enviou; pendentes no topo; hostname do Windows |
| H2 | Histórico sem rede | `test_historico_sem_rede_so_fila` | Só a fila, aviso |
| R1 | Laudo hostil (`<img src=x onerror>`, `javascript:`, `file:///`, `<a href>`, `<script>`) | `test_html_link_e_imagem_viram_texto`, `test_visor_nao_abre_link_nem_carrega_recurso` | Literais no texto; nenhuma âncora nem imagem no documento; `loadResource` sempre `None` |
| M1 | Marcadores (perfil, caminho, conta) fora do corpo | `test_corpo_1_3_sem_marcadores`, `test_nome_de_perfil_palavra_inteira_sem_mutilar` (perfil `admin` com "Administrators"/"administrador" intactos), `test_nome_de_tres_letras_e_curtos_ignorados`, `test_saneamento_das_gravacoes` | Ausentes; mensagens não mutiladas |
| M2 | Sessão e corpo fora do `bench.log` | `test_envio_ok_timeout_longo_e_sessao_no_cabecalho`, `test_guarda_cifrado_e_le` | Só 8 caracteres do `envio_id`; fila cifrada sem marcador em claro |
| M3 | Corpo e sessão fora do log da API e do SQLite; `coletadoPor` fora do prompt | `test_corpo_e_sessao_fora_do_log_e_do_sqlite`, `test_coletado_por_e_bench_usuario_fora_do_prompt` | Ausentes |
| A1 | Rotas da carreta e do login intocadas | Suite inteira da API (testes de `test_relatorio.py`, `test_bench.py`, `test_auth.py`) | Passando sem mudança nos testes existentes |
| A2 | Migração `0006` com banco povoado | `test_0006_preserva_dados_ids_e_relatorios` | Ids, `relatorios.diagnostico_id`, `foreign_key_check` vazio, `integrity_check` ok, CHECK ativo |
| A3 | Caminhos vizinhos | `test_caminhos_vizinhos`, `test_sem_sessao_ou_com_token_da_carreta_401` | `404/405/422`; token de carreta não vale |
| D1 | `curl` pelo Bypass nas rotas novas e vizinhas | `curl` sem service token | **Pendente (responsável)**, depois do deploy |
| D2 | Deploy da API depois do merge na `main`, com backup | `docs/api/DEPLOY.md` (seção do Módulo 06) | **Pendente (responsável)** |
| D3 | Coleta real na bancada com laudo pela borda e tempo do laudo | Bench elevado + API real | **Pendente (responsável)** |
| D4 | Rede desligada e religada na bancada, sem duplicata no SQLite (`envio_id`) | Bench + `sqlite3` no servidor | **Pendente (responsável)** |

**Tamanho do corpo (item 8 do ajuste):** corpo 1.3 real desta máquina com **29,5 KB** (processos 12,0 KB, disco 6,0 KB, eventlog 4,6 KB, rede 3,7 KB, bateria 0,3 KB), contra 512 KB da API e 480 KB do corte do Bench. Os mesmos módulos do pendrive na mesma máquina somam 33,8 KB **com catálogo de limpeza vazio** (disco 9,1 KB); com o catálogo real, o `itensLimpeza` do pendrive é maior, e o Bench não o envia. O tempo real do laudo pela borda é o passo D3 do responsável

## Passos do responsável, depois do merge na `main`

1. Pendências anteriores (04: D1–D3, C4; 05: D1, D2, C3, espelho), se ainda abertas.
2. Backup do SQLite antes do deploy, com SHA-256 e `integrity_check` (`docs/api/DEPLOY.md`,
   seção "Módulo 06 do Bench").
3. Deploy pelo `api-deploy` (a `0006` roda no arranque), sem mudar volume nem container.
4. Conferir `integrity_check`, `foreign_key_check`, contagem de `diagnosticos` e migrações `[1..6]`.
5. `.env` opcional: `BENCH_RELATORIO_LIMITE_HORA` (padrão 30) → `restart`.
6. `curl` sem service token: `POST /v1/bench/relatorio` e `GET /v1/bench/historico/X` sem sessão
   → `401`; `/v1/relatorio`, `/v1/bench/../relatorio`, `/v1/bench/%2e%2e/relatorio`,
   `/v1/benchx/relatorio` → barrados pelo Access ou `404`.
7. Bancada: coleta elevada, laudo e o tempo dele pela borda; Histórico; rede desligada (fila) e
   religada (reenvio), conferindo uma linha por `envio_id`:
   `SELECT envio_id, count(*) FROM diagnosticos WHERE envio_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1`
   (esperado: nenhuma linha).

Nada muda na Cloudflare.

## Limites conhecidos

- Qualquer técnico com sessão lê o histórico de qualquer hostname (risco aceito, ADR-016).
- Grupos do Event Log ficam sem classificação na tela offline (a API classifica no envio).
- A varredura dos perfis pode levar minutos em máquinas com muitos arquivos; teto de 300 s com
  resultado parcial e aviso.
- `Get-NetTCPConnection` pode devolver conjuntos diferentes entre chamadas; a lista de portas é um
  retrato do momento.
