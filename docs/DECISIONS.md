# Architecture Decision Records

Registro sequencial de decisões, com contexto e alternativas rejeitadas.
Cada entrada é permanente — ADRs substituídos são marcados, nunca apagados.

---

## ADR-001 — Chamar o produto de ITC Bench e usar a identidade de `docs/design/`

**Status:** Accepted
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
O app junta configuração e diagnóstico. O nome não pode prender o produto a um dos dois e deve
seguir a família ITC NoteScan / ITC Tasks.

**Decision**
Nome ITC Bench; símbolo, paleta, tipografia e ícones conforme `docs/design/README.md` e
`docs/design/itc-bench-identidade-telas.html`.

**Alternatives considered**
- ITC Setup — fraco para diagnóstico; "setup" já nomeia metade dos instaladores.
- ITC Toolbox — longo no lockup; soa como pasta de utilitários.

**Consequences**
Tokens e símbolo fixados em `docs/UI-UX-BRIEF.md`. O `.ico` multi-tamanho fica para o módulo de
empacotamento (14).

---

## ADR-002 — Um app instalável em Python + PySide6, empacotado com PyInstaller

**Status:** Accepted (ferramenta de instalador: planejada para o Módulo 14)
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
O Configurador tem duas UIs (CustomTkinter em `main_moderno.py` + `ui/`, PySide6 em `app_qt.py`
+ `interface_qt/`), roda da pasta do EXE e não tem `.spec`. A versão Qt já cobre mais abas e tem
`LogBus` para atualizar a UI a partir de threads.

**Decision**
Um único app em Python + PySide6, partindo de `interface_qt/` e `backend/`, empacotado com
PyInstaller e distribuído por instalador Windows. A UI CustomTkinter é descartada.

**Alternatives considered**
- Manter CustomTkinter — menos abas migradas, duplicação atual.
- Reescrever em C#/.NET — perderia o `backend/` existente e a experiência da equipe em Python.
- App portátil sem instalador — mantém caminhos atrelados ao EXE e segredos ao lado dele.

**Consequences**
Inno Setup ou WiX: **planejado**, decisão em ADR no Módulo 14. Versões de Python e PySide6
fixadas no manifesto do Módulo 01.

---

## ADR-003 — Absorver o pendrive como módulo de Diagnóstico; a API continua no repo dela

**Status:** Superseded by ADR-012
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
O pendrive (`tecnico-assistente/pendrive/`, PowerShell 5.1) e a API (`tecnico-assistente/api/`,
FastAPI + SQLite) vivem num monorepo (ADR-001 de lá). Com o Bench instalado, carregar pendrive
deixa de fazer sentido.

**Decision**
O diagnóstico vira o grupo Diagnóstico do Bench. A API permanece em `ITC-Brasil/tecnico-assistente`
e o Bench é cliente dela.

**Alternatives considered**
- Trazer a API para este repo — misturaria app de desktop com serviço do servidor, deploys diferentes.
- Manter o pendrive separado — o técnico continua com duas ferramentas e dois logins.

**Consequences**
Mudanças de API exigem PR no outro repo (marcadas **[TA]** no plano). Reaproveitar os `.ps1` ou
portar para Python: **planejado**, ADR no Módulo 05.

---

## ADR-004 — Organizar o menu em 7 grupos

**Status:** Accepted
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
O Configurador tem 17 abas planas (`interface_qt/aba_*.py`) mais o pendrive, sem ordem de trabalho.

**Decision**
Barra lateral com Início, Preparar, Software, Segurança, Aparência e periféricos, Diagnóstico e
Sistema, com os itens de `docs/APP-FLOW.md`.

**Alternatives considered**
- Manter as 17 abas — difícil de achar, sem relação com a sequência de preparação.
- Assistente linear único — rígido para correções pontuais; a Preparação completa já cobre o fluxo guiado.

**Consequences**
Apps, Winget e WebApps viram uma tela (Programas); Sistema se divide entre Identificação e Energia.
A navegação é montada no Módulo 01.

---

## ADR-005 — Login por técnico validado no GLPI através da API do Técnico Assistente

**Status:** Accepted (rotas: planejadas para o Módulo 03, no repo `tecnico-assistente`)
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
Hoje qualquer pessoa com acesso de administrador abre o Configurador; o pendrive usa senha única
com SHA-256 em `config\auth.hash`. Nenhum registro diz quem fez cada ação. Todo técnico já tem
conta no GLPI.

**Decision**
O Bench envia usuário e senha à API, que valida na API do GLPI, exige o grupo de técnicos, limita
tentativas e devolve sessão. O Bench nunca fala com o GLPI. Sem internet, vale o último login
daquele técnico naquela máquina por 7 dias (hash com DPAPI). A integração GLPI fica isolada em um
módulo da API. O UAC continua obrigatório.

**Alternatives considered**
- Base de usuários própria — mais um cadastro para manter e desligar.
- Bench falando direto com o GLPI — credenciais de app GLPI no instalador; acoplaria o Bench à versão do GLPI.
- TOTP (Ente Auth) como fator principal — exige segredo por técnico e recuperação de celular; fica
  como possível segundo fator só para Configurações, depois.
- Senha única compartilhada (modelo do pendrive) — sem rastreio, revogação impossível.

**Consequences**
GLPI 11 hoje, 12 com HTTPS antes da volta a campo: troca toca um arquivo na API. Escopo DPAPI e
persistência da sessão: ADR no Módulo 03.

---

## ADR-006 — Cadastros no NocoDB, entregues pela API, com cópia local DPAPI

**Status:** Accepted (rotas: planejadas para o Módulo 05, neste repo, em `api/`; ADR-012)
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
Wi-Fi, servidores e senhas estão em `config/wifi_db.json` e `config/segredos.json` ao lado do EXE.
A base "ITC Bench" no NocoDB já tem as tabelas Servidores, Instaladores, WiFi e Unidades
(`docs/BACKEND-SCHEMA.md`). O ADR-005 do Técnico Assistente define o NocoDB como espelho só de ida
e proíbe acesso das carretas ao NocoDB.

**Decision**
O NocoDB é fonte da verdade dos cadastros. Após o login, o Bench pede os cadastros à API e guarda
cópia protegida por DPAPI. O Bench nunca acessa o NocoDB.

**Alternatives considered**
- Bench lendo o NocoDB direto — token que lê, altera e apaga a base inteira em cada instalação,
  sem revogação por máquina (mesmo motivo do ADR-005 de lá).
- JSON no instalador — segredos distribuídos em cada máquina, atualização exige reinstalar.
- Cadastros no SQLite da API com tela própria — construiria a interface que o NocoDB já dá.

**Consequences**
Revisa o ADR-005 do Técnico Assistente: um ADR correspondente entra lá no módulo que implementar
as rotas. Funciona offline com dados da última sincronização.

---

## ADR-007 — Ajuda contextual em cada tela e tela Ajuda consolidada

**Status:** Accepted
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
O manual (`Manual_Configurador_ITC.pdf`, 31/10/2026) é um PDF separado e só tem passo a passo de
Usuários, Tela, Mouse e Proteção do Login.

**Decision**
Botão "?" ao lado do título de cada tela abre as instruções dela; a tela Ajuda reúne todas, na
ordem do menu, com busca. O texto das telas sem manual é escrito quando cada uma for migrada.

**Alternatives considered**
- Manter o PDF — desatualiza e fica longe de onde o técnico precisa.
- Tooltips só — não cabem passo a passo nem regras ("o que o Bench não deixa fazer").

**Consequences**
Cada módulo de migração (06–12) inclui a ajuda da tela como tarefa. Formato do conteúdo: Módulo 01.

---

## ADR-008 — Dados fora do código; só o endereço da API no instalador

**Status:** Accepted
**Date:** 2026-11-03
**Module:** Pre-implementation

**Context**
`config/config.ini` do Configurador guarda senhas em texto claro; `config/segredos.json` fica
legível ao lado do EXE. A análise de 03/11/2026 os classifica como críticos.

**Decision**
Endereços, chaves, senhas e redes Wi-Fi nunca entram no repositório nem em `.conversa/`. O único
dado de ambiente no instalador é o endereço da API.

