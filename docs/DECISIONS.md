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

**Status:** Accepted (ferramenta de instalador decidida no ADR-025: Inno Setup)
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
Inno Setup ou WiX: decidido no ADR-025 (Módulo 15): Inno Setup. Versões de Python e PySide6
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

---

## ADR-019 — Acesso remoto pelo executor, instaladores com SHA-256 em `protegido\` e senhas fora de argumento

**Status:** Accepted
**Date:** 2026-11-05
**Module:** 09

**Context**
O Configurador instala GLPI Agent, RustDesk e AnyDesk com `shell=True`, a partir de instaladores
guardados ao lado do EXE ou baixados para `%TEMP%` sem conferência. Os segredos vêm de
`segredos.json`. A senha do RustDesk vai em argumento (`--password`) e a do AnyDesk por
`echo senha |`. A espera é feita com `sleep(10)`, e a versão é comparada como texto. Desenho
proposto e aprovado com ajustes em `.conversa/` em 05/11/2026.

**Decision**
1. **Inventário.**
   - Entram: GLPI Agent (instalar, reconfigurar, forçar inventário), RustDesk e AnyDesk
     (instalar, atualizar, reconfigurar).
   - Saem: a pasta Ferramentas, a URL do GLPI digitada pelo técnico, o TOML na conta de quem roda
     o programa, os `sleep`, o `--password` e o `echo`.
   - Energia vai para o 12; a "Manutenção geral" vai para o 13.
2. **Servidores** (contrato no molde do ADR-017; uma linha ativa por par):
   - `GLPI Agent`/`servidor`, público: URL `http(s)://` com host, sem espaço nem aspas.
     **`http://` é aceito provisoriamente**, com aviso na tela, até o GLPI estar em HTTPS.
   - `RustDesk`/`servidor`, público: nome DNS ou IPv4, sem porta (portas 21116 e 21117).
   - `RustDesk`/`chave`, não público: base64 de 44 caracteres. É a chave pública do servidor,
     distribuída a todo cliente; não é segredo forte, só não é exibida em Configurações.
   - `RustDesk`/`senha` e `AnyDesk`/`senha`, não públicos.
   - Linha ausente, vazia, duplicada, com `Publico` trocado ou com formato errado recusa aquele
     programa e diz qual par falta. O log recebe só `Id` e motivo.
3. **Tag do GLPI opcional** (hoje nenhuma regra do GLPI usa tag). Com `Unidades.TagGLPI`
   preenchida na unidade da máquina, entra `TAG=`, validada contra espaço e aspas. Sem unidade ou
   com a tag vazia, o agente é instalado sem `TAG=`, e a tela mostra "sem tag", sem bloquear. Em
   "Reconfigurar", tag vazia não apaga a tag já gravada. A tag não vai ao log.
4. **Instaladores** (`servicos/instaladores.py`, sem Qt, também usado pelo 10):
   - Linha ativa com `Programa` exatamente igual ao nome, `SHA256` de 64 hexadecimais, `Link`
     `https://` e extensão de `Arquivo` igual à esperada.
   - O arquivo fica em `%ProgramData%\ITC\Bench\protegido\instaladores\<sha256>.<ext>`, com o
     nome derivado do hash e nunca de `Arquivo`.
   - Download com `urllib`, só `https`, redirecionamento só para `https`, teto de 300 MB e
     cancelamento entre blocos. O hash é calculado durante a gravação em `.parcial`, que só vira o
     arquivo final se o hash bater.
   - "Escolher arquivo…" (pendrive, sem rede) copia o arquivo para `.parcial` e calcula o hash
     **sobre a cópia**, nunca sobre a origem.
   - O SHA-256 é conferido de novo logo antes de executar. Arquivo guardado com o hash certo é
     reaproveitado.
   - Hash diferente: o arquivo é apagado e a ação recusa. O log recebe `Id` e os 12 caracteres
     do hash esperado e do obtido; não há nova tentativa automática.
   - A limpeza apaga o que não corresponde a **nenhuma** linha ativa de Instaladores. Sem
     cadastros, nada é apagado.
   - O `Link` nunca vai ao log.
5. **Execução** só pelo executor (ADR-011), com lista de argumentos e caminho absoluto:
   - **GLPI Agent:** `msiexec.exe /i <msi> /quiet /norestart SERVER= [TAG=] ADD_FIREWALL_EXCEPTION=1
     RUNNOW=1`.
   - **RustDesk:** `msiexec.exe /i <msi> /qn /norestart` sem atalhos nem impressora.
   - **AnyDesk:** `<exe> --install <Program Files (x86)>\AnyDesk --start-with-win --silent`, sem
     ícone na área de trabalho. A pasta vem de `SHGetKnownFolderPath`.
   - Códigos do `msiexec`: 0 é sucesso; 3010 e 1641 são sucesso com reinício pendente (aviso, não
     falha); 1618 significa outra instalação em andamento (mensagem própria).
   - O instalador não é interrompido no meio (matar o cliente não para o Windows Installer). O
     cancelamento vale entre passos, no download e nas esperas. Timeout de 600 s.
6. **Espera:** um trecho PowerShell por espera, com polling de 1 s até 90 s (serviço existe e
   está `Running`; no RustDesk, também até o `RustDesk.toml` existir). Parar o RustDesk:
   `Stop-Service`, espera de `Stopped` e encerramento só dos `rustdesk.exe` da pasta instalada.
7. **Versão numérica:** a primeira sequência `\d+(\.\d+)*` do texto vira uma tupla de inteiros
   (cobre `ad 8.0.14`), lida em `DisplayVersion` das chaves `Uninstall` por `winreg`.
   - Ausente: instala.
   - Mais velha ou ilegível: instala por cima.
   - Igual: só "Reconfigurar".
   - Mais nova: não rebaixa; só "Reconfigurar", com "atualize o cadastro".
8. **Senhas fora de argumento:**
   - **AnyDesk:** `--set-password` com a senha na entrada padrão (`Sensivel`), sem shell nem
     `echo`.
   - **RustDesk:** sem o serviço rodando, o Bench grava só a linha `password` da seção de topo do
     `RustDesk.toml` do perfil do serviço
     (`%WINDIR%\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config`). O resto do arquivo
     é preservado (`id`, `key_pair`, `salt`). Ao iniciar, o RustDesk a regrava cifrada (prefixo
     `00`), e o Bench confere isso. Se sobrar texto puro, o Bench tira a linha e falha.
     **Emenda (10/11/2026, máquina real):** o RustDesk 1.5.1 regrava com prefixo `01`. O Bench
     aceitava só `00`, via "falha" e retirava a senha já cifrada. Passa a valer qualquer versão
     do formato (`0` + dígito + texto cifrado, `remoto.SENHA_CIFRADA`), sempre com a conferência
     de que o texto puro sumiu do arquivo.
   - Escritas atômicas (`.tmp` + `replace`), com o `.tmp` apagado em `finally`. A pasta (e o
     caminho até ela) não pode ser ponto de reparse.
   - O Configurador não gravava método de verificação; o padrão do RustDesk fica.
   - Não é exceção ao executor: gravar arquivo não abre processo.
9. **`RustDesk2.toml`:** o Bench grava `rendezvous_server`, `relay_server`, `nat_type`, `serial`
   e, em `[options]`, `custom-rendezvous-server`, `relay-server`, `key`, `direct-server` e
   `direct-access-port`, **preservando as outras chaves** de `[options]`. As strings são escapadas
   por `json.dumps` (string básica TOML válida). As opções `stop-service-hide-tray` e `hide-icon`
   vão por `rustdesk.exe --option` depois da gravação.
10. **Forçar inventário:** `GET http://127.0.0.1:62354/now`, o endpoint local do agente. Não abre
    processo e não fala com o GLPI. Reconfigurar o GLPI grava `server` e `tag` em
    `HKLM\SOFTWARE\GLPI-Agent` por `winreg` e reinicia o serviço.
11. **Tela e log:**
    - A tela mostra programa, versão (instalada e do cadastro), serviço e configuração conferida
      (servidor e tag do GLPI; servidor, chave por `hmac.compare_digest` e senha cifrada do
      RustDesk).
    - O ID do RustDesk e do AnyDesk (`--get-id`) aparece na tela.
    - Senhas e o valor da chave nunca aparecem.
    - O log recebe programa, versão, passo, resultado, código, `Id` e os 12 caracteres do hash.
      Nunca senha, chave, URL, host, tag, `Link` ou ID.
    - `--dev` sem admin: só leitura.

**Alternatives considered**
- `rustdesk.exe --password` — a senha aparece na linha de comando (`Win32_Process`, auditoria
  4688).
- Reescrever o `RustDesk.toml` inteiro — troca o ID e as chaves da máquina.
- Cópia do TOML no `%APPDATA%` — vai para a conta de quem roda o Bench, não para a do usuário.
- `glpi-agent.bat --force` via `cmd.exe /c` — regras de aspas do cmd com caminho com espaço.
- Hash sobre o arquivo de origem escolhido — a origem pode ser trocada entre a conferência e a
  cópia.
- Uma chamada ao executor por tentativa de polling — até 90 PowerShells.
- Deixar o serviço de instaladores para o 10 — duas versões do mesmo código.
- Rebaixar para a versão do cadastro — desfaz uma atualização sem motivo.

**Riscos aceitos (responsável, 05/11/2026)**
- A senha do RustDesk fica alguns segundos em texto puro numa pasta só de SYSTEM, LocalService e
  Administradores; a forma cifrada é reversível por admin local, como pelo `--password`.
- A aceitação da senha em texto puro pelo RustDesk não foi testada; é cenário obrigatório da
  máquina real. Se falhar, a decisão volta ao responsável.
- GLPI em `http://` até a migração para HTTPS.

**Consequences**
O responsável cadastra as cinco linhas de Servidores e as três de Instaladores e troca as senhas
do RustDesk e do AnyDesk. O 10 usa `servicos/instaladores.py` e a mesma pasta. O 13 chama
`servicos/remoto.py`.

## ADR-020 — Programas e Remover programas: lista única em Instaladores, winget e Web Apps sem shell, desinstalação por argumentos

**Status:** Accepted
**Date:** 2026-11-06
**Module:** 10

**Context**
O Configurador instala de uma pasta ao lado do EXE com `shell=True` (`.exe` sempre visual, código
de saída ignorado), roda o winget em texto com `--force` e, no erro, de novo sem `--source`; cria
Web Apps com um `.bat` (`start msedge --kiosk "{url}"`) e um `.vbs` em `%TEMP%`; desinstala
executando a `UninstallString` do registro com shell, troca `/I` por `/X` em qualquer lugar do
texto e faz "limpeza profunda" apagando pastas e entradas do registro por nome parcial. Desenho
proposto e aprovado com ajustes em `.conversa/` em 06/11/2026.

**Decision**
1. **Inventário.** Entram o lote de instaladores, o winget, os Web Apps (inclusive os jogos), a
   desinstalação e a remoção do Windows Terminal. Saem a pasta local de instaladores, as listas
   locais (`winget_db.json`, `webapps_db.json`, `games_db.json`), o `.bat`, o `.vbs`, o `--force`,
   o fallback sem `--source`, o `/I`→`/X` em texto e a limpeza de resíduos inteira. A lista de
   pré-instalados a remover vai para o perfil do Módulo 13; no 10 a seleção é manual.
2. **Lista única = a tabela `Instaladores`**, com seis colunas novas (TA-ADR-029):
   `Tipo` (`instalador`, `winget`, `webapp`; vazio = `instalador`), `Categoria` (`Programas`,
   `Jogos`; vazio = `Programas`), `Identificador` (ID do winget ou URL do Web App), `Argumentos`
   (um por linha, só instalador), `Deteccao` (opcional) e `Modo` (`quiosque`, `app`; só Web App;
   vazio = `quiosque`).
   - Obrigatórios: instalador = `Programa`, `Versao`, `Arquivo` `.exe`/`.msi`, `SHA256`, `Link`
     `https://` (regra do ADR-019); winget = `Identificador` no formato de ID; Web App =
     `Identificador` `https://` com host, ícone opcional (`Link` `https://` + `SHA256` + `Arquivo`
     `.ico`).
   - Duplicada (mesmo tipo e `Identificador`, ou mesmo `Programa` entre instaladores): as duas
     aparecem como "cadastro duplicado" e nenhuma instala.
   - `instaladores.do_cadastro` (Acesso remoto) considera só `Tipo = instalador`; GLPI Agent,
     RustDesk e AnyDesk não aparecem em Programas.
