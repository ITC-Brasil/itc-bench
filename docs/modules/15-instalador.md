# Módulo 15 — Empacotamento, instalador e CI

Branch `ci/modulo-15-instalador`, a partir de `develop` em `06a156d`. Desenho aprovado em
`.conversa/para-agent.md` (2026-11-08) com 10 ajustes. Decisões em ADR-025 e TA-ADR-032.
Nenhuma tela ou regra de preparação nova; a atualização automática fica para o 16.

## O que entrou

| Peça | Onde |
|---|---|
| PyInstaller `onedir`, janela, sem UPX, `asInvoker`, `VERSIONINFO` pela versão | `app/empacotamento/itc-bench.spec` |
| Ícone com 8 tamanhos (16–256) e o gerador | `app/empacotamento/itc-bench.ico`, `gerar_ico.py` |
| Grupo `build` (PyInstaller 6.22.3, hooks 2026.9) no lock | `app/pyproject.toml`, `app/uv.lock` |
| Pasta fixa conferida (pai, árvore, reparse, dono, ACL), ambiente `QT_*`/`QML*`/`PYTHON*` retirado, busca de DLL sem `PATH`, mutex para o instalador, `--teste` lendo os recursos | `app/src/itc_bench/nucleo/instalacao.py`, `__main__.py` |
| `--teste` nunca altera, nem elevado | `nucleo/elevacao.py` |
| `ProgramFilesDir` e pasta de instalação pelo HKLM | `nucleo/caminhos.py` |
| Endereço da API sem credencial, query, fragmento ou espaço | `servicos/api.py` |
| Versão 0.15.0 | `itc_bench/__init__.py` |
| Instalador Inno Setup 6.7.4 (endereço por `/APIURL=` ou página, `AppMutex`, desinstalação (b) com aviso) | `instalador/itc-bench.iss` |
| Build, teste de instalação no runner, varredura do pacote | `instalador/build.ps1`, `testar.ps1`, `varrer.py` |
| Workflow: PR compila, varre e testa; tag cria Release em rascunho | `.github/workflows/app-build.yml` |
| Lock da API com hash e `--require-hashes` (pendência do 14) | `api/requirements*.txt`, `api/Dockerfile`, `api-ci.yml`, `AGENTS.md` |
| Procedimento de build, instalação, troca do endereço e desinstalação | `docs/BUILD.md` |
| Passo 0 (instalador) no roteiro de máquina real | `docs/testes/maquina-real.md` |

## Ajustes da Etapa 1

| # | Ajuste | Como ficou |
|---|---|---|
| 1 | Ambiente do usuário no processo elevado | `limpar_ambiente()` antes do `QApplication` (empacotado e `uv run`), `QT_PLUGIN_PATH` de volta para o pacote, `SetDefaultDllDirectories` + `AddDllDirectory`. Bootloader do PyInstaller 6 ignora `PYTHONPATH`: confirmado no runner (`--teste` com `PYTHONPATH` e `QT_*` hostis sai 0; o app recusaria se `sys.path` tivesse entrada fora do pacote). Teste `test_main_limpa_o_ambiente_antes_do_qt` injeta as variáveis |
| 2 | `--teste` elevado | `modo_admin` falso com `--teste`; `test_teste_elevado_roda_sem_admin`; no runner, log com `admin=False` |
| 3 | Pais, pasta fixa, limite | `conferir_pasta` confere `Program Files\ITC`, compara com `ProgramFilesDir` do HKLM e registra o limite (detecta, não impede) no ADR-025 |
| 4 | Varredura do `PYZ`, zips e instalador | `varrer.py` abre o arquivo do PyInstaller embutido no EXE e o `PYZ` módulo a módulo, os `.zip`, e roda sobre `dist\` e sobre a árvore instalada no runner |
| 5 | Só o CI gera artefato distribuível | `docs/BUILD.md`, ADR-025 |
| 6 | Inno: hash, `{tmp}`, `AppMutex`, upgrade | 6.7.4 com SHA-256 da release; nada de `{tmp}`; `CloseApplications=no` + mutex; upgrade preserva `protegido\` e `ApiUrl` (testado) |
| 7 | Reparse antes de apagar `protegido\`; sem atalho público | `EhReparse` na pasta e nos pais antes do `DelTree`; atalho só no Menu Iniciar (testado) |
| 8 | Endereço no log do Inno; recusas no CI | Limite no ADR-025; CI testa nova sem `/APIURL`, `http://`, credencial, query, fragmento e `https://` vazio |
| 9 | `--require-hashes` também no dev | `requirements-dev.txt` com hash, `api-ci` com `--require-hashes` |
| 10 | Status do ADR-002 | Atualizado |

Achado no caminho: o PyInstaller empacotava o `libcrypto-3-x64.dll` de outro programa achado no
`PATH` da máquina de build, e o `_ssl` não carregava (o EXE saía com 1 antes do log). O `.spec`
fixa o OpenSSL da pasta `DLLs` do Python.

## Verificação

