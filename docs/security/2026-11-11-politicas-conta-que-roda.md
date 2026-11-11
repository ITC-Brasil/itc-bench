# Auditoria de segurança — Políticas na conta que roda o Bench — 2026-11-11

Escopo: ADR-034. `servicos/hive.py` (`recusa_alvo`, `escrever`, `aplicar` com
`permitir_dono`), `servicos/politicas.py` (`aplicar`), `recursos/politicas/comum.ps1`
(`Hive-Escrita`), `ui/politicas.py` (aviso e ajuda). Branch
`feat/politicas-marcar-desativar-todas`. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 1 (risco aceito, ADR-034) |

## Achado

### [INFORMATIVA, risco aceito] O técnico pode restringir a própria conta

Com a conta que roda o Bench marcada, as políticas valem para ela no próximo logon. Mitigações:
aviso na confirmação, ajuda da tela, Desfazer e Desativar todas. Não é escalada de privilégio: a
política só restringe, e quem aplica já é administrador elevado.

## Conferido

- **Escopo da liberação:** só o perfil `politicas` com `ITC_PERMITIR_DONO=1` libera no
  PowerShell; o perfil `aparencia` continua com `ERRO|dono` (teste real
  `test_hive_escrita_real_conta_que_roda`, 3 casos). Em Python, o padrão de `permitir_dono` é
  falso (Aparência e Preparação; `test_recusa_dono_so_sem_permissao`).
- **Recusas mantidas:** RID 500 e Suporte, no Python e no trecho.
- **Variável nova:** `ITC_PERMITIR_DONO` só aceita `1`; qualquer outro valor mantém a recusa. O
  executor continua exigindo `ITC_[A-Z0-9_]+` e apaga `ITC_*` herdado.
- **Log:** sem mudança; sem nome de conta nem SID.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** a tela só avisa; a regra está no serviço e no trecho.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** nada novo.
5. **Inputs:** a variável nova é um sinalizador fixo; nenhum dado do usuário entra no trecho.
