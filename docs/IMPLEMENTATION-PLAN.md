# Plano de implementação — ITC Bench

Um módulo por sessão. Branch saindo de `develop`, PR para `develop`, merge pelo responsável.
Numeração revista pelo ADR-012: o 03 novo é a migração da API, e os seguintes subiram +1.

## Ajustes em relação à ordem proposta

- **Diagnóstico sobe para o 06**, antes das telas do Configurador. Motivo: só usa rotas que já
  existem na API (`POST /v1/relatorio`, `GET /v1/historico/{hostname}`) e substitui o pendrive
  inteiro, liberando o técnico de carregar duas ferramentas cedo. Aprovado pelo responsável em 03/11/2026.
- **Contas é a primeira tela migrada (07)**: `backend/contas.py` já segue o padrão seguro e o
  manual já tem a ajuda dela; valida o executor do Módulo 02 numa tela real.
- **Preparação completa vem depois das telas que ela orquestra (13)**: depende de todas as etapas.
- **Empacotamento dividido em dois (15, 16)**: instalador e CI primeiro; atualização automática
  depois, porque precisa de rota de versão na API.

## Módulos

### 00 — Kickoff da documentação · `docs/modulo-00-kickoff`
- [x] `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `PROMPT_CLAUDE_CODE.md`
- [x] PRD, TRD, APP-FLOW, UI-UX-BRIEF, BACKEND-SCHEMA, este plano
- [x] DECISIONS (ADR-001 a ADR-008), PROGRESS, AUDIT-PROMPT, auditoria baseline

### 01 — Esqueleto do app · `feat/modulo-01-esqueleto`
- [x] Manifesto com versões fixadas (Python, PySide6), ambiente, lint e testes escolhidos
- [x] Estrutura de pastas; ponto de entrada com elevação UAC e modo `--dev`
- [x] Caminhos `ProgramData` / `LOCALAPPDATA` sem efeito colateral no import
- [x] Log rotativo em `%ProgramData%\ITC\Bench\logs`
- [x] Tema (tokens de `docs/UI-UX-BRIEF.md`), fontes embutidas, ícones extraídos
- [x] Barra lateral com os 7 grupos e telas vazias com "?"; `__version__` central
- Sem funcionalidades.

### 02 — Execução segura de comandos · `feat/modulo-02-executor`
- [x] Executor único: lista de argumentos, dados por ambiente, timeout, código de saída, log
- [x] Testes com entradas hostis (aspas, `&`, `|`, `;`, quebra de linha)
- [x] Proibir `shell=True` por lint/teste
- [x] ACL explícito em `%ProgramData%\ITC\Bench` na execução elevada (SYSTEM e `S-1-5-32-544` total, Usuários leitura), antes do cache do 05 (achado médio da auditoria do 01)

### 03 — Migração da API para o monorepo · `chore/modulo-03-monorepo`
- [x] ADR-012 (substitui o ADR-003), com a tabela de renumeração
- [x] Programa Windows em `app/`; comandos, `.gitattributes` e ferramentas ajustados
- [x] `api/` importada com histórico (filter-repo + replace-text, fonte `0bc5620`); varredura de segredos
- [x] Workflows por parte com `paths`; gitleaks; `dependabot.yml`; deploy só manual, environment `producao`, `DEPLOY_DIR`
- [x] `docs/api/` (API, TOKENS, SCHEMA, DEPLOY, TA-ADRs); regras da API no `AGENTS.md`
- [x] Transição no servidor e no TA, em `docs/api/DEPLOY.md`: desligar `push` no TA, backup, deploy key, troca do remote, primeiro deploy, relatório de teste
- [x] Depois do deploy validado: `push` em `api/**` de volta no `api-deploy.yml`
- [ ] Pasta de deploy no servidor renomeada para `itc-bench` (`mv`, `DEPLOY_DIR`, novo deploy; compose, volume e container mantêm os nomes); depois, README do TA apontando para cá (arquivamento do TA é do responsável)

### 04 — Login e sessão · `feat/modulo-04-login`
- [x] Rotas de login em `api/`, integração GLPI isolada em um arquivo, perfil de técnicos (não grupo), limite de tentativas; ADR-013
- [x] Tela Entrar, sessão, bloqueio por 15 min parado
- [x] Login offline 7 dias com hash DPAPI; escopo DPAPI decidido em ADR (máquina, ADR-013)
- [x] Técnico registrado em cada linha do log
- [ ] Depois do merge (responsável): deploy da API, `.env`, Bypass e rate limiting na Cloudflare, `curl`, login real, teste com conta comum

### 05 — Cadastros via API com cache DPAPI · `feat/modulo-05-cadastros`
- [x] Rotas dos 4 cadastros em `api/`; ADR que revisa o TA-ADR-005 (nota do ADR-006)
- [x] Cliente e cache cifrado; indicação "sincronizado HH:MM"; modo offline
- [x] Tela Configurações (leitura; edição continua no NocoDB)
- [ ] Depois do merge (responsável): `Publico` em Servidores, usuários Viewer e Editor no NocoDB, base separada do espelho, deploy, `.env`, cadastros reais na bancada, conta comum sem leitura de `cadastros.dpapi`

### 06 — Diagnóstico · `feat/modulo-06-diagnostico`
- [x] Decidir em ADR: chamar os `.ps1` do pendrive ou portar para Python. O pendrive não veio para o monorepo: a referência é `pendrive/` no repo `ITC-Brasil/tecnico-assistente` arquivado (até `0bc5620`), incluindo `pendrive/SCHEMA.md` (cópia em `docs/api/SCHEMA.md`)
- [x] Coleta e laudo, Histórico; envio pela sessão do técnico em `/v1/bench/` (ADR-016)
- [ ] Depois do merge (responsável): backup do SQLite, deploy (`0006`), `curl` das rotas novas, coleta real com laudo pela borda, fila e reenvio na bancada
- ~~Token da carreta (`itcta_`) guardado com DPAPI em escopo de máquina~~ — não se aplica: envio pela sessão do técnico (ADR-016)
- ~~Definir e documentar como o token chega à máquina~~ — não se aplica (ADR-016)
- O login do técnico tornou o token da carreta desnecessário nos notebooks: trazido para o 06 por decisão do responsável (ADR-016, ADR-015 e TA-ADR-028). O `itcta_` continua só nas carretas.

### 07 — Contas · `feat/modulo-07-contas`
- [x] Migrar `backend/contas.py` + `aba_usuarios.py`/`aba_admin.py`; SID `S-1-5-32-544`; fim do `wmic` (ADR-017)
- [x] Ajuda da tela a partir do manual
- [x] Conta Suporte por Servidores (`Conta Suporte`/`usuario` e `senha`); ações em lote para o 13
- [ ] Depois do merge (responsável): linhas `Conta Suporte` no NocoDB, troca da senha Suporte, cenários V1–V8 em máquina real, com o instalador

### 08 — Identificação e Wi-Fi · `feat/modulo-08-identificacao-wifi`
- [x] `sistema.py` (renomear PC sem interpolação), `wifi.py` com dados do cache; ajuda escrita
- [ ] Cenários V1–V8 em máquina real, com o instalador (`docs/modules/08-identificacao-wifi.md`)

### 09 — Acesso remoto · `feat/modulo-09-acesso-remoto`
- [x] GLPI Agent, RustDesk, AnyDesk com dados de Servidores; senha AnyDesk sem `echo`; polling no lugar de `sleep(10)`; comparação de versão numérica

### 10 — Programas e Remover programas · `feat/modulo-10-programas`
- [x] Apps + Winget + WebApps em lista única; download sob demanda com SHA-256; desinstalador sem shell

### 11 — Políticas e USB · `feat/modulo-11-politicas-usb`
- [x] GPO: local e ACL do `.bat` de logon (achado 4 da análise); USB — sem script de logon, sobras do Configurador removíveis; USB = bloqueio de armazenamento removível (ADR-021)

### 12 — Proteção do login e Aparência · `feat/modulo-12-protecao-aparencia`
- [ ] Proteção, Tela e papel de parede, Mouse e teclado, Energia (ajudas do manual)

### 13 — Preparação completa, Início e Limpeza · `feat/modulo-13-preparacao`
- [ ] Perfis, etapas, retomada após reinício; tela Início; Limpeza; Registro; Ajuda consolidada

### 14 — Revisão de segurança e testes de ponta a ponta · `chore/modulo-14-revisao`
- [ ] Máquina limpa preparada do zero; auditoria completa

### 15 — Empacotamento, instalador e CI · `ci/modulo-15-instalador`
- [ ] `.spec` do PyInstaller, `.ico` multi-tamanho, Inno Setup x WiX decidido em ADR, endereço da API no instalador, CI

### 16 — Atualização automática · `feat/modulo-16-atualizacao`
- [ ] Rota de versão disponível em `api/`; download assinado/conferido; "atualizar ao fechar"
