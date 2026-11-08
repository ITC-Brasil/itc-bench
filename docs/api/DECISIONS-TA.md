> Importado de `ITC-Brasil/tecnico-assistente` em `0bc5620` (ADR-012). Os ADRs de lá aparecem como
> `TA-ADR-NNN` para não colidir com os do Bench; hosts, porta e usuário de deploy trocados por
> marcadores. Documento histórico: decisões novas da API entram em `docs/DECISIONS.md`.

# Architecture Decision Records

Registro sequencial de decisões, com contexto e alternativas rejeitadas.
Cada entrada é permanente — ADRs substituídos são marcados, nunca apagados.

---

## TA-ADR-001 — Usar monorepo com `pendrive/` e `api/`

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
O projeto tem duas partes que se comunicam por um contrato de dados: o cliente em
PowerShell no pendrive produz JSONs de sessão (`sessao.json` e um arquivo por módulo),
e a API no glpi-srv consome esses JSONs para gerar o relatório. Qualquer mudança no
formato produzido pela Fase 1 precisa ser acompanhada pela API no mesmo momento, e
defeitos já encontrados na Fase 1 (campos renomeados, semântica corrigida) mostram que
esse contrato ainda vai evoluir.

**Decision**
Manter as duas partes num único repositório, `ITC-Brasil/tecnico-assistente`, com
`pendrive/` e `api/` na raiz e o deploy filtrado por `paths: api/**`.

**Alternatives considered**
- Dois repositórios (`tecnico-assistente-pendrive` e `tecnico-api`) — rejeitado: o
  contrato de dados ficaria dividido entre dois históricos, e uma mudança de schema
  exigiria PRs coordenados em repositórios diferentes.

**Consequences**
Mudanças no contrato cabem num único PR, revisado de uma vez. O workflow de deploy
precisa de filtro por caminho para que alterações só em `pendrive/` não disparem deploy
no servidor. A documentação (`documentacao-tecnico-assistente.md`, `docs/`) cobre as
duas partes.

---

## TA-ADR-002 — Descartar IA local no notebook

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
O plano original previa um modelo de linguagem rodando do próprio pendrive
(`llama-server` do llama.cpp + GGUF), para ler os JSONs de sessão e escrever o relatório
sem depender de internet. O candidato principal era o Qwen3.5-4B em Q4_K_M (arquivo de
2,74 GB). A tabela oficial da Unsloth indica requisito de 5,5 GB de memória para esse
modelo em 4 bits; com contexto travado em 8K, KV cache em `q8_0` e sem o arquivo de
visão `mmproj`, a estimativa caiu para 3,2–3,6 GB. A sessão real
`2026-09-24_1130_RESERVA-06` (Lenovo V15 G3, i5-1235U) registrou em `processos.json`
`totalGB: 7.7` e `disponivelGB: 2.1` com a máquina em uso normal — o cenário em que o
técnico rodaria a ferramenta. Além disso, o prompt montado a partir de uma sessão real
ficou em cerca de 13 mil caracteres (~4–5 mil tokens), o que inviabiliza reduzir o
contexto para 4K como alavanca de economia de memória.

**Decision**
Não executar modelo de linguagem no notebook; a geração de texto acontece fora da
máquina, num serviço central (TA-ADR-003).

**Alternatives considered**
- Qwen3.5-2B em Q4_K_M (1,28 GB, requisito oficial de 3,5 GB) — rejeitado: queda grande
  nos indicadores que importam para a tarefa — qualidade multilíngue (WMT24++ de 66,6
  para 45,8), aderência a instruções (IFEval de 89,8 para 78,6) e contexto longo
  (AA-LCR de 57,0 para 25,6) — e ainda disputaria os 2 GB livres com o Windows.
- Qwen3.5-0.8B — rejeitado: IFEval 44,0 e WMT24++ 27,2; o próprio fabricante o
  posiciona para prototipagem e fine-tuning.
- OpenCode CLI portátil no pendrive — rejeitado: agente interativo de código usado para
  uma única requisição; documentação recomenda WSL no Windows, ausente na frota.
- Gemma 4 E4B, Granite 4.1/4.2 3B, Ministral 3 3B, Ornith — rejeitados na pesquisa de
  modelos (peso, qualidade de escrita, licença comercial restritiva ou categoria errada).

**Consequences**
O Kit de Benchmark construído para medir os candidatos locais não é importado para o
repositório. A camada de IA passa a depender de conectividade, o que exige fallback para
o relatório determinístico da Fase 1 (TA-ADR-003). O pendrive não carrega binários nem
modelos, e a ferramenta continua rodando em qualquer máquina da frota sem consumo
adicional de memória.

---

## TA-ADR-003 — Usar OpenCode Go como provedor, chamado apenas pelo servidor

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
Com a IA fora do notebook (TA-ADR-002), era preciso um provedor de modelo. A gestão
descartou pay-as-you-go e preferiu modelos chineses por custo; a conectividade nas
carretas é excelente. O Grupo já tem assinatura do OpenCode Go (US$ 10/mês), cuja chave
funciona fora do OpenCode por endpoints compatíveis com OpenAI
(`https://opencode.ai/zen/go/v1/chat/completions`). A documentação do Go afirma que o
serviço é projetado para agentes de código com tráfego semelhante, pede user agent
próprio e cabeçalho `x-opencode-session`, e informa que o tráfego é monitorado contra
abuso. Nosso uso — uma requisição por diagnóstico, sem loop de ferramentas — não é
tráfego típico de agente de código. Consultar o suporte foi descartado pela gestão, para
não atrair atenção desnecessária. Pela tabela de privacidade do Go, MiMo, GLM, Qwen,
DeepSeek, Kimi, MiniMax e LongCat têm treinamento "não usado" e retenção de 0 dias.
Custo estimado: ~10.000 tokens de entrada e ~1.000 de saída por diagnóstico, cerca de
US$ 0,0017 no MiMo-V2.6-Flash, frente a um limite mensal de US$ 60 nesse modelo.

**Decision**
Usar o OpenCode Go como provedor, com a chave guardada apenas no servidor central, que é
o único componente a chamar o Go.

**Alternatives considered**
- Chave do Go gravada nos pendrives, chamada direto do PowerShell — rejeitado: chave em
  texto em mais de dez pendrives com técnicos rotativos e alunos por perto; revogação
  exigiria atualizar todos; tráfego da mesma chave vindo de dezenas de IPs é o padrão
  que sistemas antiabuso associam a chave compartilhada.
- Pay-as-you-go (Zen ou provedor direto) — rejeitado pela gestão.
- Consultar o suporte do Go antes — rejeitado pela gestão.

**Consequences**
Risco aceito: a chave pode ser suspensa por uso fora do padrão previsto. Mitigações:
user agent próprio (`itc-tecnico-assistente/1.0`), `x-opencode-session` por
diagnóstico, origem única de tráfego, alerta no ntfy quando o Go recusar, e fallback
para o relatório determinístico no pendrive. O cliente da API é genérico e compatível
com OpenAI: trocar de provedor é mudar URL e chave no `.env`.

---

## TA-ADR-004 — Usar Python 3.12 + FastAPI + SQLite no serviço central

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
O serviço central precisa receber o diagnóstico, validar o token da carreta, montar o
prompt, chamar o Go, guardar histórico e responder. O volume é baixo (centenas de
diagnósticos por mês). A equipe de TI mantém o glpi-srv com containers Docker e já
opera n8n com PostgreSQL. Quem mantém o código não é desenvolvedor em tempo integral.

**Decision**
Implementar o serviço em Python 3.12 com FastAPI e Uvicorn, usando SQLite num volume
nomeado como banco.

**Alternatives considered**
- Workflow no n8n (webhook → nó HTTP → resposta) — rejeitado: prompt e lógica ficariam
  dentro do workflow, fora do Git e sem CI; testes automatizados inviáveis; controle por
  token, limite de requisições e histórico por hostname ficariam menos limpos. Seria mais
  rápido para um primeiro protótipo.
