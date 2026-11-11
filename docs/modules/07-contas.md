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
- **"Aplicar conta Suporte" com a Suporte logada** é permitido (emenda do ADR-017); a confirmação
  avisa que as senhas salvas no Windows dessa conta se perdem.
- **Log sem mensagem do Windows:** falha vai ao log pelo código, aviso pelo tipo (perfil com o
  HResult); a mensagem completa, que pode ter caminho de perfil, só aparece na tela.

## Verificação

App: 313 testes (2 pulados: ciclo real que altera contas e lista local de nomes), ruff e mypy limpos,
`itc-bench --teste --dev` com código 0. Máquina de desenvolvimento (Windows 11, administrador) só para
leitura e para o teste de lista de processos; nada foi criado nem apagado nela. Os cenários que
alteram contas ficam para uma máquina real com o Bench instalado, junto das bancadas do 04–06
(sem VM, decisão do responsável); falhas viram correções em PR próprio.

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
| M0 | Caminho de perfil fora do log (aviso do perfil, erro do Windows, aviso do lote) | `test_caminho_de_perfil_fora_do_log` | Só código/HResult no log; mensagem completa na tela |
| S3 | Aplicar Suporte com a Suporte logada | `test_aplicar_suporte_com_a_suporte_logada` | Permitido, aviso do cofre na confirmação; ações manuais seguem recusando |
| M1 | Senha fora do script, do log e da mensagem | `test_senha_so_no_ambiente_e_como_sensivel` | Só em `ITC_SENHA` como `Sensivel` |
| M2 | Senha fora da lista de processos | `test_senha_fora_da_lista_de_processos` (PowerShell real procura o marcador em `Win32_Process.CommandLine`) | 0 processos |
| M3 | Sem `wmic`, `net user`, `shell=True` ou `subprocess` fora do executor | `test_sem_wmic_net_user_no_src`, `test_sem_shell.py` | Passa |
| M4 | Trechos dentro do limite do executor | `test_scripts_cabem_no_limite` | Todos abaixo de 12 000 caracteres |
| V1 | Criar padrão e admin, com e sem senha, senha não expira | Tela, contas `Teste01`/`Teste02` (roteiro) | **Pendente (máquina real, com o instalador)** |
| V2 | Tornar admin e padrão, trocar e remover senha | Tela (roteiro, passo 6 para V8) | **Pendente (máquina real, com o instalador)** |
| V3 | Tentar nativo, logada, Suporte e último admin na máquina real | Tela (roteiro, passo 6 para V8) | **Pendente (máquina real, com o instalador)** |
| V4 | Excluir com e sem perfil, com perfil carregado | Tela (entrar com `Teste01` e trocar de usuário) | **Pendente (máquina real, com o instalador)** |
| V5 | Clone de grupos | Tela (origem em "Usuários da área de trabalho remota") | **Pendente (máquina real, com o instalador)** |
| V6 | Windows em inglês (grupo por SID) | Máquina em inglês, se houver | **Pendente (máquina real, com o instalador)** |
| V7 | Conta Suporte com e sem rede (cache) | Bench logado, cadastro "Conta Suporte", rede ligada e desligada | **Pendente (máquina real, com o instalador, e cadastro no NocoDB)** |
| V8 | Marcador fora do `bench.log` e da lista de processos durante criar/trocar senha | Tela (roteiro, passo 6 para V8) | **Pendente (máquina real, com o instalador)** |
| F1 | Filtro (ADR-036): modificáveis = locais menos nativo, Suporte e Gestão; o resto em não modificáveis; contagem "N de M" | `test_modificavel`, `test_filtro_modificaveis_e_nao_modificaveis`, `test_sem_admin_so_leitura`, `test_botoes_seguem_as_regras` | Passa |
| F2 | Encerrar sessões (ADR-036): só contas com sessão; marcar e confirmar; pelo SID; recusa a sessão do Bench, sem sessão e falha do `logoff` com mensagem; SID inválido recusado no PowerShell real | `test_com_sessao`, `test_encerrar_sessao_*` (5), `test_encerrar_real_recusa_sid_invalido`, `test_encerrar_sessoes_marca_e_confirma`, `test_escolher_sessoes_libera_so_com_marcada` | Passa |
| F3 | Gestão restrita (ADR-036): não modificável (com ou sem acento, qualquer caixa); toda ação recusada; nome reservado; fora do lote nas duas direções; não vale como Suporte; não deixa a Preparação pendente; recusa real no PowerShell | `test_gestao_*` (4), `test_nome_gestao_reservado_na_criacao`, `test_trechos_tem_a_mesma_lista_de_restritas`, `test_recusa_real_da_gestao_no_powershell` (3), `test_gestao_aparece_so_em_nao_modificaveis`, `test_gestao_administradora_nao_deixa_contas_pendente` | Passa |
| V9 | Encerrar sessões de `Teste01` aberta por troca rápida de usuário; tentar a sessão do Bench | Roteiro, passo 5.8 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

1. NocoDB, base "ITC Bench", tabela Servidores: `Conta Suporte` / `usuario` (valor = nome da conta,
   `Publico` marcado, `Ativo`) e `Conta Suporte` / `senha` (valor = senha nova, `Publico`
   desmarcado, `Ativo`). Uma linha de cada.
2. Trocar a senha Suporte que estava no `segredos.json` do Configurador e aplicá-la em cada
   notebook com "Aplicar conta Suporte".
3. V1–V8 numa máquina real com o instalador (roteiro abaixo).

## Roteiro do teste em máquina real (V1–V8)

1. Use um notebook reserva, nunca o de uso diário. Instale o Bench e entre online.
2. Antes de tudo, confira em Contas que a Suporte existe, está ativa e é administradora (se não,
   "Aplicar conta Suporte").
3. Crie as contas de teste `Teste01` (padrão, com senha) e `Teste02` (administrador, sem senha).
   Rode as ações de tipo, senha, clone e exclusão **só nelas**, incluindo excluir com e sem pasta
   e excluir `Teste01` com sessão aberta (troca rápida de usuário).
4. Tente as recusas sem confirmar nada: Administrador nativo, a conta em uso, a Suporte, o último
   administrador.
5. Lote: "Tornar todos administradores" e depois "Remover administrador de todos (exceto
   Suporte)"; confira que a Suporte continua administradora.
6. Durante uma troca de senha, a lista de processos (`Get-CimInstance Win32_Process`, coluna
   `CommandLine`) não mostra a senha; ao fim, a senha usada não aparece no `bench.log`.
7. Se houver máquina em inglês, repita 3 e 5 nela.
8. Exclua `Teste01` e `Teste02` ao terminar.

Sem `.env`, deploy ou mudança na API.

## Limites conhecidos

- A senha Suporte é a mesma em todos os notebooks (risco aceito, ADR-017).
- Membros de domínio/AzureAD do grupo Administradores não são alterados pelas ações em lote.
- Cópia de pastas pessoais fora do Bench (ADR-017).
- "Conta em uso" vê console, RDP e troca rápida pelo `explorer.exe`; uma sessão sem Explorer
  (shell trocado) só é vista pelo perfil carregado, que bloqueia a exclusão.
