# TRD — ITC Bench

Requisitos técnicos. O que ainda não existe está marcado como **planejado**, com o módulo.

## Stack

A definir no Módulo 01 (manifesto ainda não existe). Decidido em ADR-002: Python, PySide6,
PyInstaller, instalador Windows (Inno Setup ou WiX, decidido no módulo de empacotamento).
Diagnóstico: reaproveita os scripts PowerShell 5.1 do pendrive ou porta para Python — decidido
no módulo de Diagnóstico.

## Arquitetura

```
ITC Bench (Windows, UAC admin)
 ├─ UI PySide6 (7 grupos)          ← interface_qt/ do Configurador como base
 ├─ backend/ (ações no Windows)    ← backend/ do Configurador, por composição, não mixins
 ├─ executor seguro de comandos    ← Módulo 02
 ├─ cliente da API (sessão)        ← Módulos 03–04
 └─ cache local DPAPI              ← Módulo 04
        │ HTTPS
        ▼
API do Técnico Assistente (repo próprio, FastAPI + SQLite)
 ├─ GLPI (login do técnico)        ← módulo isolado na API (ADR-005)
 ├─ NocoDB base "ITC Bench"        ← cadastros (ADR-006)
 └─ laudo por IA                   ← POST /v1/relatorio (existente)
```

O Bench nunca abre conexão com GLPI ou NocoDB (ADR-005, ADR-006).

## Caminhos (planejado, Módulo 01)

| O quê | Onde |
|---|---|
| Binários | `%ProgramFiles%\ITC\Bench` |
| Dados da máquina, cache | `%ProgramData%\ITC\Bench` |
| Log rotativo | `%ProgramData%\ITC\Bench\logs` |
| Preferências do técnico | `%LOCALAPPDATA%\ITC\Bench` |

Substitui `get_paths()` de `configurador/config.py`, que grava em `BASE_DIR` (pasta do EXE) e
tem efeito colateral no import (cria pastas, move arquivos, lê segredos).

## Execução de comandos (planejado, Módulo 02)

Padrão de `configurador/backend/contas.py`: `_powershell(script, **variaveis)` passa o script
como argumento e os dados por variável de ambiente; `nome_valido()` valida antes. Todos os
`shell=True` do Configurador são reescritos assim ao migrar a tela. Casos conhecidos:
`usuarios.py` (`net user "{user}" "{senha}"`), `remoto.py:165` (senha do AnyDesk por `echo`),
`sistema.py:21` (`Rename-Computer`), `desinstalador.py:63` (UninstallString executada com shell).
Requisitos: timeout, código de saída checado, saída para o log, senha nunca na linha de comando.

## Autenticação (planejado, Módulo 03, exige tecnico-assistente)

- Bench envia usuário e senha à API; a API valida no GLPI, exige o grupo de técnicos, limita
  tentativas e devolve sessão. Rotas exatas: a definir no repo da API.
- Sem internet: último login daquele técnico naquela máquina vale 7 dias; hash guardado com DPAPI.
- Bloqueio após 15 minutos parado.
- UAC continua obrigatório (elevação por `ShellExecuteW runas`, já usado em `app_qt.py`).

## Cadastros (planejado, Módulo 04, exige tecnico-assistente)

Após o login, o Bench pede Servidores, Instaladores, WiFi e Unidades à API e guarda cópia
protegida com DPAPI. Esquema: `docs/BACKEND-SCHEMA.md`.

## Instaladores

Download sob demanda com SHA-256 conferido contra a tabela Instaladores, ou winget. Nada de
binário de terceiro no repositório nem no instalador do Bench.

## Log

Arquivo rotativo em `%ProgramData%\ITC\Bench\logs`, com técnico, ação e resultado. Na UI, o
`LogBus` (Signal do Qt) do Configurador continua para atualizar a tela a partir de threads.

## Qualidade

Testes, lint e CI: planejado (Módulo 01 define ferramentas; CI no módulo de empacotamento).
Hoje o Configurador não tem nenhum dos três.

## Segurança

Auditoria por módulo com `docs/security/AUDIT-PROMPT.md`. Baseline:
`docs/security/2026-11-03-modulo-00.md`.
