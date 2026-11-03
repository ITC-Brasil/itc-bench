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

**Status:** Accepted
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

**Status:** Accepted (rotas: planejadas para o Módulo 04, no repo `tecnico-assistente`)
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
