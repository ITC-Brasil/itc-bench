# Módulo 10 — Programas e Remover programas

**Branch:** `feat/modulo-10-programas` · **Data:** 2026-11-06 · **ADR:** ADR-020, TA-ADR-029

O módulo muda `app/` e `api/` no mesmo PR (ADR-012): a tabela Instaladores ganhou seis colunas e
a API passou a validar por `Tipo`. O desenho foi proposto e aprovado em `.conversa/` (Etapa 1).

Respostas do responsável:
- a lista de pré-instalados a remover fica para o perfil do 13;
- o Web App tem modo por linha (`Modo`: `quiosque` ou `app`);
- drivers e runtimes ficam bloqueados;
- `Deteccao` não é obrigatória (MSI pelo `ProductCode`, EXE pelo nome).

Ajustes incorporados:
- linhas do 09 fora de Programas, e `do_cadastro` só com `Tipo = instalador`;
- winget com `--scope machine`;
- `%ProgramData%` fora dos locais aceitos para desinstalador, com caminho final resolvido;
- ACL explícita na pasta de ícones e limpeza dela;
- nomes reservados e atalho alheio no `.lnk`;
- timeout sem matar o instalador;
- separação da `UninstallString` só quando volta ao mesmo texto.

## O que entrou

| Item | Onde |
|---|---|
| Colunas `Tipo`, `Categoria`, `Identificador`, `Argumentos`, `Deteccao`, `Modo` e validação por tipo | `api/app/services/nocodb_cadastros.py` |
| Versão numérica compartilhada | `app/src/itc_bench/nucleo/versao.py` (o 09 passou a usar) |
| Campos novos no cadastro (cache antigo continua legível) e `do_cadastro` só com instaladores | `servicos/cadastros.py`, `servicos/instaladores.py` |
| Executor com `encerrar_no_timeout=False` (instalador segue rodando, sem pipe) | `servicos/executor.py` |
| Lista, validação, detecção, winget, Web Apps e lote | `servicos/programas.py`, `recursos/programas/winget.ps1`, `atalho.ps1` |
| Lista de instalados, separação da `UninstallString`, recusas, protegidos, Windows Terminal | `servicos/desinstalar.py`, `recursos/programas/terminal.ps1` |
| Telas Programas e Remover programas com ajuda | `ui/programas.py`, `ui/janela.py` |
| Testes | `api/tests/test_cadastros.py`, `app/tests/test_programas.py`, `test_desinstalar.py`, `test_programas_tela.py`, `test_executor.py`, `test_instaladores.py`, `test_cadastros.py` |

## Decisões de implementação

- **Ordem do lote:** instaladores, winget, atalhos web. Um item que falha não para os outros.
  Item que passa do tempo fica "ainda em execução"; os instaladores, winget e desinstalações
  seguintes ficam "não iniciado", e os atalhos web e o Terminal seguem.
- **Timeout sem matar.** No modo `encerrar_no_timeout=False` o processo roda fora de Job Object e
  com saída em `DEVNULL`: fechar um pipe fazia o filho morrer escrevendo nele (achado no teste
  real com `ping`). Não combina com `cancelar` (o executor recusa).
- **winget.** `winget.exe` pelo `InstallLocation` do `Microsoft.DesktopAppInstaller`, só dentro de
  `Program Files\WindowsApps` ou `%WINDIR%\SystemApps`, com `Get-AuthenticodeSignature` `Valid` e
  assinante `O=Microsoft Corporation`. Situação pelo `winget export --include-versions` em pasta
  temporária (lista de pacotes, sem segredo; funciona sem admin). Códigos conferidos no
  `returnCodes.md` oficial do winget-cli; "sem instalador de máquina" é `0x8A150010`.
- **Web App.** O `.lnk` aponta direto para o `msedge.exe` de App Paths (dentro de Program Files);
  os argumentos saem de `Modo`, juntados por espaço (URL validada sem espaço nem aspas).
- **Separação da `UninstallString`.** Aceita se `list2cmdline` dos argumentos for igual ao texto
  original. Única folga: sem aspas no texto, espaços repetidos entre argumentos contam como um
  (o argv não muda). NSIS `/S /D=C:\Program Files\X` passa (o programa recebe a mesma linha);
  aspas que sumiriam (`"arg"`, `/X="a b"`) são recusadas. Recusa por local é conferida antes da
  existência do arquivo.
