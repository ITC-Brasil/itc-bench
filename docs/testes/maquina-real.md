# Roteiro de máquina real — ITC Bench

Roteiro único dos cenários que alteram a máquina (Módulos 01 e 04 a 16). Executado **depois do
Módulo 15** (instalador) e **antes da primeira release com instalador** (decisão do responsável no
Módulo 14). Situação de todos os passos: **Pendente (máquina real, com o instalador)**.

Cada passo cita o cenário de origem (`MM/Vn`, `MM/Cn` ou `MM/Dn`) do `docs/modules/MM-*.md`. O
resultado de cada passo volta para a tabela de verificação do doc de origem e para o doc do 15.

## Antes de começar

- **Máquina:** notebook reserva, Windows 11 Pro pt-BR instalado do zero, sem domínio nem Azure AD,
  sem conta Microsoft. Uma conta local administradora para o técnico (`Bancada`). Rodada opcional
  num Windows Home e num Windows em inglês (passo 12).
- **Contas de teste:** `Teste01` e `Teste02`, criadas pelo próprio Bench no passo 5.
- **Cadastros:** unidade de teste no NocoDB, com linhas de teste em Servidores (Conta Suporte,
  GLPI Agent, RustDesk, AnyDesk), Instaladores (um MSI, um EXE com silencioso, um winget, um Web
  App, um papel de parede) e Wi-Fi (SSID de um roteador de teste, um com acento). Nada de
  instalador ou rede real de carreta.
- **API:** deploy de `develop` feito (`docs/api/DEPLOY.md`), borda conferida.
- **Bypass do Bench (antes do passo 0):** `curl.exe -s -D - -o NUL https://<endereço da API>/v1/bench/sessao`
  responde `401` com `www-authenticate: Bearer` e sem `Cf-Access-*`. `403` com `Cf-Access-*` = Bypass ausente
  (o login falha); `502`/`530` = túnel ou container fora (`docs/api/DEPLOY.md`). No PowerShell 5.1,
  `curl` é apelido do `Invoke-WebRequest`: use `curl.exe`.
- **Instalador** do Módulo 15, baixado do artefato do `app-build` ou da Release (nunca de build
  local, `docs/BUILD.md`), com o SHA-256 conferido contra o `SHA256SUMS`.
- **Marcadores:** antes de começar, anote fora do repositório as senhas de teste usadas
  (Suporte, Wi-Fi, RustDesk, AnyDesk, `Teste01`). As buscas do passo 11 procuram por elas.

## O que registrar

Para cada passo: data, versão do Bench, resultado (passou/falhou), código de saída ou situação
mostrada na tela, e as linhas do `bench.log` que provam o resultado. Na evidência gravada no
repositório, troque nome de máquina, nomes de conta, SIDs, SSIDs, hosts e caminhos de perfil por
placeholders (`<computador>`, `<conta-1>`, `S-1-5-21-…-1002`, `<ssid>`, `*.exemplo.invalid`,
`C:\Users\<conta>`), como manda o ADR-009. Print de tela só sem esses dados.

## Passos

