# Módulo 09 — Acesso remoto

**Branch:** `feat/modulo-09-acesso-remoto` · **Data:** 2026-11-05 · **ADR:** ADR-019

Este módulo mexe só em `app/`; a API não muda (Servidores, Instaladores e Unidades já chegam
pela rota de cadastros, ADR-014). O desenho foi proposto e aprovado em `.conversa/` (Etapa 1).

Respostas do responsável:
- a tag do GLPI é opcional;
- a chave do RustDesk é segredo (não forte);
- "Escolher arquivo…" entra;
- AnyDesk sem ícone na área de trabalho;
- `http://` no GLPI é aceito por enquanto;
- versão mais nova não é rebaixada.

Ajustes incorporados: versão pela primeira sequência numérica (`ad 8.0.14`), códigos 3010, 1641
e 1618 do `msiexec`, limpeza contra todas as linhas de Instaladores, `RustDesk2.toml` que
preserva as outras opções, senha do RustDesk fora de qualquer arquivo na falha e hash sobre a
cópia do arquivo escolhido.

## O que entrou

| Item | Onde |
|---|---|
| Instaladores do cadastro: validação, download `https` com SHA-256, cópia de arquivo escolhido, conferência antes de executar, limpeza | `app/src/itc_bench/servicos/instaladores.py` |
| Dados de Servidores, versão numérica, TOML do RustDesk, situação, instalar, reconfigurar, forçar inventário | `app/src/itc_bench/servicos/remoto.py` |
| Trechos PowerShell: estado dos serviços; parar/iniciar/esperar com polling | `app/src/itc_bench/recursos/remoto/*.ps1` |
| Tela Acesso remoto com ajuda (cartão por programa, confirmação, registro ao vivo, cancelar) | `app/src/itc_bench/ui/remoto.py`, `ui/janela.py` |
| Testes | `app/tests/test_instaladores.py`, `test_remoto.py`, `test_remoto_tela.py` |

## Decisões de implementação

- **Instalador pelo hash.** O arquivo fica em `protegido\instaladores\<sha256>.<ext>`. Um arquivo
  já guardado só é reaproveitado se o hash bater; adulterado, é baixado de novo. Antes de
  executar, `remoto.instalar` confere o hash outra vez.
