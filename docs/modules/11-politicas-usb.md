# Módulo 11 — Políticas e USB

**Branch:** `feat/modulo-11-politicas-usb` · **Data:** 2026-11-06 · **ADR:** ADR-021

Só `app/`; a API não muda. O desenho foi proposto e aprovado em `.conversa/` (Etapa 1).

Respostas do responsável:
- USB = bloquear e liberar armazenamento removível (`Deny_All`), por conta e na máquina, sem
  cópia para pendrive;
- a Microsoft Store entra, com aviso de edição;
- "Ocultar unidade C:" não entra;
- sem reaplicação no logon.

Ajustes incorporados:
- sobras do Configurador (dois nomes fixos) e o legado `DisallowRun\1`;
- o Python nunca abre o hive temporário;
- cancelamento só entre chamadas;
- dono da chave na conferência de ACL e o Default User explicado;
- recusa da conta que roda o Bench;
- aviso de edição no lugar de cadeado;
- leitura só em 64 bits;
- alvos só de `contas.listar()`.

## O que entrou

| Item | Onde |
|---|---|
| Catálogo fechado (12 políticas), situação, recusas, aplicar/desfazer, sobras do Configurador | `app/src/itc_bench/servicos/politicas.py` |
| Trechos fixos: comum (raízes, hive, 64 bits), leitura com ACL, escrita com SDDL, carga/descarga do hive | `app/src/itc_bench/recursos/politicas/{comum,ler,escrever,hive}.ps1` |
| Telas Segurança › Políticas e Segurança › USB (mesmo painel), com ajuda | `app/src/itc_bench/ui/politicas.py`, `ui/janela.py` |
| Rótulos de módulo da navegação corrigidos (tarefa futura do PROGRESS) | `ui/navegacao.py` |

## Catálogo

| Id | Política | Escopo | Valor | Desfazer | Aviso de edição |
|---|---|---|---|---|---|
| `cmd` | Bloquear Prompt de Comando | conta | `Software\Policies\Microsoft\Windows\System` `DisableCMD = 2` | apaga | — |
| `regedit` | Bloquear Editor do Registro | conta | `...\CurrentVersion\Policies\System` `DisableRegistryTools = 1` | apaga | — |
| `painel` | Bloquear Painel de Controle e Configurações | conta | `...\Policies\Explorer` `NoControlPanel = 1` | apaga | — |
| `programas` | Bloquear Programas e Recursos | conta | `...\Policies\Uninstall` `NoAddRemovePrograms = 1` | apaga | — |
| `temas` | Remover a página de Temas | conta | `...\Policies\Explorer` `NoThemesTab = 1` | apaga | — |
| `ponteiros` | Bloquear troca de ponteiros | conta | `Software\Policies\Microsoft\Windows\Personalization` `NoChangingMousePointers = 1` | apaga | — |
| `powershell` | Bloquear PowerShell pelo Explorer | conta | `DisallowRun = 1`, `DisallowRun\ITCBench1..3` | apaga os três, o legado `1 = PowerShell.exe` e `DisallowRun` se a lista ficar vazia | — |
| `store` | Bloquear Microsoft Store | conta e máquina | `Software\Policies\Microsoft\WindowsStore` `RemoveWindowsStore = 1` | apaga | Home e Pro |
| `compartilhamento` | Ocultar compartilhamento de conexão | máquina | `...\Network Connections` `NC_ShowSharedAccessUI = 0` | apaga | Home |
| `wifidirect` | Bloquear Wi-Fi Direct | máquina | `...\WcmSvc\GroupPolicy` `fBlockWiFiDirect = 1` | apaga | Home |
| `ics` | Desativar ICS | máquina | `Services\SharedAccess` `Start = 4` | `Start = 3` (Manual) | — |
| `usb` | Armazenamento removível | conta e máquina | `Software\Policies\Microsoft\Windows\RemovableStorageDevices` `Deny_All = 1` | apaga | Home |

## Decisões de implementação

- **Toda leitura passa pelo trecho, não pelo `winreg`.** O serviço não importa `winreg` nem
  `ctypes`. A ACL (dono e regras) só é lida pelo .NET, e assim nada no processo Python abre o
  hive temporário.
- **Uma chamada de escrita por alvo.** Sai uma linha `OK|id` ou `ERRO|tipo|id` por política. A
  chamada roda sem o evento de cancelamento: o técnico cancela "depois deste passo".
