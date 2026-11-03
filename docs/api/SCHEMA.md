# SCHEMA dos arquivos de sessão — Técnico Assistente (Fase 1)

Este documento descreve o que a ferramenta grava em disco. O formato foi
desenhado para ser lido por um modelo de linguagem na Fase 2: os dados já
saem **agrupados e classificados**, com campos autoexplicativos e sem texto
cru redundante.

Regras gerais:

- Um diretório por execução: `sessoes/AAAA-MM-DD_HHmm_<HOSTNAME>/`.
- Um arquivo JSON por módulo, mais `sessao.json` com os metadados.
- Codificação **UTF-8 sem BOM**. Datas em ISO 8601 (`o` do .NET), com fuso.
- Tamanhos em **bytes** (`bytes`), exceto onde o nome do campo diz outra
  unidade (`...MB`, `...GB`, `...MWh`).
- `hostname` aparece em todos os arquivos: é o identificador universal do
  projeto e a chave da agregação da Fase 3.
- Campo ausente ou não coletado é `null`, nunca string vazia.

## Envelope comum dos módulos

Todo `<modulo>.json` tem a mesma casca:

```json
{
  "versaoSchema": "1.2",
  "tipo": "modulo",
  "modulo": "disco",
  "rotulo": "Disco, espaço e SMART",
  "hostname": "BSBIA-NB-014",
  "sessaoId": "2026-09-05_1432_BSBIA-NB-014",
  "coletadoEm": "2026-09-05T14:32:10.1234567-03:00",
  "duracaoSegundos": 42.7,
  "executadoElevado": true,
  "status": "ok",
  "erro": null,
  "dados": { }
}
```

- `status`: `ok` ou `erro`. Falha de um módulo **não** derruba a sessão; o
  erro fica aqui e no índice do `sessao.json`.
- `dados`: conteúdo específico do módulo, descrito abaixo. Todo módulo pode
  ter `dados.avisos` (array de strings) com o que ficou incompleto — quase
  sempre por falta de privilégio administrativo.

## sessao.json

```json
{
  "versaoSchema": "1.2",
  "tipo": "sessao",
  "id": "2026-09-05_1432_BSBIA-NB-014",
  "hostname": "BSBIA-NB-014",
  "usuarioExecucao": "tecnico.admin",
  "usuarioSessao": "BSBIA-NB-014\\aluno01",
  "projeto": "BSBIA",
  "subPerfil": "aluno",
  "politicaLimpeza": "permissiva",
  "inicio": "2026-09-05T14:32:00-03:00",
  "fim": "2026-09-05T14:51:00-03:00",
  "ultimaAtualizacao": "2026-09-05T14:51:00-03:00",
  "duracaoSegundos": 1140,
  "encerradaNormalmente": true,
  "executadoElevado": true,
  "ferramentaVersao": "1.2 (Fase 2)",
  "maquina": {
    "fabricante": "LENOVO", "modelo": "82C6", "familia": "V14 G4 AMN",
    "numeroSerie": "XXXXXXXX", "memoriaTotalGB": 8,
    "processador": "AMD Ryzen 5 7520U", "sistema": "Microsoft Windows 11 Pro",
    "versaoSistema": "10.0.22631"
  },
  "modulos": {
    "disco": { "rotulo": "...", "arquivo": "disco.json", "status": "ok", "erro": null, "duracaoSegundos": 42.7 }
  },
  "correcoes": [],
  "avisos": []
}
```

`modulos` é o índice: diz quais módulos rodaram nesta sessão e onde está o
resultado de cada um. É regravado a cada módulo concluído, então uma sessão
interrompida no meio continua legível.

- `fim`: preenchido só quando o técnico sai pelo `[S]`. Janela fechada pelo X
  deixa `fim: null` e `encerradaNormalmente: false`, o que é informação correta.
- `ultimaAtualizacao`: carimbo de cada gravação do `sessao.json`. Numa sessão
  interrompida, é o horário do último registro feito.
- `usuarioExecucao`: `$env:USERNAME`, a conta que executou a ferramenta. Numa sessão
  elevada é a conta que elevou, em geral a do técnico.
- `usuarioSessao`: `Win32_ComputerSystem.UserName` (`DOMINIO\usuario` ou
  `MAQUINA\usuario`), o usuário com sessão interativa no console. `null` quando não há
  ninguém logado no console.

## eventlog.json

`dados`:

| campo | descrição |
|---|---|
| `janelaDias`, `janelaInicio` | janela analisada (padrão 7 dias) |
| `logsAnalisados` | sempre `["System","Application"]` |
| `niveisAnalisados` | sempre `["critico","erro","aviso"]` (Level 1, 2 e 3) |
| `avisoSomenteBase` | sempre `true`: Avisos (Level 3) só são lidos para os pares provedor + id da base curada |
| `totalOcorrencias` | soma de eventos individuais |
| `totalGrupos` | grupos `(provedor, id)` |
| `gruposCriticos`, `gruposDesconhecidos` | contagens de apoio |
| `grupos[]` | um item por par `(provedor, id)` |