- **Sem rede.** O download falha com "use Escolher arquivo…". O arquivo escolhido é lido para
  `.parcial` em `protegido\` e o hash é calculado sobre essa cópia.
- **Ordem do RustDesk.**
  1. MSI.
  2. Espera do serviço e do `RustDesk.toml` (o ID já foi gerado). **ADR-032:** se o serviço não
     existir, `rustdesk.exe --install-service`; se não subir no tempo, parar e iniciar uma vez.
  3. Parar o serviço e encerrar só os `rustdesk.exe` da pasta instalada.
  4. Gravar o `RustDesk2.toml` (mesclado).
  5. Iniciar o serviço (mesma regra do passo 2).
  6. **Senha (ADR-031):** `recursos/remoto/senha.ps1` chama `rustdesk.exe --password` com a
     senha em `ITC_SENHA`. O Bench não grava mais a senha no `RustDesk.toml`.
  7. Esperar até 20 s que a senha apareça cifrada (`00…` nas versões antigas, `01…` no 1.5.1).
  8. `--option stop-service-hide-tray Y` e `--option hide-icon Y`.

  Se o `--password` falhar ou a senha cifrada não aparecer, o Bench falha com mensagem. Se o
  RustDesk gravasse o texto puro, o Bench tira a linha antes de falhar.
  *Até 10/11/2026 (ADR-019, item 8) a senha ia em texto puro no `RustDesk.toml`; o RustDesk
  1.5.1 deixou de aceitar e o caminho mudou pelo ADR-031.*
- **Método de verificação do RustDesk.** O Configurador não gravava esse método; fica o padrão do
  RustDesk.
- **Cancelar.** O botão vira "Cancelando depois deste passo…". O `msiexec` e o `--install` não
  recebem `cancelar`; o download, a cópia e as esperas recebem.
- **Escolher arquivo** fica desabilitado quando a ação é "Reconfigurar" (versão igual ou mais
  nova): não reinstala por cima.
- **AnyDesk.** O `InstallLocation` vem entre aspas no registro, e o Bench tira as aspas. Isso
  apareceu na leitura real desta máquina e virou correção com teste.

## Verificação

App: testes completos (ver `PROGRESS.md`), ruff e mypy limpos e `itc-bench --teste --dev` com
código 0.

A máquina de desenvolvimento (Windows 11, sem elevação nesta sessão, com GLPI Agent, RustDesk e
AnyDesk já instalados) foi usada só para leitura:
- serviços lidos pelo PowerShell real;
- versões lidas pela chave `Uninstall`: `1.19`, `1.5.1` e `ad 9.6.7`;
- ID do RustDesk e do AnyDesk lido por `--get-id` (valor não registrado).

Nada foi instalado nem reconfigurado nela.

| # | Cenário | Como | Resultado |
|---|---|---|---|
| S1 | Linha de Servidores ausente, vazia, duplicada, com `Publico` trocado ou com formato errado | `test_dados_recusa` (8 casos), `test_chave_invalida_e_sem_instalador` | Recusa só aquele programa e diz o par que falta |
| S2 | Tag: preenchida, sem unidade, vazia, com aspas | `test_dados_completos`, `test_tag_opcional_sem_unidade_ou_vazia`, `test_glpi_sem_tag_nao_passa_tag` | `TAG=` só quando preenchida; aspas recusadas |
| S3 | GLPI em `http://` | `test_glpi_http_aceito_com_aviso` | Aceito, com aviso |
| I1 | Linha de Instaladores inválida (SHA, extensão, `http`, sem versão), ausente, duplicada | `test_validar_recusa`, `test_do_cadastro_*` | Recusa e diz o que falta |
| I2 | Download conferido, nome pelo hash, sem `.parcial`, `Link` fora do log | `test_obter_baixa_confere_e_nomeia_pelo_hash` | Passa |
| I3 | Guardado com hash certo / adulterado | `test_obter_reaproveita_guardado_sem_baixar`, `test_obter_rebaixa_guardado_adulterado` | Reaproveita / baixa de novo |
| I4 | SHA-256 errado (download e arquivo escolhido) | `test_sha_errado_apaga_e_recusa`, `test_copiar_arquivo_errado_recusa` | Arquivo apagado; recusa; log com 12 caracteres |
| I5 | SHA-256 errado logo antes de executar | `test_sha_errado_antes_de_executar` | Nenhum processo aberto |
| I6 | Sem rede | `test_sem_rede_sugere_escolher_arquivo` | "use Escolher arquivo…" |
| I7 | Cancelar no download; teto de 300 MB; redirecionamento para `http` | `test_cancelar_no_meio_nao_deixa_arquivo`, `test_teto_de_tamanho`, `test_redirecionamento_para_http_recusado` | Nada fica no disco; recusas |
| I8 | Limpeza contra todas as linhas ativas; sem cadastros | `test_limpar_*` | Só o que não é de nenhuma linha (e `.parcial`); sem cadastros, nada |
| R1 | Versão numérica: `ad 8.0.14`, `1.10.0` contra `1.4.5`, igual, ilegível | `test_versao`, `test_comparar` | Igual, mais nova, mais velha certas |
| R2 | `msiexec` 0, 3010, 1641 / 1618, 1603, outro | `test_glpi_msiexec_codigos_de_sucesso`, `test_msiexec_falhas` | Sucesso (com reinício pendente) / mensagem própria |
| R3 | `RustDesk2.toml` preserva outras opções; texto hostil escapado | `test_rustdesk2_preserva_outras_opcoes_e_escapa`, `test_toml_texto_hostil_round_trip` | `tomllib` relê igual |
| R4 | Linha `password` troca só ela; preserva `id`, `salt` e `[options]` | `test_com_senha_troca_so_a_linha_e_preserva_id` | Passa |
| R5 | RustDesk instala, configura, senha cifrada; senha e chave fora de argumento e do log; sem `.tmp` | `test_rustdesk_instala_configura_e_senha_some` | Passa |
| R6 | RustDesk não cifra a senha | `test_rustdesk_senha_nao_cifrada_e_retirada` | Falha com mensagem; nenhum arquivo da pasta tem a senha |
| R7 | `.tmp` com a senha quando o `replace` falha | `test_gravar_atomico_nao_deixa_tmp` | Pasta vazia |
| R8 | AnyDesk: senha pela entrada padrão, sem ícone na área de trabalho, fora do log | `test_anydesk_senha_pela_entrada_nunca_em_argumento` | Passa |
| R9 | Cancelar antes de começar; serviço que não sobe | `test_cancelar_antes_de_comecar`, `test_servico_que_nao_sobe` | Nada executado / "não respondeu a tempo" |
| R10 | Reconfigurar GLPI com tag vazia | `test_reconfigurar_glpi_tag_vazia_nao_apaga` | Tag gravada continua |
| R11 | Forçar inventário | `test_forcar_inventario` | `GET` em `127.0.0.1:62354/now`; falha vira mensagem |
| R12 | Leitura real: serviços, versões, `InstallLocation` sem aspas | `test_leitura_real_dos_servicos` | Passa nesta máquina |
| T1 | Tela: Instalar, Atualizar, Reconfigurar, ID, "atualize o cadastro" | `test_rotulos_por_versao` | Passa |
| T2 | `--dev` sem admin; cadastro incompleto | `test_sem_admin_so_le_e_falta_desabilita` | Nada habilitado; "Falta: …" |
| T3 | Confirmação com servidor, tag, SHA-256 e comando, sem segredo | `test_confirmacao_sem_segredo`, `test_comando_sem_segredo` | Passa |
| M1 | Nenhum `shell=True`, `echo` com segredo ou `subprocess` fora do executor no `src/` | `test_sem_shell.py`, busca no `src/` | Passa |
| V1 | GLPI Agent do zero; servidor e tag no registro; "Forçar inventário" chega ao GLPI | Roteiro, passo 2 | **Pendente (máquina real, com o instalador)** |
| V2 | RustDesk do zero; ID na tela; conexão com a senha permanente do cadastro | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V3 | AnyDesk do zero; ID na tela; acesso sem supervisão com a senha | Roteiro, passo 4 | **Pendente (máquina real, com o instalador)** |
| V4 | Já instalado na mesma versão (Reconfigurar) e versão mais velha (Atualizar) | Roteiro, passo 5 | **Pendente (máquina real, com o instalador)** |
| V5 | SHA-256 errado no cadastro; sem rede com "Escolher arquivo…" | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |
| V6 | Linha de Servidores ausente ou vazia | Roteiro, passo 6 | **Pendente (máquina real, com o instalador)** |
| V7 | Cancelar no meio (durante o download e durante o MSI) | Roteiro, passo 7 | **Pendente (máquina real, com o instalador)** |
| V8 | Serviço que demora a subir (máquina lenta, primeiro boot) | Roteiro, passo 3 | **Pendente (máquina real, com o instalador)** |
| V9 | Windows em inglês | Máquina em inglês, se houver | **Pendente (máquina real, com o instalador)** |
| V10 | Senhas fora do `bench.log`, de `Win32_Process`, de `%TEMP%`, de `protegido\` e da pasta do serviço do RustDesk (`RustDesk.toml` só com `00…`, sem `.tmp`) | Roteiro, passo 8 | **Pendente (máquina real, com o instalador)** |
| V11 | `--dev` sem admin abre a tela só para leitura | Roteiro, passo 1 | **Pendente (máquina real, com o instalador)** |

## Passos do responsável

1. Cadastrar no NocoDB, base "ITC Bench", tabela Servidores (uma linha ativa por par):
   - `GLPI Agent`/`servidor` (público);
   - `RustDesk`/`servidor` (público, só o host);
   - `RustDesk`/`chave` (não público);
   - `RustDesk`/`senha` (não público);
   - `RustDesk`/`api` (público, opcional, URL `https://` do "Servidor da API"; ADR-030);
   - `AnyDesk`/`senha` (não público).
