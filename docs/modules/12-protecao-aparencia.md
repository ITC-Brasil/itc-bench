# Módulo 12 — Proteção do login e Aparência

**Branch:** `feat/modulo-12-protecao-aparencia` · **Data:** 2026-11-06 · **ADR:** ADR-022, TA-ADR-030

`app/` e `api/` (só a validação de `Tipo = papel`). O desenho foi proposto e aprovado em
`.conversa/` (Etapa 1).

**Respostas do responsável:**
- proteção pela combinação (ACL só de execução, detecção e flags em `.DEFAULT`);
- ações de incidente com confirmação dupla;
- papel de parede pelo cadastro (`Tipo = papel`);
- tela de bloqueio, tampa, botão de energia e resolução/escala fora;
- sem `-restoredefaultschemes` e sem troca para Alto desempenho.

**Ajustes incorporados:**
- assinatura por `IsOSBinary` e "não lida" quando a verificação não roda;
- IFEO com `UseFilter`;
- "não protegido" depois de atualização exposto para o Início;
- `Policies\System` com lista por valor;
- preferência só herda a ACL, em tipo nativo;
- energia lida pelo `powercfg /query` (só os números);
- hibernação com a situação na confirmação;
- ACL da pasta conferida e `limpar` sem apagar a imagem ativa;
- `papel` ignorado pelos outros consumidores de Instaladores;
- `dado = None` só do serviço do papel de parede.

## O que entrou

| Item | Onde |
|---|---|
| Hive comum (alvos, carregar/ler/escrever/descarregar, laço por alvo), sem mudar o 11 | `app/src/itc_bench/servicos/hive.py`; `politicas.py` passa a usar |
| Perfil `aparencia` nos trechos: chaves exatas, valores `Wallpaper`/`WallpaperStyle`, caminho da imagem conferido, ACL só sob raiz de política, `REG_EXPAND_SZ` | `recursos/politicas/{comum,escrever}.ps1` |
| Proteção do login: detecção, proteger/desproteger, atalho na tela de login, incidente | `servicos/protecao.py`, `recursos/protecao/{ler,escrever}.ps1` |
| Papel de parede: cadastro, download/cópia com SHA-256, imagem conferida, pasta com ACL, política por alvo | `servicos/papel_de_parede.py`; `instaladores.py` (`papeis()`, `limpar`, versão), `programas.py` (ignora `papel`) |
| Mouse e teclado: catálogo fechado por alvo | `servicos/aparencia.py` |
| Energia: `powercfg` com aliases, leitura numérica, padrão do esquema, hibernação | `servicos/energia.py`, `recursos/energia/ler.ps1` |
| Telas com ajuda | `ui/protecao.py`, `ui/aparencia.py`, `ui/janela.py` |
| API: `Tipo = papel` validado | `api/app/services/nocodb_cadastros.py` |

## Decisões de implementação

- **`OriginalFilename` não é o nome do arquivo.** A leitura real no Windows 11 deu
  `utilman2.exe`, `ScreenMagnifier.exe` e `SR.exe` para `utilman`, `Magnify` e `Narrator`. A
  lista aceita por exe ficou no trecho, e o ADR-022 registra a tabela.
- **`$FLAGS` e `$flags` são a mesma variável no PowerShell.** O defeito apareceu na leitura
  real: o JSON das flags saía com a chave `System.Collections.Hashtable`. A variável foi
  renomeada.
- **Raiz do perfil `aparencia`:** a primeira versão só passou nos testes falsos e no teste real
  do papel, porque `Policies\System` também é raiz de política. O teste real de Mouse
  (`ERRO|raiz`) mostrou que o ramo `aparencia` não tinha entrado no `comum.ps1`.
- **Proteger em três chamadas** do executor (`takeown`, `icacls /deny`, `icacls /setowner`). O
  `setowner` fica num `finally`, então o arquivo nunca fica com dono Administradores, nem com
  falha no meio. Cancelar vale entre arquivos.
- **Papel de parede sem SPI:** a política vale no próximo logon. A máquina nunca é alvo.
- **Energia:** escrita direto no `powercfg.exe` (sem PowerShell); a leitura é por trecho, para
  juntar `powercfg /query` com o padrão do registro numa chamada. `HibernateEnabled` ausente cai
  para `HibernateEnabledDefault`.

## Verificação

App: 641 testes passando e 4 pulados; ruff e mypy limpos. API: 242 testes no container.

A máquina de desenvolvimento (Windows 11 Pro em português) foi usada só para leitura:
- proteção: os 7 binários deram "original", "não protegido", "sem depurador" e atalho padrão;
- energia: esquema Equilibrado com os valores AC/DC e os padrões lidos.

