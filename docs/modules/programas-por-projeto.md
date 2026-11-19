# Programas por projeto e perfil, como o Wi-Fi

**Branch:** `feat/programas-por-projeto` · **Data:** 2026-11-19 · **ADR:** ADR-074 · **TA-ADR:** TA-ADR-042

App e API.

## O que entrou

| Item | Onde |
|---|---|
| `projeto` e `perfis` em todo instalador; sigla ou perfil desconhecido descarta a linha; `Perfis` só pedida com a tabela Perfis lida | `api/app/services/nocodb_cadastros.py` |
| `Instalador.perfis` no cache e `Cadastros.instaladores_para(unidade, perfil)` | `app/src/itc_bench/servicos/cadastros.py` |
| `programas.listar(cadastros, unidade, perfil)`; duplicata por máquina ou por projeto e perfil | `app/src/itc_bench/servicos/programas.py` |
| Etapa 6 só com os programas do projeto e do perfil; some sem nenhum | `app/src/itc_bench/servicos/etapas.py` (`itens_programas`, `ocultas`) |
| Tela Programas: "Projeto desta máquina" / "Todos os projetos", coluna Para, aviso de bancada | `app/src/itc_bench/ui/programas.py`, `ui/janela.py` |
| Ajuda das telas Programas e Configuração | `ui/programas.py` (`AJUDA`), `ui/preparacao.py` (`AJUDA`) |

## Verificação

App: `tests/test_programas_projeto.py` (13). API: `test_programas_por_projeto_e_perfis` e
`test_papel_por_projeto` ajustado em `api/tests/test_cadastros.py`.

| # | Cenário | Teste | Resultado |
|---|---|---|---|
| R1 | Programa sem projeto vale para todas as máquinas, inclusive em bancada | `test_programa_sem_projeto_vale_para_todas_as_maquinas` | Passa |
| R2 | Programa do projeto só nas unidades dele; unidade sem projeto e bancada só os gerais | `test_programa_do_projeto_so_nas_unidades_dele`, `test_bancada_so_os_gerais` | Passa |
| R3 | Perfil filtra; `perfis` vazio vale para todos | `test_perfil_filtra_e_vazio_vale_para_todos` | Passa |
| R4 | Cache com `perfis` e cache antigo sem eles | `test_cache_le_os_perfis_e_cache_antigo_sem_eles` | Passa |
| L1 | Lista em Todos e da máquina; duplicata só quando iria para a mesma máquina | `test_listar_todas_e_da_maquina`, `test_mesmo_programa_em_projetos_diferentes_nao_e_duplicata` | Passa |
| E1 | Etapa 6 com o projeto e o perfil; some sem programa; sem cadastro não some | `test_etapa_6_instala_so_os_do_projeto_e_perfil`, `test_etapa_6_some_sem_programa_para_o_projeto_e_perfil` | Passa |
| T1 | Tela abre em Projeto desta máquina, coluna Para, aviso do projeto | `test_tela_abre_nos_programas_desta_maquina_com_a_coluna_para` | Passa |
| T2 | Todos os projetos; bancada; reabre no projeto e relê com a unidade trocada | `test_todos_os_projetos_mostra_tudo`, `test_bancada_avisa_e_mostra_so_os_gerais`, `test_ao_voltar_a_tela_reabre_no_projeto_e_rele_se_a_unidade_mudou` | Passa |
| A1 | API: sem as tabelas, colunas não pedidas e linha para todos; com elas, projeto e perfis; sigla e perfil errados descartam | `test_programas_por_projeto_e_perfis`, `test_papel_por_projeto` | Passa |

App: ruff, format e mypy limpos; `pytest` completo com 1184 passando, 10 pulados e a falha de
ambiente conhecida (`test_papel_de_parede`, passa elevado); os 222 testes da área que já
existiam continuam passando. API: 291 testes no container `python:3.12.14-slim-trixie`.

Máquina real: roteiro 8.8f e 10.29, ainda não executado. Antes, criar a coluna `Perfis` em
Instaladores no NocoDB e publicar a API.
