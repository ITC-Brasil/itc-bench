# Auditoria — Modo do Windows, seletor e tamanho do ponteiro, janela maximizada, 2026-11-13

Prompt: `docs/security/AUDIT-PROMPT.md`. Escopo: ADR-043, ADR-044, ADR-045 e ADR-047
(`__main__.py`, `servicos/aparencia.py`, `recursos/politicas/comum.ps1`, `ui/aparencia.py`,
`ui/ponteiro.py`). O ponteiro colorido (ADR-046) tem auditoria própria:
`2026-11-13-ponteiro-colorido.md`.

| Categoria | Resultado |
|---|---|
| 1. Banco sem tranca | Não se aplica: nada novo é guardado pelo Bench. |
| 2. Permissão no navegador | Aplicar continua só com administrador e fora do `--dev`. O modo do Windows não é aplicado na conta que roda o Bench: a tela tira essa conta da chamada, e o `comum.ps1` recusaria de novo (`So-Papel` só libera o papel de parede para o dono, ADR-039). |
| 3. IDOR | O alvo continua sendo o SID das contas listadas pelo Windows, com as recusas do `hive.recusa_alvo` (nativo, Suporte, Gestão). |
| 4. Chaves expostas | Nenhum segredo. |
| 5. Inputs sem tratamento | A lista fechada de chaves do perfil `aparencia` ganhou só a chave exata `Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`, nas duas camadas (`CHAVES_ACEITAS` e `$EXATAS_APARENCIA`, conferidas iguais por `test_chaves_iguais_ao_trecho`). Valores só `0` e `1` vindos do catálogo (`MODO_WINDOWS`); opção fora da lista recusada (`test_modo_windows_grava_os_dois_valores_do_tema`). Tamanho do ponteiro só de 1 a 15 (`branco_0` e `branco_16` não existem). Os quadradinhos são desenhados pelo Bench, sem ler arquivo; rótulos em texto puro. |

## Achados

- **[INFORMATIVA] Chave nova no perfil `aparencia`.** `Themes\Personalize` é preferência da
  conta (herda a ACL, o aluno pode trocar). Não é política, não abre caminho para outras chaves:
  a regra continua por igualdade exata.
- **[INFORMATIVA] Ids antigos do ponteiro.** Contas que tivessem "preto, grande" do Bench
  aparecem como "diferente" até reaplicar (ADR-047). Nenhuma versão com esses ids foi
  distribuída depois deste corte de tamanho.

Nenhum achado crítico, alto, médio ou baixo. A janela maximizada (ADR-043) não muda superfície
de ataque.

## Pontos fortes verificados

- Serviço e trecho do ponteiro sem mudança de regra no ADR-045 e no ADR-047: só a tela e os
  valores gravados, ainda da lista fechada.
- Dica e textos novos em texto puro (`test_texto_puro.py` passa; a dica das colunas da Limpeza de
  contas foi corrigida para `texto.dica`).
