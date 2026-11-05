# Módulo 08 — Identificação e Wi-Fi

**Branch:** `feat/modulo-08-identificacao-wifi` · **Data:** 2026-11-05 · **ADR:** ADR-018

Só `app/`; a API não muda. Desenho proposto e aprovado em `.conversa/` (Etapa 1). Respostas do
responsável: senha vazia no cadastro é erro (todas as redes têm senha); WPA3 fica fora (os
notebooks não suportam); renomear por `Rename-Computer` pelo executor. Decisões anteriores: o
técnico digita o nome inteiro (sem padrão nem sugestão); `Unidades.Codigo` = `<SIGLA><nn>`;
contas por turno vão para o 13.

## O que entrou

| Item | Onde |
|---|---|
| Trechos PowerShell: estado (nome ativo e pendente, domínio/Azure AD, nomes locais) e renomear | `app/src/itc_bench/recursos/identificacao/*.ps1` |
| Validação NetBIOS, leitura do estado, renomear, reiniciar | `app/src/itc_bench/servicos/identificacao.py` |
| `wlanapi.dll` por ctypes: interfaces, perfis, ler perfil (com chave só com admin), gravar, conectar, conexão atual | `app/src/itc_bench/nucleo/wlan.py` |
| Validação da senha, XML do perfil, situação, instalar com cancelamento, testar conexão | `app/src/itc_bench/servicos/wifi.py` |
| Telas Identificação e Wi-Fi com ajuda | `app/src/itc_bench/ui/identificacao.py`, `ui/wifi.py`, `ui/janela.py` |
| Testes | `app/tests/test_identificacao.py`, `test_wifi.py`, `test_preparar_tela.py` |

## Decisões de implementação

- **Wi-Fi sem processo.** Nada do Wi-Fi passa pelo executor: o XML vai da memória do Bench ao
  serviço WLAN. Um teste de AST garante que `servicos/wifi.py` e `nucleo/wlan.py` não importam
  executor, `subprocess` ou `tempfile`, nem abrem ou gravam arquivo.
- **Interfaces.** A instalação grava o perfil em todas as interfaces Wi-Fi; a situação e o teste
  usam a primeira (os notebooks têm uma).
- **Comparação.** O perfil instalado é igual quando é `WPA2PSK` e a chave lida em claro (só com
  administrador) bate com a do cadastro (`hmac.compare_digest`). Perfil com outra segurança, chave
  cifrada ou XML ilegível conta como diferente; sem administrador, "senha não conferida".
- **Marcação padrão.** A tela marca as redes "Não instaladas" e "Senha ou segurança diferente";
  cadastro inválido não pode ser marcado.
- **Nome do perfil = SSID.** Uma rede instalada à mão com o mesmo nome é substituída pela do
  cadastro (a confirmação avisa).
- **Testar conexão** recebe a checagem da API da janela (`api.saude`); sem rede até a API, devolve
  "conectado, mas sem acesso à API".
- **Erros do Windows na tela como texto puro** (`QMessageBox` com `PlainText`).

## Verificação

