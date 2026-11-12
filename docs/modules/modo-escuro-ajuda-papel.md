# Pós-16 — Modo escuro, Ajuda em seções, papel de parede e topo das telas (ADR-037 a ADR-040)

Branch `feat/modo-escuro`, saindo de `develop` em `7b4b911`. Pedidos do responsável em
12/11/2026. Mesclada na `develop` e levada à `main` no mesmo dia, a pedido dele, na versão
0.19.0, sem bump e sem tag.

## Commits

```
6cc5e6d feat(ui): add dark mode and theme every control
29a032d feat(ui): split the help screen into sections
5ec6162 feat(appearance): wallpaper preview and apply on the account running the Bench
```

E o commit de documentação que leva este arquivo.

## O que entrou

### Modo escuro e tema em todos os controles (ADR-037)

- `app/src/itc_bench/ui/tema.py`:
  - `Paleta` com duas instâncias:
    - `CLARO`: valores do HTML de design, sem mudança;
    - `ESCURO`: superfícies `#141818`/`#1A2020`/`#1F2626`, linhas `#2C3434`, texto `#E6EAEA`,
      `--cy5` como destaque e estados `#7BC896`, `#E3A64A`, `#E57368`, `#6FA8E8`.
  - `aplicar(app, modo)` liga o estilo `Fusion`; `trocar(app, modo)` aplica a `QPalette`
    (`paleta_qt`) e a folha `qss(paleta)`.
  - A folha cobre o que antes ficava no estilo nativo do Windows: `QPushButton`, campos,
    `QComboBox` (seta `recursos/icones/seta.svg`), caixas de marcar e botões de opção (`marcado.svg`,
    `ponto.svg`), tabelas, árvores, listas, abas, rolagem, menus e dicas.
  - Seis nomes que existiam no código sem regra ganharam uma: `cartao`, `faixa`, `subtitulo`,
    `dica`, `perigo`, `link`.
  - Botão desativado em `borda_controle`, e `#perigo:disabled` sem o vermelho.
  - A barra lateral, a marca, o lado escuro de Entrar e o `#primario` (`--cy9`) são iguais nos dois
    modos.
- `app/src/itc_bench/servicos/preferencias.py` (novo, sem Qt):
  - `modo()` e `gravar_modo()` em `%LOCALAPPDATA%\ITC\Bench\preferencias.json` (`{"modo": ...}`);
  - gravação por `.tmp` + `replace`;
  - arquivo ilegível ou valor fora de `MODOS` vira `claro`.
- `app/src/itc_bench/__main__.py`: `tema.aplicar(app, preferencias.modo())`. A tela Entrar já abre
  no modo guardado.
- `app/src/itc_bench/ui/configuracoes.py`: caixa "Aparência do Bench" (Claro/Escuro), sinal
  `modo_escolhido`. `ui/janela.py`, `escolher_modo`: troca na hora e grava; se falhar, vale até
  fechar, com aviso.
- `app/src/itc_bench/ui/preparacao.py`: `COR` passa a guardar o tipo (`ok`, `aviso`, `erro`, `info`,
  `neutro`), e a cor vem de `tema.cor_situacao`.
- `app/src/itc_bench/ui/entrar.py`: `subtitulo` e `estado` com `setWordWrap(True)`. O texto
  cortava nos 360 px do formulário.

### Ajuda em seções (ADR-038)

- `app/src/itc_bench/ui/ajuda.py`:
  - **índice** (`QTreeWidget`, `ajudaIndice`) com os 7 grupos e as 20 telas, com os ícones da barra;
  - **à direita**, a ajuda da tela em `QScrollArea`: caminho, nome (`ajudaNome`), abertura
    (`ajudaAbertura`), um `cartao` por subtítulo, passos em círculo (`ajudaPasso`) e tópicos
    (`ajudaTopico`);
  - `blocos(texto)` separa pelos subtítulos que os `AJUDA*` já usam;
  - a busca filtra o índice;
  - "Abrir esta tela" emite `abrir_tela`, ligado a `Janela.abrir`;
  - `ir_para(chave)` escolhe a tela no índice.
- Só a ajuda da própria tela Ajuda (`AJUDA`) foi reescrita, para explicar o índice.

### Prévia do papel de parede (ADR-038)

