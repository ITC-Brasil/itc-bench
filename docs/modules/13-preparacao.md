# Módulo 13 — Preparação completa, Início, Limpeza, Registro e Ajuda

**Branch:** `feat/modulo-13-preparacao` · **Data:** 2026-11-06 · **ADR:** ADR-023

Só `app/`; a API não muda. O desenho foi proposto e aprovado em `.conversa/` (Etapa 1).

**Respostas do responsável:**
- perfis no código: `sala_de_aula`, `administrativo`, `so_diagnostico`, pré-selecionados por
  `Unidades.PerfilPadrao`;
- contas por turno fora (opção B registrada como futuro);
- Limpeza de manutenção, sem "zerar aluno";
- pré-instalados Appx entram;
- retomada assistida, sem Run/RunOnce, tarefa ou serviço; 2 reinícios; 24 h;
- Exportar do Registro com máscara.

**Ajustes incorporados:**
- Appx em trecho próprio: todas as contas e provisionado, lista fechada, recusa de sistema,
  `NonRemovable` e framework;
- etapa Contas: aviso de que a conta em uso perde administrador; "feito" inclui RID 500
  desativado;
- "contas de aluno" fechada no código;
- Acesso remoto "feito" pelas linhas completas do cadastro;
- Limpeza da preparação sem a lixeira;
- Windows Update: reinício pendente ou serviço que não para = "não limpo", sem mudar o tipo de
  inicialização;
- logs do Bench fora da Limpeza;
- `preparacao.json` com dono e ACL conferidos e ids validados;
- temporários por usuário com perfil e `AppData\Local\Temp` sem reparse e saída só numérica.

## O que entrou

| Item | Onde |
|---|---|
| Perfis e parâmetros fechados | `servicos/perfis.py` |
| Motor (ler, rodar, pausar, dependência, falha parcial) | `servicos/preparacao.py` |
| As 14 etapas, só chamando os serviços de 07 a 12 | `servicos/etapas.py` |
| Remover pré-instalados (Appx) | `servicos/desinstalar.py` (`APPX_PREINSTALADOS`, `appx_*`, `remover_appx`), `recursos/programas/appx.ps1` |
| Retomada assistida | `servicos/retomada.py` |
| Limpeza com prévia | `servicos/limpeza.py`, `recursos/limpeza/limpeza.ps1` |
| Início: máquina e alertas | `servicos/inicio.py`, `recursos/inicio/ler.ps1` |
| Registro: leitura, filtro e exportação mascarada | `servicos/registro.py` |
| Ajuda consolidada | `ui/ajuda.py` |
| Telas e selos | `ui/{inicio,preparacao,limpeza,registro}.py`, `ui/janela.py` |

## Decisões de implementação

- **Administrador nativo.** O ADR-017 proíbe o Bench de alterar o RID 500. A etapa Contas só
  fica "feita" com ele desativado; se estiver ativo, a etapa falha com a mensagem "desative-o
  pelo Windows" e não mexe nele.
- **Início sem ler as 14 etapas.** Ler tudo leva minutos (winget, hives fechados). O Início lê
  máquina, proteção, políticas da máquina do perfil, nome pendente, Suporte, cadastros e fila, e
  mostra a última leitura da Preparação feita na sessão. USB por conta não entra no alerta (exige
  carregar hives).
- **Diagnóstico na preparação** coleta e põe na fila; o envio segue pelo reenvio da fila depois
  da preparação (ADR-015), sem esperar o laudo.
- **Programas na preparação:** só `Categoria = Programas`, sem os `.exe` interativos (pediriam
  clique no meio do lote).
- **Políticas na preparação:** usuário (`cmd`, `regedit`, `painel`, `programas`, `temas`,
  `ponteiros`, `powershell`) em Contas futuras e contas de aluno; máquina (`compartilhamento`,
  `wifidirect`, `ics`). Store fica fora (efeito só em Enterprise/Education).
- **Mouse e teclado na preparação:** só o atalho Shift 5x desligado. **Energia:** tela 15/10 min,
  suspensão nunca/30 min (tomada/bateria).
- **Leitura que falha** vira `falhou` com o nome da exceção; aplicação que falha também. Nenhuma
  mensagem do Windows vai ao log (a do traceback poderia ter caminho de perfil).