3. **Instaladores** pelo serviço do ADR-019 (download ou arquivo escolhido, SHA-256 sobre a cópia
   e antes de executar, `protegido\instaladores\`).
   - Cada linha de `Argumentos` é **um** item da lista do executor, validado por
     `^[A-Za-z0-9/_=.:+,{}-]+$` (sem espaço, aspas, `\`, `&|<>%^`); item inválido recusa o programa.
   - MSI: `msiexec.exe /i <arquivo> /qn /norestart` + `Argumentos` (só `PROPRIEDADE=valor`).
     EXE: `<arquivo>` + `Argumentos`; sem argumentos é interativo, com aviso na confirmação.
   - Códigos: `msiexec` como no ADR-019 (0; 3010/1641 reinício pendente; 1618 outra instalação).
     EXE: 0 ok, 3010 reinício pendente, outro falha.
4. **Winget.**
   - Executável: `InstallLocation` do pacote `Microsoft.DesktopAppInstaller` (lido pelo executor)
     + `winget.exe`, com assinatura Authenticode válida e assinante Microsoft conferidos antes do
     uso. O alias do perfil (`WindowsApps`) não é usado. Ausente: itens winget desabilitados com o
     motivo.
   - Comando fixo: `install --id <ID> -e --source winget --scope machine --silent
     --disable-interactivity --accept-package-agreements --accept-source-agreements`. Sem
     `--force`, `--ignore-security-hash`, `--version` nem nova tentativa em outra origem ou escopo.
     Pacote sem instalador de máquina falha com mensagem própria (o Bench roda como admin; escopo
     de usuário cairia no perfil do técnico).
   - Situação e versão: `winget export --source winget --include-versions` em JSON (não depende do
     idioma), arquivo temporário em `protegido\` apagado em `finally`.
   - Códigos `APPINSTALLER_CLI_ERROR_*` em tabela fechada; outro código vira falha com o hex.
   - **Risco aceito:** o Bench não confere SHA-256 do que o winget baixa; o winget confere contra o
     manifesto do repositório comunitário. Conferido pelo Bench: origem fixa, ID exato, escopo de
     máquina, `winget.exe` assinado pela Microsoft. Programa que precisa de hash nosso vai como
     `instalador`.
5. **Web Apps:** atalho `.lnk` no Desktop Público para `msedge.exe` (caminho de
   `HKLM\...\App Paths\msedge.exe`, dentro de `Program Files`).
   - Argumentos montados pelo Bench a partir de `Modo`: `quiosque` = `--kiosk <url>
     --edge-kiosk-type=fullscreen --no-first-run`; `app` = `--app=<url> --no-first-run`; valor
     desconhecido recusa a linha. URL `https://` com host, sem espaço, aspas nem controle.
   - Ícone baixado com SHA-256 e guardado em `%ProgramData%\ITC\Bench\icones\<sha256>.ico`,
     **local novo fora de `protegido\`** (o Explorer do usuário precisa ler). O Bench grava a ACL
     explicitamente: sem herança; Administradores e SYSTEM controle total; Usuários leitura e
     execução. `instaladores.limpar` trata também essa pasta com a mesma regra.
   - `.lnk` por trecho PowerShell fixo no executor (`WScript.Shell.CreateShortcut`), valores só por
     `ITC_*`. Descrição fixa "ITC Bench" marca os atalhos do Bench.
   - Nome do arquivo = `Programa` sem `\/:*?"<>|` e controles, sem `..`, até 60 caracteres, sem
     ponto ou espaço no fim, fora dos nomes reservados (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
     `LPT1`–`LPT9`). Atalho com o mesmo nome sem a descrição "ITC Bench" não é sobrescrito.
6. **Remover programas** (`servicos/desinstalar.py`).
   - Lista por `winreg`: `HKLM` 64 e 32 bits e `HKU\<SID>` dos perfis carregados. Pula
     `SystemComponent=1`, `ParentKeyName` e sem `DisplayName`.
   - MSI (chave `{GUID}` com `WindowsInstaller=1`): `msiexec.exe /x {GUID} /qn /norestart`; a
     `UninstallString` é ignorada.
   - EXE: `QuietUninstallString` (silencioso) ou `UninstallString` (interativo, avisado). Variáveis
     de `REG_EXPAND_SZ` expandidas. Caminho entre aspas até a aspa seguinte; sem aspas, o primeiro
     prefixo terminado em `.exe` em fronteira de espaço que existe como arquivo. O resto vai por
     `CommandLineToArgvW`; se `list2cmdline` da lista não reproduzir o texto original, o comando
     é recusado (o silencioso cai para o interativo, se este servir).
   - **Recusa:** não separável; não `.exe`; executável em lista fechada (`cmd`, `powershell`,
     `pwsh`, `rundll32`, `wscript`, `cscript`, `mshta`, `regsvr32`, `msiexec` fora do caso MSI);
     caminho final (depois de expandir, resolver `..`, junções e links) fora de `Program Files`,
     `Program Files (x86)` e `%WINDIR%`. `%ProgramData%` e perfis ficam fora: o usuário comum
     poderia trocar o executável que o Bench rodaria como admin.
   - **Locais por origem** (revisão do PR, 06/11/2026): a chave `Uninstall` de `HKU\<SID>` é
     gravável pelo próprio usuário. Entrada de HKU só roda executável em `Program Files` ou
     `Program Files (x86)`; `%WINDIR%` é recusado ("remova pelo Painel de Controle, entrando na
     conta do usuário"). MSI por `ProductCode` continua aceito, porque o `msiexec /x {GUID}` não
     leva nada do registro. Entrada de HKLM aceita `%WINDIR%` fora de uma lista fechada de
     subpastas graváveis por Usuários (`Temp`, `Tasks`, `tracing`, `Registration\CRMLog` e, em
     `System32` e `SysWOW64`, `Tasks`, `Tasks_Migrated`, `spool\drivers\color`,
     `spool\PRINTERS`, `spool\SERVERS`, `com\dmp`, `FxsTmp`,
     `Microsoft\Crypto\RSA\MachineKeys`). Foi escolhida a lista fechada, e não "só
     `System32`/`SysWOW64`", para não recusar desinstaladores legítimos em outras pastas de
     `%WINDIR%`.
   - Sem limpeza de resíduos; entrada cujo desinstalador não existe aparece como "desinstalador
     ausente", sem apagar.
   - **Protegidos**, com cadeado e motivo, sem seleção: ITC Bench, GLPI Agent, RustDesk, AnyDesk e
     prefixos fixos de driver e runtime (Visual C++, .NET, Windows Driver Package, Intel, Realtek,
     AMD, NVIDIA).
   - Atalhos "ITC Bench" do Desktop Público aparecem como "Atalho web" e só eles são apagados.
   - **Windows Terminal:** item fixo quando o pacote `Microsoft.WindowsTerminal` existe; trecho PS
     fixo remove o pacote de todos os usuários e o provisionado de mesmo nome exato, sem curinga.
7. **Execução e lote.** Só pelo executor, com descrição sem caminho nem URL. Timeout 900 s por
   instalador/desinstalador e 1800 s por winget. O executor ganhou `encerrar_no_timeout=False`:
   instalador, `msiexec` e winget **não são mortos** no timeout. O item fica "ainda em execução,
   confira depois" e o lote **pula os instaladores, winget e desinstalações seguintes** (todos
   podem usar o Windows Installer), seguindo só com Web Apps e atalhos. Cancelamento entre itens
   e no download; um falhou, os outros seguem; resumo no fim.
8. **Detecção.** Versão pela primeira sequência numérica (`nucleo/versao.py`, a do ADR-019):
   igual = instalado; mais velha ou ilegível = desatualizado; mais nova = não rebaixa.
   - MSI: `ProductCode` e `ProductVersion` lidos do próprio `.msi` guardado e conferido
     (`msi.dll` por `ctypes`), procurado em `Uninstall\{ProductCode}`; sem o arquivo guardado, cai
     na regra do EXE.
   - EXE: `Deteccao`, ou `Programa`, como prefixo do `DisplayName` (regra do 09).
   - Nenhum = "não instalado"; mais de um = "ambíguo" (instala se pedido, com aviso).
   - winget pelo `export`; Web App pelo `.lnk` "ITC Bench".
9. **Tela e log.** Por item: programa, origem, categoria, situação, versões e motivo de bloqueio.
   O log recebe programa, tipo, `Id`, versão, passo, resultado, código, 12 caracteres do hash e o
   ID do winget. Nunca `Link`, URL do Web App, caminho de perfil, nome de usuário, SID nem a
   `UninstallString` (só o nome do executável e o modo). `--dev` sem admin: só leitura.
10. **Serviços sem Qt** para o 13: `servicos/programas.py` e `servicos/desinstalar.py`.

**Alternatives considered**
- Tabela nova "Programas" no NocoDB — mais um token e variável, e o 09 leria outra tabela para o
  mesmo conceito.
- Lista em arquivo no app — muda só com release, contra o ADR-006.
- Parâmetros em texto livre separados por espaço — volta a interpretar linha de comando vinda do
  cadastro.
- Manter `--force` e o fallback sem `--source` — mascaram "já instalado" e podem trazer outro
  pacote da msstore.
- `IShellLinkW` por `ctypes` — vtable à mão para o mesmo resultado do trecho PS com `ITC_*`.
- Ícone em `protegido\` — o Explorer do usuário não lê.
- Limpeza de resíduos por lista fechada de pastas — manutenção por programa sem ganho; por nome
  parcial, já apagou o que não devia.
- Esconder programas protegidos — o técnico acharia que o Bench não os viu.
- Matar o instalador no timeout — o Windows Installer continua e o próximo MSI pega 1618.

**Riscos aceitos (responsável, 06/11/2026)**
- Pacotes do winget sem SHA-256 do Bench (item 4).
- Desinstalador interativo é programa do fabricante, executado como admin, de pasta só gravável
  por admin.
- Perfis não carregados não aparecem na lista de remoção.

**Consequences**
O responsável cria as seis colunas em Instaladores, cadastra as linhas e faz o deploy da API
antes do app novo. O 13 escolhe programas pelo serviço.

## ADR-021 — Políticas e USB: catálogo fechado no código, escrita no hive do usuário-alvo e bloqueio de armazenamento removível

**Status:** Accepted
**Date:** 2026-11-06
**Module:** 11

**Context**
O Configurador grava 13 políticas por `winreg` no `HKEY_CURRENT_USER` do processo elevado (o
parâmetro de hive de outro usuário existe, mas ninguém o passa), então as políticas de usuário
caem na conta que elevou, não na do aluno. A situação vem de `gpo_prefs.json`, não do registro.
Desfazer apaga o valor, inclusive `SharedAccess\Start`, o que tira a configuração do serviço.
Um `.bat` com `%USERNAME%` interpolado e `-ExecutionPolicy Bypass` e um `.ps1` gerado por texto
ficam ocultos na pasta Inicializar de todos os usuários para reaplicar no logon. "USB" no
Configurador é copiar uma pasta para pendrives. Desenho proposto e aprovado com ajustes em
`.conversa/` em 06/11/2026.

**Decision**
1. **Catálogo fechado no código** (`servicos/politicas.py`, `CATALOGO`):
   - Cada política tem id estável, nome, descrição, grupo, escopos (`usuario`, `maquina`),
     valores (chave relativa, nome, tipo, dado, valor de desfazer) e as edições em que o efeito
     não está confirmado.
   - O Módulo 13 escolhe políticas só por id. Sem NocoDB e sem mudança na API.
   - **Raízes aceitas,** conferidas no Python (teste) e de novo no PowerShell:
     - usuário: `Software\Policies\` e `Software\Microsoft\Windows\CurrentVersion\Policies\`;
     - máquina: `SOFTWARE\Policies\` e a chave exata
       `SYSTEM\CurrentControlSet\Services\SharedAccess`.
2. **Políticas:**
   - **Usuário:** Prompt de Comando (`DisableCMD = 2`, deixa `.bat` de terceiros), Regedit,
     Painel de Controle, Adicionar/Remover (só o painel antigo), aba Temas, ponteiros do mouse.
   - **PowerShell pelo Explorer:** `DisallowRun = 1` e `ITCBench1..3` (`powershell.exe`,
     `powershell_ise.exe`, `pwsh.exe`).
     - O valor legado do Configurador `DisallowRun\1` com dado exatamente `PowerShell.exe` (sem
       diferenciar maiúsculas) conta na situação e é apagado no desfazer.
     - `DisallowRun` só é apagado quando a lista fica vazia.
   - **Máquina:**
     - compartilhamento de conexão (`NC_ShowSharedAccessUI = 0`);
     - Wi-Fi Direct;
     - ICS (`SharedAccess\Start = 4`; desfazer grava `3`, Manual). O ICS fica no registro, e não
       em `Set-Service`: é o mesmo valor, pelo mesmo caminho das outras políticas, e o serviço
       em execução para no próximo reinício.
   - **Usuário e máquina:** Microsoft Store (`RemoveWindowsStore = 1`, efeito documentado só no
     Enterprise e no Education) e armazenamento removível (`RemovableStorageDevices\Deny_All = 1`).
   - **Saem:** wallpaper e estilo (vão para o 12). "Ocultar unidade C:" não entra.
3. **USB** = bloquear ("Desabilitar") e liberar ("Habilitar") armazenamento removível por
   `Deny_All`, que cobre disco removível, CD/DVD, WPD/MTP e fita.
   - Por usuário, no hive do aluno: deixa Suporte e técnico usarem pendrive.
   - Na máquina: bloqueia todos.
   - Liberar apaga só `Deny_All`. Sem cópia para pendrive e sem `servicos/usb.py`.
4. **Alvos:** "Máquina", "Contas futuras" (Default User) e as contas de `contas.listar()`,
   sempre por SID.
   - Hive carregado: escreve em `HKU\<SID>`.
   - Perfil não carregado ou Default: chamadas separadas do executor. O trecho carrega o
     `NTUSER.DAT` em `HKU\ITCBench_<8 hex>`, escreve ou lê, e descarrega.
     - O descarregar roda num `finally` do Python, sem cancelamento, até 3 tentativas.
     - O caminho do perfil é lido pelo trecho em `ProfileList` e conferido (`%SystemDrive%\Users\`,
       sem perfil `TEMP`, arquivo existente). O Python nunca recebe esse caminho.
     - Antes de cada leitura ou aplicação, `HKU\ITCBench_*` que tenham sobrado são descarregados.
   - **O processo Python nunca abre `HKU\ITCBench_*`.** O serviço não importa `winreg`.
   - **Leitura só em 64 bits:** toda leitura é pelo trecho, em `RegistryView.Registry64`. O
     PowerShell é o de `System32`, e o serviço recusa rodar em Python de 32 bits (sem
     `WOW6432Node`).
   - Há teste para cada regra.
5. **Recusas** (Python e de novo no trecho):
   - Administrador nativo (RID 500);
   - conta Suporte;
   - conta dona do processo elevado ("é a conta que está rodando o Bench");
   - conta sem perfil.

   Conta administradora é aceita com aviso.
6. **ACL:**
   - **Criação:** a primeira chave que faltar no caminho é criada com
     `O:BAG:SYD:PAI(A;CI;KA;;;SY)(A;CI;KA;;;BA)(A;CI;KR;;;BU)`, e as de baixo herdam. Dono:
     Administradores; Usuários só leem.
   - **Default User:** as chaves `Policies` do perfil padrão vêm com a mesma forma (SY/BA total,
     Usuários leitura).
     - Na criação da conta, o Windows copia o hive e só dá controle à raiz.
     - Chave com ACL protegida mantém dono BA e Usuários leitura: a conta nova só lê.
     - Cenário da máquina real.
   - **"O usuário pode alterar":**
     - Vale para a chave mais próxima que exista, até a raiz de política.
     - Aparece quando o dono dela é o SID-alvo, ou quando ela dá escrita a ele, a Todos, a
       Usuários autenticados, a Interativo ou a Usuários (e a Administradores, se a conta for
       admin).
     - O Bench só avisa; não troca ACL existente.
7. **Máquina:** registro direto pelo executor. A tela diz que vale no próximo logon.
   - Sem `Registry.pol`/LGPO.
   - Sem `gpupdate`: ele só sobrescreve o que a GPO local também configura, e nesse caso a
     situação mostra "diferente".
   - Sem `WM_SETTINGCHANGE`: seria ctypes fora do critério do ADR-018 e não alcança outra sessão
     nem hive descarregado.
8. **Edição:** `EditionID` lido pelo trecho.
   - Efeito não confirmado: no Home, para as políticas de máquina e o USB; no Home e no Pro,
     para a Store.
   - Nesses casos a tela mostra "efeito não confirmado nesta edição", e a política pode ser
     aplicada.
   - Só vira cadeado o que o teste na máquina real confirmar sem efeito.
9. **Sem reaplicação no logon** (confirmado pelo responsável): as chaves de política no hive do
   aluno só são graváveis por admin.
   - Sobras do Configurador: os dois arquivos de nome fixo `itc_security_check.bat` e `.ps1` na
     pasta Inicializar de todos os usuários, sem curinga.
   - A tela Políticas as mostra com "Remover".
10. **Situação** por política × alvo:
    - aplicada;
    - não aplicada;
    - diferente (outro valor, legado ou parcial);
    - não lida (perfil descarregado, até "Ler");
    - e o alerta "o usuário pode alterar".

    **Desfazer = padrão do Windows**, sem guardar o valor anterior. Aplicar é idempotente.
11. **Executor:**
    - Trechos fixos em `recursos/politicas/`. Variáveis:
      - `ITC_HIVE`: regex de SID, `MAQUINA` ou `ITCBench_[0-9a-f]{8}`;
      - `ITC_OPERACOES`: JSON montado só do catálogo e revalidado no trecho.
    - Erros do trecho só como código: a mensagem de `reg load` pode trazer caminho de perfil.
    - **Granularidade:**
      - uma chamada de escrita por alvo, com todas as políticas escolhidas para ele;
      - a chamada nunca é cancelada no meio: o cancelamento vale entre alvos ("Cancelar depois
        deste passo");
      - timeout de 60 s;
      - falha num alvo não para o lote.
12. **Log:** `Políticas: <aplicar|desfazer> alvo <maquina|padrao|usuario n> politica=<id>
    resultado=<ok|erro> codigo=<c>`. Nunca nome de conta, SID, caminho de perfil nem nome do
    hive temporário.
13. **Telas:**
    - **Segurança › Políticas:** alvo; tabela por grupo com situação; aplicar e desfazer;
      confirmação do que muda; cancelamento; sobras do Configurador; "?".
    - **Segurança › USB:** a mesma lógica, só com o armazenamento removível e os botões
      Habilitar/Desabilitar.
    - **`--dev` sem admin:** só leitura. O trecho lê HKLM e os hives que o usuário pode ler.

**Alternatives considered**
- Catálogo no NocoDB ou em arquivo — escrita arbitrária no registro como admin a partir de
  cadastro, ou um formato a mais para validar sem ganho.
- `USBSTOR\Start = 4` — bloqueia o técnico também e não é política.
- Cópia para pendrive — o Explorer faz; mexe em mídia externa e não protege a máquina.
- Tarefa agendada ou `Run` no logon — superfície a cada logon para um problema que deixa de
  existir com a escrita no hive certo.
- Guardar o valor anterior — estado a mais, e o anterior pode ser de outra ferramenta.
- `winreg` no Python para ler — não lê ACL e abriria o hive temporário.
- LGPO/`Registry.pol` — binário externo ou formato próprio; `gpedit` não existe no Home.
- Cadeado por edição sem teste — esconderia política que pode funcionar.

**Consequences**
Sem passos do responsável (sem API, NocoDB nem `.env`). Os cenários de escrita (Default User,
perfil descarregado, Home/Pro, Windows em inglês) ficam para a máquina real com o instalador.

---

## ADR-022 — Proteção do login, papel de parede, mouse e teclado e energia sem conta errada e sem shell

**Status:** Accepted
**Date:** 2026-11-06
**Module:** 12

**Context**
O Configurador grava papel de parede, ponteiros, velocidade do mouse e as flags do Shift 5x no
`HKEY_CURRENT_USER` do processo elevado (a conta que elevou, não a do aluno), chama
`SystemParametersInfo` na mesma conta, roda `powercfg` com `shell=True` e restaura energia com
`-restoredefaultschemes`. A proteção do `utilman.exe`/`sethc.exe` usa `takeown` e `icacls`, mas
troca a ACE de Administradores, nega também a leitura ao SYSTEM e lê a situação pelo texto
`(DENY)` do `icacls`. Resolução e escala usam ctypes, e a escala usa uma API não documentada.
Desenho proposto e aprovado com ajustes em `.conversa/` em 06/11/2026.

**Decision**
1. **Inventário.** Entram proteção do login (reescrita), detecção de troca e de IFEO, papel de
   parede por política, mouse e teclado por alvo e energia. Saem resolução, frequência e escala
   (fica só "Abrir configurações de vídeo", `explorer.exe ms-settings:display`), todo
   `SystemParametersInfo`, `-restoredefaultschemes`, a troca para Alto desempenho, a lista de
   hashes de intrusos e a tela de bloqueio. Sem exceção nova ao executor.
2. **Proteção do login** (`servicos/protecao.py`, `recursos/protecao/`):
   - **Proteger** = uma ACE `(D;;FX;;;SY)` (nega só execução ao SYSTEM) no `utilman.exe` e no
     `sethc.exe`, pelo executor: `takeown.exe /f <arq> /a` → `icacls.exe <arq> /deny
     *S-1-5-18:(X)` → `icacls.exe <arq> /setowner *<SID do TrustedInstaller>`. Desproteger troca o
     passo do meio por `/remove:d *S-1-5-18`. O `setowner` roda sempre, mesmo se o passo do meio
     falhar, e nunca é cancelado. O resto da ACL não muda. Proteger só roda com o binário
     "original".
   - **Detecção** dos 7 binários de acessibilidade da tela de login (`utilman`, `sethc`, `osk`,
     `Magnify`, `Narrator`, `DisplaySwitch`, `AtBroker`):
     - **original** = `Get-AuthenticodeSignature` `Valid` com `IsOSBinary` e `OriginalFilename`
       (sem `.mui`) numa lista fechada por exe. Conferido no Windows 11: `utilman.exe` →
       `utilman2.exe`, `Magnify.exe` → `ScreenMagnifier.exe`, `Narrator.exe` → `SR.exe`; os
       outros, o próprio nome;
     - **trocado** = `NotSigned`/`HashMismatch`/`NotTrusted`, não é binário do Windows, ou outro
       `OriginalFilename` (um `cmd.exe` copiado é assinado pela Microsoft, mas tem outro nome
       original);
     - **não lida** = `CryptSvc` parado, `UnknownError` ou exceção. Nunca "trocado" sem a
       verificação ter rodado.
     - **IFEO:** `Debugger` na chave do exe ou em qualquer subchave dela, com ou sem
       `UseFilter` (no filtro por caminho, `UseFilter = 1` fica na chave do exe e a subchave tem
       `FilterFullPath` + `Debugger`; revisão do PR #35); `SilentProcessExit\<exe>\MonitorProcess`. Só 64 bits.
     - **ACL:** protegido, não protegido, dono diferente do TrustedInstaller.
   - **Shift 5x na tela de login:** `Flags` de `StickyKeys`/`Keyboard Response`/`ToggleKeys` em
     `HKU\.DEFAULT` (`506`/`122`/`58`; desfazer `510`/`126`/`62`). Nas contas, pelo Mouse e teclado.
   - **Incidente** (confirmação dupla, aviso para abrir chamado e trocar as senhas):
     - "Remover depurador" apaga só `Debugger`/`MonitorProcess` nas chaves e subchaves dos 7 exes
       fixos;
     - "Restaurar original" roda `sfc.exe /scanfile=<arq>` e detecta de novo (o código do `sfc`
       não decide); a tela oferece proteger de novo.
   - **O que cobre:** troca offline por sobrescrita. **Não cobre:** apagar/renomear e copiar outro
     arquivo (herda a ACL da pasta), IFEO gravado offline, e a atualização cumulativa que troca o
     binário (a proteção some). Nesses casos a detecção mostra. "Não protegido" aparece claro na
     tela e em `situacao()`, que o Início do 13 usa para o alerta. A defesa contra ataque offline
     é BitLocker + senha de BIOS + boot só pelo disco (fora do escopo; recomendado na ajuda).
   - **O que quebra:** na tela de login, o botão de Acessibilidade, Win+U e o Shift 5x. Dentro da
     sessão continuam (o processo roda como o usuário).
   - Fora do Diagnóstico: mudaria o contrato 1.3 da API.
3. **Papel de parede** (`servicos/papel_de_parede.py`):
   - **Origem:** Instaladores com `Tipo = papel` (`Arquivo` `.jpg`/`.jpeg`/`.png`, `SHA256`, `Link`
     `https://`; TA-ADR-030), baixado pelo `instaladores.obter` ou "Escolher arquivo…" com o hash
     calculado sobre a cópia e conferido contra o cadastro. Os outros consumidores de
     Instaladores ignoram `papel` (Programas, Remover programas, Acesso remoto, `do_cadastro`).
   - **Pasta** `%ProgramData%\ITC\Bench\papel\<sha256>.<ext>`, ACL explícita sem herança (SY/BA
     total, Usuários leitura e execução, critério do ADR-020), reaplicada a cada uso: pasta
     existente com dono ou ACL diferentes é corrigida; ponto de reparse recusa. `limpar` cobre a
     pasta e nunca apaga a imagem de linha ativa.
   - **Validação:** até 20 MB, assinatura de bytes (JPEG/PNG) igual à extensão, dimensões do
     cabeçalho entre 640×480 e 7680×4320.
   - **Aplicação:** `...\Policies\System\Wallpaper` e `WallpaperStyle` (Preencher `10`, Ajustar
     `6`, Estender `22`, Centralizar `0`) por alvo, pelo hive do 11 (contas e Contas futuras,
     mesmas recusas). Vale no próximo logon. Desfazer apaga só esses dois valores, nunca a chave.
   - **Única exceção ao "valor fixo" do ADR-021:** o caminho da imagem não é fixo no código. O
     único produtor é `papel_de_parede.caminho()`, a partir do SHA-256 do cadastro; o trecho só
     grava se casar com `^<ProgramData>\ITC\Bench\papel\[0-9a-f]{64}\.(jpg|jpeg|png)$`
     (ProgramData lido no trecho) e o arquivo existir.
4. **Hive comum** (`servicos/hive.py`): carregar, ler, escrever, descarregar e o laço por alvo
   saem de `politicas.py` sem mudar o comportamento do 11. O trecho recebe `ITC_PERFIL`
   (`politicas` | `aparencia`), e as raízes ficam fixas no `comum.ps1`:
   - `aparencia`: chaves exatas de mouse, teclado, cursores e acessibilidade; em
     `...\Policies\System`, só os **valores** `Wallpaper` e `WallpaperStyle`.
   - Chave criada sob raiz de política recebe a ACL do ADR-021; chave de preferência só herda
     (o aluno continua podendo mudar). Tipos nativos: `REG_SZ` em `Control Panel`,
     `REG_EXPAND_SZ` nos caminhos de cursor, `REG_DWORD` em `Accessibility`.
5. **Mouse e teclado** (`servicos/aparencia.py`), por alvo, numa lista fechada:
   - ponteiro: branco, preto ou invertido × normal, grande ou extra grande, com arquivos de
     `%SystemRoot%\cursors`;
   - velocidade 1–20;
   - duplo clique 200–900 ms;
   - botões invertidos;
   - atraso e velocidade de repetição do teclado;
   - atalho Shift 5x.

   Desfazer = padrão do Windows. Situação: padrão, ajustado (com o valor), diferente, não lida.
   Vale no próximo logon.
6. **Energia** (`servicos/energia.py`):
   - **Esquema:** o ativo, sem trocar.
   - **Escrita:** `powercfg.exe` com aliases (`SCHEME_CURRENT`; `SUB_VIDEO VIDEOIDLE`,
     `SUB_SLEEP STANDBYIDLE`, `SUB_SLEEP HIBERNATEIDLE`, `SUB_DISK DISKIDLE`), AC/DC, depois
     `/setactive SCHEME_CURRENT`. Lista fechada: Nunca, 5, 10, 15, 30, 60 min.
   - **Leitura:** `powercfg /query`, só os dois últimos `0x…` (AC, DC), sem texto.
   - **Desfazer:** volta ao padrão do esquema (`Power\User\Default\PowerSchemes`, fallback
     `PowerSettings\...\DefaultPowerSchemeValues`); sem padrão, não mexe.
   - **Hibernação:** `/hibernate off|on`, lida de `HibernateEnabled`. A tela mostra a atual, e a
     confirmação do desfazer avisa que volta para ligada.
   - Tampa e botão de energia ficam para depois (alias `SUB_BUTTONS`, lista fechada).
7. **Executor:** trechos fixos com `ITC_*` e erros só como código; nativos por caminho absoluto.
   - Proteção: uma chamada por passo e arquivo, cancelamento entre arquivos.
   - Aparência: uma escrita por alvo, como no 11.
   - Energia: cancelável entre chamadas.
   - Timeout 60 s (`sfc`, 600 s). Falha parcial não para o lote.
8. **Log:** item, escopo, resultado e código. Nunca nome de conta, SID, caminho de perfil, hive
   temporário ou caminho da imagem (só `Id` e 12 caracteres do hash).
9. **Telas:** Segurança › Proteção do login; Aparência › Tela e papel de parede, Mouse e teclado,
   Energia. Confirmação do que muda, "Cancelar depois deste passo", "?" com ajuda, `--dev` só
   leitura. Serviços sem Qt, por id, para o 13.

**Alternatives considered**
- ACL negando leitura e execução (Configurador) — o Defender, o `sfc` e o servicing leem como
  SYSTEM.
- Lista de SHA-256 legítimos ou de intrusos — muda a cada build; só pega o que lista.
- Assinatura pelo texto do certificado — `IsOSBinary` confere a cadeia até a raiz do Windows.
- `SystemParametersInfo` — o processo elevado é de outra conta.
- Papel de parede só por "Escolher arquivo…" ou recurso do app — o 13 não reproduz; a imagem
  não entra no repo.
- Resolução e escala por ctypes com confirmação — fora do critério do ADR-018 e API não
  documentada; o Windows já escolhe a resolução nativa.
- WMI `root\cimv2\power` para ler energia — falha em algumas máquinas com Modern Standby.
- `-restoredefaultschemes` — apaga esquemas criados e os do fabricante.
- Tela de bloqueio por `PersonalizationCSP` — HKLM fora das raízes e sem efeito documentado no
  Home.

**Consequences**
O responsável cria a opção `papel` em `Tipo` no NocoDB, cadastra a linha da imagem e faz o deploy
da API antes do app novo. Os cenários de escrita ficam para a máquina real com o instalador.

---

## ADR-023 — Preparação completa por perfis fechados, retomada assistida, Limpeza de manutenção, Registro e Ajuda consolidada

**Status:** Accepted
**Date:** 2026-11-06
**Module:** 13

**Context**
No Configurador, a preparação em lote (`aba_master.py`, `estado.py`) monta o plano lendo as
outras abas, não trata erro por etapa (uma exceção derruba o resto), pula etapa vazia em
silêncio e retoma depois do reinício por `HKCU\...\Run` com comando interpolado, executando as
tarefas sem confirmação e sem limpar a lista. A Limpeza esvazia pastas pessoais e perfis de
alunos, com `robocopy /MIR /B` de reserva. As contas por turno são criadas como administradoras
com senha fixa no código e depois ficam sem senha. A tela de logs só mostra a sessão, sem teto.
Desenho proposto e aprovado com ajustes em `.conversa/` em 06/11/2026.

**Decision**
1. **Perfis fechados no código** (`servicos/perfis.py`): `sala_de_aula` (Sala de aula, todas as
   etapas), `administrativo` (Administrativo, sem Políticas, USB e Remover pré-instalados) e
   `so_diagnostico` (Só diagnóstico). Perfil = id, nome e tupla ordenada de ids de etapa;
   parâmetros só de listas fechadas do código (ids de política, opções de mouse e teclado,
   tempos de energia, itens da Limpeza, famílias Appx) ou "linhas ativas do cadastro" (Wi-Fi da
   unidade, Programas `Categoria = Programas`, papel de parede ativo, Acesso remoto).
   `Unidades.PerfilPadrao` pré-seleciona pelo id; texto desconhecido é ignorado com aviso. Na
   hora o técnico só desmarca etapas, escolhe as contas-alvo entre as "contas de aluno" e digita
   o nome do computador. Nunca texto livre, caminho, comando, ordem ou parâmetro editável.
2. **Motor** (`servicos/preparacao.py`, sem Qt): cada etapa tem `ler()` e `aplicar()` que só
   chamam os serviços dos módulos 07 a 12. A situação é sempre lida do Windows antes de aplicar;
   etapa "feita" é pulada, sem marca guardada. Situações: `feito`, `pendente`, `nao_iniciado`,
   `bloqueada` (pré-requisito: cache, administrador, cadastro, etapa de que depende), `falhou`
   (com código) e `aguardando_reinicio`. Falha numa etapa segue para a próxima que não depende
   dela (Contas bloqueia Políticas, USB, Papel de parede e Mouse e teclado). "Pausar" = parar
   depois da etapa corrente; o `cancelar` só vai a quem já cancela com segurança. Ordem:
   Identificação, Contas, Wi-Fi, Acesso remoto, Programas, Remover pré-instalados, Políticas,
   USB, Proteção do login, Papel de parede, Mouse e teclado, Energia, Limpeza, Diagnóstico.
   - **Contas:** `aplicar_suporte` e `lote("padrao")`. A confirmação diz que a conta logada
     também perde administrador (ADR-017, item 6) e que depois o UAC pede a Suporte. "Feito" =
     Suporte ativa no `S-1-5-32-544`, nenhuma outra conta ativa no grupo, RID 500 desativado.
     O Bench não altera o RID 500 (ADR-017): ativo, a etapa fica pendente pedindo para
     desativá-lo pelo Windows, sem bloquear as dependentes (revisão do PR #37).
   - **Contas de aluno** (`preparacao.contas_de_aluno`): contas locais ativas, não
     administradoras, menos Suporte, RID 500 e a conta logada, com as recusas do ADR-021.
   - **Acesso remoto:** "feito" = os programas com cadastro completo instalados e configurados,
     sem número fixo.
   - **Limpeza na preparação:** só temporários (sistema e por usuário), cache do Windows Update e
     relatórios de erro. A lixeira só pela tela Limpeza.
3. **Remover pré-instalados (Appx):** trecho próprio (`recursos/programas/appx.ps1`) chamado
   pelo serviço de desinstalação. Lista fechada por nome de família (`Name` do pacote) de apps de
   consumidor da Microsoft (`desinstalar.APPX_PREINSTALADOS`). Remove para todas as contas
   (`Remove-AppxPackage -AllUsers`) e o pacote provisionado. Recusa, no Python e no trecho, nome
   fora da lista, `SignatureKind = System`, `NonRemovable` e framework. Confirmação com a lista.
4. **Contas por turno fora do 13.** As do Configurador são administradoras e sem senha, criadas
   com senha fixa no código, contra o ADR-017. Item futuro possível (opção B): sufixo fixo no
   código, conta padrão, senha digitada na hora (sem cadastro, disco ou log), por
   `contas.criar`.
5. **Reinício e retomada assistida.** Pedem reinício: renomear e instaladores com 3010/1641. O
   Bench não reinicia sozinho e não usa Run/RunOnce, tarefa agendada nem serviço. Antes de
   "Reiniciar agora" grava `protegido\preparacao.json`: `formato`, perfil, etapas desmarcadas,
   nome pedido, alvos por SID, horário e contagem de reinícios (sem senha, token, técnico ou
   nome de conta; SIDs nunca no log). Ao ler: dono e ACL conferidos pelo critério do ADR-020
   (senão apaga e registra), cada id validado contra o catálogo (o que não casa é descartado),
   vencido (24 h) ou ilegível é apagado. O técnico sempre faz login ao reabrir (sessão só em
   memória; offline de 7 dias do ADR-013). Máximo de 2 reinícios por preparação; etapa que pediu
   reinício e continua pendente depois do boot não pede outro. "Descartar preparação" apaga o
   arquivo.
6. **Início:** máquina lida por CIM sem texto localizado (`recursos/inicio/ler.ps1`); etapas do
   perfil da unidade; último diagnóstico (fila local); alertas com atalho para a tela que
   resolve (proteção do login por `protecao.situacao().alertas()`, políticas e USB do perfil,
   nome pendente, Suporte ausente, cache vencido, fila de diagnóstico). BitLocker fora. Selos na
   barra: `feito/aplicáveis` na Preparação e alertas críticos no Início. Leitura em tarefa,
   cache de 60 s. Atalhos: forçar inventário GLPI e abrir a Limpeza.
7. **Limpeza de manutenção** (`servicos/limpeza.py`, `recursos/limpeza/limpeza.ps1`), lista
   fechada: temporários do sistema, temporários por usuário (por SID; caminho de `ProfileList`
   conferido no trecho, cadeia perfil → `AppData` → `Local` → `Temp` sem reparse, conferida de
   novo logo antes de varrer), lixeira, cache do Windows
   Update e relatórios de erro (WER). Enumeração manual que nunca desce em reparse point (o link
   é removido como link), cada caminho conferido contra a raiz, arquivo em uso só contado. Saída
   só números por id. Prévia com tamanho antes, confirmação com o total. Windows Update: com
   reinício pendente de atualização ou serviço que não para no tempo, o item fica "não limpo";
   `wuauserv`/`bits` só param e voltam ao estado anterior no `finally`, sem mudar o tipo de
   inicialização. Fora: pastas pessoais e perfis ("zerar aluno", se pedido, ADR próprio),
   `Windows.old`, WinSxS, pontos de restauração e logs (o do Bench já rota).
8. **Registro:** `bench.log` e rotacionados só leitura, filtros por nível e texto. O log tem
   técnico (ADR-013), nomes de contas afetadas (ADR-017) e nome do computador (ADR-018), nunca
   senha, token, SSID, host de servidor, SID ou caminho de perfil. Exportar grava só as linhas
   filtradas, com máscara de nome do computador, nomes das contas locais e `X:\Users\<nome>`.
9. **Ajuda consolidada:** `ui/ajuda.py` reúne as constantes `AJUDA*` das telas sem copiar
   texto; tela Ajuda na ordem do menu com busca sem acento e maiúscula.
10. **Executor e log:** nenhuma exceção nova ao executor. Log da preparação: perfil, etapa,
    situação, resultado e código; nunca mensagem do Windows, nome de conta, SID, SSID, nome de
    programa do cadastro ou senha.
11. **API sem mudança:** `Unidades.PerfilPadrao` já vem na rota de cadastros (ADR-014).

**Alternatives considered**
- Perfis no NocoDB ou em arquivo local — configuração vinda de fora, sem revisão, e muda pouco.
- Marca "feito" em disco — diverge do Windows quando alguém desfaz à mão.
- Run/RunOnce, tarefa agendada ou serviço para retomar — abre elevado sem técnico ou aparece na
  conta do aluno.
- Contas por turno com senha no cadastro — mesma senha em todas as máquinas da unidade.
- `cleanmgr /sagerun` e `Remove-Item -Recurse` — sem prévia por item; segue junction no PS 5.1.
- Sanear o log na gravação — desfaz decisões do 07 e do 08.
- Ajuda em Markdown — muda o formato de 7 módulos sem ganho agora.

**Consequences**
O responsável preenche `Unidades.PerfilPadrao` com o id do perfil. Os cenários de escrita ficam
para a máquina real com o instalador.

## ADR-024 — Revisão do Módulo 14: caminhos sem ambiente do usuário, texto puro único, `--dev` só leitura e riscos aceitos consolidados

**Status:** Accepted
**Date:** 2026-11-07
**Module:** 14

**Context**
A revisão transversal do Módulo 14 (`docs/security/2026-11-07-modulo-14.md`) achou regras que só
valiam em parte do código e deu destino às pendências informativas das auditorias de 00 a 13 que
estavam sem ADR nem tarefa. Nenhuma tela ou regra de produto nova.

**Decision**
1. **Pastas da máquina sem o ambiente do usuário.** `%ProgramData%` e a raiz dos perfis vêm de
   `HKLM\...\ProfileList` (`ProgramData`, `ProfilesDirectory`), com `%SystemDrive%` trocado pela
   unidade de `GetSystemWindowsDirectoryW`; outra variável no valor é recusada.
   `PROGRAMDATA`, `SystemDrive` e o próprio `SHGetKnownFolderPath` seguem variáveis de
   `HKCU\Environment`, que valem no processo elevado da mesma conta. Vale para todas as pastas
   de `protegido\`, para a Inicializar das sobras do Configurador e para a lista de perfis do
   Diagnóstico. `%LOCALAPPDATA%` (preferências, sem segredo) continua pelo ambiente.
2. **Texto puro num lugar só.** Caixa de mensagem estática do Qt e dica (`setToolTip`) usam rich
   text automático; dado que não é constante do código passa por `ui/texto.py` (`aviso` em texto
   puro, `dica` com o dado escapado). `test_texto_puro.py` barra `QMessageBox.warning()` e afins,
   `setHtml`, `setMarkdown` e dica não constante fora do helper.
3. **`--dev` nunca altera a máquina**, nem de um terminal elevado (`elevacao.modo_admin`): os
   ADR-017 a 023 já diziam "`--dev`: só leitura", mas valia só sem elevação.
4. **Propriedades MSI que carregam outro arquivo** (`TRANSFORMS`, `PATCH`, `MSIPATCHREMOVE`,
   `SOURCELIST`) são recusadas em `Argumentos`: o arquivo apontado não passa pelo SHA-256 do
   Bench (ADR-019/020).
5. **Lista fechada de quem fala com a API do Windows fora do executor** (`winreg`/`ctypes`), com
   motivo por módulo, em `test_invariantes.py`. Entrou `nucleo/caminhos.py` (item 1).
6. **Riscos aceitos consolidados** (informativos das auditorias, sem mudança de código):
   - corrida antes do Job Object (02);
   - texto da senha no `QLineEdit` até ser limpo (04);
   - cancelar a espera do laudo não aborta o HTTP; o timeout do cliente encerra (06);
   - senha em memória como `str` (07, 08);
   - formas cifradas do RustDesk/AnyDesk reversíveis por administrador local (09);
   - chave do RustDesk é segredo fraco por desenho do produto (09);
   - desinstalador só interativo roda como administrador, com aviso e confirmação (10);
   - janela com dono Administradores durante a proteção do utilman/sethc (12);
   - "Restaurar original" confia no WinSxS (12);
   - corrida residual na Limpeza entre a checagem da cadeia e a abertura da pasta (13);
   - atributo `Normal` posto num hard link criado pelo aluno para arquivo em que ele já grava (13).
7. **Mantidos como estão (verificados no 14):** segredos de todas as unidades sem `?unidade=`
   (ADR-014) e senha Suporte igual em todos os notebooks (ADR-017), com senha por máquina (LAPS)
   como tarefa futura; histórico de qualquer hostname com sessão ou token (ADR-016, TA-ADR das
   duas rotas); link simbólico de registro em `HKCU\Software\Policies` não é possível ao aluno
   (dono Administradores, só leitura para o usuário) e em chaves de preferência não dá ganho.

**Alternatives considered**
- `SHGetKnownFolderPath(FOLDERID_ProgramData)` — testado: com `SystemDrive` trocado no ambiente,
  falha ou devolve o caminho desviado.
- Corrigir só a pasta Inicializar (item 40 do inventário) — as pastas de 05, 10, 12 e 13 vinham
  da mesma variável.
- `setTextFormat` em cada caixa e dica tela a tela — já existia em parte e divergiu; um helper e
  um teste não deixam voltar.
- Um ADR por risco aceito — espalha o que é uma decisão só (fechar o 14).

**Consequences**
Desenvolver com `--dev` não exercita escrita; teste de escrita fica nos testes automatizados com
executor falso e no roteiro de máquina real (`docs/testes/maquina-real.md`). Mensagens de erro
com `<` passam a aparecer literalmente.

---

## ADR-025 — Empacotamento `onedir`, instalador Inno Setup, endereço da API no HKLM e Bench endurecido quando empacotado

**Status:** Accepted
**Date:** 2026-11-08
**Module:** 15

**Context**
O ADR-002 deixou a ferramenta de instalador em aberto, e o ADR-008 manda que o endereço da API
seja o único dado de ambiente no instalador. O Bench roda elevado e lê `.ps1`, DLLs e ícones
do próprio pacote: quem grava na pasta do pacote ganha administrador. O Módulo 14 (ADR-024)
mostrou que o ambiente do usuário (`HKCU\Environment`) vale no processo elevado da mesma conta.
O Módulo 16 precisa de versão gravada e caminho fixo. Desenho aprovado em `.conversa/` em
08/11/2026, com ajustes.

**Decision**
1. **PyInstaller `onedir`**, janela (`console=False`), UPX desligado, manifesto `asInvoker` (a
   elevação continua no `elevacao.py`; `--dev` e `--teste` sem UAC). `recursos/` vai inteiro
   para `_internal\itc_bench\recursos\` e é lido por `importlib.resources`, como fora do pacote.
   `VERSIONINFO` gerado no `.spec` a partir de `__version__`. Ícone `.ico` com 8 tamanhos (16 a
   256) gerado do símbolo por `app/empacotamento/gerar_ico.py` e guardado no repositório.
   O OpenSSL do `_ssl` é fixado na pasta `DLLs` do Python: a análise de dependências do
   PyInstaller procura também no `PATH` da máquina de build e tinha empacotado um `libcrypto` de
   outro programa (o `_ssl` não carregava).
   **Origem dos binários em lista fechada** (`app/empacotamento/origens.py`, chamado pelo
   `.spec` depois da `Analysis`): todo item de `a.binaries` tem que vir do Python base
   (`sys.base_prefix`, inclusive `DLLs`), do ambiente do projeto (`sys.prefix`, o `.venv`) ou de
   `System32` (pela `GetSystemDirectoryW`); qualquer outro para o build com a lista do que veio
   de fora. Única exclusão explícita: o UCRT (`ucrtbase.dll` e `api-ms-win-*`), parte do Windows
   10/11 e resolvido pelo carregador; o PyInstaller só coletava essas 43 DLLs porque achava
   cópias na pasta de um JDK no `PATH` da máquina de desenvolvimento. Elas saem do pacote e o
   build registra quantas.
2. **Inno Setup 6.7.4** (instalador por máquina, 64 bits, `C:\Program Files\ITC\Bench` fixo,
   `UsePreviousAppDir=no`, `DisableDirPage=yes`), `AppId` fixo
   `{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}`. Compilador baixado da release oficial com SHA-256
   conferido e instalado em modo portátil no CI. O script não extrai nem executa nada de `{tmp}`;
   o motor do Inno usa uma pasta temporária com nome aleatório (CSPRNG) e liga o
   `RedirectionGuard` (sem seguir junction criada por não administrador).
   - **Bench aberto:** `AppMutex=ITCBench,Global\ITCBench`, criado pelo app
     (`nucleo/instalacao.py`); `CloseApplications=no`. **Substituído pelo ADR-026 (item 9):**
     um usuário comum cria os dois nomes; o instalador passou a contar só mutex de
     Administradores. A instalação silenciosa recusa e o
     assistente pede para fechar: nunca mata uma preparação no meio (Módulo 16).
   - **Upgrade por cima** não roda o desinstalador: mantém `protegido\` e `ApiUrl`. Apaga
     `{app}\_internal` antes de copiar, para não sobrar arquivo da versão anterior.
   - Atalho só no Menu Iniciar de todos os usuários; nenhum na Área de Trabalho Pública.
3. **Endereço da API em `HKLM\SOFTWARE\ITC\Bench\ApiUrl`** (vista 64 bits, onde o
   `servicos/api.py` já lia). Chega por `/APIURL=` na silenciosa ou pela página do assistente
   (preenchida com o valor atual). Instalação nova silenciosa sem `/APIURL` falha; atualização sem
   ele mantém o valor. Trocar depois: rodar o instalador de novo com `/APIURL=`.
   - Validação igual no Pascal Script e no `validar()`: `https://`, host, sem `usuario:senha@`,
     query, fragmento nem espaço. A recusa de credencial, query e fragmento é nova no app.
   - **Limite aceito:** o log do Inno (`/LOG`) grava a linha de comando, com o endereço. Não é
     segredo (ADR-008: só ele vai no instalador), mas fica no log da máquina.
   - O endereço nunca entra no `.iss`, no CI nem no EXE; o CI usa `https://api.exemplo.invalid`.
     **Emendado pelo ADR-027:** o instalador de release (build de tag) leva o endereço embutido.
4. **Pasta de instalação conferida pelo app** (`nucleo/instalacao.py`, só empacotado), antes de
   qualquer ação: o EXE tem que estar na pasta fixa (`ProgramFilesDir` do HKLM, sem o ambiente
   do usuário); a pasta, o pai (`Program Files\ITC`) e tudo dentro sem ponto de reparse; dono
   SYSTEM, Administradores ou TrustedInstaller; nenhuma ACE de permissão com escrita, `DELETE`,
   `WRITE_DAC` ou `WRITE_OWNER` para outro SID (`CREATOR OWNER` ignorado: no filho vira o dono).
   Falhou: sem modo administrador, log, mensagem "Reinstale" e saída 3 (`--dev` segue só
   leitura). Não corrige a ACL: os arquivos podem já ter sido trocados.
   **Limite:** a conferência roda depois de Python e Qt carregarem do pacote; ela detecta, não
   impede. A proteção é a ACL herdada de `Program Files`, que o instalador não altera.
5. **Ambiente do usuário fora do processo** (ajuste 1): antes de qualquer `QApplication`, o
   `main` tira `QT_*`, `QML*` e `PYTHON*` do ambiente (no empacotado e no `uv run`; só
   `QT_QPA_PLATFORM=offscreen`, a do CI, fica). No empacotado, `QT_PLUGIN_PATH` volta apontando
   para o pacote, e `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS)` com
   `AddDllDirectory` do pacote tira o `PATH` da busca de DLL (o gancho do PySide6 põe o pacote no
   `PATH`, mas o `PATH` também traz pastas do usuário). O bootloader do PyInstaller 6 não usa
   `PYTHONPATH` (testado no runner: `sys.path` só com o pacote); o app recusa, como pasta
   alterada, se alguma entrada de `sys.path` cair fora do pacote. No `uv run`, `PYTHON*` já foi
   lido pelo interpretador: a limpeza só evita passar adiante.
6. **`--teste` nunca altera a máquina**, nem elevado (como o `--dev` no ADR-024): no runner do
   CI ele roda elevado. Lê todos os arquivos de `recursos/` e sai com 4 se faltar algum.
7. **Desinstalação:** sai a pasta, o atalho, a chave de desinstalação e
   `HKLM\SOFTWARE\ITC\Bench`; sai `%ProgramData%\ITC\Bench\protegido\` (cache de cadastros, login
   offline, fila, `preparacao.json`, instaladores), com a pasta e os pais conferidos contra ponto
   de reparse antes. Ficam `logs\`, `papel\` e `icones\`, usados pela preparação aplicada. A
   desinstalação não desfaz a preparação: aviso na confirmação do assistente e no log da
   silenciosa.
8. **Versão:** SemVer com fonte única em `itc_bench/__init__.py` (o hatch lê dali). Chega ao EXE
   (`VERSIONINFO`), ao instalador (`/DAppVersion`), a `DisplayVersion` e `InstallLocation` da
   chave de desinstalação (o que o 16 lê) e ao rodapé. Tag `vX.Y.Z` diferente de `__version__`
   falha o CI. Este módulo sobe para 0.15.0; 1.0.0 depois do roteiro de máquina real.
9. **Sem assinatura de código por enquanto**, com `SHA256SUMS` publicado junto do instalador
   (UAC mostra "Editor desconhecido"; SmartScreen avisa em arquivo baixado). Passo de assinatura
   no workflow desligado. OV ou Trusted Signing reavaliados antes de distribuir em larga escala.
10. **CI (`app-build.yml`):** PR compila, varre e testa a instalação no runner, artefato do
    Actions por 7 dias; tag `v*` cria Release em rascunho, publicada pelo responsável. Só o CI
    gera artefato distribuível (`docs/BUILD.md`). Varredura do pacote por `instalador/varrer.py`
    (árvore, `.zip` e o `PYZ` embutido no EXE descomprimido; árvore instalada no runner) e
    gitleaks em modo diretório.

**Alternatives considered**
- `onefile` — extrai Python, Qt e `.pyd` em `%TEMP%\_MEIxxxx`, gravável pelo usuário, e o
  processo elevado carrega DLL dali (contra ADR-011 e ADR-024); também abre mais devagar.
- WiX (MSI) — melhor para GPO/Intune, mas o parâmetro e a página do endereço dão mais trabalho e
  o harvest do `onedir` vira um XML longo; o WiX 6 pede taxa de manutenção a empresas.
- `requireAdministrator` no manifesto — UAC até para `--dev` e `--teste`.
- Endereço em arquivo em `%ProgramData%` ou ao lado do EXE — mais uma ACL a conferir, ou proibido.
- Fechar o Bench pelo Restart Manager na atualização — mataria uma preparação no meio.
- Corrigir a ACL da pasta de instalação pelo próprio app — legitimaria arquivos já trocados.
- Apagar `%ProgramData%\ITC\Bench` inteiro na desinstalação — quebra papel de parede e atalhos
  aplicados.

**Consequences**
O instalador do CI é o que vai para o roteiro de máquina real (`docs/testes/maquina-real.md`).
Quem já tem `ApiUrl` gravado à mão não precisa passar `/APIURL` numa atualização. Um usuário
comum conseguia criar o mutex e travar a instalação silenciosa (corrigido no ADR-026). Build local serve para teste, não para distribuir.

## ADR-026 — Atualização automática: manifesto assinado, instalador servido pela API, disparo ao fechar e mutex de Administradores

**Status:** Accepted
**Date:** 2026-11-08
**Module:** 16

**Context**
O Bench roda elevado e, ao atualizar, executa o instalador elevado em todos os notebooks: quem
escolhe o arquivo e o hash ganha administrador na frota. O repositório é privado (a Release do
GitHub não baixa sem token, e token nos notebooks está fora de cogitação) e não há assinatura de
código (ADR-025). O Módulo 15 deixou o `AppMutex` e a versão gravada (`DisplayVersion`).
Desenho aprovado em `.conversa/` em 08/11/2026, com dez ajustes.

**Decision**
1. **Fonte da versão:** tabela `bench_versoes` no SQLite da API, gravada só pela CLI
   `app.bench_versao` no servidor, com operador (TA-ADR-033). Rota `GET /v1/bench/versao` com a
   sessão do técnico. Sem link no dado.
2. **Hospedagem:** a API serve o instalador em `GET /v1/bench/versao/arquivo?sha256=`, mesmo
   `ApiUrl`, sob o Bypass de `/v1/bench/`, sem extensão e com `Cache-Control: no-store`. O
   cliente usa o abridor da API, que não segue redirecionamento.
3. **Manifesto assinado:** `{produto, app_id, versao, minima, sha256, tamanho, notas,
   publicado_em}` em JSON UTF-8, assinado nos bytes exatos com ECDSA P-256/SHA-256, formato
   IEEE P1363 (64 bytes). O Bench confere pela CNG (`BCryptVerifySignature`,
   `nucleo/assinatura.py`) e só lê o JSON depois. **Duas chaves públicas no pacote**
   (`recursos/atualizacao/principal.pub` e `reserva.pub`, SPKI em base64): perda ou vazamento da
   principal se resolve com versão nova assinada pela reserva. Chaves privadas só com o
   responsável (PKCS#8 cifrado, `instalador/gerar-chaves-versao.ps1`), fora do repositório, do
   servidor e do CI; a reserva fica guardada fora de linha. A tela mostra só as notas assinadas.
   Servidor comprometido só consegue negar a atualização ou reservir um manifesto antigo
   (barrado pelo item 6).
4. **Download** para `%ProgramData%\ITC\Bench\protegido\atualizacao\setup-<sha256>.exe` (SY/BA
   por herança da protegida, sem reparse point), via `.parcial`, com retomada por `Range` e teto
   no tamanho assinado; manifesto e assinatura guardados ao lado (valem offline). Nunca `%TEMP%`.
   Limpeza do que não é da versão anunciada; logs do Inno ficam.
5. **Ao fechar**, com o técnico tendo confirmado na faixa (ou sempre, se obrigatória): recusa com
   Preparação em andamento ou retomada pendente (ADR-023); solta o mutex e chama
   `executor.disparar()` com `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=<protegido>
   /ESPERAPID=<pid>`, sem `/APIURL`. Até 3 tentativas por versão; depois só manual.
   - **Emenda ao ADR-011 (`executor.disparar`):** único processo que segue depois do Bench, então
     fora do Job Object, sem pipe e sem espera. Continua valendo: lista de argumentos, caminho
     absoluto, sem shell, ambiente limpo. Só aceita `protegido\atualizacao\setup-<sha256>.exe`;
     abre o arquivo sem compartilhar escrita nem remoção (sem seguir reparse point), recalcula o
     hash pelo handle e cria o processo com ele aberto.
6. **Downgrade:** o app aceita só versão maior que a em execução e que a `DisplayVersion` do
   HKLM (vale o maior se divergirem). O instalador recusa só versão **menor** que a instalada
   (igual fica para reparo manual).
7. **Obrigatória x adiável:** adiável; obrigatória quando `minima` > versão em execução: a faixa
   não deixa adiar e oferece "Fechar e atualizar agora", e o fechamento atualiza sem perguntar.
   Desvio do desenho: as telas de ação não ficam bloqueadas (os painéis recebem o modo
   administrador na criação; bloquear exigiria refazê-los).
8. **Consulta e download ao abrir**, depois do login online e só elevado; `--dev` e `--teste`
   nunca consultam nem limpam (não alteram a máquina). Offline ou sem sessão, a versão já baixada
   e conferida pode ser instalada.
9. **Mutex de Administradores (ajuste 1):** prova no runner mostrou que um usuário comum cria
   `Global\ITCBench` (e o local `ITCBench` na mesma sessão), o que travava o `AppMutex` do
   Módulo 15. O `AppMutex` sai. O Bench elevado cria só `Global\ITCBench` com DACL SY/BA; o
   instalador (`BenchAberto()`) e o app (`mutex_de_administrador()`) só contam mutex que abre com
   `READ_CONTROL` e tem dono Administradores ou SYSTEM. Mutex de terceiro é ignorado com log e
   com aviso no Início (texto puro, com "?", sem usuário nem SID: não rodar o instalador à mão com
   o Bench aberto; pedir para encerrar a sessão desse usuário). Na
   atualização, `/ESPERAPID` é a garantia principal: espera o PID sair (60 s) só se ele ainda for
   o `ITC Bench.exe` da pasta fixa; o `PrepareToInstall` confere o mutex de novo antes de copiar.
10. **`--teste-atualizacao` (CI):** consulta, baixa e "fecha" sem janela. Só funciona na cópia
    de teste do CI, com o marcador `recursos/atualizacao/copia-de-teste-ci.txt` gravado pelo job
    ao lado das chaves de teste (pasta conferida pelo ADR-025), e com a sessão em
    `ITC_BENCH_SESSAO_TESTE`, gerada no job; sem um dos dois sai 5 sem consultar a API. Nenhuma
    sessão de teste no código (revisão do PR #43, achado 2).
11. **Build de release** (tag) falha se as duas chaves públicas do pacote não forem as comitadas.
    O teste de atualização usa cópias do pacote com chaves de teste, que nunca são publicadas.

**Alternatives considered**
- Linha em `Instaladores` (`Tipo = bench`) — quem edita o NocoDB ganharia administrador na frota.
- Só SHA-256 vindo da API — servidor comprometido roda código em todos os notebooks.
- Ed25519 com `cryptography` — DLL nativa nova no processo elevado; em Python puro, cripto à mão.
- Chave privada em secret do GitHub — a conta GitHub vira ponto único.
- Namespace privado (`CreatePrivateNamespace`) contra o squatting do mutex — o Inno não o usa e o
  Pascal Script teria de montar o boundary descriptor por ponteiro.
- Disparar pelo `executar` — o Job Object mataria o instalador quando o Bench sai.

**Consequences**
Exige deploy da API (migração 0007) e as chaves públicas reais comitadas pelo responsável; sem
elas o build de release falha. Falha no meio da cópia deixa o Bench sem `_internal` (o
`[InstallDelete]` já rodou): reinstalação manual (`docs/BUILD.md`). O Inno extrai o motor em
`%TEMP%` do técnico elevado, em pasta aleatória (risco aceito, Inno 6.7.4). Risco aceito (revisão do
PR #43, achado 1): com `Global\ITCBench` ocupado por outro usuário, um instalador rodado à mão
não percebe o Bench aberto; a atualização automática segue protegida pelo `/ESPERAPID`. Atualiza o ADR-025
(item 2, mutex) e o ADR-011 (disparo fora do Job).

## ADR-027 — Endereço da API embutido no instalador de release

**Status:** Accepted
**Date:** 2026-11-09
**Module:** pós-16 (emenda ao ADR-025, item 3)

**Context**
São cerca de 600 notebooks. Pelo ADR-025, a instalação nova pede o endereço da API (página do
assistente ou `/APIURL=`), e nenhum endereço entra no instalador. Para a frota, isso obriga a
digitar ou distribuir o endereço junto com o instalador em cada máquina. O responsável escolheu
(opção C, por simplicidade) que o instalador de release já saia do CI com o endereço.

**Decision**
1. **Origem:** segredo `BENCH_API_URL` no environment `release` do GitHub, usado só no build de
   tag `vX.Y.Z`. PR e push continuam sem endereço; o pacote (`dist`) nunca o recebe.
2. **Validação antes do ISCC** (`instalador/endereco-padrao.ps1`): a mesma regra do
   `EnderecoValido()` e do `validar()`, mais a recusa de aspas. Ausente ou inválido, o build de
   tag falha: nunca sai instalador de release sem endereço. O valor vai ao ISCC por
   `/DApiUrlPadrao=`; o GitHub mascara o segredo e nenhum passo imprime o valor, o tamanho ou
   parte dele.
3. **Precedência no `.iss`:** `/APIURL=` → valor já gravado no HKLM (upgrade mantém) → padrão
   embutido. Instalação nova silenciosa sem `/APIURL` funciona quando há padrão; sem padrão
   (build de PR) recusa como antes. O assistente vem preenchido com o padrão, e a validação do
   `.iss` vale também para ele. `/APIURL=` continua servindo para trocar o endereço.
4. O endereço fica no script compilado do Inno, dentro do `setup.exe` de release, e **é legível**
   por quem tiver o arquivo. O instalador de release é interno: não sai da equipe.

**Alternatives considered**
- Script `.cmd` ao lado do instalador com o `/APIURL` — dois arquivos para manter juntos, e o
  endereço fica igualmente legível.
- `itc-bench.ini` lido pelo instalador — mais um arquivo a distribuir e conferir; o mesmo
  endereço em texto.
- Manter o ADR-025 — digitar ou passar o endereço em 600 máquinas.

**Consequences**
O endereço deixa de ser segredo de quem tem o instalador de release (nunca foi segredo forte:
ADR-008). Um instalador adulterado continua coberto pelo `SHA256SUMS` da Release. O login do
técnico vai para o endereço embutido; trocar o servidor exige `/APIURL=` ou release nova. O
responsável cria o environment `release` e o segredo `BENCH_API_URL` (`docs/BUILD.md`). O CI
testa com endereços `.invalid` (`instalador/testar-endereco.ps1`).

## ADR-028 — SHA256 opcional em Instaladores (`instalador`, `papel` e ícone de `webapp`)

**Status:** Accepted
**Date:** 2026-11-09
**Module:** pós-16 (emenda aos ADR-019, ADR-020 e ADR-022)

**Context**
Os ADR-019, 020 e 022 exigem o SHA256 em toda linha de Instaladores que o Bench baixa. Para
preencher o hash, alguém precisa baixar cada programa no escritório, e não faz sentido o técnico
mandar ao escritório um hash gerado na própria máquina. O responsável decidiu que o SHA256 é
opcional: linha sem hash é válida e instala normalmente, sem pedir ação de ninguém.

**Decision**
1. **Sem hash.** O link continua só `https://` (redirecionamento só para `https://`), com a
   extensão conferida e, para `instalador`, a `Versao` obrigatória. O arquivo fica em
   `c<chave>.<sha>.<ext>`: `chave = sha256("Id\nLink\nVersao")` e `sha` é o hash calculado no
   download (ou na cópia de "Escolher arquivo…"). Se `Link` ou `Versao` mudarem, a chave muda, o
   arquivo antigo não é reaproveitado e sai na limpeza.
2. **Com hash.** Sem mudança: o arquivo fica em `<sha>.<ext>`, conferido no download, na cópia e
   antes de executar. Divergiu, recusa. SHA256 preenchido e inválido continua recusado.
3. **Conferência antes de executar** nos dois casos pelo hash do nome do arquivo
   (`instaladores.conferir`). Uma troca do arquivo no cache continua recusada.
4. **Registro.** O `bench.log` registra a linha sem hash (`Id`) e o começo do hash calculado. O
   link continua fora do log, host inclusive: o host pode ser servidor interno, e o teste ponta a
   ponta já barra o host do download no log. Na tela, só "SHA-256: não cadastrado" no texto secundário, sem
   aviso nem pedido de ação.
5. **API.** O `papel` deixa de exigir SHA256 (TA-ADR-034).
6. A atualização do próprio Bench (manifesto ECDSA, ADR-026) continua obrigatória e não passa
   por aqui.

**Riscos aceitos**
- Sem hash, a integridade depende do TLS do `https://`, de o host do link não estar
  comprometido e do controle de quem edita Instaladores no NocoDB. Um link trocado no NocoDB, ou
  um site de fabricante comprometido, faz o Bench executar outro binário como administrador.
- "Escolher arquivo…" sem hash executa o arquivo que o técnico escolheu, sem conferência.
- Continua protegido: troca do arquivo no cache (hash do nome conferido antes de executar), pasta
  `protegido` só para SYSTEM e Administradores, teto de 300 MB, `https://` obrigatório.
- **Mitigação opcional:** para programas sensíveis (RustDesk, AnyDesk), preencher o SHA256 põe a
  linha de volta no modo estrito.

**Alternatives considered**
- Hash obrigatório (situação anterior): obriga a baixar cada programa no escritório.
- Fixar no cadastro o hash do primeiro download do técnico: exige o técnico mandar o hash ao
  escritório, que é o que se quis evitar.
- Arquivo auxiliar com o hash ao lado do cache: mais um arquivo para manter; o nome já guarda o
  hash.

**Consequences**
Cadastro mais simples; linhas sem hash ficam protegidas só pelo transporte e pelo controle de
edição do NocoDB. O roteiro de máquina real ganha um cenário sem hash e um com hash divergente.

---

## ADR-029 — Contas por turno na Identificação, com o nome do computador como base

**Status:** Accepted
**Date:** 2026-11-10
**Module:** Pós-16 (pedido do responsável)

**Context**
O ADR-023 (item 4) deixou as contas por turno fora do 13 e descreveu a opção B (sufixo fixo,
conta padrão, senha digitada na hora). O responsável pediu o fluxo na tela Identificação:
digitar o nome do computador uma vez, gerar as contas a partir dele, ver a prévia, criar e
decidir o reinício, sem digitação repetida. Decisões tomadas com o responsável em 10/11/2026.

**Decision**
1. **Nome base** = o nome digitado no campo do computador, que já vem preenchido com o que vale
   depois de reiniciar (`Estado.pendente`, ADR-018). Sem segundo campo de nome.
2. **Regra** (`servicos/contas_turno.py`, sem Qt): com turno marcado, `BASE-Manha`,
   `BASE-Tarde`, `BASE-Noite` (nessa ordem, sufixo ignorado); sem turno e com sufixo,
   `BASE-Sufixo`; sem nenhum dos dois, só `BASE`. Opção "Criar também o usuário do sufixo"
   (só com turno marcado, desmarcada por padrão; pedido do responsável em 10/11/2026): soma
   `BASE-Sufixo` às contas dos turnos, por último. O sufixo não entra dentro do nome do turno.
3. **Turnos sem acento** (`Manha`), por perfil, scripts e acesso remoto; a tela mostra "Manhã".
4. **Sufixo livre, mas restrito**: letras sem acento, números, hífen e `_`, sem espaço e sem
   hífen ou `_` na ponta. Desvia da opção B (sufixo fixo) a pedido do responsável.
5. **Contas Local padrão, sempre sem senha**, por `contas.criar` (ADR-017). Nunca
   administradora. Risco aceito pelo responsável: qualquer pessoa entra em qualquer turno.
6. **Conta com o nome do computador permitida só aqui** (`permitir_nome_computador`, conferido
   também em `criar.ps1` por `ITC_PERMITIR_NOME_PC`). A tela Contas continua recusando. Risco
   aceito: login ambíguo `PC\PC`; e o Bench recusa renomear o computador para o nome de uma conta
   local, então a troca futura de nome exige outro nome.
7. **Limite de 20 caracteres** do Windows: a prévia marca ✕ e explica; nada é abreviado.
8. Conta que já existe não é recriada (⚠); erro numa conta não para as outras (✕ com o
   motivo). Resumo com criados, já existentes e erros.
9. **Um bloco só, um botão** (revisão de 10/11/2026, pedido do responsável): o campo do nome já
   vem com o nome que vale depois de reiniciar; o botão "Renomear e criar usuários" (ou "Criar
   usuários", se o nome não mudou) renomeia e depois cria, com o nome digitado como base
   (`contas_turno.configurar`). Se o renomear falhar, nenhuma conta é criada. Sai o botão
   "Reiniciar agora" da tela e a pergunta de reinício depois do renomear: o reinício só é
   oferecido depois da criação, com duas confirmações ("Reiniciar agora" → "Sim, reiniciar"),
   pelo `identificacao.reiniciar` existente; depois o Bench fecha pela janela. "Deixar para
   depois" não reinicia. Mantém o item 5 do ADR-023.
10. Log: só as contagens; os nomes das contas criadas vão pelo log de `contas.criar` (ADR-017).

**Alternatives considered**
- Senha digitada na hora (opção B) — recusada pelo responsável: mais lenta na bancada.
- Recusar a conta com o nome do computador — recusada pelo responsável.
- Abreviar turno (M/T/N) para caber em 20 — nome menos claro.

**Consequences**
Os cenários de escrita (criar de verdade, reiniciar) ficam para a máquina real com o instalador.
A Preparação completa não muda.

---

## ADR-030 — "Servidor da API" do RustDesk, opcional, vindo de Servidores

**Status:** Accepted
**Date:** 2026-11-10
**Module:** Pós-16 (pedido do responsável; emenda ao ADR-019, itens 2 e 9)

**Context**
O ADR-019 grava no `RustDesk2.toml` só o servidor de ID/Relay e a chave. O campo "Servidor da
API" do RustDesk ficava vazio, e o cliente avisa que o servidor personalizado usa HTTP por
padrão. O responsável pediu que o Bench preencha esse campo com o servidor da API do RustDesk
da empresa, que é outro endereço, em `https://`.

**Decision**
1. **Linha nova e opcional** em Servidores: `RustDesk`/`api`, **pública**, com a URL. O endereço
   não entra no código nem no repositório (ADR-008).
2. **Validação:** só `https://` com host; sem usuário e senha, query (`?`), fragmento (`#`),
   espaço ou aspas (`remoto.validar_url_api_rustdesk`). Duplicada, com `Publico` trocado, vazia
   ou inválida recusa o RustDesk com o motivo, como as outras linhas do ADR-019.
3. **Gravação:** com a linha, `rustdesk2()` grava `[options] api-server`; sem ela, não mexe na
   chave (fica o que já estava, inclusive um valor posto à mão).
4. **Situação:** com a linha, "Configuração: conferida" exige também `api-server` igual ao
   cadastro. A confirmação de Instalar/Reconfigurar mostra "Servidor da API: <URL>".
5. **Log:** como o resto do ADR-019, sem URL nem host.

**Alternatives considered**
- Linha obrigatória — quebraria a instalação de quem usa o servidor gratuito, que não tem API.
- Derivar a URL do servidor de ID (`https://<host>`) — o servidor da API é outro endereço.
- Aceitar `http://` — o próprio RustDesk avisa contra; a URL fornecida é `https://`.

**Consequences**
O responsável cadastra `RustDesk`/`api` no NocoDB e sincroniza; depois, Reconfigurar o RustDesk
nas máquinas já instaladas. Cenário 7.2a do roteiro de máquina real.

---

## ADR-031 — Senha permanente do RustDesk por `rustdesk.exe --password`

**Status:** Accepted
**Date:** 2026-11-10
**Module:** Pós-16 (decisão do responsável; substitui o ADR-019, item 8, para o RustDesk)

**Context**
O ADR-019 (item 8) evitava a senha na linha de comando: o Bench gravava `password` em texto puro
no `RustDesk.toml` do serviço e esperava o RustDesk regravá-la cifrada. Ficou registrado que isso
nunca tinha sido testado e que, se falhasse, a decisão voltava ao responsável. Na máquina real
(10/11/2026, RustDesk 1.5.1) três tentativas falharam: o serviço iniciou e a senha nunca foi
cifrada. A senha definida pela tela do RustDesk aparece com prefixo `01`, que o Bench passou a
reconhecer, mas o caminho pelo arquivo não funciona nessa versão.

**Decision**
1. **Senha por `rustdesk.exe --password`,** o caminho oficial do RustDesk, com o serviço rodando
   (depois de gravar o `RustDesk2.toml` e iniciar o serviço).
2. **Executor sem exceção nova:** o trecho fixo `recursos/remoto/senha.ps1` recebe a senha em
   `ITC_SENHA` (`Sensivel`) e o caminho do `rustdesk.exe` instalado em `ITC_EXE`, e chama
   `& $exe --password $env:ITC_SENHA`. A saída do RustDesk não é devolvida (só `OK` ou
   `ERRO|codigo`); o log tem só o código.
3. **Nada de senha no disco:** o Bench deixa de gravar `password` no `RustDesk.toml`. Depois do
   `--password`, confere em até 20 s que a senha aparece cifrada (`0` + dígito) e que o texto
   puro não está no arquivo; se o texto puro aparecer, a linha sai antes de falhar.

**Risco aceito (responsável, 10/11/2026)**
- Durante a chamada (menos de um segundo), a senha fica na linha de comando do `rustdesk.exe`:
  visível para administradores locais (`Win32_Process`) e em auditoria de processos (evento 4688
  com linha de comando, se ligada). Aceito porque a senha já é igual em toda a frota e reversível
  por administrador local (ADR-024), e quem vê o processo já é administrador.

**Alternatives considered**
- Manter a gravação pelo arquivo — não funciona no RustDesk 1.5.1 (máquina real).
- Senha definida à mão em cada máquina — trabalho e erro de digitação em ~600 notebooks.
- Política do servidor RustDesk para a senha — depende da edição do servidor; fica para depois.

**Consequences**
`docs/modules/09-acesso-remoto.md` (ordem do RustDesk) e o roteiro 7.2b mudam. O AnyDesk não
muda (senha pela entrada padrão, ADR-019).

---

## ADR-032 — Serviço do RustDesk 1.5.1: criar se faltar e um segundo início

**Status:** Accepted
**Date:** 2026-11-10
**Module:** Pós-16 (máquina real; emenda ao ADR-019, item 6)

**Context**
Na máquina real (10/11/2026), o MSI do RustDesk 1.5.1 com `/qn` instala os arquivos em 2 s
("Installation completed successfully"), mas não cria o serviço: ele só aparece quando o
`rustdesk.exe` roda. Criado, o primeiro início estoura o tempo do Windows (eventos 7009/7000,
30 s) e o serviço só sobe num segundo início (o técnico parava e iniciava pela tela do
RustDesk). O Bench esperava o serviço por 90 s e falhava com "não respondeu a tempo".

**Decision**
1. Antes de esperar ou iniciar o serviço do RustDesk (Instalar e Reconfigurar,
   `remoto._subir_rustdesk`): se o serviço `RustDesk` não existir, rodar
   `rustdesk.exe --install-service` pelo executor (argumentos fixos, sem dado, caminho da pasta
   instalada).
2. Se o serviço não ficar Running no tempo, parar e iniciar **uma vez** (ação `reiniciar` do
   `servico.ps1`). Falhando de novo, a mensagem continua "não respondeu a tempo".
3. `servico.ps1`: o erro do `Start-Service` vira `AVISO|iniciar`; quem decide é a espera pelo
   estado Running. Vale para os três programas.

**Alternatives considered**
- Aumentar a espera — o serviço criado não sobe sozinho; esperar mais não resolve.
- Criar o serviço com `sc.exe create` — repete o que o próprio RustDesk faz, com o risco de
  errar o caminho ou os argumentos do serviço.

**Consequences**
Pior caso do Instalar do RustDesk: cerca de 3 min antes da mensagem de erro. Cenário 7.2c do
roteiro de máquina real.

---

## ADR-033 — Políticas: marcar/desmarcar todas e desativar todas

**Status:** Accepted
**Date:** 2026-11-11
**Module:** Pós-16 (pedido do responsável; emenda ao ADR-021, item 13)

**Context**
Na tela Segurança › Políticas o técnico marca política por política (12 itens) para aplicar ou
desfazer, e não havia como tirar de uma vez todas as restrições de uma conta, por exemplo para
liberar a máquina para manutenção.

**Decision**
1. **"Marcar todas" / "Desmarcar todas":** um botão acima da lista que marca todas as políticas;
   se já estão todas marcadas, desmarca todas. O texto acompanha a marcação manual e a marcação
   sobrevive a "Atualizar". Só muda a tela: funciona sem administrador.
2. **"Desativar todas":** ao lado de Aplicar e Desfazer, desfaz **todo o catálogo da tela** nos
   **alvos marcados**, sem depender das caixas de política. É o mesmo Desfazer do ADR-021
   (`politicas.aplicar("desfazer", …)`): mesma confirmação detalhada (o que muda em cada alvo),
   com um cabeçalho "Desativar TODAS…", mesmas recusas de alvo, mesmo cancelamento entre alvos e
   mesmo log. Sem alvo marcado, avisa e não faz nada. Exige administrador; `--dev` só lê.
3. **Só na tela Políticas.** A tela USB tem uma política só e não muda (Desabilitar/Habilitar).
   "Desativar todas" não toca no bloqueio de USB, que é desfeito pela tela USB.

**Alternatives considered**
- Dois botões separados para marcar e desmarcar — mais um botão para a mesma ação.
- "Desativar todas" em todos os alvos de uma vez — alcança contas que o técnico não escolheu;
  os alvos continuam escolhidos à mão.
- Incluir o USB no "Desativar todas" — liberaria pendrive sem passar pela tela USB.

**Consequences**
Sem mudança no serviço, na API ou no NocoDB. Cenário 9.8 do roteiro de máquina real (11/V13).

---

## ADR-034 — Políticas também na conta que está rodando o Bench

**Status:** Accepted
**Date:** 2026-11-11
**Module:** Pós-16 (pedido do responsável; emenda ao ADR-021, item 5)

**Context**
O ADR-021 (item 5) recusava aplicar políticas na conta dona do processo elevado ("é a conta que
está rodando o Bench"), no Python e de novo no PowerShell. O responsável quer poder aplicar as
políticas também no usuário atual, por exemplo na conta de uso da máquina quando o técnico roda
o Bench nela.

**Decision**
1. **Políticas (e a tela USB, que usa o mesmo serviço) aceitam a conta que roda o Bench.**
   `politicas.aplicar` passa `permitir_dono=True` a `hive.aplicar`; `hive.recusa_alvo` só
   recusa essa conta quando `permitir_dono` é falso.
2. **Segunda conferência no trecho:** `comum.ps1` (`Hive-Escrita`) só libera a conta atual com o
   perfil `politicas` **e** `ITC_PERMITIR_DONO=1`. Qualquer outro perfil continua recusando.
3. **Aparência (papel de parede, mouse e teclado) e Preparação completa não mudam:** o padrão de
   `permitir_dono` é falso e elas continuam recusando a conta que roda o Bench.
4. **Continuam recusados** o Administrador nativo (RID 500) e a conta Suporte.
5. **Aviso:** com a conta que roda o Bench marcada, a confirmação diz que a restrição vale para
   ela no próximo logon e como desfazer (Desfazer ou Desativar todas, ADR-033). A ajuda da tela
   diz que a conta é aceita.

**Alternatives considered**
- Manter a recusa — o técnico teria de entrar com outra conta para restringir a conta em uso.
- Liberar também na Aparência — fora do pedido; a recusa lá continua protegendo a sessão do
  técnico.

**Riscos aceitos (responsável, 11/11/2026)**
- O técnico pode restringir a própria conta (CMD, Regedit, Painel de Controle, PowerShell pelo
  Explorer) e só perceber no próximo logon. O Bench continua funcionando nela (não usa o
  Explorer para abrir processos), e Desfazer ou Desativar todas desfazem.

**Consequences**
Cenários 9.2 e 11/V6 do roteiro passam a esperar "aceita, com aviso".

---

## ADR-035 — SeTakeOwnership e SeRestore ligados só durante a operação

**Status:** Accepted
**Date:** 2026-11-11
**Module:** Pós-16 (máquina real; emenda ao ADR-022, item 2, e ao ADR-011, item ACL)

**Context**
Na máquina real (11/11/2026), "Proteger" na Proteção do login deu `setowner_5` no utilman e no
sethc: o `icacls /setowner *<SID do TrustedInstaller>` sai com 5 (acesso negado), porque dar o
dono a outra conta exige o SeRestorePrivilege **ligado** no token que o `icacls` herda, e o
administrador o tem desligado. A negação ao SYSTEM foi aplicada, mas o dono ficou
Administradores, contra o ADR-022 ("o arquivo nunca fica com dono Administradores"). O
`nucleo/acl.py` já ligava os dois privilégios na inicialização (segunda tentativa do ACL de
`%ProgramData%\ITC`) e nunca os desligava.

**Decision**
1. `nucleo/acl.py` ganha `habilitar_privilegios()` e `desabilitar_privilegios()` (o mesmo
   `AdjustTokenPrivileges`, com `SE_PRIVILEGE_ENABLED` ou `0`).
2. **Proteção do login** (`protecao.alterar`): liga os dois privilégios antes dos passos
   (`takeown`, `icacls`, `setowner`) e desliga num `finally`, também com exceção. Falha ao ligar
   ou desligar vai ao log e não para: o passo do dono continua dizendo se deu certo.
3. **ACL de `%ProgramData%\ITC`** (`acl.proteger`): a segunda tentativa liga e desliga num
   `finally`, em vez de deixar ligado pelo resto da execução.

**Alternatives considered**
- `Set-Acl` com `SetOwner` no PowerShell — exige o mesmo privilégio ligado, e ligar dentro do
  trecho pediria `Add-Type` (proibido).
- Deixar os privilégios ligados desde a inicialização — o Bench e todo processo que ele abrisse
  passariam por cima das permissões de arquivo.

**Consequences**
O roteiro 10.1 confere o dono TrustedInstaller de volta. Na máquina em que o erro apareceu,
"Proteger" de novo (já com a correção) devolve o dono.

---

## ADR-036 — Contas: filtro modificáveis/não modificáveis e encerrar sessões

**Status:** Accepted
**Date:** 2026-11-11
**Module:** Pós-16 (pedido do responsável; emenda ao ADR-017)

**Context**
A tela Contas mostrava todas as contas juntas, inclusive as que o Bench nunca deixa alterar
(Administrador nativo, Suporte, contas Microsoft), e não havia como encerrar a sessão de outra
conta aberta na máquina (troca rápida de usuário) antes de excluí-la ou de aplicar algo nela.

**Decision**
1. **Filtro** acima da tabela: "Contas modificáveis" (padrão) e "Contas não modificáveis".
   Modificável (`contas.modificavel`) = conta local que não é o Administrador nativo nem a
   Suporte (nome cadastrado ou "Suporte"). O resto vai para "não modificáveis", só consulta. As
   outras regras do ADR-017 (conta em uso, último administrador, sessão aberta) continuam por
   ação, nas contas modificáveis.
2. **Encerrar sessões…** na Conta selecionada: lista as contas com sessão aberta
   (`contas.com_sessao`: perfil carregado ou em uso), o técnico marca quais e confirma ("o que
   estiver aberto e não salvo é perdido"). Cada uma vai por `contas.encerrar_sessao(sid)`.
3. **Trecho fixo `recursos/contas/encerrar.ps1`:** SID só por `ITC_SID` (validado); acha as
   sessões pelo dono do `explorer.exe` (como `Sids-Logados`); **recusa a sessão em que o próprio
   Bench roda** (`GetCurrentProcess().SessionId`); `logoff.exe` de `System32` por número de
   sessão. Erros como código (`sem_sessao`, `propria`, `encerrar`), sem mensagem do Windows no
   log.
4. Exige administrador; `--dev` só lê.

**Alternatives considered**
- Esconder as contas não modificáveis de vez — o técnico deixaria de ver que a Suporte existe.
- Encerrar pelo texto do `quser`/`query session` — saída localizada; o dono do `explorer.exe`
  já é usado na listagem e não depende do idioma.
- Permitir encerrar a sessão do Bench — o Bench fecharia no meio da ação.

**Consequences**
"Aplicar conta Suporte" continua na tela (o pedido de tirá-lo ficou para depois). Cenário 5.8
do roteiro (07/V9). Sessão sem `explorer.exe` (só serviço) não aparece como encerrável.
