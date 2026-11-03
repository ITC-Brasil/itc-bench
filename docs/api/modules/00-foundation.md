# Módulo 00 — Fundação do repositório

**Concluído em:** 2026-09-24 · **Branch:** `module/00-foundation`

O módulo tem duas partes. A primeira é a importação da Fase 1 (`pendrive/`), escrita
por volta de 2026-09-04 e 09-05 sem documentação de módulo e sem histórico no Git: ela
é documentada aqui **retroativamente**. A segunda é a fundação do repositório
(`.gitignore`, `.gitattributes`, `docs/`, `CLAUDE.md`).

## O que foi implementado

### Fase 1 — ferramenta do pendrive (retroativo)

**Entrada e fluxo**
- `pendrive/IniciarDiagnostico.bat`, `Definir-Senha.bat`, `Testar-Ferramenta.bat`:
  atalhos que chamam o `.ps1` correspondente com `-NoProfile -ExecutionPolicy Bypass`.
- `pendrive/menu.ps1`: `Test-AutenticacaoTecnico` (3 tentativas contra
  `config/auth.hash`), `Select-PerfilUso` (projeto e sub-perfil de
  `config/perfis.json`), menu `[1]`–`[6]` de coleta, `[A]`–`[D]` de correção, `[R]`
  para o relatório da última sessão desta máquina e `[S]` para sair. Um `try/catch/finally`
  global grava o erro (`Write-ErroFatal`) e sempre pausa antes de fechar
  (`Wait-Saida`), a menos que receba `-SemPausa`.
- `pendrive/Definir-Senha.ps1`: grava em `config/auth.hash` o SHA-256 (hex minúsculo) da
  senha. A proteção é deliberadamente contra uso casual: quem tem acesso técnico ao
  pendrive consegue contorná-la (`pendrive/README.md` §1).

**Sessão** (`pendrive/lib/Util-Sessao.ps1`)
- `New-Sessao`: cria `sessoes/<yyyy-MM-dd_HHmm>_<COMPUTERNAME>/` e coleta os metadados
  da máquina via CIM (`Get-ModeloNotebook`: fabricante, modelo, família, número de
  série da BIOS, memória, CPU, SO).
- `Invoke-Coletor`: roda cada coletor isolado. Se ele falha, grava `status: "erro"` no
  envelope do módulo e o log em `erros.log`, e a sessão continua.
- `Save-Sessao`: regrava `sessao.json` a cada módulo, para que uma execução
  interrompida continue legível. `-Encerrar` preenche `fim` e
  `encerradaNormalmente: true`.
- `Save-Json`: UTF-8 **sem** BOM, `ConvertTo-Json -Depth 12`.
- `Add-CorrecaoSessao`: registra cada ação em `correcoes.json` com resultado
  `sucesso`, `falha` ou `cancelada`.

**Coletores** (`pendrive/modulos/`)
- `Coleta-Processos.ps1` (`Get-ColetaProcessos`): memória, com `pressaoAlta` a partir de
  85% de uso; maiores processos; serviços automáticos parados; itens de inicialização.
- `Coleta-Rede.ps1` (`Get-ColetaRede`): adaptadores (IP, gateway, DNS, MAC, flags
  `semIP` e `apipa`), ping para `8.8.8.8` e `1.1.1.1`, resolução de `www.google.com` e
  portas TCP em escuta com o processo dono.
- `Coleta-EventLog.ps1` (`Get-ColetaEventLog`): logs `System` e `Application`, níveis 1 e
  2, janela padrão de 7 dias, eventos agrupados por provedor e ID e cruzados com
  `config/eventlog-conhecidos.json`.
- `Coleta-Disco.ps1` (`Get-ColetaDisco`): faz quatro coletas.
  - Volumes, com `critico` abaixo de 10% livre e `atencao` entre 10% e 20%.
  - SMART via `Get-StorageReliabilityCounter`.
  - Catálogo de limpeza (`Expand-ItensLimpeza`, `Measure-Pasta`).
  - Uma única varredura de `C:\Users` que produz as pastas de perfil ≥ 500 MB e os
    25 maiores arquivos ≥ 200 MB, cada caminho etiquetado por `Get-TierCaminho`.
