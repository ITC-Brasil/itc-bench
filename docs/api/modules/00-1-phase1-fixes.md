# Módulo 00.1 — Correções da Fase 1

**Branch:** `module/00.1-phase1-fixes` · **Datas:** 2026-09-24 a 2026-09-28 · **Escopo:**
`docs/prompts/00-1-phase1-fixes.md` · **PR:** ITC-Brasil/tecnico-assistente#2

Corrige os defeitos da Fase 1 antes que o Módulo 03 escreva o schema de entrada da API
sobre `pendrive/SCHEMA.md`. Só `pendrive/` mudou em código. O contrato dos JSONs subiu
para `versaoSchema` 1.1 (TA-ADR-018), e as regras de classificação do Event Log foram
fechadas na revisão do PR (TA-ADR-020).

## O que foi implementado

### Origem dos defeitos

Os defeitos 1 a 6 são os da tabela de `docs/modules/00-foundation.md`. O 7 veio do
prompt da sessão e não está no Módulo 00: foi confirmado no código
(`Coleta-Disco.ps1:175` gravava `smartDisponivel = $true` assim que o contador
respondia). O 8 e o 9 foram achados nesta sessão. Os itens 10 a 13 são as decisões da
revisão do PR #2.

| # | Defeito ou decisão | Arquivo e função | Correção |
|---|---|---|---|
| 1 | Resumo de disco zerado | `pendrive/modulos/Coleta-Disco.ps1`, `Get-ColetaDisco` | Nova `Get-ResumoTier`, que soma com laço explícito. `Measure-Object -Property` sobre `[ordered]` devolve soma nula no PS 5.1 |
| 2 | Semântica de desgaste do SSD | `Coleta-Disco.ps1`, nova `Set-ContadoresSmart` | `percentualVidaRestante` → `percentualDesgaste`, sem conversão (TA-ADR-019). `pendrive/lib/Util-Relatorio.ps1` passou a mostrar `desgaste: N%` |
| 3 | APIPA em adaptador desconectado | `pendrive/modulos/Coleta-Rede.ps1`, nova `Test-Apipa` | `apipa` só é `true` com `Status -eq 'Up'` |
| 4 | Pendrive no próprio diagnóstico | `Coleta-Disco.ps1`, novas `Get-UnidadeFerramenta` e `Test-ExcluirUnidadeFerramenta` | A letra vem de `$RaizFerramenta` (`$Raiz` do `menu.ps1`) e o disco de `Get-Partition -DriveLetter`. Volume e disco físico saem só se a unidade for `Removable` ou `USB` **e** não for a do sistema. Metadado em `dados.unidadeFerramenta` |
| 5 | `fim` nulo ao fechar pelo X | `pendrive/lib/Util-Sessao.ps1`, `Save-Sessao` | Campo novo `ultimaAtualizacao`, gravado a cada `Save-Sessao`. `fim` continua significando saída pelo `[S]` |
| 6 | Base de Event Log pequena | `pendrive/config/eventlog-conhecidos.json`, `pendrive/modulos/Coleta-EventLog.ps1` | Base de 11 para 17 eventos, `peso` e `fonte` em todas as entradas, `nota` NVMe nos eventos de disco. O coletor leva `peso` e `nota` ao `eventlog.json` |
| 7 | `smartDisponivel` contradiz os dados | `Coleta-Disco.ps1`, `Set-ContadoresSmart` | `estadoSmart`: `completo`, `parcial` (lista em `observacao` os contadores ausentes) ou `indisponivel` |
| 8 | Listas não ordenadas (achado nesta sessão) | `Coleta-Disco.ps1` (`itensLimpeza`, `maioresPastasPerfil`), `Coleta-EventLog.ps1` (`grupos`) | Mesma causa do 1: `Sort-Object @{Expression='bytes'}` com chave em string não ordena `[ordered]`. Troca por scriptblock `{ $_.bytes }` |
| 9 | Temperatura 0 em disco USB (achado na coleta real) | `Coleta-Disco.ps1`, `Set-ContadoresSmart` | Discos USB devolvem `Temperature = 0` em vez de nulo. 0 °C vira `null`. O barramento da unidade da ferramenta passou a vir de `Get-PhysicalDisk`, que responde sem elevação |
| 10 | Classificação só pelo id | `Coleta-EventLog.ps1`, `Get-IndiceEventosConhecidos` e `Find-EventoConhecido` | Removido o fallback por id: só o par exato provedor + id classifica (TA-ADR-020). Na coleta real, `Microsoft-Windows-Perflib 1000` recebia a descrição de `Application Error 1000` |
| 11 | Avisos da base não coletados | `Coleta-EventLog.ps1`, nova `Select-EventosDaBase` e `Get-ColetaEventLog` | Segunda consulta com `Level = 3` e `Id` da base, filtrada pelo par exato. `grupos[].nivel` ganha `aviso`, `dados.avisoSomenteBase: true` (TA-ADR-020) |
| 12 | `volmgr 162` sem fonte e contraditório | `eventlog-conhecidos.json` | Descrição neutra, `acaoSugerida: null`, peso `baixo`, categoria `estabilidade`. Revisão definitiva pendente antes do Módulo 03 |
| 13 | Confiança da fonte | `eventlog-conhecidos.json`, `Coleta-EventLog.ps1` | `fonteOficial` em toda entrada (`false` nas 5 com `fonte: null`), copiado para `grupos[].fonteOficial` (TA-ADR-020) |

