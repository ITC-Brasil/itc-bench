# Módulo 14 — Revisão de segurança e testes de ponta a ponta

**Branch:** `chore/modulo-14-revisao` · **Data:** 2026-11-07 · **ADR:** ADR-024, TA-ADR-031

Revisão, não funcionalidade: nenhuma tela ou regra de produto nova. Plano aprovado em
`.conversa/` (Etapa 1). Auditoria completa em `docs/security/2026-11-07-modulo-14.md`, com o
inventário de pendências de 00 a 13 e o destino de cada uma.

**Decisões do responsável (Etapa 1):**
- entram no 14 os itens 10, 35, 37/45, 40, 16/17 se divergirem, a base dos caminhos pelo ambiente
  e qualquer achado médio ou alto; os informativos aceitos vão num ADR só (ADR-024);
- GLPI em `http://`: risco aceito com TA-ADR até o GLPI ter certificado;
- segredos de todas as unidades e senha Suporte única mantidos; LAPS como tarefa futura;
- roteiro de máquina real escrito agora, executado depois do 15 e antes da primeira release com
  instalador;
- histórico não é reescrito;
- `pip-audit` no CI agora, só como aviso;
- API muda só pela correção do limite de login (e, achado na revisão, pelo `certifi`).

## Correções

| Commit | Tipo | O quê | Teste que falhava antes |
|---|---|---|---|
| `cda404d` | security(app) | `%ProgramData%` e raiz dos perfis pelo HKLM, sem o ambiente do usuário (médio) | `test_programdata_nao_segue_variavel_de_usuario`, `test_pasta_do_sistema_recusa_variavel_que_nao_seja_systemdrive` |
| `1c1e85e` | fix(api) | Limite de login conferido e reservado na mesma transação | `test_tentativas_em_paralelo_nao_passam_do_limite` (8 de 8 chegavam ao GLPI com limite 3) |
| `5198c28` | security(app) | Recusa `TRANSFORMS`, `PATCH`, `MSIPATCHREMOVE`, `SOURCELIST` | `test_propriedade_msi_que_carrega_arquivo_e_recusada` |
| `9ff0dac` | security(app) | Dicas e caixas de mensagem com dado externo em texto puro (`ui/texto.py`) | `test_sem_caixa_estatica_nem_dica_crua` |
| `9a33b6d` | fix(app) | `--dev` só leitura também de um terminal elevado | `test_dev_elevado_roda_sem_admin` |
| `ee25c72` | docs | Conta de desenvolvimento mascarada numa saída gravada | varredura do histórico |
| `d86948b` | security(api) | `certifi` 2026.10.23 (PYSEC-2026-4320) | `pip-audit` |
| `3dfb9ad` | ci | `pip-audit` no `app-ci` e no `api-ci`, só aviso | — |

## Verificação das invariantes

