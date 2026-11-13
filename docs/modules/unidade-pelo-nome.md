# Unidade da máquina pelo nome do computador

**Branch:** `feat/monitores-video` · **Data:** 2026-11-13 · **ADR:** ADR-048

Só `app/`; a API não muda.

## O que entrou

| Item | Onde |
|---|---|
| Código antes do primeiro hífen, no formato de `Unidades.Codigo` | `servicos/cadastros.py` (`codigo_do_nome`, `CODIGO_UNIDADE`) |
| Nome que vale depois de reiniciar, lido do HKLM | `servicos/cadastros.py` (`nome_do_computador`) |
| Unidade do cadastro com aquele código | `servicos/cadastros.py` (`unidade_pelo_nome`) |
| Escolha automática sem unidade gravada; escolha do técnico vale mais | `ui/janela.py` (`_identificar_unidade`, `escolher_unidade(manual=)`) |
| Avisos em Configurações (identificada; divergente) e ajuda | `ui/janela.py` (`_avisos_cadastros`), `ui/configuracoes.py` (`AJUDA`) |
| Nome fixo nos testes | `tests/conftest.py` |

## Contexto

O histórico desta máquina de desenvolvimento (evento 6011 do log do Sistema) mostrou nomes como
`ABCCEL-CEILANDI`, `RESERVA-06` e `QUALIFICA-EST`, nenhum no padrão do código. A regra só
identifica quando a equipe nomeia como `<código>-<resto>` (exemplo do responsável:
`BSBIA01-EST94`).

## Verificação

App: 1043 passando, 10 pulados, 1 falha do ambiente local; ruff, format e mypy limpos. Nome
desta máquina (`QUALIFICA-EST`): nenhum código, nada muda.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| U1 | Regra do código (10 nomes: com e sem hífen, minúsculas, dígito depois do código, sigla longa, vazio) | `test_codigo_do_nome` | Passa |
| U2 | Sem unidade, escolhe a do nome e avisa em Configurações | `test_sem_unidade_usa_a_do_nome` | Passa |
| U3 | Nome sem código ou com código fora do cadastro não escolhe | `test_nome_sem_codigo_ou_codigo_fora_do_cadastro_nao_escolhe` | Passa |
| U4 | Escolha manual (bancada ou outra unidade) vale mais; divergência avisada | `test_escolha_manual_vale_mais_que_o_nome` | Passa |
| V1 | Máquina renomeada para `<código>-EST01`, login online | máquina real | Pendente (11.9) |

## Limites conhecidos

- Sem unidade gravada, a escolha "bancada" vale só na sessão; na próxima, o nome volta a valer.
- Nome fora do padrão continua com a escolha manual de sempre.