Cada item de `grupos[]` (ordenado por nível — crítico, erro, aviso — e, dentro do nível, por frequência):

```json
{
  "log": "System",
  "provedor": "Microsoft-Windows-Kernel-Power",
  "id": 41,
  "nivel": "critico",
  "ocorrencias": 6,
  "primeiraOcorrencia": "2026-08-30T08:11:02-03:00",
  "ultimaOcorrencia": "2026-09-04T17:44:20-03:00",
  "conhecido": true,
  "apelido": "Kernel-Power 41",
  "categoria": "energia",
  "peso": "alto",
  "descricao": "A máquina foi desligada sem encerrar o Windows...",
  "acaoSugerida": "Verificar saúde da bateria e a fonte usada na carreta...",
  "nota": null,
  "fonteOficial": true,
  "exemploMensagem": null
}
```

- `categoria`, `peso`, `descricao`, `acaoSugerida`, `nota` e `fonteOficial` vêm de
  `config/eventlog-conhecidos.json`; ficam `null` quando `conhecido: false`.
- `peso`: `alto` | `medio` | `baixo`, a importância do evento para correlação.
- `fonteOficial`: `false` quando a descrição da base não tem fonte oficial da
  Microsoft (entradas herdadas da Fase 1). O relatório deve tratar esses grupos
  com confiança menor (TA-ADR-020). `null` quando `conhecido: false`.
- `nota`: ressalva da base curada, por exemplo a de que os NVMe da frota não
  expõem contadores de erro no SMART.
- `nivel`: `critico` | `erro` | `aviso` — o nível mais grave registrado no grupo.
  `aviso` só aparece para pares da base curada (caso do `disk 51`, registrado
  como Aviso no Windows 10/11). Aviso de evento fora da base não é lido.
- `conhecido` exige provedor **e** id iguais aos da base: o mesmo id em outro
  provedor é outro evento e fica `conhecido: false`, sem descrição (TA-ADR-020).
- `exemploMensagem` só é preenchido quando `conhecido: false` — trecho de até
  300 caracteres da última ocorrência, para dar contexto ao relatório da
  Fase 2. Nunca há despejo de entradas individuais.

## disco.json

`dados.unidadeFerramenta` — de onde a ferramenta rodou: `letra`,
`discoNumero`, `tipo`, `barramento`, `excluida`. Com `excluida: true`, o
volume e o disco físico da ferramenta **não** aparecem em `volumes` nem em
`discosFisicos`. Só é excluída unidade removível ou USB que não seja a do
sistema; outros dispositivos USB continuam sendo coletados.

`dados.volumes[]` — um por letra de unidade: `letra`, `rotulo`,
`sistemaArquivos`, `tipo`, `totalGB`, `livreGB`, `percentualLivre`,
`critico` (livre < 10%), `atencao` (livre entre 10% e 20%).

`dados.discosFisicos[]` — um por disco físico, com SMART:
`numero`, `modelo`, `tipoMidia`, `barramento`, `tamanhoGB`, `saude`,
`estadoOperacional`, `estadoSmart`, `errosLeituraNaoCorrigidos`,
`errosEscritaNaoCorrigidos`, `errosLeituraCorrigidos`,
`errosEscritaCorrigidos`, `temperaturaC`, `temperaturaMaximaC`,
`horasLigado`, `percentualDesgaste`, `observacao`.

- `estadoSmart`: `completo` (todos os contadores), `parcial` (alguns;
  `observacao` lista os que o driver não expõe) ou `indisponivel` (nenhum;
  sem elevação, o motivo fica em `observacao`). Os NVMe da frota costumam
  sair `parcial`.
- `percentualDesgaste`: `Wear` do `MSFT_StorageReliabilityCounter`, sem
  conversão. 0 = novo, 100 = limite estimado de desgaste atingido. `null`
  quando o driver não informa — nunca 0.
- `temperaturaMaximaC`: `TemperatureMax`, a temperatura máxima de operação
  normal do dispositivo, **não** a maior temperatura já registrada.
- Temperatura 0 vira `null`: drivers sem suporte (comum em USB) devolvem 0 em
  vez de nulo. `percentualDesgaste: 0` continua ambíguo — pode ser disco novo
  ou driver que não informa; em disco USB, tratar como não informado.
- Contador ausente é `null`. Ausência de erro no SMART de um NVMe `parcial`
  não é evidência de disco saudável: os contadores de erro não existem.