- PostgreSQL — rejeitado para esta fase: volume não justifica um serviço de banco a
  mais; SQLite simplifica CI (banco temporário por suite) e backup (um arquivo).

**Consequences**
Código versionado, testável e com deploy automatizado. Migração para PostgreSQL continua
possível se o volume crescer. O arquivo SQLite precisa entrar na rotina de backup do
glpi-srv no dia do deploy.

---

## TA-ADR-005 — SQLite como fonte da verdade e NocoDB como espelho só de ida

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
A administração quer consultar diagnósticos e a visão da frota sem construir interface
(TA-ADR-008), e o Grupo centraliza dados no NocoDB. Para as carretas escreverem no NocoDB,
cada pendrive precisaria de um token do NocoDB, que dá acesso amplo à base (ler, alterar,
apagar) e não tem revogação por carreta.

**Decision**
O SQLite do serviço é a fonte da verdade; o serviço espelha os diagnósticos para uma
tabela do NocoDB, de forma assíncrona e só de ida. As carretas nunca acessam o NocoDB.

**Alternatives considered**
- Carretas gravando direto no NocoDB — rejeitado: token amplo e sem revogação individual
  gravado nos pendrives.
- NocoDB como banco principal do serviço — rejeitado: indisponibilidade do NocoDB
  derrubaria a geração de relatórios.
- Sincronização nos dois sentidos — rejeitado nesta fase: complexidade de conflito sem
  necessidade atual.

**Consequences**
Se o NocoDB estiver fora do ar, o diagnóstico é gravado e marcado como pendente de
espelhamento, com reenvio posterior. Edições feitas no NocoDB não voltam ao serviço;
marcar diagnóstico como resolvido pelo NocoDB exigiria rever esta decisão. Leituras que
a carreta precisar (histórico, resumo da unidade) são rotas da API sobre o SQLite.

---

## TA-ADR-006 — Montar o prompt do relatório no servidor

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
O texto do prompt (instruções, regras, formato de saída) e a escolha do modelo vão
evoluir com o uso em campo. Os pendrives ficam nas carretas e só são atualizados quando
alguém os manuseia.

**Decision**
O pendrive envia apenas os dados agrupados da sessão; o servidor monta o prompt a partir
de `api/app/prompts/relatorio.md` e do histórico do hostname.

**Alternatives considered**
- Montar o prompt no pendrive (como fazia a função `New-PromptRelatorio` do Kit de
  Benchmark) — rejeitado: cada ajuste de prompt exigiria atualizar todos os pendrives.

**Consequences**
Ajuste de prompt ou troca de modelo é uma mudança no servidor, com deploy normal. O
servidor precisa conhecer o schema dos JSONs da Fase 1 e tolerar campos novos ou
ausentes.

---

## TA-ADR-007 — Autenticar em duas camadas: Cloudflare Access e token por carreta

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
O serviço é exposto pelo `<túnel cloudflared>` da Cloudflare. É preciso impedir que a internet
em geral alcance o serviço e, ao mesmo tempo, identificar e revogar individualmente um
pendrive perdido. O glpi-srv já opera Authelia como SSO.

**Decision**
Exigir, na borda, um service token do Cloudflare Access (compartilhado por todos os
pendrives) e, na API, um token individual por carreta, armazenado apenas como hash
SHA-256.

**Alternatives considered**
- Apenas token por carreta — rejeitado: o serviço ficaria exposto a varreduras da
  internet.
- Apenas service token do Cloudflare — rejeitado: sem rastreabilidade por carreta e sem
  revogação individual.
- Authelia — rejeitado: projetado para pessoas com navegador, não para um script
  PowerShell.

**Consequences**
Perder um pendrive exige revogar só o token daquela carreta; o service token do
Cloudflare continua válido para os demais e sozinho não dá acesso à API. O runbook
`docs/TOKENS.md` documenta as duas camadas e a rotação de cada uma.

---

## TA-ADR-008 — Não construir frontend nesta fase

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
Os técnicos trabalham no terminal do pendrive e recebem o relatório na pasta da sessão.
A administração (duas ou três pessoas) precisa criar e revogar tokens e consultar
diagnósticos, com baixa frequência.

**Decision**
Não haver interface web: tokens administrados por CLI dentro do container
(`python -m app.tokens`) e consulta de diagnósticos pelo espelho no NocoDB (TA-ADR-005).

**Alternatives considered**
- SPA em Next.js + shadcn — rejeitado: segundo projeto com build e deploy próprios,
  manutenção desproporcional ao uso.
- Painel Jinja2 + HTMX no próprio FastAPI — adiado: opção preferida caso o NocoDB não
  atenda alguma necessidade da administração.

**Consequences**
Nenhuma superfície web autenticada para proteger. Swagger e ReDoc desligados em
produção. Se o painel for criado, precisará de autenticação de pessoa (Authelia ou
política de e-mail do Cloudflare Access), separada da autenticação das carretas.

---

## TA-ADR-009 — Publicar a porta do container apenas em 127.0.0.1

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
No glpi-srv, o `cloudflared` roda no host e acessa os serviços por `localhost`. As
lições aprendidas do servidor registram que o Docker contorna o UFW via iptables: uma
porta publicada no formato padrão fica acessível em todas as interfaces, inclusive a
`eno8303`, na LAN do RB1100.

**Decision**
Publicar a porta no compose como `"127.0.0.1:${APP_PORT}:${APP_PORT}"`.

**Alternatives considered**
- Publicação padrão com regra de UFW — rejeitado: a regra não filtra portas publicadas
  pelo Docker.

**Consequences**
O único caminho até o serviço é o túnel da Cloudflare. Testes locais a partir de outra
máquina da LAN não alcançam o container; o health check do deploy roda no próprio
servidor, em `127.0.0.1`.

---

## TA-ADR-010 — Limitar a chamada ao OpenCode Go a 60 segundos

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
A Cloudflare encerra requisições proxied que passam de cerca de 100 segundos, com erro
524. Se o Go demorar, o pendrive receberia um erro genérico da borda em vez de uma
resposta que permita decidir o fallback.

**Decision**
Timeout de 60 segundos na chamada ao Go, configurável por `OPENCODE_GO_TIMEOUT_SECONDS`,
com resposta HTTP 502/503 e código interno legível ao estourar.

**Alternatives considered**
- Sem timeout próprio — rejeitado: a conexão seria cortada pela Cloudflare sem
  informação útil.
- Processamento assíncrono com consulta posterior — rejeitado: a resposta de um modelo
  Flash para ~1.000 tokens de saída cabe com folga no limite; complexidade sem ganho.

**Consequences**
O cliente no pendrive trata qualquer 502/503 como sinal para gerar o relatório
determinístico. Se um modelo futuro for lento demais para o limite, esta decisão precisa
ser revista.

---

## TA-ADR-011 — Proibir modelos `muse-spark-*`

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
A tabela de privacidade do OpenCode Go indica que os modelos Muse Spark Contributor
(Meta) usam os prompts e respostas para treinar modelos futuros e não têm retenção zero,
em troca de preço reduzido. Os diagnósticos contêm hostnames, nomes de usuário, caminhos,
software instalado e dados de rede de máquinas de projetos do Grupo.

**Decision**
Nunca configurar modelos `muse-spark-*` no serviço.

**Alternatives considered**
- Permitir pelo custo menor — rejeitado: o custo dos modelos com retenção zero já é
  irrisório para o volume do projeto.

**Consequences**
A lista de modelos aceitos fica restrita aos de retenção zero. O serviço pode validar o
valor de `OPENCODE_GO_MODEL` na inicialização e recusar modelos proibidos.

---

## TA-ADR-012 — Compensar a ausência de branch protection com o pipeline

