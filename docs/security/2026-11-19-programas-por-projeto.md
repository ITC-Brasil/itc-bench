# Auditoria de segurança — `feat/programas-por-projeto` (ADR-074, TA-ADR-042)

**Data:** 2026-11-19 · **Prompt:** `docs/security/AUDIT-PROMPT.md` · **Base:** `develop` `82b5d90`
(diff ainda sem commit).

**Resultado:** nenhum achado crítico, alto, médio ou baixo. 2 informativos. Não bloqueia o
fechamento.

## Stack e escopo

API FastAPI (leitura do NocoDB) e app Windows (PySide6). Arquivos revisados (diff inteiro):
`api/app/services/nocodb_cadastros.py`, `app/src/itc_bench/servicos/cadastros.py`,
`servicos/programas.py`, `servicos/etapas.py`, `ui/programas.py`, `ui/janela.py`, os testes e
a documentação.

## 1. Banco sem tranca

Não se aplica: nada novo no SQLite da API nem no `%ProgramData%\ITC\Bench`. O cache DPAPI
ganha a lista `perfis` de cada instalador (códigos de perfil, sem segredo).

## 2. Permissão definida na tela

Correto. O filtro por projeto e perfil só escolhe **quais** programas aparecem e quais a etapa
6 instala; a instalação continua pelo mesmo `programas.instalar`, com o mesmo SHA-256, a mesma
exigência de administrador e as mesmas recusas. O botão "Todos os projetos" não libera nada que
a tela não mostrava antes (antes, tudo aparecia).

## 3. IDOR / dados vindos de fora

Correto. `projeto` e `perfis` vêm do cadastro pela API autenticada; a API só aceita sigla de
Projeto ativo e código de perfil válido (`CODIGO_PERFIL`, já usado nos Perfis), e descarta o
resto. No app, os valores só entram em comparação e em texto de tela.

## 4. Chaves expostas

Correto. Nenhum segredo, endereço ou SSID no diff; os testes usam valores fictícios
(`exemplo.invalid`, `Ex.Abc`).

## 5. Inputs sem tratamento

Correto. A coluna Para entra em `QTableWidgetItem` (texto simples); nada em rich text nem em
comando. Os códigos de perfil não vão para o PowerShell.

## Informativos

- **I1.** Uma linha de programa com `Projeto` de sigla errada, que antes valia para todos, agora
  é descartada e aparece no aviso de linhas ignoradas (TA-ADR-042). É o comportamento mais
  seguro; conferir o NocoDB depois de publicar.
- **I2.** O Bench 0.20.0 ignora `projeto` e `perfis` nos programas: até a versão nova, as
  máquinas continuam vendo todos os programas, como hoje.

## Verificação

App: `test_programas_projeto.py` (13) e os 222 testes da área. API: 291 no container.
