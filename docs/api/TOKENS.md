# Runbook de tokens

Como criar, trocar e revogar os tokens que autenticam cada carreta na API. Cobre os sete
cenários de `PROMPT_CLAUDE_CODE.md` §6.5. Cada cenário termina com "Como saber que deu
certo" e com a verificação registrada no Módulo 02.

## Como a autenticação funciona

São duas camadas (TA-ADR-007):

| Camada | Onde é checada | Quem tem | Como se revoga |
|---|---|---|---|
| Service token do Cloudflare Access (`CF-Access-Client-Id` e `CF-Access-Client-Secret`) | Na borda da Cloudflare, antes de chegar ao glpi-srv | Todos os pendrives: é compartilhado | No painel Zero Trust (cenário 6) |
| Token da carreta (`itcta_...`) | Na API, em cada requisição | Um pendrive, o da carreta | `python -m app.tokens revoke` (cenário 2) |

O token da carreta vai no cabeçalho **`Authorization: Bearer itcta_...`**. Os cabeçalhos
do Cloudflare Access não usam o `Authorization`, então os dois não se misturam.

- O token tem o formato `itcta_` seguido de 43 caracteres (`secrets.token_urlsafe(32)`,
  256 bits).
- O banco guarda só o SHA-256 do token (`carretas_tokens.token_hash`). Ninguém consegue
  recuperar um token perdido: nem o banco, nem a CLI, nem o backup. Por isso ele é
  guardado no Vaultwarden no momento da criação.
- Cada carreta tem **no máximo um token ativo**. O banco garante isso com um índice único
  parcial.
- O `revoke` vale na requisição seguinte, sem reiniciar o container: cada requisição
  consulta o banco.
- Toda execução da CLI que passa da leitura dos argumentos, inclusive as recusadas e as
  que falham no banco, grava uma linha em `tokens_auditoria`. Um erro de uso (saída 2)
  para antes de abrir o banco e não grava nada. A auditoria guarda o id da linha do token e a carreta, nunca o
  token nem o hash. A tabela não aceita `UPDATE` nem `DELETE`.

Respostas da API que o pendrive precisa tratar:

| Status | Corpo | Quando |
|---|---|---|
| `401` | `{"erro": "nao_autorizado"}` | Sem cabeçalho, esquema diferente de `Bearer`, token mal formado, inexistente ou **revogado**. Todos recebem a mesma resposta |
| `413` | `{"erro": "corpo_grande"}` | Corpo acima de `MAX_BODY_BYTES` (512 KB), com ou sem `Content-Length` |
| `429` | `{"erro": "limite_excedido"}` + `Retry-After: <segundos>` | Mais de `RATE_LIMIT_PER_TOKEN_PER_HOUR` (60) requisições do mesmo token na hora cheia UTC (TA-ADR-021) |
| `400` | texto do uvicorn | `Content-Length` malformado ou negativo: o uvicorn recusa antes da aplicação |

A ordem das verificações é corpo, depois token, depois limite: um corpo grande dá `413`
mesmo sem token, e um token revogado dá `401` mesmo acima do limite.

## Antes de começar

- Todos os comandos rodam no glpi-srv, por SSH, onde o container `tecnico-api` está no
  ar. A CLI usa o mesmo banco da API (`/data/tecnico.db`).
- **`--operador` é obrigatório** em todos os comandos, com o nome de quem executa. Ele vai
  para a auditoria. O nome é declarado por quem digita, não autenticado: o controle real
  é quem tem acesso ao Docker no glpi-srv.
- A carreta é normalizada para maiúsculas: `um-03` e `UM-03` são a mesma carreta.
- **Os horários da CLI estão em UTC** (`CURRENT_TIMESTAMP` do SQLite). Para o horário de
  Brasília, subtraia 3 horas: `18:17` UTC são `15:17`.
- Código de saída: `0` ok, `1` recusado por uma regra (a mensagem diz o motivo), `2` erro
  de uso do comando (subcomando desconhecido, `--operador` ausente), `3` falha do banco
  (a operação foi desfeita).
- Use `docker exec -it`, para o token sair só no seu terminal. Não redirecione a saída do
  `create` nem do `rotate` para arquivo ou log.

Referência dos comandos:

```
docker exec -it tecnico-api python -m app.tokens create --carreta UM-03 --descricao "..." --operador matheus
docker exec -it tecnico-api python -m app.tokens list --operador matheus
docker exec -it tecnico-api python -m app.tokens revoke --carreta UM-03 --motivo "..." --operador matheus
docker exec -it tecnico-api python -m app.tokens rotate --carreta UM-03 --operador matheus
docker exec -it tecnico-api python -m app.tokens auditoria [--carreta UM-03] --operador matheus
docker exec -it tecnico-api python -m app.tokens uso [--carreta UM-03] --operador matheus
```

O `uso` conta os diagnósticos recebidos (tabela `diagnosticos`) por carreta, token e dia
UTC, com o número de hostnames distintos, as falhas da IA e o primeiro e o último horário.

O `list` mostra todas as linhas, ativas (`ativo` = 1) e revogadas (`ativo` = 0), sem token
nem hash. O `auditoria` mostra o histórico, filtrado pela carreta se `--carreta` for
informado. As três consultas também entram na auditoria.

## Cenário 1 — Nova carreta entrando em operação

1. Crie o token:
   ```
   docker exec -it tecnico-api python -m app.tokens create --carreta UM-03 --descricao "Pendrive da UM-03" --operador matheus
   ```
2. Copie o token da saída para o Vaultwarden, num item com o nome da carreta. Ele não será
   mostrado de novo.
3. Grave o token no pendrive da carreta (cenário 7).

**Como saber que deu certo:**
- O `list` mostra a carreta com `ativo` = 1, a sua descrição e o seu nome em
  `criado_por`.
- O `auditoria --carreta UM-03` mostra `create` / `ok`.
- A primeira requisição do pendrive responde `200`, e o `ultimo_uso` da linha é
  preenchido.
- Um segundo `create` para a mesma carreta é recusado (`já tem token ativo; use rotate`,
  saída 1). Isso é o esperado: para trocar, use o cenário 3.

## Cenário 2 — Pendrive perdido ou roubado

1. Revogue o token, com o motivo:
   ```
   docker exec -it tecnico-api python -m app.tokens revoke --carreta UM-03 --motivo "pendrive perdido em Campinas" --operador matheus
   ```
2. No Vaultwarden, marque o item antigo como revogado.
3. Quando o pendrive novo estiver pronto, crie um token novo para a carreta (cenário 1).
   O `create` é aceito porque a carreta não tem mais token ativo.

O service token do Cloudflare **não** precisa ser trocado: sozinho, ele não dá acesso à
API (ver cenário 6).

**Como saber que deu certo:**
- O `list` mostra a linha antiga com `ativo` = 0, `revogado_em` e o motivo.
- A próxima requisição com o token antigo responde `401 {"erro": "nao_autorizado"}`, sem
  reiniciar o container.
- O `auditoria --carreta UM-03` mostra `revoke` / `ok` com o motivo.

## Cenário 3 — Rotação periódica preventiva

1. Gire o token:
   ```
   docker exec -it tecnico-api python -m app.tokens rotate --carreta UM-03 --operador matheus
   ```
   O `rotate` revoga o token atual e cria o novo na mesma transação. Se algo falhar no
   meio, nada muda: o token atual continua valendo e a auditoria registra `falha`.
   A descrição é copiada do token anterior.
2. Troque o token no Vaultwarden e no pendrive (cenário 7). **A partir do `rotate`, o
   pendrive com o token antigo recebe `401`.** Faça a troca no pendrive logo em seguida,
   ou no dia em que a carreta estiver na base.

**Como saber que deu certo:**
- O `list` mostra a linha anterior com `ativo` = 0 e motivo `rotate`, e uma linha nova
  com `ativo` = 1.
- O `auditoria` mostra `rotate` / `ok`, com `substitui o token N`.
- O pendrive com o token novo responde `200`; com o antigo, `401`.

## Cenário 4 — Carreta desativada

1. Revogue o token, sem criar outro:
   ```
   docker exec -it tecnico-api python -m app.tokens revoke --carreta UM-05 --motivo "carreta desativada" --operador matheus
   ```
2. No Vaultwarden, arquive o item da carreta.

As linhas da carreta ficam no banco e na auditoria, como histórico. Nada é apagado.

**Como saber que deu certo:**
- O `list` mostra a carreta só com linhas `ativo` = 0.
- Um `rotate` da carreta é recusado (`não tem token ativo; use create`, saída 1).
- Se a carreta voltar a operar, siga o cenário 1.

## Cenário 5 — Suspeita de vazamento sem saber qual pendrive

