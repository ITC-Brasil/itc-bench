# API — Técnico Assistente

Rotas planejadas em `PROMPT_CLAUDE_CODE.md` §6. Cada uma é documentada aqui, no formato
completo, no módulo que a implementa.

| Rota | Auth | Módulo |
|---|---|---|
| `GET /v1/saude` | pública | 01 |
| `POST /v1/relatorio` | token da carreta | 03 (autenticação no 02) |
| `GET /v1/historico/{hostname}` | token da carreta | 03 (autenticação no 02) |
| `POST /v1/bench/relatorio` | sessão do técnico | 06 do Bench |
| `GET /v1/bench/historico/{hostname}` | sessão do técnico | 06 do Bench |

A documentação interativa (`/docs`, `/redoc`, `/openapi.json`) só existe com
`APP_ENABLE_DOCS=true`. Com o padrão (`false`), as três rotas respondem `404`
(`api/app/main.py`).

## Autenticação e limites

**Módulo:** 02 · **Arquivos:** `api/app/auth.py`, `api/app/body_limit.py` · **Runbook:**
`docs/TOKENS.md`

`POST /v1/relatorio` e `GET /v1/historico/{hostname}` declaram `Depends(exigir_token)`
(Módulo 03). O limite de corpo vale para todas as rotas.

**Cabeçalho do token da carreta:** `Authorization: Bearer itcta_<43 caracteres>`. Os
cabeçalhos do Cloudflare Access (`CF-Access-Client-Id` e `CF-Access-Client-Secret`) são
checados na borda e não usam o `Authorization`.

Ordem das verificações: corpo, depois token, depois limite de requisições.

| Status | Corpo | Quando |
|---|---|---|
| `400` | `{"erro": "requisicao_invalida"}` | `Content-Length` que não é só de dígitos. Atrás do uvicorn, o h11 recusa antes, com `Invalid HTTP request received.` em texto puro |
| `413` | `{"erro": "corpo_grande"}` | Corpo acima de `MAX_BODY_BYTES` (padrão 524288), pelo `Content-Length` ou contado em chunked |
| `401` | `{"erro": "nao_autorizado"}` + `WWW-Authenticate: Bearer` | Sem cabeçalho, esquema diferente de `Bearer`, token mal formado, inexistente ou revogado. A resposta é a mesma nos cinco casos |
| `429` | `{"erro": "limite_excedido"}` + `Retry-After: <segundos até a próxima hora cheia>` | Mais de `RATE_LIMIT_PER_TOKEN_PER_HOUR` (padrão 60) requisições do token na hora cheia UTC (TA-ADR-021) |
| `422` | `{"erro": "requisicao_invalida"}` | Corpo ou parâmetro fora do schema, depois do token (Módulo 03). A resposta nunca devolve o conteúdo enviado |

## Saúde

Rota pública, sem token: é usada pelo health check do deploy, que roda no próprio
glpi-srv em `127.0.0.1` (TA-ADR-009). Ela não devolve versão, caminho do banco nem texto de
erro.

### GET /v1/saude

**Módulo:** 01 · **Arquivo:** `api/app/routes/saude.py`

Auth: pública
Query: nenhuma
Body: nenhum
Response 200: `{ "status": "ok" }`, quando o banco existe e o runner de migrações já rodou
Response 503: `{ "status": "erro" }`, quando o banco está ausente, ilegível ou sem `schema_migrations`

**Verificação do banco:** `db.check()` (`api/app/db.py`) abre o `DATABASE_PATH` em modo
somente leitura (`?mode=ro`, `uri=True`), então nunca cria o arquivo, e executa
`SELECT 1 FROM schema_migrations LIMIT 1`. Um banco apagado com o container no ar
continua em `503` até o próximo start, quando o `lifespan` o recria.

```
curl -s http://127.0.0.1:${APP_PORT}/v1/saude
{"status":"ok"}
```

## Relatório

**Módulo:** 03 · **Arquivos:** `api/app/routes/relatorio.py`, `api/app/normalizacao.py`,
`api/app/prompt.py`, `api/app/prompts/relatorio.md`, `api/app/services/opencode_go.py`