**Alternatives considered**
- Arquivo de segredos cifrado no instalador — a chave teria de ir junto.
- Variáveis de ambiente na máquina — espalhadas, sem atualização central.

**Consequences**
`.gitignore` bloqueia `segredos*.json` e `*.ini.local`. Exemplos nas telas de design não vão para
código nem testes. Telas sem cadastro preenchido recusam a ação e dizem o que falta.

---

## ADR-009 — Aceitar os hosts reais de servidor no histórico git de `b70473b`

**Status:** Accepted
**Date:** 2026-11-03
**Module:** 00

**Context**
O commit `b70473b` (`docs: add approved design and configurador analysis`) trouxe
`docs/design/itc-bench-identidade-telas.html` com os hosts reais de GLPI e RustDesk na Tela 6.
O `b76f685` os trocou por `exemplo.invalid`. O PR #1 foi mergeado em `develop` com merge commit
(`e0bd38d`), não squash, e por isso `b70473b` ficou no histórico de `develop`. Isso contraria o
ADR-008.

**Decision**
Aceitar o risco: manter o histórico como está e não reescrever `develop` nem `main`.

**Alternatives considered**
- Recriar `develop` com um único commit e force push — exige liberar o force push e obriga
  quem já clonou o repo a clonar de novo, para esconder dados que não são credenciais.
- Reescrever o histórico com `git filter-repo` — mesmo custo, e o GitHub continua servindo o
  commit antigo pelo hash até o garbage collection.

**Consequences**
Os nomes de host podem ser lidos no histórico de qualquer clone. Não há senha, chave completa
nem token. A partir daqui, achados da categoria 4 em histórico git são tratados antes do merge
do PR. A auditoria do Módulo 00 (`docs/security/2026-11-03-modulo-00.md`) aponta para este ADR.

---

## ADR-010 — Stack do app: Python 3.13, PySide6 6.12, uv, ruff, mypy e pytest-qt

**Status:** Accepted
**Date:** 2026-11-03
**Module:** 01

**Context**
O ADR-002 fixou Python + PySide6 + PyInstaller, mas deixou versões, ferramentas e layout para o
Módulo 01. O Configurador roda em Python 3.11, sem manifesto nem lock, com efeitos colaterais no
import de `config.py`. Proposta e ajustes aprovados em `.conversa/` em 03/11/2026.

**Decision**
- **Python 3.13 x64** (`requires-python = "==3.13.*"`, `.python-version` = `3.13`), **PySide6
  6.12.0**, PyInstaller 6.22.3 no módulo 14.
- **uv** com `pyproject.toml` (PEP 621, build hatchling, layout `src/`) e `uv.lock` versionado;
  `[tool.uv] required-version = ">=0.12.17,<0.13"` (versão instalada na bancada de
  desenvolvimento: 0.12.17; a 0.13 entra com ADR próprio ou ajuste deste).
- **ruff** (lint e format), `select = ["E", "W", "F", "I", "B", "UP", "S", "BLE", "SIM", "PTH",
  "TID", "RUF"]`. `S602`/`S604` barram `shell=True`; `S110`, `BLE001` e `E722` barram `except: pass`
  e captura genérica muda. `TID251` (`banned-api`) proíbe `PySide6` fora de `ui/`, do ponto de
  entrada e dos testes: `nucleo/` e `servicos/` não importam Qt.
- **mypy** `strict` em `src/`, usando os stubs que o próprio PySide6 distribui.
- **pytest + pytest-qt** (`qtbot`), com `QT_QPA_PLATFORM=offscreen`.
- **Fontes** Archivo (400/600/800) e Inter (400/500/600) em TTF estáticos, SIL OFL 1.1, com
  `OFL.txt` e README de origem (URL, commit, SHA-256) em `src/itc_bench/recursos/fontes/`.
- **Layout:** `src/itc_bench/{nucleo,servicos,ui,recursos}`; recursos lidos por
  `importlib.resources`. Elevação em `nucleo/elevacao.py`, com a decisão separada da chamada a
  `ShellExecuteW`.
- **Identificadores em português** (módulos, funções, variáveis, testes), como no Configurador.
  Exceções: nomes de API externa e de bibliotecas, e mensagens de commit (inglês, `AGENTS.md`).

**Alternatives considered**
- Python 3.14 — há pouco tempo no PyInstaller e nas bibliotecas Windows; 3.11 — suporte termina
  em 2027.
- pip-tools (`requirements.in`/`.txt`) — dois arquivos e sem gerência de Python; Poetry — lock
  próprio, mais lento, nada que o uv não cubra.
- black + flake8 + isort — três ferramentas para o que o ruff faz.
- pyright — exige Node; o mypy usa os mesmos stubs do PySide6 (não há plugin de mypy para ele;
  a escolha é pelo ecossistema Python puro, não por plugin).
- Fontes variáveis — o `QFontDatabase` aplica pesos de forma inconsistente em TTF variável no
  Windows; estáticos dão o peso exato do design.
- Pastas planas como no Configurador — misturam Qt e lógica e tornam difícil testar sem janela.

**Consequences**
`uv sync --frozen` reproduz o ambiente. Atualizar Python ou PySide6 exige rodar lint, testes e
`--teste` e registrar a troca aqui ou em ADR novo. Código novo em `nucleo/` e `servicos/` pode
ser testado sem Qt.

---

## ADR-011 — Executor único de comandos e ACL de `%ProgramData%\ITC`

**Status:** Accepted
**Date:** 2026-11-03
**Module:** 02

**Context**
O Configurador chama programas de quatro jeitos, vários com `shell=True` e com o dado do usuário
dentro do texto do comando (`docs/referencia/analise-configurador-2026-11-03.md`, item 3). Só
`backend/contas.py` segue um padrão seguro (dados em `ITC_*` no ambiente). A auditoria do Módulo
01 achou `%ProgramData%\ITC\Bench` com o ACL herdado, que deixa usuário comum criar arquivos ali.
Desenho aprovado em `.conversa/` em 03/11/2026, com ajustes.

**Decision**
- **Um executor**, `servicos/executor.py`, sem Qt:
  `executar(argumentos, *, ambiente=None, entrada=None, timeout=120, codificacao="auto") -> Resultado`
  e `powershell(script, *, timeout=120, **variaveis) -> Resultado`. `Resultado` (imutável):
  `codigo` (`None` se esgotou), `saida`, `erros`, `duracao`, `esgotado`, e `ok`. Código ≠ 0 não
  levanta exceção; uso errado levanta (`TypeError` para comando em texto, `ValueError` para caminho
  relativo ou nome de variável inválido).
- **Programa por caminho absoluto** (`sistema32("netsh.exe")`), `shell=False` explícito,
  `CREATE_NO_WINDOW`. Motivo: `CreateProcess` sem caminho procura na pasta atual e no PATH.
  A pasta de sistema vem de `GetSystemDirectoryW`, não de `SYSTEMROOT` do ambiente.
- **Ambiente:** o filho herda `os.environ` sem nenhum `ITC_*` herdado; nomes novos têm que casar
  com `ITC_[A-Z0-9_]+` (senão `ValueError`). `SYSTEMROOT` e `WINDIR` do filho são sobrescritos
  com a pasta real do Windows (com `SYSTEMROOT` falso o PowerShell nem inicia).
- **Dado sensível:** `Sensivel` (`repr`/`str` = `***`) só no ambiente ou no stdin, nunca nos
  argumentos (aparecem na lista de processos). O log tem o comando, os nomes das variáveis, código
  e duração, nunca os valores. Cada valor sensível é trocado por `***` em `saida` e `erros` antes de
  devolver e de logar. O stderr do PowerShell com `-EncodedCommand` vem em CLIXML (`<`, `&` e
  quebras escapados): é convertido em texto antes da máscara, senão a senha escapada passaria.