- **Limpeza:** a cadeia perfil → `AppData` → `Local` → `Temp` é conferida duas vezes (ao montar as
  raízes e logo antes de varrer).
- **Selos:** texto no próprio botão do menu (`Preparação completa  6/12`, `Início  ⛔ 2`).

## Verificação

App: 691 testes passando e 4 pulados; ruff e mypy limpos. API sem mudança.

A máquina de desenvolvimento (Windows 11 Pro em português) foi usada só para leitura, sem
administrador:
- `inicio.maquina()`: modelo, série, `EditionID = Professional`, build, disco e bateria lidos;
- `limpeza.previa()` dos 5 itens: números lidos, nenhum código de erro;
- `itc-bench --teste`: abre, loga e fecha com 0.

A única escrita foi numa pasta temporária do pytest (junction criada e apagada).

| # | Cenário | Como | Resultado |
|---|---|---|---|
| S1 | Perfis só com etapas e parâmetros dos catálogos | `test_perfis_usam_so_etapas_e_parametros_fechados` | Passa |
| S2 | `PerfilPadrao` desconhecido cai em Sala de aula com aviso | `test_perfil_do_cadastro` | Passa |
| S3 | Etapa feita é pulada; rodar de novo não refaz | `test_etapa_feita_e_pulada_sem_aplicar`, `test_rodar_de_novo_nao_refaz` | Passa |
| S4 | Falha numa etapa: segue, bloqueia dependentes, log sem a mensagem | `test_falha_segue_e_bloqueia_dependentes` | Passa |
| S5 | Pausar depois da etapa corrente | `test_pausar_para_depois_da_etapa_corrente` | Passa |
| S6 | Reinício marca o andamento | `test_reinicio_marca_andamento` | Passa |
| S7 | Contas de aluno fechadas | `test_contas_de_aluno_fechadas` | Passa |
| S8 | Appx: lista só Microsoft; fora da lista recusado sem chamar o trecho; recusa do trecho | `test_appx_*` | Passa |
| S9 | Limpeza: item fora da lista recusado; só números | `test_limpeza_*`, `test_trecho_limpeza_raizes_fixas` | Passa |
| S10 | Varredura não segue junction (prévia e limpar), arquivo fora intacto | `test_varredura_nao_segue_junction` | Passa |
| S11 | Retomada: grava e lê; vencido, ACL errada, inválido e link apagados; ids filtrados; limite de 2 | `tests/test_retomada.py` | Passa (link pulado sem privilégio) |
| S12 | Início: alertas com tela; sem texto localizado | `test_alertas_*`, `test_maquina_sem_texto_localizado` | Passa |
| S13 | Registro: rotacionados em ordem, filtro, exportar sem dado novo | `test_ler_*`, `test_filtrar_*`, `test_exportar_*` | Passa |
| S14 | Ajuda: todas as telas na ordem do menu; busca sem acento | `test_ajuda_*` | Passa |
| S15 | `--dev` sem admin: Preparação e Limpeza só leem | `test_preparacao_sem_admin_so_le`, `test_limpeza_sem_admin_nao_limpa` | Passa |
| S16 | Nenhum `shell=True`, `cmd /c`, `.bat` ou `-ExecutionPolicy` no `src/` | grep + `test_sem_shell.py` | Só os nomes das sobras do Configurador (`politicas.py`) |
| V1 | Perfil completo do zero | máquina real | Pendente (máquina real, com o instalador) |
| V2 | Mesmo perfil de novo (nada refeito) | máquina real | Pendente (máquina real, com o instalador) |
| V3 | Falha numa etapa e continuação | máquina real | Pendente (máquina real, com o instalador) |
| V4 | Pausar e cancelar | máquina real | Pendente (máquina real, com o instalador) |
| V5 | Reinício e retomada: com e sem rede, sessão vencida, offline | máquina real | Pendente (máquina real, com o instalador) |
| V6 | Limpeza com prévia e sem seguir junction | máquina real | Pendente (máquina real, com o instalador) |
| V7 | Início com alertas (utilman desprotegido, política faltando) | máquina real | Pendente (máquina real, com o instalador) |
| V8 | Registro e Exportar sem dado sensível | máquina real | Pendente (máquina real, com o instalador) |
| V9 | Ajuda com busca | máquina real | Pendente (máquina real, com o instalador) |
| V10 | Windows Home e Pro; Windows em inglês | máquina real | Pendente (máquina real, com o instalador) |
| V11 | `--dev` sem admin | máquina real | Pendente (máquina real, com o instalador) |

