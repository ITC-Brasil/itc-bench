# Windows Home, contas novas, Proteção do login e Energia

**Branch:** `feat/windows-home-contas` (saindo da `develop`, `8317224`; mesclada pelo PR #83 e levada à `main` pelo #84) · **Datas:** 2026-11-14 e
2026-11-16 · **ADR:** ADR-049 a ADR-054

Só `app/`; a API não muda. Oito entregas:

| Data | Entrega | ADR |
|---|---|---|
| 14/11 | Encerrar sessões no Windows Home | ADR-049 |
| 14/11 | Perfil da conta nova sem entrar nela | ADR-050 |
| 14/11 | Telas com rolagem em resolução baixa | — |
| 16/11 | Contas novas sem a animação do primeiro logon | ADR-051 |
| 16/11 | Contas novas sem a tela de privacidade, localização sim e o resto não | ADR-054 |
| 16/11 | Aba Ajuda revisada contra o código de todas as telas | — |
| 16/11 | Proteção do login: cmd e PowerShell, "Restaurar originais" e tela nova | ADR-052 |
| 16/11 | Tela Energia como a do Windows, com "Nunca" por padrão | ADR-053 |

## O que entrou

| Item | Onde |
|---|---|
| Encerrar sessões sem `logoff.exe` (não existe no Home): o trecho só acha as sessões (`SESSAO\|n`) e o logoff é por `WTSLogoffSession`, que recusa a sessão 0 e a do Bench | `recursos/contas/encerrar.ps1`, `nucleo/sessoes.py` (novo), `servicos/contas.py` (`encerrar_sessao`) |
| Perfil criado na criação da conta, sem entrar nela: `criar.ps1` escreve `SID\|`; `CreateProfile` da `userenv.dll`; falha não desfaz a conta, vira aviso | `recursos/contas/criar.ps1`, `nucleo/perfil_conta.py` (novo), `servicos/contas.py` (`criar`, `preparar_perfil`), `servicos/contas_turno.py` |
| Contas novas sem a animação do primeiro logon: `criar.ps1` grava `EnableFirstLogonAnimation` = 0 no HKLM; falha vira aviso (ADR-051) | `recursos/contas/criar.ps1` |
| Contas novas sem a tela de privacidade: `criar.ps1` grava 6 valores fixos da máquina (localização sim; diagnóstico opcional, tinta e digitação, ID de anúncio e Localizar meu dispositivo não); falha vira aviso (ADR-054) | `recursos/contas/criar.ps1` |
| Proteção do login: cmd e PowerShell na detecção (não na proteção); "Restaurar originais" restaura pelo sfc todos os trocados/ausentes; tela com resumo, cores, Proteger azul e Desproteger vermelho, botões conforme a situação e "Em caso de ataque" separado (ADR-052) | `servicos/protecao.py` (`FERRAMENTAS`, `caminho`, `restaurar_trocados`), `recursos/protecao/ler.ps1` e `escrever.ps1`, `ui/protecao.py` |
| Tela Energia como "Editar configurações do plano" do Windows: colunas Na bateria e Na tomada, "Nunca" por padrão, Aplicar só o que mudou, "Restaurar padrão do plano", hibernação num botão (ADR-053) | `ui/aparencia.py` (`PainelEnergia`) |
| Conteúdo de toda tela numa `QScrollArea` (`rolagemTela`): sem espaço, rola em vez de sobrepor controles | `ui/janela.py` (`Tela`), `ui/tema.py` (fundo transparente) |
| Ajuda revisada: textos de Início, Preparação, Identificação, Contas, Wi-Fi, Acesso remoto, USB, Políticas (alvos), Monitores, Papel de parede, Mouse e teclado, Coleta e laudo, Configurações e Atualização; a Ajuda passa a mostrar a aba Monitores e a ajuda da Atualização (junto de Configurações) | `ui/*.py` (constantes `AJUDA*`), `ui/ajuda.py` (`TEXTOS`) |
| Estilos `#proteger` (azul) e `#desproteger` (vermelho), na altura dos botões comuns | `ui/tema.py` |
| `ctypes` dos dois módulos novos na lista fechada | `tests/test_invariantes.py` |
| Testes sem tocar o sistema (`_sem_encerrar_sessao`, `_sem_criar_perfil`) | `tests/conftest.py` |
| Roteiro de máquina real 12.3, 12.5, 12.6, 12.7 e 12.8 | `docs/testes/maquina-real.md` |

## Contexto

- No Home, Contas › Encerrar sessões… falhava com "Falha do PowerShell (código 1)" porque o
  `logoff.exe` não existe nessa edição. `Add-Type` é proibido nos trechos, então a chamada à
  `wtsapi32` fica em Python, por ctypes.
- Conta criada pelo Bench não tinha perfil até o primeiro logon; Políticas, Aparência e Limpeza a
  recusavam, e o técnico entrava em cada conta nova (inclusive as por turno) só para isso.
- Em 1536x764 (VM), controles das telas se sobrepunham.
- O primeiro logon de conta nova mostrava a animação "Olá"; o responsável quer direto para a área
  de trabalho.
- A Proteção do login não olhava o cmd e o PowerShell (alvos comuns da troca), restaurava um
  arquivo por vez e misturava ações do dia a dia com as de incidente.
- A tela Energia era uma lista com caixas de marcar; o responsável quer como a do Windows, com
  "Nunca" já escolhido.

## Verificação

14/11: VM Windows 11 Home Single Language 25H2, `uv run` (não o instalador do CI).
16/11, no clone em `feat/windows-home-contas` (Windows 11 Home Single Language 25H2), sem
elevação: ruff, format e mypy limpos; `pytest` 1076 passando, 10 pulados, 1 deixado de fora
(`test_papel_de_parede::test_trecho_aparencia_recusa_valor_e_caminho_fora`, exige elevação; falha
de ambiente já conhecida). Telas novas conferidas por imagem gerada da própria tela.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| S1 | Encerrar sessão: só números conferidos; recusa sessão 0 e a do Bench | `test_contas.py` | Passa |
| S2 | Trecho de sessões na VM: `propria` para a conta do Bench, `sem_sessao` para as demais | máquina real (só leitura) | Passa |
| S3 | Encerrar sessão real aberta pela troca rápida no Home (`DESKTOP-104LH4L-jjh`, sessão 8): log "ok (1 sessão(ões))" e a sessão sumiu na conferência elevada; outras 3 contas encerradas no mesmo dia | responsável, Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| P1 | Criar conta chama `CreateProfile` com o SID; falha vira aviso sem desfazer a conta | `test_contas.py`, `test_contas_turno.py` | Passa |
| P2 | Conta "Ola" criada pelo Bench: perfil, papel de parede e políticas valeram sem entrar | máquina real, responsável, 14/11/2026 | Passa |
| P3a | Contas › Criar conta, Bench elevado: conta `TesteBench01` com perfil (`ProfileList` e `NTUSER.DAT`) sem entrar; depois excluída com o perfil | Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| P3b | Contas por turno (Identificação, sufixo): conta criada com "criado", sem aviso de perfil; pasta em `C:\Users` e entrada em `ProfileList` | responsável, Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| A1 | `criar.ps1` grava o valor depois da conta e antes do SID; falha vira aviso e a conta fica | `test_contas.py` | Passa |
| A2a | Conta criada pelo Bench elevado: `EnableFirstLogonAnimation` = 0 no HKLM | Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| A2c | Conta criada pelo Bench elevado: os 6 valores de privacidade gravados (tela fora; localização sim; o resto não) | Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| A2b | Primeiro logon de conta nova vai direto para a área de trabalho, sem animação e sem a tela de privacidade | responsável, Inspiron 5423 (Home), 16/11/2026 | Passa |
| R1 | cmd e PowerShell lidos como "original" nesta máquina (PowerShell pelo caminho dele) | leitura real, 16/11/2026 | Passa |
| R2 | Restaurar originais: só trocados/ausentes, um `sfc /scanfile` por arquivo; nada trocado, nenhum `sfc` | `test_protecao.py` | Passa |
| R3 | cmd/PowerShell fora de Proteger; mesma lista nos dois trechos | `test_protecao.py` | Passa |
| R4 | Tela: resumo, Proteger azul/Desproteger vermelho, textos dos botões, botões de ataque só com ataque | `test_aparencia_tela.py` | Passa |
| R5 | Elevado: os 9 lidos como "original"; Proteger deixa Utilman e Sethc protegidos com dono TrustedInstaller; Desproteger volta; Restaurar originais sem trocados não roda `sfc` | Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| E1 | Energia: "Nunca" por padrão, só o diferente do atual entra, dicas, botão de hibernação | `test_aparencia_tela.py` | Passa |
| E2 | Elevado: Aplicar "Nunca" nos 8 valores, conferido pela leitura do Windows; valores de antes restaurados | Bench elevado, Inspiron 5423 (Home), 16/11/2026 | Passa |
| T1 | Tela rola em vez de sobrepor em resolução baixa | `test_janela.py`; VM 1536x764 | Passa |

## Limites conhecidos

- Perfil só é criado na criação de conta; contas antigas sem perfil continuam exigindo um logon.
- A animação e a tela de privacidade do primeiro logon são desligadas para a máquina inteira (valores do HKLM), não só
  para as contas do Bench.
- cmd e PowerShell são só detectados e restaurados; não recebem a negação de execução.

## Pendências do fechamento

- Auditoria de segurança feita: `docs/security/2026-11-16-windows-home-contas.md` (nada crítico ou alto; 1 baixo corrigido, 1 baixo aceito).
- Roteiros 12.3, 12.5, 12.6, 12.7 e 12.8 passaram na máquina real em 16/11/2026.
