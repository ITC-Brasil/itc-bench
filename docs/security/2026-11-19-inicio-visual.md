# Auditoria de segurança — `feat/inicio-visual` (ADR-073)

**Data:** 2026-11-19 · **Prompt:** `docs/security/AUDIT-PROMPT.md` · **Base:** `develop` `82b5d90`
(diff ainda sem commit no clone `itc-bench-git`).

**Resultado:** nenhum achado crítico, alto, médio ou baixo. 2 informativos. Não bloqueia o
fechamento.

## Stack e escopo

App Windows em Python 3.13 + PySide6. A tela Início só lê a máquina (trecho PowerShell fixo
`recursos/inicio/ler.ps1`, só CIM e registro) e abre outras telas. A API não muda.

Arquivos revisados (diff inteiro): `recursos/inicio/ler.ps1`, `servicos/inicio.py`,
`ui/inicio.py`, `ui/indicadores.py`, `ui/tema.py`, `ui/janela.py` (`cabecalho_proprio`, técnico),
os SVG novos em `recursos/icones/` e os testes.

## 1. Banco sem tranca

Não se aplica: nada é gravado em `%ProgramData%\ITC\Bench` nem no cache DPAPI. A leitura do
Início continua só em memória (60 s).

## 2. Permissão definida na tela

Correto. A tela não ganhou ação nova: Atualizar relê; os botões dos alertas e das ações rápidas
só abrem outras telas, que mantêm as próprias verificações; Forçar inventário GLPI continua
desativado sem administrador e passa pelo mesmo `remoto.forcar_inventario`.

## 3. IDOR / dados vindos de fora

Correto. O trecho não recebe entrada (nenhuma variável `ITC_*`, nenhum argumento). Tudo o que
volta é validado em Python: textos cortados em 100 caracteres (nome do computador em 15),
números em faixas fechadas (`_faixa`: carga 0–100, núcleos 1–1024, memória positiva etc.) e
tipo de memória por tabela fechada; o que não casa vira "—". Booleanos não passam por número
(`_int` recusa `bool`).

## 4. Chaves expostas

Correto. Nenhum segredo, endereço ou SSID no diff. Os SVG são traços simples, sem script,
`foreignObject` ou imagem embutida. O log do Início continua só com o nome da leitura e o tipo
do erro (`Início: leitura maquina falhou: …`).

## 5. Inputs sem tratamento

Correto. Todo texto da máquina e da sessão entra em `QLabel` com `Qt.PlainText` (`_label`),
inclusive o login do técnico e o modelo; nada em rich text nem em dica crua (`test_texto_puro`
passa). Nada vai para comando.

## Adendo — Windows 10/11 e saúde da bateria

O trecho passou a rodar `powercfg /batteryreport /xml` pelo caminho fixo do System32, sem
entrada do usuário, com saída num arquivo do TEMP de nome aleatório (GUID), apagado no
`finally`; o XML é lido com `XmlResolver = $null` (sem entidades externas) e só três nós
viram números. Reserva: `root\wmi` (`BatteryStaticData`, `BatteryFullChargedCapacity`), só
leitura. Um outro processo do mesmo usuário poderia, em tese, trocar o XML entre a gravação e a
leitura; o pior efeito seria um número errado no cartão, limitado pelas faixas do Python, sem
execução nem escrita (informativo). As capacidades passam por `_faixa` (1 a 10.000.000 mWh) e a saúde é
limitada a 100%. O rótulo do Windows vem de `EditionID`, `DisplayVersion` e do build (número),
sem texto localizado. Sem achado novo.

## Adendo — leitura automática da Configuração

O Início pede à tela Configuração a mesma leitura do botão Ler situação (`prep.ler_todas`, só
`ler()` de cada etapa); nada é aplicado, e não começa com a tela ocupada. `ui/tarefa.py`:
quando uma tarefa acaba depois de o Bench fechar, o resultado é descartado com uma linha no log
(antes, o aviso para a tela apagada gerava um erro não tratado). Sem achado novo.

## Informativos

- **I1.** O cartão Máquina mostra o nome do computador e o login do técnico da sessão. Os dois
  já apareciam no rodapé e no log da sessão; não há dado novo exposto.
- **I2.** O uso de CPU e de RAM é o do momento da leitura (sem amostra contínua): informativo,
  sem efeito em decisão do Bench.

## Verificação

App: `test_inicio_visual.py` (40 novos) e a suíte completa (1211 passando, 10 pulados, a falha
de ambiente conhecida).