- **PowerShell 5.1:** `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile
  -NonInteractive -EncodedCommand <base64 de UTF-16LE>`. Abertura fixa: saída UTF-8,
  `$ErrorActionPreference = 'Stop'`, `$ProgressPreference = 'SilentlyContinue'` e `PSModulePath`
  só com `System32\WindowsPowerShell\v1.0\Modules` e `Program Files\WindowsPowerShell\Modules`,
  lidos por `[Environment]::GetFolderPath`.
  Sem `-ExecutionPolicy`: `-EncodedCommand` não é script em arquivo, e GPO ganha da linha de
  comando. Testado com `-ExecutionPolicy Restricted`: `Get-LocalUser` e `Get-NetAdapter` (CDXML)
  funcionam. **Limite de tamanho:** linha de comando do Windows tem 32 767 caracteres; o base64 de
  UTF-16LE ocupa 8/3 caracteres por caractere do script, então abertura + script ficam em até
  ~12 000 caracteres (o executor recusa acima disso).
- **Timeout** 120 s padrão; quem instala programas (Módulo 08) passa o seu. Cada processo entra
  num Job Object com `KILL_ON_JOB_CLOSE`. No timeout, `TerminateJobObject` encerra processo e
  filhos (`esgotado=True`). No fim normal de cada chamada o handle do job é fechado e o que sobrou
  é encerrado. Uma opção para manter filhos vivos só entra quando um módulo precisar, com registro.
  **Limite conhecido:** o processo roda por alguns microssegundos antes de entrar no job (o
  `Popen` não cria suspenso); um filho criado nesse intervalo escapa.
- **Codificação:** PowerShell em UTF-8. Nativos em `auto` (padrão): UTF-8 se a saída for UTF-8
  válido, senão OEM (`GetOEMCP`, cp850 no pt-BR). Motivo: no Windows 11 o `netsh` já escreve
  UTF-8 mesmo com OEM 850, e o `cmd` escreve OEM; texto OEM com acento quase nunca é UTF-8
  válido. `oem`, `ansi` (`GetACP`) e `utf-8` forçam a página. Sempre `errors="replace"`.
- **UI:** `ui/tarefa.py`, `QRunnable` no pool global com sinais `concluido(Resultado)` e
  `falhou(str)`. Exceção dentro da tarefa (que não passa pelo `sys.excepthook`) vai para o log com
  traceback e para `falhou`.
- **Sem shell:** ruff `TID251` bane `subprocess`, `os.system`, `os.popen`, `os.startfile`,
  `os.spawn*`, `os.exec*` e `asyncio.create_subprocess_exec/_shell` em todo `src/`, menos no
  executor; um teste percorre a AST de `src/` com os mesmos nomes e com `shell=` diferente de
  `False`.
- **ACL** em `%ProgramData%\ITC` e `%ProgramData%\ITC\Bench`, a cada execução elevada, antes de
  abrir o log: SDDL `O:BAD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)` (dono
  Administradores; sem herança; SYSTEM e `S-1-5-32-544` total; `S-1-5-32-545` leitura) aplicado com
  `TreeSetNamedSecurityInfoW`, por ctypes, sem dependência nova. Antes, recusa e registra se `ITC`,
  `Bench` ou algo dentro for ponto de reparse, e confere de novo depois do ACL (fecha a corrida
  em que um usuário cria junction entre a checagem e o ACL; o `TreeSetNamedSecurityInfoW` não
  atravessa junction, testado). Por item, a falha só chega pelo callback de progresso. Se a troca de dono falhar por acesso, habilita
  `SeTakeOwnershipPrivilege` e `SeRestorePrivilege` e tenta de novo; se ainda falhar, log e tela.
  Sem admin, não tenta e registra no log.
- **Segredos (decisão do responsável):** cache, token e qualquer arquivo DPAPI dos Módulos 04 e
  05 ficam numa subpasta sem leitura para Usuários (só SYSTEM e `S-1-5-32-544`), porque DPAPI em
  escopo de máquina é decifrável por qualquer usuário local. Nome e criação ficam para o 04.

**Alternatives considered**
- Tupla `(codigo, linhas)` como em `contas.py` — não separa falha de tempo esgotado nem dá duração.
- `-Command` com o script na lista de argumentos — o PowerShell 5.1 remove aspas duplas internas.
- `-File` com `.ps1` empacotado — exigiria `-ExecutionPolicy Bypass` ou assinatura.
- Filtro de regex no `logging` para senhas — não cobre `repr`, exceção nem tela.
- `taskkill /T /F` — segue a árvore por PID do pai e perde órfãos.
- PowerShell em volta de nativos para ter UTF-8 — corrompe a saída OEM.
- `QThread` por chamada ou `QProcess` — mais código, ou executor preso ao Qt (ADR-010).
- pywin32 ou `Set-Acl` para o ACL — dependência de ~10 MB, ou mais um processo e sem troca de dono.

**Consequences**
Todo backend migrado do Configurador passa pelo executor; `remoto.py` (`echo senha | anydesk`)
usa `entrada=Sensivel(...)`. Script PowerShell maior que ~12 000 caracteres precisa ser dividido.
`--dev` sem admin, depois de uma execução elevada, grava o log em `%LOCALAPPDATA%`.

---

## ADR-012 — Monorepo: a API do Técnico Assistente vem para `api/`, o app vai para `app/`

**Status:** Accepted (substitui o ADR-003)
**Date:** 2026-11-03
**Module:** 03

**Context**
O ADR-003 manteve a API em `ITC-Brasil/tecnico-assistente` (TA) e marcou com **[TA]** os módulos
que dependiam de PR lá. O responsável decidiu descontinuar o TA: a única parte viva é a `api/`
(FastAPI + SQLite no glpi-srv). O pendrive não está em uso. Login (ADR-005) e cadastros (ADR-006)
precisam de rotas novas na API, e manter dois repos para um só produto dobra PRs, CI e revisão.

**Decision**
1. **Monorepo.** `app/` (programa Windows: `pyproject.toml`, `uv.lock`, `.python-version`, `src/`,
   `tests/`) e `api/` (como no TA). São dois projetos separados, sem workspace uv: o app é Python
   3.13 e a API roda Python 3.12.14 no Docker, e um workspace uv impõe um `requires-python` e um
   lock comuns. A API mantém `requirements.in` + pip-compile (TA-ADR-025).
2. **Importação só de `api/`, com histórico.** `git filter-repo --path api/ --replace-text` num
   clone descartável da `main` do TA em `0bc5620d303fea2a0b56a27b03a6df3d2f0ae976` (PR #22, deploy
   verde nesse SHA), depois `git merge --allow-unrelated-histories`. Os hosts reais do histórico
   de `api/.env.example` (e, por garantia, os outros hosts e o usuário de deploy) viram
   `exemplo.invalid` antes do merge; a varredura por regex e o gitleaks 8.30.1 rodam na cópia
   reescrita e no histórico completo da branch. O PR para `develop` é por **merge commit**: squash
   apagaria o histórico importado.
3. **O pendrive fica fora.** Continua no TA arquivado, como referência do Diagnóstico (Módulo 06).
   Docs e ADRs do TA vêm como arquivos (sem histórico) para `docs/api/`, com os ADRs renomeados
   para `TA-ADR-NNN`.
4. **CI com um workflow por parte, filtrado por `paths`:** `app-ci.yml` (`app/**`), `api-ci.yml`
   (`api/**`), `api-deploy.yml` e `gitleaks.yml` (histórico inteiro, sem `paths`). Sai do CI da
   API a comparação da base de Event Log com a cópia do pendrive: a cópia de `api/app/` passa a
   ser a única, e a consequência do TA-ADR-022 que exigia as duas iguais deixa de valer.
5. **Deploy pelo itc-bench, sem parada e sem troca de dados.** Mesmo container (`tecnico-api`),
   mesmo projeto compose (nome fixo `tecnico-assistente`), mesmo volume, mesmo `.env`, mesmo
   domínio e mesmo diretório no glpi-srv; muda só o remote do clone. Secrets no environment
   `producao` do GitHub, restrito à `main`: os seis do TA mais **`DEPLOY_DIR`**, porque o caminho
   do clone revela o usuário de deploy. O script remoto recebe o diretório como argumento.
   Durante a transição o `api-deploy.yml` ficou só com `workflow_dispatch`; depois do primeiro
   deploy validado (2026-11-04) voltou o gatilho de `push` na `main` em `api/**`, mantido o manual.
