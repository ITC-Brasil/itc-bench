# Auditoria de segurança — `feat/windows-home-contas` (ADR-049 a ADR-053)

**Data:** 2026-11-16 · **Prompt:** `docs/security/AUDIT-PROMPT.md` · **Base:** `develop` `8317224`
(diff ainda sem commit no clone `itc-bench-git`).

**Resultado:** nenhum achado crítico, alto ou médio. 1 baixo corrigido, 1 baixo aceito,
3 informativos. Não bloqueia o fechamento.

## Stack e escopo

App Windows em Python 3.13 + PySide6, rodando elevado; escrita no sistema por PowerShell (trechos
fixos de `recursos/`, dados por `$env:ITC_*`), por executáveis do System32 com argumentos fixos
(`sfc`, `powercfg`, `icacls`, `takeown`) e por ctypes de lista fechada. Sem banco próprio, sem
frontend web. A API (`api/`) não muda nesta entrega.

Arquivos revisados (diff inteiro): `nucleo/perfil_conta.py` (novo), `nucleo/sessoes.py` (novo),
`recursos/contas/criar.ps1`, `recursos/contas/encerrar.ps1`, `recursos/protecao/ler.ps1`,
`recursos/protecao/escrever.ps1`, `servicos/contas.py`, `servicos/contas_turno.py`,
`servicos/protecao.py`, `ui/protecao.py`, `ui/aparencia.py` (`PainelEnergia`), `ui/janela.py`,
`ui/tema.py` e os testes.

## 1. Banco sem tranca

Não se aplica: nada novo é gravado em `%ProgramData%\ITC\Bench` nem no cache DPAPI. O log
(`servicos/contas.py`, `preparar_perfil` e `encerrar_sessao`) leva só nome da conta, número de
sessão e código; nunca o caminho do perfil (`nucleo/perfil_conta.py` não loga e não devolve o
caminho).

## 2. Permissão definida na tela

Correto. Os botões novos (Proteger/Desproteger, atalho, Remover depurador, Restaurar originais,
Aplicar e Restaurar padrão do plano da Energia, hibernação) ficam desativados sem administrador
(`_ocupar` em `ui/protecao.py` e `ui/aparencia.py`), mas a barreira real é o Windows: sem
elevação, `sfc`, `powercfg`, `icacls`, `CreateProfile`, `WTSLogoffSession` e a escrita em HKLM
falham com acesso negado. Nenhuma ação depende só da tela.

## 3. IDOR / caminhos e alvos vindos de fora

Correto:
- `servicos/protecao.py`: `restaurar` recusa exe fora de `BINARIOS`; `restaurar_trocados` só usa
  nomes vindos da lista fechada (o JSON da leitura é conferido contra `BINARIOS` em `situacao`);
  o caminho do PowerShell vem de `CAMINHOS`, fixo. `alterar` continua recusando tudo fora de
  `PROTEGIVEIS` (cmd e PowerShell incluídos; teste `test_cmd_e_powershell_so_na_deteccao`).
- `recursos/protecao/escrever.ps1`: `remover_depurador` apaga só `Debugger`/`MonitorProcess` das
  9 chaves fixas (teste `test_trechos_fixos`).
- `nucleo/perfil_conta.py`: SID só `S-1-5-21-…` e nome nas regras de conta local antes de chamar
  `CreateProfile`; o SID vem do `criar.ps1` e é filtrado de novo em `servicos/contas.py`
  (`re.fullmatch(r"SID\|S-1-5-21-[\d-]+", …)`).
- `nucleo/sessoes.py`: recusa sessão `<= 0` (serviços) e a do próprio Bench;
  `servicos/contas.py` só aceita `SESSAO\|\d{1,5}`.
- `ui/aparencia.py` (`PainelEnergia`): o valor vem do `currentData` de uma lista fechada; o
  serviço `energia.tempos` recusa ajuste, fonte ou tempo fora da lista.

**Baixo, risco aceito — B1.** `servicos/contas.py`, `encerrar_sessao`: o trecho acha os números de
sessão e o logoff vem depois, por número. Se uma sessão terminar nesse intervalo (segundos) e o
Windows reusar o número para outra conta, a outra conta seria encerrada. Exige o técnico já
estar encerrando sessões e uma corrida estreita; o efeito é só perder trabalho aberto, sem
elevação nem acesso. Mitigação possível no futuro: conferir o SID da sessão por
`WTSQuerySessionInformation` antes do logoff. Aceito como está (ADR-049 já descreve o fluxo).

## 4. Chaves expostas

Correto. Varredura do diff e dos arquivos novos por URL, senha, token, chave e IP privado: nada
encontrado. Nenhum endereço, SSID ou credencial nos ADRs, no doc do módulo ou no roteiro.

## 5. Inputs sem tratamento (injeção e rich text)

Correto:
- Sem `shell=True` e sem interpolação: `sfc` recebe `[sfc.exe, "/scanfile=<caminho fixo>"]`;
  os trechos PowerShell não recebem dado novo (`criar.ps1` grava valor fixo em chave fixa;
  `ler.ps1` usa `$REL` fixo).
- `Add-Type` continua fora dos trechos; ctypes só nos módulos da lista fechada
  (`test_invariantes.py`).
- Texto na tela: `QLabel` de estado e mensagens em `PlainText` (`ui/protecao.py`, `_aviso` e
  `confirmar`); `_rotulo` já é `PlainText`; células da tabela são texto puro.

**Baixo, corrigido — B2.** `ui/aparencia.py`, `PainelEnergia`: as dicas "Agora: X · padrão do
plano: Y" eram `QLabel` com formato automático. O conteúdo é só número formatado pelo Bench (sem
risco hoje), mas ficou `setTextFormat(PlainText)` para não depender disso.

## Informativos

- **I1.** `criar.ps1` (ADR-051) grava `EnableFirstLogonAnimation = 0` no HKLM: vale para a
  máquina inteira e não há Desfazer. Decisão do responsável, registrada no ADR-051.
- **I2.** "Remover depurador" agora também apaga `Debugger` do IFEO do cmd e do PowerShell. Um
  depurador legítimo nesses dois é improvável numa máquina de aluno; a ação continua com dupla
  confirmação.
- **I3.** "Restaurar originais" roda `sfc /scanfile` sem limite de quantidade, mas a lista tem no
  máximo 9 arquivos fixos e cada um tem tempo limite (`TIMEOUT_SFC`, 10 min).
