# Prompt de auditoria de segurança — ITC Bench

Roda no fechamento de cada módulo. Relatório em `docs/security/AAAA-MM-DD-modulo-NN.md`.
Achado crítico ou alto bloqueia o fechamento; risco aceito vira ADR.

## Adaptação à stack do Bench

| Categoria | No ITC Bench |
|---|---|
| 1. Banco sem tranca | Não há banco próprio. Equivalente: cache local DPAPI e arquivos em `%ProgramData%\ITC\Bench` — ACL, escopo DPAPI, se um técnico lê dados de outro. Isolamento real dos cadastros é da API (repo `tecnico-assistente`) |
| 2. Permissão no navegador | Telas que escondem ação por perfil/sessão sem checagem no backend local ou na API; ações privilegiadas sem sessão válida; login offline contornável |
| 3. IDOR | Chamadas à API com hostname/ID controlado pelo cliente (`/v1/historico/{hostname}`) — confirmar que a API valida. No app: caminhos de arquivo vindos de dados externos |
| 4. Chaves expostas | Repo, `.conversa/`, `.spec`, instalador, CI, histórico git, e o EXE gerado (strings). Só o endereço da API é permitido (ADR-008) |
| 5. Inputs sem tratamento | Não é XSS de navegador: é **injeção de comando** (PowerShell/cmd, `shell=True`, interpolação), rich text do Qt (`setHtml`, `Qt.RichText`) com dado externo, laudo da IA renderizado, UninstallString do registro, path traversal em downloads |

## Prompt (verbatim)

```
Revisa este código atrás de cinco falhas de segurança. Antes de começar, detecte a stack do projeto (linguagem, framework, ORM/query builder, mecanismo de auth, frontend, arquivos de deploy como Docker/CI/Helm/Terraform) e adapte cada categoria ao equivalente dessa stack:

1. BANCO SEM TRANCA (isolamento de inquilino/dono) — em Supabase é RLS ausente; em APIs próprias são queries de listagem/busca/agregação/relatório/exportação que não filtram pelo usuário autenticado ou pela organização/workspace/tenant ao qual ele pertence. Identifique primeiro QUAL é o mecanismo de isolamento do projeto (RLS, middleware de tenant, filtro manual por user_id, etc.) e aponte onde ele está ausente ou furado.

2. PERMISSÃO DEFINIDA NO NAVEGADOR — operações privilegiadas (admin, configurações, gestão de usuários, ações de escrita) em que o frontend esconde a UI por papel (isAdmin, canEdit, role...) mas o servidor NÃO faz a verificação equivalente. Cruze cada gate de papel do frontend com o endpoint correspondente e confirme se o backend valida o privilégio em toda rota sensível.

3. IDOR — rotas que buscam, alteram ou deletam um objeto por ID (path, query ou body) sem verificar se o objeto pertence ao usuário/tenant do chamador. Percorra sistematicamente TODOS os handlers de rota do backend, não amostras.

4. CHAVES EXPOSTAS (hardcode) — API keys, tokens, senhas, segredos de assinatura (JWT, webhooks), chaves privadas e credenciais padrão embutidos no código-fonte, configs, docker-compose, charts, CI, scripts e documentação. Atenção especial a defaults públicos que viram segredo real se não forem sobrescritos (ex: ${VAR:-valor-default}) e à ausência de validação de startup que rejeite esses defaults. Verifique também o histórico git por segredos commitados e o bundle do frontend por chaves embutidas.

5. INPUTS SEM TRATAMENTO (XSS) — no frontend: innerHTML/dangerouslySetInnerHTML/equivalentes do framework (v-html, [innerHTML], dangerouslySet...), renderização de markdown/HTML sem sanitização, URLs controladas por usuário em href/src (javascript:), eval/new Function. No backend: input do usuário entrando em HTML de e-mails, templates ou respostas sem escape. Verifique se existe lib de sanitização no projeto e se ela é aplicada nos pontos encontrados.

REGRAS DA AUDITORIA:
- Reporte apenas achados verificados no código real. Nada de especulação. Para cada achado: caminho do arquivo, número(s) exato(s) da linha, trecho do código, por que é explorável e severidade (crítica/alta/média/baixa/informativa).
- Liste arquivo por arquivo, linha por linha.
- Registre também o que foi verificado e está CORRETO (ex: "router X valida posse em todos os handlers") — isso vira a seção de pontos fortes e prova a cobertura da auditoria.
- Quando a categoria não se aplicar à stack (ex: projeto sem frontend), diga isso explicitamente em vez de forçar achados.
- Note condições de explorabilidade (feature flags, config insegura necessária, etc.).
```
