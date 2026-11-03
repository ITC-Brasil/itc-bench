# Arquitetura — Técnico Assistente

## Visão geral

O técnico roda a ferramenta PowerShell do pendrive (`pendrive/menu.ps1`), que coleta
dados da máquina de forma determinística e grava um JSON por módulo em
`pendrive/sessoes/<AAAA-MM-DD_HHmm_HOSTNAME>/`. Na Fase 2, o pendrive envia esses
JSONs à API central no glpi-srv, que monta o prompt, chama o OpenCode Go e devolve o
relatório; sem API, o pendrive usa o relatório determinístico da Fase 1.

```
Pendrive (PowerShell 5.1, TLS 1.2)
   │  HTTPS + service token Cloudflare Access + token da carreta
   ▼
Cloudflare (borda) ── <túnel cloudflared> ──► glpi-srv: container tecnico-api (127.0.0.1)
                                          ├──► OpenCode Go (chave só aqui)
                                          ├──► SQLite (fonte da verdade)
                                          ├──► NocoDB (espelho, só de ida)
                                          └──► ntfy (alertas)
```

Estado em 2026-09-28: `pendrive/` (Fase 1) pronto. A API tem o núcleo do Módulo 01, os
tokens do Módulo 02, o relatório com IA do Módulo 03 (`POST /v1/relatorio`,
`GET /v1/historico/{hostname}`), o espelho e os alertas do 04 e o pipeline do 05. O
pendrive envia o diagnóstico completo à API desde o Módulo 07 (contrato 1.2). O deploy
no glpi-srv (Módulo 06) é passo do responsável.

## Stack

| Camada | Tecnologia | Estado |
|---|---|---|
| Cliente | Windows PowerShell 5.1 (sem módulos externos) | Fase 1 e cliente da API (Módulo 07) |
| API | Python 3.12 + FastAPI + Uvicorn | Implementado (Módulos 01 a 03) |
| Banco | SQLite em volume nomeado | Tokens (Módulo 02), diagnósticos e relatórios (Módulo 03) |
| IA | OpenCode Go, `mimo-v2.6-flash` | Implementado (Módulo 03), sem teste com a chave real |
| Espelho e alertas | NocoDB, ntfy | Implementado (Módulo 04), sem teste contra os serviços reais |
| CI/CD | GitHub Actions | Implementado (Módulo 05); deploy real no Módulo 06 |

Versões exatas são registradas em `documentacao-tecnico-assistente.md` §2 quando cada
dependência for instalada.

## Decisões estruturais

- A IA nunca roda no notebook (TA-ADR-002) e nunca decide nem executa ações (TA-ADR-016).
- O pendrive não escreve fora de si mesmo: todos os caminhos partem de `$PSScriptRoot`
  (TA-ADR-013).
- Correções só por funções de parâmetro fixo, com confirmação `SIM` digitada
  (`Confirm-Acao` em `pendrive/lib/Util-Interface.ps1`, TA-ADR-014).
- O hostname é a chave de identificação em sessões, histórico e relatórios (TA-ADR-015).
- `pendrive/lib/Util-Relatorio.ps1` (`Write-RelatorioSessao`) é o único ponto que
  transforma JSON em texto; a Fase 2 substitui só esse arquivo.
- O prompt é montado no servidor (TA-ADR-006); o SQLite é a fonte da verdade e o NocoDB é
  espelho só de ida (TA-ADR-005).
- Duas camadas de autenticação: Cloudflare Access na borda e token por carreta na API
  (TA-ADR-007).
- Sem frontend nesta fase (TA-ADR-008).

## Restrições de infraestrutura

Estas restrições não são limites operacionais: elas moldaram decisões de arquitetura.

| Restrição | Origem | Consequência arquitetural |
|---|---|---|
| 8 GB RAM, ~2 GB livres em uso | Frota | IA fora do notebook (TA-ADR-002) |
| ~100 s por requisição | Cloudflare Tunnel | Timeout de 60 s no Go (TA-ADR-010) |
| Docker contorna UFW | iptables no glpi-srv | Porta em 127.0.0.1 (TA-ADR-009) |
| Sem branch protection em privado | GitHub Free | Proteção via CI (TA-ADR-012) |
| Deploy keys SSH bloqueadas | GitHub Free (org) | Servidor clona via Fine-grained PAT |
| PowerShell 5.1 nas máquinas | Frota | Cliente força TLS 1.2 antes de chamar a API |

## Fluxo de dados

**Fase 1 (implementado):** `IniciarDiagnostico.bat` → `menu.ps1` → senha
(`config/auth.hash`, SHA-256) → projeto e sub-perfil (`config/perfis.json`) →
`New-Sessao` cria a pasta → cada coletor roda isolado em `Invoke-Coletor`
(`pendrive/lib/Util-Sessao.ps1`) e grava `<modulo>.json` → `Save-Sessao` regrava
`sessao.json` a cada módulo → `Write-RelatorioSessao` imprime o relatório na tela.

**Fase 2 (API no Módulo 03, cliente no 07):** no `[1] Diagnóstico completo`,
`Invoke-RelatorioApi` (`pendrive/lib/Util-Relatorio.ps1`) força TLS 1.2, testa
`/v1/saude` e envia `sessao.json` e os JSONs de módulo para `POST /v1/relatorio`; a API limita o corpo, valida o token e o limite por
hora, valida o schema, normaliza a sessão para o contrato atual
(`api/app/normalizacao.py`), lê o histórico do hostname, grava o diagnóstico, monta o
prompt (`api/app/prompt.py`), chama o Go fora de transação, grava o relatório (ou a
falha) e responde. Depois da resposta, uma thread espelha o relatório no NocoDB e, em
falha da IA ou token revogado, alerta no ntfy (Módulo 04, TA-ADR-024). Qualquer resposta diferente de
`200` leva o pendrive ao relatório determinístico.

## Infra local

- Pendrive: `powershell -NoProfile -ExecutionPolicy Bypass -File pendrive\Testar-Ferramenta.ps1 -SemPausa`
  (sai com código 0 quando tudo passa).
- API: pytest dentro de `python:3.12.14-slim-trixie` e `docker compose` a partir de `api/`.
  Os comandos exatos estão no `CLAUDE.md`.