**Status:** Accepted
**Date:** 2026-09-24
**Module:** Pre-implementation

**Context**
A organização `ITC-Brasil` está no GitHub Free. Em repositório privado nesse plano não
há branch protection, rulesets nem secret scanning; a falta é silenciosa. Dependabot
continua disponível. Deploy keys SSH são bloqueadas, então o servidor clona via
Fine-grained PAT.

**Decision**
Proteger o fluxo pelo pipeline: `gitleaks` no CI, deploy apenas após testes verdes,
Dependabot ativo, fluxo `module/NN-nome` → `develop` → `main` por convenção, e merge
sempre feito pelo responsável, nunca pelo agente.

**Alternatives considered**
- Tornar o repositório público — rejeitado: expõe detalhes da infraestrutura.
- Assinar GitHub Team — rejeitado: custo não justificado para este projeto.

**Consequences**
Um push direto na `main` continua tecnicamente possível e dispararia o deploy; a
disciplina de PR é o controle. O PAT do servidor é somente leitura, para que um token
vazado não permita enviar código à `main`. O primeiro commit exige inspeção manual de
dados sensíveis, já que não há varredura automática no GitHub.

---

## TA-ADR-013 — Usar Windows PowerShell 5.1 sem instalação no host

**Status:** Accepted
**Date:** ~2026-09-04 (retroativo — decisão embutida na Fase 1)
**Module:** 00 (retroativo — Fase 1)

**Context**
A ferramenta roda em máquinas de terceiros, plugada por pendrive, sem permissão para
instalar software e sem deixar rastro. Um script `.bat` puro é fraco para estruturar e
analisar saídas de comandos.

**Decision**
Escrever a ferramenta em Windows PowerShell 5.1, nativo da frota, com um `.bat` de
entrada que contorna a `ExecutionPolicy`, todos os caminhos relativos a `$PSScriptRoot`
e nenhuma escrita fora do pendrive.

**Alternatives considered**
- Script `.bat` puro — rejeitado: sem objetos estruturados, parsing frágil.
- PowerShell 7 — rejeitado: não vem instalado na frota.

**Consequences**
Código restrito à sintaxe e aos cmdlets do 5.1, com limitações próprias (por exemplo,
`Measure-Object -Property` não enxerga chaves de `[ordered]`). O cliente da Fase 2
precisa forçar TLS 1.2 antes de chamar a API.

---

## TA-ADR-014 — Aplicar correções apenas por templates parametrizados com confirmação

**Status:** Accepted
**Date:** ~2026-09-04 (retroativo — decisão embutida na Fase 1)
**Module:** 00 (retroativo — Fase 1)

**Context**
A ferramenta executa ações corretivas em máquinas de alunos, professores e projetos
parceiros, operada por técnicos em ritmo de atendimento.

**Decision**
Toda correção é uma função com parâmetros fixos (encerrar processo, reiniciar serviço,
resetar adaptador de rede, limpar itens do tier `seguro`), com o fluxo mostrar →
confirmar → executar → registrar. Processos críticos (`svchost`, `lsass`, `csrss` e
afins) são recusados mesmo com confirmação.

**Alternatives considered**
- Comandos livres digitados ou gerados — rejeitado: erro de digitação ou de geração
  poderia danificar a máquina do atendimento.

**Consequences**
Novas correções exigem código, não configuração. A IA da Fase 2 nunca executa nada
(TA-ADR-016).

---

## TA-ADR-015 — Usar o hostname como identificador das máquinas

**Status:** Accepted
**Date:** ~2026-09-05 (retroativo — decisão embutida na Fase 1)
**Module:** 00 (retroativo — Fase 1)

**Context**
O número de patrimônio não está gravado em lugar que o Windows ou a ferramenta consigam
ler. As 595 máquinas da frota têm hostname único e definido, independente do projeto.

**Decision**
Usar o hostname como chave de identificação em sessões, histórico e relatórios.

**Alternatives considered**
- Número de patrimônio — rejeitado: não legível pela máquina.
- Número de série do fabricante — rejeitado: legível, mas não é o identificador que a
  equipe usa no dia a dia.

**Consequences**
Renomear uma máquina quebra a continuidade do histórico dela. O histórico centralizado
na API é indexado por hostname.

---

## TA-ADR-016 — A IA correlaciona, prioriza e escreve; nunca decide ações

**Status:** Accepted
**Date:** ~2026-09-05 (retroativo — princípio definido no planejamento)
**Module:** 00 (retroativo — Fase 1)

**Context**
Modelos de linguagem erram, e o dado bruto de uma máquina (milhares de eventos, árvores
de pastas) não cabe num prompt nem é interpretável com confiabilidade.

**Decision**
A IA só recebe dados já filtrados, agrupados e classificados por código determinístico,
e seu papel se limita a correlacionar sinais, ranquear hipóteses e redigir o relatório e
o chamado. Classificação de segurança de limpeza e qualquer ação corretiva ficam no
código, com aprovação do técnico.

**Alternatives considered**
- Agente com execução de comandos de diagnóstico e correção — rejeitado: risco de ação
  indevida em máquina de terceiros e dependência total da qualidade do modelo.

**Consequences**
A Fase 1 funciona completa sem IA. O prompt da API impõe regras explícitas ao modelo
(não inventar dado, tratar `null` como não informado, não sugerir execução automática).

---

## TA-ADR-017 — Ajustar recomendações de limpeza por projeto e sub-perfil

**Status:** Accepted
**Date:** ~2026-09-05 (retroativo — decisão embutida na Fase 1)
**Module:** 00 (retroativo — Fase 1)

**Context**
Nas máquinas de alunos do BSBIA e do QDFM, os arquivos ficam 20 a 30 dias e a limpeza é
recomendada ao fim de cada turma. Nas máquinas de professores e pedagogas desses mesmos
projetos, e nas do SEDET e da CODHAB, arquivos podem ter importância.

**Decision**
O técnico escolhe projeto e sub-perfil no início da sessão, e `config/perfis.json` define
a agressividade da recomendação: sub-perfil aluno admite sugestão de limpeza de fim de
ciclo; professor/pedagoga, SEDET e CODHAB ficam em modo conservador.

**Alternatives considered**
- Política única para toda a frota — rejeitado: agressiva demais para professores e
  projetos parceiros, ou tímida demais para as máquinas de aluno.

**Consequences**
A sessão registra projeto e sub-perfil, e a API deve considerá-los ao redigir as
recomendações. Um novo projeto exige entrada nova em `perfis.json`.

---

## TA-ADR-018 — Versionar o contrato dos JSONs da sessão e subir para 1.1

**Status:** Accepted
**Date:** 2026-09-24 (descoberta — surgiu na implementação do Módulo 00.1)
**Module:** 00.1

**Context**
Os JSONs gravados pelo pendrive (`sessao.json`, `<modulo>.json`, `correcoes.json`) são o
contrato de entrada da API, que o Módulo 03 vai implementar sobre `pendrive/SCHEMA.md`.
As correções do Módulo 00.1 mudam nome, tipo ou significado de campos. Pendrives ainda
não atualizados continuarão gravando 1.0 nas carretas, e sessões antigas podem ser
reenviadas. Sem uma versão explícita, a API não teria como distinguir um
`resumo.recuperavelSeguroBytes: 0` real de um zero causado pelo defeito.

**Decision**
Todo envelope carrega `versaoSchema`, definido num único ponto
(`$script:VersaoSchema` em `pendrive/lib/Util-Sessao.ps1`). A partir do Módulo 00.1 o
valor é `"1.1"`, e cada versão tem uma linha por campo alterado na seção "Histórico de
versões" de `pendrive/SCHEMA.md`.

Campos que mudam de 1.0 para 1.1:

| Campo | Mudança |
|---|---|
| `disco.dados.resumo.recuperavelSeguroBytes`, `revisarBytes` | Semântica: em 1.0 são sempre 0 |
| `disco.dados.discosFisicos[].percentualVidaRestante` → `percentualDesgaste` | Nome (o valor sempre foi `Wear`; TA-ADR-019) |
| `disco.dados.discosFisicos[].smartDisponivel` → `estadoSmart` | Nome e tipo: bool → `completo` / `parcial` / `indisponivel` |
| `disco.dados.unidadeFerramenta` | Novo; a unidade do pendrive sai de `volumes` e `discosFisicos` |
| `disco.dados.itensLimpeza`, `maioresPastasPerfil`, `eventlog.dados.grupos` | Ordem (em 1.0 não saíam ordenados) |
| `eventlog.dados.grupos[].peso`, `nota` | Novos |
| `rede.dados.adaptadores[].apipa` | Semântica: só `true` em adaptador `Up` |
| `sessao.ultimaAtualizacao` | Novo |

Tratamento de sessões 1.0 pela API (a implementar no Módulo 03, numa etapa de
normalização antes de montar o prompt):
- `resumo.*Bytes`: descartar e recalcular a partir de `itensLimpeza`.
- `percentualVidaRestante`: copiar para `percentualDesgaste` sem converter.
- `smartDisponivel`: descartar e derivar `estadoSmart` dos contadores nulos.
- `apipa`: recalcular a partir de `status` e `enderecosIPv4`.
- Volume ou disco USB do próprio pendrive: não há como identificar com segurança. A
  API avisa no relatório que a sessão 1.0 pode incluir o pendrive.
- `ultimaAtualizacao` ausente: usar `inicio + duracaoSegundos` como aproximação.
- Listas: reordenar por `bytes` ou `ocorrencias` na normalização.

Regra de incremento:
- **Minor** (`1.1` → `1.2`): renomear campo, trocar tipo, mudar o significado de um
  valor, acrescentar campo ou mudar a ordem de uma lista. Exige linha no histórico do
  `SCHEMA.md` e regra de normalização da versão anterior na API.
- **Major** (`1.x` → `2.0`): quando a API deixa de conseguir normalizar a versão
  anterior e passa a recusá-la.
- Mudança só de texto (descrição da base curada, mensagem de aviso) não sobe versão.
- Os arquivos de `pendrive/config/` têm `versaoSchema` próprio, com a mesma regra.
  `eventlog-conhecidos.json` foi para 1.1 (ganhou `peso`, `nota` e `fonte`), e os
  demais continuam em 1.0.

**Alternatives considered**
- Corrigir sem versionar — rejeitado: a API não teria como saber se um valor vem de um
  pendrive corrigido ou não, e o zero de disco seria lido como verdadeiro.
- Manter os nomes e mudar só os valores (`smartDisponivel` com string, por exemplo) —
  rejeitado: um consumidor antigo leria `"parcial"` como verdadeiro sem falhar.
  Renomear faz a incompatibilidade aparecer.
- Versão por módulo (`disco.json` 1.1, `rede.json` 1.0) — rejeitado: aumenta as
  combinações a normalizar sem ganho real, porque todos os arquivos de uma sessão saem
  da mesma versão da ferramenta.

**Consequences**
O Módulo 03 precisa da etapa de normalização por versão e de testes com uma sessão 1.0
e uma 1.1. Toda mudança futura em campo consumido pela API passa pelo histórico do
`SCHEMA.md`. `ferramentaVersao` passou a `1.1 (Fase 1)`.

---

## TA-ADR-019 — Gravar `Wear` do SSD como `percentualDesgaste`, sem conversão

**Status:** Accepted
**Date:** 2026-09-24 (descoberta — surgiu na implementação do Módulo 00.1)
**Module:** 00.1

**Context**
`pendrive/modulos/Coleta-Disco.ps1` gravava `MSFT_StorageReliabilityCounter.Wear` num
campo chamado `percentualVidaRestante`. A documentação oficial define `Wear` como "The
storage device wear indicator, in percentage", e 100% significa limite estimado de
desgaste atingido (Microsoft Learn, *MSFT_StorageReliabilityCounter class*,
https://learn.microsoft.com/en-us/windows-hardware/drivers/storage/msft-storagereliabilitycounter,
consultado em 2026-09-24). Um SSD novo com `Wear = 3` aparecia como "3% de vida
restante". Um relatório com IA lendo esse campo recomendaria trocar um disco saudável.

**Decision**
O campo passa a se chamar `percentualDesgaste` e recebe `Wear` como vem (0 = novo,
100 = limite). Quando o driver não informa o contador, o valor é `null`, nunca 0.

**Alternatives considered**
- Manter `percentualVidaRestante` e gravar `100 - Wear` — rejeitado: introduz uma
  conversão que a fonte não faz, e um `null` precisaria de tratamento especial para
  não virar 100.
- Manter o nome e só documentar — rejeitado: o nome continuaria induzindo a leitura
  errada em qualquer consumidor.

**Consequences**
A mudança entra no contrato 1.1 (TA-ADR-018). O prompt do relatório (Módulo 03) deve
tratar valor alto como pior. Pela mesma fonte, `temperaturaMaximaC` (`TemperatureMax`)
é a temperatura máxima de operação do dispositivo, não a maior já registrada. Isso está
registrado no `SCHEMA.md`, sem mudança de nome.

---

## TA-ADR-020 — Classificar eventos só por provedor + id, ler Avisos da base e marcar a confiança da fonte

**Status:** Accepted
**Date:** 2026-09-25 (descoberta — surgiu na verificação do Módulo 00.1)
**Module:** 00.1

**Context**
A coleta real do Módulo 00.1 mostrou três problemas em
`pendrive/modulos/Coleta-EventLog.ps1` e `pendrive/config/eventlog-conhecidos.json`:
- `Find-EventoConhecido` aceitava o id sozinho quando ele era único na base, e por isso
  `Microsoft-Windows-Perflib 1000` recebeu a descrição de `Application Error 1000`.
- O coletor só lia os níveis Crítico e Erro (`Level = 1, 2`). O `disk 51` é registrado
  como Aviso no Windows 10/11 (53 ocorrências em 30 dias na máquina de desenvolvimento)
  e nunca chegava ao `eventlog.json`, apesar do peso `alto`.
- Cinco entradas herdadas da Fase 1 não têm fonte oficial, e a descrição do `volmgr 162`
  contradiz a única referência encontrada.

**Decision**
- Um evento só é `conhecido` quando provedor **e** id batem com a base (sem diferenciar
  maiúsculas). Qualquer outro caso fica `conhecido: false`, sem descrição.
- O coletor lê Crítico e Erro de qualquer provedor e Aviso (`Level = 3`) **somente** para
  os pares provedor + id da base (`Select-EventosDaBase`). Cada grupo grava em `nivel` o
  mais grave registrado (`critico`, `erro` ou `aviso`), e `dados.avisoSomenteBase: true`
  deixa a regra explícita no JSON.
- Toda entrada da base tem `fonteOficial` (`true` quando `fonte` aponta para uma página
  oficial da Microsoft). O coletor copia o campo para `grupos[].fonteOficial`. **O prompt
  do relatório (Módulo 03) deve tratar os grupos com `fonteOficial: false` com confiança
  menor**: citar o evento e a contagem, sem afirmar causa nem recomendar ação só com base
  na descrição da base.
- O `volmgr 162` passa a ter descrição neutra, `acaoSugerida: null` e peso `baixo` até a
  revisão com fonte oficial, que é pendência antes do Módulo 03.
- WHEA-Logger 17/19 (Aviso, erro de hardware corrigido) não entram na base: só existem
  tópicos do Microsoft Q&A, que o critério da base não aceita como fonte.

**Alternatives considered**
- Manter o fallback por id — rejeitado: o mesmo id em outro provedor é outro evento, e a
  descrição errada chega à IA como fato.