## Passos do responsável

- Preencher `Unidades.PerfilPadrao` com o id do perfil (`sala_de_aula`, `administrativo` ou
  `so_diagnostico`). Vazio = Sala de aula.
- Sem `.env`, deploy ou mudança no NocoDB além disso.

## Roteiro do teste em máquina real (V1–V11)

Notebook reserva, Windows recém-instalado, contas `Teste01` e `Teste02` (padrão), Bench pelo
instalador, cadastros sincronizados com a unidade de teste.

1. **V1.** Abra o Bench, entre, vá a Preparação completa. Confira o perfil da unidade. Digite um
   nome de teste, marque `Teste01` e `Teste02`. Ler situação: cada etapa feita/pendente/bloqueada
   com motivo. Rodar: a confirmação lista o que muda (Contas avisa a conta em uso). Ao fim, o
   selo mostra o número de feitas.
2. **V2.** Ler situação de novo e Rodar: só Limpeza e Diagnóstico (que rodam uma vez por
   preparação) ficam pendentes se for uma sessão nova; nada mais é refeito (veja o Registro).
3. **V3.** Tire a linha de Wi-Fi da unidade do cadastro: Wi-Fi fica bloqueada e o resto segue.
   Apague a conta Suporte do cadastro: Contas bloqueia e Políticas/USB/papel/mouse ficam
   bloqueadas por dependência.
4. **V4.** Comece a rodar e clique Pausar durante Programas: para depois de Programas. Rodar de
   novo continua.
5. **V5.** Rode com nome novo: Identificação fica "aguardando reinício". Reiniciar agora; volte,
   entre (online; depois repita offline com o cabo fora; e com a sessão vencida, esperando 12 h
   ou revogando no servidor). Escolha Continuar: o nome aparece feito e o resto segue. Confira que
   `protegido\preparacao.json` some ao terminar e que um terceiro reinício é recusado. Descarte e
   confira que o arquivo some. Mude o dono do arquivo com `icacls` e abra: o Bench apaga e
   registra.
6. **V6.** Crie em `C:\Users\Teste01\AppData\Local\Temp` uma junction para uma pasta com um
   arquivo de teste. Calcular e Limpar: a junction some, o arquivo de destino fica. Com
   atualização esperando reinício, o Windows Update fica "não limpo"; confira que `wuauserv`
   e `bits` voltam ao estado anterior e o tipo de inicialização não muda.
7. **V7.** Desproteja o utilman pela tela Proteção: o Início mostra o alerta crítico, o selo
   conta 1, o botão leva à Proteção. Desfaça uma política da máquina do perfil: idem com
   Políticas.
8. **V8.** Registro: filtros por nível e texto. Exportar: o arquivo não tem nome do computador,
   nomes das contas nem `C:\Users\…`.
9. **V9.** Ajuda: busque "junção" e "reinicio"; "Ver toda a ajuda" no ? de uma tela leva à seção.
10. **V10.** Repita V1 num Windows Home e num Windows em inglês: nada depende de texto do
    Windows; Políticas avisa as edições sem efeito confirmado.
11. **V11.** `itc-bench --dev`: telas abrem, só leitura, botões de ação desabilitados.

## Limites conhecidos

- O Administrador nativo ativo deixa a etapa Contas em "falhou" até o técnico desativá-lo pelo
  Windows (ADR-017).
- Limpeza e Diagnóstico não têm leitura de "já feito": rodam uma vez por preparação na sessão.
- O Início não alerta USB por conta (ler exige carregar os hives).
- A varredura da Limpeza confere a cadeia de pastas logo antes de varrer; uma troca por junction
  no intervalo de milissegundos entre a conferência e a abertura da pasta não é coberta.
- Contas por turno ficam para um módulo futuro (ADR-023, item 4).