- `Coleta-Bateria.ps1` (`Get-ColetaBateria`): roda `powercfg /batteryreport` gravando na
  pasta da sessão, extrai as capacidades com `ConvertFrom-RelatorioBateria` e classifica
  o desgaste com `Get-ClassificacaoDesgaste`:
  - `saudavel` abaixo de 20%;
  - `desgaste-moderado` abaixo de 40%;
  - `desgaste-alto` abaixo de 60%;
  - `substituicao-recomendada` a partir de 60%.

**Correções** (`pendrive/modulos/Correcoes.ps1`, TA-ADR-014)
- `Start-/Invoke-CorrecaoMatarProcesso`, `...ReiniciarServico`, `...ResetarAdaptador` e
  `...LimparItem`/`Start-CorrecaoLimparTemporarios`.
- `$Script:ProcessosProtegidos` recusa `System`, `Idle`, `Registry`, `smss`, `csrss`,
  `wininit`, `winlogon`, `services`, `lsass`, `lsm`, `svchost`, `dwm`, `fontdrvhost`,
  `MemCompression`, `powershell`, `pwsh`, `conhost` e `WindowsTerminal`.
- A confirmação é `Confirm-Acao` (`pendrive/lib/Util-Interface.ps1`), que exige `SIM`
  digitado com a mesma caixa (`-ceq`).
- A limpeza é item a item e só oferece o tier `seguro`.

**Configuração** (`pendrive/config/`)
- `perfis.json`: define 4 projetos (BSBIA, QDFM, SEDET, CODHAB) e 2 políticas.
  - `permissiva`: sub-perfil aluno, ciclo de retenção de 20 a 30 dias.
  - `conservadora`: demais sub-perfis (TA-ADR-017).
- `classificacao-disco.json`: 19 itens (12 `seguro`, 3 `revisar`, 4 `bloqueado`).
  - As regras de prefixo tratam `%SystemRoot%`, `%ProgramFiles%` e
    `%ProgramFiles(x86)%` como `bloqueado`, e `%ProgramData%` e `%SystemDrive%\Users`
    como `revisar`.
  - `tierFallback: "revisar"`.
- `eventlog-conhecidos.json`: 11 eventos curados, entre eles Kernel-Power 41, disk 7 e
  51, BugCheck 1001, Service Control Manager 7000, 7031 e 7034, volmgr 162 e
  EventLog 6008.

**Relatório** (`pendrive/lib/Util-Relatorio.ps1`)
- `Write-RelatorioSessao`: único ponto que transforma os JSONs em texto na tela. É o
  ponto de troca da Fase 2 (Módulo 07).

**Autoteste** (`pendrive/Testar-Ferramenta.ps1`)
- Não coleta nada da máquina. Cobre 8 grupos: sintaxe dos 12 `.ps1`, carga dos JSONs de
  configuração, hash de senha, classificação de tier, parsing do relatório de bateria,
  pausa e tratamento de erro, e scripts de entrada.
- `-SemPausa` para uso automatizado; sai com 0 quando tudo passa e 1 em caso de falha.

**Contrato de dados:** `pendrive/SCHEMA.md` descreve o envelope comum dos módulos e o
formato de `sessao.json` e `correcoes.json` (`versaoSchema: "1.0"`). Esse é o
contrato que a API vai consumir (TA-ADR-001, TA-ADR-006).

### Fundação do repositório

- `.gitignore`: ignora `.env`/`.env.*` (exceto `.env.example`), `pendrive/config/auth.hash`,
  `pendrive/config/api.json`, `pendrive/sessoes/*` (exceto `.gitkeep`), `*.db` e os
  arquivos `-journal`, `-wal` e `-shm`, além dos artefatos de Python e de editor.
- `.gitattributes`: `*.bat`, `*.cmd` e `*.ps1` com `eol=crlf`. Sem isso, um checkout em
  Linux (o glpi-srv, ou quem preparar pendrives a partir dele) entregaria `.bat` com
  LF, o que quebra `goto` e labels no `cmd.exe`. Foi a escolha mais simples para um
  problema real, por isso ficou registrada aqui e não em ADR.
