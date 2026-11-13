# Monitores — resolução, frequência, orientação e escala

**Branch:** `feat/monitores-video` · **Data:** 2026-11-13 · **ADR:** ADR-041

Só `app/`; a API não muda.

## O que entrou

| Item | Onde |
|---|---|
| Leitura e escrita no Windows (ctypes do `user32`) | `nucleo/video.py` |
| Regras, validação, confirmação e desfazer | `servicos/video.py` |
| Aba Monitores: desenho dos monitores clicável (posição e tamanho reais, como no Windows), opções do escolhido embaixo, marca "alterado", prazo de 15 s | `ui/monitores.py` |
| Abas Monitores e Papel de parede na mesma tela | `ui/janela.py` |
| Texto da tela e da ajuda do papel de parede | `ui/aparencia.py` |
| `nucleo/video.py` na lista fechada de ctypes | `tests/test_invariantes.py` |
| Nenhum teste muda o monitor real | `tests/conftest.py` (`_sem_mudar_monitor`) |

## Verificação

App: 982 passando, 10 pulados, 1 falha do ambiente local (`test_papel_de_parede`, exige
elevação); ruff, format e mypy limpos. Leitura real nesta máquina (só leitura): 1 monitor, tela
interna 1920x1080 a 60 Hz, escala 125% (recomendada), 17 modos.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| M1 | Estruturas com o tamanho do SDK | `test_estruturas_com_tamanho_do_windows` | Passa |
| M2 | Dois monitores com nome de tela; externo sem nome | `test_ler_dois_monitores_com_nomes_de_tela`, `test_externo_sem_nome_e_varios_externos` | Passa |
| M3 | Valor fora da lista do Windows recusado sem chamar o Windows (6 casos) | `test_recusa_valor_fora_da_lista_do_windows` | Passa |
| M4 | Escala sem leitura recusada | `test_escala_sem_leitura_recusa` | Passa |
| M5 | Aplicar nos dois monitores; sem mudança não chama o Windows | `test_aplicar_nos_dois_monitores`, `test_sem_mudanca_nao_chama_o_windows` | Passa |
| M6 | Resolução nova mantém a frequência ou usa a maior | `test_resolucao_nova_mantem_frequencia_se_existir_senao_a_maior` | Passa |
| M7 | Falha num monitor não para o outro | `test_falha_num_monitor_nao_para_o_outro` | Passa |
| M8 | Desfazer volta resolução, orientação e escala | `test_desfazer_volta_tudo_como_estava` | Passa |
| M9 | Confirmação só com o que muda; log sem nome do monitor | `test_mudancas_so_lista_o_que_muda`, `test_log_sem_nome_do_monitor` | Passa |
| M10 | Leitura real só lê | `test_leitura_real_so_le` | Passa |
| T1 | Um cartão por monitor; frequências seguem a resolução | `test_monitores_tela.py` | Passa |
| T2 | Sem admin só lê; nada mudou não pergunta | `test_sem_admin_so_le`, `test_nada_mudou_nao_pergunta` | Passa |
| T3 | Sem resposta em 15 s volta; "Manter" mantém; sem confirmar desfaz | `test_manter_*`, `test_sem_confirmar_desfaz` | Passa |
| V1 | Notebook + monitor externo: resolução e frequência em cada um | máquina real | Pendente (10.11) |
| V2 | Retrato e escala; sem responder, volta em 15 s | máquina real | Pendente (10.12) |
| V3 | Dois externos; tirar um cabo e Atualizar | máquina real | Pendente (10.13) |

## Limites conhecidos

- Estender ou duplicar, monitor principal e posição ficam com o Windows ("Abrir configurações de
  vídeo").
- A escala vale para a conta que roda o Bench e usa API não documentada (ADR-041).
- Monitor que não informa o nome aparece como "Monitor externo".
