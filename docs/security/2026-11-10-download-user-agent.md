# Auditoria de segurança — Download com User-Agent próprio e código HTTP — 2026-11-10

Escopo: `servicos/instaladores.py` (`AGENTE`, `_abrir`, tratamento de `HTTPError` em `obter`).
Branch `feat/rustdesk-servidor-api`. Sem mudança na API. Feita com
`docs/security/AUDIT-PROMPT.md`.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 1 |

## Achado

### [INFORMATIVA] O User-Agent revela o produto e a versão

Todo download de Instaladores manda `ITC-Bench/<versão>`. O servidor do download (fabricante
do programa) passa a saber que é o Bench e qual versão. Não é segredo (a versão está no EXE e
na API) e não identifica a máquina nem o técnico. Motivo: o download do AnyDesk dava 403 ao
User-Agent padrão do urllib (máquina real, 10/11/2026).

## Conferido

- O esquema continua só `https://`, conferido em `validar()` e de novo em `_abrir`; o
  redirecionamento segue só para `https://` (`_SoHttps`) e leva o mesmo cabeçalho (teste
  `test_download_com_user_agent_proprio`).
- O código HTTP vai à tela e ao log; o `Link` e o host continuam fora do log (teste
  `test_download_http_erro_mostra_o_codigo`).
- Teto de 300 MB, hash calculado no download e conferido antes de executar: sem mudança
  (ADR-019, ADR-028).

## Categorias

1. **Banco sem tranca:** não se aplica.
2. **Permissão no cliente:** não muda.
3. **IDOR:** não se aplica.
4. **Chaves expostas:** o cabeçalho não leva token, sessão nem dado da máquina.
5. **Inputs:** o `Link` vem do cadastro, como antes; nada novo é interpretado.