As únicas escritas foram em chaves de teste `HKCU\Software\ITCBenchTeste_<hex>`, apagadas no fim.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| S1 | Extração do hive sem mudar o 11 | suíte do 11 inteira sem mudança de teste | Passa |
| S2 | Proteger: três passos fixos, por caminho absoluto, SID do SYSTEM e do TrustedInstaller | `test_proteger_tres_passos_fixos`, `test_desproteger_remove_so_a_negacao` | Passa |
| S3 | Dono volta ao TrustedInstaller com falha no `icacls` ou no `takeown` | `test_dono_volta_mesmo_com_falha_no_meio`, `test_dono_volta_mesmo_com_falha_no_takeown` | Passa |
| S4 | Proteger recusa arquivo trocado ou não lido; só utilman/sethc | `test_proteger_recusa_arquivo_trocado_ou_nao_lido`, `test_so_utilman_e_sethc` | Passa; nada roda |
| S5 | Cancelar entre arquivos | `test_cancelar_entre_arquivos` | O primeiro termina, o segundo fica cancelado |
| S6 | Situação e alertas (IFEO, dono alterado, não protegido) e atalho | `test_situacao_e_alertas`, `test_atalho` (4 casos) | Passa |
| S7 | Restaurar decide pela nova detecção | `test_restaurar_decide_pela_deteccao` | Passa |
| S8 | Trechos da proteção: leitura sem escrita; remover só `Debugger`/`MonitorProcess`; 64 bits | `test_trechos_fixos` | Passa |
| S9 | Papel: dimensões e assinatura de bytes (PNG, JPEG, extensão trocada, GIF) | `test_dimensoes` (6 casos) | Passa |
| S10 | Papel: download, hash diferente, imagem pequena apagada, "Escolher arquivo…" conferido contra o cadastro, extensão | `test_obter_*`, `test_escolher_arquivo_confere_contra_o_cadastro`, `test_extensao_recusada` | Passa |
| S11 | Papel: operações fechadas, imagem fora da pasta e estilo fora da lista recusados | `test_operacoes_aplicar_e_desfazer` | Passa |
| S12 | Papel por alvo: máquina fora, Suporte e conta do Bench recusadas, perfil fechado carrega e descarrega, log sem caminho/SID/hive | `test_aplicar_por_alvo_sem_caminho_no_log` | Passa |
| S13 | `papel` fora de Programas, Acesso remoto e `do_cadastro`; `limpar` cobre a pasta | `test_listar_tira_acesso_remoto_e_marca_duplicados`, `test_do_cadastro_ignora_winget_e_webapp_com_o_mesmo_nome`, `test_limpar_sem_base_trata_instaladores_icones_e_papel` | Passa |
| S14 | Mouse: catálogo dentro das chaves aceitas, igual ao trecho, tipos nativos, fora da lista recusado | `test_catalogo_*`, `test_chaves_iguais_ao_trecho`, `test_tipos_nativos`, `test_operacoes_recusam_fora_da_lista` | Passa |
| S15 | Mouse: situação (ausente = padrão, ajustado, diferente) e desfazer = padrão | `test_estado`, `test_aplicar_e_desfazer_por_alvo` | Passa |
| S16 | Energia: aliases, lista fechada, falha parcial, cancelar, desfazer pelo padrão, sem `restoredefaultschemes`, hibernação | `test_energia.py` | Passa |
| S17 | Telas: sem admin só leitura; "não protegido" visível; confirmação com de → para; hibernação atual e Inicialização rápida | `test_aparencia_tela.py` (7 testes) | Passa |
| R1 | PowerShell real: detecção da proteção | `test_situacao_real` (proteção) | Passa |
| R2 | PowerShell real: perfil `aparencia` recusa outro valor em `Policies\System`, caminho fora, estilo fora e raiz fora | `test_trecho_aparencia_recusa_valor_e_caminho_fora` | Passa; chave apagada |
| R3 | PowerShell real: preferência criada só herda ACL; `REG_SZ`, `REG_EXPAND_SZ` e `REG_DWORD` | `test_preferencia_herda_acl_e_tipo_nativo` | Passa; chave apagada |
| R4 | PowerShell real: energia lida | `test_situacao_real` (energia) | Passa |
| M1 | Nenhum `shell=True`, `cmd /c`, `.bat` ou `-ExecutionPolicy Bypass` no `src/` | `test_sem_shell.py` e busca no `src/` | Passa |
| V1 | Proteger e desproteger utilman/sethc: dono e ACL de volta, acessibilidade depois | Roteiro, passo 2 | **Pendente (máquina real, com o instalador)** |
| V2 | Win+U, botão de Acessibilidade e Shift 5x na tela de login | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V3 | `sfc /verifyonly` depois de proteger | Roteiro, passo 4 | **Pendente (máquina real, com o instalador)** |
| V4 | Binário trocado e IFEO `Debugger` (com e sem `UseFilter`) detectados, removidos e restaurados | Roteiro, passo 5 | **Pendente (máquina real, com o instalador)** |
| V5 | Papel de parede no logado, em perfil fechado e em Contas futuras; usuário comum não troca a imagem | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |
| V6 | Mouse e teclado por alvo; desfazer | Roteiro, passo 7 | **Pendente (máquina real, com o instalador)** |
| V7 | Energia AC/DC, hibernação, desfazer | Roteiro, passo 8 | **Pendente (máquina real, com o instalador)** |
| V8 | Windows Home e Pro | Roteiro, passo 9 | **Pendente (máquina real, com o instalador)** |
| V9 | Windows em inglês | Roteiro, passo 10 | **Pendente (máquina real, com o instalador)** |
| V10 | `--dev` sem admin | Roteiro, passo 1 | **Pendente (máquina real, com o instalador)** |
| V11 | Log sem nome de usuário, SID, caminho de perfil nem caminho da imagem | Roteiro, passo 11 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