- `pendrive/sessoes/.gitkeep`: mantém a pasta no repositório vazia.
- `pendrive/SCHEMA.md`: o número de série de exemplo foi trocado por `XXXXXXXX`
  (precaução pedida pelo responsável). O hostname `BSBIA-NB-014` e o usuário `aluno01`
  são fictícios e foram mantidos.
- `docs/`: `ARCHITECTURE.md` (com a tabela de restrições de infraestrutura), `PROGRESS.md`,
  `API.md`, e `TOKENS.md`, `DEPLOY.md` e `NOCODB.md` como marcadores dos módulos 02, 05/06
  e 04. `docs/DECISIONS.md` (TA-ADR-001 a TA-ADR-017) foi entregue pelo responsável e
  versionado sem alteração.
- `CLAUDE.md`, `README.md` e `documentacao-tecnico-assistente.md`.

## Verificação realizada

Verificado retroativamente em 2026-09-24, no Windows PowerShell 5.1.26100.9502, antes
do commit de importação.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Autoteste completo da Fase 1 | `powershell -NoProfile -ExecutionPolicy Bypass -File pendrive\Testar-Ferramenta.ps1 -SemPausa` | ✅ "Todos os testes passaram.", código de saída 0, cerca de 6,4 s |
| Autoteste não deixa resíduo | `find pendrive/sessoes -type f` depois da execução | ✅ Pasta vazia (o log de erro do teste de erro fatal é removido) |
| Nenhum `.git` aninhado nem resto de KitBenchmark | `find pendrive -name ".git*" -o -iname "*KitBenchmark*"` | ✅ Nada encontrado |
| Nenhum dado real no primeiro commit | `grep` por IP, MAC, e-mail, URL, GUID, `Users\<nome>`, padrões de hostname e serial em `pendrive/` | ✅ Só IPs públicos ou de loopback (`8.8.8.8`, `1.1.1.1`, `127.0.0.1`) e exemplos fictícios; serial de exemplo trocado |
| `sessoes/`, `auth.hash` e `api.json` fora do Git | `git status --short` antes do commit | ✅ Só `pendrive/sessoes/.gitkeep` versionado |
| `DECISIONS.md` intacto | `git diff --quiet develop -- docs/DECISIONS.md` | ✅ Sem diferença |
| Defeito "resumo de disco zerado" | `[ordered]@{bytes=100},[ordered]@{bytes=50} \| Measure-Object -Property bytes -Sum` no PS 5.1 | ✅ Reproduzido: soma 0 (com `pscustomobject`, 150) |
| Coleta real numa máquina da frota | — | Não executado neste módulo. O autoteste não cobre os coletores (`Get-Coleta*`) |

## Defeitos conhecidos em aberto

Estão listados no pré-requisito do Módulo 07 (`PROMPT_CLAUDE_CODE.md` §15). O relato
original do teste de campo não está no repositório. As causas abaixo foram localizadas
no código neste módulo, e a coluna "Confirmação" diz o que foi de fato verificado.

| # | Defeito | Onde | Causa no código | Confirmação |
|---|---|---|---|---|
| 1 | Resumo de disco zerado | `pendrive/modulos/Coleta-Disco.ps1:255` e `:257` | `Measure-Object -Property bytes` sobre itens `[ordered]` devolve soma nula no PS 5.1 (limitação citada no TA-ADR-013). `resumo.recuperavelSeguroBytes` e `revisarBytes` vão como 0 para o `disco.json`. Na tela o valor sai certo porque `Util-Relatorio.ps1:75` soma a partir do JSON relido (`pscustomobject`) | Reproduzido |
| 2 | Semântica de desgaste do SSD | `Coleta-Disco.ps1:183` | O campo se chama `percentualVidaRestante`, mas recebe `$rc.Wear` do `Get-StorageReliabilityCounter`, que indica desgaste. O sentido provavelmente está invertido; confirmar na documentação da Microsoft ao corrigir | Inferido do código |
| 3 | APIPA em adaptador desconectado | `modulos/Coleta-Rede.ps1:42` | `apipa` fica `true` para qualquer adaptador com 169.254.x.x, inclusive `Disconnected`, o que é normal no Windows. O `resumo.temIPValido` (linha 103) já filtra os ativos; o dado bruto por adaptador engana quem o consome | Inferido do código |
| 4 | Próprio pendrive entra no diagnóstico | `Coleta-Disco.ps1:131` e `:152` | `Get-Volume` filtra só por letra e tamanho, e `Get-PhysicalDisk` lista tudo, então o volume e o disco USB do pendrive aparecem em `volumes` e `discosFisicos`. Um pendrive cheio pode ser marcado como `critico` | Inferido do código |
| 5 | `fim` da sessão | `pendrive/menu.ps1:245`, `lib/Util-Sessao.ps1:99` | `fim` só é preenchido ao sair por `[S]`. Se a janela for fechada pelo X (caso comum em campo), fica `fim: null`, `encerradaNormalmente: false` e `duracaoSegundos` do último módulo gravado | Inferido do código; o sintoma exato do teste não está registrado |
| 6 | Base de Event Log pequena | `pendrive/config/eventlog-conhecidos.json` | Só 11 eventos curados; grupos fora da base saem sem descrição nem ação sugerida | Contagem conferida |