O agrupamento de eventos foi extraído para `ConvertTo-GruposEvento` (commit `refactor`,
sem mudança de comportamento) para receber teste com eventos simulados.

### Escolhas feitas no caminho

- **`estadoSmart` com nome novo.** O tipo muda de bool para string. Com o nome antigo,
  um consumidor 1.0 leria `"parcial"` como verdadeiro sem falhar (TA-ADR-018).
- **`ultimaAtualizacao` em vez de reaproveitar `fim`.** `fim` preenchido continua
  querendo dizer "encerrou normalmente".
- **Exclusão do pendrive condicionada a `Removable`/`USB` e fora do `%SystemDrive%`.**
  Uma exclusão ingênua pela letra de `$PSScriptRoot` tiraria o `C:` do diagnóstico
  quando a ferramenta roda do repositório. Com `Removable` **ou** `USB`, um SSD USB que
  o Windows reporta como `Fixed` também sai. Só é excluída a letra da ferramenta: um
  pendrive com duas partições deixaria a segunda em `volumes`, caso raro que não foi
  tratado.
- **Versão num ponto só.** `$script:VersaoSchema = '1.1'` em `Util-Sessao.ps1` substitui
  os três literais `'1.0'` (sessão, módulo e correções). `ferramentaVersao` passou a
  `1.1 (Fase 1)`.
- **Avisos só dos pares da base.** A consulta `Level = 3` filtra por `Id` no
  `FilterHashtable` e depois pelo par exato em `Select-EventosDaBase`. Um mesmo par com
  níveis diferentes vira um grupo só, com o nível mais grave.

### Base de Event Log

Critério: entrada nova só entra com página oficial da Microsoft aberta e conferida. Fórum
(Microsoft Q&A, answers.microsoft.com) e TechNet Wiki de autoria comunitária não contam.
Os níveis foram conferidos no manifesto do provedor (`Get-WinEvent -ListProvider`) ou
em ocorrência real do log System desta máquina.

| Evento | Situação | Peso | `fonteOficial` | Fonte |
|---|---|---|---|---|
| Kernel-Power 41 | herdado | alto | `true` | `troubleshoot/windows-client/performance/event-id-41-restart` |
| disk 7 | herdado, sem fonte oficial (só fórum) | alto | `false` | `null` |
| disk 51 | herdado; nível Aviso no Windows 10/11 | alto | `true` | `troubleshoot/.../event-id-51-information` |
| BugCheck 1001, WER-SystemErrorReporting 1001 | herdados, sem fonte oficial (só fórum) | alto | `false` | `null` |
| Application Error 1000 | herdado | baixo | `true` | `troubleshoot/.../troubleshoot-application-service-crashing-behavior` |
| SCM 7000 | herdado | baixo | `true` | `previous-versions/.../dd349365(v=ws.10)` |
| SCM 7031 | herdado | medio | `true` | `previous-versions/.../dd349397(v=ws.10)` |
| SCM 7034 | herdado, sem fonte oficial (só TechNet Wiki) | medio | `false` | `null` |
| volmgr 162 | herdado, descrição neutralizada | baixo | `false` | `null` |
| EventLog 6008 | herdado | medio | `true` | `archive/blogs/yongrhee/...6008...` |
| **SCM 7009** | novo (RESERVA-06) | medio | `true` | `troubleshoot/.../service-not-start-events-7000-7011-time-out-error` |
| **SCM 7011** | novo | medio | `true` | mesma página do 7009 |
| **NDIS 10317** | novo (RESERVA-06) | medio | `true` | `troubleshoot/windows-client/networking/event-10317-mobile-broadband-device` |
| **Ntfs 55** | novo | alto | `true` | `troubleshoot/.../troubleshoot-data-corruption-and-disk-errors` |
| **volmgr 46** | novo | baixo | `true` | `troubleshoot/.../event-id-46-start-a-computer` |
| **WindowsUpdateClient 20** | novo | medio | `true` | `previous-versions/.../cc735642(v=ws.10)` |

