# Módulo 16 — Atualização automática

Branch `feat/modulo-16-atualizacao`, a partir de `develop` em `a6f6def` (com o Módulo 15).
Desenho aprovado em `.conversa/para-agent.md` (2026-11-08) com 10 ajustes; defesa do mutex
(ajuste 1) proposta em `.conversa/para-cowork.md` e implementada como proposta. Decisões em
ADR-026 e TA-ADR-033. Nenhuma regra de preparação nova; a única tela nova é a faixa da atualização.

## O que entrou

| Peça | Onde |
|---|---|
| Tabela `bench_versoes`, contador de limite (migração 0007) | `api/app/migrations/0007_20261108_bench_versoes.sql` |
| CLI `publicar`/`listar`/`revogar` com operador | `api/app/bench_versao.py` |
| `GET /v1/bench/versao` e `/versao/arquivo?sha256=` (sessão, `no-store`, `Range`) | `api/app/routes/bench_versao.py`, `config.py`, `.env.example` |
| Verificação ECDSA P-256 pela CNG, chave SPKI | `app/src/itc_bench/nucleo/assinatura.py` |
| Consulta, manifesto, download com retomada, limpeza, instalar ao fechar | `servicos/atualizacao.py` |
| `executor.disparar()` (emenda ao ADR-011) | `servicos/executor.py` |
| Mutex só `Global\ITCBench`, DACL SY/BA, dono conferido | `nucleo/instalacao.py`, `__main__.py` |
| Faixa (Instalar ao fechar, Agora não, Fechar e atualizar agora, "?") e `closeEvent` | `ui/atualizacao.py`, `ui/janela.py` |
| `--teste-atualizacao` para o CI | `__main__.py` |
| Pasta das chaves públicas | `recursos/atualizacao/` |
| Instalador: sem `AppMutex`, `BenchAberto()` por dono, `/ESPERAPID`, recusa de versão menor, `PrepareToInstall` | `instalador/itc-bench.iss` |
| Chaves e assinatura do manifesto (PowerShell 7) | `instalador/gerar-chaves-versao.ps1`, `assinar-versao.ps1` |
| Teste de atualização no runner, API falsa, ACL, prova do mutex | `instalador/testar-atualizacao.ps1`, `api_falsa.py`, `conferir-acl.ps1`, `prova-mutex.ps1` |
| Trava de chaves no build de tag e teste de atualização | `.github/workflows/app-build.yml` |
| Versão 0.16.0 | `itc_bench/__init__.py` |
| Publicar versão, custódia das chaves, falha | `docs/BUILD.md` |
| Passo 13 do roteiro | `docs/testes/maquina-real.md` |

## Ajustes da Etapa 1

| # | Ajuste | Como ficou |
|---|---|---|
| 1 | Mutex criável por usuário comum | Provado no runner (run 42449077920). Sai o `AppMutex`; só conta mutex com dono BA/SY; `/ESPERAPID` é a garantia principal. Teste no CI com usuário comum segurando o nome |
| 2 | `disparar` em ADR próprio | ADR-026 item 5 (emenda ao ADR-011); testes aceitam só `protegido\atualizacao\setup-<sha>.exe` conferido e recusam fora da pasta, nome errado, relativo, texto e arquivo alterado |
| 3 | Manifesto com produto, `AppId` e notas; P1363 | Assinatura antes do JSON; vetor do `ECDsaCng` do .NET; recusas de truncada, DER, chave errada e campo alterado |
| 4 | Duas chaves públicas | `principal.pub` e `reserva.pub`; o CI atualiza com o manifesto assinado pela reserva |
| 5 | `.iss` recusa só menor | `Rebaixamento()`; igual aceito (CI) |
| 6 | `/ESPERAPID` confere o executável | `QueryFullProcessImageNameW` contra a pasta fixa; PID de outro programa não espera (CI). Com o `AppMutex` removido, a pergunta da ordem deixa de existir: as conferências estão no `InitializeSetup` (depois de esperar) e no `PrepareToInstall` |
| 7 | Build de teste nunca distribuível | Tag falha sem as chaves comitadas iguais às do pacote; instaladores de teste em pasta própria, nunca enviados |
| 8 | Limite de download x retomada | Downloads do byte 0 (3/h) e retomadas (10/h) contados em separado (TA-ADR-033) |
| 9 | 206 a `Range`, `no-store`, sem extensão | Testado na API |
| 10 | Riscos aceitos | `%TEMP%` do Inno e falha no meio da cópia na auditoria e no ADR-026 |

