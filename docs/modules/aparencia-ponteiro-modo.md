# Aparência: ponteiro, modo do Windows, aba Papel de parede e janela maximizada

**Branch:** `feat/monitores-video` · **Data:** 2026-11-13 · **ADR:** ADR-043, ADR-044, ADR-045,
ADR-046, ADR-047

Só `app/`; a API não muda. Pedidos do responsável na mesma sessão, entregues juntos.

## O que entrou

| Item | ADR | Onde |
|---|---|---|
| Janela principal abre maximizada (sem tela cheia) | ADR-043 | `__main__.py` |
| Modo claro ou escuro do Windows na aba Papel de parede, nas mesmas contas, menos a que roda o Bench | ADR-044 | `servicos/aparencia.py` (`MODO_WINDOWS`, `_TEMA`), `recursos/politicas/comum.ps1` (`$EXATAS_APARENCIA`), `ui/aparencia.py` (`PainelPapel`) |
| Ponteiro por quadradinhos Branco, Preto, Invertido e Personalizado | ADR-045 | `ui/ponteiro.py` (`SeletorPonteiro`, `Quadro`), `ui/aparencia.py` (`PainelMouse`) |
| Ponteiro colorido em seis cores fixas, gerado dos cursores do Windows | ADR-046 | `servicos/cursores.py`, `servicos/aparencia.py` (`_ponteiro`, `aplicar`), `recursos/politicas/escrever.ps1` |
| Tamanho do ponteiro de 1 a 15 por controle deslizante | ADR-047 | `servicos/aparencia.py` (`TAMANHOS`, `_ponteiro`), `ui/ponteiro.py` (`SetaIcone`, `QSlider`) |
| Aba Papel de parede: sem a frase e o botão de vídeo repetidos; Estilo e Modo lado a lado; prévia maior, sem cobrir a legenda; registro mais curto | ADR-041 (aba Monitores) | `ui/aparencia.py` (`PainelPapel`, `PreviaPapel`) |

## Decisões de implementação

- **Modo do Windows** é preferência por conta: `AppsUseLightTheme` e `SystemUsesLightTheme` em
  `Themes\Personalize`. Vai numa segunda chamada separada do papel de parede, porque o ADR-039
  libera a conta que roda o Bench só para o papel de parede. Desfazer devolve só o papel.
- **Ponteiro colorido:** o Windows 11 gera `*_eoa.cur` na conta pela página de Configurações; o
  Bench gera os seus a partir dos `aero_*.cur` (BMP de 32 bits), em
  `%ProgramData%\ITC\Bench\cursores\<cor>\` com a ACL da pasta do papel de parede. Os cursores
  são gerados antes de gravar o registro; se falharem, nenhuma conta muda. Ocupado e
  trabalhando (`.ani`) continuam os do Windows.
- **Tamanho:** `CursorSize = n` e `CursorBaseSize = 32 + (n - 1) x 16` para todos os estilos;
  preto e invertido usam só os arquivos do tamanho base. Os ids `_normal`, `_grande` e `_extra`
  saíram (`<cor>_<n>`).
- **Prévia do papel de parede:** mínimo de 280 x 170 px; o registro da aba tem no máximo 90 px.

## Verificação

App: 1043 passando, 10 pulados, 1 falha do ambiente local (`test_papel_de_parede`, exige
elevação); ruff, format e mypy limpos. Capturas com `QWidget.grab()` nos temas claro e escuro.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| A1 | Janela abre maximizada, sem tela cheia | `test_abre_maximizada`; `itc-bench --dev --teste` (código 0) | Passa |
| A2 | Modo do Windows: grava os dois valores; recusa fora da lista; fora de Mouse e teclado; desfazer volta ao claro | `test_modo_windows_*` em `test_aparencia.py` | Passa |
| A3 | Modo na tela: opções, confirmação e aplicação nas contas menos a do Bench | `test_papel_modo_do_windows_na_confirmacao`, `test_papel_aplica_modo_nas_contas_menos_a_do_bench` | Passa |
| A4 | Lista do comum.ps1 igual à do Python, com a chave do tema | `test_chaves_iguais_ao_trecho` | Passa |
| A5 | Quadradinhos marcam a linha e o valor; lista atualiza os quadradinhos; desenho nos dois temas | `test_quadrado_do_ponteiro_*`, `test_lista_do_ponteiro_*`, `test_quadrados_desenham_nos_dois_modos` | Passa |
| A6 | Personalizado com cor e tamanho; a fileira de cores só aparece com ele | `test_personalizado_com_cor_e_tamanho` | Passa |
| A7 | Recolorir troca o branco e mantém preto e transparência; recusa formato estranho | `test_recolorir_*` em `test_cursores.py` | Passa |
| A8 | Gera os 11 cursores numa pasta de teste; caminho no registro só do Bench | `test_preparar_gera_*`, `test_opcoes_e_escritas_do_ponteiro_colorido` | Passa |
| A9 | Falha ao gerar não grava nenhuma conta | `test_aplicar_colorido_gera_antes_e_falha_sem_gravar` | Passa |
| A10 | Trecho recusa cursor fora das pastas (4 casos); todo valor do catálogo passa na regra | `test_trecho_recusa_cursor_fora_das_pastas`, `test_todo_ponteiro_do_catalogo_passa_na_regra_do_trecho` | Passa |
| A11 | Tamanho de 1 a 15 e o cálculo do tamanho base | `test_ponteiro_tamanhos_de_1_a_15`, `test_ponteiro_preto_tamanho_6` | Passa |
| V1 | Modo escuro numa conta de teste | máquina real | Pendente (10.14) |
| V2 | Ponteiro rosa no tamanho 6 numa conta de teste | máquina real | Pendente (10.15) |

## Limites conhecidos

- A página do ponteiro nas Configurações do Windows mostra "Branco" com o ponteiro colorido do
  Bench; mexer nela pode trocar o esquema (ADR-046).
- Acima de 128 px o Windows amplia a imagem do cursor.
- O modo do Windows não é aplicado na conta que roda o Bench.
