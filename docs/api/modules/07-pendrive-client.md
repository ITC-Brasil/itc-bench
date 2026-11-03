# Módulo 07 — Cliente no pendrive (Fase 2)

**Branch:** `module/07-pendrive-client` (a partir da `module/06-initial-deploy`) · **Data:**
2026-09-28 · **Escopo:** `PROMPT_CLAUDE_CODE.md` §15, Módulo 07, mais a correção do
`usuarioLogado` pedida pelo responsável

O pendrive passa a enviar o diagnóstico completo à API e a mostrar o laudo da IA, com
queda para o relatório determinístico da Fase 1 em qualquer falha. O ponto único
continua sendo `pendrive/lib/Util-Relatorio.ps1`. O módulo também corrige o
`usuarioLogado`, visto na verificação da frota: o contrato sobe para 1.2 (TA-ADR-018) com
`usuarioExecucao` e `usuarioSessao`, e a API passa a aceitar 1.2.

## O que foi implementado

### Arquivos

| Arquivo | Conteúdo |
|---|---|
| `pendrive/lib/Util-Sessao.ps1` | `$script:VersaoSchema = '1.2'`; `Get-UsuarioSessao` (`Win32_ComputerSystem.UserName`, `null` sem usuário no console); `New-Sessao` e `Save-Sessao` gravam `usuarioExecucao` (`$env:USERNAME`) e `usuarioSessao` no lugar de `usuarioLogado`; `ferramentaVersao` `1.2 (Fase 2)` |
| `pendrive/lib/Util-Relatorio.ps1` | Cliente da API (ver "Cliente") e `Write-RelatorioSessao -UsarIA` |
| `pendrive/menu.ps1` | Só a opção `[1] Diagnóstico completo` passa `-UsarIA` |
| `pendrive/config/api.example.json` | Formato do `api.json` com valores de exemplo: `url`, `tokenCarreta`, `cfAccessClientId`, `cfAccessClientSecret`, `timeoutSegundos` (120 desde 2026-09-29; era 90) |
| `pendrive/Testar-Ferramenta.ps1` | Seção "Cliente da API" (27 verificações) e os casos do contrato 1.2 |
| `pendrive/SCHEMA.md` | Versão 1.2 no histórico, `usuarioExecucao`/`usuarioSessao`, `relatorio.md` e `chamado.md` |
| `pendrive/README.md` | Preparação do `api.json`, mensagens de falha e o que fazer, arquivos novos da sessão |
| `api/app/normalizacao.py` | `VERSOES = ("1.0", "1.1", "1.2")` |
| `api/tests/test_normalizacao.py`, `test_prompt.py`, `test_relatorio.py` | 1.2: os dois campos preservados, `usuarioSessao` no prompt sem a conta que executou, `POST` aceito |
| `docs/TOKENS.md` | Cenário 7 com o formato real do `api.json` e o resultado parcial |

### Contrato 1.2

| Campo | 1.1 | 1.2 |
|---|---|---|
| `sessao.usuarioLogado` | `$env:USERNAME` | removido |
| `sessao.usuarioExecucao` | — | `$env:USERNAME`: a conta que executou (numa sessão elevada, a que elevou) |
| `sessao.usuarioSessao` | — | `Win32_ComputerSystem.UserName` (`DOMINIO\usuario`), ou `null` |

A API normaliza 1.0 e 1.1 como no Módulo 03 (`usuarioLogado` → `usuarioExecucao`,
`usuarioSessao: null`) e mantém os dois campos da 1.2. O prompt continua sem
`usuarioExecucao` e recebe `usuarioSessao` (TA-ADR-023). O prefixo `DOMINIO\` vai junto: é
o valor da fonte, sem tratamento.

### Cliente

Tudo em `pendrive/lib/Util-Relatorio.ps1`:

| Função | Papel |
|---|---|
| `Read-ConfigApi` | Lê `config\api.json` a partir de `$script:RaizRelatorio` (pai do `lib`, TA-ADR-013). Arquivo ausente, JSON inválido ou campo vazio → `$null`. Sem `timeoutSegundos`, usa 120 (era 90 até 2026-09-29) |
| `New-CorpoApi` | Monta `{"sessao":…,"modulos":{…},"correcoes":…}` concatenando o texto dos arquivos da sessão (só `disco`, `eventlog`, `rede`, `processos`, `bateria`), sem `ConvertTo-Json`, e devolve os bytes UTF-8 |
| `Send-HttpApi` | Uma requisição com `Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -TimeoutSec`. Nunca lança: devolve `status`/`corpo`/`retryAfter` ou `falha` = `timeout`/`inacessivel`. Decodifica o corpo como UTF-8 a partir de `RawContentStream` |
| `$script:TransporteApi` | Bloco que chama `Send-HttpApi`; o autoteste troca por um servidor simulado |
| `Get-FalhaApi` | Traduz a resposta em `motivo` e mensagem ao técnico (tabela abaixo) |
| `Invoke-RelatorioApi` | Força TLS 1.2, `GET /v1/saude` (timeout de até 15 s, só com os cabeçalhos da Cloudflare), `POST /v1/relatorio` com `Authorization: Bearer` e os dois `CF-Access-*`, valida `relatorio_md` e `chamado_titulo` |
| `Save-RelatorioApi` | `relatorio.md` (com um comentário HTML de cabeçalho: modelo, diagnóstico, data) e `chamado.md` (`# título` + descrição), UTF-8 sem BOM |
| `Write-RelatorioIA` | Mostra o laudo, o chamado e os caminhos, com o lembrete de conferir as evidências (TA-ADR-016) |
| `Write-RelatorioSessao -UsarIA` | Tenta a API; sucesso → mostra o laudo e sai; falha → `Relatório da IA indisponível: <mensagem>` e o relatório determinístico. Sem `-UsarIA`, o relatório determinístico indica o `relatorio.md` quando ele existe |

