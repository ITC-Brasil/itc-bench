# Plano de implementação — ITC Bench

Um módulo por sessão. Branch saindo de `develop`, PR para `develop`, merge pelo responsável.
**[TA]** = exige PR antes no repo `ITC-Brasil/tecnico-assistente`.

## Ajustes em relação à ordem proposta

- **Diagnóstico sobe para o 05**, antes das telas do Configurador. Motivo: só usa rotas que já
  existem na API (`POST /v1/relatorio`, `GET /v1/historico/{hostname}`) e substitui o pendrive
  inteiro, liberando o técnico de carregar duas ferramentas cedo. Aprovado pelo responsável em 03/11/2026.
- **Contas é a primeira tela migrada (06)**: `backend/contas.py` já segue o padrão seguro e o
  manual já tem a ajuda dela; valida o executor do Módulo 02 numa tela real.
- **Preparação completa vem depois das telas que ela orquestra (12)**: depende de todas as etapas.
- **Empacotamento dividido em dois (14, 15)**: instalador e CI primeiro; atualização automática
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
- [x] ACL explícito em `%ProgramData%\ITC\Bench` na execução elevada (SYSTEM e `S-1-5-32-544` total, Usuários leitura), antes do cache do 04 (achado médio da auditoria do 01)

### 03 — Login e sessão · `feat/modulo-03-login` · **[TA]**
- [ ] [TA] Rotas de login na API, integração GLPI isolada em um arquivo, grupo de técnicos, limite de tentativas; ADR lá
- [ ] Tela Entrar, sessão, bloqueio por 15 min parado
- [ ] Login offline 7 dias com hash DPAPI; escopo DPAPI decidido em ADR
- [ ] Técnico registrado em cada linha do log

### 04 — Cadastros via API com cache DPAPI · `feat/modulo-04-cadastros` · **[TA]**
- [ ] [TA] Rotas dos 4 cadastros; ADR que revisa o ADR-005 de lá
- [ ] Cliente e cache cifrado; indicação "sincronizado HH:MM"; modo offline
- [ ] Tela Configurações (leitura; edição continua no NocoDB)

### 05 — Diagnóstico · `feat/modulo-05-diagnostico`
- [ ] Decidir em ADR: chamar os `.ps1` do pendrive ou portar para Python
- [ ] Coleta e laudo, Histórico; envio à API existente
- [ ] Token da carreta (`itcta_`) guardado com DPAPI em escopo de máquina, em `%ProgramData%\ITC\Bench`; nunca no repositório nem no instalador (ADR-008)
- [ ] Definir e documentar como o token chega à máquina (hoje é gravado no pendrive)
- Se o login do técnico tornar o token da carreta desnecessário, isso é ADR novo e **[TA]**, fora do escopo do 05.

### 06 — Contas · `feat/modulo-06-contas`
- [ ] Migrar `backend/contas.py` + `aba_usuarios.py`/`aba_admin.py`; SID `S-1-5-32-544`; fim do `wmic`
- [ ] Ajuda da tela a partir do manual

### 07 — Identificação e Wi-Fi · `feat/modulo-07-identificacao-wifi`
- [ ] `sistema.py` (renomear PC sem interpolação), `wifi.py` com dados do cache; ajuda escrita

### 08 — Acesso remoto · `feat/modulo-08-acesso-remoto`
- [ ] GLPI Agent, RustDesk, AnyDesk com dados de Servidores; senha AnyDesk sem `echo`; polling no lugar de `sleep(10)`; comparação de versão numérica

### 09 — Programas e Remover programas · `feat/modulo-09-programas`
- [ ] Apps + Winget + WebApps em lista única; download sob demanda com SHA-256; desinstalador sem shell

### 10 — Políticas e USB · `feat/modulo-10-politicas-usb`
- [ ] GPO: local e ACL do `.bat` de logon (achado 4 da análise); USB

### 11 — Proteção do login e Aparência · `feat/modulo-11-protecao-aparencia`
- [ ] Proteção, Tela e papel de parede, Mouse e teclado, Energia (ajudas do manual)

### 12 — Preparação completa, Início e Limpeza · `feat/modulo-12-preparacao`
- [ ] Perfis, etapas, retomada após reinício; tela Início; Limpeza; Registro; Ajuda consolidada

### 13 — Revisão de segurança e testes de ponta a ponta · `chore/modulo-13-revisao`
- [ ] Máquina limpa preparada do zero; auditoria completa

### 14 — Empacotamento, instalador e CI · `ci/modulo-14-instalador`
- [ ] `.spec` do PyInstaller, `.ico` multi-tamanho, Inno Setup x WiX decidido em ADR, endereço da API no instalador, CI

### 15 — Atualização automática · `feat/modulo-15-atualizacao` · **[TA]**
- [ ] [TA] Rota de versão disponível; download assinado/conferido; "atualizar ao fechar"