### 0. Instalador (Módulo 15)

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 0.1 | Baixar o instalador pelo navegador e abrir | SmartScreen avisa (sem assinatura, ADR-025); "Mais informações" → "Executar assim mesmo". UAC com "Editor desconhecido". Registrar o texto das duas telas | 15 |
| 0.1a | Numa máquina sem o Bench, rodar o instalador da Release sem parâmetro (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`, administrador) | Instala; `reg query HKLM\SOFTWARE\ITC\Bench /v ApiUrl` mostra o endereço embutido; login online funciona (ADR-027). Desinstalar antes do 0.2 | 27 |
| 0.2 | No assistente, informar `http://...`, depois `https://u:s@...` | Mensagem de endereço inválido; não avança | 15 |
| 0.3 | Informar o endereço real `https://` e concluir | Instala em `C:\Program Files\ITC\Bench`; atalho só no Menu Iniciar; `reg query HKLM\SOFTWARE\ITC\Bench /v ApiUrl` mostra o endereço | 15 |
| 0.4 | `icacls "C:\Program Files\ITC\Bench"` e `...\ITC` | Escrita só para SYSTEM, Administradores, TrustedInstaller e CREATOR OWNER (herdado); Usuários só leitura e execução | 15 |
| 0.5 | Propriedades do `ITC Bench.exe` → Detalhes; Configurações → Aplicativos | Versão do produto = versão do instalador; "ITC Bench" com a mesma versão e editor Grupo ITC Brasil | 15 |
| 0.6 | Com o Bench aberto, rodar o instalador de novo (assistente) | Pede para fechar o ITC Bench; não fecha sozinho | 15 |
| 0.7 | Fechar o Bench e rodar o instalador por cima, numa máquina já preparada (depois do passo 3) | Atualiza sem perguntar de novo o que já está gravado (página vem com o endereço atual); `protegido\`, login offline e cadastros continuam; preparação intacta | 15 |
| 0.8 | Copiar `ITC Bench.exe` e `_internal` para `C:	empench` e abrir elevado | "A pasta de instalação foi alterada. Reinstale o ITC Bench."; sai sem mexer na máquina; log com "Pasta de instalação recusada" | 15 |
| 0.9 | No fim do roteiro: desinstalar pelo Configurações | Aviso de que a preparação não é desfeita; somem a pasta, o atalho e `HKLM\SOFTWARE\ITC\Bench`; `protegido\` some; ficam `logs\`, `papel\`, `icones\`; papel de parede e atalhos de Web App continuam funcionando | 15 |

### 1. Instalação, elevação e `--dev`

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 1.1 | Instalar pelo instalador; abrir pelo atalho numa sessão sem elevação | Pedido do UAC; recusar mostra a mensagem e sai com 1; aceitar abre o Bench | 01/7 |
| 1.2 | `icacls "%ProgramData%\ITC\Bench"` e `...\protegido` | SDDL do ADR-011; `protegido\` só SYSTEM e Administradores | 02, 04/C1 |
| 1.3 | Abrir com `--dev` sem elevação: Contas, Wi-Fi, Remoto, Programas, Políticas, USB, Proteção, Aparência, Preparação, Limpeza | Telas leem; botões de ação desativados com "Precisa de administrador." | 09/V11, 10/V9, 11/V11, 12/V10, 13/V11 |
| 1.4 | Abrir com `--dev` **de um terminal elevado** | Mesma coisa que 1.3: só leitura; log com `admin=False` | 14 |
| 1.5 | Variável de usuário `PROGRAMDATA` apontando para uma pasta de teste (`setx PROGRAMDATA C:\temp\pd`, nova sessão), abrir o Bench elevado | Log e pastas continuam em `C:\ProgramData\ITC\Bench`; nada criado na pasta de teste. Apagar a variável depois | 14 |

### 2. Login e cadastros

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 2.1 | Primeiro login com técnico com perfil no GLPI; um sem o perfil | Entra; o outro recebe "fora do perfil" | 04/D3 |
| 2.2 | Antes do primeiro login, abrir Wi-Fi | Aviso de cadastros ausentes, nada instalado | 08/V6 |
| 2.3 | Configurações depois do login | Cadastros de teste; segredos mascarados | 05/D2 |
| 2.4 | Desligar a rede, fechar e abrir o Bench | Login offline do mesmo técnico; cadastros do cache | 04, 07/V7 |
| 2.5 | Na conta `Teste01` (depois do passo 5): `type` e `dir` em `protegido\` | Acesso negado | 04/C4, 05/C3 |

### 3. Preparação completa do zero

Perfil `sala_de_aula` (pré-selecionado pelo `Unidades.PerfilPadrao` da unidade de teste), contas
`Teste01` e `Teste02` marcadas como alunos (criar antes, passo 5.1, se ainda não existirem).

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 3.1 | Rodar o perfil completo, com a rede ligada | Cada etapa lida antes de aplicar; ao fim, todas "feito" (Contas "pendente" se o RID 500 estiver ativo, sem bloquear as dependentes) | 13/V1 |
| 3.2 | Rodar o mesmo perfil de novo | Nada refeito; todas "feito" na leitura | 13/V2 |
| 3.3 | Tirar a rede no meio de Programas | Programas "falhou"; as independentes seguem; dependentes de Contas não são afetadas | 13/V3 |
| 3.4 | Pausar e cancelar | Pausa depois da etapa corrente; cancelar não deixa hive carregado nem serviço parado | 13/V4 |
| 3.5 | Renomear pela Preparação e reiniciar; reabrir com e sem rede, com sessão vencida e offline | Retomada pede login; `preparacao.json` com ACL; no máximo 2 reinícios; arquivo de mais de 24 h ignorado | 13/V5, 08/V2, 08/V9 |
| 3.6 | Início depois da preparação | Máquina, alertas e selos coerentes com o que foi feito | 13/V7 |

### 4. Diagnóstico

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 4.1 | Coleta elevada com laudo pela borda | Laudo na tela; tempo anotado | 06/D3 |
| 4.2 | Coletar, desligar a rede antes do envio, religar | Reenvio pela fila; uma linha no SQLite (`envio_id`) | 06/D4 |

### 5. Contas

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 5.1 | Criar `Teste01` (padrão, com senha, não expira) e `Teste02` (admin, sem senha) | Criadas; grupo por SID | 07/V1 |
| 5.2 | Tornar admin/padrão, trocar e remover senha | Feito; lista lida de novo | 07/V2 |
| 5.3 | Tentar alterar o nativo, a conta logada, a Suporte e o último admin | Recusas com a mensagem do ADR-017 | 07/V3 |
| 5.4 | Excluir com e sem perfil e com perfil carregado (`Teste01` logada em outra sessão) | Recusa com sessão aberta; exclusão sem deixar perfil órfão | 07/V4 |
| 5.5 | Clonar grupos de uma conta em "Usuários da área de trabalho remota" | Grupos iguais | 07/V5 |
| 5.6 | Conta Suporte com e sem rede | Criada com a senha do cadastro; sem rede, do cache | 07/V7 |
| 5.7 | Durante criar e trocar senha, `Get-CimInstance Win32_Process` em loop | Senha nunca na linha de comando | 07/V8 |

### 6. Identificação e Wi-Fi

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 6.1 | Renomear e reiniciar depois; voltar ao nome original | Nome pendente na tela | 08/V1 |
| 6.2 | Instalar uma e várias redes; já instalada; senha diferente | Situações certas por rede | 08/V3 |
| 6.3 | SSID com acento e caractere especial | O Windows conecta sozinho | 08/V4 |
| 6.4 | Cancelar no meio de várias | Para entre redes | 08/V5 |

### 7. Acesso remoto

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 7.1 | GLPI Agent do zero; "Forçar inventário" | Servidor e tag no registro; inventário no GLPI | 09/V1 |
| 7.2 | RustDesk do zero (máquina lenta se houver) | ID na tela; conexão com a senha do cadastro; `RustDesk.toml` sem `.tmp` | 09/V2, 09/V8 |
| 7.3 | AnyDesk do zero | ID na tela; acesso sem supervisão | 09/V3 |
| 7.4 | Mesma versão (Reconfigurar) e versão mais velha (Atualizar) | Não rebaixa | 09/V4 |
| 7.5 | SHA-256 errado; sem rede com "Escolher arquivo…"; linha de Servidores vazia | Recusa antes de executar; mensagem do cadastro | 09/V5, 09/V6 |
| 7.6 | Cancelar no download e no MSI | Arquivo parcial apagado; MSI não morto | 09/V7 |
| 7.7 | RustDesk com `SHA256` vazio no cadastro; depois troque a `Versao` e sincronize. Papel de parede com `SHA256` vazio: aplicar numa conta não aberta (ex.: RESERVA-06) e entrar nela | Instala; confirmação com "SHA-256: não cadastrado"; `bench.log` com "sem SHA-256 cadastrado" e o começo do hash; a versão nova baixa de novo e o arquivo antigo some de `protegido\instaladores`; o papel fica "Aplicado", sem "Falhou (valor)", e aparece no logon da conta | ADR-028 |
| 7.8 | `SHA256` preenchido com um hash que não é o do arquivo | Recusa antes de executar, como em 7.5 | ADR-028 |

### 8. Programas

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 8.1 | MSI e EXE do zero; mesma versão; versão mais velha | Instala; não reinstala; não rebaixa | 10/V1 |
| 8.2 | SHA-256 errado; sem rede com e sem arquivo guardado | Recusa; usa o guardado | 10/V2 |
| 8.3 | winget presente, ID inexistente, pacote só de usuário, winget ausente | Mensagens próprias; escopo de máquina | 10/V3 |
| 8.4 | Web App (quiosque e app); atalho alheio com o mesmo nome | Atalho e ícone; o alheio não é trocado | 10/V4 |
| 8.5 | Lote com um item falhando; cancelar no meio | Segue e mostra a falha; não inicia o próximo | 10/V5 |
| 8.6 | Instalador MSI com `TRANSFORMS=` em Argumentos | Recusado antes de executar | 14 |
| 8.7 | Desinstalar MSI, EXE silencioso, EXE interativo, comando recusado, protegido | Conforme o ADR-020 | 10/V6 |
| 8.8 | Entrada em HKU criada por `Teste01` apontando para `%WINDIR%` | Recusada | 10/V11 |
| 8.9 | Remover o Windows Terminal; criar conta nova | Não volta | 10/V7 |

### 9. Políticas e USB

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 9.1 | Aplicar e desfazer política de máquina | Situação lida de novo | 11/V1 |
| 9.2 | Política de conta na logada, em perfil carregado e em perfil fechado; conta que roda o Bench | Aplica; a do Bench recusada | 11/V2, 11/V6 |
| 9.3 | Cancelar com perfil fechado | Hive descarregado (`reg query HKU`) | 11/V3 |
| 9.4 | Contas futuras: criar conta depois | Recebe as políticas, só lê | 11/V4 |
| 9.5 | `Teste01` tenta apagar a política | Acesso negado (dono Administradores) | 11/V5 |
| 9.6 | Sobras do Configurador e `DisallowRun` legado | Detectadas e removíveis | 11/V7 |
| 9.7 | USB desabilitar e habilitar por conta e na máquina | Pendrive não abre / abre | 11/V8 |

### 10. Proteção e Aparência

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 10.1 | Proteger e desproteger utilman/sethc | Dono TrustedInstaller de volta; acessibilidade funciona depois | 12/V1 |
| 10.2 | Win+U, botão de Acessibilidade e Shift 5x na tela de login | Bloqueados quando protegido | 12/V2 |
| 10.3 | `sfc /verifyonly` | Sem violação | 12/V3 |
| 10.4 | Binário trocado e IFEO `Debugger` (com e sem `UseFilter`) | Detectados, removidos, restaurados | 12/V4 |
| 10.5 | Papel de parede na logada, em perfil fechado e em Contas futuras; `Teste01` tenta trocar | Aplicado; usuário não troca | 12/V5 |
| 10.6 | Mouse e teclado por alvo; desfazer | Valores nativos | 12/V6 |
| 10.7 | Energia AC/DC, hibernação; desfazer | `powercfg /q` confere | 12/V7 |
| 10.8 | Cadastro com nome de programa `<b>Teste</b>`: abrir Programas, Preparação e Configurações | Texto aparece literal, sem negrito, inclusive nas dicas | 14 |

### 11. Limpeza, Registro e varreduras finais

| # | Ação | Esperado | Origem |
|---|---|---|---|
| 11.1 | Limpeza com prévia; junction em `Temp` de `Teste01` apontando para fora | Prévia com números; nada fora apagado | 13/V6 |
| 11.2 | Registro e Exportar | Arquivo sem nome de máquina, contas nem caminho de perfil | 13/V8 |
| 11.3 | Ajuda com busca em todas as telas | Resultados e "?" em toda tela | 13/V9 |
| 11.4 | `findstr /s /i` pelos marcadores no `bench.log` (todos os rotacionados), em `%TEMP%`, `protegido\` e na pasta do serviço do RustDesk | Nenhuma senha; sem SSID, host, SID, nome de conta ou caminho de perfil no log | 07/V8, 08/V8, 09/V10, 10/V10, 11/V12, 12/V11 |

### 13. Atualização automática (Módulo 16)

Com a API publicando uma versão de teste maior que a instalada (`docs/BUILD.md`, "Publicar uma
versão"), assinada com a chave principal real, e o notebook já preparado nos passos anteriores.

| # | Passo | Esperado | Origem |
|---|---|---|---|
| 13.1 | Entrar online pelo túnel | Faixa com a versão e as notas; `protegido\atualizacao\setup-<hash>.exe` | 16/V9 |
| 13.2 | "Instalar ao fechar" e fechar | UAC não aparece de novo; o instalador espera o Bench sair; ao abrir, versão nova no rodapé e em Aplicativos | 16/V9 |
| 13.3 | Conferir `ApiUrl`, login offline e `protegido\` | Mantidos | 16/V9 |
| 13.4 | Com retomada pendente (passo 3), confirmar e fechar | Aviso; nada instalado | 16/V10 |
| 13.5 | Usuário comum logado em outra sessão, com o Bench do técnico fechado | Atualização não trava | 16/V11 |
| 13.6 | `minima` acima da instalada | Faixa obrigatória, sem "Agora não" | 16/V12 |
| 13.7 | SmartScreen e UAC no instalador baixado | "Editor desconhecido" (ADR-025) | 15 |
| 13.8 | `findstr /s /i` pelo endereço da API e pelo token no `bench.log` | Nenhum token; endereço só no log do Inno | 16/V13 |

### 12. Rodada em Windows Home e em inglês (se houver máquina)

Repetir 3.1, 5.1, 6.2, 9.1, 10.5 e 11.4.

| # | Esperado | Origem |
|---|---|---|
| 12.1 | Home: políticas com aviso de edição; Store só no Pro | 11/V9, 12/V8, 13/V10 |
| 12.2 | Inglês: grupos por SID, mesmas situações | 07/V6, 08/V7, 09/V9, 10/V8, 11/V10, 12/V9, 13/V10 |