- **Locais por origem** (revisão do PR): entrada de HKU só roda de Program Files; entrada de HKLM
  aceita `%WINDIR%` fora de uma lista fechada de subpastas graváveis por Usuários (ADR-020).
- **Detecção MSI** só quando o `.msi` está guardado e conferido; antes do primeiro download, vale
  o nome.
- **Ajuda.** O manual do Configurador só lista as abas Winget, Softwares & Jogos, Web Apps e
  Desinstalador, sem capítulo de uso; a ajuda foi escrita para o comportamento novo.

## Verificação

API: 241 testes no container oficial. App: 539 testes passando e 4 pulados; ruff e mypy limpos;
`itc-bench --teste --dev` com código 0.

A máquina de desenvolvimento (Windows 11 em português) foi usada só para leitura:
- 165 entradas de `Uninstall` lidas, 29 de perfis carregados;
- `winget.exe` localizado pelo pacote, assinatura válida da Microsoft;
- `winget export` com código 0;
- Edge achado em App Paths;
- Desktop Público listado;
- lista de remoção montada: 33 silenciosos, 24 interativos, 34 recusados (25 por local, 9 por
  separação), 17 protegidos e o Windows Terminal.

Nada foi instalado, removido nem criado nela; os nomes dos programas não foram gravados.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| A1 | API: tipos, categoria, modo, ID do winget, URL do Web App; vazios com padrão; log sem valor | `test_instaladores_por_tipo` | Inválidos em `descartados`; padrões certos; URL fora do log |
| C1 | Cache antigo sem os campos novos | `test_instalador_de_cache_antigo_vira_tipo_instalador` | Vira `instalador`/`Programas`/`quiosque` |
| C2 | winget/Web App com o mesmo nome de um instalador do 09 | `test_do_cadastro_ignora_winget_e_webapp_com_o_mesmo_nome` | O 09 só vê instaladores |
| C3 | Lista: Acesso remoto fora, duplicados e ID inválido bloqueados | `test_listar_tira_acesso_remoto_e_marca_duplicados` | Passa |
| P1 | Argumentos um por linha; `&`, aspas, `\`, espaço, `%` recusados; MSI só `PROPRIEDADE=valor` | `test_argumentos_um_por_linha_e_validados` | Passa |
| P2 | Instalador do zero (MSI) com lista fixa e sem matar no timeout; `Link` fora do log | `test_msi_monta_lista_sem_matar_no_timeout` | Passa |
| P3 | Já instalado na mesma versão, mais velha, mais nova, ilegível, ambíguo; `Deteccao`; MSI pelo `ProductCode` | `test_detectar_por_prefixo` (7 casos), `test_deteccao_substitui_o_programa`, `test_msi_pelo_product_code` | Passa |
| P4 | `msiexec` 3010, 1641, 1618, 1603; EXE 0, 3010, outro | `test_codigos_do_msiexec`, `test_exe_com_argumentos_e_codigos` | Passa |
| P5 | SHA-256 errado antes de executar | `test_sha_errado_antes_de_executar` | Nenhum processo aberto |
| P6 | Sem rede sem arquivo guardado / com arquivo escolhido | `test_sem_rede_e_sem_arquivo`, `test_arquivo_escolhido_sem_rede` | "Escolher arquivo…" / instala da cópia |
| P7 | Lote com um item falhando | `test_um_falha_os_outros_seguem` | Os outros seguem |
| P8 | Timeout no meio do lote | `test_timeout_pula_instaladores_e_winget_mas_segue_webapp`, `test_timeout_sem_encerrar_deixa_o_processo_rodando` | Processo continua; seguintes não iniciados; Web App segue |
| P9 | Cancelar no meio | `test_cancelar_entre_itens` | O item atual termina; o resto fica "cancelado" |
| W1 | winget: comando fixo, sem `--force`, `--scope machine` | `test_comando_winget_fixo` | Passa |
| W2 | winget ausente, fora da pasta de pacotes, assinatura errada | `test_winget_confere_pasta_e_assinatura`, `test_winget_ausente_falha_so_os_itens_winget` | Só os itens winget falham |
| W3 | ID inexistente, sem escopo de máquina, sem rede, reinício, código desconhecido | `test_codigos_do_winget` (6 casos) | Mensagem própria; desconhecido com o hex |
| W4 | `export` em JSON, arquivo apagado | `test_winget_export_le_json_e_apaga` | Passa |
| B1 | Web App: atalho por `ITC_*`, argumentos do modo, URL fora do log | `test_webapp_cria_atalho_por_variaveis`, `test_url_e_modo_do_webapp` | Passa |
| B2 | Ícone com SHA-256 e ACL da pasta | `test_webapp_com_icone_baixa_com_hash_e_protege_pasta`, `test_icone_do_webapp_exige_hash_e_ico` | Passa |
| B3 | Atalho alheio com o mesmo nome; nomes reservados; sem Edge | `test_webapp_nao_sobrescreve_atalho_alheio`, `test_nome_atalho` (7 casos), `test_webapp_sem_edge` | Recusa com motivo |
| B4 | Limpeza de instaladores e ícones | `test_limpar_sem_base_trata_instaladores_e_icones` | Passa |
| D1 | `UninstallString`: aspas, espaços, sem aspas com espaço no caminho, NSIS `/D=`, argumentos com `/`, espaços repetidos | `test_separar_aceita` (6 casos) | Separa e volta ao mesmo texto |
| D2 | Aspas internas, aspas que somem, aspa sem fechar, colado na aspa, prefixo inexistente | `test_separar_recusa` (6 casos) | Recusa |
| D3 | MSI por `ProductCode` (`MsiExec.exe /I{…}` ignorado); `msiexec` sem ser MSI | `test_msi_pelo_product_code_ignora_a_uninstall_string`, `test_msiexec_sem_ser_msi_e_recusado` | `/x {GUID} /qn /norestart` / recusa |
| D4 | `QuietUninstallString` preferida; interativo como queda | `test_quiet_preferida_e_interativo_como_queda` | Passa |
| D5 | `cmd`, `rundll32`, `%ProgramData%`, perfil, não `.exe`; caminho final resolvido; `REG_EXPAND_SZ` | `test_recusas` (5 casos), `test_caminho_final_resolvido`, `test_expand_sz_com_program_files` | Passa |
| D6 | Protegidos (Bench, acesso remoto, runtime, driver) | `test_protegidos` (6 casos), `test_protegido_e_recusado_nao_executam` | Sem seleção, nada executado |
| D7 | Lote de remoção: códigos, 1605, 1618, timeout, cancelar, log sem caminho | `test_lote_codigos_e_log_sem_comando`, `test_msi_1605_e_1618`, `test_timeout_pula_programas_mas_segue_atalho_e_terminal`, `test_cancelar_entre_itens` | Passa |
| D8 | Windows Terminal por trecho fixo (todos os usuários e provisionado) | `test_terminal_por_script_fixo` | Passa |
| D9 | Locais por origem: HKU em Program Files (aceito), em System32 e `Windows\Temp` (recusado); HKLM em `Windows\Temp` e no spool (recusado), em `%WINDIR%` legítimo e System32 (aceito); HKU MSI por `ProductCode` (aceito); junção para subpasta gravável | `test_locais_por_origem` (7 casos), `test_hku_msi_por_product_code_aceito`, `test_subpasta_gravavel_pelo_caminho_final` | Passa |
| T1 | Telas: abas, busca, bloqueados, contagem, `--dev` só leitura, confirmação com modo e origem, protegido travado | `test_programas_tela.py` (5 testes) | Passa |
| M1 | Nenhum `shell=True`, `cmd /c` ou `subprocess` fora do executor no `src/` | `test_sem_shell.py`, busca no `src/` | Passa (só o `list2cmdline` da elevação, de antes) |
| M2 | Leitura real nesta máquina: registro, winget, `export`, Edge, atalhos, lista de remoção | Script de leitura (só contagens) | Passa |
| V1 | Instalador MSI e EXE do zero; mesma versão; versão mais velha | Roteiro, passo 2 | **Pendente (máquina real, com o instalador)** |
| V2 | SHA-256 errado; sem rede com e sem arquivo guardado | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V3 | winget presente; ID inexistente; pacote só de usuário (escopo de máquina); winget ausente (Windows sem App Installer) | Roteiro, passo 4 | **Pendente (máquina real, com o instalador)** |
| V4 | Web App criado, ícone, quiosque e app; atalho alheio com o mesmo nome | Roteiro, passo 5 | **Pendente (máquina real, com o instalador)** |
| V5 | Lote com um item falhando; cancelar no meio | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |
| V6 | Desinstalar MSI, EXE com `QuietUninstallString`, EXE só interativo; comando recusado; protegido | Roteiro, passo 7 | **Pendente (máquina real, com o instalador)** |
| V11 | Entrada de HKU criada por usuário comum apontando para `%WINDIR%` | Roteiro, passo 7 | **Pendente (máquina real, com o instalador)** |
| V7 | Windows Terminal removido e não volta em conta nova | Roteiro, passo 8 | **Pendente (máquina real, com o instalador)** |
| V8 | Windows em inglês | Roteiro, passo 9 | **Pendente (máquina real, com o instalador)** |
| V9 | `--dev` sem admin | Roteiro, passo 1 | **Pendente (máquina real, com o instalador)** |
| V10 | Log sem `Link`, URL, caminho de perfil nem nome de usuário | Roteiro, passo 10 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

1. Criar em Instaladores (NocoDB, base "ITC Bench") as seis colunas: `Tipo`, `Categoria`, `Modo`
   (SingleSelect com os valores do `BACKEND-SCHEMA.md`), `Identificador`, `Deteccao`
   (SingleLineText) e `Argumentos` (LongText).
2. Deploy da API (`api-deploy.yml`) **antes** do app novo.
3. Cadastrar as linhas: instaladores com `SHA256` do arquivo oficial e `Link` `https://`, os IDs
   do winget que estavam no Configurador e os Web Apps e jogos (URL `https://`, ícone opcional).
   `Programa` do instalador com o nome de "Aplicativos instalados".