`dados.itensLimpeza[]` — catálogo de `config/classificacao-disco.json` já
expandido para os caminhos reais da máquina, ordenado por tamanho:

```json
{
  "id": "cache-chrome",
  "rotulo": "Cache do Google Chrome",
  "tier": "seguro",
  "estrategia": "conteudo",
  "caminho": "C:\\Users\\aluno01\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache",
  "usuario": "aluno01",
  "bytes": 1932735283,
  "arquivos": 8421,
  "idadeMinimaDias": 0,
  "requerElevacao": false,
  "medido": true,
  "nota": null
}
```

- `tier`: `seguro` | `revisar` | `bloqueado`. **Somente `seguro` pode ser
  oferecido como limpeza.** `bloqueado` nunca vira opção, por maior que seja.
- `estrategia`: `conteudo` | `arquivos` | `lixeira` | `nenhuma`.
- `nota`: instrução textual quando o item exige procedimento próprio — é o
  caso do WinSxS, que só deve ser reduzido com
  `DISM /Online /Cleanup-Image /StartComponentCleanup`.

`dados.maioresPastasPerfil[]` — pastas de perfil acima do limiar:
`caminho`, `usuario`, `bytes`, `arquivos`, `tier`.

`dados.maioresArquivos[]` — os 25 maiores arquivos acima do limiar:
`caminho`, `bytes`, `extensao`, `ultimaModificacao`, `tier`.

`dados.resumo` — `recuperavelSeguroBytes`, `itensSeguroComConteudo`,
`revisarBytes`, `itensRevisar`, `limiarArquivoMB`, `limiarPastaMB`.

`dados.tiers` — o texto que define cada tier, copiado da configuração, para
que o consumidor da Fase 2 não precise abrir outro arquivo.

## bateria.json

```json
{
  "presente": true,
  "baterias": [ { "nome": "...", "cargaAtualPercentual": 87, "statusCodigo": 2, "emUsoDeBateria": false } ],
  "capacidadeProjetoMWh": 44000,
  "capacidadeAtualMWh": 33000,
  "desgastePercentual": 25.0,
  "classificacaoDesgaste": "desgaste-moderado",
  "ciclosCarga": 212,
  "relatorioGerado": true,
  "arquivoRelatorio": "batteryreport.html",
  "avisos": []
}
```

`classificacaoDesgaste`: `saudavel` (<20%), `desgaste-moderado` (20–40%),
`desgaste-alto` (40–60%), `substituicao-recomendada` (≥60%),
`desconhecido` (não foi possível extrair).
O HTML completo do `powercfg /batteryreport` fica na própria pasta da sessão.

## rede.json

`dados.adaptadores[]`: `nome`, `descricao`, `status`, `tipoConexao`,
`macAddress`, `velocidadeMbps`, `enderecosIPv4[]`, `gateway`,
`servidoresDNS[]`, `dhcp`, `semIP` (ativo sem IP), `apipa` (adaptador `Up`
com IP 169.254.x.x; em adaptador desconectado é sempre `false`, porque esse
endereço é normal ali).

`dados.testesConectividade[]`: `tipo` (`ping` | `resolucao-dns`), `alvo`,
`sucesso`, `latenciaMs`, `detalhe`.

`dados.portasEmEscuta[]`: `protocolo`, `enderecoLocal`, `porta`, `pid`,
`processo`, `escutaExterna`.

`dados.resumo`: `adaptadoresAtivos`, `temIPValido`, `internetOk`, `dnsOk`,
`portasEmEscutaTotal`.

## processos.json

`dados.memoria`: `totalGB`, `disponivelGB`, `percentualEmUso`,
`pressaoAlta` (≥85% — relevante numa frota inteira de 8 GB).

`dados.processosPorMemoria[]` (15 maiores): `nome`, `pid`, `memoriaMB`,
`instancias`, `inicio`, `caminho`.

`dados.processosPorCpu[]` (10 maiores): `nome`, `pid`, `tempoCpuSegundos`,
`memoriaMB`.

`dados.servicosAutomaticosParados[]`: `nome`, `nomeExibicao`, `estado`,
`inicio`, `contaLogon`, `atrasado`.

`dados.itensInicializacao[]`: `nome`, `comando`, `origem`, `usuario`.

`dados.resumo`: `totalProcessos`, `servicosAutomaticosParados`,
`itensInicializacao`, `memoriaPressaoAlta`.

## correcoes.json

Criado apenas quando houve alguma ação corretiva. As mesmas entradas são
espelhadas em `sessao.json > correcoes`.