- Ler todos os Avisos dos logs System e Application — rejeitado: multiplica o volume do
  `eventlog.json` com eventos sem significado para o diagnóstico, sem descrição nem peso.
- Remover as entradas sem fonte — rejeitado: disk 7 e BugCheck 1001 são sinais relevantes
  de falha. Marcar a confiança preserva o sinal sem tratá-lo como confirmado.

**Consequences**
O contrato 1.1 (TA-ADR-018) ganha `niveisAnalisados` com `aviso`, `avisoSomenteBase`,
`grupos[].fonteOficial` e a semântica exata de `conhecido`. Um Aviso novo só passa a ser
coletado quando entra na base com fonte. Sessões 1.0 podem ter grupos classificados só
pelo id: na normalização, a API deve refazer a classificação pelo par exato. O Módulo 03
precisa de uma regra no prompt para `fonteOficial: false`.

---

## TA-ADR-021 — Contar requisições por token no SQLite, em janela fixa de uma hora UTC

**Status:** Accepted
**Date:** 2026-09-28
**Module:** 02

**Context**
A §6.2 exige um limite de requisições por token (`RATE_LIMIT_PER_TOKEN_PER_HOUR`, 60 por
padrão) antes da chamada ao OpenCode Go. O limite protege a cota do Go e contém um token
vazado que dispare diagnósticos em loop. O container roda com `restart: always`
(`api/docker-compose.yml`), então o processo pode reiniciar a qualquer momento, inclusive
em loop, se uma requisição derrubar o processo. A API e a CLI de tokens escrevem no
mesmo arquivo SQLite.

**Decision**
Contar no SQLite, na tabela `tokens_uso` (`token_id` como chave, `janela`, `contagem`),
em janela fixa por hora cheia UTC (`%Y-%m-%dT%H`), com um único upsert
`INSERT ... ON CONFLICT (token_id) DO UPDATE ... RETURNING contagem` feito na mesma
transação `BEGIN IMMEDIATE` que valida o token e grava o `ultimo_uso`
(`api/app/auth.py`). Acima do limite, a resposta é
`429 {"erro": "limite_excedido"}`, com `Retry-After` em segundos até a próxima hora
cheia. O `CMD` do `api/Dockerfile` continua sem `--workers`.

**Alternatives considered**
- Contador em memória no processo — rejeitado: **um crash em loop zera o limite a cada
  restart.** Com `restart: always`, uma requisição que derruba o processo e é reenviada
  dispara um restart por tentativa, e cada restart devolve a cota cheia ao token. É
  justamente o caso de abuso que o limite existe para conter. Também exigiria um worker
  só, para o contador não ser dividido entre processos.
- Janela deslizante (log de horários por token) — rejeitada: exige uma linha por
  requisição e limpeza periódica. A precisão extra não compensa a 60 por hora.
- Biblioteca de rate limit (`slowapi` ou equivalente) — rejeitada: dependência nova para
  um upsert de uma instrução, e o armazenamento padrão dela é em memória.

**Consequences**
- O limite sobrevive a restart e a crash em loop, e continuaria correto com vários
  workers.
- A tabela tem uma linha por token e não cresce: a janela nova sobrescreve a anterior.
- Toda requisição autenticada é uma escrita no SQLite. A 60 por hora por carreta, o
  custo é irrelevante. As escritas concorrentes da API e da CLI esperam o lock por até
  5 s (`BUSY_TIMEOUT_SECONDS` em `api/app/db.py`) em vez de falhar com
  `database is locked`.
- Janela fixa permite uma rajada de até 2× o limite na virada da hora (60 às 14:59 e 60
  às 15:00). É aceito.
- Requisições recusadas antes do token (`413`, `401`) não contam. A que passa do limite
  conta e atualiza o `ultimo_uso`.
- O `CMD` segue sem `--workers`, agora porque o SQLite aceita um escritor por vez: mais
  workers não aumentariam a vazão de escrita e só aumentariam a espera pelo lock.
  O limite, em si, já não depende disso.

---

## TA-ADR-022 — Manter na API uma cópia da base de Event Log para normalizar sessões 1.0

**Status:** Accepted
**Date:** 2026-09-28 (descoberta — surgiu na implementação do Módulo 03)
**Module:** 03

**Context**
O TA-ADR-020 exige que a API refaça a classificação dos grupos de eventos das sessões 1.0
pelo par exato provedor + id, porque o pendrive 1.0 aceitava o id sozinho (o `Perflib
1000` recebia a descrição do `Application Error 1000`). Para isso a API precisa da base
curada, que vive em `pendrive/config/eventlog-conhecidos.json`. A imagem da API é
construída com contexto `api/` (`api/docker-compose.yml`, `build: .`) e copia só
`api/app`, e o pytest oficial monta só `api/` no container. Nenhum dos dois enxerga
`pendrive/`.

**Decision**
A API carrega a própria cópia, `api/app/eventlog-conhecidos.json`, idêntica à do pendrive,
em `api/app/normalizacao.py` (`BASE_EVENTOS`). Ela só é usada para normalizar sessões
1.0: numa sessão 1.1 a classificação do pendrive é mantida. O CI do Módulo 05 compara os
dois arquivos como JSON e falha se forem diferentes.

**Alternatives considered**
- Construir a imagem com o contexto na raiz do repositório — rejeitado: muda o
  `Dockerfile`, o compose, o `.dockerignore` e o comando oficial do pytest, e manda o
  `pendrive/` inteiro para o contexto de build do servidor.
- Manter a classificação que veio na sessão 1.0 — rejeitado: é justamente o defeito que o
  TA-ADR-020 corrigiu, e a descrição errada chegaria à IA como fato.
- Um script que gere a cópia no build — rejeitado: mais uma etapa para lembrar, com o
  mesmo resultado da comparação no CI.

**Consequences**
Toda mudança na base exige alterar os dois arquivos no mesmo commit. Até o CI do Módulo
05 existir, a igualdade é conferida só por `test_api_base_has_the_pendrive_entries`
(`api/tests/test_normalizacao.py`), que checa 17 entradas e a presença do `volmgr 162`,
não o conteúdo completo. Uma sessão 1.0 normalizada recebe as descrições da base atual,
inclusive a neutra do `volmgr 162`, e não as da Fase 1.

---

## TA-ADR-023 — Tirar do prompt identificadores que não servem ao diagnóstico

**Status:** Accepted
**Date:** 2026-09-28 (descoberta — surgiu na implementação do Módulo 03)
**Module:** 03

**Context**
A sessão inteira é enviada ao OpenCode Go, um provedor externo. O TA-ADR-003 aceitou o Go
pela retenção zero dos modelos MiMo/GLM/Qwen/DeepSeek, mas a sessão carrega dados que o
laudo não usa: a conta que executou a ferramenta (`usuarioLogado`, que em 1.0 e 1.1 é
`$env:USERNAME`, a conta que elevou), o número de série (`maquina.numeroSerie`) e o MAC
de cada adaptador (`rede.dados.adaptadores[].macAddress`).

**Decision**
`api/app/prompt.py` remove recursivamente as chaves `usuarioExecucao` (o `usuarioLogado`
normalizado), `numeroSerie` e `macAddress` antes de montar a mensagem
(`FORA_DO_PROMPT`). O SQLite guarda a sessão normalizada completa, com esses campos. O
hostname e os caminhos de arquivo continuam no prompt.

**Alternatives considered**
- Enviar a sessão completa — rejeitado: expõe ao provedor dados sem uso no laudo, e a
  retenção zero é uma política do provedor, não uma garantia técnica nossa.
- Anonimizar também hostname e caminhos (`C:\Users\<nome>\...`) — rejeitado: o hostname
  é a chave do histórico (TA-ADR-015) e o técnico precisa dos caminhos reais para entender a
  recomendação de limpeza.

