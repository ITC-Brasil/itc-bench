# Módulo 02 — Execução segura de comandos

**Branch:** `feat/modulo-02-executor` · **Data:** 2026-11-03 · **ADR:** ADR-011

## O que entrou

| Item | Onde |
|---|---|
| Pré-requisito do 01: `sys.excepthook` (log com traceback + tela), `--teste` não executa ações | `src/itc_bench/__main__.py`, `tests/test_excecao.py`, `docs/modules/01-esqueleto.md` |
| Executor único: `executar()`, `powershell()`, `Resultado`, `Sensivel`, `sistema32()` | `src/itc_bench/servicos/executor.py` |
| Testes com entradas hostis (ambiente, argumento, stdin) | `tests/test_entradas_hostis.py` |
| Proibição de processo externo fora do executor e de `shell=` | `pyproject.toml` (ruff `TID251`), `tests/test_sem_shell.py` |
| Tarefa em segundo plano para a UI, sinais `concluido` e `falhou` | `src/itc_bench/ui/tarefa.py`, `tests/test_tarefa.py` |
| ACL explícito em `%ProgramData%\ITC` na execução elevada | `src/itc_bench/nucleo/acl.py`, `nucleo/caminhos.py`, `tests/test_acl.py` |

## Como usar

```python
from itc_bench.servicos.executor import Sensivel, executar, powershell, sistema32

r = powershell("New-LocalUser -Name $env:ITC_NOME -Password (ConvertTo-SecureString $env:ITC_SENHA -AsPlainText -Force)",
               nome=nome, senha=Sensivel(senha))
r = executar([sistema32("netsh.exe"), "wlan", "show", "profiles"])
if not r.ok: ...  # r.codigo, r.erros, r.esgotado
```

Na UI: `tarefa.iniciar(funcao, ao_concluir, ao_falhar)`.

## Decisões de implementação

- **CLIXML:** com `-EncodedCommand`, o PowerShell manda o stderr em CLIXML. O executor converte
  em texto antes de mascarar. Sem isso, uma senha com `<` ou `&` chegava escapada e passava pela
  máscara (achado durante a verificação e corrigido; teste `test_sensivel_com_caracteres_escapados_no_clixml`).
- **`netsh` em UTF-8:** no Windows 11 (build 26340) o `netsh` escreve UTF-8 mesmo com OEM 850;
  o `cmd` escreve OEM. Por isso o padrão é `auto` (UTF-8 válido, senão OEM), em vez de `oem`.
- **Caminhos de sistema pela API:** `GetSystemDirectoryW` e `[Environment]::GetFolderPath`;
  `SYSTEMROOT`/`WINDIR` do filho vêm da API. Com `SYSTEMROOT` falso herdado, o PowerShell não
  inicia (erro interno 8009001d).
- **ACL:** `TreeSetNamedSecurityInfoW` devolve sucesso mesmo quando um item falha; a falha só chega
  pelo callback de progresso. O retry com `SeTakeOwnershipPrivilege`/`SeRestorePrivilege` depende
  disso. O ACL não atravessa junction (testado); a checagem de reparse roda antes e depois.
- **Tarefa da UI:** o `QObject` de sinais era coletado pelo Python antes da entrega na suíte
  completa; a tarefa fica num conjunto até o sinal chegar na thread da tela.
- **`elevacao.py`** importa `subprocess` só para `list2cmdline` (parâmetros do `ShellExecuteW`);
  liberado por linha no ruff e por nome no teste de AST.

## Verificação

Bancada: Windows 11 Pro 10.0.26340, pt-BR (OEM 850, ANSI 1252), sessão elevada; "usuário comum" é
o mesmo usuário com `runas /trustlevel:0x20000` (token sem Administradores, `admin=False`).

