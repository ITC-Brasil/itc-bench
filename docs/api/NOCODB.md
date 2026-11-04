# Espelho NocoDB

O NocoDB é a tela de consulta dos relatórios (TA-ADR-008). Ele recebe uma cópia de cada
relatório gerado, **só de ida**: o SQLite da API é a fonte da verdade, e editar ou apagar
uma linha no NocoDB não muda nada na API (TA-ADR-005). As carretas nunca acessam o NocoDB.

**Código:** `api/app/services/nocodb.py` (envio), `api/app/tarefas.py` (disparo depois do
relatório), `api/app/main.py` (`repetir_espelho`, reenvio periódico). **Módulo:** 04.

## Configuração

Variáveis no `api/.env` do glpi-srv:

| Variável | Valor | Observação |
|---|---|---|
| `NOCODB_ENABLED` | `true` | Com `false`, nada é enviado e os relatórios ficam `pendente` |
| `NOCODB_URL` | `https://nocodb.exemplo.invalid` | Sem barra no fim (uma barra final é removida) |
| `NOCODB_TOKEN` | token de API do NocoDB | Vai no cabeçalho `xc-token`. `changeme` ou vazio desliga o espelho |
| `NOCODB_TABLE_ID` | id da tabela (`m...`) | Visível na URL da tabela ou em "Details → API Snippets" |
| `NOCODB_RETRY_SECONDS` | `300` | Intervalo do reenvio periódico; mínimo 10 |

O token do NocoDB é amplo (sem revogação individual): fica só no `.env` do servidor,
nunca nos pendrives. Use um token de uma conta **Editor** só na base dos relatórios, separada
da base "ITC Bench" dos cadastros (TA-ADR-027).

## Tabela no NocoDB (criar uma vez, passo do responsável)

Crie uma tabela, por exemplo `Relatorios Tecnico Assistente`, com estas colunas. Os
nomes precisam ser **exatamente** estes, porque são as chaves enviadas pela API.

| Coluna | Tipo sugerido | Origem na API |
|---|---|---|
| `DiagnosticoId` | Number | `relatorios.diagnostico_id`: identifica a linha e revela duplicatas |
| `Data` | DateTime | `diagnosticos.recebido_em`, em UTC (`AAAA-MM-DD HH:MM:SS+00:00`) |
| `Carreta` | SingleLineText | `diagnosticos.carreta` |
| `Hostname` | SingleLineText | `diagnosticos.hostname` |
| `Projeto` | SingleLineText | `diagnosticos.projeto` |
| `SubPerfil` | SingleLineText | `diagnosticos.sub_perfil` |
| `Modelo` | SingleLineText | `relatorios.modelo` |
| `MaiorConfianca` | SingleLineText (ou SingleSelect `ALTA`/`MÉDIA`/`BAIXA`) | `relatorios.maior_confianca`, pode ser vazio |
| `ChamadoTitulo` | SingleLineText | `relatorios.chamado_titulo` |
| `Relatorio` | LongText (com Rich Text, se quiser Markdown formatado) | `relatorios.relatorio_md` |

Coluna extra no NocoDB (comentário, status de atendimento) é permitida: a API não a lê
nem a sobrescreve.

## Como funciona

- Cada relatório nasce com `espelho_status = 'pendente'` (`relatorios`).
- **Depois de responder ao pendrive**, a API envia os pendentes em segundo plano (thread),
  até 20 por vez, um registro por requisição:
  `POST {NOCODB_URL}/api/v2/tables/{NOCODB_TABLE_ID}/records` com `[{...campos...}]` e
  timeout de 10 s. A resposta ao pendrive não espera o NocoDB.
- `200` → `espelho_status = 'ok'`, `espelho_em` preenchido. Qualquer outro status →
  continua `pendente`, com `espelho_erro = 'http_<status>'`. Falha de conexão ou timeout →
  `espelho_erro` `indisponivel` ou `timeout`, e **o lote para ali**: com o NocoDB fora do
  ar, cada passada tenta um registro só.
- `espelho_tentativas` conta as tentativas de cada relatório.
- **Reenvio:** a cada `NOCODB_RETRY_SECONDS` (padrão 300 s), a API tenta de novo os
  pendentes, mesmo sem relatório novo. Ao ligar o espelho com relatórios antigos
  pendentes, eles são enviados aos poucos, 20 por passada.
- Um `threading.Lock` impede que a passada depois do relatório e a periódica enviem a
  mesma linha ao mesmo tempo. Vale para um processo só, que é o `CMD` do
  `api/Dockerfile` (sem `--workers`, TA-ADR-021 e TA-ADR-024).

## Como conferir

Pela CLI não há comando próprio; use o Python da imagem:

```
docker exec tecnico-api python -c "import sqlite3; c = sqlite3.connect('/data/tecnico.db'); print(c.execute(\"SELECT espelho_status, count(*), max(espelho_tentativas) FROM relatorios GROUP BY 1\").fetchall())"
docker exec tecnico-api python -c "import sqlite3; c = sqlite3.connect('/data/tecnico.db'); print(c.execute(\"SELECT id, espelho_tentativas, espelho_erro FROM relatorios WHERE espelho_status = 'pendente' ORDER BY id DESC LIMIT 10\").fetchall())"
```

- Tudo `ok` e o NocoDB com o mesmo número de linhas: espelho em dia.
- `pendente` com `http_401`/`http_403`: token errado. Com `http_404`: `NOCODB_TABLE_ID`
  errado. Com `http_400`: nome de coluna diferente da tabela acima.
- `pendente` com `indisponivel`/`timeout`: NocoDB fora do ar; volta sozinho.

## Reconstruir o espelho

Como o espelho é reconstruível do SQLite (TA-ADR-005): apague as linhas da tabela no NocoDB
e marque tudo como pendente de novo. O reenvio periódico refaz a tabela, 20 por passada.

```
docker exec tecnico-api python -c "import sqlite3; c = sqlite3.connect('/data/tecnico.db', isolation_level=None); c.execute(\"UPDATE relatorios SET espelho_status = 'pendente'\"); print('ok')"
```

## Cadastros do Bench (leitura)

Além do espelho, a API **lê** quatro tabelas da base "ITC Bench" (Servidores, Instaladores,
WiFi, Unidades) para `GET /v1/bench/cadastros` (ADR-014, TA-ADR-027). Para esses cadastros o
NocoDB é a fonte da verdade; a API não grava nada lá e não copia nada para o SQLite.

**Código:** `api/app/services/nocodb_cadastros.py` (leitura e validação),
`api/app/routes/cadastros.py` (cópia em memória e rota). **Módulo:** 05 do Bench.

| Variável | Valor | Observação |
|---|---|---|
| `NOCODB_URL` | a mesma do espelho | |
| `NOCODB_CADASTROS_TOKEN` | token do usuário de leitura | Usuário próprio, **Viewer só na base "ITC Bench"**. Nunca o `NOCODB_TOKEN` do espelho |
| `NOCODB_TABELA_SERVIDORES` | id da tabela (`m...`) | Idem para `NOCODB_TABELA_INSTALADORES`, `NOCODB_TABELA_WIFI`, `NOCODB_TABELA_UNIDADES` |
| `NOCODB_CADASTROS_TIMEOUT_SECONDS` | `5` | Por requisição; máximo 15. A leitura inteira tem teto de 30 s |
| `NOCODB_CADASTROS_TTL_SECONDS` | `60` | Validade da cópia em memória |
| `BENCH_CADASTROS_ETAG_KEY` | aleatória | Chave do HMAC da versão; vazia = aleatória por processo |

Sem o token ou um dos ids, a API sobe e a rota responde `503 cadastros_indisponivel`.

**Tokens separados.** O NocoDB não tem escopo por token: o token herda o papel do usuário em cada
base. Por isso dois usuários: o do espelho (**Editor** só na base dos relatórios, que fica
**separada** da "ITC Bench") e o de leitura (**Viewer** só na "ITC Bench"). Risco aceito: o token
de leitura lê a base inteira, segredos inclusive, sem alterar nem apagar.

**Coluna nova em Servidores:** `Publico` (Checkbox). Marque só o que pode aparecer na tela; o
resto, inclusive a `Observacao` da linha, sai como segredo.

**Leitura:** `GET {NOCODB_URL}/api/v2/tables/{id}/records?fields=...&limit=1000&offset=N` por
tabela, até `pageInfo.isLastPage`, com `xc-token`. Qualquer status diferente de `200`, timeout ou
resposta fora do formato vira `timeout`, `indisponivel`, `http_<status>` ou `resposta_invalida`
no log, sem URL, query nem cabeçalho.

**Como conferir:** com uma sessão do Bench, `GET /v1/bench/cadastros` → `200`; no log da API,
`cadastros lidos do NocoDB: servidores N, ...`. `http_401`/`http_403` no log: token errado ou sem
acesso à base; `http_404`: id de tabela errado.

## Limites conhecidos

- **Duplicata possível:** se o NocoDB aceitar o registro e a API cair antes de gravar
  `ok`, a linha é reenviada. A coluna `DiagnosticoId` mostra a duplicata.
- O valor `desligado` de `espelho_status` (migração `0002`) não é usado: com o espelho
  desligado, os relatórios ficam `pendente`, para serem enviados quando ele for ligado.
