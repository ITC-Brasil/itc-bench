# Auditoria de segurança — Modo escuro, Ajuda em seções e papel de parede — 2026-11-12

Escopo: ADR-037, ADR-038 e ADR-039. Branch `feat/modo-escuro`, árvore de trabalho sobre `7b4b911`,
antes do commit; o código auditado entrou em `6cc5e6d`, `29a032d` e `5ec6162`. Feita com
`docs/security/AUDIT-PROMPT.md` por Claude (Opus 5.5).

Depois da auditoria entrou o ADR-040: topo das telas mais alto e "?" à direita. É só layout em
`ui/janela.py` e `ui/tema.py`, sem dado de fora e sem regra nova, e não muda nenhuma categoria
abaixo.

Arquivos lidos:
- `app/src/itc_bench/ui/tema.py`, `servicos/preferencias.py` (novo), `__main__.py`;
- `ui/configuracoes.py`, `ui/janela.py`, `ui/entrar.py`, `ui/preparacao.py`, `ui/ajuda.py`;
- `ui/aparencia.py`, `servicos/papel_de_parede.py`, `servicos/hive.py`,
  `recursos/politicas/comum.ps1`;
- `recursos/icones/marcado.svg`, `ponto.svg`, `seta.svg` (novos).

**Stack:** Python 3.13 + PySide6 6.12, app Windows elevado, sem servidor nesta mudança.
PowerShell 5.1 por trecho fixo (`executor.powershell`, dados só em `ITC_*`).

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 2 (corrigidos) |
| Informativa | 3 (1 risco aceito, 2 reforços feitos) |

## Achados

### [BAIXA, corrigido] Caminho do perfil no log ao falhar a preferência

- **Arquivos:** `app/src/itc_bench/servicos/preferencias.py` (função `_ler`) e
  `app/src/itc_bench/ui/janela.py` (`Janela.escolher_modo`).
- **Trecho antes:**
  - `log.warning("Preferências ilegíveis em %s; usando o padrão: %s", arq, erro)`;
  - `log.error("Aparência não gravada: %s", erro)`.
- **Por que importa:** `arq` fica em `%LOCALAPPDATA%\ITC\Bench`, isto é, `C:\Users\<nome>\...`.
  O `str()` de um `OSError` também traz o caminho. A regra do registro (ADR-023, ajuda da tela
  Registro) é nunca ter pasta de perfil no log. O nome da conta iria para o `bench.log`, que é
  exportado para chamado.
- **Condições:** arquivo de preferência corrompido ou pasta sem permissão de escrita.
- **Correção:** o log leva só o tipo do erro (`type(erro).__name__`). A tela mostra só
  `erro.strerror`, sem caminho. Teste novo:
  `test_modo_escuro.py::test_preferencia_ilegivel_nao_loga_caminho`.

### [BAIXA, corrigido] Decodificador da prévia escolhido pelo conteúdo

- **Arquivo:** `app/src/itc_bench/ui/aparencia.py`, `carregar_previa`.
- **Antes:** `QImageReader(str(arquivo))` decidia o formato pelo conteúdo. A prévia aceita o
  arquivo de "Escolher arquivo…", que vem de fora do cadastro, e o abria com o decodificador que
  o Qt achasse no conteúdo.
- **Correção:**
  - extensão fora de `pp.EXTENSOES` é recusada;
  - `pp.conferir_imagem` roda antes (até 20 MB, assinatura de bytes igual à extensão, de 640x480
    a 7680x4320);
  - `setFormat(b"png"|b"jpeg")` + `setDecideFormatFromContent(False)`;
  - leitura reduzida a 960 px de largura.
  Testes:
  - `test_aparencia_tela.py::test_papel_previa_recusa_arquivo_invalido`: conteúdo inválido, imagem
    pequena, `.gif` com PNG dentro e PNG com nome `.jpg`.

### [INFORMATIVA, risco aceito] O técnico pode pôr o papel de parede na própria conta