### POST /v1/relatorio

Auth: token da carreta (`Authorization: Bearer itcta_...`)
Query: nenhuma
Body: a sessão da Fase 1 agrupada num objeto, no máximo 512 KB (`pendrive/SCHEMA.md`):

```
{
  "sessao":    { ...conteúdo de sessao.json... },
  "modulos":   { "disco": { ...disco.json... }, "eventlog": {...}, "rede": {...}, "processos": {...}, "bateria": {...} },
  "correcoes": { ...correcoes.json... }        // opcional
}
```

- `sessao.versaoSchema` precisa ser `"1.0"`, `"1.1"` ou `"1.2"`; `sessao.id` com 1 a 120
  caracteres; `sessao.hostname` com letras, dígitos e hífen, até 63 caracteres (espaços
  nas pontas são aceitos e removidos). O hostname é gravado em maiúsculas.
- `modulos` e `correcoes` são opcionais. A chave de cada módulo é o nome do arquivo sem
  `.json`. Módulos fora de `disco`, `eventlog`, `rede`, `processos` e `bateria` são
  ignorados, assim como campos desconhecidos no primeiro nível. Um módulo com
  `status: "erro"` e `dados: null` é aceito.
- A sessão é normalizada para o contrato atual antes de tudo (TA-ADR-018; ver
  `docs/modules/03-ai-report.md` e, para a 1.2, `docs/modules/07-pendrive-client.md`).
- Cliente de referência: `Invoke-RelatorioApi` em `pendrive/lib/Util-Relatorio.ps1`
  (Módulo 07), que monta o corpo com o texto dos próprios arquivos da sessão.

Response 200:

```
{
  "relatorio_md": "## Resumo\n...",       // laudo em Markdown, com "## Avisos da coleta" no fim quando houver
  "chamado_titulo": "Disco C: quase cheio",
  "chamado_descricao": "...",
  "maior_confianca": "ALTA",              // "ALTA" | "MÉDIA" | "BAIXA" | null
  "modelo": "mimo-v2.6-flash",
  "tokens_entrada": 9800,                 // null se o provedor não informar
  "tokens_saida": 950,
  "diagnostico_id": 1
}
```

Falhas da IA respondem rápido, com código interno e sem texto do provedor. O diagnóstico
fica gravado com o código em `diagnosticos.falha`:

| Status | Corpo | Quando |
|---|---|---|
| `503` | `{"erro": "ia_nao_configurada"}` | `OPENCODE_GO_API_KEY` vazia ou `changeme`. O Go não é chamado |
| `503` | `{"erro": "ia_timeout"}` | Sem resposta em `OPENCODE_GO_TIMEOUT_SECONDS` (60 s, TA-ADR-010) |
| `503` | `{"erro": "ia_cota"}` | Go respondeu `402` ou `429` |
| `503` | `{"erro": "ia_indisponivel"}` | Falha de conexão ou `5xx` do Go |
| `502` | `{"erro": "ia_autenticacao"}` | Go respondeu `401` ou `403` (chave inválida) |
| `502` | `{"erro": "ia_recusa"}` | Outro `4xx` do Go |
| `502` | `{"erro": "ia_resposta_invalida"}` | Resposta `200` sem o JSON pedido ou com campo obrigatório vazio |

Mais os `401`, `413`, `422` e `429` de "Autenticação e limites". Para o pendrive
(Módulo 07), qualquer resposta diferente de `200` leva ao relatório determinístico.

### GET /v1/historico/{hostname}

Auth: token da carreta. Qualquer carreta lê o histórico de qualquer hostname, porque uma
máquina pode ser atendida por carretas diferentes.
Query: nenhuma
Body: nenhum
Response 200: os 20 diagnósticos mais recentes do hostname (sem diferenciar maiúsculas),
do mais novo para o mais antigo, sem a sessão completa:

```
{
  "hostname": "TESTE-NB-11",
  "diagnosticos": [
    {
      "diagnostico_id": 1,
      "recebido_em": "2026-09-28 20:10:41",      // UTC
      "carreta": "UM-03",
      "sessao_id": "2026-09-28_1510_TESTE-NB-11",
      "projeto": "BSBIA",
      "sub_perfil": "aluno",
      "versao_schema": "1.1",
      "resumo": { "volumes": [...], "discos": [...], "eventosPesoAlto": [...], "totalGruposEventos": 3,
                  "bateriaDesgastePercentual": null, "memoriaPercentualEmUso": null, "internetOk": null },
      "falha": "ia_nao_configurada",             // null quando o relatório foi gerado
      "relatorio": null                          // ou { "maior_confianca", "chamado_titulo", "modelo" }
    }
  ]
}
```

Response 422: `{"erro": "requisicao_invalida"}` para hostname fora do padrão.

## Bench (login do técnico)

Rotas do ITC Bench (ADR-013). O prefixo `/v1/bench/` passa pela borda **sem** o service token
do Cloudflare Access (aplicação Access com Bypass só nesse caminho); a proteção é a sessão e o
limite de tentativas no SQLite. A integração com o GLPI fica só em `app/services/glpi.py`
(API v2: `POST /api.php/token` com grant `password`, depois `GET /api.php/v2/session`; acesso
pelo campo `profiles`, todos os perfis do usuário em qualquer entidade).

O IP do cliente vem do `CF-Connecting-IP` (lido só nestas rotas; confiável porque a porta escuta
só em `127.0.0.1`, TA-ADR-009). Sem o cabeçalho, ou malformado, vale o IP da conexão.

### POST /v1/bench/login

```json
{"usuario": "login do GLPI", "senha": "...", "maquina": "NB-EXEMPLO-01"}
```

`usuario` é normalizado (sem espaços nas pontas, minúsculas); `maquina` segue a regra de hostname
do `/v1/relatorio`. Campos a mais → `422`.

| Código | Corpo | Quando |
|---|---|---|
| 200 | `{"sessao": "itcbs_…", "expira_em": "AAAA-MM-DDTHH:MM:SSZ", "tecnico": {"login", "nome"}}` | Senha certa e o usuário tem o perfil `GLPI_PERFIL_TECNICOS_ID` em qualquer entidade |
| 401 | `{"erro": "credenciais_invalidas"}` | Senha errada, usuário inexistente ou inativo (mesma resposta) |
| 403 | `{"erro": "fora_do_perfil"}` | Senha certa, sem o perfil de técnicos em nenhuma entidade |
| 429 | `{"erro": "limite_excedido"}` + `Retry-After` (s) | 5 falhas do usuário ou 20 do IP na janela fixa de 15 min; conferido antes do GLPI |
| 503 | `{"erro": "glpi_indisponivel"}` | GLPI fora, lento (`GLPI_TIMEOUT_SECONDS`), resposta fora do formato, ou `GLPI_*`/`BENCH_LOGIN_HMAC_KEY` vazios, ou `GLPI_URL` `http://` para host público |
| 422 | `{"erro": "requisicao_invalida"}` | Corpo inválido; nada da entrada volta na resposta |

Contam como falha só `401` e `403`; o login certo zera as falhas do usuário; `503` não conta.
A sessão vale **12 h** (`BENCH_SESSAO_HORAS`), sem renovação; no banco só o SHA-256.

Auditoria (`bench_login_auditoria`): uma linha por tentativa e por logout. O usuário por extenso
só aparece quando o GLPI o reconheceu (`ok`, `fora_do_perfil`, `logout`); nos outros casos, e na
chave do limite, `h:` + 16 hex do `HMAC-SHA256(BENCH_LOGIN_HMAC_KEY, usuario)`. Senha nunca.
Ao bater o limite, alerta ntfy com o HMAC e o IP. Linhas de auditoria e sessões vencidas há
mais de 90 dias são apagadas a cada login certo.

### GET /v1/bench/sessao

`Authorization: Bearer itcbs_…` → `200 {"tecnico": {"login", "nome"}, "expira_em"}`; ausente,
malformada, vencida ou revogada → `401 {"erro": "nao_autorizado"}`. Um token `itcta_` não vale
aqui, e uma sessão `itcbs_` não vale nas rotas da carreta.

