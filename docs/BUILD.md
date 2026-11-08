# Build, instalador e distribuição — ITC Bench

Decisões em ADR-025. Arquivos: `app/empacotamento/` (PyInstaller e ícone), `instalador/`
(Inno Setup, build, teste de instalação, varredura) e `.github/workflows/app-build.yml`.

## Só o CI gera artefato distribuível

O instalador que vai para os notebooks sai **só** do workflow `app-build`: o artefato do PR
(guardado 7 dias) ou a Release em rascunho criada pela tag `vX.Y.Z`. Um build local pode embutir
caminhos e arquivos da máquina de desenvolvimento (perfil, checkout, DLL achada no `PATH`) e não
passa pelo teste de instalação nem pela varredura do CI. Use build local só para testar.

## Versão

Fonte única: `__version__` em `app/src/itc_bench/__init__.py` (SemVer). Ela vai para o
`VERSIONINFO` do EXE, para o instalador (`/DAppVersion`), para `DisplayVersion` em
`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}_is1`
e para o rodapé do app. A tag tem que ser `v` + essa versão, ou o CI falha.

Release: subir `__version__` num PR, fazer o merge até a `main`, criar a tag `vX.Y.Z` na `main`.
O workflow cria a Release em **rascunho** com o instalador e o `SHA256SUMS`; o responsável confere
e publica.

## Build local (para teste)

Pré-requisitos: uv 0.12.x e o Inno Setup 6.7.4 (do link oficial de
`github.com/jrsoftware/issrc/releases`, conferindo o SHA-256 que está no `app-build.yml`). Pode ser
instalado só para o usuário, em modo portátil:

```
innosetup-6.7.4.exe /VERYSILENT /CURRENTUSER /PORTABLE=1 /DIR=C:\ferramentas\inno
```

Da raiz do repositório, no PowerShell:

```
.\instalador\build.ps1 -Iscc C:\ferramentas\inno\ISCC.exe
```

Saída em `app/dist/`: `ITC Bench\` (pasta do PyInstaller), `itc-bench-X.Y.Z-setup.exe` e
`SHA256SUMS`. O ícone só precisa ser regerado se o símbolo mudar:
`uv --directory app run python empacotamento/gerar_ico.py`.

`instalador/testar.ps1` é o teste do CI: instala, desinstala e apaga
`%ProgramData%\ITC\Bench\protegido`. **Não rode numa máquina de uso.**

## Instalar

Conferir o hash antes:

```
Get-FileHash .\itc-bench-X.Y.Z-setup.exe -Algorithm SHA256
```

Assistente: abrir o instalador, aceitar o UAC e informar o endereço da API na página
"Endereço da API".

Silenciosa (administrador):

```
itc-bench-X.Y.Z-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /APIURL=https://<endereço da API> /LOG=C:\caminho\instalar.log
```

- Instalação nova sem `/APIURL` falha (código ≠ 0). Atualização sem `/APIURL` mantém o endereço
  gravado.
- O endereço precisa ser `https://` com o nome do servidor, sem usuário, senha, query ou
  fragmento. Fica em `HKLM\SOFTWARE\ITC\Bench\ApiUrl`.
- O `/LOG` grava a linha de comando, com o endereço. Não é segredo, mas fica no log.
- Com o Bench aberto, a atualização silenciosa recusa e o assistente pede para fechá-lo. O
  instalador nunca fecha o Bench à força.
- Pasta fixa: `C:\Program Files\ITC\Bench`. Atalho só no Menu Iniciar.

## Trocar o endereço da API sem reinstalar

Rodar o mesmo instalador de novo com o endereço novo (mesma versão, por cima):

```
itc-bench-X.Y.Z-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /APIURL=https://<endereço novo>
```

Ou, num terminal elevado:

```
reg add HKLM\SOFTWARE\ITC\Bench /v ApiUrl /t REG_SZ /d https://<endereço novo> /f
```

O Bench lê o valor ao abrir.

## Desinstalar

Pelo Painel de Controle/Configurações ou, silenciosa:

```
"C:\Program Files\ITC\Bench\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

| Sai | Fica |
|---|---|
| `C:\Program Files\ITC\Bench` | `%ProgramData%\ITC\Bench\logs\` |
| Atalho do Menu Iniciar e chave de desinstalação | `%ProgramData%\ITC\Bench\papel\` e `icones\` (usados pelo papel de parede e pelos atalhos de Web App já aplicados) |
| `HKLM\SOFTWARE\ITC\Bench` (endereço da API) | |
| `%ProgramData%\ITC\Bench\protegido\` (cadastros, login offline, diagnósticos não enviados, `preparacao.json`, instaladores) | |

**A desinstalação não desfaz a preparação da máquina**: contas, Wi-Fi, políticas, programas,
proteção do login e aparência ficam como estão. O assistente avisa antes de continuar; a
silenciosa escreve o aviso no log.

## Assinatura

Sem assinatura por enquanto (ADR-025): o UAC mostra "Editor desconhecido" e o SmartScreen avisa
num arquivo baixado da internet. Confira o `SHA256SUMS`. O passo de assinatura do workflow
está desligado.

## Conferências que o Bench faz quando empacotado

Ao abrir, antes de mexer na máquina: o EXE tem que estar em `Program Files\ITC\Bench`, sem
ponto de reparse, e só SYSTEM, Administradores e TrustedInstaller podem gravar na pasta, no pai
e em tudo dentro. Se falhar: mensagem "A pasta de instalação foi alterada. Reinstale o ITC Bench.",
log e código 3. Variáveis `QT_*`, `QML*` e `PYTHON*` do usuário são ignoradas (aparecem no log
pelo nome).

## Atualização automática (ADR-026)

### Chaves (uma vez)

Duas chaves ECDSA P-256: **principal** (assina as versões) e **reserva** (só se a principal for
perdida ou vazar). Precisa do PowerShell 7.4 ou mais novo (`pwsh`).

```
pwsh -File instalador/gerar-chaves-versao.ps1 -Saida <pasta fora do repositório>
```

- O script pede uma senha por chave (16 caracteres ou mais) e grava `principal.key.pem` e
  `reserva.key.pem` (PKCS#8 cifrado) em `-Saida`. Recusa pasta dentro do repositório.
- As públicas vão para `app/src/itc_bench/recursos/atualizacao/principal.pub` e `reserva.pub`.
  **Quem comita é o responsável**, na branch. Sem as duas comitadas, o build de tag falha.
- Custódia: a principal e a senha dela ficam no cofre de senhas do responsável; a reserva, com a
  senha separada, em mídia cifrada fora de linha. Nenhuma das duas vai para servidor, CI,
  `.conversa/` ou repositório.
- Principal perdida ou vazada: assine a próxima versão com a reserva, gere um par novo, troque a
  `principal.pub` nessa versão e revogue no servidor o que tiver sido assinado indevidamente.

### Publicar uma versão

1. Suba `__version__`, faça a tag `vX.Y.Z` e publique a Release em rascunho do `app-build`.
2. Baixe da Release o `itc-bench-X.Y.Z-setup.exe` e o `SHA256SUMS`.
3. Assine na sua máquina:
   ```
   pwsh -File instalador/assinar-versao.ps1 -Instalador itc-bench-X.Y.Z-setup.exe -Sha256Sums SHA256SUMS -Minima X.Y.Z -Notas "texto curto" -Chave <pasta>\principal.key.pem -Saida <pasta>
   ```
   `-Minima` acima da versão instalada torna a atualização obrigatória. Saem `manifesto.json` e
   `manifesto.sig`.
4. Copie os três arquivos para o servidor e publique (`docs/api/API.md`):
   ```
   docker exec -it tecnico-api python -m app.bench_versao publicar --arquivo <setup.exe> --manifesto <manifesto.json> --assinatura <manifesto.sig> --operador <nome>
   ```
5. Revogar: `python -m app.bench_versao revogar --versao X.Y.Z --operador <nome>`. A rota volta a
   servir a anterior não revogada; quem já instalou a revogada não volta (o Bench não rebaixa).

### O que o técnico vê

Depois do login online o Bench consulta, baixa e confere em segundo plano. A faixa no alto mostra
a versão e as notas: "Instalar ao fechar" ou "Agora não" (obrigatória: só "Fechar e atualizar
agora"). Com Preparação em andamento ou retomada pendente, o Bench fecha sem atualizar. O
instalador espera o Bench sair e roda silencioso, mantendo o endereço e `protegido\`.

### Atualização falhou

- Log do Inno: `%ProgramData%\ITC\Bench\protegido\atualizacao\inno-X.Y.Z.log` (só
  administrador lê). O Bench avisa ao abrir e tenta nos próximos fechamentos, até 3 vezes.
- Se a falha foi no meio da cópia, a pasta interna da versão anterior já foi apagada e o Bench
  não abre: rode o instalador do CI por um administrador (upgrade por cima mantém `ApiUrl` e
  `protegido\`). O instalador recusa versão menor que a instalada; a mesma versão é aceita
  (reparo).
