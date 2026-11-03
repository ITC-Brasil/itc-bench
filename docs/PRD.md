# PRD — ITC Bench

## Problema

O técnico de campo do Grupo ITC Brasil usa duas ferramentas separadas na bancada:

- **ITC Configurador** (`itc-config/configurador`, ~7,8 mil linhas Python, sem git): prepara o
  notebook. Tem duas UIs convivendo (CustomTkinter em `main_moderno.py` + `ui/`, PySide6 em
  `app_qt.py` + `interface_qt/`), segredos em `config/segredos.json` e senhas em claro em
  `config/config.ini` ao lado do EXE, ~40 chamadas `shell=True` com interpolação e 1,3 GB de
  instaladores na pasta. Análise: `docs/referencia/analise-configurador-2026-11-03.md`.
- **Pendrive do Técnico Assistente** (`tecnico-assistente/pendrive/`, PowerShell 5.1): coleta
  diagnóstico (`modulos/Coleta-Bateria.ps1`, `Coleta-Disco.ps1`, `Coleta-EventLog.ps1`,
  `Coleta-Processos.ps1`, `Coleta-Rede.ps1`, `Correcoes.ps1`) e envia à API (`POST /v1/relatorio`),
  que devolve o laudo da IA. Acesso por senha local com SHA-256 em `config\auth.hash`.

Wi-Fi, servidores e senhas vivem em JSON copiados à mão entre máquinas; não há registro de quem
fez cada ação.

## Usuários

| Perfil | Uso |
|---|---|
| Técnico de campo (grupo de técnicos no GLPI) | Único usuário do app. Prepara, diagnostica, libera a máquina |
| Responsável de TI | Mantém cadastros no NocoDB (base "ITC Bench"), aprova módulos |
| Aluno, professor, pedagoga, atendente | **Não** usam. O login trava o app mesmo em conta administradora (ADR-005) |

## Objetivos

1. Um app só, instalado, com login por técnico (ADR-002, ADR-005).
2. Nenhum segredo no instalador ou ao lado do EXE; cadastros centrais via API (ADR-006, ADR-008).
3. Preparação completa com retomada após reinício (antigo Master).
4. Diagnóstico com laudo e histórico dentro do app (ADR-003).
5. Ajuda contextual em toda tela (ADR-007).
6. Registro em arquivo de tudo o que o app fez, com o técnico que fez.

## Escopo funcional (7 grupos, ADR-004)

| Grupo | Telas | Origem |
|---|---|---|
| Início | Início; Preparação completa | — ; aba Master |
| Preparar | Identificação; Contas; Wi-Fi; Acesso remoto | Sistema; Usuários e Admin; Wi-Fi; Admin |
| Software | Programas; Remover programas | Apps, Winget, WebApps; Desinstalador |
| Segurança | Políticas; Proteção do login; USB | GPO; Proteção; USB |
| Aparência e periféricos | Tela e papel de parede; Mouse e teclado; Energia | Tela, Wallpaper; Mouse; Sistema |
| Diagnóstico | Coleta e laudo; Histórico; Limpeza | Pendrive; Pendrive; Limpeza |
| Sistema | Registro; Ajuda; Configurações | Logs; manual PDF; `segredos.json`, `wifi_db.json` |

Tela de entrada (Entrar) antes de qualquer menu, com bloqueio após 15 minutos parado
(`docs/design/itc-bench-identidade-telas.html`, Tela 0).

## Fora de escopo

- UI CustomTkinter do Configurador.
- Acesso direto do Bench ao GLPI ou ao NocoDB.
- TOTP (Ente Auth) — possível segundo fator só para Configurações, depois (ADR-005).
- Mudar a API do Técnico Assistente neste repo: ela fica no repo dela.

## Critérios de sucesso

- Notebook preparado do zero só com o Bench instalado e login de técnico.
- Nenhum arquivo do Bench contém senha, chave ou endereço além do endereço da API.
- Cada ação no log com data, técnico e resultado.

## Pendências

- Texto de ajuda: o manual (`Manual_Configurador_ITC.pdf`, 31/10/2026) só cobre Usuários, Tela,
  Mouse e Proteção do Login; o resto é escrito quando cada tela for migrada (ADR-007).
- GLPI 11 → 12 com HTTPS antes de as máquinas voltarem a campo (afeta só a API).