- `app/src/itc_bench/ui/aparencia.py`:
  - `PreviaPapel`: monitor 16:9 com moldura e contorno; `destino()` posiciona a imagem por estilo
    (Centralizar numa tela de referência `TELA_REFERENCIA = (1920, 1080)`).
  - `carregar_previa`: extensão em `pp.EXTENSOES`, `pp.conferir_imagem`, decodificador fixo e
    leitura reduzida a 960 px.
  - Legenda com dimensões, tipo e tamanho.
  - "Baixar e ver a imagem" (só com administrador) roda `pp.obter` sem aplicar.
  - A ajuda da tela ganhou a seção "Prévia".

### Papel de parede na conta que roda o Bench (ADR-039)

- `app/src/itc_bench/servicos/papel_de_parede.py`: `aplicar(..., permitir_dono=False)` e
  `ler_com_dono()`, que devolve o SID da conta do Bench para a tela. `ler()` ficou igual para a
  Preparação.
- `app/src/itc_bench/recursos/politicas/comum.ps1`: `So-Papel`; `Hive-Escrita` libera a conta do
  Bench com perfil `aparencia` só se todas as operações forem em `$CHAVE_PAPEL`.
- `app/src/itc_bench/ui/aparencia.py`: a tela passa `permitir_dono=True`, mostra "(você)" na lista
  e avisa na confirmação e na ajuda.
- Preparação completa e Mouse e teclado continuam recusando.

### Topo das telas e botão de ajuda (ADR-040)

- `app/src/itc_bench/ui/janela.py`, classe `Tela`:
  - topo de 64 para 80 px, com margens de 12 px e caminho e título centralizados;
  - "?" redondo no canto direito (`#ajudaBotao`), com destaque em ciano ao passar o mouse;
  - cartão de ajuda a 88 px do alto.
- `app/src/itc_bench/ui/entrar.py`: o "?" da tela Entrar continua ao lado do título.

### Desfeito

Uma mudança na tela Registro (log colorido por partes, selos de avisos e erros) foi feita e
desfeita a pedido do responsável. `ui/registro.py` e os testes dela estão iguais à `develop`.

## Verificação

| Cenário | Como | Resultado |
|---|---|---|
| Sem arquivo de preferência | `test_modo_escuro.py::test_sem_arquivo_e_claro` | ✅ claro |
| Grava e lê; sem `.tmp` sobrando | `test_grava_e_le` | ✅ |
| JSON quebrado, lista, modo `roxo`, modo numérico | `test_arquivo_ruim_vira_claro` (4 casos) | ✅ claro |
| Modo desconhecido não grava | `test_recusa_modo_desconhecido` | ✅ `ValueError`, sem arquivo |
| Arquivo ilegível não põe o caminho no log | `test_preferencia_ilegivel_nao_loga_caminho` | ✅ |
| Claro com os valores do design | `test_claro_mantem_os_valores_do_design` | ✅ |
| Barra lateral, marca e primário iguais nos dois modos | `test_barra_lateral_igual_nos_dois_modos` | ✅ |
| Contraste WCAG AA (texto 4,5; estados e secundário 3) | `test_contraste_do_texto` (claro e escuro) | ✅ |
| Troca muda paleta, folha e cor de situação | `test_trocar_muda_paleta_e_folha` | ✅ `Base` `#1A2020` no escuro |
| Situações da Preparação seguem o modo | `test_situacoes_da_preparacao_seguem_o_tema` | ✅ |
| Configurações mostra o modo e emite a escolha | `test_configuracoes_emite_o_modo` | ✅ |
| Ajuda cobre as 20 telas na ordem do menu | `test_modulo13_tela.py::test_ajuda_cobre_todas_as_telas_na_ordem_do_menu` | ✅ |
| Busca filtra o índice; sem resultado mostra vazio | `test_painel_ajuda_filtra` | ✅ |
| "Ver toda a ajuda" e "Abrir esta tela" | `test_painel_ajuda_vai_para_a_tela_e_abre` | ✅ sinal com `contas` |
| Subtítulos, passos, tópicos e continuação | `test_ajuda_separa_secoes_passos_e_topicos` | ✅ |
| Nenhuma palavra das 20 ajudas se perde | `test_toda_ajuda_vira_secoes_sem_perder_texto` | ✅ |
| Imagem não baixada oferece baixar (só admin) | `test_aparencia_tela.py::test_papel_previa_sem_baixar_oferece_baixar` | ✅ |
| Arquivo escolhido aparece na prévia; estilo troca | `test_papel_previa_do_arquivo_escolhido` | ✅ `1600x900 · PNG` |
| Conteúdo inválido, < 640x480, `.gif`, PNG chamado `.jpg` | `test_papel_previa_recusa_arquivo_invalido` | ✅ recusados; 3840x2160 lido a 960 px |
| Posição por estilo (quatro estilos) | `test_papel_previa_posiciona_por_estilo` | ✅ |
| Conta do Bench com "(você)" e aviso | `test_tela_aceita_a_conta_que_roda_o_bench` | ✅ |
| `pp.aplicar` com `permitir_dono` escreve na conta do Bench; Suporte recusada | `test_papel_de_parede.py::test_tela_aplica_na_conta_que_roda_o_bench` | ✅ `ITC_PERMITIR_DONO=1`, perfil `aparencia` |
| Sem `permitir_dono` (Preparação), conta do Bench recusada | `test_aplicar_por_alvo_sem_caminho_no_log` (já existia) | ✅ |
| Trecho: liberação só para `politicas` ou `aparencia` com papel | `test_politicas.py::test_trecho_libera_dono_so_para_politicas_e_papel` | ✅ |
| PowerShell real: politicas/1, papel/1 passam; politicas/0, aparencia sem ops, papel/0, Mouse/1 recusam | `test_hive_escrita_real_conta_que_roda` (6 casos) | ✅ nesta máquina, sem pulo |
| Telas nos dois modos | capturas `QWidget.grab()` de Entrar, Início, Preparação, Contas, Configurações, Ajuda e papel de parede | ✅ conferidas a olho |
| Topo de 80 px e "?" redondo à direita; Entrar com "?" ao lado do título | capturas da tela Programas nos dois modos; `test_janela.py`, `test_entrar.py` | ✅ "?" abre e fecha o cartão (`test_janela.py`) |
| Modo escuro com o Bench instalado e elevado | roteiro 11.5 | pendente (máquina real) |
| "Baixar e ver a imagem" com cadastro real | roteiro 10.9 | pendente (máquina real) |
| Ajuda nova na janela instalada | roteiro 11.3 | pendente (máquina real) |
| Papel na conta do Bench, logon e Desfazer | roteiro 10.10 | pendente (máquina real) |