App: testes completos (ver `PROGRESS.md`), ruff e mypy limpos, `itc-bench --teste --dev` com
código 0. Máquina de desenvolvimento (Windows 11) só para leitura: estado do nome pelo PowerShell
real e perfis pela `wlanapi` real (1 interface). Nada foi renomeado nem instalado nela.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| N1 | Nome válido (1 a 15, letras, números, hífen) | `test_validar` (17 casos) | Aceito; minúsculas viram maiúsculas |
| N2 | Nome inválido: 16+, hífen na ponta, `_`, acento, espaço, ponto, aspas, só dígitos | `test_validar` | Recusado com a mensagem certa |
| N3 | Nome reservado e igual a conta/grupo local | `test_validar` (`SYSTEM`, `LOCALHOST`, `TESTE01`) | Recusado |
| N4 | Igual ao nome atual / ao pendente | `test_validar`, `test_pendente_e_dominio` | "Esse já é o nome" / "já vai ter esse nome depois de reiniciar" |
| N5 | Domínio ou Azure AD | `test_pendente_e_dominio`, `test_renomear_recusa_antes_do_powershell`; `renomear.ps1` confere de novo | Recusado sem chamar o `Rename-Computer` |
| N6 | Nome só por `ITC_NOME` | `test_renomear_nome_so_pelo_ambiente` | Nome fora do texto do script; log "antigo -> novo" |
| N7 | Erro do Windows | `test_renomear_erro_do_windows_na_tela_codigo_no_log` | Mensagem na tela, só o código no log |
| N8 | Reiniciar com argumentos fixos | `test_reiniciar_argumentos_fixos` | `System32\shutdown.exe /r /t 10` |
| N9 | Estado real (leitura) | `test_estado_real` | Nome ativo lido; sem pendente; fora de domínio |
| N10 | Tela: botões, pendente na tela, `--dev` sem admin | `test_identificacao_*` | Renomear só com nome válido; "Depois de reiniciar: …"; sem admin, nada habilitado |
| W1 | Senha: 8–63 comuns, 64 hex, vazia, curta, 64 não hex, acento; SSID vazio ou > 32 bytes | `test_validar` (10 casos) | Só os válidos passam; vazia é cadastro inválido |
| W2 | SSID com acento e `& < " >`, senha com `]]> < & ' "` | `test_xml_escapa_ssid_e_senha_e_usa_hex` | XML válido; SSID em `hex` UTF-8; senha íntegra |
| W3 | Chave de 64 hex | `test_xml_chave_hex` | `networkKey` |
| W4 | Situação: igual, senha diferente, ausente, inválida, sem admin | `test_situacao`, `test_situacao_chave_cifrada_ou_outra_seguranca_e_diferente` | Classificação certa; WPA3 ou chave cifrada = diferente |
| W5 | Filtro por unidade | `test_filtro_por_unidade`, `test_wifi_marca_ausentes_e_filtra_unidade` | Esta unidade / Todas / Instaladas no Windows |
| W6 | Instalar várias, uma falha, uma inválida, duas interfaces | `test_instalar_varias_interfaces_falha_e_invalida` | 1 instalada (nas 2 interfaces), 1 falha com código, 1 pulada |
| W7 | Já instalada igual | `test_ja_instalada_igual_fica_igual` | Sobrescreve sem erro; continua igual |
| W8 | Cancelar no meio | `test_instalar_cancela_entre_redes` | A rede em curso termina; as seguintes ficam canceladas |
| W9 | Testar conexão: conecta, sem API, não conecta, cancelado | `test_testar_*` | Mensagens certas; espera de 20 s |
| W10 | Sem adaptador / sem cadastro / `--dev` sem admin | `test_sem_adaptador`, `test_wifi_sem_*` | Aviso na tela; ações desabilitadas; "Abrir redes do Windows" disponível |
| W11 | Leitura real pela `wlanapi` | `test_leitura_real` | Interfaces e perfis listados (sem idioma, sem processo) |
| M1 | SSID e senha fora do log | `test_instalar_varias_interfaces_falha_e_invalida` | Log só com `Id`, contagens e código |
| M2 | Wi-Fi sem processo, sem arquivo, sem `tempfile` | `test_wifi_nao_abre_processo_nem_grava_arquivo` | Passa |
| M3 | Sem `shell=True` ou `subprocess` fora do executor; sem `netsh` no `src/` | `test_sem_shell.py`, busca no `src/` | Passa; nenhum `netsh` |
| V1 | Renomear e reiniciar depois (nome pendente na tela); voltar ao nome original | Tela (roteiro) | **Pendente (máquina real, com o instalador)** |
| V2 | Renomear e reiniciar agora; diagnóstico e login offline depois do reinício | Tela (roteiro) | **Pendente (máquina real, com o instalador)** |
| V3 | Instalar uma e várias redes de teste; já instalada; senha diferente | Tela (roteiro) | **Pendente (máquina real, com o instalador)** |
| V4 | SSID com acento e caractere especial; conectar de verdade | Roteador de teste | **Pendente (máquina real, com o instalador)** |
| V5 | Cancelar no meio de várias | Tela | **Pendente (máquina real, com o instalador)** |
| V6 | Sem cache de cadastros (máquina nova) | Tela antes do primeiro login | **Pendente (máquina real, com o instalador)** |
| V7 | Windows em inglês | Máquina em inglês, se houver | **Pendente (máquina real, com o instalador)** |
| V8 | Senha de Wi-Fi fora do `bench.log`, de `Win32_Process` e de `%TEMP%`/`protegido\` depois de instalar | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

1. NocoDB, base "ITC Bench": preencher `Unidades` com `Codigo` no formato `<SIGLA><nn>` (só
   maiúsculas e dígitos, até 8) e usar os mesmos códigos em `WiFi.Unidade`. Conferir que toda rede
   tem senha WPA2 de 8 a 63 caracteres comuns.
2. V1–V8 numa máquina real com o instalador (roteiro abaixo).

## Roteiro do teste em máquina real (V1–V8)

1. Use um notebook reserva. **Anote o nome original do computador** antes de tudo. Instale o
   Bench e, antes do login, abra Wi-Fi: deve aparecer "Sem cadastros" e "Abrir redes do Windows"
   (V6).
2. Entre online e sincronize. Em Identificação, renomeie para um nome de teste (ex.: `TESTE-08`),
   escolha "Depois": a tela mostra "Depois de reiniciar: TESTE-08" (V1). Reinicie, confira o nome,
   abra o Bench offline (login offline) e o diagnóstico (V2).
3. Cadastre no NocoDB duas ou três redes **de teste** (um roteador de bancada, nunca as redes das
   unidades), uma com acento e `&` no nome. Sincronize e instale uma, depois as outras (V3, V4).
   Instale de novo: "Instalada (igual)". Troque a senha de uma no NocoDB, sincronize: "Senha ou
   segurança diferente"; instale e teste a conexão.
4. Instale as três e cancele depois da primeira (V5).
5. Se houver máquina em inglês, repita 3 (V7).
6. Durante a instalação, `Get-CimInstance Win32_Process | Select CommandLine` não mostra a senha;
   depois, procure a senha de teste no `bench.log`, em `%TEMP%` e em
   `%ProgramData%\ITC\Bench\protegido\` (não pode aparecer em texto) (V8).
7. Ao terminar, apague as redes de teste do Windows e volte ao nome original pela tela.

Sem `.env`, deploy ou mudança na API.

## Limites conhecidos

- Só WPA2-Personal (decisão do responsável); WPA3-only e redes abertas não são instaladas.
- A senha fica na memória do processo do Bench durante a chamada (como qualquer `Sensivel`).
- O histórico do diagnóstico passa ao nome novo depois do reinício; o do nome antigo fica na API.
- Reinício com retomada e contas por turno ficam para o 13; remover o Windows Terminal, para o 10.
