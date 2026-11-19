# Configuração e Manutenção — Rodar pelas marcações atuais, contas locais e Encerrar sessões

**Branch:** `feat/preparacao-contas-rodar` · **Data:** 2026-11-19 · **ADR:** ADR-071, ADR-072

Só `app/`; a API não muda.

## O que entrou

| Item | Onde |
|---|---|
| Rodar com as etapas marcadas agora (bug: a desmarcada depois de ler rodava) | `ui/preparacao.py` (`_andamento_atual`, `_rodar`, `_ocupar`) |
| Rodar sem "Ler situação"; confirmação sem leitura e com as contas marcadas | `ui/preparacao.py` (`confirmacao`, `COM_CONTAS`) |
| Contas locais, bloqueadas em cinza com o motivo; regras do ADR-021 sem mudança | `servicos/etapas.py` (`contas_locais`, `MOTIVO_CONTA`), `ui/preparacao.py` (`_carregar_alunos`) |
| Suporte, Gestão e Administrador nativo nunca aparecem (ADR-072) | `servicos/etapas.py` (`escondida`) |
| Versão 0.20.0 (ADR-072) | `app/src/itc_bench/__init__.py`, `README.md` |
| Campo `bench` na listagem de contas (conta do processo) | `recursos/contas/listar.ps1`, `servicos/contas.py` (`Conta.bench`) |
| Marcar todas / Desmarcar todas (etapas e contas) e Atualizar | `ui/preparacao.py` |
| Encerrar sessões… reaproveitado da tela Contas | `ui/contas.py` (`pedir_encerrar`), `servicos/contas.py` (`encerrar_sessoes`) |
| Ajuda das duas telas | `ui/preparacao.py` (`AJUDA`, `AJUDA_MANUTENCAO`) |

## Verificação

Testes em `app/tests/test_preparacao_tela.py` (16), sem tocar no Windows: etapas, contas e
sessões falsas.

| # | Cenário | Teste | Resultado |
|---|---|---|---|
| P1 | Ler, desmarcar uma etapa, rodar: a desmarcada não roda | `test_desmarcada_depois_de_ler_nao_roda` | Passa |
| P2 | Ler com uma desmarcada, marcar depois: entra no contador e roda | `test_marcada_depois_de_ler_entra_no_contador_e_roda` | Passa |
| P3 | Confirmação lista só as marcadas agora | `test_confirmacao_lista_so_as_marcadas_agora` | Passa |
| P4 | Sem ler: Rodar disponível com N marcadas e roda todas | `test_rodar_sem_ler_fica_disponivel_e_roda_as_marcadas` | Passa |
| P5 | Confirmação sem leitura com etapas e "Contas marcadas" | `test_confirmacao_sem_leitura_lista_etapas_e_contas` | Passa |
| P6 | Sem administrador, Rodar e Encerrar desativados | `test_sem_admin_rodar_continua_desativado`, `test_encerrar_sem_admin_desativado` | Passa |
| C1 | Motivo de cada conta local; contas livres = `contas_de_aluno` | `test_contas_locais_com_motivo_e_mesmas_regras`, `test_administradora_aparece_com_motivo` | Passa |
| C3 | Suporte (padrão e cadastrada), Gestão (com e sem acento) e nativo nunca aparecem | `test_suporte_gestao_e_nativo_nunca_aparecem` | Passa |
| C2 | Painel com todas as locais; bloqueada cinza e sem marcar; `alvos` só as livres | `test_painel_mostra_todas_as_locais_e_bloqueadas_sem_marcar` | Passa |
| M1 | Marcar/desmarcar todas as etapas (contador e Rodar) | `test_marcar_e_desmarcar_todas_as_etapas` | Passa |
| M2 | Marcar/desmarcar todas as contas, só as livres | `test_marcar_e_desmarcar_todas_as_contas_so_as_livres` | Passa |
| A1 | Atualizar mantém as marcações e marca conta nova | `test_atualizar_mantem_as_marcacoes` | Passa |
| A2 | Atualizar e Encerrar desativados enquanto ocupado | `test_atualizar_desativado_enquanto_ocupado` | Passa |
| E1 | Encerrar usa o diálogo da tela Contas, encerra e relê (a conta vira alvo) | `test_encerrar_sessoes_usa_o_dialogo_das_contas_e_atualiza` | Passa |
| E2 | Manutenção com os mesmos botões e contas | `test_manutencao_tem_os_mesmos_botoes` | Passa |

Os testes de contas, preparação e manutenção que já existiam continuam passando (o filtro
`contas_de_aluno` dá o mesmo resultado).

App: ruff, format e mypy limpos; `pytest` completo, depois do ADR-072 e do bump, com 1171
passando, 10 pulados e a falha de ambiente conhecida
(`test_papel_de_parede::test_trecho_aparencia_recusa_valor_e_caminho_fora`, passa elevado).
`itc-bench --dev --teste` com código 0; o log mostra "ITC Bench 0.20.0 iniciado".

Leitura real nesta máquina (só leitura, sem administrador): 7 contas locais, uma com `bench`
(a do técnico), motivos Administrador nativo, administradora (2), Suporte e conta do Bench; as
2 livres são exatamente as de `contas_de_aluno`.

Capturas das duas telas, claro e escuro: `.conversa/captura-{configuracao,manutencao}-{claro,escuro}.png`
(fora do git).

Máquina real: roteiro 10.25 a 10.28 (`docs/testes/maquina-real.md`), ainda não executado.