**Consequences**
O laudo não consegue citar serial nem MAC; quem precisar deles consulta
`diagnosticos.dados`. O `usuarioSessao` do contrato 1.2 (Módulo 07), que é o usuário
logado na máquina, entra no prompt. Uma chave nova com dado pessoal precisa entrar em
`FORA_DO_PROMPT` quando surgir no contrato.

---

## TA-ADR-024 — Espelho e alertas em thread do próprio processo, com estado no SQLite

**Status:** Accepted
**Date:** 2026-09-28
**Module:** 04

**Context**
A §6.6 pede um espelho no NocoDB assíncrono, tolerante a falha, com pendentes e reenvio,
e a §6.7 pede alertas ntfy com limitação de repetição. Nenhum dos dois pode atrasar nem
mudar a resposta ao pendrive, que tem no máximo 100 s pelo túnel (TA-ADR-010) e já espera
até 60 s pelo Go. O container roda um processo uvicorn só (TA-ADR-021) e reinicia com
`restart: always`.

**Decision**
- O estado fica no SQLite: `relatorios.espelho_status`/`espelho_tentativas`/`espelho_erro`
  para o espelho e a tabela `alertas` (chave, último envio, suprimidos) para a repetição
  (migração `0003_20260928_espelho_alertas.sql`).
- O trabalho roda em thread daemon do próprio processo (`tarefas.em_thread`), disparada
  depois da resposta pronta: espelho depois de cada relatório, alerta em falha da IA e em
  token revogado. Um laço `asyncio` no `lifespan` (`repetir_espelho`) reenvia os pendentes
  a cada `NOCODB_RETRY_SECONDS`.
- A decisão de enviar um alerta é gravada no SQLite **antes** do envio, na mesma
  transação que confere o último envio da chave (`ntfy.reservar`).

**Alternatives considered**
- Fila externa (Redis, RQ, Celery) — rejeitado: mais um serviço no glpi-srv para um
  volume de dezenas de relatórios por dia.
- `BackgroundTasks` do FastAPI — rejeitado como mecanismo único: não roda quando a
  dependência levanta exceção, e o alerta de token revogado nasce justamente num `401`.
- Contador de repetição em memória — rejeitado pelo mesmo motivo do TA-ADR-021: um restart
  zera o controle e uma tempestade de falhas manda uma mensagem por tentativa.
- Gravar o envio só depois que o ntfy aceitar — rejeitado: duas threads na mesma
  tempestade mandariam o mesmo alerta; a reserva antes do envio fecha a corrida.

**Consequences**
- Um restart no meio de um envio perde só aquela tentativa: o pendente continua
  `pendente` e o laço reenvia.
- Com o ntfy fora do ar, o alerta reservado se perde por uma janela de
  `NTFY_REPEAT_MINUTES`. É aceito para um canal de alerta.
- O `threading.Lock` do espelho só protege um processo. Subir `--workers` exige uma coluna
  de reserva por linha antes, sob pena de enviar a mesma linha duas vezes.
- O NocoDB pode receber duplicata se a API cair entre o `200` e o `UPDATE`; a coluna
  `DiagnosticoId` identifica.

---

## TA-ADR-025 — Gerar o lock das dependências da API com `pip-compile` a partir de `requirements.in`

**Status:** Accepted
**Date:** 2026-09-28 (descoberta — surgiu na operação do Dependabot depois do Módulo 05)
**Module:** fora de módulo (branch `chore/requirements-pip-compile`)

**Context**
O `api/requirements.txt` fixava com `==` as 5 dependências diretas e as 13 transitivas,
lidas do `pip freeze`, e o `api/requirements-dev.txt` fazia o mesmo com o pytest. Para o
Dependabot, todo pacote listado num manifesto é dependência explícita: "All dependencies
explicitly defined in a manifest are kept up to date by version updates" (GitHub Docs,
*Dependabot options reference*,
https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference,
consultado em 2026-09-28). Ele então abria um PR por transitiva. Os PRs #10 e #12 subiram
só o `pydantic_core` para 2.49.0 e falharam no CI com `ResolutionImpossible`, porque o
`pydantic==2.13.5` exige a versão exata do core. O grupo `pydantic` do #11 não resolveu:
o #12 já veio pelo grupo, mas de novo só com o `pydantic-core`. Nenhum desses PRs pode ser aceito, e fechá-los toda semana esconde as
atualizações úteis.

**Decision**
- `api/requirements.in` lista só as 5 diretas, com `==` nas versões atuais. O
  `api/requirements.txt` é o lock gerado por
  `pip-compile --strip-extras --output-file=requirements.txt requirements.in`, com o
  cabeçalho e as anotações `# via` que ele escreve, e nunca é editado à mão.
- O lock de testes segue o mesmo modelo: `api/requirements-dev.in` com
  `-c requirements.txt`, `-r requirements.in` e `pytest==9.1.1`, compilado para
  `api/requirements-dev.txt`. O `-c` mantém cada pacote comum na versão do lock da API.
- O `pip-compile` roda dentro de `python:3.12.14-slim-trixie`, a imagem do `Dockerfile` e
  do CI, com `pip-tools==7.5.3`, a versão que o Dependabot declara suportar (GitHub Docs,
  *Dependabot supported ecosystems and repositories*,
  https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories,
  linha "pip-compile | `pip` | 7.5.3", consultado em 2026-09-28), e com `click==8.1.8`
  no ambiente da ferramenta. Com o `click` 8.5 que o pip instala junto, o `pip-tools`
  7.5.3 grava um `--no-index` falso no comando do cabeçalho.
- O grupo `pydantic` sai do `.github/dependabot.yml`.

A documentação oficial lista o `pip-compile` com suporte a version updates no ecossistema
`pip`, sem descrever o mecanismo. O código do Dependabot confirma o tratamento:
`python/lib/dependabot/python/file_updater.rb` do `dependabot/dependabot-core` escolhe o
resolvedor `:pip_compile` quando o repositório tem arquivos `.in` e regenera os `.txt`
compilados a partir deles.

