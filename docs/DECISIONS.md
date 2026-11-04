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
2. **GLPI.** API v2 (`/api.php`), OAuth2 grant `password` com o cliente OAuth cadastrado no GLPI;
   lê o usuário e os grupos e descarta o token. A legada (`initSession` + `App-Token`) fica como
   reserva atrás da mesma interface, só se a v2 falhar no servidor. Arquivo único
   `api/app/services/glpi.py`: `autenticar(settings, usuario, senha, transport) -> Tecnico`, levanta
   `CredenciaisInvalidas` ou `GlpiIndisponivel`. Grupo pelo id (`GLPI_GRUPO_TECNICOS_ID`).
   **`GLPI_URL` é interna** (o próprio servidor ou a rede do Docker), nunca rota pela internet,
   porque o GLPI 11 está sem HTTPS: a API recusa no arranque `http://` para host que não seja
   `localhost`, IP privado, nome sem ponto ou `.internal`/`.local`/`.lan`/`.invalid` (log de erro e
   login em `503`).
3. **Rotas e dados.** `POST /v1/bench/login` → `200 {sessao, expira_em, tecnico}`,
   `401 credenciais_invalidas`, `403 fora_do_grupo` (só com senha certa), `429 limite_excedido`
   com `Retry-After`, `503 glpi_indisponivel` (inclui timeout e GLPI não configurado),
   `422 requisicao_invalida`. `POST /v1/bench/logout` → `204`. `GET /v1/bench/sessao` → `200` ou
   `401`. Sessão `itcbs_` + 43 caracteres, só SHA-256 no banco, validade **absoluta de 12 h**,
   sem renovação. Migração `0004`: `bench_sessoes`, `bench_login_tentativas`,
   `bench_login_auditoria`, sem coluna de senha. Limite em janela fixa de 15 min: 5 falhas por
   usuário e 20 por IP, conferido antes de chamar o GLPI; sucesso zera o usuário; `503` não conta.
   - **Usuário que pode ser senha:** auditoria e alerta ntfy gravam o usuário por extenso só
     quando o GLPI o reconhece (`ok` ou `fora_do_grupo`). Nos outros casos, e sempre na chave do
     limite, vai `HMAC-SHA256(BENCH_LOGIN_HMAC_KEY, usuario_normalizado)` (16 hex).
   - **Deploy sem parada:** toda variável nova tem padrão; com `GLPI_*` ou a chave HMAC vazios a
     API sobe e o login responde `503 glpi_indisponivel`.
4. **Token da carreta.** Separado: `itcbs_` diz quem, `itcta_` diz qual carreta. Proposta para
   o 06 (ADR próprio): `/v1/relatorio` aceitar a sessão e tirar o `itcta_` dos notebooks.
5. **Cliente.** `servicos/api.py`, stdlib (`urllib.request` + `ssl.create_default_context()`),
   timeout 15 s, **sem seguir redirecionamento**. Endereço: `HKLM\SOFTWARE\ITC\Bench\ApiUrl`
   (instalador, Módulo 15); em `--dev`, `ITC_BENCH_API_URL` antes. Resposta que não for JSON
   (302, HTML do Access) é `ErroApi`; um 403 em HTML nunca vira `fora_do_grupo`; 429 sem
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
- Grupo por nome — renomear o grupo abriria ou fecharia acesso.
- Sessão deslizante — sessão roubada viveria indefinidamente.
- SHA-256 puro ou PBKDF2 no offline — força bruta rápida; scrypt resiste melhor a GPU.
- DPAPI escopo de usuário — some ao trocar a conta do Windows na bancada.
- httpx/requests no app — dependência e peso no EXE para quatro chamadas JSON.
- Suspender o bloqueio durante tarefas — máquina aberta durante instalações longas.

**Consequences**
O responsável faz, nesta ordem: deploy → `.env` (`GLPI_*`, `BENCH_LOGIN_HMAC_KEY`) → `restart` →
Access Bypass e rate limiting na Cloudflare → verificação com `curl`. A bancada precisa da
chave `ApiUrl` até o instalador existir.