4. Rodar V1–V11 num notebook reserva (roteiro abaixo).

Sem `.env` novo.

## Roteiro do teste em máquina real (V1–V11)

1. Abra o Bench sem administrador (`--dev`): Programas e Remover programas mostram a lista e nada
   fica habilitado (V9). Depois abra com administrador, entre e sincronize.
2. **Instaladores:** instale um MSI e um EXE com argumentos silenciosos, do zero. A situação passa
   a "instalado" com a versão. Clique de novo: continua "instalado". Num notebook com versão mais
   velha, aparece "desatualizado" e instala por cima. Um `.exe` sem argumentos abre a janela do
   fabricante (avisado na confirmação) (V1).
3. Num cadastro **de teste**: troque um caractere do `SHA256`, sincronize e instale (recusa "não
   confere"). Desconecte a rede: com o arquivo já guardado, instala; sem ele, use "Escolher
   arquivo…" com o instalador num pendrive (V2). Desfaça.
4. **winget:** instale um pacote; confira em "Aplicativos instalados" que é para todos os
   usuários. Cadastre um ID inexistente (mensagem "não existe") e um pacote só de usuário
   (mensagem "escopo de máquina"). Num Windows sem App Installer, os itens winget aparecem
   bloqueados com o motivo e os outros instalam (V3).
5. **Web Apps:** crie um em quiosque e um em app. Os atalhos aparecem na área de trabalho de
   outra conta, com o ícone do cadastro; quiosque abre em tela cheia (sai com Alt+F4). Crie à mão
   um atalho com o mesmo nome e tente de novo: recusa sem sobrescrever (V4).
6. Monte um lote com um item de cadastro errado no meio: ele falha e os outros instalam. Num
   lote longo, clique em "Cancelar depois deste passo" durante um instalador: ele termina e o
   resto fica "cancelado" (V5).
7. **Remover:** desinstale um MSI (silencioso), um EXE com `QuietUninstallString` e um só
   interativo (siga a janela). Um programa instalado no perfil do usuário aparece "recusado"; um
   driver aparece com cadeado (V6). Numa conta comum, crie em
   `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Teste` um `DisplayName` e uma
   `UninstallString` apontando para `%WINDIR%\System32\`, e outra entrada apontando para
   `%WINDIR%\Temp\`. Com o perfil carregado, as duas aparecem "recusado" no Bench e nada roda
   (V11). Apague a chave.
8. Remova o Windows Terminal; crie uma conta nova, entre nela e confira que ele não está lá (V7).
9. Se houver máquina em inglês, repita 2, 4 e 7 (V8).
10. No `bench.log`, procure o `Link` de um instalador, a URL de um Web App, `C:\Users\` e o nome
    do usuário: nenhum aparece (V10).

## Limites conhecidos

- winget sem SHA-256 do Bench (risco aceito no ADR-020): vale a conferência do winget contra o
  manifesto.
- Programas instalados só para um usuário cujo perfil não está carregado não aparecem.
- Sem limpeza de resíduos; entradas órfãs aparecem como "desinstalador ausente".
- Instalador que passa do tempo continua rodando; o técnico confere depois.
- A situação de um `.exe` depende de `Programa` (ou `Deteccao`) casar com o nome no Windows.
- A lista de pré-instalados a remover e o seletor de perfil ficam para o 13.