Nenhum deles foi corrigido neste módulo: a correção pertence ao pré-requisito do
Módulo 07.

## Decisões

Nenhum ADR novo neste módulo. `docs/DECISIONS.md` foi versionado com TA-ADR-001 a TA-ADR-017.
Os TA-ADR-013 a TA-ADR-017 são os retroativos da Fase 1 (PowerShell 5.1 sem instalação,
correções por template, hostname como chave, IA que nunca decide, perfis por projeto).

Escolhas simples registradas aqui, sem ADR:
- `.gitattributes` com CRLF para scripts Windows (motivo na seção de fundação).
- O restante do Módulo 00 (docs e `CLAUDE.md`) foi feito na branch `module/00-foundation`,
  com PR para a `develop`. Só os três commits de importação foram direto para a `main`,
  como prevê a exceção do Módulo 00.

## Dependências entre módulos

- **Módulo 03** consome `pendrive/SCHEMA.md` como contrato do schema Pydantic tolerante. Os
  defeitos 1 a 3 afetam o que a IA lê: até serem corrigidos, o prompt deve tratar
  `resumo.*Bytes = 0`, `percentualVidaRestante` e `apipa` em adaptador desconectado com
  cautela.
- **Módulo 07** substitui `Write-RelatorioSessao` (`pendrive/lib/Util-Relatorio.ps1`) e
  depende da correção dos seis defeitos acima.
- **Módulo 05** vai rodar `gitleaks` sobre este histórico. O primeiro commit foi
  inspecionado manualmente porque não há secret scanning no GitHub Free (TA-ADR-012).

## Pontos de atenção

- `.ps1` em **UTF-8 com BOM**: o PS 5.1 lê arquivo sem BOM como ANSI e corrompe os
  acentos. Os JSONs de sessão, ao contrário, saem **sem** BOM (`Save-Json`), e a API
  deve aceitar os dois.
- Qualquer soma sobre coleções `[ordered]` no PS 5.1 precisa de laço ou de conversão para
  `pscustomobject`; `Measure-Object -Property` falha em silêncio (defeito 1).
- As sessões reais contêm hostname, `usuarioLogado`, MAC, número de série da BIOS e
  caminhos de perfil. É por isso que `pendrive/sessoes/*` fica fora do Git, e por isso
  valem o TA-ADR-011 e a retenção zero do provedor.
- `config/auth.hash` é SHA-256 sem sal. Serve só contra uso casual, por decisão de
  projeto; não reutilizar essa senha em outro lugar.
- O autoteste cobre sintaxe e lógica pura, mas não os coletores. Uma regressão em
  `Get-Coleta*` só aparece em máquina real.
- Precisa de administrador: SMART, `Temp` do Windows e Windows Update, reset de
  adaptador e, em geral, reiniciar serviço. Sem elevação a sessão registra o aviso e
  continua.

## Commits

```
47c7c1c feat(pendrive): import phase 1 diagnostic tool
c4e7e2e docs: add pre-implementation and retroactive ADRs 001-017
b412f3d docs: add Claude Code initialization prompt
84a69ba docs: add docs skeleton and root readme
d658174 docs: add CLAUDE.md with permanent session context
```

Mais o commit `docs: document module 00 foundation`, que contém este arquivo.