2. Cadastrar em Instaladores três linhas, `GLPI Agent`, `RustDesk` e `AnyDesk`, com `Versao`,
   `Arquivo` (`.msi`, `.msi`, `.exe`), `SHA256` do arquivo oficial e `Link` `https://`.
3. Preencher `Unidades.TagGLPI` (opcional).
4. Trocar as senhas do RustDesk e do AnyDesk: as atuais ficaram em `segredos.json`, ao lado do EXE
   do Configurador.
5. Rodar V1–V11 numa máquina real com o instalador (roteiro abaixo).

Sem `.env`, deploy ou mudança na API.

## Roteiro do teste em máquina real (V1–V11)

1. Use um notebook reserva, sem GLPI Agent, RustDesk nem AnyDesk. Abra o Bench sem administrador
   (`--dev`): a tela mostra a situação e nada fica habilitado (V11). Depois abra com administrador,
   entre e sincronize.
2. **GLPI Agent:** clique em Instalar; confira na confirmação o servidor, a tag (ou "sem tag"), o
   SHA-256 e o comando. Depois de instalado:
   - o cartão mostra "Configuração: conferida";
   - `HKLM\SOFTWARE\GLPI-Agent` tem `server` e `tag`;
   - "Forçar inventário" faz a máquina aparecer ou ser atualizada no GLPI (V1).
