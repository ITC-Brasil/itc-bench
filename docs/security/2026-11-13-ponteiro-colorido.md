# Auditoria — Ponteiro colorido (ADR-046), 2026-11-13

Prompt: `docs/security/AUDIT-PROMPT.md`. Escopo: `servicos/cursores.py`, as mudanças em
`servicos/aparencia.py`, `recursos/politicas/escrever.ps1` e `ui/ponteiro.py`.

| Categoria | Resultado |
|---|---|
| 1. Banco sem tranca | Pasta nova `%ProgramData%\ITC\Bench\cursores\` com `acl.SDDL` (Usuários só leem; Administradores e SYSTEM gravam), conferida depois de aplicar e sem ponto de reparse (`acl.verificar_reparse`). Um aluno não troca o cursor que outra conta usa. |
| 2. Permissão no navegador | Gerar e gravar só acontece no Aplicar, que exige administrador e não roda no `--dev`. Sem administrador, a criação da pasta e a ACL falham e nenhuma conta é alterada. |
| 3. IDOR | Não se aplica: a cor vem de uma lista fechada; o caminho é montado pelo Bench (`cursores.arquivo`). |
| 4. Chaves expostas | Nenhum segredo. |
| 5. Inputs sem tratamento | A fonte é a pasta de cursores do Windows (pela API). `recolorir` confere cabeçalho, tipo `.cur`, número de imagens, limites de cada entrada e BMP de 32 bits antes de tocar nos bytes; arquivo maior que 2 MB é recusado. O trecho `escrever.ps1` aceita em `Control Panel\Cursors` só `%SystemRoot%\cursors\<nome>.cur/.ani` ou `…\ITC\Bench\cursores\<cor da lista>\aero_<nome>.cur` existente (`test_trecho_recusa_cursor_fora_das_pastas`, 4 casos; `test_todo_ponteiro_do_catalogo_passa_na_regra_do_trecho`). |

## Achados

- **[INFORMATIVA] Configurações do Windows mostram "Branco".** O Bench grava `CursorType = 0` com
  os arquivos coloridos; se o aluno mexer na página do ponteiro, o Windows pode trocar o esquema.
  Risco aceito no ADR-046 (é preferência).
- **[INFORMATIVA] Formato dos cursores do Windows.** Se mudar, `recolorir` recusa e a cor não é
  aplicada, sem gravar nada (`test_aplicar_colorido_gera_antes_e_falha_sem_gravar`).

Nenhum achado crítico, alto, médio ou baixo.

## Pontos fortes verificados

- Os testes geram cursores só na pasta temporária do pytest; nenhum grava em `%ProgramData%`
  real nem no registro da conta (o trecho real é chamado com valores que ele recusa antes de
  abrir o registro).
- Log só com o id da cor e o tipo de erro; nenhum caminho.
