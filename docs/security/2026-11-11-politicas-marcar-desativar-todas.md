# Auditoria de segurança — Políticas: marcar/desmarcar e desativar todas — 2026-11-11

Escopo: ADR-033. `ui/politicas.py` (botões "Marcar todas"/"Desmarcar todas" e "Desativar
todas", `_executar` com lista de políticas explícita). Branch
`feat/politicas-marcar-desativar-todas`. Sem mudança no serviço, na API ou no NocoDB. Feita com
`docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 1 |

## Achado

### [INFORMATIVA] Um clique tira todas as restrições de segurança dos alvos marcados

"Desativar todas" desfaz o catálogo inteiro (CMD, Regedit, Painel, Store, PowerShell, ICS…) nos
alvos marcados. Mitigações: exige o Bench elevado e técnico logado; os alvos são escolhidos à
mão (nenhum marcado = aviso, nada feito); a confirmação lista cada política × alvo com a mudança
e começa por "Desativar TODAS"; as recusas do ADR-021 (nativo, Suporte, conta que roda o Bench)
continuam no serviço e no trecho; o USB fica de fora. O log registra cada política e alvo como no
Desfazer, sem nome de conta nem SID.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** o botão segue a mesma regra do Desfazer (`_ocupar`: administrador,
   não ocupado, leitura feita); a recusa real continua no serviço (`politicas.aplicar`) e no
   PowerShell. "Marcar todas" só muda a tela e vale sem administrador.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** nada novo.
5. **Inputs:** nenhum dado novo vai ao serviço: só ids do catálogo fixo no código; textos da tela
   em texto puro (`confirmar`, `PlainText`).
