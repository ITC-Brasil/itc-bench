# Nova tela Início — grade de 4 colunas, indicadores, processador e memória

**Branch:** `feat/inicio-visual` · **Data:** 2026-11-19 · **ADR:** ADR-073

Só `app/`; a API não muda. Design: canvas "ITC Bench — nova tela Início" (escuro, claro e disco
quase cheio), aprovado pelo responsável. Os valores de exemplo do design não entram no código.

## O que entrou

| Item | Onde |
|---|---|
| Tela nova: cabeçalho, Máquina, Configuração, 4 indicadores, Alertas, Último diagnóstico, Ações rápidas | `ui/inicio.py` |
| Cabeçalho próprio da tela (sem o topo e a moldura da janela); "?" abre a mesma ajuda | `ui/janela.py` (`Tela.cabecalho_proprio`) |
| Anel, barra, bateria e desenho SVG, pintados com `QPainter` | `ui/indicadores.py` |
| Cores novas `anel`, `ok_fundo`, `err_fundo` (claro e escuro) e estilos `#inicio…` | `ui/tema.py` |
| Nome do computador, processador e memória na leitura do Início | `recursos/inicio/ler.ps1`, `servicos/inicio.py` (`Maquina`, `maquina`) |
| Regras de cor e limite (disco, bateria), tipo de memória, nome curto do processador | `servicos/inicio.py` (`nivel_disco`, `nivel_bateria`, `tipo_memoria`, `cpu_curto`) |
| Ícones SVG novos e o desenho do notebook | `recursos/icones/` |
| Ajuda da tela | `ui/inicio.py` (`AJUDA`) |

## Verificação

Testes em `app/tests/test_inicio_visual.py` (59), sem tocar no Windows.

| # | Cenário | Teste | Resultado |
|---|---|---|---|
| R1 | Disco: normal, atenção a partir de 85% usado, crítico abaixo de 10% livre | `test_nivel_disco` | Passa |
| R2 | Disco crítico exatamente quando o alerta de disco aparece (mesmo limite) | `test_disco_critico_usa_o_mesmo_limite_do_alerta` | Passa |
| R3 | Bateria: carga baixa só fora da tomada; atenção abaixo de 30%, crítica abaixo de 15% | `test_nivel_bateria` | Passa |
| R4 | Nome curto do processador (Intel, AMD, Celeron, vazio) e tipo de memória SMBIOS | `test_cpu_curto`, `test_tipo_memoria` | Passa |
| D1 | Parser dos dados novos de CPU e memória | `test_parser_dos_dados_novos` | Passa |
| D2 | Valores fora da faixa viram "—"; nome com no máximo 15 caracteres | `test_parser_recusa_valores_fora_da_faixa` | Passa |
| D3 | Saída sem os campos novos continua valendo | `test_parser_sem_os_campos_novos_continua_valendo` | Passa |
| D4 | Trecho só lê (sem `Set-`, `Remove-`, `UserName`) | `test_trecho_so_le_e_sem_nome_de_usuario` | Passa |
| T1 | Tela sem leitura da máquina, nos dois modos: "—", "Não lido", "Leitura incompleta" | `test_tela_sem_leitura_da_maquina_mostra_tracos` | Passa |
| T2 | Estado vazio dos alertas, nos dois modos | `test_estado_vazio_dos_alertas` | Passa |
| T3 | Alertas com o botão da tela que resolve; disco cheio leva à Limpeza | `test_alertas_com_botao_da_tela_e_disco_cheio` | Passa |
| T4 | Indicadores com dados, configuração com andamento lido, sem administrador | `test_indicadores_com_dados`, `test_configuracao_com_andamento_lido`, `test_sem_admin_avisa_e_inventario_desativado` | Passa |
| T5 | "?" emite o sinal de ajuda; 4 colunas iguais nas três faixas | `test_botao_de_ajuda_emite_sinal`, `test_quatro_colunas_iguais` | Passa |
| W1 | Windows 10 ou 11 pelo build (22000 = 11; Home, Pro, sem build) | `test_windows_10_ou_11_pelo_build` | Passa |
| B1 | Saúde da bateria: cálculo, teto de 100%, sem uma das capacidades; níveis 80% e 50% | `test_saude_da_bateria`, `test_nivel_saude`, `test_parser_da_saude_recusa_fora_da_faixa`, `test_trecho_le_a_saude_so_do_wmi` | Passa |
| B2 | Cartão: "Saúde: 40%" crítica, "Saúde: —" sem a capacidade de fábrica, sem linha num desktop; ciclos no fim | `test_cartao_mostra_a_saude`, `test_cartao_mostra_os_ciclos`, `test_parser_dos_ciclos` | Passa |
| B3 | Trecho: `powercfg` pelo caminho do System32, XML temporário de nome aleatório apagado, sem resolver entidades; WMI de reserva | `test_trecho_le_a_saude_pelo_powercfg_e_wmi_de_reserva`, `test_trecho_so_le_e_sem_nome_de_usuario` | Passa |
| L1 | Início pede a leitura da Configuração e mostra "Lendo…"; não pede quando já leu; sem leitura, explica como ler | `test_inicio_pede_a_leitura_e_mostra_lendo`, `test_inicio_nao_pede_leitura_quando_ja_leu`, `test_inicio_sem_leitura_explica_como_ler` | Passa |
| L2 | Configuração lê sozinha uma vez, depois das contas, com o perfil da unidade e sem aplicar; não atropela quem está rodando | `test_leitura_automatica_le_uma_vez_depois_das_contas`, `test_leitura_automatica_nao_atropela_quem_esta_rodando` (em `test_preparacao_tela.py`) | Passa |

App: ruff, format e mypy limpos; `pytest` completo com 1238 passando, 10 pulados e a falha de
ambiente conhecida (`test_papel_de_parede::test_trecho_aparencia_recusa_valor_e_caminho_fora`,
passa elevado).

Leitura real nesta máquina (só leitura, sem administrador): saúde 93% e 45 ciclos, iguais ao
`powercfg /batteryreport` (38.000 e 35.260 mWh), sem arquivo sobrando no TEMP; `Core i5-1235U`, 10 núcleos, 12 threads, 8 GB DDR4,
2 slots com 1 módulo; a leitura inteira do Início levou 2,6 s.

Janela inteira em 1366x768 e 1536x864, claro e escuro, com dados falsos: 8 cartões, nenhum
sobreposto, sem rolagem horizontal, topo da janela escondido no Início. Capturas em
`.conversa/captura-janela-inicio-*.png` e `.conversa/captura-inicio-*.png` (fora do git).

Máquina real: roteiro 3.6a a 3.6c (`docs/testes/maquina-real.md`), ainda não executado.