## Verificação

| Cenário | Como | Resultado |
|---|---|---|
| Testes do app | `uv run ruff check . && uv run mypy && uv run pytest -q` e `app-ci` ([run 42522700748](https://github.com/ITC-Brasil/itc-bench/actions/runs/42522700748)) | Local: 795 passados, 4 pulados antes dos dois últimos testes; `app-ci` verde |
| Testes novos do app | `tests/test_atualizacao.py` (47 casos), `test_instalacao.py` (mutex) | Passaram |
| Testes da API | `pytest -q` no container | 268 passados; `api-ci` verde ([run 42522700819](https://github.com/ITC-Brasil/itc-bench/actions/runs/42522700819)) |
| Build e instalação | `app-build` [run 42522700911](https://github.com/ITC-Brasil/itc-bench/actions/runs/42522700911) | Verde; todas as conferências do `testar.ps1` |
| Bench elevado aberto | `testar.ps1` passo 6 | Instalação silenciosa recusa; o Bench continua aberto |
| Atualização N → N+1 | `testar-atualizacao.ps1`: 0.16.0 → 0.16.1 pela API falsa, assinada pela reserva | `--teste-atualizacao` sai 0; `DisplayVersion` 0.16.1; marcador do N+1; `ApiUrl` e `protegido\` mantidos; log do Inno com `ESPERAPID`; ACL de 280 itens sem escrita de terceiros nem reparse; `protegido\atualizacao` só SY/BA |
| Recusa: hash errado | API falsa troca bytes | Sai 5; versão N |
| Recusa: redirecionamento | 302 para outro host | Sai 5 |
| Recusa: assinatura de chave fora do pacote | Manifesto assinado por chave estranha | Sai 5 |
| Recusa: versão igual | Manifesto da N | Sai 5 |
| Recusa: `http://` | `ApiUrl` em `http://` | Sai 5 |
| Recusa: Preparação em andamento / retomada | Testes do app | Nada disparado |
| Instalador: menor / igual | 0.16.0 sobre 0.16.1; 0.16.1 sobre 0.16.1 | Recusa; aceita |
| Mutex de usuário comum | Usuário criado no job segura `Global\ITCBench` | `criado=True`; instalação passa |
| Varredura do pacote | `varrer.py dist` (árvore, zips, `PYZ`) e árvore instalada | 635 itens, nada encontrado (o primeiro run achou a sessão de teste montada como constante; corrigido) |
| gitleaks | `gitleaks dir app/dist --redact` | "no leaks found" |
| Endereço e link reais no artefato | Varredura e `https://api.exemplo.invalid` / `127.0.0.1` no CI | Ausentes |
| Commits da branch | `git log -p develop..HEAD` por hosts, contas, SIDs, perfis, checkout | Nada encontrado |
| UAC, SmartScreen, máquina preparada, túnel | — | Pendente (máquina real, com o instalador): passo 13 do roteiro |

## Limites conhecidos

- Obrigatória não bloqueia as telas de ação (desvio do desenho, risco baixo aceito).
- Falha no meio da cópia exige reinstalação manual.
- As chaves públicas reais ainda não estão no repositório: até lá o Bench não instala atualização
  e o build de tag falha.
- A defesa do mutex aguarda o ok do chat de planejamento.

## Passos do responsável

1. Gerar os dois pares (`pwsh -File instalador/gerar-chaves-versao.ps1 -Saida <fora do repo>`) e
   comitar só `principal.pub` e `reserva.pub` na branch.
2. Revisar e fazer o merge do PR.
3. Deploy da API (migração 0007, backup antes).
4. Por versão: tag, Release, assinar, copiar ao servidor, `app.bench_versao publicar`.
5. Passo 13 do roteiro de máquina real.