Comandos: `ruff check` e `ruff format --check` limpos, `mypy` sem erro em 70 arquivos.
`pytest` (12/11/2026, depois das correções da auditoria): **951 passando, 10 pulados, 2 falhas
do ambiente local**, as mesmas da `develop`, que não dependem desta mudança (como em
`contas-por-turno.md`):
- `test_papel_de_parede.py::test_trecho_aparencia_recusa_valor_e_caminho_fora`: o trecho exige
  elevação;
- `test_paridade.py::test_gravacoes_anonimas`: o nome da conta do Windows "Teste" aparece em
  `bateria.json`.

27 casos de teste novos:
- 15 em `tests/test_modo_escuro.py` (novo);
- 5 em `test_aparencia_tela.py`;
- 3 em `test_modulo13_tela.py`;
- 1 em `test_papel_de_parede.py`;
- 3 casos a mais no parametrizado de `test_politicas.py`.

## Pontos de atenção

- **Fusion:** com o estilo `Fusion`, os controles deixam de ter a aparência exata do Windows 11.
  Foi escolha do responsável ("tema em tudo"). Voltar ao estilo nativo quebra o modo escuro, porque
  o `windows11` ignora parte da folha e da paleta.
- **Especificidade:** `#cartao QLabel` (fundo transparente) ganha de `#ajudaPasso`. Por isso o
  círculo do passo usa `#cartao QLabel#ajudaPasso`. Estilo novo para `QLabel` dentro de cartão
  precisa do mesmo cuidado.
- **Cor de situação:** a cor pintada numa linha da Preparação fica até a próxima atualização da
  lista depois de trocar o modo.
- **Formato das ajudas:** subtítulo curto sem pontuação final, passos `1.` e tópicos `•`
  (`docs/UI-UX-BRIEF.md`). Um subtítulo terminado em ponto vira texto comum.
- **Duas conferências da conta do Bench:** a liberação depende de `So-Papel` no PowerShell.
  Qualquer operação nova no perfil `aparencia` que não seja na `$CHAVE_PAPEL` volta a ser recusada
  na conta do Bench, o que é o comportamento desejado para mouse e teclado.

## Pendente

Roteiro de máquina real 10.9, 10.10, 11.3 e 11.5. Auditoria:
`docs/security/2026-11-12-modo-escuro-ajuda-papel.md`.