1. NocoDB, tabela Instaladores: acrescentar a opção `papel` no SingleSelect `Tipo`.
2. Cadastrar a linha do papel de parede: `Programa`, `Arquivo` (`.jpg`/`.png`), `SHA256` e `Link`
   `https://` do arquivo, `Ativo`. A imagem do Configurador não entra no repositório.
3. Deploy da API (`api-deploy.yml`) antes de instalar o app novo. Sem `.env` novo.

## Roteiro do teste em máquina real (V1–V11)

Notebook reserva com as contas comuns `Teste01` e `Teste02` e a conta Suporte.

1. Abra o Bench sem administrador (`--dev`): as quatro telas mostram a situação e os botões
   ficam desabilitados (V10). Depois abra com administrador.
2. **Proteger:**
   - Antes, num prompt de administrador, guarde `icacls C:\Windows\System32\utilman.exe` e o
     mesmo do `sethc.exe`.
   - Clique em Proteger: os dois ficam "protegido".
   - `icacls` mostra a linha nova `NT AUTHORITY\SYSTEM:(DENY)(X)` e o resto igual; o dono
     (`Get-Acl`) continua `NT SERVICE\TrustedInstaller`.
   - Desproteger: `icacls` igual ao guardado (V1).
3. **Tela de login:** protegido e com "Desligar atalho", bloqueie a sessão (Win+L). O botão de
   Acessibilidade, Win+U e Shift 5x não abrem nada. Desproteja e "Ligar atalho": voltam a abrir.
   Dentro da conta, o Narrador abre nos dois casos (V2).
4. **`sfc`:** protegido, rode `sfc /verifyonly` num prompt de administrador. Anote se acusa os
   dois arquivos. Depois de uma atualização cumulativa, a tela mostra "não protegido" (V3).
5. **Incidente** (só no notebook reserva):
   - Crie `HKLM\...\Image File Execution Options\osk.exe\Debugger = cmd.exe`: a tela mostra
     "DEPURADOR". "Remover depurador" apaga, e a chave `osk.exe` fica.
   - Repita com uma subchave com `UseFilter = 1`, `FilterFullPath` e `Debugger`.
   - Copie `cmd.exe` sobre o `sethc.exe` (com `takeown`): a tela mostra "TROCADO" e Proteger
     recusa. "Restaurar original" traz o original, e Proteger volta a funcionar (V4).
6. **Papel de parede:** com a linha `papel` cadastrada, aplique em `Teste01` (logada, outra
   sessão), em `Teste02` (fechada) e em Contas futuras.
   - Entre em cada uma: o papel de parede é o do Grupo e Configurações › Personalização não deixa
     trocar.
   - Em `Teste01`, tente gravar em `C:\ProgramData\ITC\Bench\papel\`: acesso negado.
   - Crie `Teste03`: recebe o papel de parede.
   - Desfazer: cada conta volta ao papel dela.
   - Sem rede, use "Escolher arquivo…" com a imagem num pendrive; com outra imagem, recusa (V5).
7. **Mouse e teclado:**
   - Em `Teste02` (fechada), aplique ponteiro preto grande, velocidade 15 e botões invertidos;
     entre nela e confira.
   - Ela consegue mudar a velocidade nas Configurações (preferência, não política).
   - Desfazer volta ao padrão (V6).
8. **Energia:**
   - Tela "Nunca" na tomada e 5 min na bateria; confira em Configurações › Energia.
   - Desfazer volta ao padrão do plano.
   - Desligar hibernação: `powercfg /a` diz que a hibernação está desligada. Ligar a traz de
     volta (V7).
9. **Edição:** repita 2, 6 e 8 num Windows Home (V8).
10. Se houver máquina em inglês, repita 2, 6 e 8 (V9).
11. No `bench.log`, procure `Teste01`, `S-1-5-21`, `C:\Users\`, `ITCBench_` e `\papel\`: nenhum
    aparece (V11).

## Limites conhecidos

- **Proteção:**
  - não resiste a apagar/renomear o arquivo nem a IFEO gravado offline, e some com atualização
    que troca o binário (a detecção mostra);
  - a defesa contra boot por pendrive é BitLocker + senha de BIOS.
- **"Restaurar original"** depende do WinSxS; se ele também foi trocado offline, o `sfc` não
  resolve.
- **Papel de parede e mouse** valem no próximo logon (sem SPI).
- **Energia:** padrão do plano não encontrado → o Bench não mexe naquele ajuste.
- **Resolução e escala** ficam com o Windows.