1. Veja o último uso de cada token:
   ```
   docker exec -it tecnico-api python -m app.tokens list --operador matheus
   ```
   Procure `ultimo_uso` incompatível com a rotina da carreta: uso com a carreta parada,
   fora do horário de trabalho ou de uma carreta que não deveria estar coletando.
2. O `ultimo_uso` só mostra a requisição mais recente. Para ver o volume, veja os
   diagnósticos por dia:
   ```
   docker exec -it tecnico-api python -m app.tokens uso --operador matheus
   ```
   Sinais de token vazado: muitos diagnósticos num dia (uma carreta faz poucos),
   `hostnames` acima do número de notebooks atendidos, horários (`primeiro`, `ultimo`, em
   UTC) fora do expediente, ou diagnósticos num dia em que a carreta não trabalhou. A
   coluna `token_id` separa o token atual dos anteriores da mesma carreta.
3. Veja o histórico das carretas suspeitas:
   ```
   docker exec -it tecnico-api python -m app.tokens auditoria --carreta UM-03 --operador matheus
   ```
   Confira quem criou e girou o token e quando. Um `create` ou `rotate` que ninguém
   reconhece é sinal de acesso indevido ao glpi-srv, e isso é um incidente maior que o
   token.
4. Gire os tokens das carretas suspeitas (cenário 3). Se não der para isolar, gire todos,
   carreta por carreta.

**Como saber que deu certo:**
- O `list` mostra linhas novas com `ativo` = 1 para cada carreta girada.
- A partir daí, o `ultimo_uso` das linhas antigas não muda mais, e o `uso` não mostra
  diagnósticos novos com o `token_id` antigo.

## Cenário 6 — Rotação do service token do Cloudflare Access

O service token é **compartilhado** por todos os pendrives e só abre a borda. Sem o token
da carreta, a API responde `401`. Por isso, revogar o token de uma carreta (cenário 2)
não exige trocar o service token. Troque o service token quando ele vencer, quando
houver suspeita de vazamento em massa (vários pendrives) ou quando vazar a cópia
guardada no Vaultwarden.

1. No painel Zero Trust da Cloudflare, em Access → Service Auth, crie um service token
   novo, **sem apagar o antigo**.
2. Adicione o token novo à política da aplicação `diag.exemplo.invalid`, ao lado do antigo.
3. Troque o `CF-Access-Client-Id` e o `CF-Access-Client-Secret` no Vaultwarden e em
   cada pendrive (cenário 7).
4. Quando todos os pendrives estiverem trocados, remova o token antigo da política e
   depois apague-o.

**Como saber que deu certo:**
- Um pendrive com o service token novo recebe `200` no `/v1/saude` pelo túnel.
- Depois do passo 4, uma requisição com o service token antigo é barrada pela Cloudflare
  e não chega ao glpi-srv.

## Cenário 7 — Onde o token fica no pendrive e como trocá-lo lá

O token fica em `pendrive/config/api.json`, junto com a URL da API e o service token do
Cloudflare. O arquivo nunca vai para o Git: o `.gitignore` o exclui, e o
`pendrive/config/api.example.json` versionado mostra o formato:

```
{
  "url": "https://diag.exemplo.invalid",
  "tokenCarreta": "itcta_...",
  "cfAccessClientId": "....access",
  "cfAccessClientSecret": "...",
  "timeoutSegundos": 120
}
```

O cliente (`Read-ConfigApi` e `Invoke-RelatorioApi` em
`pendrive/lib/Util-Relatorio.ps1`) envia o token em `Authorization: Bearer itcta_...`
só no `POST /v1/relatorio`, e os dois campos da Cloudflare em `CF-Access-Client-Id` e
`CF-Access-Client-Secret` em todas as requisições.

1. Com o pendrive no notebook da base, abra `config\api.json` no Bloco de Notas (se não
   existir, copie o `api.example.json` com esse nome).
2. Troque `tokenCarreta` (ou `cfAccessClientId` e `cfAccessClientSecret`, no cenário 6)
   pelo valor novo, copiado do Vaultwarden. Mantenha as aspas.
3. Salve e execute um `[1] Diagnóstico completo` de teste.

**Como saber que deu certo:**
- O diagnóstico de teste mostra "Relatório da sessão (IA)" e grava `relatorio.md` na
  pasta da sessão, em vez de "Relatório da IA indisponível".
