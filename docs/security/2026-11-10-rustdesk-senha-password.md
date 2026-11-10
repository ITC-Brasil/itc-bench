# Auditoria de segurança — Senha do RustDesk por `--password` — 2026-11-10

Escopo: ADR-031. `servicos/remoto.py` (`_configurar_rustdesk`, `_codigo_senha`,
`senha_cifrada`), `recursos/remoto/senha.ps1`. Branch `feat/rustdesk-servidor-api`. Sem mudança
na API. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 1 (risco aceito, ADR-031) |
| Informativa | 1 |

## Achados

### [BAIXA, risco aceito] Senha na linha de comando do `rustdesk.exe`

`recursos/remoto/senha.ps1`: `& $exe --password $env:ITC_SENHA`. Durante a chamada, a senha
fica na linha de comando do processo `rustdesk.exe`, legível por administrador local
(`Win32_Process`) e em auditoria 4688 com linha de comando. Condição: ser administrador da
máquina no instante da chamada, ou ter a auditoria ligada. Aceito no ADR-031: a senha é a mesma
na frota e já é reversível por administrador local (ADR-024).

### [INFORMATIVA] Melhora em relação ao ADR-019

A senha deixou de ir em texto puro para o `RustDesk.toml` (antes ficava no disco alguns
segundos, e para sempre se o processo morresse no meio). Agora não há escrita da senha pelo
Bench; teste `test_rustdesk_senha_pelo_password_e_nunca_no_disco`.

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** gravar exige o Bench elevado; `--dev` só lê.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** nenhuma senha, host ou chave real no código, nos testes ou nos docs.
5. **Inputs:** a senha não entra no texto do script (`ITC_SENHA`); o caminho do executável vem de
   `remoto.exe("RustDesk")` (pasta de instalação) e é conferido de novo no trecho
   (`Test-Path -PathType Leaf`). Sem `Start-Process`, `iex`, `cmd /c` nem `-ExecutionPolicy`
   (`test_trechos_ps_sem_formas_proibidas`). A saída do `rustdesk.exe` não é lida nem logada.

## Log

Só "`--password` falhou: <código>" e "senha não encontrada cifrada"; nunca senha, chave, host ou
ID (testes com `caplog`).
