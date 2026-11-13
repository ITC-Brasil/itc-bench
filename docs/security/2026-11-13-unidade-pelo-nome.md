# Auditoria — Unidade pelo nome do computador (ADR-048), 2026-11-13

Prompt: `docs/security/AUDIT-PROMPT.md`. Escopo: `codigo_do_nome`, `nome_do_computador` e
`unidade_pelo_nome` em `servicos/cadastros.py`; `_identificar_unidade`, `escolher_unidade` e
`_avisos_cadastros` em `ui/janela.py`; a ajuda de `ui/configuracoes.py`.

| Categoria | Resultado |
|---|---|
| 1. Banco sem tranca | A unidade decide o filtro do Wi-Fi no cache DPAPI (`Armazem.filtrar`, `sincronizar(..., unidade)`). Escolher uma unidade só **restringe**: sem unidade (bancada) o cache já guarda o Wi-Fi de todas. Nomear a máquina com o código de outra unidade não dá acesso a nada que a bancada não tenha. Os outros cadastros (servidores, instaladores) não dependem da unidade. |
| 2. Permissão no navegador | Gravar a unidade em HKLM continua exigindo administrador (`gravar_unidade`); sem ele, vale só na sessão, como antes. Trocar o nome do computador também exige administrador. |
| 3. IDOR | O código vem do nome do computador, mas só vale se existir em `Cadastros.unidades`, que vem da API; código fora do cadastro não escolhe nada. A API valida a unidade de novo (`?unidade=`, ADR-014). |
| 4. Chaves expostas | Nenhum segredo; os testes usam códigos fictícios e o `conftest.py` fixa o nome. |
| 5. Inputs sem tratamento | O nome entra só por `fullmatch` em `^[A-Z]{1,6}[0-9]{2}$` depois de cortado no primeiro hífen; nada é interpolado em comando. Os avisos vão para `QLabel` PlainText (`configuracoes.aviso`). O log tem o código da unidade, que já aparecia ("Unidade desta máquina"), e não o nome do computador. |

## Achados

- **[INFORMATIVA] Bancada com nome no padrão.** Sem unidade gravada, "bancada" escolhida vale só
  na sessão; na próxima, o nome volta a escolher a unidade e o cache passa a ter só o Wi-Fi dela.
  Efeito de disponibilidade, não de segurança. Registrado no ADR-048.

Nenhum achado crítico, alto, médio ou baixo.

## Pontos fortes verificados

- A escolha automática usa o mesmo `escolher_unidade` da escolha manual (grava com admin,
  ressincroniza, filtra o cache), sem caminho novo.
- A escolha do técnico na sessão vale mais que o nome (`unidade_manual`), e a divergência é
  avisada sem trocar (`test_escolha_manual_vale_mais_que_o_nome`).
