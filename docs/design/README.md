# Design — ITC Bench

Material aprovado em 03/11/2026, antes do Módulo 00.

| Arquivo | Conteúdo |
|---|---|
| `itc-bench-identidade-telas.html` | Nome, símbolo (grade 64, traço 8u), versões de cor, 18 ícones de navegação (grade 24, traço 2px), organização do menu em 7 grupos e 8 telas: Entrar, Início, Preparação completa, Programas, Diagnóstico, Wi-Fi com ajuda aberta, Acesso remoto, Ajuda. Abrir no navegador. |
| `simbolo/itc-bench-simbolo.svg` | Principal: tela `#008F95`, base `#1B1B1B`, prompt `#003C3F` |
| `simbolo/itc-bench-simbolo-escuro.svg` | Sobre fundo escuro: `#30A5AB` e `#F5F0E8` |
| `simbolo/itc-bench-simbolo-mono.svg` | Preto chapado |
| `simbolo/itc-bench-simbolo-negativo.svg` | Branco chapado |
| `simbolo/itc-bench-simbolo-16.svg` | Variante para 24px ou menos: traço 10u, prompt recolhido |

Família visual: mesma montagem do ITC NoteScan e do ITC Tasks. "ITC" em Archivo 600, 11px, espaçamento .42em, ciano; nome em Archivo 800, 36px, -.025em, grafite `#1B1B1B`. Interface em Inter; números e versões com `tabular-nums`. Paleta e regras de contraste: skill `itc-identidade-visual`.

Endereços, chave e nomes de máquina que aparecem nas telas são exemplos. Os dados reais vêm da base ITC Bench no NocoDB, pela API.

Pendente: o `.ico` multi-tamanho (16, 24, 32, 48, 256) é gerado a partir dos SVGs no módulo de empacotamento.