**Alternatives considered**
- Manter o grupo `pydantic` (#11) — rejeitado: o #12 saiu pelo grupo e mesmo assim só com o
  core, porque o Dependabot trata cada pino como dependência explícita, e cada par direta/transitiva com versão exata exigiria outro grupo.
- Ignorar as transitivas no Dependabot (`ignore` por nome ou `allow` só das diretas) —
  rejeitado: com todas no mesmo `requirements.txt`, o Dependabot não distingue direta de
  transitiva; seria uma lista manual de 13 nomes a manter, e uma transitiva vulnerável
  ficaria sem PR.
- `uv pip compile` — rejeitado: gera o mesmo formato, mas acrescenta uma ferramenta nova
  ao fluxo sem ganho para 18 pacotes, e o Dependabot trata `uv` como outro gerenciador
  (`uv.lock`), não como compilador de `requirements.in`.

**Consequences**
- As versões não mudaram: o lock gerado tem as mesmas 18 (API) e 23 (testes) versões de
  antes. Só a grafia foi normalizada pelo `pip-compile` (`pydantic_core` → `pydantic-core`,
  `typing_extensions` → `typing-extensions`, `Pygments` → `pygments`).
- O Dependabot passa a abrir PRs das diretas, com o lock recompilado, e uma transitiva
  sobe junto com a direta que a exige.
- Adicionar ou atualizar dependência à mão exige editar o `.in` e rodar o comando do
  `CLAUDE.md`. Editar só o `.txt` é desfeito na próxima compilação.
- O `Dockerfile` e o CI não mudaram: continuam instalando o `requirements.txt` e o
  `requirements-dev.txt`.
- Se o `pip-tools` do Dependabot mudar de versão, o cabeçalho gerado por ele pode diferir
  do nosso; o conteúdo do lock é o que importa.

---

## TA-ADR-026 — Pedir raciocínio baixo ao modelo e limitar o tamanho do laudo

**Status:** Accepted
**Date:** 2026-09-29 (descoberta — medição com sessão real no servidor)
**Module:** fora de módulo (branch `fix/ia-latency`)

**Context**
O relatório tem de sair antes do corte de cerca de 100 s da Cloudflare (TA-ADR-010), e o
`OPENCODE_GO_TIMEOUT_SECONDS` aceita no máximo 90 s (`api/app/config.py`). A primeira
medição com uma sessão real, feita pelo responsável no servidor, estourou os dois:

| Configuração | Prompt | Saída | Raciocínio | Tempo |
|---|---|---|---|---|
| `mimo-v2.6-flash`, padrão do provedor | 12.543 tokens | 9.002 tokens | 5.344 tokens | 126,7 s |
| `mimo-v2.6-flash`, `reasoning_effort: "low"` | 12.543 tokens | 4.934 tokens | 2.085 tokens | 62,2 s |

Sessão da máquina RESERVA-06. O tempo cresce com os tokens de saída, e mais da metade da
saída no padrão era raciocínio. O provedor aceitou o campo `reasoning_effort` no corpo
da requisição compatível com OpenAI.

**Decision**
- `api/app/services/opencode_go.py` envia `reasoning_effort` no corpo, com o valor de
  `OPENCODE_GO_REASONING_EFFORT` (padrão `low`). Vazio não envia o campo e deixa o padrão
  do provedor.
- `api/app/prompts/relatorio.md` limita o laudo: no máximo cerca de 700 palavras no
  `relatorio_md`, no máximo 4 hipóteses, evidência em uma ou duas linhas e sem repetir o
  Resumo nas outras seções. As regras sobre os dados (§6.4, TA-ADR-019 e TA-ADR-020) não
  mudaram.
- Medição em produção depois do deploy (2026-09-29, mesma sessão RESERVA-06,
  `reasoning_effort: low` e o limite de tamanho): **75 s**, com 13.117 tokens de entrada
  e 3.722 de saída. A decisão se mantém: o tempo cabe nos 90 s permitidos, com cerca de
  25 s de margem sobre o corte da Cloudflare, desde que o `OPENCODE_GO_TIMEOUT_SECONDS`
  do servidor esteja acima de 75 (o padrão de 60 não basta). O `timeoutSegundos` do
  pendrive passou de 90 para 120 (`pendrive/config/api.example.json`).

**Alternatives considered**
- Subir o timeout — rejeitado: o teto de 90 s da configuração existe por causa do corte
  de cerca de 100 s da Cloudflare, e os 126,7 s medidos passam dos dois. Nenhum valor
  permitido cobre o caso.
- Trocar de modelo (`glm-5.3-flash`, `qwen3.8-flash`, `deepseek-v4.1-flash`, previstos
  na §7) — rejeitado por ora: exige nova avaliação da qualidade do laudo em português e da
  aderência ao formato JSON. O parâmetro resolveu o tempo com o modelo já avaliado, e a
  troca continua possível só pela variável `OPENCODE_GO_MODEL`.
- Streaming da resposta — rejeitado: mantém a conexão ativa pela Cloudflare, mas não reduz
  o tempo total. Exigiria no pendrive (PS 5.1, `Invoke-WebRequest`) um cliente que leia
  eventos aos poucos, e o timeout do servidor ainda teria de cobrir a geração inteira.

**Consequences**
- O tempo medido com `low` (62,2 s) fica abaixo dos 90 s permitidos, mas acima do
  padrão de 60 s do `OPENCODE_GO_TIMEOUT_SECONDS`. O limite de tamanho do prompt deve
  reduzir a saída; a nova medição com a mesma sessão, depois do deploy, confirma se 60 s
  bastam ou se o `.env` do servidor precisa de um valor entre 60 e 90.
- Com menos raciocínio, a qualidade da correlação pode cair. A medição depois do deploy
  compara o laudo com o anterior.
- Se o provedor ou um modelo futuro recusar o campo, `OPENCODE_GO_REASONING_EFFORT=` (vazio)
  volta ao comportamento anterior sem mudar código.

---

## TA-ADR-027 — NocoDB como fonte dos cadastros do Bench, lido pela API

**Status:** Accepted (revisa o TA-ADR-005, sem editá-lo)
**Date:** 2026-11-04
**Module:** 05 do ITC Bench

**Context**
O TA-ADR-005 fez do SQLite a fonte da verdade e do NocoDB um espelho só de ida dos
diagnósticos. O ADR-006 do Bench fez do NocoDB a fonte da verdade de Servidores, Instaladores,
WiFi e Unidades, entregues pela API (ADR-014 do Bench).

**Decision**
Para esses quatro cadastros o NocoDB é a fonte da verdade e a API só lê, com um token de
usuário Viewer só na base "ITC Bench" (`NOCODB_CADASTROS_TOKEN`). Diagnósticos e relatórios
continuam com o SQLite como fonte e espelho só de ida, com token próprio (Editor, só na base
dos relatórios, separada da "ITC Bench"). A API não guarda cadastros no SQLite: cópia só em
memória. O Bench e as carretas continuam sem acesso ao NocoDB. O espelho dos relatórios é
ligado no deploy do Módulo 05 (decisão do responsável, 04/11/2026).

**Alternatives considered**
- Copiar os cadastros para o SQLite — segredo em mais um disco e duas fontes em conflito.
- Editar cadastros no SQLite com tela própria — fere o TA-ADR-008.
- Um token para espelho e leitura — o de escrita leria os segredos de Wi-Fi.

**Consequences**
NocoDB fora do ar não derruba relatório nem login; derruba só a renovação dos cadastros,
coberta pela cópia defasada na API (até 24 h) e pelo cache do Bench (7 dias).

---

## TA-ADR-028 — Diagnóstico do Bench sem token de carreta, com limite por técnico e envio idempotente

**Status:** Accepted (revisa o TA-ADR-023 para `origem: "bench"`)
**Date:** 2026-11-04
**Module:** 06 do ITC Bench

**Context**
O ADR-016 do Bench manda o diagnóstico pela sessão do técnico. A tabela `diagnosticos` exige
`token_id` e `carreta`. O laudo leva até ~75 s e o túnel corta em ~100 s: um corte depois de
gravado faz o Bench reenviar.

**Decision**
- Migração `0006` reconstrói `diagnosticos` numa transação: `token_id` aceita nulo (CHECK:
  `token_id` ou `bench_usuario`; `carreta` continua `NOT NULL`, `'BANCADA'` no Bench), colunas `bench_usuario`, `bench_sessao_id`, `unidade`,
  `envio_id` (UNIQUE) e `processando_desde`. Ids e `relatorios.diagnostico_id` mantidos; nenhuma
  coluna removida ou renomeada.
- `POST /v1/bench/relatorio`: sessão; `envio_id` UUID (`422` se não for); limite por técnico em
  `bench_relatorio_uso` (upsert do TA-ADR-021); `unidade` validada contra as Unidades ativas da
  cópia de cadastros, senão nula com log; `carreta = 'BANCADA'`.
- **Idempotência:** mesmo `envio_id` com relatório → devolve o gravado; com `falha` → nova
  tentativa da IA na mesma linha; em processamento há menos de 120 s → `409 em_processamento`
  sem chamar a IA; mais antigo → falha presumida, nova tentativa.
- **Fora do prompt:** `coletadoPor` e `bench_usuario` entram em `FORA_DO_PROMPT`.
- **Revisão do TA-ADR-023:** para `origem: "bench"` os caminhos de perfil chegam como
  `%PERFIL%\…` e sem nome de arquivo, porque a Limpeza (Módulo 13 do Bench) lê os nomes
  localmente. A carreta segue como está.

**Alternatives considered**
- Linha-sentinela em `carretas_tokens` — "token" falso em `tokens list`.
- Limite por sessão — novo login zeraria.
- Lock em memória por `envio_id` — não sobrevive a restart nem a vários workers.

**Consequences**
Backup do SQLite antes do deploy, com restauração documentada em `docs/api/DEPLOY.md`.

## TA-ADR-029 — Instaladores vira a lista de programas do Bench: seis colunas e validação por `Tipo`

**Status:** Accepted (estende o TA-ADR-027)
**Date:** 2026-11-06
**Module:** 10 do ITC Bench

**Context**
O ADR-020 do Bench junta instaladores, pacotes do winget e Web Apps numa lista só. A API lê de
`Instaladores` uma lista fixa de colunas; colunas novas não chegariam ao Bench.

**Decision**
- `Instaladores` ganha `Tipo`, `Categoria`, `Identificador`, `Argumentos`, `Deteccao` e `Modo`,
  entregues como texto (`tipo`, `categoria`, `identificador`, `argumentos`, `deteccao`, `modo`).
  Vazio de `Tipo`, `Categoria` e `Modo` vira `instalador`, `Programas` e `quiosque`.
- Linha descartada (log com tabela, `Id` e motivo, sem valor): `tipo_invalido`,
  `categoria_invalida`, `modo_invalido` e `identificador_invalido` (winget sem ID no formato;
  Web App sem `https://` com host).
- O resto continua como no TA-ADR-027 (`SHA256` inválido vira vazio; o Bench recusa).
- A rota e o formato só ganham campos; nada sai nem muda de nome. Sem migração (o SQLite não
  guarda cadastros).

**Alternatives considered**
- Tabela nova no NocoDB — variável e token a mais para o mesmo conceito.
- Repassar as colunas sem validar — o cadastro errado só apareceria na bancada.

**Consequences**
Deploy da API antes do app novo; o Bench antigo ignora os campos novos.

---

## TA-ADR-030 — `Tipo = papel` em Instaladores para o papel de parede do Bench

**Status:** Accepted (estende o TA-ADR-029)
**Date:** 2026-11-06
**Module:** 12 do ITC Bench

**Context**
O ADR-022 do Bench aplica um papel de parede que vem do cadastro, com hash conferido, como os
instaladores. A API só aceita `instalador`, `winget` e `webapp`.

**Decision**
- `Tipo` aceita `papel`. A linha exige `Arquivo` terminado em `.jpg`, `.jpeg` ou `.png`, `SHA256`
  com 64 hexadecimais e `Link` `https://` com host; senão é descartada com `papel_invalido` (log
  com tabela, `Id` e motivo, sem valor).
- Formato e rota iguais; sem migração.

**Alternatives considered**
- Tabela nova — variável e token a mais para uma linha.
- `Tipo = instalador` com nome fixo — Programas a mostraria como instalador.

**Consequences**
Deploy da API antes do app novo. O Bench do Módulo 11 mostra a linha `papel` em Programas como
"Tipo desconhecido", sem instalar, até o app do 12 chegar.

## TA-ADR-031 — Revisão do Módulo 14 do Bench: limite de login atômico e GLPI em `http://` aceito

**Status:** Accepted
**Date:** 2026-11-07
**Module:** 14 do ITC Bench

**Context**
A auditoria do Módulo 04 registrou que o limite de tentativas do login era conferido e contado em
transações separadas: tentativas em paralelo passavam do limite. O login fala com o GLPI em
`http://` interno desde o TA-ADR do login.

**Decision**
- **Correção de bug, sem regra nova:** conferir e reservar a tentativa na mesma `BEGIN IMMEDIATE`;
  o lock não fica preso durante a chamada ao GLPI. A tentativa reservada é devolvida quando o
  GLPI aceita (a do IP; a do usuário é zerada como antes) ou está fora do ar. Os limites, a janela
  e o alerta não mudam. Teste `test_tentativas_em_paralelo_nao_passam_do_limite`.
- **GLPI em `http://` interno: risco aceito** até o GLPI ter certificado; quando tiver, a API
  passa a exigir `https` (decisão do responsável no Módulo 14).
- `certifi` 2026.10.23 (PYSEC-2026-4320), só ele no lock (TA-ADR-025).
- `test_rotas_auth.py`: toda rota exige token ou sessão, menos a lista fechada (saúde, login,
  logout).

**Alternatives considered**
- Segurar o lock durante a chamada ao GLPI — trava toda escrita da API por até 10 s.
- Lock por chave em memória — não vale com mais de um worker.

**Consequences**
Deploy da API depois do merge (`api-deploy.yml`). Uma tentativa em andamento conta para o limite
enquanto o GLPI responde.

---

## TA-ADR-032 — Lock da API com hash e instalação com `--require-hashes`

**Status:** Accepted
**Date:** 2026-11-08
**Module:** Bench 15 (pendência deixada pela revisão do Módulo 14)

**Context**
O lock do TA-ADR-025 fixa versões com `==`, mas não o conteúdo: um pacote republicado ou um
espelho alterado com a mesma versão seria instalado no container e no CI sem aviso.

**Decision**
- `api/requirements.txt` e `api/requirements-dev.txt` passam a ser gerados com
  `pip-compile --generate-hashes` (mesma imagem, `pip-tools==7.5.3` e `click==8.1.8` do
  TA-ADR-025). As versões não mudaram na regeneração.
- O `Dockerfile` e o `api-ci` instalam com `--require-hashes`: pacote sem hash ou com hash
  diferente do lock não instala.
- O comando de lock e o de testes do `AGENTS.md` incluem as duas opções.

**Alternatives considered**
- Só `==` (como estava) — não detecta artefato trocado com a mesma versão.
- `uv pip compile` na API — troca a ferramenta que o Dependabot entende (TA-ADR-025).

**Consequences**
Deploy da API depois do merge (`api-deploy.yml`), porque o `Dockerfile` muda. O Dependabot
regenera o lock com hash, já que lê o comando do cabeçalho do `pip-compile`.

## TA-ADR-033 — Versão do Bench e instalador servidos pela API

**Status:** Accepted
**Date:** 2026-11-08
**Module:** Bench 16 (ADR-026)

**Context**
A atualização automática do Bench precisa de uma fonte de versão e de um lugar para baixar o
instalador sem token nos notebooks, com o repositório privado.

**Decision**
- Migração `0007`: `bench_versoes` (versão, ordem numérica única, mínima, sha256, tamanho, notas,
  manifesto e assinatura em base64, quem e quando publicou e revogou) e `bench_versao_uso`.
- CLI `python -m app.bench_versao publicar|listar|revogar --operador`: confere o formato do
  manifesto, assinatura com 64 bytes (P1363), hash e tamanho do arquivo contra o manifesto e
  versão maior que todas já publicadas (revogadas inclusive). Copia o arquivo para
  `BENCH_VERSOES_DIR` (`/data/bench`, no volume existente) como `setup-<sha256>.exe`. A API não
  confere a assinatura nem vê chave privada: quem confia é o Bench.
- `GET /v1/bench/versao` (sessão do técnico): a mais recente não revogada, ou 204.
- `GET /v1/bench/versao/arquivo?sha256=`: só o instalador da versão servida (404 para outro
  hash), por `FileResponse` do Starlette (206 a `Range`, testado), sem extensão no caminho e com
  `Cache-Control: no-store`.
- Limite por técnico, janela fixa de uma hora: 30 consultas, 3 downloads a partir do byte 0 e
  10 retomadas (`Range` com início > 0), contados em separado: a retomada não gasta o limite de
  download nem vira download ilimitado.

**Alternatives considered**
- Linha em `Instaladores` no NocoDB — editável por mais gente, pela web.
- Arquivo de configuração no servidor — sem histórico nem operador.
- Contar o limite por versão — a janela por tipo cobre o mesmo abuso com uma tabela só.

**Consequences**
Deploy da API depois do merge (migração com backup, `docs/api/DEPLOY.md`). Publicar uma versão é
passo do responsável (`docs/BUILD.md`).