```json
{
  "versaoSchema": "1.2",
  "tipo": "correcoes",
  "hostname": "BSBIA-NB-014",
  "sessaoId": "2026-09-05_1432_BSBIA-NB-014",
  "acoes": [
    {
      "acao": "limpar-temporarios",
      "alvo": "C:\\Users\\aluno01\\AppData\\Local\\Temp",
      "resultado": "sucesso",
      "detalhe": "Liberado 1,84 GB.",
      "contexto": { "id": "temp-usuario", "tier": "seguro", "bytesAntes": 1975684, "bytesDepois": 12048, "bytesLiberados": 1963636, "itensBloqueados": 3 },
      "confirmadoPeloTecnico": true,
      "executadoElevado": true,
      "momento": "2026-09-05T14:49:03-03:00"
    }
  ]
}
```

- `acao`: `matar-processo` | `reiniciar-servico` | `resetar-adaptador` |
  `limpar-temporarios`.
- `resultado`: `sucesso` | `falha` | `cancelada`. `cancelada` significa que a
  ferramenta ofereceu e o técnico recusou — é informação útil, por isso é
  registrada.
- `contexto`: campos específicos da ação (antes/depois, PID, estados).

## Histórico de versões

A regra de incremento está no TA-ADR-018 (`docs/DECISIONS.md`).

### 1.2 (Módulo 07)

| Arquivo | Campo | Mudança |
|---|---|---|
| `sessao.json` | `usuarioLogado` → `usuarioExecucao` | Renomeado: o valor sempre foi `$env:USERNAME`, que numa sessão elevada é a conta que elevou, não o usuário da máquina (verificação da frota, 2026-09-28) |
| `sessao.json` | `usuarioSessao` | Novo: `Win32_ComputerSystem.UserName`, o usuário logado no console, ou `null` |
| `sessao.json` | `ferramentaVersao` | `1.2 (Fase 2)` |

A API normaliza 1.0 e 1.1 copiando `usuarioLogado` para `usuarioExecucao`, com
`usuarioSessao: null` (`api/app/normalizacao.py`).

### 1.1 (Módulo 00.1)

| Arquivo | Campo | Mudança |
|---|---|---|
| `disco.json` | `resumo.recuperavelSeguroBytes`, `resumo.revisarBytes` | Semântica: em 1.0 saíam sempre 0 (defeito de soma); agora trazem o total real |
| `disco.json` | `discosFisicos[].percentualVidaRestante` → `percentualDesgaste` | Renomeado; o valor sempre foi desgaste (`Wear`), não vida restante |
| `disco.json` | `discosFisicos[].smartDisponivel` → `estadoSmart` | Renomeado e tipo trocado: bool → `completo` / `parcial` / `indisponivel` |
| `disco.json` | `unidadeFerramenta` | Novo; volume e disco da ferramenta saem de `volumes` e `discosFisicos` |
| `disco.json` | `itensLimpeza`, `maioresPastasPerfil` | Ordem: em 1.0 não saíam ordenados por `bytes`; agora saem |
| `eventlog.json` | `grupos` | Ordem: em 1.0 a frequência não era aplicada dentro de cada nível |
| `eventlog.json` | `grupos[].peso`, `grupos[].nota`, `grupos[].fonteOficial` | Novos, vindos da base curada |
| `eventlog.json` | `niveisAnalisados`, `avisoSomenteBase`, `grupos[].nivel` | Avisos lidos para os pares da base; `nivel` ganha o valor `aviso` |
| `eventlog.json` | `grupos[].conhecido` | Semântica: só com provedor + id exatos (em 1.0 o id sozinho bastava) |
| `rede.json` | `adaptadores[].apipa` | Semântica: só `true` em adaptador `Up` |
| `sessao.json` | `ultimaAtualizacao` | Novo; carimbo de cada gravação |
| `sessao.json` | `ferramentaVersao` | `1.1 (Fase 1)` |

### 1.0

Versão da Fase 1 original.

## Notas para as próximas fases

**Fase 2 (IA).** A geração de relatório continua isolada em
`lib/Util-Relatorio.ps1`, função `Write-RelatorioSessao`. Com `-UsarIA` (opção
`[1] Diagnóstico completo`), ela envia os arquivos descritos aqui à API
(`POST /v1/relatorio`, corpo em `docs/API.md`) e grava na pasta da sessão:

- `relatorio.md`: o laudo da IA (`relatorio_md`), com uma linha de cabeçalho com
  modelo, diagnóstico e data.
- `chamado.md`: título e descrição do chamado para o GLPI.

Em qualquer falha, mostra o relatório determinístico da Fase 1 e o motivo.

**Fase 3 (histórico).** A agregação em
`historico/por_maquina/<HOSTNAME>.json` (append-only) é direta: cada
`sessao.json` já é um registro fechado, com `hostname`, `id` ordenável por
data, `projeto`/`subPerfil` e o índice `modulos` apontando para os detalhes.
Um "Resumo da Unidade Móvel" pode ser montado lendo apenas os `sessao.json`
de cada pasta, sem abrir os arquivos de módulo.