| Resposta | `motivo` | Mensagem (resumo) |
|---|---|---|
| Sem `api.json` válido | `nao_configurada` | API não configurada |
| Conexão recusada, DNS, TLS, redirecionamento | `inacessivel` | API inacessível |
| Tempo esgotado | `timeout` | A API não respondeu a tempo |
| Saúde `200` sem `{"status":"ok"}` (página da Cloudflare) | `borda` | Resposta inesperada; conferir o service token |
| Saúde com outro status | `api_indisponivel` | API fora do ar |
| `3xx` | `borda` | A Cloudflare pediu login |
| `401` | `token_recusado` | Token da carreta recusado; avisar a TI |
| `403` | `borda` | Acesso recusado pela Cloudflare |
| `413` | `corpo_grande` | Sessão acima de 512 KB |
| `429` | `limite` | Tente em N minuto(s), de `Retry-After` |
| `400` (inclusive o texto puro do uvicorn) e `422` | `sessao_recusada` | Pendrive desatualizado; avisar a TI |
| `502`/`503` | `ia` | A IA está indisponível agora (código `ia_*`) |
| `200` sem `relatorio_md`/`chamado_titulo` | `resposta_invalida` | Formato inesperado |

### Escolhas feitas no caminho

- **Só o `[1]` usa a API.** Um módulo avulso daria um laudo parcial e mais uma linha no
  histórico da máquina. `[2]` a `[6]` e `[R]` mostram o relatório determinístico.
- **Corpo pelo texto dos arquivos.** `ConvertFrom-Json` + `ConvertTo-Json` no PS 5.1
  corta a profundidade e muda tipos; a concatenação envia exatamente o que foi gravado.
- **Corpo da resposta como UTF-8 explícito.** A API não manda `charset`, e o PS 5.1
  decodificaria como ISO-8859-1, estragando os acentos do laudo.
- **`-MaximumRedirection 0`.** Sem o service token, a Cloudflare Access redireciona para
  a página de login, que o PS seguiria até um `200` com HTML. O redirecionamento vira
  falha, e a saúde exige o JSON `{"status":"ok"}`.
- **A saúde não leva o token da carreta**, só os cabeçalhos da borda: a rota é pública e
  não precisa dele.
- **Nenhum ADR novo.** A versão 1.2 segue a regra do TA-ADR-018 (renomear e acrescentar
  campo = minor, com linha no `SCHEMA.md` e normalização na API).

## Verificação realizada

