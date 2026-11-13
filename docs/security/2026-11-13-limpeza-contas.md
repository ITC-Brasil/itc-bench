# Auditoria — Limpeza de contas (ADR-042), 2026-11-13

Prompt: `docs/security/AUDIT-PROMPT.md`. Escopo: `recursos/limpeza/contas.ps1`, as funções novas
de `servicos/limpeza.py`, `PainelLimpezaContas` em `ui/limpeza.py` e a mudança em `ui/janela.py`.

| Categoria | Resultado |
|---|---|
| 1. Banco sem tranca | Não se aplica: nada é gravado. O que se apaga é por conta; uma conta nunca recebe dado de outra. |
| 2. Permissão no navegador | O botão só existe com administrador e fora do `--dev`. As recusas valem no Python (`recusa_conta`) e de novo no trecho (`Recusa`): nativo, Suporte, Gestão, dono do processo e sessão aberta. Sem administrador, o próprio Windows nega acesso aos perfis alheios. |
| 3. IDOR | O SID vem da listagem do Windows (`contas.listar`), não de texto digitado; o trecho confere o formato `S-1-5-21-…`, o `ProfileList` e que o perfil fica em `<sistema>\Users`. |
| 4. Chaves expostas | Nenhum segredo; os testes usam SIDs e nomes fictícios. |
| 5. Inputs sem tratamento | Sem interpolação: SIDs e nomes protegidos vão por `ITC_SIDS` e `ITC_PROTEGIDAS`. Caminhos montados só com partes fixas do trecho; cada item conferido contra a raiz; reparse point nunca seguido. Nome da conta só em `QTreeWidgetItem` (texto puro) e nas confirmações PlainText. |

## Achados

- **[INFORMATIVA] Corrida entre a checagem de sessão e a varredura.** Se alguém entrar na conta
  durante a limpeza, arquivos abertos ficam e são contados como "em uso". Sem perda de
  configuração: o registro da conta nunca é tocado.
- **[INFORMATIVA] Apagar de vez.** Decisão do responsável (ADR-042), com prévia e duas
  confirmações.
- **[BAIXA, corrigida] Suporte sem cadastro.** A primeira versão confiava só nos nomes passados
  pela tela; `_suporte` passa a incluir sempre `Suporte` (ADR-017), coberto por
  `test_recusa_conta`.

Nenhum achado crítico, alto ou médio aberto.

## Pontos fortes verificados

- O trecho não usa `Remove-Item`, não escreve no registro e não cita `NTUSER`
  (`test_trecho_so_pastas_fixas_e_nunca_o_registro_da_conta`).
- Varredura igual à da limpeza de manutenção (ADR-023): reparse removido como link, prefixo
  conferido, só números na saída.
- Testes nunca apagam arquivo de conta real: o trecho real só roda com SIDs que ele recusa.