Ficaram de fora por falta de fonte oficial: WHEA-Logger 17/19 (Aviso; só Microsoft Q&A),
WHEA-Logger 18 (só TechNet Wiki comunitário; o manifesto local confirma o nível Erro),
Application Hang 1002 (só fórum), Ntfs 98 (nível não confirmado), Ntfs 137,
stornvme/storport 11 e 129, disk 153/157 e Kernel-Boot/Kernel-General. Como os Avisos
agora são lidos para qualquer par da base, basta a entrada existir com fonte para o
evento passar a ser coletado.

A ação sugerida das entradas novas se limita ao que a fonte diz. Na NDIS 10317, a fonte
oficial trata de banda larga móvel e considera o evento benigno ao ligar ou retomar da
suspensão. A ligação com Wi-Fi que não volta da suspensão vem da observação de campo na
RESERVA-06 e está marcada assim no campo `nota`.

### Nota de confiança para o relatório

Grupos com `fonteOficial: false` (disk 7, BugCheck 1001, WER-SystemErrorReporting 1001,
SCM 7034, volmgr 162) têm descrição sem fonte oficial. O prompt do Módulo 03 deve citar
o evento e a contagem desses grupos sem afirmar causa nem recomendar ação só com base na
descrição da base (TA-ADR-020). Grupos com `conhecido: false` não têm descrição da base; o
único texto é `exemploMensagem`, trecho da própria mensagem do Windows.

## Verificação realizada

Ambiente: **máquina de desenvolvimento, não da frota.** Windows 11 Pro 10.0.26340, PS
5.1.26100.9502, NVMe interno e dois dispositivos USB removíveis (`D:` e `E:`).
Identificadores da máquina (hostname, usuário, MAC, IP, serial) não estão reproduzidos
aqui, e nenhuma sessão foi copiada para o repositório.

Três formas de execução:
- **Autoteste:** `Testar-Ferramenta.ps1 -SemPausa`, no repositório e a partir do `E:`.
- **Coleta de desenvolvimento (24/09):** script de apoio fora do repositório que chama
  os coletores reais de disco, rede e Event Log por `Invoke-Coletor` e grava no
  diretório temporário da sessão, a partir do `C:`. Sem elevação por
  `runas /trustlevel:0x20000`.
