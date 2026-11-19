# Auditoria de segurança — `feat/preparacao-contas-rodar` (ADR-071)

**Data:** 2026-11-19 · **Prompt:** `docs/security/AUDIT-PROMPT.md` · **Base:** `develop` `f4450ca`
(diff ainda sem commit no clone `itc-bench-git`).

**Resultado:** nenhum achado crítico, alto, médio ou baixo. 3 informativos. Não bloqueia o
fechamento.

## Stack e escopo

App Windows em Python 3.13 + PySide6, rodando elevado; escrita no sistema por trechos
PowerShell fixos (`recursos/`, dados por `$env:ITC_*`) e por `WTSLogoffSession` (ctypes). Sem
banco próprio e sem frontend web. A API não muda.

Arquivos revisados (diff inteiro): `ui/preparacao.py`, `ui/contas.py` (`pedir_encerrar`),
`servicos/etapas.py` (`contas_locais`, `MOTIVO_CONTA`), `servicos/contas.py` (`Conta.bench`,
`encerrar_sessoes`), `recursos/contas/listar.ps1` (campo `bench`) e os testes.

## 1. Banco sem tranca

Não se aplica: nada novo é gravado em `%ProgramData%\ITC\Bench` nem no cache DPAPI. A retomada
(`retomada.gravar`) continua com os mesmos campos.

## 2. Permissão definida na tela

Correto.
- **Rodar sem leitura** não pula conferência: `prep.rodar` chama `_ler` de cada etapa antes de
  `aplicar` e pula as feitas, bloqueadas e com falha de leitura, como antes. A leitura prévia
  era só da tela.
- **Rodar e Encerrar sessões…** ficam desativados sem administrador (`_ocupar`), mas a barreira
  real é o Windows: sem elevação, os trechos e o `WTSLogoffSession` falham com acesso negado.
- **Conta bloqueada** fica sem SID no item da lista (`_carregar_alunos`), então `alvos()` nunca
  a devolve, mesmo que a tela fosse manipulada. As etapas conferem de novo: Políticas, USB,
  papel de parede e mouse por `hive.recusa_alvo` e pelo trecho; a Limpeza de usuários por
  `limpeza.limpar_contas` (recusas do ADR-042) e pelo trecho.
- `contas_de_aluno` agora é o filtro de `contas_locais`; o resultado é o mesmo
  (`test_contas_locais_com_motivo_e_mesmas_regras` compara os dois) e o teste antigo
  `test_contas_de_aluno_fechadas` continua passando.

## 3. IDOR / alvos vindos de fora

Correto.
- O campo `bench` vem de `[Security.Principal.WindowsIdentity]::GetCurrent()` no trecho de
  listagem, sem entrada externa; serve só para o texto do motivo, não para decidir alvo.
- Encerrar sessões usa o mesmo caminho da tela Contas: `contas.encerrar_sessao` relê a conta
  pelo SID, o trecho só acha as sessões e recusa a do Bench, e `nucleo/sessoes.encerrar` recusa
  a sessão 0 e a do Bench (ADR-036, ADR-049). Os SIDs vêm da lista lida do Windows, marcados
  no diálogo.

## 4. Chaves expostas

Correto. Nenhum segredo, endereço ou SSID no diff, nos testes (SIDs e nomes fictícios) ou na
documentação.

## 5. Inputs sem tratamento

Correto. Nomes de conta e motivos entram em `QListWidgetItem`, no `QPlainTextEdit` do registro
da tela e em `confirmar`/`txt.aviso` (texto simples); nada em rich text. Nenhum dado vai para
comando: os trechos recebem SIDs por variável de ambiente, como antes.

## Informativos

- **I1.** A confirmação passa a listar os nomes das contas marcadas. É texto da tela, não do
  log; o log da Preparação continua sem nome de conta.
- **I2.** `contas.encerrar_sessao` já gravava o nome da conta no log ("Contas: encerrar sessão
  …"), como na tela Contas (ADR-036). Agora o mesmo log aparece a partir da Configuração e da
  Manutenção; nada novo.
- **I3.** Rodar sem leitura confia na conferência do motor. Uma etapa cuja `ler()` falhe vira
  "falhou" e não aplica (`prep.rodar`), então não há aplicação às cegas.

## Adendo — ADR-072

`etapas.escondida` só tira da lista Suporte, Gestão e o Administrador nativo, que já eram
recusados como alvo; nenhuma conta passa a ser alvo. A conta do Bench e a logada continuam
bloqueadas. O bump para 0.20.0 só muda `__version__` e o README. Sem achado novo.

## Verificação

App: `test_preparacao_tela.py` (16 novos) e os testes de contas, preparação e manutenção que
já existiam.