### POST /v1/bench/logout

`Authorization: Bearer itcbs_…` → `204` sempre; revoga a sessão se ela for válida.

### GET /v1/bench/saude

Igual a `GET /v1/saude`, no prefixo que passa pela borda sem service token.

### GET /v1/bench/cadastros

Cadastros da base "ITC Bench" no NocoDB (ADR-014, TA-ADR-027), para o Bench guardar no cache
DPAPI. Exige `Authorization: Bearer itcbs_…` (o `304` também). Leitura do NocoDB só em
`app/services/nocodb_cadastros.py`; rota em `app/routes/cadastros.py`.

Parâmetro opcional `unidade=<Unidades.Codigo>`: sem ele, todo o Wi-Fi (fase de bancada); com
ele, só o Wi-Fi daquela unidade. Servidores, Instaladores e Unidades vêm sempre inteiros.

| Código | Corpo | Quando |
|---|---|---|
| 200 | ver abaixo, com `ETag: "<versao>"` e `Cache-Control: no-store` | Sessão válida |
| 304 | vazio, com o `ETag` | `If-None-Match` igual à versão desta resposta (com o mesmo filtro) |
| 401 | `{"erro": "nao_autorizado"}` | Sessão ausente, malformada, vencida ou revogada |
| 422 | `{"erro": "unidade_invalida"}` | `unidade` fora das Unidades ativas (diferencia maiúsculas) |
| 422 | `{"erro": "requisicao_invalida"}` | `unidade` vazia ou com mais de 32 caracteres |
| 503 | `{"erro": "cadastros_indisponivel"}` | Leitura não configurada, NocoDB fora sem cópia em memória, ou cópia com mais de 24 h. Não mexe na sessão e não é o `glpi_indisponivel` do login |

```json
{
  "versao": "<64 hex>", "lido_em": "AAAA-MM-DDTHH:MM:SSZ", "defasado": false, "unidade": null,
  "servidores": [{"id": 1, "servico": "RustDesk", "papel": "servidor de ID", "valor": "...", "versao": "", "observacao": "", "publico": true}],
  "instaladores": [{"id": 1, "programa": "...", "versao": "...", "arquivo": "...", "sha256": "<hex minúsculo>", "link": "https://...", "observacao": "", "tipo": "instalador", "categoria": "Programas", "identificador": "", "argumentos": "", "deteccao": "", "modo": "quiosque"}],
  "wifi": [{"id": 10, "ssid": "...", "senha": "...", "unidade": "UM-01", "categoria": "Carreta", "atualizado_em": "..."}],
  "unidades": [{"id": 1, "codigo": "UM-01", "nome": "...", "cidade": "...", "uf": "..", "tag_glpi": "...", "perfil_padrao": "..."}],
  "descartados": {"wifi": [12]}
}
```

- Só linhas com `Ativo = true`. Linha sem o campo de exibição (`Servico`, `Programa`, `SSID`,
  `Codigo`) ou Wi-Fi com unidade fora das Unidades ativas sai em `descartados` (só o `Id`).
- **Instaladores por `tipo`** (TA-ADR-029): `instalador`, `winget`, `webapp` ou `papel`; vazios de
  `tipo`, `categoria` e `modo` saem como `instalador`, `Programas` e `quiosque`. Tipo, categoria
  ou modo fora da lista, winget sem ID no formato e Web App sem `https://` com host saem em
  `descartados` (log com o `Id` e o motivo, sem valor).
- **`tipo = papel`** (TA-ADR-030): papel de parede do Bench. Exige `arquivo` `.jpg`/`.jpeg`/`.png`,
  `sha256` com 64 hexadecimais e `link` `https://` com host; senão sai em `descartados` com
  `papel_invalido`.
- **Segredos:** `servidores[].valor` e `observacao` são segredo quando `publico` é `false`
  (`Publico` vazio ou ausente no NocoDB = segredo); `wifi[].senha` sempre. Saem em texto nesta
  resposta (o Bench precisa deles offline) e em nenhum log ou tabela.