- Com o token antigo, a mesma tela mostra "Token da carreta recusado".
- O `list` mostra o `ultimo_uso` do token novo atualizado, e o `uso` conta o diagnóstico.

## Verificação

Execução com a CLI real no container `tecnico-api` local (imagem do `api/Dockerfile`,
porta de teste 3099, volume novo), em 2026-09-28: CLI no Módulo 02 e passos HTTP no
Módulo 03, com `GET /v1/historico/{hostname}` e `POST /v1/relatorio` (este com a chave
`changeme` do `.env.example`, que responde `503 ia_nao_configurada` sem chamar a IA, mas
grava o diagnóstico). Os tokens foram mascarados na transcrição. O container de produção
entra no Módulo 06.

| Cenário | Passo verificado | Resultado |
|---|---|---|
| 1 | `create --carreta UM-03` | Saída 0; token `itcta_` + 43 caracteres mostrado uma vez, com o aviso do Vaultwarden; id 1 |
| 1 | `list` | `1  UM-03  1  Pendrive da UM-03  2026-09-28 18:17:36  matheus`, sem token nem hash |
| 1 | Segundo `create` para UM-03 | Saída 1, `recusado: a carreta UM-03 já tem token ativo; use rotate` |
| 1 | Requisição com o token e `ultimo_uso` | Módulo 03, container: `GET /v1/historico/TESTE-NB-11` → `200 {"hostname":"TESTE-NB-11","diagnosticos":[]}`; `list` com `ultimo_uso` 2026-09-28 20:10:41 |
| 2 | `revoke --carreta UM-03 --motivo "pendrive perdido em Campinas"` | Saída 0; `list` com a linha 1 em `ativo` = 0, `revogado_em` 18:17:40 e o motivo |
| 2 | `create` depois do `revoke` | Saída 0, token id 2 |
| 2 | Token revogado responde `401` na requisição seguinte | Módulo 03, container: depois do `revoke`, `GET /v1/historico` → `401` com `WWW-Authenticate: Bearer` e `{"erro":"nao_autorizado"}`; `POST /v1/relatorio` → `401`, sem reiniciar |
| 3 | `rotate --carreta UM-03` | Saída 0; token id 3 mostrado, `O token 2 foi revogado no mesmo passo`; `list` com a linha 2 em `ativo` = 0 e motivo `rotate`, e a linha 3 em `ativo` = 1 com a descrição copiada |
| 3 | Falha no meio do `rotate` não muda nada | Pytest: `test_failure_in_the_middle_of_rotate_keeps_the_old_token` passou (`carretas_tokens` idêntica, uma linha `falha`) |
| 3 | Token antigo `401`, novo `200` | Pytest: `test_rotate_swaps_the_accepted_token` passou. No container, o equivalente com `revoke` + `create`: antigo `401`, novo aceito (`POST` → `503 ia_nao_configurada`, que só ocorre depois da autenticação) |
| 4 | `create` e `revoke --carreta UM-05 --motivo "carreta desativada"` | Saída 0 nos dois; `list` com a UM-05 só em `ativo` = 0 |
| 4 | `rotate --carreta UM-05` | Saída 1, `recusado: a carreta UM-05 não tem token ativo; use create` |
| 5 | `auditoria --carreta UM-03` | Saída 0; cinco linhas: `create ok` (token 1), `create recusado`, `revoke ok` com o motivo, `create ok` (token 2), `rotate ok` (token 3, `substitui o token 2`); sem token nem hash |
| 5 | `ultimo_uso` no `list` | Módulo 03, container: preenchido depois do primeiro `GET` |
| 5 | `uso` | Módulo 03, container: `UM-03  1  2026-09-28  1  1  1  20:10:41  20:10:41` e `UM-03  2  2026-09-28  1  1  1  20:10:57  20:10:57` (um diagnóstico por token, com a falha `ia_nao_configurada`) |
| 6 | Rotação do service token | Não executado — depende do Módulo 06 |
| 7 | Troca do token no pendrive | Parcial, Módulo 07: o cliente real (`Invoke-RelatorioApi`) contra o container local, com um token válido, chegou à IA (`ia`, `ia_nao_configurada` com a chave `changeme`) e o `uso` contou o diagnóstico; depois do `revoke`, o mesmo token recebeu "Token da carreta recusado". A troca num pendrive real, pela borda da Cloudflare, depende do Módulo 06 |
