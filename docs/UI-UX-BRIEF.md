# UI/UX Brief — ITC Bench

Fonte: `docs/design/README.md` e `docs/design/itc-bench-identidade-telas.html` (aprovados em
03/11/2026). Regras gerais de cor e contraste: skill `itc-identidade-visual`.

## Marca

- Símbolo: grade 64, módulo 8, traço 8u. Tela `#008F95` (retângulo 8,10 → 56,44), base
  `#1B1B1B` (barra 4 → 60 em y=52), prompt `›` `#003C3F`.
- Arquivos: `docs/design/simbolo/itc-bench-simbolo.svg` (principal), `-escuro.svg`
  (`#30A5AB`/`#F5F0E8`), `-mono.svg`, `-negativo.svg`, `-16.svg` (≤ 24px: traço 10u, prompt
  recolhido).
- Lockup: "ITC" Archivo 600, 11px, espaçamento .42em, ciano; "Bench" Archivo 800, 36px, -.025em,
  `#1B1B1B`. Mesma montagem do ITC NoteScan e do ITC Tasks.
- `.ico` multi-tamanho (16, 24, 32, 48, 256): pendente, módulo de empacotamento.

## Tokens (do HTML de design)

| Token | Valor | Uso |
|---|---|---|
| `--cy` | `#008F95` | Ciano principal |
| `--cy5` | `#30A5AB` | Ciano sobre escuro, item ativo na barra |
| `--cy9` | `#006C72` | Ícones e texto ciano sobre claro |
| `--cy12` | `#003C3F` | Prompt, texto sobre ciano claro |
| `--cy50` | `#E0F4F5` | Fundo de item selecionado |
| `--ink` | `#1B1B1B` | Texto, barra lateral |
| `--mute` / `--faint` | `#5F594E` / `#8A8378` | Texto secundário |
| `--page` / `--card` / `--well` | `#E9E5DD` / `#FDFBF7` / `#F5F0E8` | Fundos |
| `--line` / `--line2` | `#D8D2C6` / `#EDE8DE` | Bordas |
| `--ok` / `--warn` / `--err` / `--info` | `#1A7F3C` / `#CC7A00` / `#C0392B` / `#1565C0` | Estados |

Tipografia: Archivo (títulos, 400–800), Inter (interface, 400–600). Números e versões com
`tabular-nums`. No Qt, as fontes vão embutidas no app (Módulo 01).

## Ícones

18 ícones de navegação, grade 24, traço 2px, terminação reta, sem preenchimento; um por item do
menu. Desenhados em SVG no HTML de design (`inicio`, `prep`, `id`, `contas`, `wifi`, `remoto`,
`prog`, `remover`, `gpo`, `protecao`, `usb`, `aparencia`, `mouse`, `energia`, `diag`, `hist`,
`limpeza`, `registro`, `ajuda`, `config`). Extrair para arquivos no Módulo 01.

## Layout

- Janela com barra lateral escura (`--ink`), marca no topo, grupos com rótulo em caixa alta,
  rodapé com hostname · usuário e versão.
- Área principal: trilha (`Grupo › Tela`), título com "?", ações à direita (primária por último).
- Tabelas com coluna de situação em selo colorido (feito, pendente, não iniciado, atenção, crítico).
- Log ao vivo em fonte mono com horário.

## Estados obrigatórios por tela

Carregando, vazio, erro (com o que fazer), offline (dados do cache e data da última sincronização,
ex.: "sincronizado 11:40"), sem permissão.

## Conteúdo

- Português do Brasil, frases curtas, verbo no imperativo nas ações ("Instalar 2 redes").
- Endereços, chaves e nomes de máquina das telas de design são exemplos; não copiar para código
  nem para teste.
- Segredos nunca exibidos: senha mostrada como `••••••••`, chave pública truncada com "copiar".
