# Auditoria de segurança — Contas: filtro e encerrar sessões — 2026-11-11

Escopo: ADR-036. `servicos/contas.py` (`modificavel`, `com_sessao`, `encerrar_sessao`,
`RESTRITAS`, `recusa`, `mudariam`, `validar_nome`, mensagens), `servicos/etapas.py`
(`_admins_extra`), `recursos/contas/comum.ps1`, `criar.ps1` e `lote.ps1` (`$RESTRITAS`), `recursos/contas/encerrar.ps1`, `ui/contas.py` (filtro, `EscolherSessoes`,
`_encerrar`). Branch `feat/politicas-marcar-desativar-todas`. Feita com
`docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 2 |

## Achados

### [INFORMATIVA] Encerrar sessão perde o trabalho não salvo da conta

É o efeito pedido. Mitigações: lista só de contas com sessão, marcação explícita, confirmação com
os nomes e o aviso "fechados sem salvar"; a sessão do Bench é recusada no trecho.

### [INFORMATIVA] O filtro é só da tela

"Não modificáveis" esconde ações na tela, mas a recusa real continua no serviço e no trecho
(ADR-017: `recusa`, `comum.ps1`). Nenhuma regra de segurança depende do filtro.

## Conferido

- **Gestão restrita:** recusada no Python (`recusa`) e de novo no trecho (`Recusa` do
  `comum.ps1`), com teste real no PowerShell para `Gestão`, `gestao` e `GESTÃO`; nome reservado
  em `validar_nome` e `criar.ps1`; fora do lote no `mudariam` e no `lote.ps1`. A lista é fixa
  no código, igual nos dois lados (`test_trechos_tem_a_mesma_lista_de_restritas`). Não vale
  como Suporte (`suporte_ok`), então o "Remover administrador de todos" continua exigindo a
  Suporte.

- **Comando:** `logoff.exe` por caminho absoluto (`[Environment]::SystemDirectory`), com só o
  número da sessão (inteiro lido do CIM); SID só por `ITC_SID`, validado por regex; sem
  `Start-Process`, `cmd /c` nem `-ExecutionPolicy` (`test_trechos_ps_sem_formas_proibidas`);
  `$env:` só `ITC_*` (`test_trechos_ps_recebem_dados_so_por_itc`). Teste real recusa SID
  inválido.
- **Sessão do Bench:** recusada pelo `SessionId` do próprio processo do trecho, que roda na
  sessão do Bench.
- **Permissão:** exige o Bench elevado; o botão segue `_ocupar` (admin, não ocupado).
- **Tela:** nomes de conta em texto puro (`_rotulo`, `QListWidgetItem`, `confirmar`).
- **Log:** "Contas: encerrar sessão <nome>: ok/erro" com código; o nome da conta já era
  permitido no log (ADR-017); sem SID nem mensagem do Windows.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** ver "Filtro"; a recusa está no serviço e no trecho.
3. **IDOR:** não se aplica (sem API).
4. **Chaves expostas:** nada novo.
5. **Inputs:** só SID validado e número de sessão; nenhum texto livre vai ao comando.