| Invariante | Como foi verificada | Resultado |
|---|---|---|
| Executor único; sem `shell=True`, `cmd /c`, `.bat`, `-ExecutionPolicy`, `Invoke-Expression`, `-EncodedCommand` em trecho, `Start-Process`, `Add-Type` | Testes `test_sem_shell.py` (AST, já existia) e `test_invariantes.py::test_trechos_ps_sem_formas_proibidas` (31 `.ps1` + `ABERTURA_PS`) | Passou; nenhuma ocorrência |
| Dados só por `ITC_*`; script nunca montado com dado | `test_trechos_ps_recebem_dados_so_por_itc`, `test_script_nunca_montado_com_dado`, `test_funcoes_script_so_leem_recursos` (exceção: `desinstalar.script_appx`, constante validada, ADR-023) | Passou |
| Exceções ao executor só pelo critério do ADR-018 | `test_winreg_e_ctypes_so_na_lista_fechada`: 12 módulos, cada um com motivo (ADR-024, item 5); busca `rg -l "^\s*(import\|from) (winreg\|ctypes)" app/src` | Passou; lista do ajuste 1 da Etapa 1 mais `nucleo/caminhos.py` |
| Grupo Administradores só pelo SID | `test_grupo_administradores_so_pelo_sid` | Passou |
| Alvo por SID; recusas do ADR-017/021 iguais | Leitura: `servicos/hive.py:310-321` (`hive.aplicar` → `recusa_alvo` em todo alvo de Políticas, USB, Papel, Mouse); `servicos/etapas.py:78` (contas de aluno pela mesma função); `recursos/contas/comum.ps1` (ADR-017 de novo no PS) | Sem divergência |
| `protegido\` e `%ProgramData%\ITC\Bench`: ACL, dono, sem reparse | Leitura: `nucleo/caminhos.py` (`inicializar` → `verificar_reparse` + `proteger_segredos` a cada abertura elevada), `servicos/retomada.py:52` (arquivo); testes `test_acl.py`; base da pasta corrigida (`cda404d`) | Corrigido o médio; o resto sem divergência |
| Segredo nunca em argumento, log ou ambiente fora de `ITC_*` | `test_ponta_a_ponta.py::test_preparacao_completa_simulada_sem_vazar_dado` (marcadores de senha, SSID, host, chave, tag, SID, perfil) | Passou |
| Log sem senha, token, SSID, host, SID, caminho de perfil | Mesmo teste, com o `Popen` falso devolvendo no stderr tudo que recebeu em `ITC_*` | Passou; o executor mascara `Sensivel` e o log não traz os demais |
| Ação que altera exige sessão válida ou offline (ADR-013) | Testes `test_entrar.py` (`test_comeca_na_entrar_e_entra_online`, `test_sair_e_sessao_expirada_voltam_para_entrar`, `test_401_na_sincronizacao_volta_para_entrar`, `test_bloqueio_*`) | Passou |
| `--dev` nunca altera | `test_dev_elevado_roda_sem_admin`; `test_preparacao_sem_admin_nao_altera_nada` (só o trecho de leitura `identificacao/estado` roda) | Corrigido e passou |
| Qt sem rich text com dado externo | `test_texto_puro.py` (AST em todo o app); laudo por `insertText` (`ui/laudo.py`) | Corrigido e passou |
| Downloads: SHA-256 antes de usar, `https://`, destino fixo | Leitura: `servicos/instaladores.py:71,108,117` (esquema no link e no redirecionamento), hash na cópia e antes de executar; nome `<sha256>.<ext>` em pasta fixa; testes `test_instaladores.py` | Sem divergência |
| API: autenticação e validação em toda rota; sem IDOR por hostname | `api/tests/test_rotas_auth.py` (todas as rotas, lista pública fechada; hostname malformado recusado) | Passou; histórico por hostname é risco aceito (ADR-016) |

## Ponta a ponta simulado

| Cenário | Teste | Resultado |
|---|---|---|
| Preparação completa dos três perfis com os serviços reais, executor falso que falha ecoando os dados, Wi-Fi/registro/rede bloqueados, escrita fora da pasta do teste recusada | `test_preparacao_completa_simulada_sem_vazar_dado` | Passou: as 14 etapas terminam em situação válida; Contas tenta criar a Suporte (senha por `ITC_SENHA`), Programas tenta o download, Remoto tenta o registro; nenhuma escrita fora; nenhum marcador vazado |
| A mesma Preparação sem administrador | `test_preparacao_sem_admin_nao_altera_nada` | Passou: só leitura, nenhuma escrita |
| Login → sessão → cadastros → logout/expiração | `test_entrar.py`, `test_login.py`, `test_offline.py` (existentes) | Passou |
| API: login, cadastros, relatório, histórico com GLPI, NocoDB e IA falsos | suíte da API no container | 246 passaram |

Totais: app 708 passaram e 4 pulados (ruff e mypy limpos); API 246 passaram no container.

## Varredura do histórico e dependências

- `git log -p origin/main origin/develop` com padrões fora do repositório: um achado real
  (conta de desenvolvimento em `docs/modules/02-executor.md`, commit `5e2c9ca`), mascarado no
  arquivo atual; o resto é já tratado (ADR-009) ou IP de exemplo. gitleaks 8.30.1: limpo.
- `pip-audit`: app limpo; API com `certifi` vulnerável, atualizado. Lock da API sem hash
  (`--require-hashes`) e strings do EXE ficam para o 15.

## Máquina real

`docs/testes/maquina-real.md`: roteiro único, de máquina limpa preparada do zero aos casos de
borda de 01 e 04 a 14, com o cenário de origem em cada passo. **Pendente (máquina real, com o
instalador).**

## Limites conhecidos

- O ponta a ponta simulado prova o caminho dos dados e as recusas, não o efeito no Windows: o
  executor falso falha em toda chamada, então as etapas que dependem de uma leitura bem-sucedida
  param na leitura.
- `%LOCALAPPDATA%` continua pelo ambiente (preferências do usuário, sem segredo).
- `--dev` não exercita escrita; teste de escrita só nos testes automatizados e na máquina real.

## Passos do responsável

- Deploy da API depois do merge (`api-deploy.yml`): limite de login e `certifi`.
- Executar `docs/testes/maquina-real.md` depois do 15.