Ambiente: máquina de desenvolvimento (não da frota), Windows 11 Pro 10.0.26340,
PowerShell 5.1.26100.9502; API na imagem `python:3.12.14-slim-trixie` e no container
local com a porta de teste 3099 e a chave `changeme`, derrubado com `docker compose down -v`
ao fim. Tokens de teste mascarados.

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| Autoteste do pendrive | `Testar-Ferramenta.ps1 -SemPausa`, commit `e0603e4` | ✅ 112 OK, código de saída 0 (eram 83 no 00.1; +2 do contrato 1.2 e +27 do cliente) |
| Contrato 1.2 | Autoteste: `Save-Sessao` e `Get-UsuarioSessao` | ✅ `versaoSchema` 1.2 na sessão e no módulo; `usuarioExecucao` e `usuarioSessao` gravados; `usuarioLogado` ausente; `Get-UsuarioSessao` devolve `DOMINIO\usuario` nesta máquina |
| Sem `api.json` | Autoteste | ✅ `nao_configurada`; incompleto também; `api.example.json` lido com todos os campos |
| Corpo | Autoteste | ✅ sessão e só módulos conhecidos; acento preservado em UTF-8 |
| API indisponível | Autoteste, conexão real na porta 9 (recusada) | ✅ `inacessivel` |
| Timeout | Autoteste, `TcpListener` real que aceita e não responde, `timeoutSegundos` 2 | ✅ `timeout`, em menos de 10 s |
| Token revogado (401), 429, 503, 422, 413, 400 em texto puro, 200 fora do formato, saúde com página da Cloudflare | Autoteste, transporte simulado | ✅ o `motivo` e a mensagem de cada linha da tabela |
| Sucesso | Autoteste, transporte simulado | ✅ `POST` com `Bearer` e os dois `CF-Access-*`, saúde sem `Authorization`, corpo igual ao montado, TLS 1.2 ligado; `relatorio.md` e `chamado.md` em UTF-8 com os acentos; laudo e chamado na tela |
| Queda para o determinístico | Autoteste, `-UsarIA` com `401` simulado | ✅ "Relatório da IA indisponível: Token da carreta recusado" seguido do relatório padrão; sem `-UsarIA`, a indicação do `relatorio.md` |
| O teste de TLS pega o defeito | Mutação numa cópia do `pendrive/`: linha do `SecurityProtocol` removida | ✅ só "TLS 1.2 habilitado" falha |
| Cliente real contra a API real (local) | `Invoke-RelatorioApi` com token válido | ✅ `ia` (`ia_nao_configurada`), em 0,5 s: passou pela saúde, pelo token e pelo schema |
| Token revogado contra a API real | `revoke` e nova chamada | ✅ `token_recusado` |
| Sessão 1.2 real | `New-Sessao` + coletor de rede reais, corpo de 25 784 bytes enviado à API local | ✅ aceito (`ia`); banco com `versao_schema` 1.2, `usuarioExecucao` e `usuarioSessao`, sem `usuarioLogado` |
| API: 1.2 | Suite na imagem, commit `e27fd43` | ✅ 145 passed |
| Encoding | Três primeiros bytes dos `.ps1` alterados | ✅ `ef bb bf` (BOM) em `Util-Relatorio.ps1`, `menu.ps1`, `Testar-Ferramenta.ps1`; CRLF mantido |
| Laudo real pela borda | — | **Não executado** — depende da chave real do Go e do Módulo 06 (etapa 12 do roteiro) |
| Diagnóstico completo numa máquina da frota | — | **Não executado** — passo do responsável, depois do deploy |

Um commit intermediário (`53b9dd4`) foi feito com um teste falhando: o `"\a"` na
fixture 1.2 virou o caractere BEL. A correção está em `e27fd43`; a suite final passa.

## Decisões

Nenhum ADR novo. O contrato 1.2 segue o TA-ADR-018.

## Dependências entre módulos

- **Módulo 06:** o `api.json` de cada pendrive precisa do token da carreta (etapa 10) e
  do service token (etapa 8). A etapa 12 é a verificação real deste cliente.
- **Fase 3:** `relatorio.md` e `chamado.md` ficam na pasta da sessão, ao lado dos JSONs.

## Pontos de atenção

- **Pendrives antigos continuam em 1.1.** A API aceita e normaliza; o `usuarioSessao`
  dessas sessões é `null`.
- **O `api.json` tem segredos** (token da carreta e service token): fica só no pendrive
  e no Vaultwarden. Pendrive perdido = cenário 2 do `docs/TOKENS.md`.
- **Conexão recusada leva cerca de 2 s no Windows** antes de falhar; com a API fora do ar
  e sem internet, o técnico espera até `timeoutSegundos` (120) no pior caso.
- **`timeoutSegundos` passou de 90 para 120 (2026-09-29).** Em produção, um relatório real
  levou 75 s (TA-ADR-026); com 90 s no pendrive, a margem sobre o timeout da IA no servidor
  (até 90 s) era nenhuma. O padrão de `Read-ConfigApi`, usado quando o `api.json` não tem o
  campo, também passou a 120. Com 120, quem encerra uma espera longa é o servidor (erro
  `ia_timeout`) ou a Cloudflare (cerca de 100 s), nunca o pendrive antes deles.
- **O laudo é apoio.** A tela lembra de conferir as evidências; nenhuma ação é executada
  a partir dele (TA-ADR-016).

## Commits

```
16b4a82 feat(pendrive): split usuarioLogado into usuarioExecucao and usuarioSessao
53b9dd4 feat(api): accept session schema 1.2
e27fd43 test(api): fix backslash in the 1.2 session user fixture
e0603e4 feat(pendrive): send full diagnosis to the API with deterministic fallback
```

O commit `docs: document module 07 pendrive client` fecha a lista.