- **`versao`:** HMAC-SHA256 do JSON canônico da resposta com `BENCH_CADASTROS_ETAG_KEY` (sem
  ela, chave aleatória por processo). Não muda se o NocoDB não mudou.
- **Cópia em memória** por `NOCODB_CADASTROS_TTL_SECONDS` (60): uma leitura do NocoDB por vez; os
  outros pedidos recebem a cópia (só esperam quando não há nenhuma). NocoDB fora: a cópia sai com
  `"defasado": true` e o `lido_em` dela, por até 24 h. Uma leitura que falhou não se repete
  dentro do TTL.
- Auditoria `bench_cadastros_entregas` (migração `0005`): uma linha por `200` (sessão, usuário,
  unidade, horário, 12 caracteres da versão), apagada depois de 90 dias. O log da API tem as
  contagens e a versão curta; nunca valor, SSID, link, observação ou o `If-None-Match`.

### POST /v1/bench/relatorio

**Módulo:** 06 do Bench · **Arquivo:** `api/app/routes/bench_relatorio.py` · **ADR:** ADR-016,
TA-ADR-028

Diagnóstico do Bench com a sessão do técnico (`Authorization: Bearer itcbs_…`), sem token de
carreta. Mesma normalização, prompt e chamada à IA de `POST /v1/relatorio` (função comum
`gerar_laudo` em `routes/relatorio.py`).

Body: o da rota da carreta (`sessao`, `modulos`; contrato 1.3 em `docs/api/SCHEMA.md`) mais:

- `envio_id` (obrigatório): UUID gerado pelo Bench por coleta; repetido, a rota é idempotente.
- `unidade` (opcional, até 32): código da unidade da máquina. A API confere contra as Unidades
  ativas (cópia dos cadastros); fora da lista, grava nulo e registra no log sem o valor.

Ordem: sessão → limite por técnico (`BENCH_RELATORIO_LIMITE_HORA`, padrão 30 por hora cheia UTC,
contado em `bench_relatorio_uso`) → corpo. Grava `carreta = 'BANCADA'`, `bench_usuario` (login
GLPI da sessão), `bench_sessao_id` (id da linha em `bench_sessoes`), `unidade`, `envio_id`.

| Status | Corpo | Quando |
|---|---|---|
| `200` | o mesmo de `POST /v1/relatorio` | Laudo gerado, ou já gravado para este `envio_id` (devolve o gravado sem chamar a IA) |
| `401` | `{"erro": "nao_autorizado"}` | Sessão ausente, vencida, revogada, ou token de carreta |
| `409` | `{"erro": "em_processamento"}` | Mesmo `envio_id` com a IA em andamento há menos de 120 s |
| `422` | `{"erro": "requisicao_invalida"}` | Corpo fora do schema ou `envio_id` que não é UUID |
| `429` | `{"erro": "limite_excedido"}` + `Retry-After` | Acima do limite do técnico na hora (todas as sessões dele somam) |
| `502`/`503` | `{"erro": "ia_*"}` | Como na rota da carreta; o diagnóstico fica gravado com `falha` e um novo envio com o mesmo `envio_id` tenta a IA de novo na mesma linha |

`coletadoPor` (sessão) e `bench_usuario` nunca vão ao prompt (`FORA_DO_PROMPT`). Em 1.3 os grupos
do Event Log chegam sem classificação e a API classifica pela base (`classificar_eventos`).

### GET /v1/bench/historico/{hostname}

**Módulo:** 06 do Bench · **Arquivo:** `api/app/routes/bench_relatorio.py`

Sessão do técnico. Mesmo padrão de hostname e mesmos 20 itens de `GET /v1/historico/{hostname}`,
mais `bench_usuario`, `unidade`, e em `relatorio` também `relatorio_md` e `chamado_descricao`.
Qualquer técnico com sessão lê qualquer hostname (risco aceito no ADR-016). `401` sem sessão;
`422` para hostname fora do padrão.
