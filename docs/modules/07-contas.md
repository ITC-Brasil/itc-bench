# Módulo 07 — Contas

**Branch:** `feat/modulo-07-contas` · **Data:** 2026-11-05 · **ADR:** ADR-017

Só `app/`; a API não muda. Desenho proposto e aprovado com ajustes em `.conversa/` (Etapa 1).
Ajustes do responsável: conta Suporte em Servidores (`Conta Suporte`/`usuario` público e
`Conta Suporte`/`senha` não público), cópia de pastas fora, conta "ITC" deixa de existir como
protegida, as duas ações em lote ficam (com a exceção da conta logada só em "remover administrador
de todos"), conta logada também sem troca de senha, Suporte protegida pelo nome cadastrado e por
`Suporte`, tamanho do perfil com teto de tempo, só nomes fictícios em teste e documento.

## O que entrou

| Item | Onde |
|---|---|
| Trechos PowerShell: comum (regras, membros por SID com fallback ADSI, contas em uso), listar, criar, tipo, senha, excluir, suporte, lote | `app/src/itc_bench/recursos/contas/*.ps1` |
| Regras puras (`validar_nome`, `recusa`, `mudariam`, `suporte_ok`, `suporte_do_cadastro`, `protegidas`), execução e log | `app/src/itc_bench/servicos/contas.py` |
| Tela Contas com ajuda, confirmação com resumo, exclusão com nome digitado | `app/src/itc_bench/ui/contas.py`, `ui/janela.py` |
| Testes | `app/tests/test_contas.py`, `app/tests/test_contas_tela.py` |

## Decisões de implementação

- **Conta Suporte junto do serviço de contas.** `suporte_do_cadastro` e `aplicar_suporte` ficam em
  `servicos/contas.py` (lêem os `Cadastros` do 05); por isso os commits "serviço" e "origem da
  senha Suporte" do desenho viraram um só.
- **Remover senha** pelo ADSI (`UserFlags | 0x20` e `SetPassword('')`): o `Set-LocalUser` não tem
  o equivalente do `-NoPassword`. Política de senha mínima da máquina faz isso falhar com a
  mensagem do Windows.
- **Avisos do PowerShell** (membros por ADSI, dono de `explorer.exe` que saiu no meio) vão para o
  stderr e para o log como aviso; não interrompem a leitura.
- **A tela lê as contas ao abrir**, não ao montar a janela (a leitura roda PowerShell).
- **Membros de domínio/AzureAD** do grupo Administradores aparecem numa linha só leitura e ficam
  como estão nas duas ações em lote (fora do escopo, ADR-017).
- **"Aplicar conta Suporte" com a Suporte logada** recusa (regra da conta logada). Para trocar a
  senha Suporte, o técnico entra com outra conta.

## Verificação

App: 310 testes (2 pulados: ciclo real da VM e lista local de nomes), ruff e mypy limpos,
`itc-bench --teste --dev` com código 0. Máquina de desenvolvimento (Windows 11, administrador) só para
leitura e para o teste de lista de processos; nada foi criado nem apagado nela. Os cenários que
alteram contas ficam para a VM de teste (`ITC_TESTE_CONTAS=1` roda `test_ciclo_real_em_vm`).

| # | Cenário | Como | Resultado |
|---|---|---|---|
| L1 | Listar | `test_listar_real` (PowerShell real) | Contas locais com SID `S-1-5-21-…`; RIDs 501/503/504 fora; conta Microsoft marcada como não local e "em uso" |
| L2 | `--dev` sem admin | `test_sem_admin_so_leitura` | Lista aparece; todos os botões de alteração desligados |
| N1 | Nome inválido, reservado, duplicado | `test_validar_nome` (17 casos) e `test_validacao_ao_digitar` | Recusado com a mensagem certa; `ITC` aceito |
| N2 | Nome igual a grupo ou computador | `criar.ps1` (`nome_grupo`, `nome_computador`) e `validar_nome` | Recusado (Python para computador; PS para os dois) |
| R1 | Administrador nativo | `test_nativo_bloqueia_tudo`, `test_segunda_checagem_no_powershell` | Todas as ações recusadas no Python e no PS |
| R2 | Conta logada (rebaixar, senha, remover senha, excluir) | `test_conta_logada`, `test_segunda_checagem_no_powershell` | Recusadas; tornar admin permitido |
| R3 | Suporte (nome cadastrado e `Suporte`) | `test_suporte_protegida_pelo_padrao_e_pelo_cadastrado`, PS idem | Recusada fora de "Aplicar conta Suporte" |
| R4 | Último administrador ativo | `test_ultimo_admin_ativo` | Rebaixar e excluir recusados; com outro admin ativo, permitido |
| R5 | Perfil carregado | `test_perfil_carregado_bloqueia_so_exclusao` | Exclusão recusada |
| R6 | Conta Microsoft | `test_conta_microsoft_so_leitura` | Só leitura |
| R7 | Regra só no Python não chama o PS | `test_recusa_em_python_nao_chama_powershell` | Nenhuma chamada de alteração |
| S1 | Suporte pelo cadastro: sem cache, sem senha, senha pública, linha duplicada, nome cadastrado | `test_suporte_do_cadastro` | Recusas com o que falta; nome cadastrado usado |
| S2 | Aplicar Suporte: nativa, logada, criada | `test_aplicar_suporte_recusas` | Recusas sem chamar o PS; senha só como `Sensivel` |
| B1 | Tornar todos administradores / remover de todos | `test_lote_quem_muda`, `test_lote_padrao_recusa_sem_suporte` | Lista certa; logada incluída no "remover"; recusa sem Suporte ativa e admin |
| E1 | Excluir: nome digitado exato | `test_exclusao_exige_nome_exato` | Botão só com o nome igual (maiúsculas contam) |
| E2 | Excluir com perfil que falha | `test_excluir_perfil_que_falhou_e_aviso` | Conta excluída, aviso "use a Limpeza" |
| E3 | Tamanho do perfil com teto | `test_tamanho_perfil` | Soma correta; teto estourado → "não calculado" |
| M1 | Senha fora do script, do log e da mensagem | `test_senha_so_no_ambiente_e_como_sensivel` | Só em `ITC_SENHA` como `Sensivel` |
| M2 | Senha fora da lista de processos | `test_senha_fora_da_lista_de_processos` (PowerShell real procura o marcador em `Win32_Process.CommandLine`) | 0 processos |
| M3 | Sem `wmic`, `net user`, `shell=True` ou `subprocess` fora do executor | `test_sem_wmic_net_user_no_src`, `test_sem_shell.py` | Passa |
| M4 | Trechos dentro do limite do executor | `test_scripts_cabem_no_limite` | Todos abaixo de 12 000 caracteres |
| V1 | Criar padrão e admin, com e sem senha, senha não expira | VM, `test_ciclo_real_em_vm` + tela | **Pendente (VM de teste)** |
| V2 | Tornar admin e padrão, trocar e remover senha | VM | **Pendente (VM de teste)** |
| V3 | Tentar nativo, logada, Suporte e último admin na máquina real | VM | **Pendente (VM de teste)** |
| V4 | Excluir com e sem perfil, com perfil carregado | VM (entrar com a conta e trocar de usuário) | **Pendente (VM de teste)** |
| V5 | Clone de grupos | VM (conta de origem em "Usuários da área de trabalho remota") | **Pendente (VM de teste)** |
| V6 | Windows em inglês (grupo por SID) | VM en-US | **Pendente (VM de teste)** |
| V7 | Conta Suporte com e sem rede (cache) | VM com Bench logado, cadastro "Conta Suporte" | **Pendente (responsável: cadastro no NocoDB)** |
| V8 | Marcador fora do `bench.log` e da lista de processos durante criar/trocar senha | VM | **Pendente (VM de teste)** |

## Passos do responsável

1. NocoDB, base "ITC Bench", tabela Servidores: `Conta Suporte` / `usuario` (valor = nome da conta,
   `Publico` marcado, `Ativo`) e `Conta Suporte` / `senha` (valor = senha nova, `Publico`
   desmarcado, `Ativo`). Uma linha de cada.
2. Trocar a senha Suporte que estava no `segredos.json` do Configurador e aplicá-la em cada
   notebook com "Aplicar conta Suporte".
3. VM Windows 11 pt-BR (e uma en-US) para V1–V8.

Sem `.env`, deploy ou mudança na API.

## Limites conhecidos

- A senha Suporte é a mesma em todos os notebooks (risco aceito, ADR-017).
- Membros de domínio/AzureAD do grupo Administradores não são alterados pelas ações em lote.
- Cópia de pastas pessoais fora do Bench (ADR-017).
- "Conta em uso" vê console, RDP e troca rápida pelo `explorer.exe`; uma sessão sem Explorer
  (shell trocado) só é vista pelo perfil carregado, que bloqueia a exclusão.
