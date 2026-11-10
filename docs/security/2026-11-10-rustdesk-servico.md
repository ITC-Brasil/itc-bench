# Auditoria de segurança — Serviço do RustDesk 1.5.1 — 2026-11-10

Escopo: ADR-032. `servicos/remoto.py` (`_subir_rustdesk`, Instalar e Reconfigurar do RustDesk),
`recursos/remoto/servico.ps1` (`Start-Service` com erro vira aviso). Branch
`feat/rustdesk-servidor-api`. Sem mudança na API. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 2 |

## Achados

### [INFORMATIVA] Processo novo: `rustdesk.exe --install-service`

Roda pelo executor com lista de argumentos fixa, sem dado do cadastro nem `ITC_*`, e o caminho
do `rustdesk.exe` vem de `remoto.exe("RustDesk")` (pasta instalada, a mesma já usada pelo
`--get-id` e pelo `--option`). O serviço criado roda como LocalSystem, como o RustDesk sempre
faz; o Bench não escolhe conta nem caminho do serviço (alternativa `sc.exe create` recusada no
ADR-032).

### [INFORMATIVA] `Start-Service` com erro não interrompe o trecho

`servico.ps1`: o erro do `Start-Service` vira `AVISO|iniciar` e a decisão fica com a espera
pelo estado `Running`. Não esconde falha: sem `Running` no tempo, o trecho sai com
`ERRO|tempo` e o Bench mostra "não respondeu a tempo". A mensagem do Windows não vai ao log.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** criar o serviço exige o Bench elevado; `--dev` só lê.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** nada novo; nenhum host, senha ou chave em código, testes ou docs.
5. **Inputs:** nenhum dado externo nos argumentos novos; trechos PS sem formas proibidas
   (`test_trechos_ps_sem_formas_proibidas`).

## Log

"`--install-service` código N", "serviço não subiu (ação); parando e iniciando": só códigos.
