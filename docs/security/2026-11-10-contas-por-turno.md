# Auditoria de segurança — Contas por turno na Identificação — 2026-11-10

Escopo: ADR-029. `servicos/contas_turno.py`, `ui/identificacao.py`, `servicos/contas.py`
(`permitir_nome_computador`), `recursos/contas/criar.ps1` e `ui/janela.py`. Branch
`feat/contas-por-turno`. Sem mudança na API. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 3 (riscos aceitos pelo responsável, no ADR-029) |

## Riscos aceitos

### [INFORMATIVA, decisão do responsável] Contas sem senha

As contas por turno são Local padrão e não têm senha (ADR-029, item 5): quem está diante da
máquina entra em qualquer turno. Elas não são administradoras: `contas_turno.criar` sempre passa
`tipo="padrao"` e nunca passa senha (teste `test_criar_cria_so_o_que_falta_padrao_e_sem_senha`).

### [INFORMATIVA, decisão do responsável] Conta com o nome do computador

Sem turno e sem sufixo, a conta leva o nome do computador (ADR-029, item 6). A recusa continua
valendo na tela Contas: o padrão de `permitir_nome_computador` é `False`, em Python e em
`criar.ps1`, onde só `ITC_PERMITIR_NOME_PC = '1'` desliga a regra.

### [INFORMATIVA] Reinício

Só com duas confirmações, pelo `identificacao.reiniciar` existente (`shutdown.exe` em
`System32`, por lista de argumentos, sem dado do operador). Ver ADR-023, item 5.

## Categorias

1. **Banco sem tranca:** não se aplica. Nada é gravado em disco, nem no cache, nem em `protegido\`.
2. **Permissão no navegador:** o botão fica desativado sem administrador, mas o bloqueio real é
   o Windows: `New-LocalUser` exige elevação. `contas.criar` confere o nome de novo sobre uma
   leitura nova, e `criar.ps1` confere de novo no PowerShell (conta existente, grupo, Suporte).
3. **IDOR:** não se aplica. Nenhuma chamada à API.
4. **Chaves expostas:** nenhuma senha, token ou host no código, nos testes ou na documentação.
   Os testes usam só nomes fictícios (`BSBIA02-EST32`, `PC-TESTE`).
5. **Inputs sem tratamento:**
   - O sufixo passa por uma lista fechada de caracteres (`SUFIXO`: letras sem acento, números,
     `-` e `_`) e o nome final por `contas.validar_nome` (20 caracteres, reservados, Suporte).
   - O nome vai ao PowerShell só por `ITC_NOME` (executor), nunca no texto do script.
   - Prévia, resumo e janelas em texto puro: `_rotulo` usa `Qt.PlainText`, e `escolher` e a
     mensagem de "Deixar para depois" também fixam `PlainText`. As mensagens do Windows só
     aparecem dessa forma.

## Log

`contas_turno.criar` registra só as contagens. O nome de cada conta criada vai pelo log de
`contas.criar`, como o ADR-017 já permite. Nenhuma senha (não há), SID ou caminho de perfil.
