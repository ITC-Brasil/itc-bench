# Inicialização (ADR-075)

Tela no grupo Diagnóstico para ver o que abre com o Windows e desligar o que não precisa.

Arquivos: `servicos/inicializacao.py`, `ui/inicializacao.py`,
`recursos/inicializacao/{comum,ler,desligar}.ps1`, `recursos/icones/inicializacao.svg`,
`tests/test_inicializacao.py`.

## Verificação

| Cenário | Resultado |
|---|---|
| Leitura real nesta máquina, sem administrador: Run, pasta Inicializar, apps da Loja da conta, tarefas | ok: 9 itens fora apps, 7 apps, 17 serviços |
| Conta sem sessão, sem administrador | ignorada sem erro (hive não abre) |
| Desligar itens que não existem (Run, Run da conta, app, tarefa) | ok: todos voltam "sumiu", nada muda |
| Essencial pedido para desligar | filtrado no Python (e recusado no trecho) |
| Atrasos de boot ordenados pelo número | ok (teste) |
| Tela: só os sem função e ligados, todos marcados; essenciais, neutros e desligados escondidos | ok (teste) |
| Sem administrador: Desligar desligado | ok (teste) |
| Confirmar, desligar e ler de novo; cancelar não roda | ok (teste) |
| Vários itens da mesma conta sem sessão num Desligar (log de 23/11 no BSBIA04: `conta_em_uso` a partir do 2º) | corrigido: hive carregado uma vez por execução; teste no PowerShell falha sem a correção |
| Etapa 5 da Manutenção: lê só os sem função ligados, respeita os mantidos, encerra outras sessões antes (nunca a do Bench) (ADR-080) | ok (teste) |
| Desligar de verdade como administrador, todas as contas | pendente: roteiro 10.30 |

Achado no caminho: no PowerShell `$apps` e `$APPS` são a mesma variável; a raiz dos apps
chama `$RAIZ_APPS`. E no PS 5.1 `@($json | ConvertFrom-Json)` embrulha o array inteiro num item
só; o trecho usa `ConvertFrom-Json -InputObject`.
