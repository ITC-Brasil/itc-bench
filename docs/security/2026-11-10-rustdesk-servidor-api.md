# Auditoria de segurança — Servidor da API do RustDesk — 2026-11-10

Escopo: ADR-030. `servicos/remoto.py` (`dados`, `validar_url_api_rustdesk`, `rustdesk2`,
`_conferir_rustdesk`, `_configurar_rustdesk`), `ui/remoto.py` (confirmação e ajuda). Branch
`feat/rustdesk-servidor-api`. Sem mudança na API. Feita com `docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 1 |

## Achado

### [INFORMATIVA] Valor do cadastro gravado num arquivo de configuração

A URL de `RustDesk`/`api` vem do NocoDB (pela API) e vai para o `RustDesk2.toml` da pasta do
serviço. Quem edita Servidores no NocoDB decide para onde o cliente RustDesk aponta a API, como
já decide o servidor de ID (ADR-019). Mitigação: só `https://` com host, sem credencial, query,
fragmento, espaço nem aspas; string escapada por `toml_texto` (`json.dumps`), testada com texto
hostil (`test_toml_texto_hostil_round_trip`).

## Categorias

1. **Banco sem tranca:** não se aplica (nada novo em disco do Bench).
2. **Permissão no cliente:** gravar continua exigindo o Bench elevado; `--dev` só lê.
3. **IDOR:** não se aplica (sem rota nova).
4. **Chaves expostas:** o endereço real não está no código, nos testes nem na documentação (só
   `*.exemplo.invalid`). Linha pública: não é segredo.
5. **Inputs:** validação acima; sem processo novo, sem `ITC_*` novo; a confirmação da tela usa
   o rótulo em texto puro existente (`confirmar`, `PlainText`).

## Log

Sem URL nem host, como o resto do Acesso remoto (ADR-019, item 11).
