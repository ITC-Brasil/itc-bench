# API — Técnico Assistente

Rotas planejadas em `PROMPT_CLAUDE_CODE.md` §6. Cada uma é documentada aqui, no formato
completo, no módulo que a implementa.

| Rota | Auth | Módulo |
|---|---|---|
| `GET /v1/saude` | pública | 01 |
| `POST /v1/relatorio` | token da carreta | 03 (autenticação no 02) |
| `GET /v1/historico/{hostname}` | token da carreta | 03 (autenticação no 02) |

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