- **O Python nunca vê o caminho do perfil.** O trecho `hive.ps1` lê `ProfileImagePath` (ou
  `ProfileList\Default`) e o confere sob `<raiz do Windows>\Users\`, sem `TEMP`. A raiz vem de
  `GetFolderPath('System')`, não de `%SystemDrive%`. Depois carrega com `reg.exe` pelo caminho
  da API, e a mensagem do `reg` é descartada.
- **Sobras de `ITCBench_*`.** São descarregadas no início de cada aplicação e de cada leitura de
  perfil fechado. A mesma chamada devolve o SID dono do processo, para a recusa "conta que roda
  o Bench".
- **PowerShell 5.1 e `ConvertFrom-Json`.** O cmdlet devolve o array como um objeto só, e os
  trechos desenrolam com `ForEach-Object`. O defeito apareceu na leitura real: sem o
  desenrolar, nenhuma chave era lida e tudo saía "não aplicada".
- **"O usuário pode alterar":** considera dono ou permissão de escrita (`SetValue`,
  `CreateSubKey`, `Delete`, `ChangePermissions`, `TakeOwnership`) para o SID, Todos, Usuários
  autenticados, Interativo e Usuários, e Administradores se a conta for admin. Em Contas futuras
  vale o mesmo, sem o SID.

## Verificação

App: 578 testes passando e 4 pulados; ruff e mypy limpos. A máquina de desenvolvimento (Windows 11
Pro em português) foi usada só para leitura. A única escrita foi o teste numa chave própria em
`HKCU\Software\ITCBenchTeste_<hex>`, apagada no fim:
- situação da máquina lida (todas "não aplicada");
- leitura do próprio hive: conta comum sem permissão nas chaves de política; com o grupo
  Administradores, 9 chaves alteráveis.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| S1 | Catálogo: ids únicos, raízes aceitas, sem wallpaper e sem "ocultar C:" | `test_catalogo_ids_unicos_e_raizes_aceitas`, `test_raiz_aceita` (8 casos), `test_sem_wallpaper_nem_unidade_c` | Passa |
| S2 | Desfazer: PowerShell (legado, lista vazia por último), ICS volta para Manual, escopos | `test_operacoes_powershell_aplicar_e_desfazer`, `test_ics_desfazer_volta_manual_e_escopo` | Passa |
| S3 | Situação: aplicada, não aplicada, diferente, ICS em 3, legado do Configurador | `test_estado`, `test_estado_powershell_legado` | Passa |
| S4 | Aviso de edição (Store no Pro, USB no Home, nada no Enterprise) | `test_aviso_edicao` | Passa |
| S5 | Recusas: nativo, Suporte, conta que roda o Bench, sem perfil, inexistente | `test_recusa_alvo`, `test_recusado_nao_escreve` | Passa; nada é escrito |
| S6 | Máquina, conta carregada e Contas futuras num lote; protegidos passados ao trecho | `test_aplicar_carregado_maquina_e_padrao` | Ordem sobras → listar → escrever → carregar → escrever → descarregar |
| S7 | Falha (exceção) no meio da escrita em perfil fechado | `test_falha_no_meio_descarrega` | Descarrega mesmo assim |
| S8 | Falha parcial por política | `test_falha_parcial_por_politica` | Resultado por política, descarrega |
| S9 | Cancelar durante a escrita | `test_cancelar_entre_alvos_sem_interromper_escrita` | O alvo atual termina e descarrega; o próximo fica "cancelado"; escrita sem evento de cancelamento |
| S10 | Descarregar falha | `test_descarregar_falha_vira_aviso` | 3 tentativas; aviso "reinicie" |
| S11 | Log sem SID, nome, caminho e hive temporário | `test_log_sem_sid_nome_nem_hive` | Passa |
| S12 | Leitura: perfil fechado só com "Ler"; com "Ler", carrega e descarrega | `test_ler_nao_carrega_sem_pedido`, `test_ler_descarregado_carrega_e_descarrega` | Passa |
| S13 | Python nunca abre o registro; trechos só em 64 bits; Python de 32 bits recusado | `test_servico_nao_abre_registro`, `test_trechos_em_64_bits`, `test_bits_recusa_32` | Passa |
| S14 | Sobras do Configurador: só os dois nomes exatos | `test_sobras_configurador` | Passa; outros arquivos ficam |
| R1 | PowerShell real: leitura da máquina | `test_ler_maquina_real` | Passa (edição e dono lidos) |
| R2 | PowerShell real: gravar, desfazer e raiz recusada, numa chave de teste | `test_escrever_real_em_chave_de_teste` | Passa; chave apagada |
| R3 | PowerShell real: hive com nome inválido e nativo recusados | `test_hive_recusa_nome_e_sid` | Passa |
| T1 | Telas: sem admin só leitura, situação com "pode alterar", confirmação com mudança e avisos, USB só com USB, sobras visíveis | `test_politicas_tela.py` (6 testes) | Passa |
| M1 | Nenhum `shell=True`, `cmd /c`, `.bat` ou `-ExecutionPolicy Bypass` no `src/` | `test_sem_shell.py` e busca no `src/` | Passa |
| V1 | Aplicar e desfazer política de máquina | Roteiro, passo 2 | **Pendente (máquina real, com o instalador)** |
| V2 | Política de conta no usuário logado, em outro com perfil carregado e em perfil fechado | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V3 | Perfil fechado: cancelar no meio e conferir que o hive foi descarregado | Roteiro, passo 4 | **Pendente (máquina real, com o instalador)** |
| V4 | Contas futuras: conta criada depois recebe e só lê (dono e ACL) | Roteiro, passo 5 | **Pendente (máquina real, com o instalador)** |
| V5 | Dono da chave: a conta comum não consegue apagar a política | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |
| V6 | Conta que roda o Bench recusada | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V7 | Sobras do Configurador e legado do `DisallowRun` | Roteiro, passo 7 | **Pendente (máquina real, com o instalador)** |
| V8 | USB: desabilitar e habilitar por conta e na máquina | Roteiro, passo 8 | **Pendente (máquina real, com o instalador)** |
| V9 | Windows Home e Pro (Store no Pro; políticas com aviso no Home) | Roteiro, passo 9 | **Pendente (máquina real, com o instalador)** |
| V10 | Windows em inglês | Roteiro, passo 10 | **Pendente (máquina real, com o instalador)** |
| V11 | `--dev` sem admin | Roteiro, passo 1 | **Pendente (máquina real, com o instalador)** |
| V12 | Log sem nome de usuário, SID, caminho de perfil nem dados de pendrive | Roteiro, passo 11 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

Nenhum além do teste em máquina real (sem API, NocoDB nem `.env`).

## Roteiro do teste em máquina real (V1–V12)

Notebook reserva com as contas comuns `Teste01` e `Teste02` e a conta Suporte.

1. Abra o Bench sem administrador (`--dev`): Políticas e USB mostram a situação da máquina e os
   botões ficam desabilitados (V11). Depois abra com administrador.
2. **Máquina:** marque Máquina e "Ocultar compartilhamento de conexão" e "Desativar ICS";
   aplique. A situação fica "aplicada". Depois de reiniciar, o serviço Compartilhamento de
   Conexão com a Internet fica Desativado. Desfaça: ele volta para Manual e o valor de política
   some (V1).
3. **Contas:**
   - Entre com `Teste01`, troque de usuário para a conta do técnico e aplique "Bloquear Editor
     do Registro" em `Teste01` (perfil carregado) e em `Teste02` (fechado).
   - Volte para cada uma: o regedit não abre.
   - Tente aplicar na conta que está rodando o Bench e na Suporte: recusado com o motivo (V2,
     V6).
4. **Cancelar com perfil fechado:** num lote com `Teste02` (fechado) e outra conta, clique em
   Cancelar durante o primeiro alvo. O primeiro termina e o segundo fica "cancelado". Num
   prompt de administrador, `reg query HKU` não mostra `ITCBench_*` (V3).
5. **Contas futuras:** aplique "Bloquear Prompt de Comando".
   - Crie `Teste03` e entre: o cmd não abre.
   - Em `regedit` como administrador, com o hive de `Teste03` carregado, a chave
     `Software\Policies\Microsoft\Windows\System` tem dono Administradores e Usuários só com
     leitura (V4).
6. **Dono da chave:** em `Teste01`, tente `reg delete` da política aplicada: acesso negado. Na
   tela, a situação não mostra "usuário pode alterar" para `Teste01` (V5).
7. **Sobras do Configurador:**
   - Se o notebook tiver o Configurador antigo, a tela mostra o script de logon e "Remover"
     apaga os dois arquivos.
   - Com o valor antigo `DisallowRun\1 = PowerShell.exe` numa conta, a situação de "Bloquear
     PowerShell" fica "diferente". Desfazer apaga o valor antigo e o `DisallowRun` (V7).
8. **USB:** "Desabilitar USB" em `Teste01`:
   - com um pendrive, `Teste01` não abre o disco e a Suporte abre;
   - "Habilitar USB" em `Teste01` libera.
   Depois "Desabilitar USB" em Máquina bloqueia também a Suporte; "Habilitar USB" libera (V8).
9. **Edição:** no Pro, confira se a Store bloqueia (o aviso aparece); num Home, confira cada
   política com aviso e anote no ADR-021 as que não têm efeito, para virarem cadeado (V9).
10. Se houver máquina em inglês, repita 2, 3 e 8 (V10).
11. No `bench.log`, procure `Teste01`, `S-1-5-21`, `C:\Users\`, `ITCBench_` e a letra ou o rótulo
    do pendrive: nenhum aparece (V12).

## Limites conhecidos

- **Bloqueio de PowerShell:** vale só pelo Explorer; uma cópia renomeada abre.
- **Efeito no Windows 11:** "Programas e Recursos" e Temas são parciais.
- **Edição:** "Efeito não confirmado" vale até o teste na máquina real.
- **ACL existente:** se uma chave já der escrita ao usuário, o Bench avisa e não troca a ACL.
- **Quando vale:** a política vale no próximo logon (sem `WM_SETTINGCHANGE`); o ICS, no próximo
  reinício.
- **Pendrive já espetado:** pode continuar aberto até ser removido.
- **Perfil preso:** se o hive não descarregar, o Bench avisa; reinicie antes de entrar na conta.