- **Execução de campo (24 a 28/09), commit `fa8301f`:** a branch exportada com
  `git archive` para `E:\TecnicoAssistente\` (pendrive vazio, como numa carreta), senha
  criada pelo `Definir-Senha.bat` na primeira execução, `IniciarDiagnostico.bat`,
  opção `[1] Diagnóstico completo` e saída pelo `[S]`, feitas pelo responsável. As
  sessões ficaram no pendrive.

### Execução de campo a partir do `E:` (commit `fa8301f`)

| Cenário | Elevada (24/09, 22:05) | Sem elevação simulada via `runas /trustlevel`, commit `fa8301f` (25/09, 20:59) |
|---|---|---|
| Elevação registrada | ✅ `executadoElevado: true` na sessão e nos 5 módulos | ✅ `executadoElevado: false` na sessão e nos 5 módulos; aviso de sessão sem privilégio gravado |
| Módulos | ✅ processos, rede, eventlog, disco e bateria `ok` | ✅ os 5 `ok` |
| Encerramento | ✅ `fim` preenchido, `encerradaNormalmente: true`, `ultimaAtualizacao` presente | ✅ idem |
| `E:` fora das listas | ✅ `unidadeFerramenta`: `E`, disco 2, `Removable`, `USB`, `excluida: true`; `volumes` = `C`, `D`; `discosFisicos` = 0, 1 | ✅ idêntico: a detecção funcionou sem elevação |
| Outro USB (`D:`, disco 1) | ✅ continua coletado | ✅ continua coletado |
| SMART | ✅ NVMe `parcial` (5 contadores ausentes listados), temperatura 35 °C; USB `parcial` com temperatura `null` | ✅ esperado: todos `indisponivel`, "Contadores SMART exigem execução como administrador." |
| Resumo de limpeza | ✅ 2688912899 bytes = soma dos 13 itens seguros | ✅ esperado menor: 1710279609 bytes = soma dos 9 itens seguros |
| Itens do catálogo encontrados | ✅ 30 | ✅ esperado menor: 21 (pastas de sistema não lidas) |
| Ordenação | ✅ `itensLimpeza`, `maioresPastasPerfil` e `grupos` em ordem | ✅ idem |
| APIPA | ✅ adaptador `Disconnected` com 169.254.x.x: `apipa: false` | ✅ idem |
| Event Log | ✅ `niveisAnalisados` com `aviso`, `avisoSomenteBase: true`; `Perflib 1000` com `conhecido: false`; 4 grupos conhecidos com `fonteOficial: true` | ✅ idem, com 5 grupos conhecidos (inclui WindowsUpdateClient 20); sem diferença de acesso ao log |
| `disk 51` | ✅ nenhum grupo: as 53 ocorrências dos últimos 30 dias são de até 08/09, fora da janela de 7 dias | — (mesma janela) |
| Aviso de disco sem privilégio | — | ✅ "Sem privilégio administrativo: SMART e pastas de sistema (...) podem não ser lidos." |
| Duração do módulo de disco | 517 s | 487 s |

Uma segunda execução por duplo clique (25/09, 20:41) saiu **elevada**, porque o UAC
desta máquina está desligado (`EnableLUA=0`, `ConsentPromptBehaviorAdmin=0`). Ver
Pontos de atenção. Os resultados dela são iguais aos da execução elevada da tabela.

### Autoteste e coleta de desenvolvimento

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Autoteste completo | `Testar-Ferramenta.ps1 -SemPausa` no repositório (`b47f6e9`) | ✅ 83 OK, código de saída 0 |
| Autoteste a partir do pendrive | `E:\TecnicoAssistente\Testar-Ferramenta.ps1 -SemPausa` (`fa8301f`, sem `auth.hash`) | ✅ 79 OK, saída 0; nenhum `auth.hash` nem sessão criados |
| D1 — soma do resumo | Teste com itens `[ordered]` de 100 + 50 + nulo | ✅ 150 bytes, 2 itens |
| D2 — `Wear` sem conversão | Contador simulado `Wear = 3` e `Wear = $null` | ✅ `percentualDesgaste` 3 e `null` |
| D3 — adaptador simulado | `Test-Apipa` com `Up` e `Disconnected` em 169.254.x.x | ✅ `true` / `false` |
| D4 — decisão de exclusão | Simulação: removível, SSD USB `Fixed`, disco do sistema, 2º disco SATA, caminho UNC | ✅ exclui só os dois primeiros |
| D4 — rodando do repositório (`C:`) | Coleta de desenvolvimento, elevada e sem elevação | ✅ `excluida: false`, `C:` presente em `volumes` |
| D5 — sessão interrompida e encerrada | Teste: `Invoke-Coletor` sem e com `Save-Sessao -Encerrar` | ✅ `ultimaAtualizacao` sempre; `fim` só no encerramento |
| D6 — integridade da base | Teste: `peso` válido, `fonte` presente, 7009 e 10317 com fonte, sem duplicata | ✅ 17 entradas, 12 com fonte |
| D7 — três estados | NVMe com temperatura e desgaste; todos os contadores; nenhum | ✅ `parcial` / `completo` / `indisponivel` |
| D9 — temperatura 0 | Teste com `Temperature = 0` | ✅ `null` |
| D10 — Perflib 1000 | Teste contra a base real | ✅ `Application Error 1000` reconhecido; `Perflib 1000` não. O teste falha com o código anterior |
| D11 — Aviso da base | Teste com `disk 51`, WHEA 17 e Perflib 51 simulados | ✅ só `disk 51` passa |
| D11 — coleta real de 30 dias | `Get-ColetaEventLog -Dias 30` na máquina de desenvolvimento | ✅ `disk 51` em **um** grupo, `nivel: aviso`, 53 ocorrências |
| Agrupamento | Teste: 53 avisos `disk 51` + `Ntfs 55` em Aviso e Erro | ✅ 2 grupos; 53 ocorrências com primeira e última corretas; `Ntfs 55` com `nivel: erro` |
| D13 — `fonteOficial` | Teste: coerente com `fonte` em toda entrada | ✅ 5 `false`, 12 `true` |
| Contrato 1.1 | Teste e execuções de campo | ✅ `versaoSchema: "1.1"` em `sessao.json` e nos módulos |
| Encoding | `file` nos `.ps1`/`.bat` exportados | ✅ UTF-8 com BOM nos `.ps1`, CRLF em todos |
| Nenhuma sessão versionada | `git status --short` antes de cada commit | ✅ `pendrive/sessoes/` só com `.gitkeep` |

### Verificação complementar na frota (2026-09-28)

Feita pelo responsável depois do fechamento do módulo, numa máquina da frota: Lenovo
V15 G3 IAP (82UM), Windows 11 Pro 10.0.26200, NVMe SSSTC CL4-4D256-Q62. Pendrive
montado como `D:`. Identificadores da máquina (hostname, usuário, MAC, IP, serial) não
estão reproduzidos aqui, e nenhuma sessão foi copiada para o repositório.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Árvore da ferramenta no pendrive | Comparação com `git archive` do `b47f6e9` em diante | ✅ idêntica; único arquivo a mais: `config/auth.hash` |
| Sessão sem elevação | `IniciarDiagnostico.bat` sem elevar | Nenhum módulo executado: o operador saiu pelo `[S]`. Não repetido (decisão abaixo) |
| Sessão elevada, módulos | `[1] Diagnóstico completo` | ✅ os 5 módulos `ok` |
| Encerramento pelo X | Janela fechada pelo X | ✅ `fim: null`, `encerradaNormalmente: false`, sem aviso de erro |
| Pendrive fora das listas | `disco.json` | ✅ `unidadeFerramenta`: `D`, `USB`, `excluida: true`; só `C:` em `volumes` e só o disco 0 em `discosFisicos` |
| SMART em NVMe real | `disco.json` | ✅ `estadoSmart: parcial`: os 4 contadores de erro e `horasLigado` não expostos pelo driver |
| Desgaste em NVMe real | `disco.json` | `percentualDesgaste: 0` com `horasLigado: null`: ambíguo, vira regra do prompt no Módulo 03 |
| Temperatura | `disco.json` | ✅ `temperaturaC` 43, `temperaturaMaximaC` 83 (limite de operação, TA-ADR-019) |
| Event Log | `eventlog.json`, janela de 7 dias | ✅ 3 grupos: `HAL 21` desconhecido (`fonteOficial: null`), `NDIS 10317` e `SCM 7009` conhecidos com `fonteOficial: true`. Nenhum grupo `fonteOficial: false`, nenhum `disk 51`, nenhum `volmgr 162` |
| `usuarioLogado` | `sessao.json` | ⚠️ defeito: grava `$env:USERNAME` (`pendrive/lib/Util-Sessao.ps1`), que numa sessão elevada é a conta que elevou, não quem estava logado. Correção no Módulo 07 |

Decisões do responsável na mesma data, sem ADR:
- O técnico roda sempre elevado. O caso sem elevação já foi verificado neste módulo via
  `runas /trustlevel` e não será repetido; a verificação do UAC na frota sai das
  pendências.
- `usuarioLogado` de sessões 1.0 e 1.1 é tratado pela API como "conta que executou a
  ferramenta" e fica fora do relatório. O Módulo 07 separa `usuarioExecucao` e
  `usuarioSessao` (`Win32_ComputerSystem.UserName`), no contrato 1.2 (TA-ADR-018).
- Pendências novas do Módulo 03: `percentualDesgaste` 0 com `horasLigado` `null` é "não
  informado" no prompt; `HAL 21` só entra na base com fonte oficial (TA-ADR-020).

## Decisões

TA-ADR-018 (versionamento do contrato, campos alterados, tratamento de sessões 1.0 e regra
de incremento), TA-ADR-019 (semântica de `Wear`) e TA-ADR-020 (classificação por provedor + id,
Avisos da base, `fonteOficial` e confiança menor no prompt) foram escritos neste módulo.
Ver `docs/DECISIONS.md`.

## Dependências entre módulos

- **Módulo 03** implementa a normalização de sessões 1.0 descrita no TA-ADR-018 (inclusive
  reclassificar eventos pelo par exato) e lê `estadoSmart`, `percentualDesgaste` (valor
  alto é pior), `unidadeFerramenta`, `ultimaAtualizacao` e `grupos[].nivel`, `peso`,
  `nota` e `fonteOficial`. Precisa da regra de confiança menor para `fonteOficial: false`.
- **Módulo 07** tinha como pré-requisito estas correções. O
  `PROMPT_CLAUDE_CODE.md` §15 agora aponta para este módulo.

## Pontos de atenção

- **UAC desligado faz a ferramenta rodar sempre elevada.** Nesta máquina,
  `EnableLUA=0`: todo processo de um administrador tem integridade Alta, inclusive o
  duplo clique no `IniciarDiagnostico.bat`. Se isso se repetir na frota, o aviso "sem
  privilégio" nunca aparece e o cenário sem elevação não ocorre em campo. Para simular
  sem elevação numa máquina assim:
  `runas /trustlevel:0x20000 "cmd /c E:\TecnicoAssistente\IniciarDiagnostico.bat"`.
  O estado do UAC na frota ainda não é conhecido (passo manual do responsável).
- **`[ordered]` no PS 5.1.** `Measure-Object -Property` e `Sort-Object` com chave em
  string falham em silêncio sobre dicionários. Use laço explícito ou scriptblock
  (`{ $_.campo }`). `Util-Relatorio.ps1` e `Correcoes.ps1` não são afetados porque
  trabalham sobre o JSON relido (`pscustomobject`).
- **`return @(...)` desempacota item único.** Quem chama `Select-EventosDaBase` ou
  `ConvertTo-GruposEvento` e usa `.Count` deve envolver o resultado em `@()`.
- **Aviso fora da base não é coletado.** Um evento de hardware que o Windows registra
  como Aviso só entra no `eventlog.json` quando ganha entrada na base, com fonte.
- **`percentualDesgaste: 0` é ambíguo.** Os discos USB devolveram `Wear = 0`, que pode
  ser "não informado". A regra está no `SCHEMA.md`.
- **Entradas sem fonte oficial.** disk 7, BugCheck 1001, WER 1001, SCM 7034 e volmgr 162
  têm `fonteOficial: false`. A descrição do volmgr 162 foi neutralizada; a revisão com
  fonte oficial é pendência antes do Módulo 03.
- **Coleta na frota pendente.** Esta máquina não é da frota. O comportamento em NVMe
  real (V14 G4, V15 G3 ou Vostro) precisa de uma coleta do responsável.

## Commits

```
6f730bc docs: record develop as default branch and pre-push hook
47cd3c0 docs: add module 00.1 session prompt
a6e770d fix(pendrive): sum disk cleanup summary with explicit loop
7a4f2bf fix(pendrive): sort ordered dictionaries with scriptblock keys
e1bec2d fix(pendrive): rename SSD Wear field to percentualDesgaste
9eb78b5 fix(pendrive): report SMART as complete, partial or unavailable
2e62e78 fix(pendrive): flag APIPA only on connected adapters
963e02a fix(pendrive): exclude the tool's own drive from disk diagnosis
bebfc13 fix(pendrive): stamp ultimaAtualizacao on every session save
4cbcb3a feat(pendrive): bump session schema to 1.1
760ed5b fix(pendrive): expand curated event log base with weight and source
dd2906e fix(pendrive): treat 0 C disk temperature as not reported
653434b docs: document module 00.1 phase1 fixes
26e93d2 fix(pendrive): classify events only by exact provider and id
5ae6ff8 feat(pendrive): read warnings for curated event pairs only
d09b589 fix(pendrive): neutralize unconfirmed volmgr 162 description
fa8301f feat(pendrive): flag curated events without an official source
1f7e9ce docs: add TA-ADR-020 on event classification and source confidence
3c3df8c refactor(pendrive): extract event grouping into ConvertTo-GruposEvento
b47f6e9 test(pendrive): cover event grouping with simulated occurrences
```

O commit de documentação da revisão (`docs: update module 00.1 after PR review`) fecha a
lista.
