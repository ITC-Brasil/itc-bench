# Limpeza de contas — arquivos e caches da conta, sem tocar nas configurações

**Branch:** `feat/monitores-video` · **Data:** 2026-11-13 · **ADR:** ADR-042

Só `app/`; a API não muda.

## O que entrou

| Item | Onde |
|---|---|
| Trecho com lista fechada de pastas, recusas e varredura sem seguir reparse | `recursos/limpeza/contas.ps1` |
| Categorias, recusas no Python, prévia e limpeza por conta | `servicos/limpeza.py` (`CATEGORIAS`, `recusa_conta`, `previa_contas`, `limpar_contas`) |
| Seção "Limpeza de contas" com prévia por categoria e duas confirmações | `ui/limpeza.py` (`PainelLimpezaContas`) |
| Nome da Suporte vindo do cadastro | `ui/janela.py` |

## Verificação

App: 1005 passando, 10 pulados, 1 falha do ambiente local (`test_papel_de_parede`, exige
elevação); ruff, format e mypy limpos. Leitura real nesta máquina, sem administrador: as contas
de outras pessoas dão "sem acesso ao perfil: precisa de administrador" (o Windows nega), a conta
logada e a com sessão dão "sessão aberta", Suporte e Administrador nativo recusados.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| L1 | Recusas: nativo, Suporte (padrão e cadastrada), Gestão, sem perfil, sessão; aluno e administradora aceitas | `test_recusa_conta` (10 casos) | Passa |
| L2 | Recusada não vai ao trecho; válidas por posição; Suporte em minúsculas | `test_recusada_nao_vai_ao_trecho_e_validas_vao_por_posicao` | Passa |
| L3 | Saída fora do contrato ignorada; todas recusadas não rodam o trecho; falha vira erro | `test_saida_fora_do_contrato_e_ignorada`, `test_todas_recusadas_nao_roda_o_trecho`, `test_falha_do_trecho_vira_erro` | Passa |
| L4 | Log sem SID nem nome | `test_log_sem_sid_nem_nome` | Passa |
| L5 | Trecho: sem `NTUSER`, sem escrita no registro, sem `Remove-Item`, sem `Packages` nem `AppData` inteiro | `test_trecho_so_pastas_fixas_e_nunca_o_registro_da_conta` | Passa |
| L6 | Trecho real recusa SID inválido, nativo e a própria conta antes de abrir pasta; ação desconhecida recusada | `test_trecho_real_recusa_sem_tocar_em_nada`, `test_acao_desconhecida_recusada` | Passa |
| T1 | Só conta que pode ser limpa tem caixa de marcar; botão com o total | `test_tela_so_deixa_marcar_quem_pode` | Passa |
| T2 | Sem admin não limpa; precisa das duas confirmações; limpa só as marcadas | `test_tela_*` | Passa |
| V1 | Prévia e recusas em máquina real | máquina real | Pendente (11.6) |
| V2 | Limpar e conferir que as configurações ficaram | máquina real | Pendente (11.7) |
| V3 | Junction em Downloads | máquina real | Pendente (11.8) |

## Limites conhecidos

- A conta precisa estar sem sessão aberta.
- Pastas pessoais redirecionadas para fora do perfil (OneDrive) não são limpas.
- Programa só da conta apagado pode deixar a entrada em "Aplicativos instalados" daquela conta.