3. **RustDesk:** instale. O cartão mostra o ID e "Configuração: conferida". De outra máquina,
   conecte pelo ID com a senha permanente do cadastro. **Esse é o teste que decide o mecanismo da
   senha (ADR-019).** Se falhar, pare e avise o responsável. Num notebook lento, a espera do
   serviço (até 90 s) tem que bastar (V2, V8).
4. **AnyDesk:** instale. O ID aparece no cartão; conecte sem supervisão com a senha do cadastro.
   Confira que não há ícone na área de trabalho e que o AnyDesk inicia com o Windows (V3).
5. Clique de novo em cada programa: o botão é "Reconfigurar" e não reinstala. Num notebook com
   uma versão mais velha, o botão é "Atualizar" e instala por cima (V4).
6. Num cadastro **de teste** (nunca os de produção):
   - troque um caractere do `SHA256` e sincronize: a instalação recusa "não confere";
   - desconecte a rede e use "Escolher arquivo…" com o instalador certo num pendrive;
   - desmarque uma linha de Servidores: o cartão diz "Falta: …" (V5, V6).
   Desfaça tudo.
7. Comece a instalar o RustDesk e clique em Cancelar durante o download (para na hora) e, numa
   segunda vez, durante o MSI (para depois que o MSI termina) (V7).
8. Durante a instalação, `Get-CimInstance Win32_Process | Select CommandLine` não mostra senha nem
   chave. Depois, procure as senhas de teste:
   - no `bench.log`;
   - em `%TEMP%`;
   - em `%ProgramData%\ITC\Bench\protegido\`;
   - em `%WINDIR%\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config\`, onde o
     `RustDesk.toml` deve ter só `password = "00…"` (ou `"01…"` no RustDesk 1.5.1) e nenhum
     `.tmp`.

   Em nenhum desses lugares a senha pode aparecer em texto (V10).
9. Se houver máquina em inglês, repita 2 a 4 (V9).

## Limites conhecidos

- A aceitação da senha do RustDesk pelo `RustDesk.toml` não foi testada; é o V2. A forma cifrada é
  reversível por admin local, como com o `--password`.
- A senha do AnyDesk e a do RustDesk ficam na memória do Bench durante a chamada.
- A tela não confere a senha do AnyDesk (o AnyDesk não expõe essa informação). A do RustDesk é
  conferida só como "cifrada", não comparada.
- GLPI em `http://` até a migração para HTTPS.
- Portas do RustDesk fixas (21116, 21117, 21118); servidor de ID e relay no mesmo host.
- Energia e "Manutenção geral" do Configurador ficam para o 12 e o 13.