ADR-039. Com a conta que roda o Bench marcada, o papel do Grupo vale nela no próximo logon, e
ela não troca. Mitigações: "(você)" na lista, aviso na confirmação, ajuda da tela e Desfazer. Não
é escalada: a política só restringe, e quem aplica já é administrador elevado.

### [INFORMATIVA, reforço] `QLabel` do número do passo na Ajuda

`ui/ajuda.py`, `_corpo`: `QLabel(marca)` estava em `AutoText`. O valor vem só dos textos `AJUDA*`
do código (dígitos de `PASSO` ou "•"), mas passou a `PlainText` como todo o resto da tela.

### [INFORMATIVA, reforço] Gravação atômica da preferência

`servicos/preferencias.py`, `gravar_modo`: grava em `preferencias.tmp` e troca por `replace`, na
pasta do próprio usuário. O valor é validado contra `MODOS` antes, e só o campo `modo` é lido de
volta, com a mesma lista.

## Verificado e correto

- **Liberação da conta do Bench só para o papel (ADR-039):** são duas conferências.
  - `comum.ps1`, `Hive-Escrita`/`So-Papel`: exige `ITC_PERMITIR_DONO=1` **e** perfil `politicas`,
    ou perfil `aparencia` com **todas** as operações em `$CHAVE_PAPEL`. Sem operações, JSON
    inválido (`catch` devolve falso) ou chave de mouse e teclado: `ERRO|dono`. Seis casos com
    PowerShell real em `test_politicas.py::test_hive_escrita_real_conta_que_roda` passaram nesta
    máquina, sem pulo.
  - `escrever.ps1` continua conferindo cada operação: `Raiz-Aceita`, `Valor-Aceito` e caminho do
    `Wallpaper` na pasta do Bench.
  - Python: `pp.aplicar` tem `permitir_dono=False` por padrão. Só a tela passa `True`; a
    Preparação (`servicos/etapas.py`) e o Mouse e teclado não passam
    (`test_papel_de_parede.py::test_tela_aplica_na_conta_que_roda_o_bench` e o teste anterior, que
    ainda espera a recusa sem o parâmetro).
  - Nativo (`-500`) e Suporte continuam recusados nos dois lados.
- **"Baixar e ver a imagem":**
  - chama o mesmo `pp.obter` do Aplicar: `validar`, `https`, SHA-256 e pasta com ACL do ADR-022;
  - não grava política;
  - o botão só aparece com administrador e segue `_ocupar` (fica desligado durante outra tarefa).
- **Folha de estilo:**
  - `tema._arquivo` monta `url()` só com nomes fixos (`marcado`, `ponto`, `seta`) dentro de
    `itc_bench.recursos`;
  - nenhum dado de fora entra na folha;
  - os SVG novos não têm script nem referência externa.
- **Ajuda em seções:** os textos vêm só das constantes `AJUDA*`, e todo rótulo é `PlainText`
  (`_rotulo`). A busca só filtra, sem montar texto. `test_texto_puro.py` passa.
- **Preferência:** fica em `%LOCALAPPDATA%` (regra de caminhos do `AGENTS.md`), sem senha nem
  cadastro, e um valor desconhecido vira claro.
- **Cores de situação:** `tema.cor_situacao` só troca a cor; o texto mostrado é o mesmo.

## Categorias

1. **Banco sem tranca:** não se aplica (nenhuma mudança na API nem no SQLite).
2. **Permissão no cliente:** as regras estão no serviço e no trecho. A tela só esconde ou avisa,
   como o "(você)" e o botão de baixar só com administrador.
3. **IDOR:** não se aplica (sem rota nova).
4. **Chaves expostas:** nada novo; nenhum endereço, chave ou SSID nos arquivos tocados.
5. **Inputs:**
   - imagem de fora: decodificador fixo e conferência antes de abrir (corrigido acima);
   - texto: só `PlainText`;
   - `ITC_OPERACOES` é montado pelo Bench do catálogo do papel e conferido de novo no trecho.