6. **Acesso do servidor ao itc-bench por deploy key SSH só de leitura** (chave própria no
   servidor, diferente da `DEPLOY_SSH_KEY`), com o host do GitHub fixado no `known_hosts` do
   servidor pelas impressões digitais publicadas pelo GitHub. Sem PAT. O acesso usa o apelido
   de host `github-itc-bench` no `~/.ssh/config` (`HostName github.com`, `IdentityFile` da chave,
   `IdentitiesOnly yes`), porque o servidor hospeda outros projetos com deploy key própria: um
   bloco `Host github.com` genérico mudaria a chave usada por eles. Remote:
   `git@github-itc-bench:ITC-Brasil/itc-bench.git`.
7. **Transição do clone, manual e única:** `git remote set-url origin
   git@github-itc-bench:ITC-Brasil/itc-bench.git`, `git fetch origin main`, `git checkout -B main
   origin/main`. O `pull --ff-only` do workflow vale a partir do deploy seguinte. Rollback também
   manual (o `workflow_dispatch` do TA puxaria o remote novo). Passos em `docs/api/DEPLOY.md`.
8. **Renumeração do plano** (o ADR-011 não é editado; onde ele diz Módulo 04 para a subpasta
   DPAPI, leia-se 05):

   | Antes | Depois | Módulo |
   |---|---|---|
   | — | 03 | Migração da API para o monorepo |
   | 03 | 04 | Login e sessão |
   | 04 | 05 | Cadastros via API com cache DPAPI |
   | 05 | 06 | Diagnóstico |
   | 06–14 | 07–15 | Contas … Empacotamento |
   | 15 | 16 | Atualização automática |

   A marcação **[TA]** sai do plano. A nota do ADR-006 ("ADR correspondente no tecnico-assistente")
   passa a ser resolvida aqui, como TA-ADR novo ou ADR do Bench, no Módulo 05.

**Alternatives considered**
- `git subtree add --prefix=api` sem `--squash` — traz os 107 commits do TA, inclusive pendrive e
  docs com host, porta e usuário de deploy reais. Com `--squash`, perde o histórico.
- `filter-repo --to-subdirectory-filter api` do repo inteiro — geraria `api/pendrive/...` e os
  mesmos hosts.
- ADR de risco aceito para os hosts do histórico de `api/` — desnecessário: a cópia é local e
  descartável, reescrever não custa nada (ao contrário do caso do ADR-009).
- Workspace uv com os dois projetos — força a mesma versão de Python e mistura PySide6 no lock da API.
- PAT fine-grained para o clone do servidor (como no TA) — credencial de usuário com validade e
  escopo de conta; a deploy key é por repositório e só de leitura.
- Manter o gatilho de `push` no deploy já neste módulo — o merge `develop` → `main` dispararia um
  deploy antes da troca do remote.

**Consequences**
Comandos do app rodam de dentro de `app/` (`uv --directory app run …`); os da API seguem os do TA
(pytest no Docker, pip-compile). `api/` não usa ruff nem mypy, como no TA. O TA recebe só dois PRs
depois deste módulo (desligar o `push` do deploy antes da troca do remote; README apontando para
cá); arquivamento é do responsável. Com `paths`, um PR só de docs não roda os testes do app nem da
API; se algum dia esses checks virarem obrigatórios por branch protection, isso precisa de ajuste.

---

## ADR-013 — Login do técnico pela API, sessão de 12 h e offline de 7 dias com DPAPI de máquina

**Status:** Accepted
**Date:** 2026-11-04
**Module:** 04

**Context**
O ADR-005 decidiu o login pelo GLPI através da API e deixou para o Módulo 04 o caminho até a
API, as rotas, o escopo DPAPI e a pasta protegida do ADR-011. A borda exige o service token do
Cloudflare Access (TA-ADR-007) e o instalador só pode levar o endereço da API (ADR-008). Desenho
proposto e aprovado com ajustes em `.conversa/` em 04/11/2026.

**Decision**
1. **Borda.** Rotas do Bench sob `/v1/bench/` (`login`, `logout`, `sessao`, `saude`; cadastros no
   05). Uma aplicação do Cloudflare Access no mesmo hostname, caminho `/v1/bench/`, política
   Bypass; o resto (`/v1/relatorio`, `/v1/saude`) continua atrás do service token. Exceção ao
   TA-ADR-007 só para esse prefixo. Verificação com `curl`: `/v1/relatorio`,
   `/v1/bench/../relatorio`, `/v1/bench/%2e%2e/relatorio`, `//v1/relatorio` e `/v1/benchx` sem
   service token têm de ser barrados pelo Access ou cair em 404 na API.
   - **Proteção principal: o limite no SQLite** (item 3). A regra de rate limiting do plano Free
     só permite janela de 10 s e bloqueio de 10 s (Cloudflare WAF docs, *Rate limiting
     parameters*, consultado em 2026-11-04); ela fica como reforço: `/v1/bench/login`, por IP,
     5 requisições em 10 s → bloqueio 10 s.
   - IP do cliente: `CF-Connecting-IP`, lido só em `/v1/bench/*`; sem o cabeçalho, o IP da
     conexão. Confiável porque a porta só escuta em `127.0.0.1` (TA-ADR-009) e o único caminho é
     o túnel.
2. **GLPI.** API v2 (`/api.php`, habilitada no servidor, confirmado pelo responsável), OAuth2
   grant `password` com o cliente OAuth cadastrado no GLPI (`POST /api.php/token`, escopo `api`),
   depois `GET /api.php/v2/session` e o token é descartado. A legada (`initSession` +
   `App-Token`, `glpiprofiles` do `getFullSession`) fica só como reserva documentada. Arquivo
   único `api/app/services/glpi.py`: `autenticar(settings, usuario, senha, transport) -> Tecnico`
   (`glpi_id`, `login`, `nome`, `tem_perfil`), levanta `CredenciaisInvalidas` ou
   `GlpiIndisponivel`.
   - **Acesso pelo perfil do GLPI, nunca pelo grupo** (os grupos têm outra finalidade):
     `GLPI_PERFIL_TECNICOS_ID`, preenchido só no `.env` do servidor. Conta qualquer vínculo do
     usuário com o perfil, em qualquer entidade, não só o perfil ativo ou o padrão: o campo
     `profiles` de `GET /session` é o `$_SESSION['glpiprofiles']` (todos os perfis do usuário;
     `CoreController` do GLPI 11), e o `active_profile` é ignorado.
   **`GLPI_URL` é interna** (o próprio servidor ou a rede do Docker), nunca rota pela internet,
   porque o GLPI 11 está sem HTTPS: a API recusa no arranque `http://` para host que não seja
   `localhost`, IP privado, nome sem ponto ou `.internal`/`.local`/`.lan`/`.invalid` (log de erro e
   login em `503`).
