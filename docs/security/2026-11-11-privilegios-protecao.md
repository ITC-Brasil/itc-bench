# Auditoria de segurança — Privilégios ligados só durante a operação — 2026-11-11

Escopo: ADR-035. `nucleo/acl.py` (`habilitar_privilegios`, `desabilitar_privilegios`,
`proteger`), `servicos/protecao.py` (`alterar`, `_alterar_arquivos`). Branch
`feat/politicas-marcar-desativar-todas`. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 1 (corrigido) |
| Informativa | 1 |

## Achados

### [BAIXA, corrigido] Privilégios ligados pelo resto da execução

`nucleo/acl.py`, `proteger`: na segunda tentativa do ACL de `%ProgramData%\ITC`, o Bench ligava
SeTakeOwnership e SeRestore e nunca os desligava. Daí em diante, o Bench e todo processo que
ele abrisse (instaladores, PowerShell, `msiexec`) rodavam com eles ligados, passando por cima
das permissões de arquivo. Condição: a primeira tentativa do ACL falhar com acesso negado.
Correção: desliga num `finally` (teste `test_falha_que_sobra_vira_erro`).

### [INFORMATIVA] Janela com os privilégios ligados na Proteção do login

Entre ligar e desligar rodam só `takeown` e `icacls` por caminho absoluto, com argumentos fixos
e só nos arquivos `utilman.exe` e `sethc.exe` (`PROTEGIVEIS`). O `finally` desliga mesmo com
exceção (`test_privilegios_desligados_mesmo_com_excecao`). Não abre processo novo além desses.

## Conferido

- Sem processo novo, sem `ITC_*` novo, sem dado externo: o `ctypes` continua só em
  `nucleo/acl.py`, que já estava na lista fechada (`test_invariantes.py`).
- O dono volta ao TrustedInstaller (exigência do ADR-022) com o SeRestore ligado; a negação
  ao SYSTEM continua igual.
- Log: só o tipo da exceção ao ligar ou desligar; nenhum caminho de perfil, SID ou nome.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** exige o Bench elevado; `--dev` só lê.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** nada novo.
5. **Inputs:** nenhum dado externo nos comandos.
