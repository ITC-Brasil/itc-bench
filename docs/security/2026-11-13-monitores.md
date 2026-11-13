# Auditoria — Monitores (ADR-041), 2026-11-13

Prompt: `docs/security/AUDIT-PROMPT.md`. Escopo: `nucleo/video.py`, `servicos/video.py`,
`ui/monitores.py` e as mudanças em `ui/janela.py`, `ui/aparencia.py` e nos testes.

| Categoria | Resultado |
|---|---|
| 1. Banco sem tranca | Não se aplica: o Bench não grava nada (o Windows guarda resolução e escala). |
| 2. Permissão no navegador | Informativa: Aplicar só com administrador e fora do `--dev` (`__main__.py:71` força `admin=False`). O serviço não confere admin, mas o próprio Windows deixa qualquer usuário mudar resolução e escala pelas Configurações; o Bench não dá privilégio novo. |
| 3. IDOR | Não se aplica. O dispositivo (`\\.\DISPLAYn`) vem da leitura do Windows e é conferido de novo em `validar`; monitor que saiu é recusado. |
| 4. Chaves expostas | Nenhum segredo nos arquivos novos; os testes usam nome fictício de monitor. |
| 5. Inputs sem tratamento | O nome do monitor (EDID, controlado pelo fabricante) só aparece em `QLabel` PlainText (`ui/contas.py`, `_rotulo`) e na confirmação PlainText; nunca no log (`test_log_sem_nome_do_monitor`). Valores aplicados só da lista do Windows, validados no serviço; estruturas ctypes com tamanho conferido no import. |

## Achados

- **[INFORMATIVA] API não documentada para a escala** (`nucleo/video.py`, `TIPO_LER_ESCALA` e
  `TIPO_GRAVAR_ESCALA`). Uma mudança futura do Windows pode quebrar a leitura; o Bench desliga a
  lista de escala e segue com o resto. Risco aceito no ADR-041.
- **[INFORMATIVA] Monitor sem imagem depois de aplicar.** Mitigado: `CDS_TEST` antes e volta
  automática em 15 s sem resposta.

Nenhum achado crítico, alto, médio ou baixo.

## Pontos fortes verificados

- Sem processo, sem `shell`, sem registro escrito pelo Bench; ctypes só em `nucleo/video.py`, na
  lista fechada de `test_invariantes.py`.
- Os testes não alteram o monitor real (`conftest.py`, `_sem_mudar_monitor`).