3. **Rotas e dados.** `POST /v1/bench/login` → `200 {sessao, expira_em, tecnico}`,
   `401 credenciais_invalidas`, `403 fora_do_perfil` (só com senha certa; no Bench: "Usuário sem
   perfil de técnico no GLPI"), `429 limite_excedido`
   com `Retry-After`, `503 glpi_indisponivel` (inclui timeout e GLPI não configurado),
   `422 requisicao_invalida`. `POST /v1/bench/logout` → `204`. `GET /v1/bench/sessao` → `200` ou
   `401`. Sessão `itcbs_` + 43 caracteres, só SHA-256 no banco, validade **absoluta de 12 h**,
   sem renovação. Migração `0004`: `bench_sessoes`, `bench_login_tentativas`,
   `bench_login_auditoria`, sem coluna de senha. Limite em janela fixa de 15 min: 5 falhas por
   usuário e 20 por IP, conferido antes de chamar o GLPI; sucesso zera o usuário; `503` não conta.
   - **Usuário que pode ser senha:** auditoria e alerta ntfy gravam o usuário por extenso só
     quando o GLPI o reconhece (`ok` ou `fora_do_perfil`). Nos outros casos, e sempre na chave do
     limite, vai `HMAC-SHA256(BENCH_LOGIN_HMAC_KEY, usuario_normalizado)` (16 hex).
   - **Deploy sem parada:** toda variável nova tem padrão; com `GLPI_*` ou a chave HMAC vazios a
     API sobe e o login responde `503 glpi_indisponivel`.
4. **Token da carreta.** Separado: `itcbs_` diz quem, `itcta_` diz qual carreta. Proposta para
   o 06 (ADR próprio): `/v1/relatorio` aceitar a sessão e tirar o `itcta_` dos notebooks.
5. **Cliente.** `servicos/api.py`, stdlib (`urllib.request` + `ssl.create_default_context()`),
   timeout 15 s, **sem seguir redirecionamento**. Endereço: `HKLM\SOFTWARE\ITC\Bench\ApiUrl`
   (instalador, Módulo 15); em `--dev`, `ITC_BENCH_API_URL` antes. Resposta que não for JSON
   (302, HTML do Access) é `ErroApi`; um 403 em HTML nunca vira `fora_do_perfil`; 429 sem
   `Retry-After` tem mensagem genérica.
6. **Offline 7 dias.** Liberam o offline: sem conexão (DNS, recusa, timeout, TLS), 502, 503, 504
   e 530 da borda, e `503 glpi_indisponivel`. Nunca liberam: 401, 403, 429; 401/403 apagam a
   entrada do técnico. Guardado por técnico: login, nome, `scrypt(senha, sal 16 B, n=2^15, r=8,
   p=1, maxmem=64 MiB)`, último login online, maior horário visto, falhas offline. Expira 7 dias
   depois do último online; relógio voltado mais de 5 min recusa; 5 senhas erradas seguidas
   apagam a entrada.
   - **DPAPI escopo de máquina** (`CRYPTPROTECT_LOCAL_MACHINE`): o Bench roda elevado com contas
     de Windows diferentes; no escopo de usuário o offline sumiria a cada conta. Qualquer
     usuário local decifra DPAPI de máquina, por isso a proteção real é o ACL da pasta.
   - **Pasta protegida** `%ProgramData%\ITC\Bench\protegido\` (arquivo `logins.dpapi`), SDDL
     `O:BAD:PAI(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)`. Em toda execução elevada o Bench cria a pasta se
     faltar e, se já existir, **reaplica o ACL e confere o dono**, com a recusa de reparse antes e
     depois do ADR-011. Isto substitui, para a pasta protegida, a linha "leia-se 05" do ADR-012
     (que não é editado): a pasta nasce no 04 e o 05 a reusa.
   - **`--dev` sem administrador:** sem pasta protegida não há offline; o Bench avisa na tela
     Entrar, registra no log e não grava nada fora dela.
7. **Sessão na UI.** Sessão só em memória. Bloqueio após 15 min sem tecla, clique ou roda.
   - **Destravar:** o mesmo técnico destrava pelo verificador local (sem rede); outro técnico, ou
     o mesmo sem verificador (`--dev`), faz login completo. Tarefa em andamento continua e vai ao
     log.
   - **Sessão vencida em uso:** um `401` da API volta à tela Entrar; tarefa em andamento continua.
   - Logout no rodapé da barra lateral (`POST logout` em segundo plano).
8. **Log.** Formato `%(asctime)s %(levelname)s [%(tecnico)s] %(name)s: %(message)s`; `-` antes do
   login e depois do logout; offline sai como `login (offline)`.
9. **Senha.** `Sensivel` no Bench (ADR-011), `SecretStr` na API; o 422 não ecoa; `glpi.py` só
   registra status HTTP e tipo do erro.

**Riscos aceitos (responsável, 04/11/2026)**
- Técnico desligado no GLPI, sem rede, mantém o offline por até 7 dias naquela máquina.
- Senha trocada no GLPI continua valendo offline por até 7 dias até o próximo login online.

**Alternatives considered**
- Service token no instalador (compartilhado ou por máquina) — segredo extraível do EXE; fere o
  ADR-008.
- API legada do GLPI como primeira escolha — obsoleta; a troca para o 12 a obrigaria de novo.
- Grupo do GLPI (por nome ou id) — os grupos têm outra finalidade no GLPI do Grupo; o perfil é o
  que define o técnico. Perfil só ativo/padrão — técnico com o perfil numa entidade secundária
  ficaria de fora.
- Sessão deslizante — sessão roubada viveria indefinidamente.
- SHA-256 puro ou PBKDF2 no offline — força bruta rápida; scrypt resiste melhor a GPU.
- DPAPI escopo de usuário — some ao trocar a conta do Windows na bancada.
- httpx/requests no app — dependência e peso no EXE para quatro chamadas JSON.
- Suspender o bloqueio durante tarefas — máquina aberta durante instalações longas.

**Consequences**
O responsável faz, nesta ordem: deploy → `.env` (`GLPI_*`, `BENCH_LOGIN_HMAC_KEY`) → `restart` →
Access Bypass e rate limiting na Cloudflare → verificação com `curl`. A bancada precisa da
chave `ApiUrl` até o instalador existir.

---

## ADR-014 — Cadastros pela API em uma rota, cache DPAPI por unidade e tela Configurações só leitura

**Status:** Accepted
**Date:** 2026-11-04
**Module:** 05

**Context**
O ADR-006 fez do NocoDB a fonte dos cadastros (Servidores, Instaladores, WiFi, Unidades),
entregues pela API com cópia local DPAPI. O Wi-Fi (08) e o acesso remoto (09) são usados
justamente sem rede, e `Servidores.Valor` mistura dado público e segredo. Desenho proposto e
aprovado com ajustes em `.conversa/` em 04/11/2026. A revisão do TA-ADR-005 está no TA-ADR-027.

**Decision**
1. **Leitura do NocoDB** em `api/app/services/nocodb_cadastros.py`: `GET /api/v2/tables/{id}/records`
   com `fields` e paginação; ids de tabela pelo `.env` (`NOCODB_TABELA_SERVIDORES`,
   `NOCODB_TABELA_INSTALADORES`, `NOCODB_TABELA_WIFI`, `NOCODB_TABELA_UNIDADES`); token próprio
   `NOCODB_CADASTROS_TOKEN` de um usuário **Viewer só na base "ITC Bench"** (o NocoDB não tem
   escopo por token; risco residual: o token lê a base inteira, sem alterar nem apagar).
   Timeout de 5 s por requisição (`NOCODB_CADASTROS_TIMEOUT_SECONDS`), teto de 30 s na leitura.
   Descartados, com `Id` e motivo no log: `Ativo` diferente de `true`, campo de exibição vazio,
   `WiFi.Unidade` fora das Unidades ativas. Erro do NocoDB vira `NocodbIndisponivel` com motivo
   (`timeout`, `indisponivel`, `http_<status>`, `resposta_invalida`), nunca URL nem cabeçalho.
2. **Rota única** `GET /v1/bench/cadastros[?unidade=<codigo>]`, com `exigir_sessao`: `200` com
   `versao`, `lido_em`, `defasado`, `unidade`, os quatro cadastros e `descartados`; `ETag` e
   `Cache-Control: no-store`; `304` com `If-None-Match` igual (o `304` também exige sessão);
   `401`; `422 unidade_invalida` (código fora das Unidades ativas); `503 cadastros_indisponivel`.
   - **Filtro por unidade (ajuste do responsável):** sem `unidade`, todo o Wi-Fi (fase de
     bancada); com `unidade`, só o Wi-Fi dela. Servidores, Instaladores e Unidades são globais. Se
     um servidor passar a ser de uma unidade só, entra uma coluna `Unidade` opcional e o mesmo
     filtro. Isto substitui a regra de 03/11 do BACKEND-SCHEMA ("a API filtra as redes por
     unidade" sempre).
   - **`versao`** = HMAC-SHA256 do JSON canônico da resposta (com o filtro) com a chave
     `BENCH_CADASTROS_ETAG_KEY`; sem ela, chave aleatória por processo (o restart invalida o
     `304`, aceito). Não deriva só do conteúdo, porque o conteúdo tem segredos. Os logs da API e
     do Bench e a auditoria guardam só os 12 primeiros caracteres.
   - **Cópia em memória**, TTL 60 s (`NOCODB_CADASTROS_TTL_SECONDS`). **Uma leitura do NocoDB
     por vez:** quem pega o lock renova; os demais recebem a cópia existente e só esperam quando
     não há nenhuma. NocoDB fora com cópia: devolve a cópia com `defasado: true` por até 24 h;
     depois, `503`. Nada de cadastro vai para o SQLite.
   - **Auditoria** `bench_cadastros_entregas` (migração `0005`, a próxima livre depois da `0004`
     do 04): uma linha por `200` com sessão, usuário, unidade, horário e os 12 caracteres da
     versão; retenção de 90 dias, limpa a cada entrega, como a auditoria do login. Sem limite por
     sessão: a sessão roubada leva tudo na primeira chamada, e o NocoDB está protegido pelo TTL.
3. **Segredos.** Tudo sai depois do login (o uso é offline; segredo sob demanda quebraria o 08 e
   o 09). Coluna nova `Servidores.Publico` (Checkbox): só `true` sai como público; vazio, falso ou
   coluna ausente = segredo. Com `Publico` falso, `Valor` **e `Observacao`** são segredo (texto
   livre pode ter senha). WiFi: `Senha` sempre segredo; `SSID` visível na tela e fora do log
   ("sensível para log"). Na API, `SecretStr` até a serialização; no Bench, `Sensivel` (ADR-011).
   Log: contagens, versão curta, `Id`; nunca valor, SSID, link ou observação.
4. **Cache no Bench** `protegido\cadastros.dpapi` (DPAPI de máquina, pasta do ADR-013), escrita
   atômica (`.tmp` + `replace`), `{"formato": 1, versao, sincronizado_em, por, unidade, dados}`.
   Validade de 7 dias desde `sincronizado_em` (igual ao login offline); relógio voltado mais de
   5 min é tratado como vencido. Vencido ou corrompido: log, arquivo apagado, tela "conecte e
   sincronize"; os módulos recebem "sem cadastros". Logout e troca de técnico não apagam (o
   cadastro é da máquina). `--dev` sem admin: cache só em memória.
5. **Unidade da máquina** escolhida à mão em Configurações, gravada em
   `HKLM\SOFTWARE\ITC\Bench\Unidade` (exige admin; sem admin, só na sessão). Ao gravar ou trocar,
   o Bench ressincroniza com `?unidade=` e regrava o cache filtrado; offline, filtra o cache
   existente e regrava. O rodapé mostra o código se estiver nas Unidades do cache; senão "—".
6. **Sincronização:** depois do login online, botão "Sincronizar agora" e a cada 30 min com sessão
   online, sempre com `If-None-Match`. Sem servidor (`SemConexao`, 502/503/504/530) ou
   `503 cadastros_indisponivel`: mantém o cache e não mexe na sessão; o `503 cadastros_indisponivel`
   nunca é tratado como o `503 glpi_indisponivel` do login. `401`: volta à tela Entrar (ADR-013).
   Rodapé: "sincronizado HH:MM" (hoje), "sincronizado DD/MM HH:MM", "offline · dados de …" e "sem
   cadastros". Interface sem Qt em `servicos/cadastros.py`.
7. **Tela Configurações** (grupo Sistema), só leitura, abas Servidores, Wi-Fi, Instaladores e
   Unidades, segredos como `••••••••` sem botão de revelar (quem precisa ver, vê no NocoDB), "?"
   (ADR-007), "Sincronizar agora" e a escolha da unidade da máquina.

**Riscos aceitos (responsável, 04/11/2026)**
- Na fase de bancada (sem unidade gravada), o cache tem o Wi-Fi de todas as unidades.
- O token de leitura do NocoDB lê a base "ITC Bench" inteira, segredos inclusive.

**Alternatives considered**
- Uma rota por tabela — quatro versões e quatro sincronizações para dados usados juntos.
- Segredo só no momento do uso (rota por id) — quebra o uso offline, que é o caso principal.
- Separar segredo pelo texto de `Papel` — texto livre; um erro de digitação vaza na tela.
- `versao` = SHA-256 do conteúdo — derivada dos segredos e gravada num log legível por Usuários.
- Cópia dos cadastros no SQLite da API — segredo em mais um disco e no backup do volume.
- Apagar o cache no logout — a carreta sem rede perderia Wi-Fi e acesso remoto.
- Unidade pela tag do GLPI Agent — o agente só é instalado no 09, e precisa da unidade antes.
- Botão de revelar segredo — expõe a senha a quem está ao lado, sem uso que o Bench precise.

**Consequences**
O responsável cria `Servidores.Publico` e o usuário Viewer no NocoDB e preenche o `.env`. Os
módulos 08–10 leem por `servicos/cadastros.py` e recusam a ação quando falta cadastro (ADR-008).

---

## ADR-015 — Diagnóstico no Bench: coletores portados, laudo síncrono, fila DPAPI e renderização sem rich text

**Status:** Accepted
**Date:** 2026-11-04
**Module:** 06

**Context**
O Módulo 06 traz o pendrive do Técnico Assistente para o Bench (ADR-003, ADR-012). Os
coletores do pendrive são `.ps1` com menu, `Write-Host` e caminhos do pendrive; o ADR-011 já
rejeitou `-File`. O laudo vem da IA em Markdown, e o Módulo 05 achou texto externo interpretado
como rich text pelo Qt. Desenho aprovado com ajustes em `.conversa/` em 04/11/2026.

**Decision**
1. **Porte.** Cada coletor (processos, rede, eventlog, disco, bateria) é um trecho PowerShell
   curto em `recursos/coletores/*.ps1`, empacotado no EXE e executado por `executor.powershell`
   (`-EncodedCommand`, PS 5.1), que só coleta e devolve JSON compacto. Validação, ordenação,
   resumos e regras (APIPA, faixas de desgaste, estado SMART, agrupamento do Event Log, parse do
   `batteryreport.html`) ficam em Python. A varredura dos perfis em `C:\Users` é Python
   (`os.scandir`). `powercfg.exe` roda por `executar` com caminho absoluto; o HTML é apagado
   depois do parse. Catálogo de limpeza e correções ficam para o 13.
2. **Saída de coletor é não confiável:** tipos e tamanhos validados, teto por lista; JSON
   inválido, tempo esgotado ou cancelamento viram `status: "erro"` no módulo, sem derrubar a
   coleta.
3. **Formato `1.3`** (`docs/api/SCHEMA.md`): o envelope do 1.2 com `origem: "bench"`,
   `coletadoPor`, `envioId` (UUID4) e `unidade`; sem `usuarioExecucao`, `usuarioSessao` nulo,
   sem `itensLimpeza`. Grupos do Event Log saem sem classificação: a API classifica pela base
   única `api/app/eventlog-conhecidos.json`; o Bench leva só a lista de pares provedor+id para
   filtrar Avisos, conferida contra a base por teste.
4. **Saneamento antes da fila e do envio** (função pura): caminho `<letra>:\Users\<perfil>\…`
   vira `%PERFIL%\…`; nome de perfil local vira `<usuario>` só em palavra inteira, sem
   diferenciar maiúsculas, excluídos `Public`, `Default`, `Default User`, `All Users` e perfis de
   sistema; `contaLogon` fora de `LocalSystem`/`NT AUTHORITY\*`/`NT SERVICE\*` vira `<conta>`;
   `usuario` de itens de inicialização sai; `maioresArquivos` sem nome de arquivo (pasta de 2º
   nível, extensão, tamanho, data). Hostname, serial e MAC continuam (TA-ADR-023).
5. **Tamanho:** corpo acima de 480 KB é cortado (mensagens de evento, grupos além de 100,
   portas) com aviso. Um corpo 1.3 fica abaixo do 1.2 do pendrive, porque `itensLimpeza` e os
   nomes de arquivo saem; os números medidos ficam em `docs/modules/06-diagnostico.md`.
6. **Laudo síncrono** (TA-ADR-010/026): timeout de 105 s só nesta chamada. Idempotência por
   `envio_id` (TA-ADR-028) cobre o `524` da borda e o cancelamento da espera; `409
   em_processamento` faz o Bench esperar e tentar de novo.
7. **Renderização:** o Markdown do laudo vira `QTextDocument` montado só com
   `QTextCursor.insertText` (títulos, listas, parágrafos, negrito); nunca `setHtml`,
   `setMarkdown` nem `QLabel` em rich text. Link e HTML aparecem como texto; imagem vira o alt.
   Aviso fixo "Gerado por IA. Revise antes de abrir chamado."
8. **Fila offline** `protegido\fila-diagnostico.dpapi` (DPAPI de máquina, ADR-013), escrita
   atômica, `{"formato": 1, "itens": [...]}` com corpo já saneado; 10 itens e 14 dias; corrompida
   vira `fila-diagnostico.corrompida`; é da máquina (logout não apaga); `--dev` sem admin, só em
   memória. Reenvio depois do login online, a cada 30 min e por botão.
9. **Executor (estende o ADR-011):** `cancelar: threading.Event | None`; a espera é feita em
   fatias e, ao sinal, o job é encerrado como no timeout (`Resultado.cancelado`).
10. **Histórico** só da API, só do hostname da máquina (`GetComputerNameExW`), mais a fila local.

**Alternatives considered**
- `.ps1` do pendrive por `-File` — política de execução ou assinatura (ADR-011).
- WMI em Python (`wmi`/`comtypes`) — dependência nova, frágil para CIM de armazenamento.
- Envio + consulta posterior do laudo — rota e estado a mais para um caso que cabe no limite.
- `setMarkdown(MarkdownNoHTML)` — mantém links clicáveis e imagens que leem arquivo local.
- Cópia da base de Event Log no app — fere a cópia única (ADR-012).
- Apagar fila corrompida — perde a prova do defeito.

**Consequences**
O 13 reusa a varredura de disco e o envelope. Par novo na base de Event Log quebra o teste do
app até a lista derivada ser regenerada.

---

## ADR-016 — Diagnóstico enviado pela sessão do técnico; o token da carreta não vai aos notebooks

**Status:** Accepted (revisa o `IMPLEMENTATION-PLAN.md`, Módulo 06)
**Date:** 2026-11-04
**Module:** 06

**Context**
O item 4 do ADR-013 deixou para o 06 o envio do diagnóstico. `/v1/relatorio` exige o `itcta_`
e o service token da borda, que o Bench não tem (ADR-013). O `itcta_` num notebook seria segredo
de máquina, sem dono humano, legível por qualquer admin local. O plano dizia que tirar o token
seria "ADR novo, fora do escopo do 06"; o responsável aprovou trazê-lo para o 06 (04/11/2026).

**Decision**
- `POST /v1/bench/relatorio` e `GET /v1/bench/historico/{hostname}` com `exigir_sessao`, sob o
  Bypass já existente de `/v1/bench/`. Nada muda na Cloudflare nem nas rotas da carreta.
- Limite de 30 envios por hora **por técnico** (`BENCH_RELATORIO_LIMITE_HORA`).
- Auditoria: `diagnosticos.bench_usuario`, `bench_sessao_id`, `unidade` (validada pela API
  contra as Unidades ativas) e `carreta = 'BANCADA'`.
- O `itcta_` continua só nas carretas/pendrive. Os itens do plano 06 "token guardado com DPAPI"
  e "como o token chega à máquina" deixam de existir (riscados no plano com remissão a este ADR).

**Riscos aceitos (responsável, 04/11/2026)**
- Qualquer técnico com sessão lê o histórico (inclusive `relatorio_md`) de qualquer hostname,
  como a carreta hoje.

**Alternatives considered**
- `itcta_` em DPAPI no `protegido\` — distribuição e rotação por máquina, e ainda barrado pelo
  service token na borda.
- Service token no instalador — fere o ADR-008.

**Consequences**
Regras da API no TA-ADR-028. Deploy com backup obrigatório (migração `0006`).

---

## ADR-017 — Contas locais pelo executor, por SID, com conta Suporte vinda de Servidores

**Status:** Accepted
**Date:** 2026-11-05
**Module:** 07

**Context**
O Configurador gerencia contas por dois caminhos: `backend/contas.py` (PowerShell com dados em
`ITC_*`, padrão a seguir) e `backend/usuarios.py` (`net user` com `shell=True`, `wmic`, grupo
"Administradores" pelo nome, senha temporária fixa no código). A senha da conta Suporte vem de
`segredos.json` ao lado do EXE. Desenho proposto e aprovado com ajustes em `.conversa/` em
05/11/2026.

**Decision**
1. **Operações** em `servicos/contas.py` (sem Qt, o 13 reusa): listar, criar (com clone só de
   grupos), tornar administrador/padrão, trocar e remover senha, excluir (com ou sem perfil),
   aplicar conta Suporte, tornar todos administradores e remover administrador de todos (exceto
   Suporte). Saem: fluxo antigo de `usuarios.py`, cópia de pastas pessoais, `AutoAdminLogon` e
   chaves de OOBE (12/13 se pedidos).
2. **Execução:** só `executor.powershell()` (PS 5.1, `-EncodedCommand`), trechos fixos em
   `recursos/contas/*.ps1`; nome, SID e senha por `ITC_*`, senha como `Sensivel`. Grupos pelo
   SID (`S-1-5-32-544`, `S-1-5-32-545`); `Set-LocalUser -PasswordNeverExpires` no lugar do
   `wmic`. Membros do grupo por `Get-LocalGroupMember`, com fallback ADSI `WinNT://` (pelo nome
   do grupo resolvido do SID) quando ele falha com SID órfão/AzureAD. Timeouts: listagem 30 s,
   alteração 60 s, lote 120 s. Sem administrador (`--dev`): só leitura.
3. **Alvo por SID**, nunca por nome. Cada regra é checada em Python sobre uma leitura feita logo
   antes e de novo dentro do trecho PS que altera (`ERRO|<codigo>|<mensagem>`):
   - Administrador nativo (RID 500): nada.
   - Conta logada (token do Bench, donos de `explorer.exe`, `Win32_ComputerSystem.UserName`):
     não rebaixar, não excluir, não trocar nem remover senha (perderia o cofre de credenciais e
     as chaves EFS).
   - Suporte: o nome cadastrado **e** `Suporte`, sem diferenciar maiúsculas; só "Aplicar conta
     Suporte" mexe nela.
   - Último administrador local ativo: não rebaixar nem excluir. Membros de domínio/AzureAD não
     contam.
   - Perfil carregado: não excluir.
   - Contas Microsoft e membros de domínio/AzureAD: só leitura. RIDs 501/503/504 não aparecem.
4. **Nome** validado em Python: 1–20 caracteres, `^[\w][\w .-]{0,19}$`, sem ponto ou espaço no
   fim; reservados `Administrador`, `Administrator`, `Convidado`, `Guest`, `DefaultAccount`,
   `WDAGUtilityAccount`, `SYSTEM`, `Suporte` e o nome Suporte cadastrado, `CON`, `PRN`, `AUX`,
   `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`; o PS recusa nome de conta, grupo ou computador existente.
   Força de senha: a da política do Windows (o erro dele vai para a tela).
5. **Conta Suporte** em Servidores (ADR-014): contrato `Servico = "Conta Suporte"`,
   `Papel = "usuario"` com `Publico = true` e `Papel = "senha"` com `Publico` falso. Sem cache ou
   sem a senha, a ação recusa (ADR-008). Mais de uma linha ativa para o mesmo papel, ou a conta
   com esse nome sendo RID 500 ou conta Microsoft, também recusa. "Aplicar" cria (administrador,
   ativa, senha não expira) ou troca a senha, ativa e garante o 544. O Bench não guarda qual
   senha aplicou.
   **Emenda (05/11/2026, responsável):** com a Suporte logada, "Aplicar" é permitido; a
   confirmação avisa "Você está nesta conta. Senhas salvas no Windows desta conta (cofre de
   credenciais) serão perdidas." É a segunda exceção à regra da conta logada; as ações manuais
   continuam recusando a Suporte.
6. **Ações em lote** (preparação e manutenção):
   - *Tornar todos administradores:* contas locais ativas (fora RID 500/501/503/504 e contas
     Microsoft) entram no 544.
   - *Remover administrador de todos (exceto Suporte):* tira do 544 e garante o 545 em todas as
     contas locais menos a Suporte e o RID 500. Recusa se a Suporte não existir, estiver
     desativada ou fora do 544. **Exceção à regra da conta logada:** a conta logada também é
     rebaixada (vale na próxima entrada; a confirmação avisa).
   Confirmação com a lista de quem muda.
7. **Excluir:** digitar o nome; caixa "apagar a pasta" desmarcada; perfil carregado recusa; conta
   removida e depois `Remove-CimInstance` do `Win32_UserProfile` (falha vira aviso); tamanho do
   perfil com teto de tempo, senão "não calculado".
8. **Log:** técnico, ação, nome das contas afetadas e resultado. O log é local e o nome já é
   visível a qualquer usuário da máquina. Nunca senha nem caminho de perfil: falha e aviso vão ao
   log só pelo código (`ERRO|codigo`, tipo do `AVISO`, HResult do perfil); a mensagem do Windows,
   que costuma ter `C:\Users\<nome>`, só vai para a tela (emenda de 05/11/2026).

**Alternatives considered**
- Senha Suporte digitada pelo técnico — uma senha por máquina, sem rotação central.
- Rota própria na API para a Suporte — mesmo segredo, mais rota, e sem cache offline próprio.
- Senha aleatória por máquina (tipo LAPS) — precisa de cofre na API para o suporte recuperar.
- Cópia de pastas com senha temporária ou `CreateProfile` — dado pessoal copiado sem uso na
  preparação; nunca testada no Configurador.
- Proteger a conta "ITC" — não existe nas máquinas do Grupo (responsável).
- Hash do nome da conta no log — tira a trilha sem esconder nada de quem usa a máquina.

**Riscos aceitos (responsável, 05/11/2026)**
- A senha Suporte é a mesma em todos os notebooks; admin local com o cache a lê (como RustDesk e
  AnyDesk no ADR-014).

**Consequences**
O responsável cadastra as duas linhas `Conta Suporte` e troca a senha atual. O 13 chama
`servicos/contas.py` e, no fim da Preparação completa, pergunta se remove os administradores.

---

## ADR-018 — Identificação por `Rename-Computer` no executor e Wi-Fi pela `wlanapi.dll`, sem senha em disco

**Status:** Accepted
**Date:** 2026-11-05
**Module:** 08

**Context**
O Configurador renomeia com `Rename-Computer "{n}"` interpolado e instala Wi-Fi gravando um XML
com a senha em claro em `%TEMP%` e chamando `netsh wlan add profile` com `shell=True`; lê os
perfis pelo texto localizado do `netsh` e testa a internet com `ping 8.8.8.8`. Desenho proposto
e aprovado em `.conversa/` em 05/11/2026.

**Decision**
1. **Inventário.** Entram renomear e instalar Wi-Fi, reescritos. Saem a lista de redes local
   (ADR-014), o popup "sem internet" e o `ping`, e a leitura de perfis pelo `netsh`. Remover o
   Windows Terminal vai para o 10; reinício com retomada e contas por turno (`<PC>-<sufixo>`), para
   o 13.
2. **Nome do computador** (`servicos/identificacao.py`, sem Qt): o técnico digita o nome inteiro,
   sem padrão, aviso nem sugestão. Validação em Python: 1–15 caracteres, só `A–Z`, `0–9` e `-`,
   sem `-` no começo ou no fim, não só dígitos, fora da lista de nomes reservados da Microsoft,
   diferente de conta ou grupo local; convertido para maiúsculas. Igual ao ativo ou ao pendente:
   nada a fazer.
3. **Renomear** com `Rename-Computer -NewName $env:ITC_NOME -Force` pelo executor (decisão do
   responsável: o padrão do resto do Bench, com o erro do Windows legível). O trecho confere de
   novo o domínio e a conta/grupo com o mesmo nome. Domínio ou Azure AD
   (`Win32_ComputerSystem.PartOfDomain`, ou subchave em
   `HKLM\SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo`) recusa, sem ler texto do
   `dsregcmd`.
   Nome pendente lido de `...\ComputerName\ComputerName` contra `...\ActiveComputerName`; a tela
   mostra os dois e oferece "Reiniciar agora" (`shutdown.exe /r /t 10`, argumentos fixos) ou
   "Depois". A retomada fica no 13.
4. **O que depende do hostname:** o histórico do diagnóstico (ADR-016) passa ao nome novo depois
   do reinício; a ajuda manda renomear antes do diagnóstico. `HKLM\SOFTWARE\ITC\Bench\Unidade`,
   o cache DPAPI de máquina e o login offline não dependem do nome.
5. **`Unidades.Codigo`** = sigla do programa + número da UM com dois dígitos
   (`^[A-Z]{1,6}[0-9]{2}$`, até 8), o mesmo de `WiFi.Unidade`. Só documentado no
   `BACKEND-SCHEMA.md`; a API não muda (já recusa código fora das Unidades ativas).
6. **Wi-Fi pela `wlanapi.dll` por ctypes** (`nucleo/wlan.py`, lógica em `servicos/wifi.py`, os
   dois sem Qt), como `nucleo/dpapi.py`: listar interfaces e perfis, ler o perfil, gravar
   (`WlanSetProfile`, `dwFlags = 0` = todos os usuários, sobrescreve). Sem processo, arquivo,
   argumento ou `ITC_*`: a senha sai do `Sensivel` só para a chamada.
   **Exceção ao executor único do ADR-011.** Critério: chamar a API do Windows direto (ctypes)
   só quando passar por um processo exporia um segredo (senha em arquivo, argumento ou
   ambiente do filho); todo o resto continua no executor (o próprio renomear, item 3). Precedente:
   `nucleo/dpapi.py`, que cifra e decifra o cache por ctypes pelo mesmo motivo.
7. **XML do perfil** montado com `xml.etree.ElementTree`; SSID em `<hex>` (UTF-8) e `<name>`;
   só `WPA2PSK`/`AES` (WPA3 fora: incompatível com os notebooks, decisão do responsável).
   Senha: 8–63 ASCII imprimíveis (`passPhrase`) ou 64 hexadecimais (`networkKey`); vazia ou fora
   disso é erro de cadastro e a rede não é instalada (todas as redes têm senha).
8. **Situação** por rede: igual, senha diferente, ausente, senha não conferida (sem admin), senha
   inválida no cadastro. A comparação lê o perfil com `WLAN_PROFILE_GET_PLAINTEXT_KEY` (só com
   admin) e compara com `hmac.compare_digest` na mesma função; a chave lida não sai dela.
9. **Tela Wi-Fi:** filtros esta unidade / todas / instaladas no Windows; "Instalar N redes"
   (cancelamento entre redes, ADR-015). Sem "Testar conexão" (decisão do responsável na revisão
   do PR #27): as redes cadastradas são as das carretas e os notebooks são preparados no
   escritório, fora do alcance delas; a conexão é conferida na carreta, pelo Windows. Sem cache: "conecte por cabo ou por uma rede do Windows, entre e sincronize",
   com "Abrir redes do Windows" (`explorer.exe ms-availablenetworks:`). O Bench não tem campo de
   SSID nem de senha.
10. **Log:** nome do computador sim (antigo → novo); Wi-Fi só por `Id` do cadastro, contagens e
    código Win32; nunca SSID, senha ou XML. `--dev` sem admin: as duas telas só leem.

**Alternatives considered**
- `SetComputerNameExW` por ctypes — mesmo efeito, mas foge do padrão do executor.
- Validar o formato de `Unidades.Codigo` na API — um erro de digitação sumiria com a unidade.
- XML em `protegido\` apagado em `finally` — fica no disco se o Bench morrer no meio.
- PowerShell `Add-Type` com C# — compila com `csc.exe` e grava fontes em `%TEMP%`.
- Hash da senha dentro do PS, ou não comparar — `netsh key=clear` é texto localizado; sem
  comparar, o técnico não vê a senha antiga.
- Popup do Bench com SSID/senha digitados — repete o painel do Windows e passa a senha pelo Bench.
- `ping 8.8.8.8` — ICMP filtrado dá falso negativo.
- "Testar conexão" no Bench (`WlanConnect` e checagem da API) — no escritório a rede da carreta
  nunca está ao alcance (responsável).
- Senha vazia = rede aberta — todas as redes do Grupo têm senha (responsável).

**Consequences**
O responsável preenche `Unidades` no NocoDB no formato acordado e usa os mesmos códigos em
`WiFi.Unidade`. O 13 chama `servicos/identificacao.py` e `servicos/wifi.py`.