| # | Cenário | Como | Resultado real |
|---|---|---|---|
| 1 | Lint | `uv run ruff check .` / `ruff format --check .` | All checks passed / 46 files already formatted |
| 2 | Tipos | `uv run mypy` (strict) | Success: no issues found in 16 source files |
| 3 | Testes | `uv run pytest` | 87 passed (acl 7, entradas hostis 42, executor 16, sem shell 4, tarefa 2, exceção 2, 01: 14) |
| 4 | Entradas hostis intactas | `test_entradas_hostis.py`: 14 valores (aspas simples e duplas, `&`, `\|`, `;`, `^`, `%VAR%`, `$()`, crase, quebra de linha, espaços, acento/€/中文, vazio, 30 000 caracteres) × 3 vias (PowerShell por `ITC_*`, argumento para processo nativo, stdin); o filho devolve o valor em base64 | 42 passed: valor idêntico byte a byte; o arquivo-marca que cada valor tenta criar não existe |
| 5 | Timeout encerra processo e filho | `test_timeout_encerra_processo_e_filho`: PowerShell abre `PING -n 60` e dorme; timeout 3 s | `esgotado=True`, `codigo=None`, ~3 s; 0 processos `PING.EXE` com a marca depois |
| 6 | Senha fora do `bench.log` e do erro | script com `Sensivel("Senha#Inventada-77")` ecoada no stdout, num `throw` e no stdin, log real em arquivo; `grep -c Inventada bench.log` | 0 ocorrências; `erros` = "erro com ***"; stdin "***"; `OSError` de programa inexistente sem a senha; log mostra só `[ITC_*: ITC_SENHA]` |
| 7 | Senha com caracteres que o CLIXML escapa | `Inv<ent>&ada"'`, `Inv_x0041_ada`, com acento | `erros` com "erro: ***", sem CLIXML, sem o valor |
| 8 | Acento legível | PowerShell `'ação Ç'`; `cmd /c echo ação`; `netsh wlan show drivers` | "ação Ç"; "ação"; "Versão", "Tipos de rádio", "Proteção de Quadro" sem `�`, `Ã` ou `├` |
| 9 | Política `Restricted` | `-ExecutionPolicy Restricted` com `Get-LocalUser` e `Get-NetAdapter` (CDXML) | os dois funcionam |
| 10 | `SYSTEMROOT` falso no ambiente | `test_sistema32_ignora_systemroot_do_ambiente` | caminho e `PSModulePath` reais; PowerShell inicia |
| 11 | Sem `shell=True` | `test_sem_shell.py` (AST de `src/`) e ruff `TID251` com `import subprocess` num arquivo de `nucleo/` | 4 passed; ruff acusa `TID251 subprocess is banned` |
| 12 | Exceção na tarefa da UI | `test_excecao_vai_para_log_e_sinal_falhou` | `falhou("erro inventado")`, traceback no log |
| 13 | `icacls` antes | `icacls C:\ProgramData\ITC` e `...\ITC\Bench` | herdado: `SISTEMA (F)`, `Administradores (F)`, `<conta-dev> (F)`, `PROPRIETÁRIO CRIADOR (F)`, `Usuários (RX)` e `Usuários (CI)(WD,AD,WEA,WA)` |
| 14 | `icacls` depois de `uv run itc-bench --teste` elevado | idem, e `bench.log` | `ITC`: `SISTEMA:(OI)(CI)(F)`, `Administradores:(OI)(CI)(F)`, `Usuários:(OI)(CI)(RX)`, sem herança; `Bench` e `bench.log` só com essas três entradas herdadas; dono Administradores; código 0 |
| 15 | Usuário comum depois do ACL | `runas /trustlevel:0x20000` com sonda PowerShell | criar arquivo/pasta em `ITC`, criar em `Bench` e `logs`, renomear e apagar `Bench`, renomear, apagar e escrever em `bench.log`: todos negados; ler `bench.log`: conseguiu; pastas intactas |
| 16 | `--dev` sem admin depois do ACL | `runas /trustlevel:0x20000 "itc-bench.exe --dev --teste"` | código 0; "Sem permissão em C:\ProgramData\ITC\Bench\logs; log gravado em …\AppData\Local\ITC\Bench\logs"; "Sem administrador: ACL de C:\ProgramData\ITC não aplicado." |
| 17 | Junction recusada | `test_junction_na_raiz_e_recusada_antes_de_criar`, `test_junction_dentro_da_arvore_e_recusada`, `test_link_simbolico_de_arquivo_e_recusado` (junction real por `CreateJunction`) | `PontoDeReparse`; nada criado no alvo; ACL do alvo inalterado |
| 18 | Arquivo que nega acesso aos Administradores | `test_arquivo_sem_acesso_para_admins_e_recuperado` (dono SYSTEM, só SYSTEM no DACL) | primeira passada falha com código 5 no callback; com os privilégios, dono vira Administradores |
| 19 | Falha que sobra | `test_falha_que_sobra_vira_erro` (mock) | `ErroAcl` depois de 2 tentativas; na entrada vira log e `QMessageBox.warning` |

## Fora do escopo

Contas e qualquer backend do Configurador (Módulo 06 em diante), login, API, instalador. A subpasta
sem leitura para Usuários, para arquivos DPAPI, é criada no Módulo 04 (ADR-011).
