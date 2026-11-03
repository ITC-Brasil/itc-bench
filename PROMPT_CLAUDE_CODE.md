# Prompt de inicialização — ITC Bench

Envie como primeira mensagem ao agente no início de cada módulo, trocando `NN`.

---

Você vai trabalhar no ITC Bench, app Windows instalável do Grupo ITC Brasil que junta o ITC
Configurador e o diagnóstico do pendrive do Técnico Assistente.

1. Leia `AGENTS.md` inteiro e siga a ordem de leitura que ele define.
2. Abra `docs/IMPLEMENTATION-PLAN.md` e execute o **Módulo NN**, só ele.
3. Crie a branch indicada no plano a partir de `develop` atualizada.
4. Um commit por tarefa (`tipo(escopo): descrição`, em inglês), `git add` arquivo por arquivo.
5. Antes de abrir o PR: `docs/modules/NN-nome.md` com tabela de verificação, entrada em
   `docs/PROGRESS.md`, ADRs em `docs/DECISIONS.md` e auditoria em
   `docs/security/AAAA-MM-DD-modulo-NN.md` usando `docs/security/AUDIT-PROMPT.md`.
6. Push e PR para `develop`. Não faça merge.
7. Atualize o **ESTADO ATUAL** de `docs/PROGRESS.md` antes de encerrar.

Referências do produto:

| Assunto | Arquivo |
|---|---|
| O quê e para quem | `docs/PRD.md` |
| Como (arquitetura, caminhos, execução de comandos) | `docs/TRD.md` |
| Telas e navegação | `docs/APP-FLOW.md`, `docs/UI-UX-BRIEF.md`, `docs/design/itc-bench-identidade-telas.html` |
| Dados (NocoDB via API, cache local) | `docs/BACKEND-SCHEMA.md` |
| Decisões | `docs/DECISIONS.md` |
| Código de origem (só leitura, fora do repo) | `itc-config/configurador`; `itc-config/tecnico-assistente` (descontinuado; a `api/` veio para cá, ADR-012) |

Stack e versões: a definir no Módulo 01; leia sempre do manifesto, nunca de memória.

Modo de execução: sequencial, com aprovação do responsável entre módulos (via PR).
Quando a decisão tiver consequência de produto, pare e pergunte.