| Cenário | Como | Resultado |
|---|---|---|
| ruff, mypy, pytest do app | `uv run ruff check . && uv run mypy && uv run pytest -q` (local) e `app-ci` | 740 passados, 4 pulados (local); `app-ci` verde |
| Testes novos | `tests/test_instalacao.py` (ambiente, critério de ACL em 13 SDDLs, pasta fixa, pai, arquivo gravável, junction real, recursos, mutex), `test_elevacao`, `test_api_cliente` (6 URLs novas), `test_invariantes` (lista fechada com `nucleo/instalacao.py`) | Passaram |
| API com lock com hash | `pip install --require-hashes -r requirements-dev.txt && pytest -q` no container; `docker build api` | 246 passados; imagem constrói; versões iguais às de antes |
| Build local | `pyinstaller ... itc-bench.spec` e `ISCC /DAppVersion=0.15.0` | EXE e instalador gerados (35 MB); `--teste` fora da pasta fixa sai 3 com "Pasta de instalação recusada" |
| Build no CI | [run 42444989319](https://github.com/ITC-Brasil/itc-bench/actions/runs/42444989319) (`app-build`, `windows-2025`) | Verde |
| Instalação silenciosa no runner | `testar.ps1` | Código 0; EXE na pasta fixa; recursos com a contagem do fonte |
| Recusas do instalador | Nova sem `/APIURL`; `http://`; `https://u:s@`; `?q=1`; `#f`; `https://` | Todas ≠ 0; nada instalado |
| ACL da pasta | Regras por SID e máscara de escrita em 318 itens (pai, pasta, árvore); sem reparse | Sem escrita além de SYSTEM, Administradores, TrustedInstaller e CREATOR OWNER |
| Versão | `VersionInfo.ProductVersion`, `DisplayVersion`, `InstallLocation` | 0.15.0, 0.15.0, `C:\Program Files\ITC\Bench` |
| `ApiUrl` | `HKLM\SOFTWARE\ITC\Bench` | `https://api.exemplo.invalid` gravado |
| EXE instalado sem GUI | `ITC Bench.exe --teste` com `PYTHONPATH` e `QT_*` hostis | 0; log com a versão, "Recursos: N arquivos lidos", variáveis ignoradas, `admin=False` |
| Bench aberto | Instalação silenciosa com o Bench em `--dev` | Recusada; Bench continua aberto |
| Upgrade por cima | Mesma build sem `/APIURL`; depois com outro `/APIURL` | Mantém `ApiUrl` e `protegido\`; troca o endereço |
| Desinstalação silenciosa | `unins000.exe /VERYSILENT` | Somem pasta, atalho, chave de desinstalação, `HKLM\SOFTWARE\ITC\Bench` e `protegido\`; sobra só `logs\`; aviso no log |
| Varredura do artefato | `uv run --group build python ../instalador/varrer.py dist` e sobre a árvore instalada (CI) | 674 itens (inclui o `PYZ` descomprimido e o `base_library.zip`); nada encontrado |
| Varredura com dados da máquina de dev | Mesmo script no build local, `--extra` com nome da máquina, usuário e pasta do checkout (lista no scratchpad) | Nada encontrado |
| gitleaks no pacote | `gitleaks dir app/dist --redact` (CI) | "no leaks found" |
| Endereço real ausente | Nenhum endereço no `.iss`, no workflow nem no EXE; o CI usa `api.exemplo.invalid`; varredura de URL no código do Bench | Ausente |
| SHA-256 publicado | `SHA256SUMS` do artefato e `sha256sum` local | `7d2660c2…c2cf0f`, iguais |
| Commits da branch | `git log -p develop..HEAD` contra nome da máquina, usuário, perfil, checkout, SIDs, tokens | Nada encontrado |

## Máquina real

| Cenário | Situação |
|---|---|
| UAC e SmartScreen no instalador sem assinatura | Pendente (máquina real, com o instalador) — passo 0.1 |
| Assistente com GUI (página do endereço, recusas) | Pendente (máquina real, com o instalador) — 0.2, 0.3 |
| ACL e versão vistas pelo técnico | Pendente (máquina real, com o instalador) — 0.4, 0.5 |
| Assistente com o Bench aberto | Pendente (máquina real, com o instalador) — 0.6 |
| Upgrade por cima numa máquina preparada | Pendente (máquina real, com o instalador) — 0.7 |
| Bench copiado para fora da pasta fixa, elevado | Pendente (máquina real, com o instalador) — 0.8 |
| Desinstalação com a preparação aplicada | Pendente (máquina real, com o instalador) — 0.9 |

## Limites conhecidos

- A conferência da pasta roda depois de Python e Qt carregarem; ela detecta, não impede.
- O `/LOG` do Inno grava o endereço da API.
- Usuário comum consegue criar o mutex `ITCBench` local e travar a atualização silenciosa.
- Sem assinatura: "Editor desconhecido" no UAC e aviso do SmartScreen.
- O gitleaks em modo diretório leu ~7 MB do pacote (pula binários grandes); a varredura própria
  cobre o resto.

## Passos do responsável

1. Revisar e fazer o merge do PR.
2. Deploy da API pelo `api-deploy.yml` (o `Dockerfile` agora instala com `--require-hashes`).
3. Para o roteiro de máquina real: baixar o instalador do artefato do `app-build` (ou criar a tag
   `v0.15.0` na `main` para a Release em rascunho), conferir o SHA-256 e seguir o passo 0 de
   `docs/testes/maquina-real.md`.
