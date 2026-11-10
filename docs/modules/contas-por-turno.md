# Pós-16 — Contas por turno na Identificação (ADR-029)

Branch `feat/contas-por-turno`, saindo de `develop`. Pedido do responsável em 10/11/2026.

## O que entrou

- `app/src/itc_bench/servicos/contas_turno.py` (sem Qt): `nomes()`, `validar_sufixo()`, `previa()`
  e `criar()`, que gera o `Resumo` (criados, já existentes, erros).
- `app/src/itc_bench/ui/identificacao.py`: um bloco só, "Configuração do computador": nome (já
  preenchido com o que vale depois de reiniciar), turnos Manhã/Tarde/Noite, sufixo opcional,
  prévia automática (com a linha "Renomear X → Y" quando o nome muda) e um botão, "Renomear e
  criar usuários" ou "Criar usuários". O botão "Reiniciar agora" e a pergunta de reinício depois
  do renomear saíram: o reinício só é oferecido depois da criação, com duas confirmações.
- `contas_turno.configurar`: renomeia se o nome mudou e só então cria as contas; se o renomear
  falhar, nenhuma conta é criada.
- `servicos/contas.py` e `recursos/contas/criar.ps1`: `permitir_nome_computador` (padrão
  desligado), usado só pelas contas por turno.
- `ui/janela.py`: a tela recebe os cadastros para proteger o nome da Suporte.

## Verificação

| Cenário | Esperado | Resultado |
|---|---|---|
| Manhã + Tarde + Noite | `BASE-Manha`, `BASE-Tarde`, `BASE-Noite` | ok (teste) |
| Só Manhã / só Tarde / só Noite | uma conta do turno | ok (teste) |
| Manhã + Tarde | duas contas | ok (teste) |
| Manhã + Noite | duas contas | ok (teste) |
| Tarde + Noite | duas contas | ok (teste) |
| Nenhum turno, sem sufixo | `BASE` (nome do computador) | ok (teste) |
| Nenhum turno, sufixo `Recepcao` | `BASE-Recepcao` | ok (teste) |
| Turno marcado e sufixo preenchido | sufixo ignorado, campo desativado com aviso | ok (teste de tela) |
| Ordem marcada Noite, Manhã | sai Manhã, Noite | ok (teste) |
| Nome final acima de 20 caracteres | ✕ na prévia, botão desativado | ok (teste) |
| Sufixo com acento, espaço ou hífen na ponta | ✕ na prévia | ok (teste) |
| Conta já existe | ⚠ "já existia", não chama o PowerShell | ok (teste) |
| Erro numa conta | ✕ com o motivo, as outras seguem | ok (teste) |
| Contas criadas | Local padrão, sem senha, `ITC_PERMITIR_NOME_PC=1` | ok (teste) |
| Sem administrador | botão desativado, "Exige administrador." | ok (teste de tela) |
| Resumo | computador, linhas por conta, totais | ok (teste de tela) |
| Nome trocado no campo | prévia com "Renomear X → Y", botão "Renomear e criar usuários" | ok (teste de tela) |
| Renomear e criar | `renomear` com o nome novo e contas com ele como base | ok (teste) |
| Renomear falha | nenhuma conta criada, sem pergunta de reinício | ok (teste e teste de tela) |
| Nome igual ao atual | não renomeia, só cria | ok (teste) |
| Botão "Reiniciar agora" da tela | não existe mais | ok (teste de tela) |
| "Deixar para depois" | não reinicia | ok (teste de tela) |
| "Reiniciar agora" → "Cancelar" | não reinicia | ok (teste de tela) |
| "Sim, reiniciar" | `shutdown /r /t 10` e o Bench fecha | pendente (máquina real) |
| Criar contas de verdade, elevado | contas no Windows | pendente (máquina real) |

Comandos: `ruff check`, `ruff format --check` e `mypy` limpos; `pytest` com 846 passando e 10
pulados. As duas falhas são do ambiente local e não dependem desta mudança: o nome da conta do
Windows "Teste" aparece em `bateria.json` (`test_paridade`), e o trecho do papel de parede exige
elevação (`test_papel_de_parede`). `itc-bench --teste` com código 0. 34 testes novos em
`tests/test_contas_turno.py`.

## Pendente

Roteiro de máquina real: criar as contas elevado, conferir que são Local padrão e sem senha, e
reiniciar pelo "Sim, reiniciar".
