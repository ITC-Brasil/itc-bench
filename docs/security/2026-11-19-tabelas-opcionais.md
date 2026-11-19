# Auditoria de segurança — `feat/tabelas-opcionais` (TA-ADR-041)

**Data:** 2026-11-19 · **Prompt:** `docs/security/AUDIT-PROMPT.md` · **Base:** `main` `4d78205`
(diff ainda sem commit no clone `itc-bench-git`).

**Resultado:** nenhum achado crítico, alto, médio ou baixo. 3 informativos. Não bloqueia o
fechamento.

## Stack e escopo

API FastAPI (Python 3.12) no glpi-srv, leitura do NocoDB por `httpx` com o token Viewer da base
"ITC Bench"; o Bench é cliente da rota `GET /v1/bench/cadastros`. O app (`app/`) não muda.

Arquivos revisados (diff inteiro): `api/app/services/nocodb_cadastros.py` (`ler`),
`api/app/routes/cadastros.py` (campo `avisos`) e `api/tests/test_cadastros.py`. A busca da
tabela pelo nome (rotas `/api/v2/meta/...`), que estava no rascunho, foi retirada antes desta
auditoria e não faz parte do diff.

## 1. Banco sem tranca

Não se aplica de forma nova. Nada é gravado no SQLite por esta mudança; a auditoria
`bench_cadastros_entregas` continua igual. Os cadastros são os mesmos para todo técnico
autenticado (não há inquilino por técnico; o filtro `?unidade=` só reduz o Wi-Fi e não mudou).

## 2. Permissão definida na tela

Correto. `avisos` sai na mesma resposta `200` da rota, que continua exigindo sessão de técnico
(`test_sem_sessao_401`, `test_token_de_carreta_nao_vale`). Quem não entrou não recebe o campo.

## 3. IDOR

Correto. O id de cada tabela vem só das variáveis `NOCODB_TABELA_*` do `api/.env`
(`ler`, laço das opcionais e das obrigatórias); nenhum parâmetro do cliente escolhe tabela,
coluna ou URL do NocoDB. A retirada da busca pelo nome elimina as chamadas às rotas de metadados
com o token Viewer (`test_sem_busca_pelo_nome`).

## 4. Chaves expostas

Correto. Nenhum segredo novo no código, nos testes ou na documentação (ids de tabela nos testes
são fictícios: `mPro`, `mPer`). O `log.warning` da tabela opcional leva só o nome lógico e o
código do erro (`tabela opcional projetos nao lida (http_404)`); nunca URL, id de tabela, token
ou texto do NocoDB.

## 5. Inputs sem tratamento

Correto.
- `routes/cadastros.py`: `avisos` passa pela mesma expressão fechada `MOTIVO` do TA-ADR-040;
  o que não casar é descartado. O `erro.code` vem de `paginas`, que só gera `timeout`,
  `indisponivel`, `resposta_invalida` ou `http_<código>`.
- O corpo da resposta de erro do NocoDB nunca é lido para `avisos`
  (`test_cadastros_entrega_avisos_restritos`: "texto do NocoDB", `mPro` e `mPer` ausentes).
- O Bench atual ignora `avisos`; mostrar o campo na tela fica para depois (e deverá traduzir o
  código como já faz com o `motivo`, sem rich text).

## Informativos

- **I1.** Uma opcional que estoura o tempo consome o teto total de 30 s da leitura; as
  obrigatórias lidas depois podem cair em `timeout` e a rota responde `503`. É o comportamento
  esperado do teto, não uma falha de isolamento.
- **I2.** Sem Perfis lida, a lista de perfis vem vazia e a Configuração do Bench não roda; o
  técnico vê a falta de perfis, mas ainda não o `avisos` (decisão adiada no TA-ADR-041).
- **I3.** Sem Projetos lida, a API para de pedir a coluna `Projeto`: redes Wi-Fi com `Projeto`
  passam a valer pela `Unidade` (regra antiga do TA-ADR-038). Uma rede de projeto sem `Unidade`
  cai como `unidade_invalida` em vez de ir para o projeto todo. Efeito de disponibilidade, sem
  exposição de dado.

## Verificação

API: 290 testes no container `python:3.12.14-slim-trixie`, 7 novos (opcional com 404 e 400,
Perfis sem a coluna `WiFi.Perfis`, opcionais lidas sem aviso, obrigatória ainda `503`, `avisos`
restrito na rota, nenhuma chamada a `/meta/`).
